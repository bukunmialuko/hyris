"""Node logic. Pure functions where possible (unit-testable without any LLM);
LLM-dependent steps take the model as an argument. Wiring lives in graph.py.
"""

import re
import uuid
from typing import TypedDict

from app.agent.prompts import ANALYZE_SYS, CRIT_SYS, GEN_SYS, wrap_article
from app.agent.state import (
    BASE_BLOOM,
    BLOOM_LADDER,
    Concept,
    LearnerContext,
    QuizQuestion,
    QuizState,
    Slot,
)
from app.agent.tools.memory import normalize_concept, qhash
from app.config import get_settings

# ---------------------------------------------------------------- structured outputs


class PageAnalysis(TypedDict):
    concepts: list[Concept]
    sufficiency_score: float
    max_supportable_questions: int


class QuestionBatch(TypedDict):
    questions: list[QuizQuestion]


class Verdict(TypedDict):
    slot_id: int
    passed: bool
    reason: str


class VerdictBatch(TypedDict):
    verdicts: list[Verdict]


# ---------------------------------------------------------------- analyze_page (LLM)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def analyze_page(llm, clean_text: str, title: str, requested: int) -> QuizState:
    """Concepts + sufficiency. Never raises; failures return {'error': ...}."""
    try:
        out: PageAnalysis = llm.with_structured_output(PageAnalysis).invoke(
            [
                ("system", ANALYZE_SYS.format(n=requested)),
                ("user", f"Title: {title}\n\n{wrap_article(clean_text)}"),
            ]
        )
        text_n = _norm(clean_text)
        grounded = []
        for c in out["concepts"]:
            if _norm(c["supporting_span"]) in text_n:
                c["salience"] = min(1.0, max(0.0, float(c["salience"])))
                # Canonicalise here, at the one place concepts enter the system, so the blueprint,
                # the question's `concept` field and the mastery key are all the same string.
                c["name"] = normalize_concept(c["name"])
                grounded.append(c)
        if not grounded:
            return {"error": "Could not identify quiz-worthy concepts on this page."}
        return {
            "concepts": grounded,
            "sufficiency": min(1.0, max(0.0, float(out["sufficiency_score"]))),
            "max_supportable": max(0, int(out["max_supportable_questions"])),
        }
    except Exception as e:  # noqa: BLE001 — resilience boundary
        return {"error": f"Analysis failed: {e}"}


# ---------------------------------------------------------------- adjust_scope (pure)


def adjust_scope(requested: int, max_supportable: int) -> QuizState:
    s = get_settings()
    final = max(0, min(int(requested), s.hard_cap, int(max_supportable)))
    if final == 0:
        return {"error": "Page does not support any quiz questions.", "final_count": 0}
    note = ""
    if final < requested * s.notable_gap:
        note = (
            f"This page had enough substance for {final} good questions "
            f"(you asked for {requested})."
        )
    return {"final_count": final, "note": note}


# ---------------------------------------------------------------- plan_quiz (pure)


def _levels(base: str, mastered: bool) -> list[str]:
    """Bloom levels for a concept, nearest-first: up the ladder, then down.
    Mastered concepts start one level above the base."""
    i = BLOOM_LADDER.index(base)
    ups, downs = BLOOM_LADDER[i + 1 :], list(reversed(BLOOM_LADDER[:i]))
    order = [base]
    for k in range(max(len(ups), len(downs))):
        if k < len(ups):
            order.append(ups[k])
        if k < len(downs):
            order.append(downs[k])
    return order[1:] + order[:1] if mastered and len(order) > 1 else order


def plan_quiz(
    concepts: list[Concept], ctx: LearnerContext, final_count: int, difficulty: str
) -> list[Slot]:
    """Blueprint: weak concepts first, new next, mastered last (bumped harder);
    variants at other Bloom levels before shrinking. Pure and deterministic."""
    base = BASE_BLOOM.get(difficulty, "apply")

    def bucket(c: Concept) -> int:
        if c["name"] in ctx["weak_concepts"]:
            return 0
        if c["name"] not in ctx["mastered_concepts"]:
            return 1
        return 2

    ranked = sorted(concepts, key=lambda c: (bucket(c), -c["salience"]))
    blueprint: list[Slot] = []
    used: set[tuple[str, str]] = set()
    pass_no = 0
    while len(blueprint) < final_count and pass_no < len(BLOOM_LADDER):
        for c in ranked:
            if len(blueprint) >= final_count:
                break
            levels = _levels(base, bucket(c) == 2)
            if pass_no >= len(levels) or (c["name"], levels[pass_no]) in used:
                continue
            used.add((c["name"], levels[pass_no]))
            blueprint.append(
                Slot(
                    slot_id=len(blueprint),
                    concept=c["name"],
                    bloom_level=levels[pass_no],
                    is_variant=pass_no > 0,
                )
            )
        pass_no += 1
    return blueprint


