"""Request identity: header parsing, namespace validation, and best-effort get-or-create.

Nothing here opens a socket: deps._sessions is None unless a test installs a fake factory.
"""

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import deps
from app.deps import ANONYMOUS, CurrentUserId, _ensure_user, current_user_id

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


class _FakeSession:
    def __init__(self, log, boom=False):
        self.log, self.boom = log, boom

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt):
        from sqlalchemy.dialects import postgresql

        sql = str(stmt.compile(dialect=postgresql.dialect()))
        if self.boom:
            from sqlalchemy.exc import OperationalError

            raise OperationalError("SELECT 1", {}, Exception("database is gone"))
        self.log.append(sql)

    def commit(self):
        pass


def test_ensure_user_issues_an_idempotent_upsert(monkeypatch):
    log = []
    monkeypatch.setattr(deps, "_sessions", lambda: _FakeSession(log))
    _ensure_user("u1")
    _ensure_user("u1")  # second sight must be the same statement, not a read-then-write
    assert len(log) == 2
    assert all("ON CONFLICT (id) DO NOTHING" in s for s in log)


def test_ensure_user_is_a_noop_without_a_session_factory(monkeypatch):
    monkeypatch.setattr(deps, "_sessions", None)
    _ensure_user("u1")  # must not raise


def test_ensure_user_swallows_a_dead_database(monkeypatch, caplog):
    monkeypatch.setattr(deps, "_sessions", lambda: _FakeSession([], boom=True))
    _ensure_user("u1")
    assert "users row not recorded" in caplog.text


def test_dead_database_does_not_leak_the_user_id(monkeypatch, caplog):
    """The id is the closest thing to a credential this system has; it must not reach the log."""
    monkeypatch.setattr(deps, "_sessions", lambda: _FakeSession([], boom=True))
    _ensure_user("secret-user-id")
    assert "secret-user-id" not in caplog.text


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
