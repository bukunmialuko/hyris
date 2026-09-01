"""Store wiring: DSN normalisation, the in-memory default, the composition root, and the history
window. Nothing here opens a socket."""

import pytest
from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from app.agent.graph import build_graph
from app.agent.tools.memory import RECENT_HASHES, load_learner_context
from app.config import Settings, normalize_dsn
from app.services.persistence import _summary, open_store, store_lifespan
from tests.conftest import fake_moderation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgresql+psycopg://u:p@db:5432/h", "postgresql://u:p@db:5432/h"),
        ("postgres+psycopg2://u:p@db/h", "postgres://u:p@db/h"),
        ("postgresql+asyncpg://u:p@db/h", "postgresql://u:p@db/h"),
        # the scheme must come out lowercase, or libpq rejects it just the same
        ("POSTGRESQL+PSYCOPG://u:p@db/h", "postgresql://u:p@db/h"),
        ("postgresql://u:p@db:5433/h", "postgresql://u:p@db:5433/h"),
        ("  postgresql://u@db/h  ", "postgresql://u@db/h"),
        ("host=db port=5432 dbname=h", "host=db port=5432 dbname=h"),
        ("", ""),
    ],
)
def test_normalize_dsn(raw, expected):
    assert normalize_dsn(raw) == expected


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        ("postgresql://u:s3cr3t@localhost:5433/hyris", "localhost:5433/hyris"),
        ("host=db port=5432 dbname=hyris user=u password=hunter2", "db:5432/hyris"),
    ],
)
def test_summary_never_shows_the_password(dsn, expected):
    assert _summary(dsn) == expected
    assert "s3cr3t" not in _summary(dsn) and "hunter2" not in _summary(dsn)


def test_connect_failure_never_echoes_the_password():
    """libpq quotes the offending connection string back on a parse error, so a typo'd scheme would
    otherwise print the whole DSN — password included — into stderr and `docker compose logs`."""
    with pytest.raises(RuntimeError) as exc:
        with open_store("postgersql://u:sup3rs3cret@localhost:5433/h"):  # scheme typo
            pass
    assert "sup3rs3cret" not in str(exc.value)
    assert "connection info string" in str(exc.value)  # the diagnostic still survives


def test_empty_dsn_refuses_rather_than_connecting():
    """libpq resolves "" to its own defaults (localhost:5432, dbname=$USER), so without this guard
    open_store("") would run CREATE TABLE against an unrelated database."""
    with pytest.raises(RuntimeError, match="needs a DSN"):
        with open_store(""):
            pass


def test_no_database_url_yields_no_store(monkeypatch):
    monkeypatch.setattr("app.services.persistence.postgres_dsn", lambda: "")
    with store_lifespan() as store:
        assert store is None


def test_build_graph_never_reads_database_url(fake_llm, monkeypatch):
    """build_graph() must ignore DATABASE_URL however it is reached. Patching only
    app.agent.graph.get_settings would pass even if build_graph called app.config.postgres_dsn(),
    which routes through the lru_cached app.config.get_settings the conftest already blanked."""
    dsn = "postgresql://nobody:nobody@127.0.0.1:1/none"
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(database_url=dsn))
    monkeypatch.setattr("app.agent.graph.get_settings", lambda: Settings(database_url=dsn))
    graph = build_graph(llm=fake_llm, moderation=fake_moderation)
    assert isinstance(graph.store, InMemoryStore)


def test_lifespan_boots_and_serves_in_memory():
    """starlette's TestClient runs lifespan events; httpx.ASGITransport does not — so this is the
    only coverage of the composition root."""
    from app.main import app
    from app.routers import quiz as quiz_router

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert quiz_router._store is None  # DATABASE_URL blanked by conftest


def _seed_history(store, user, domain, start, count):
    for i in range(start, start + count):
        store.put(
            ("users", user, "quiz_history"),
            f"quiz_{domain}_{i}",
            {"url": f"https://{domain}/a", "domain": domain, "question_hashes": [f"{domain}-{i:04d}"]},
        )


def test_history_window_is_newest_first_and_domain_scoped():
    """The regression the memory.py fix exists to prevent. Both backends apply `limit` BEFORE
    returning, in their own order, so a limit-then-sort keeps the OLDEST rows on InMemoryStore.
    Seeding more than RECENT_HASHES rows per domain makes that visible."""
    store, user, n = InMemoryStore(), "u1", RECENT_HASHES + 20
    # interleave so neither domain is contiguous in insertion order
    for i in range(n):
        _seed_history(store, user, "example.org", i, 1)
        _seed_history(store, user, "other.com", i, 1)

    ctx = load_learner_context(store, user, "https://example.org/a")
    hashes = ctx["recent_question_hashes"]

    assert len(hashes) == RECENT_HASHES
    assert not any(h.startswith("other.com") for h in hashes)  # the domain filter held
    assert f"example.org-{n - 1:04d}" in hashes  # newest kept
    assert "example.org-0000" not in hashes  # oldest dropped


