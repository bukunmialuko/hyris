"""Request identity: header parsing, namespace validation, and best-effort get-or-create.

Nothing here opens a socket: deps._sessions is None unless a test installs a fake factory.
"""

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import deps
from app.deps import ANONYMOUS, CurrentUserId, current_user_id

# Values that would corrupt a LangGraph store namespace. "." is the dangerous one: PostgresStore
# dot-joins namespaces and matches them as a LIKE prefix, so "alice.mastery" cross-reads "alice".
NAMESPACE_ATTACKS = [
    "alice.mastery",
    "users.alice.mastery",
    "",
    " ",
    "a/b",
    "a@b.com",
    "a%b",
    "x" * 65,
]


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/who")
    def who(user_id: CurrentUserId) -> dict:
        return {"user_id": user_id}

    return TestClient(app)


def test_no_header_is_anonymous(client):
    assert client.get("/who").json() == {"user_id": ANONYMOUS}


def test_valid_uuid_is_echoed_back(client):
    uid = "3f2a9c11-4b7e-4a1d-9d3e-8c2f1b6a0e55"
    assert client.get("/who", headers={"X-User-Id": uid}).json() == {"user_id": uid}


@pytest.mark.parametrize("bad", NAMESPACE_ATTACKS)
def test_namespace_attacks_are_rejected_with_400(client, bad):
    r = client.get("/who", headers={"X-User-Id": bad})
    assert r.status_code == 400, f"{bad!r} was accepted"


def test_allow_list_uses_fullmatch_not_match():
    """`$` also matches before a trailing newline, so `re.match` would accept "abc\n". strip() hides
    that today, but the regex is the guarantee — this pins it so removing strip() cannot open a hole."""
    assert deps._ALLOWED.match("abc\n")  # what re.match would have allowed
    assert not deps._ALLOWED.fullmatch("abc\n")  # what deps actually uses


def test_interior_newline_is_rejected(client):
    r = client.get("/who", headers={"X-User-Id": "a\tb"})
    assert r.status_code == 400


def test_non_ascii_is_rejected():
    """Asserted directly: httpx raises UnicodeEncodeError before such a request is ever sent."""
    with pytest.raises(HTTPException):
        current_user_id("aé")


def test_surrounding_whitespace_is_stripped(client):
    assert client.get("/who", headers={"X-User-Id": "  abc  "}).json() == {"user_id": "abc"}


def test_repeated_header_is_rejected(client):
    """Two X-User-Id headers arrive joined as "a, b", which the allow-list rejects."""
    r = client.get("/who", headers=httpx.Headers([("X-User-Id", "a"), ("X-User-Id", "b")]))
    assert r.status_code == 400


def test_lifespan_installs_the_session_factory():
    """The composition root, not just the function: httpx.ASGITransport never runs lifespan."""
    from app.main import app

    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert deps._sessions is None  # DATABASE_URL blanked by conftest


def test_concept_survives_the_api_boundary():
    """A bare schema change would drop these silently: pydantic ignores unknown keys, so the fields
    have to exist on QuizQuestion for the graph's concept to reach the client."""
    from app.schemas.quiz import RunStatus

    status = RunStatus.model_validate({
        "run_id": "run_1", "status": "done",
        "quiz": {"id": "q1", "title": "t", "questions": [{
            "slot_id": 0, "concept": "self-attention", "bloom_level": "apply",
            "question": "?", "options": ["a", "b", "c", "d"], "correct_answer": 0}]},
    })
    q = status.quiz.questions[0]
    assert q.concept == "self-attention" and q.bloom_level == "apply"


def test_identity_does_not_write_a_users_row(client, monkeypatch):
    """Dependencies resolve before body validation, so writing here meant a malformed request with a
    fresh header minted a row for a caller that never did anything. The row is created on first
    persist instead (services.quizzes.record_quiz_row upserts it alongside the quiz)."""
    from app import deps

    called = []
    monkeypatch.setattr(deps, "_sessions", lambda: called.append(1))
    client.get("/who", headers={"X-User-Id": "brand-new-caller"})
    assert called == []


