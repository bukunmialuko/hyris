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

from app.config import get_settings
from app.models.entities import USER_ID_MAX
from app.services.auth import read_token

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

def _validated(raw: str) -> str:
    """A caller-supplied id, checked as the store namespace it becomes."""
    user_id = raw.strip()
    if len(user_id) > USER_ID_MAX or not _ALLOWED.fullmatch(user_id):
        raise HTTPException(400, f"X-User-Id must be 1-{USER_ID_MAX} characters from A-Z a-z 0-9 _ -")
    return user_id


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


def current_user_id(
    authorization: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """Who the caller is.

    Precedence, strongest first:
      1. `Authorization: Bearer <token>` -- an id this server signed, so it cannot be chosen.
      2. `X-User-Id` -- the legacy header. FORGEABLE: any caller can name any learner and read
         their memory. Kept only while the extension still sends it, and only when
         settings.allow_header_identity is on; every use is logged so the migration is visible.
      3. Nothing -- "anonymous", the shared profile curl and Postman land in.

    Deliberately `def` and not `async def`: FastAPI runs a sync dependency in a threadpool.
    """
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Authorization must be 'Bearer <token>'.")
        user_id = read_token(token)
        if user_id is None:
            # Never fall through to the header or to anonymous: a caller who presented a token
            # meant to be someone, and silently demoting them would write history they cannot read.
            raise HTTPException(401, "Invalid or unrecognised device token.")
        return user_id

    if x_user_id is not None:
        if not get_settings().allow_header_identity:
            raise HTTPException(401, "X-User-Id is no longer accepted; register a device token.")
        logger.warning("identity taken from the forgeable X-User-Id header; register a device token")
        return _validated(x_user_id)

    return ANONYMOUS


CurrentUserId = Annotated[str, Depends(current_user_id)]