def test_history_degrades_to_empty_context_when_the_store_raises(caplog):
    class Broken(InMemoryStore):
        def search(self, *a, **k):
            raise RuntimeError("database is gone")

    ctx = load_learner_context(Broken(), "u1", "https://example.org/a")
    assert ctx == {"mastered_concepts": [], "weak_concepts": [], "recent_question_hashes": []}
    assert "learner memory unavailable" in caplog.text  # and it is no longer silent


async def test_no_database_url_yields_no_checkpointer(monkeypatch):
    """Without a database the graph keeps build_graph's in-memory MemorySaver."""
    from app.services.persistence import checkpointer_lifespan

    monkeypatch.setattr("app.services.persistence.postgres_dsn", lambda: "")
    async with checkpointer_lifespan() as saver:
        assert saver is None


def test_the_sync_postgres_saver_cannot_serve_astream():
    """Why checkpointer_lifespan is async while the store's is not.

    The sync PostgresSaver inherits aput/aget_tuple from BaseCheckpointSaver, which raise
    NotImplementedError -- and app.services.runs drives the graph with astream(). Swapping the async
    saver for the sync one would fail on the first node transition, with an empty error message.
    Pinned here because that failure is silent enough to be re-introduced by accident.
    """
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    for name in ("aput", "aget_tuple", "aput_writes"):
        assert name not in PostgresSaver.__dict__, f"sync saver unexpectedly implements {name}"
        assert name in AsyncPostgresSaver.__dict__, f"async saver must implement {name}"


async def test_shutdown_drains_an_in_flight_run():
    """uvicorn drains HTTP requests but knows nothing about the background generation tasks, so
    without this a Ctrl-C mid-run discarded the whole thing -- memory and quiz row included."""
    import asyncio

    from app.services.runs import RunRegistry

    reg = RunRegistry()
    finished = []

    async def slow(*_a, **_k):
        await asyncio.sleep(0.05)
        finished.append(True)

    reg._execute = slow
    await reg.start(object(), {})
    assert reg._tasks, "the task must be tracked, not fire-and-forget"
    await reg.drain(timeout=5)
    assert finished == [True], "drain must wait for the run to land"


async def test_drain_cancels_a_wedged_run_rather_than_hanging():
    import asyncio

    from app.services.runs import RunRegistry

    reg = RunRegistry()

    async def wedged(*_a, **_k):
        await asyncio.sleep(60)

    reg._execute = wedged
    await reg.start(object(), {})
    await reg.drain(timeout=0.05)  # must return, not block for a minute
    await asyncio.sleep(0)
    assert all(t.cancelled() or t.done() for t in list(reg._tasks) or [])


async def test_a_finished_run_is_readable_from_the_checkpoint_alone():
    """What makes polling safe under --workers N: the worker that fields the poll may not be the one
    that ran the graph, but every worker shares the checkpointer."""
    from app.services.runs import from_checkpoint

    class FakeSaver:
        def __init__(self, values):
            self.values = values

        async def aget_tuple(self, config):
            class T:
                checkpoint = {"channel_values": self.values}
            return T()

    done = await from_checkpoint(FakeSaver({"quiz": {"questions": [{"slot_id": 0}]}}), "run_1")
    assert done.status == "done" and done.quiz["questions"]

    failed = await from_checkpoint(FakeSaver({"error": "Could not fetch the page"}), "run_2")
    assert failed.status == "failed" and "fetch" in failed.error

    # A checkpoint that reached neither outcome: its worker died mid-run. Reporting "running" would
    # strand the caller polling forever.
    stranded = await from_checkpoint(FakeSaver({}), "run_3")
    assert stranded.status == "failed" and "did not finish" in stranded.error


async def test_no_checkpointer_means_no_cross_worker_fallback():
    from app.services.runs import from_checkpoint

    assert await from_checkpoint(None, "run_1") is None


async def test_a_broken_checkpoint_read_does_not_500_the_poll(caplog):
    from app.services.runs import from_checkpoint

    class Boom:
        async def aget_tuple(self, config):
            raise RuntimeError("database is gone")

    assert await from_checkpoint(Boom(), "run_1") is None
    assert "could not read checkpoint" in caplog.text
