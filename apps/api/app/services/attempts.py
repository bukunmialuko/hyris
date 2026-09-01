"""Scoring a submitted attempt: the half of the learning loop that closes it.

Scoring happens here, not in the client. The stored quiz is the source of truth for which option is
correct, so a caller cannot report its own score -- it sends the options it picked and gets told how
it did. That also makes the mastery signal trustworthy.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.agent.tools.memory import update_mastery
from app.models.entities import QuizAttempt, QuizRow

logger = logging.getLogger(__name__)


def load_owned_quiz(
    sessions: sessionmaker[Session] | None, quiz_id: str, user_id: str
) -> QuizRow | None:
    """The caller's own quiz, or None.

    Scoped by user_id, not just quiz_id: the payload carries the correct answers and explanations,
    so letting a caller name someone else's quiz id would hand them the answer key.
    """
    if sessions is None:
        return None
    stmt = select(QuizRow).where(QuizRow.id == quiz_id, QuizRow.user_id == user_id)
    with sessions() as session:
        return session.scalars(stmt).one_or_none()


def score(payload: dict, answers: dict[str, int]) -> list[dict]:
    """Mark each question against the stored quiz. An unanswered question is simply wrong."""
    results = []
    for q in payload.get("questions", []):
        qid = str(q.get("slot_id"))
        picked = answers.get(qid)
        results.append({
            "question_id": qid,
            "concept": q.get("concept"),
            "picked": picked,
            "correct_answer": q["correct_answer"],
            "correct": picked == q["correct_answer"],
        })
    return results


def record_attempt(
    sessions: sessionmaker[Session] | None,
    quiz_id: str,
    answers: dict[str, int],
    results: list[dict],
    attempt_id: str | None = None,
) -> tuple[str, bool]:
    """Insert the attempt. Returns (attempt_id, is_new).

    is_new is False when this exact attempt_id was already recorded -- a double-clicked submit or a
    client retry. The caller uses it to skip the mastery update, because counting one answer twice
    would move the learner's score for a thing they did once.
    """
    aid = attempt_id or f"att_{uuid.uuid4().hex[:12]}"
    if sessions is None:
        return aid, True
    correct = sum(1 for r in results if r["correct"])
    try:
        with sessions() as session:
            # RETURNING, not rowcount: psycopg3 reports rowcount as -1 for an ON CONFLICT DO
            # NOTHING insert whether or not a row went in, so `rowcount > 0` would be permanently
            # False and mastery would never move. RETURNING yields a row only on a real insert.
            inserted = session.execute(
                pg_insert(QuizAttempt)
                .values(id=aid, quiz_id=quiz_id, answers=answers, score=correct)
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(QuizAttempt.id)
            ).scalar_one_or_none()
            session.commit()
            return aid, inserted is not None
    except SQLAlchemyError as e:
        logger.warning("attempt row not recorded (%s): %s", type(e).__name__, e)
        return aid, True


def apply_mastery(store, user_id: str, results: list[dict]) -> None:
    """Move each tested concept's mastery. Best effort: the attempt is already scored and saved, so
    a store failure must not turn a submitted answer into an error."""
    if store is None:
        return
    for r in results:
        if not r["concept"]:
            continue
        try:
            update_mastery(store, user_id, r["concept"], r["correct"])
        except Exception as e:  # noqa: BLE001 -- resilience boundary
            logger.warning("mastery not updated for %r (%s): %s", r["concept"], type(e).__name__, e)
