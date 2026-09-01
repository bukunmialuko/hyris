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
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

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


# Keys consumed by URL.create itself; everything else is a libpq parameter (sslmode, options,
# application_name, connect_timeout, ...) that must survive, or the users engine would connect with
# different security than the store does.
_URL_KEYS = {"user", "password", "host", "port", "dbname"}


def sqlalchemy_dsn() -> str:
    """The SQLAlchemy URL for the users table, or "" when there is none to build.

    Built by parsing, not rewriting: psycopg accepts both a URL and libpq's key=value form, but
    create_engine parses only URLs -- a regex inverse would silently switch the users table off for a
    DSN the store happily uses. Returns "" rather than raising: this runs at startup, and
    store_lifespan has already reported a genuinely broken DSN with a better message.
    """
    dsn = postgres_dsn()
    if not dsn:
        return ""
    try:
        p = conninfo.conninfo_to_dict(dsn)
        return URL.create(
            "postgresql+psycopg",
            username=p.get("user"),
            password=p.get("password"),
            host=p.get("host"),
            port=int(p["port"]) if p.get("port") else None,
            database=p.get("dbname"),
            query={k: str(v) for k, v in p.items() if k not in _URL_KEYS},
        ).render_as_string(hide_password=False)
    except (psycopg.Error, ValueError) as e:
        # NEVER interpolate the DSN or the exception: libpq quotes the whole connection string back
        # on a parse error, password included, and a comma-separated multi-host raises ValueError.
        logger.warning("DATABASE_URL cannot be expressed as a SQLAlchemy URL (%s); users table off.",
                       type(e).__name__)
        return ""


@contextmanager
def engine_lifespan() -> Generator[sessionmaker[Session] | None, None, None]:
    """The process-wide session factory for the users table, or None when there is none.

    A second connection to the same database on purpose: PostgresStore owns a psycopg pool it does
    not expose, and SQLAlchemy needs the "+psycopg" URL libpq rejects. Sync, because an async engine
    would pull in greenlet for no gain -- FastAPI runs sync dependencies in a threadpool.
    """
    url = sqlalchemy_dsn()
    if not url:
        yield None
        return
    where = _summary(postgres_dsn())
    engine = None
    try:
        engine = create_engine(
            url,
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,  # survive a database restart
            pool_timeout=5,      # not the 30s default: a dead DB must not pin a threadpool slot
            connect_args={"connect_timeout": CONNECT_TIMEOUT},
        )
        with engine.connect():   # prove driver + credentials now, not on the first request
            pass
    except Exception as e:
        if engine is not None:
            engine.dispose()
        # str(e) on a SQLAlchemy connect error can carry the URL; never interpolate it.
        raise RuntimeError(
            f"DATABASE_URL is set but SQLAlchemy cannot reach Postgres ({where}): {type(e).__name__}"
        ) from e
    try:
        logger.info("users table: SQLAlchemy engine at %s", where)
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()
