"""The quizzes table: write a finished quiz, read a user's history.

Separate from app.agent.tools.memory on purpose. That module owns the LangGraph store, which is the
learner *profile*; this one owns the relational record of what was actually generated. They persist
to the same database but answer different questions, and only this one can be joined against.
"""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models.entities import QuizRow, User

logger = logging.getLogger(__name__)

# A history page. Bounded so a user with thousands of quizzes cannot ask the API to build an
# unbounded response, and so the query stays index-friendly.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def record_quiz_row(
    sessions: sessionmaker[Session] | None, user_id: str, page_url: str, quiz: dict
) -> None:
    """Best-effort insert of a finished quiz.

    Best-effort like record_quiz: a database that died mid-run must not fail a quiz the user is
    already looking at. The user row is upserted in the same transaction first -- app.deps.
    _ensure_user is itself best-effort, so quizzes.user_id (a NOT NULL FK) cannot assume it landed.
    """
    if sessions is None:
        return
    try:
        with sessions() as session:
            session.execute(
                pg_insert(User).values(id=user_id).on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(
                pg_insert(QuizRow)
                .values(id=quiz["id"], user_id=user_id, source_url=str(page_url), payload=quiz)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.commit()
    except SQLAlchemyError as e:
        logger.warning("quiz row not recorded (%s): %s", type(e).__name__, e)


def list_quizzes(
    sessions: sessionmaker[Session] | None, user_id: str, limit: int = DEFAULT_LIMIT
) -> list[QuizRow]:
    """This user's quizzes, newest first. No database configured means no history, not an error."""
    if sessions is None:
        return []
    stmt = (
        select(QuizRow)
        .where(QuizRow.user_id == user_id)
        .order_by(QuizRow.created_at.desc())
        .limit(min(limit, MAX_LIMIT))
    )
    with sessions() as session:
        return list(session.scalars(stmt))
