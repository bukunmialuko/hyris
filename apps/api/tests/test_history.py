"""Quiz history: the endpoint's contract, and the best-effort write that feeds it.

Offline -- the session factory is None or a fake, so nothing opens a socket.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.quizzes import record_quiz_row


@pytest.fixture
def client():
    return TestClient(app)


def test_no_database_means_no_history_not_an_error(client):
    """With DATABASE_URL unset there is genuinely nothing to list, so [] is the honest answer."""
    assert client.get("/quizzes").json() == {"quizzes": []}


def test_history_requires_a_valid_identity(client):
    assert client.get("/quizzes", headers={"X-User-Id": "alice.mastery"}).status_code == 400


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_limit_is_bounded(client, limit):
    """A caller must not be able to ask the API to build an unbounded response."""
    assert client.get(f"/quizzes?limit={limit}").status_code == 422


def test_record_quiz_row_is_a_noop_without_a_database():
    record_quiz_row(None, "u1", "https://example.org/a", {"id": "q1", "questions": []})


def test_record_quiz_row_upserts_the_user_first():
    """quizzes.user_id is a NOT NULL FK but deps._ensure_user is best-effort, so this cannot assume
    the user row landed -- it must upsert the user in the same transaction."""
    statements = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt):
            from sqlalchemy.dialects import postgresql

            statements.append(str(stmt.compile(dialect=postgresql.dialect())))

        def commit(self):
            pass

    record_quiz_row(lambda: FakeSession(), "u1", "https://example.org/a",
                    {"id": "q1", "title": "t", "questions": []})
    assert len(statements) == 2
    assert "INSERT INTO users" in statements[0], "the user must be upserted before the quiz"
    assert "INSERT INTO quizzes" in statements[1]
    assert all("ON CONFLICT" in s for s in statements), "both writes must be idempotent"


def test_record_quiz_row_swallows_a_dead_database(caplog):
    class Boom:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt):
            from sqlalchemy.exc import OperationalError

            raise OperationalError("INSERT", {}, Exception("database is gone"))

        def commit(self):
            pass

    # A quiz the user is already looking at must not fail because history could not be written.
    record_quiz_row(lambda: Boom(), "u1", "https://example.org/a", {"id": "q1", "questions": []})
    assert "quiz row not recorded" in caplog.text
