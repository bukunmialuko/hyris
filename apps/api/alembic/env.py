"""Alembic environment -- the URL comes from DATABASE_URL, the same one the app connects with."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.models.entities import Base
from app.services.persistence import sqlalchemy_dsn

target_metadata = Base.metadata

# langgraph's PostgresStore and PostgresSaver migrate THEMSELVES into the same database. Alembic
# does not own those tables, and without this filter `--autogenerate` sees them as tables that should
# not exist and emits op.drop_table('store') -- which would delete every persisted learner profile.
NOT_OURS = {
    "store", "store_vectors", "store_migrations",          # PostgresStore
    "checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations",  # PostgresSaver
}


def include_name(name, type_, parent_names):
    return name not in NOT_OURS if type_ == "table" else True


def _url() -> str:
    url = sqlalchemy_dsn()
    if not url:
        # Better than alembic's "Could not parse SQLAlchemy URL from string ''", which reads like an
        # alembic.ini problem when it is really an unset (or un-exported) environment variable.
        raise RuntimeError(
            "DATABASE_URL is unset or is not a URL SQLAlchemy can drive, so there is nothing to "
            "migrate. Export it first: DATABASE_URL=postgresql://hyris:hyris@localhost:5433/hyris"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # NullPool: this process migrates and exits, so a pool would only delay the exit.
    engine = create_engine(_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_name=include_name,
                include_schemas=False,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
