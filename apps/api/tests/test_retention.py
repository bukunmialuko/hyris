"""Retention: the SQL is the risky part, so pin its shape and its off-switch."""

import pytest
from sqlalchemy import create_engine

from app.config import Settings
from app.services import retention
from app.services.retention import _CHECKPOINT_SQL, _QUIZ_SQL, prune


def test_the_checkpoint_timestamp_comes_from_the_right_column():
    """langgraph's checkpoints table has NO timestamp column, and `metadata` holds only
    step/source/parents -- the time is an ISO string inside the `checkpoint` jsonb. Reading the
    wrong one silently matches nothing and prunes forever without deleting anything."""
    assert "checkpoint->>'ts'" in _CHECKPOINT_SQL
    assert "metadata->>'ts'" not in _CHECKPOINT_SQL


def test_a_thread_is_removed_whole():
    """checkpoint_writes and checkpoint_blobs are keyed by thread_id, so pruning must cover all
    three or the child rows outlive the checkpoint they belong to."""
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        assert _CHECKPOINT_SQL.format(table=table).startswith(f"\nDELETE FROM {table} ")


def test_deletes_are_chunked():
    """A first prune on a large table must not hold one long transaction open."""
    assert "LIMIT :chunk" in _CHECKPOINT_SQL and "LIMIT :chunk" in _QUIZ_SQL


@pytest.mark.parametrize("days", [0, -1])
def test_retention_of_zero_disables_pruning(monkeypatch, days):
    """The off-switch must not delete everything by treating 0 as 'older than now'."""
    monkeypatch.setattr(
        retention, "get_settings",
        lambda: Settings(checkpoint_retention_days=days, quiz_retention_days=days),
    )
    # sqlite has no make_interval; if any SQL were executed this would raise rather than return 0.
    engine = create_engine("sqlite://")
    try:
        assert set(prune(engine).values()) == {0}
    finally:
        engine.dispose()
