"""Learner memory: mastery profile + quiz history on a LangGraph store.

All reads degrade to an empty context — memory is an enhancement, not a dependency.
"""

import hashlib
from urllib.parse import urlparse

from langgraph.store.base import BaseStore

from app.agent.state import LearnerContext
from app.config import get_settings


def qhash(question: str) -> str:
    return hashlib.sha256(question.lower().strip().encode()).hexdigest()[:12]


def empty_context() -> LearnerContext:
    return LearnerContext(mastered_concepts=[], weak_concepts=[], recent_question_hashes=[])


def load_learner_context(store: BaseStore, user_id: str, page_url: str) -> LearnerContext:
    """Never raises: any failure degrades to an empty context."""
    s = get_settings()
    try:
        domain = urlparse(str(page_url)).netloc
        mastered, weak, hashes = [], [], []
        for item in store.search(("users", user_id, "mastery")):
            rec = item.value
            if rec["seen"] < s.min_seen:
                continue
            if rec["score"] >= s.mastered_at:
                mastered.append(item.key)
            elif rec["score"] <= s.weak_at:
                weak.append(item.key)
        for item in store.search(("users", user_id, "quiz_history")):
            if item.value["domain"] == domain:
                hashes.extend(item.value["question_hashes"])
        return LearnerContext(
            mastered_concepts=mastered, weak_concepts=weak, recent_question_hashes=hashes[-100:]
        )
    except Exception:  # noqa: BLE001 — resilience boundary
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
    except Exception:  # noqa: BLE001
        pass


def update_mastery(store: BaseStore, user_id: str, concept: str, correct: bool) -> dict:
    """EMA mastery update, called when an attempt is submitted."""
    s = get_settings()
    ns = ("users", user_id, "mastery")
    item = store.get(ns, concept)
    rec = item.value if item else {"score": 0.5, "seen": 0, "correct": 0}
    rec["score"] = round((1 - s.mastery_alpha) * rec["score"] + s.mastery_alpha * correct, 3)
    rec["seen"] += 1
    rec["correct"] += int(correct)
    store.put(ns, concept, rec)
    return rec
