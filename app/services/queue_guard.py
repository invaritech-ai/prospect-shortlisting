"""Backpressure: cap bulk enqueue to avoid flooding queues."""
from __future__ import annotations

import logging

from psycopg import errors as pg_errors
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import Engine

MAX_QUEUE_DEPTHS: dict[str, int] = {
    "scrape": 300,
    "ai_decision": 200,
    "contact_fetch": 150,
    "email_reveal": 150,
    "validation": 100,
}

logger = logging.getLogger(__name__)


def is_procrastinate_schema_ready(engine: Engine) -> bool:
    """Return whether the Procrastinate jobs table exists in public schema."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT to_regclass('public.procrastinate_jobs')::text")
        ).one()
    return bool(row[0])


def current_depth(engine: Engine, queue: str) -> int:
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT COUNT(*) FROM procrastinate_jobs "
                    "WHERE queue_name = :q AND status IN ('todo', 'doing')"
                ),
                {"q": queue},
            ).one()
        return int(row[0])
    except DBAPIError as exc:
        # Fail-closed when Procrastinate schema is not installed yet.
        if isinstance(exc.orig, pg_errors.UndefinedTable):
            logger.warning(
                "queue_guard: procrastinate_jobs table missing; fail-closed queue=%s",
                queue,
            )
            return MAX_QUEUE_DEPTHS[queue]
        raise


def available_slots(engine: Engine, queue: str, requested: int) -> int:
    """Return how many of `requested` can actually be enqueued right now."""
    depth = current_depth(engine, queue)
    headroom = max(0, MAX_QUEUE_DEPTHS[queue] - depth)
    return min(requested, headroom)
