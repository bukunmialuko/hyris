"""Pruning what would otherwise grow forever.

Three things accumulate with no natural ceiling: langgraph's checkpoint rows (one thread per run,
and app.services.runs uses a fresh thread id every time), the quizzes table, and the learner store's
quiz_history. Checkpoints are the fastest-growing and the least valuable once a run is finished --
they exist to resume and debug a run, not to be a record of it.

Deliberately a callable command rather than a background timer: when data disappears should be an
operator's decision on a schedule they can see, not a side effect of the API happening to be up.
"""

import logging

from sqlalchemy import Engine, text

from app.config import get_settings

logger = logging.getLogger(__name__)

# Deletes are chunked so a first prune on a large table cannot hold one long transaction open.
CHUNK = 5_000


def _prune(engine: Engine, sql: str, days: int, label: str) -> int:
    if days <= 0:
        logger.info("%s: retention disabled, nothing pruned", label)
        return 0
    total = 0
    while True:
        with engine.begin() as conn:
            deleted = conn.execute(text(sql), {"days": days, "chunk": CHUNK}).rowcount
        if deleted <= 0:
            break
        total += deleted
        if deleted < CHUNK:
            break
    logger.info("%s: pruned %d row(s) older than %d day(s)", label, total, days)
    return total


# The age of a thread is its newest checkpoint. Note the timestamp is inside the `checkpoint` jsonb
# as an ISO string -- langgraph's table has no timestamp column, and `metadata` holds only
# step/source/parents. checkpoint_writes and checkpoint_blobs are keyed by thread_id too, so a
# thread is removed whole; none of the three has a foreign key to another.
_CHECKPOINT_SQL = """
DELETE FROM {table} WHERE thread_id IN (
    SELECT thread_id FROM checkpoints
    GROUP BY thread_id
    HAVING max((checkpoint->>'ts')::timestamptz) < now() - make_interval(days => :days)
    LIMIT :chunk
)
"""

_QUIZ_SQL = """
DELETE FROM quizzes WHERE id IN (
    SELECT id FROM quizzes WHERE created_at < now() - make_interval(days => :days) LIMIT :chunk
)
"""


def prune(engine: Engine) -> dict[str, int]:
    """Delete aged-out checkpoints and quizzes. Returns what went, per table."""
    s = get_settings()
    out: dict[str, int] = {}
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        out[table] = _prune(
            engine, _CHECKPOINT_SQL.format(table=table), s.checkpoint_retention_days, table
        )
    # quiz_attempts follows its quiz via ON DELETE CASCADE.
    out["quizzes"] = _prune(engine, _QUIZ_SQL, s.quiz_retention_days, "quizzes")
    return out