# ---------------------------------------------------------------- device tokens

# Long enough to satisfy the RFC 7518 minimum the service enforces.
SECRET = "test-secret-not-a-real-one-but-long-enough-to-sign-with"


@pytest.fixture
def signed(monkeypatch):
    """A configured signing secret, plus a helper to mint tokens with it."""
    from app.config import Settings
    from app.services import auth

    monkeypatch.setattr(auth, "get_settings", lambda: Settings(auth_secret=SECRET))
    return auth


def test_registering_a_device_returns_a_token_for_an_id_the_caller_did_not_choose(signed):
    from app.routers.auth import register_device

    a, b = register_device(), register_device()
    assert a.user_id != b.user_id
    assert signed.read_token(a.token) == a.user_id


def test_a_bearer_token_identifies_its_owner(client, signed):
    from app.routers.auth import register_device

    d = register_device()
    r = client.get("/who", headers={"Authorization": f"Bearer {d.token}"})
    assert r.json() == {"user_id": d.user_id}


def test_a_token_this_server_did_not_sign_is_rejected(client, signed):
    """The whole point: a caller cannot mint an identity, only present one."""
    import jwt

    other = "a-different-secret-of-perfectly-adequate-length"
    forged = jwt.encode({"sub": "someone-elses-id"}, other, algorithm="HS256")
    assert client.get("/who", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_a_tampered_token_is_rejected(client, signed):
    from app.routers.auth import register_device

    tampered = register_device().token[:-2] + ("aa" if not register_device().token.endswith("aa") else "bb")
    assert client.get("/who", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_a_bad_token_never_falls_back_to_anonymous(client, signed):
    """A caller who presented a token meant to be someone. Silently demoting them to the shared
    anonymous profile would write history they could never read back."""
    r = client.get("/who", headers={"Authorization": "Bearer rubbish"})
    assert r.status_code == 401
    assert r.json() != {"user_id": ANONYMOUS}


@pytest.mark.parametrize("value", ["token-without-scheme", "Basic abc", "Bearer"])
def test_a_malformed_authorization_header_is_rejected(client, signed, value):
    assert client.get("/who", headers={"Authorization": value}).status_code == 401


def test_without_a_secret_no_token_can_be_issued(monkeypatch):
    """No weak default: a guessable signing key would make every identity forgeable while looking
    secure, so the endpoint refuses instead."""
    from fastapi import HTTPException

    from app.config import Settings
    from app.routers import auth as auth_router
    from app.services import auth as auth_service

    monkeypatch.setattr(auth_service, "get_settings", lambda: Settings(auth_secret=""))
    with pytest.raises(HTTPException) as exc:
        auth_router.register_device()
    assert exc.value.status_code == 503


def test_the_legacy_header_still_works_but_is_announced(client, caplog):
    """Kept only while the extension still sends it."""
    r = client.get("/who", headers={"X-User-Id": "legacy-caller"})
    assert r.json() == {"user_id": "legacy-caller"}
    assert "forgeable" in caplog.text


def test_the_legacy_header_can_be_switched_off(client, monkeypatch):
    from app import deps as deps_mod
    from app.config import Settings

    monkeypatch.setattr(deps_mod, "get_settings", lambda: Settings(allow_header_identity=False))
    assert client.get("/who", headers={"X-User-Id": "legacy-caller"}).status_code == 401


def test_a_short_secret_is_refused(monkeypatch):
    """PyJWT only warns about an under-length HMAC key. A brute-forceable secret makes every
    identity forgeable while the system looks authenticated, so this refuses outright."""
    from fastapi import HTTPException

    from app.config import Settings
    from app.routers import auth as auth_router
    from app.services import auth as auth_service

    monkeypatch.setattr(auth_service, "get_settings", lambda: Settings(auth_secret="hunter2"))
    with pytest.raises(HTTPException) as exc:
        auth_router.register_device()
    assert exc.value.status_code == 503 and "32 bytes" in str(exc.value.detail)
