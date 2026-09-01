"""Opt-in persistence tests: learner memory must outlive the process that wrote it.

    docker compose up -d db
    HYRIS_TEST_DATABASE_URL=postgresql://hyris:hyris@localhost:5433/hyris pytest apps/api

Skipped — not failed — when that variable is unset, so `pytest apps/api` stays offline. A variable
separate from DATABASE_URL on purpose: pointing the suite at a database must be a deliberate act,
never a side effect of somebody's .env.
"""

import os
import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph
from app.agent.tools.memory import RECENT_HASHES, load_learner_context, qhash
from app.services.persistence import open_store
from tests.conftest import FakeLLM, fake_moderation
from tests.test_graph import INPUTS, run

TEST_DSN = os.environ.get("HYRIS_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(not TEST_DSN, reason="set HYRIS_TEST_DATABASE_URL to run these")


def _cleanup(user: str) -> None:
    """No namespace-level delete exists, and search() defaults to limit=10 — so pass a limit and
    loop, or rows are left behind in a developer's database."""
    with open_store(TEST_DSN) as store:
        for ns in (("users", user, "quiz_history"), ("users", user, "mastery")):
            while items := store.search(ns, limit=100):
                for it in items:
                    store.delete(ns, it.key)


def test_setup_is_idempotent():
    with open_store(TEST_DSN) as store:
        store.setup()  # a second migration run must be a no-op, not an error


def test_quiz_history_outlives_the_store(fake_page):
    """Two open_store() blocks stand in for two processes: separate connections, separate store
    objects, nothing shared but the database."""
    user = f"pytest_{uuid.uuid4().hex[:8]}"
    try:
        with open_store(TEST_DSN) as store:  # "process" 1: generate a quiz
            graph = build_graph(MemorySaver(), store, llm=FakeLLM(), moderation=fake_moderation)
            final = run(graph, {**INPUTS, "user_id": user}, thread=user)
            written = [qhash(q["question"]) for q in final["quiz"]["questions"]]
            assert len(written) == 3

        with open_store(TEST_DSN) as store:  # "process" 2: read it back cold
            items = store.search(("users", user, "quiz_history"), limit=100)
            assert len(items) == 1
            assert items[0].value["domain"] == "example.org"
            ctx = load_learner_context(store, user, INPUTS["page_url"])
            assert sorted(ctx["recent_question_hashes"]) == sorted(written)
    finally:
        _cleanup(user)


def test_history_window_is_newest_first_on_postgres():
    """The ordering bug only manifests on Postgres (search is updated_at DESC), so the in-memory
    test cannot catch a wrong fix on the backend that actually persists."""
    user = f"pytest_{uuid.uuid4().hex[:8]}"
    n = RECENT_HASHES + 20
    try:
        with open_store(TEST_DSN) as store:
            for i in range(n):
                for domain in ("example.org", "other.com"):
                    store.put(
                        ("users", user, "quiz_history"),
                        f"quiz_{domain}_{i}",
                        {"url": f"https://{domain}/a", "domain": domain,
                         "question_hashes": [f"{domain}-{i:04d}"]},
                    )
            hashes = load_learner_context(store, user, "https://example.org/a")["recent_question_hashes"]

        assert len(hashes) == RECENT_HASHES
        assert not any(h.startswith("other.com") for h in hashes)
        assert f"example.org-{n - 1:04d}" in hashes  # newest kept
        assert "example.org-0000" not in hashes  # oldest dropped
    finally:
        _cleanup(user)


def _users_engine():
    """Built from HYRIS_TEST_DATABASE_URL directly: conftest blanks DATABASE_URL for the whole
    session, so sqlalchemy_dsn() -- which reads settings -- returns "" in here."""
    from psycopg import conninfo
    from sqlalchemy import URL, create_engine

    p = conninfo.conninfo_to_dict(TEST_DSN)
    return create_engine(URL.create(
        "postgresql+psycopg", username=p.get("user"), password=p.get("password"),
        host=p.get("host"), port=int(p["port"]) if p.get("port") else None, database=p.get("dbname"),
    ))


def _users_table_exists(engine) -> bool:
    from sqlalchemy import inspect

    return inspect(engine).has_table("users")


def test_get_or_create_is_idempotent(monkeypatch):
    """The real upsert against real Postgres: two sightings of a new id must leave exactly one row."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app import deps

    engine = _users_engine()
    if not _users_table_exists(engine):
        pytest.skip("run `alembic upgrade head` from apps/api first")
    user = f"pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(deps, "_sessions", sessionmaker(engine, expire_on_commit=False))
    try:
        deps._ensure_user(user)
        deps._ensure_user(user)  # second sight: ON CONFLICT DO NOTHING, not a duplicate key
        with engine.connect() as c:
            rows = c.execute(text("select count(*) from users where id = :u"), {"u": user}).scalar()
            tz = c.execute(text("select created_at from users where id = :u"), {"u": user}).scalar()
        assert rows == 1
        assert tz.tzinfo is not None, "created_at must be timezone-aware"
    finally:
        with engine.begin() as c:
            c.execute(text("delete from users where id = :u"), {"u": user})
        engine.dispose()
