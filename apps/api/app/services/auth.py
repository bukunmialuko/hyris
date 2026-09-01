"""Device tokens: turning an identity claim into something only this server can issue.

X-User-Id was a claim -- any caller could send any id and read that learner's memory. A device token
is the same trust model (no sign-up, one identity per browser profile) except the id is signed, so a
caller can only present an id this server minted for it.

Deliberately not a login: there is no password to steal and no account to recover. The token is a
bearer credential the extension keeps in chrome.storage.sync, closer to an API key than a session.
"""

import logging
import uuid

import jwt

from app.config import get_settings
from app.models.entities import USER_ID_MAX

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
# RFC 7518 3.2: an HMAC-SHA256 key should be at least as long as the hash output. PyJWT only warns;
# a short secret is brute-forceable, and a forgeable token is worse than no token at all.
MIN_SECRET_BYTES = 32


class AuthUnavailable(RuntimeError):
    """No signing secret is configured, so tokens cannot be minted or verified."""


def _secret() -> str:
    secret = get_settings().auth_secret
    if not secret:
        raise AuthUnavailable(
            "AUTH_SECRET is unset, so device tokens cannot be issued. Set it to a long random "
            "string; there is deliberately no default, because a guessable signing key would make "
            "every identity forgeable while looking secure."
        )
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise AuthUnavailable(
            f"AUTH_SECRET is shorter than {MIN_SECRET_BYTES} bytes. Generate one with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(32))'`."
        )
    return secret


def new_user_id() -> str:
    return uuid.uuid4().hex


def mint_token(user_id: str) -> str:
    """Sign a device token. No expiry: this is the learner's only handle on their own history, and
    an expiry they cannot refresh would silently orphan it. Revocation today means rotating
    AUTH_SECRET, which invalidates every token at once."""
    return jwt.encode({"sub": user_id}, _secret(), algorithm=ALGORITHM)


def read_token(token: str) -> str | None:
    """The user id inside a token this server signed, or None if it did not sign it."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except (jwt.InvalidTokenError, AuthUnavailable):
        return None
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub or len(sub) > USER_ID_MAX:
        return None
    return sub
