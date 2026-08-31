"""Persistence wiring — the one place that chooses Postgres over in-memory.

build_graph() deliberately does not read DATABASE_URL: it falls back to InMemoryStore whenever
nothing is injected, so the offline suite and the notebooks can never be dragged onto a
developer's database. Postgres is reached only through store_lifespan(), entered once by the
FastAPI lifespan in app.main, which owns the store for the life of the process.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from langgraph.store.base import BaseStore
from langgraph.store.postgres import PostgresStore
from psycopg import conninfo

from app.config import normalize_dsn, postgres_dsn

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5  # seconds to prove the database is reachable, at startup
# PostgresStore.batch() serialises every op on an instance lock, so only one connection is ever in
# use: this pool is for reconnecting after a database restart, not for concurrency. `timeout` is
# undeclared in langgraph's PoolConfig TypedDict but does reach ConnectionPool (it forwards **pc);
# it is what a store op waits when the database is gone, so keep it short.
POOL_CONFIG = {"min_size": 1, "max_size": 2, "timeout": 2.0}


def _summary(dsn: str) -> str:
    """host:port/dbname — safe for logs because the DSN is never formatted whole."""
    try:
        p = conninfo.conninfo_to_dict(dsn)
    except psycopg.Error:
        return "<unparseable DSN>"
    return f"{p.get('host', '?')}:{p.get('port', '?')}/{p.get('dbname', '?')}"


@contextmanager
def open_store(dsn: str) -> Generator[BaseStore, None, None]:
    """Open a Postgres-backed store — connection plus migrations — and close it on exit."""
    dsn = normalize_dsn(dsn)
    # Without this, libpq resolves "" to ITS OWN defaults (localhost:5432, dbname=$USER) and the
    # setup() below runs CREATE TABLE against whatever unrelated Postgres is running.
    # conninfo_to_dict("") returns {} and raises nothing, so it cannot catch this.
    if not dsn:
        raise RuntimeError("open_store() needs a DSN; an empty DATABASE_URL means in-memory — use store_lifespan().")
    where = _summary(dsn)
    try:
        # One direct connect first: it validates the DSN and produces the REAL error. Going straight
        # to the pool would surface an unattributed "PoolTimeout: pool initialization incomplete"
        # instead, because psycopg_pool catches connection errors on a worker thread.
        psycopg.connect(dsn, connect_timeout=CONNECT_TIMEOUT).close()
    except psycopg.Error as e:
        # libpq quotes the offending connection string back at you, so a typo'd scheme would print
        # the whole DSN — password included — to stderr and into `docker compose logs`.
        raise RuntimeError(
            f"DATABASE_URL is set but Postgres is not usable ({where}): {str(e).replace(dsn, where)}. "
            "Start it (`docker compose up -d db`) or unset DATABASE_URL to run in memory."
        ) from e
    with PostgresStore.from_conn_string(dsn, pool_config=POOL_CONFIG) as store:
        store.setup()  # idempotent: the store_migrations version table guards it
        yield store


@contextmanager
def store_lifespan() -> Generator[BaseStore | None, None, None]:
    """Yield the process-wide store, or None when DATABASE_URL is unset.

    None means "let build_graph() use its in-memory default" — the single place that choice is made.
    """
    dsn = postgres_dsn()
    if not dsn:
        logger.warning("DATABASE_URL is unset: learner memory is in-process and dies with this process.")
        yield None
        return
    with open_store(dsn) as store:
        logger.info("learner memory: PostgresStore at %s", _summary(dsn))
        yield store
