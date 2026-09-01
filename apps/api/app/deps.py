"""Request identity: who the caller claims to be, and the users row proving we have seen them.

The extension sends a random UUID it keeps in chrome.storage.sync; curl and Postman send nothing and
get "anonymous". This is not authentication -- an X-User-Id is a claim, not a credential. It is a
namespace, and it is validated as one.
"""

import logging
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.models.entities import USER_ID_MAX

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


def current_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str:
    """The caller's validated id.

    It does NOT write a users row. Dependencies resolve before body validation, so a malformed
    request with a fresh header used to mint a row for a caller that never did anything -- an
    unauthenticated write on every 422. The row is created when the caller first persists something
    instead: app.services.quizzes.record_quiz_row upserts the user in the same transaction as the
    quiz, which it has to do anyway because quizzes.user_id is a NOT NULL foreign key.
    """
    user_id = ANONYMOUS if x_user_id is None else x_user_id.strip()
    if len(user_id) > USER_ID_MAX or not _ALLOWED.fullmatch(user_id):
        # 400, never a silent downgrade to anonymous: a caller whose id was quietly replaced would
        # write a quiz history it can never read back.
        raise HTTPException(400, f"X-User-Id must be 1-{USER_ID_MAX} characters from A-Z a-z 0-9 _ -")
    return user_id


CurrentUserId = Annotated[str, Depends(current_user_id)]
