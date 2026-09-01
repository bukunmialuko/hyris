"""Learner memory: mastery profile + quiz history on a LangGraph store.

All reads degrade to an empty context — memory is an enhancement, not a dependency.
"""

import hashlib
import logging
from urllib.parse import urlparse

from langgraph.store.base import BaseStore

from app.agent.state import LearnerContext
from app.config import get_settings

logger = logging.getLogger(__name__)

# store.search() defaults to limit=10, and BOTH backends apply the limit before returning, in their
# own order (InMemoryStore insertion-order, PostgresStore updated_at DESC). So fetch a generous
# window and decide "most recent" here, where it is explicit and backend-agnostic.
MASTERY_SCAN = 500      # concepts scanned when classifying mastered/weak
HISTORY_SCAN = 1000     # quiz_history rows pulled before the newest-first sort
RECENT_HASHES = 100     # question hashes handed to the planner
CONCEPT_MAX = 80        # a mastery key is a label, not a sentence


def normalize_concept(name: str) -> str:
    """A stable mastery key.

    Mastery is keyed on this string and only counts once the SAME key recurs (settings.min_seen), so
    a label that varies by case, spacing or a trailing full stop silently starts a new concept and
    the learner never accumulates any history. The prompt asks for short canonical labels; this
    makes near-misses land on the same key anyway.
    """
    return " ".join(name.strip().lower().strip(".,;:!?").split())[:CONCEPT_MAX]


def qhash(question: str) -> str:
    return hashlib.sha256(question.lower().strip().encode()).hexdigest()[:12]


def empty_context() -> LearnerContext:
    return LearnerContext(mastered_concepts=[], weak_concepts=[], recent_question_hashes=[])


def load_learner_context(store: BaseStore, user_id: str, page_url: str) -> LearnerContext:
    """Never raises: any failure degrades to an empty context."""
    s = get_settings()
    try:
        domain = urlparse(str(page_url)).netloc
        mastered, weak = [], []
        for item in store.search(("users", user_id, "mastery"), limit=MASTERY_SCAN):
            rec = item.value
            if rec["seen"] < s.min_seen:
                continue
            if rec["score"] >= s.mastered_at:
                mastered.append(item.key)
            elif rec["score"] <= s.weak_at:
                weak.append(item.key)
        # Filter by domain in the query, not in Python: otherwise the limit truncates across every
        # domain first. Then sort explicitly — neither backend's own order is load-bearing.
        history = sorted(
            store.search(("users", user_id, "quiz_history"), filter={"domain": domain}, limit=HISTORY_SCAN),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        hashes = [h for item in history for h in item.value["question_hashes"]]
        return LearnerContext(
            mastered_concepts=mastered, weak_concepts=weak, recent_question_hashes=hashes[:RECENT_HASHES]
        )
    except Exception as e:  # noqa: BLE001 — resilience boundary
        logger.warning("learner memory unavailable (%s): %s", type(e).__name__, e)
        return empty_context()


def record_quiz(store: BaseStore, user_id: str, page_url: str, quiz: dict) -> None:
    """Best-effort write of the quiz's question hashes into history."""
    try:
        store.put(
            ("users", user_id, "quiz_history"),
            quiz["id"],
            {
                "url": page_url,
                "domain": urlparse(str(page_url)).netloc,
                "question_hashes": [qhash(q["question"]) for q in quiz["questions"]],
            },
        )
    except Exception as e:  # noqa: BLE001 — resilience boundary
        logger.warning("learner memory write dropped (%s): %s", type(e).__name__, e)


def update_mastery(store: BaseStore, user_id: str, concept: str, correct: bool) -> dict:
    """EMA mastery update, called when an attempt is submitted."""
    s = get_settings()
    ns = ("users", user_id, "mastery")
    concept = normalize_concept(concept)
    item = store.get(ns, concept)
    rec = item.value if item else {"score": 0.5, "seen": 0, "correct": 0}
    rec["score"] = round((1 - s.mastery_alpha) * rec["score"] + s.mastery_alpha * correct, 3)
    rec["seen"] += 1
    rec["correct"] += int(correct)
    store.put(ns, concept, rec)
    return rec
