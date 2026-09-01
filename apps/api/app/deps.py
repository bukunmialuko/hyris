"""Request identity: who the caller claims to be, and the users row proving we have seen them.

The extension sends a random UUID it keeps in chrome.storage.sync; curl and Postman send nothing and
get "anonymous". This is not authentication -- an X-User-Id is a claim, not a credential. It is a
namespace, and it is validated as one.
"""

import logging
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models.entities import USER_ID_MAX, User

logger = logging.getLogger(__name__)

ANONYMOUS = "anonymous"

# fullmatch, not match: `$` also matches before a trailing newline, so re.match would accept "abc\n".
# An allow-list rather than a "." blocklist, because this string becomes a LangGraph store namespace:
# PostgresStore joins labels with "." and matches them as a LIKE prefix, so ("users", "alice.mastery",
# "quiz_history") shares a prefix with ("users", "alice", "mastery") and CROSS-READS another user's
# rows. langgraph validates namespaces on put() only -- get(), search() and delete() do not -- so the
# boundary must. InMemoryStore compares tuples element-wise and cannot reproduce it, which is exactly
# why the offline suite would never have caught it.
_ALLOWED = re.compile(r"[A-Za-z0-9_-]+")

_sessions: sessionmaker[Session] | None = None
_store = None  # the LangGraph store; endpoints that move mastery need the same one the graph uses


def set_sessions(sessions: sessionmaker[Session] | None) -> None:
    """Called once by the app lifespan with the session factory this process actually got.

    None means no DATABASE_URL: identity still works, it just is not written down -- the same
    contract app.routers.quiz.set_store(None) has for learner memory.
    """
    global _sessions
    _sessions = sessions


def set_store(store) -> None:
    """Called once by the app lifespan. app.routers.quiz keeps its own copy for build_graph; this
    one is for request-time work like scoring an attempt, which must move mastery in the same store
    the graph reads."""
    global _store
    _store = store


def get_store():
    """The process-wide store, or None when there is no database."""
    return _store


Store = Annotated[object, Depends(get_store)]


def get_sessions() -> sessionmaker[Session] | None:
    """The process-wide session factory, or None when there is no database.

    Added the day a route actually needed a Session (GET /quizzes). Routes take this rather than
    reaching into another module's global, and a test can override it through the app.
    """
    return _sessions


Sessions = Annotated["sessionmaker[Session] | None", Depends(get_sessions)]


def _ensure_user(user_id: str) -> None:
    """Get-or-create, best effort.

    One statement, no read-then-write: two requests racing the same first sight both run this, one
    inserts and the other no-ops on the primary key. SELECT-then-INSERT would race into a duplicate
    key error, and catching that IntegrityError leaves the transaction aborted, so every later
    statement on the session raises InFailedSqlTransaction until a rollback.
    """
    if _sessions is None:
        return
    try:
        with _sessions() as session:
            session.execute(pg_insert(User).values(id=user_id).on_conflict_do_nothing(index_elements=["id"]))
            session.commit()
    except SQLAlchemyError as e:
        # A database that died after boot must not turn quiz generation into a 500. The id itself is
        # not logged: under this step's own threat model it is the closest thing to a credential.
        logger.warning("users row not recorded (%s): %s", type(e).__name__, e)


def current_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str:
    """The caller's id, created in the users table on first sight.

    Deliberately `def` and not `async def`: FastAPI runs a sync dependency in a threadpool, so the
    blocking round-trip below never parks the event loop.
    """
    user_id = ANONYMOUS if x_user_id is None else x_user_id.strip()
    if len(user_id) > USER_ID_MAX or not _ALLOWED.fullmatch(user_id):
        # 400, never a silent downgrade to anonymous: a caller whose id was quietly replaced would
        # write a quiz history it can never read back.
        raise HTTPException(400, f"X-User-Id must be 1-{USER_ID_MAX} characters from A-Z a-z 0-9 _ -")
    _ensure_user(user_id)
    return user_id


CurrentUserId = Annotated[str, Depends(current_user_id)]
