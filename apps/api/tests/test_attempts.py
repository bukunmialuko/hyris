"""Submitting an attempt: scoring, idempotency, ownership, and the mastery it moves.

Offline -- a fake session factory and an InMemoryStore stand in for the database.
"""

import pytest
from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from app.agent.tools.memory import load_learner_context
from app.main import app
from app.services.attempts import apply_mastery, score

QUIZ = {
    "id": "quiz_1",
    "title": "T",
    "questions": [
        {"slot_id": 0, "concept": "self-attention", "correct_answer": 2, "options": list("abcd")},
        {"slot_id": 1, "concept": "positional encodings", "correct_answer": 0, "options": list("abcd")},
    ],
}


@pytest.fixture
def client():
    return TestClient(app)


def test_scoring_marks_against_the_stored_quiz():
    """The stored quiz is the source of truth -- a client cannot report its own score."""
    results = score(QUIZ, {"0": 2, "1": 3})
    assert [r["correct"] for r in results] == [True, False]
    assert results[0]["concept"] == "self-attention"


def test_an_unanswered_question_is_wrong():
    results = score(QUIZ, {})
    assert [r["correct"] for r in results] == [False, False]
    assert results[0]["picked"] is None


def test_unknown_quiz_is_404(client):
    """No database means no stored quiz, and a caller must not be able to tell that apart from
    someone else's quiz id by probing."""
    r = client.post("/attempts", json={"quiz_id": "quiz_nope", "answers": {}})
    assert r.status_code == 404


def test_attempt_requires_a_valid_identity(client):
    r = client.post("/attempts", headers={"X-User-Id": "alice.mastery"},
                    json={"quiz_id": "quiz_1", "answers": {}})
    assert r.status_code == 400


def test_apply_mastery_moves_each_tested_concept():
    store = InMemoryStore()
    apply_mastery(store, "u1", score(QUIZ, {"0": 2, "1": 3}))
    rows = {i.key: i.value for i in store.search(("users", "u1", "mastery"), limit=10)}
    assert rows["self-attention"]["correct"] == 1
    assert rows["positional encodings"]["correct"] == 0
    assert rows["self-attention"]["score"] > rows["positional encodings"]["score"]


def test_mastery_reaches_the_planner_and_marks_a_weak_concept():
    """The point of the whole loop: enough wrong answers and the next quiz plans around it.
    min_seen is 2, so one attempt is not yet a signal -- two are."""
    store = InMemoryStore()
    wrong = score(QUIZ, {"0": 2, "1": 3})  # q1 wrong both times
    apply_mastery(store, "u1", wrong)
    assert load_learner_context(store, "u1", "https://x.org/a")["weak_concepts"] == []
    apply_mastery(store, "u1", wrong)
    ctx = load_learner_context(store, "u1", "https://x.org/a")
    assert "positional encodings" in ctx["weak_concepts"]
    assert "self-attention" not in ctx["weak_concepts"]


def test_apply_mastery_survives_a_broken_store(caplog):
    """The attempt is already scored and saved; a store failure must not turn it into an error."""
    class Broken(InMemoryStore):
        def get(self, *a, **k):
            raise RuntimeError("store is gone")

    apply_mastery(Broken(), "u1", score(QUIZ, {"0": 2}))
    assert "mastery not updated" in caplog.text


def test_apply_mastery_skips_questions_with_no_concept():
    store = InMemoryStore()
    apply_mastery(store, "u1", [{"concept": None, "correct": True}])
    assert store.search(("users", "u1", "mastery"), limit=10) == []


def test_resubmitting_an_attempt_id_does_not_move_mastery_twice(monkeypatch):
    """psycopg3 reports rowcount as -1 for ON CONFLICT DO NOTHING, so is_new must come from
    RETURNING. Getting this wrong makes mastery either never move or double-count."""
    from app.services.attempts import record_attempt

    seen = {"count": 0}

    class FakeResult:
        def __init__(self, first):
            self.first = first

        def scalar_one_or_none(self):
            return "att_1" if self.first else None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt):
            seen["count"] += 1
            return FakeResult(seen["count"] == 1)

        def commit(self):
            pass

    sessions = lambda: FakeSession()  # noqa: E731
    _, first = record_attempt(sessions, "quiz_1", {}, [], attempt_id="att_1")
    _, second = record_attempt(sessions, "quiz_1", {}, [], attempt_id="att_1")
    assert first is True and second is False
