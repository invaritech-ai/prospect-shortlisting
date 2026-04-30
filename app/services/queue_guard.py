"""Backpressure: cap bulk enqueue to avoid flooding queues."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

MAX_QUEUE_DEPTHS: dict[str, int] = {
    "scrape": 300,
    "ai_decision": 200,
    "contact_fetch": 150,
    "email_reveal": 150,
    "validation": 100,
}


def current_depth(engine: Engine, queue: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM procrastinate_jobs "
                "WHERE queue = :q AND status IN ('todo', 'doing')"
            ),
            {"q": queue},
        ).one()
    return int(row[0])


def available_slots(engine: Engine, queue: str, requested: int) -> int:
    """Return how many of `requested` can actually be enqueued right now."""
    depth = current_depth(engine, queue)
    headroom = max(0, MAX_QUEUE_DEPTHS[queue] - depth)
    return min(requested, headroom)