# ---------------------------------------------------------------- generate (LLM)


def generate_questions(
    llm, clean_text: str, slots: list[Slot], feedback: str = ""
) -> list[QuizQuestion]:
    """One batched call for the given slots. Never raises; failure returns []."""
    try:
        lines = "\n".join(
            f'- slot_id {s["slot_id"]}: "{s["concept"]}" at {s["bloom_level"]}' for s in slots
        )
        user = f"{wrap_article(clean_text)}\n\nSlots:\n{lines}"
        if feedback:
            user += f"\n\nA reviewer rejected earlier attempts. Fix:\n{feedback}"
        out: QuestionBatch = llm.with_structured_output(QuestionBatch).invoke(
            [("system", GEN_SYS), ("user", user)]
        )
        return out["questions"]
    except Exception:  # noqa: BLE001 — the gate will retry or give up
        return []


# ---------------------------------------------------------------- schema gate (pure)


def schema_gate(
    questions: list[QuizQuestion],
    blueprint: list[Slot],
    recent_hashes: list[str],
    allow_repeats: bool = False,
) -> tuple[list[QuizQuestion], list[Slot], str]:
    """(valid, missing_slots, feedback). Deterministic and free.

    Two kinds of rejection, and they are not equally serious. A malformed question can never ship.
    A well-formed question the learner has seen before is only *undesirable* -- and once the retry
    budget is spent, shipping it beats shipping nothing, which is what `allow_repeats` is for. Told
    otherwise, a returning learner on a page they already quizzed gets every question rejected, the
    run finishes with zero questions, and the guard blames the page for their own history.
    """
    recent = set(recent_hashes)
    want = {s["slot_id"] for s in blueprint}
    valid: list[QuizQuestion] = []
    reasons: list[str] = []
    seen: set[str] = set()
    for q in questions or []:
        h = qhash(q.get("question", ""))
        malformed = (
            q.get("slot_id") not in want
            or len(q.get("options", [])) != 4
            or len(set(q["options"])) != 4
            or not 0 <= q.get("correct_answer", -1) < 4
            or h in seen
            or any(v["slot_id"] == q["slot_id"] for v in valid)
        )
        if malformed:
            reasons.append(f"slot {q.get('slot_id')}: invalid or duplicate")
            continue
        if h in recent and not allow_repeats:
            reasons.append(f"slot {q.get('slot_id')}: repeats a question this learner has seen")
            continue
        seen.add(h)
        valid.append(q)
    missing = [s for s in blueprint if s["slot_id"] not in {q["slot_id"] for q in valid}]
    return valid, missing, "; ".join(reasons)


# ---------------------------------------------------------------- critique (LLM)


def critique_questions(llm, clean_text: str, questions: list[QuizQuestion]) -> dict:
    """Per-question verdicts. Fail-open: on critic failure, everything passes
    (a quality gate must not be a single point of failure)."""
    try:
        qlines = "\n\n".join(
            f'slot_id {q["slot_id"]}: {q["question"]}\n'
            + "\n".join(f"  option {i}: {o}" for i, o in enumerate(q["options"]))
            + f'\n  marked correct_answer: {q["correct_answer"]}'
            for q in questions
        )
        out: VerdictBatch = llm.with_structured_output(VerdictBatch).invoke(
            [("system", CRIT_SYS), ("user", f"{wrap_article(clean_text)}\n\nQuestions:\n{qlines}")]
        )
        got = {v["slot_id"]: v for v in out["verdicts"]}
        failed = {sid for sid, v in got.items() if not v["passed"]}
        feedback = "\n".join(f'slot {v["slot_id"]}: {v["reason"]}' for v in got.values() if not v["passed"])
        return {"failed_slot_ids": failed, "feedback": feedback}
    except Exception:  # noqa: BLE001 — fail open
        return {"failed_slot_ids": set(), "feedback": ""}


# ---------------------------------------------------------------- finalize (pure)


def finalize_quiz(
    title: str, note: str, truncated: bool, questions: list[QuizQuestion], blueprint: list[Slot]
) -> dict:
    # The concept lives only in the blueprint, but mastery is tracked per concept -- so it has to
    # travel with the question that tested it, or an attempt cannot say what was learned.
    # blueprint is written once by plan_quiz and never shrinks (critique drops questions, not slots),
    # so every slot_id resolves; a KeyError here would be the correct loud failure.
    slots = {s["slot_id"]: s for s in blueprint}
    return {
        "id": f"quiz_{uuid.uuid4().hex[:12]}",
        "title": title,
        "note": note,
        "truncated": truncated,
        "questions": [
            {**q, "concept": slots[q["slot_id"]]["concept"],
             "bloom_level": slots[q["slot_id"]]["bloom_level"]}
            for q in sorted(questions, key=lambda q: q["slot_id"])
        ],
    }
