"""In-process fan-out for Postgres `job_events` NOTIFYs.

A single asyncio task holds one dedicated psycopg connection that
LISTENs on the `job_events` channel. Every received notification is
pushed onto the per-subscriber `asyncio.Queue`s registered via
`subscribe()`. SSE endpoints consume those queues.

This module is purely additive — it does not write to the database
and never blocks the writers. If the listener task crashes, the only
impact is that connected SSE clients stop receiving live updates;
existing polling endpoints and job writers continue to work.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg

from app.core.config import settings

logger = logging.getLogger(__name__)

_CHANNEL = "job_events"
_QUEUE_MAX = 256  # per-subscriber backpressure cap


def _to_async_dsn(url: str) -> str:
    # SQLAlchemy-style "postgresql+psycopg://..." → libpq "postgresql://..."
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url[len("postgresql+psycopg2://") :]
    return url


class EventPubSub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="job_events_listener")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict]]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=_QUEUE_MAX)
        async with self._lock:
            self._subscribers.add(q)
        try:
            yield q
        finally:
            async with self._lock:
                self._subscribers.discard(q)

    async def _fanout(self, payload: dict) -> None:
        async with self._lock:
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer — drop oldest to keep stream live.
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass

    async def _run(self) -> None:
        dsn = _to_async_dsn(settings.database_url)
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with await psycopg.AsyncConnection.connect(
                    dsn, autocommit=True
                ) as conn:
                    await conn.execute(f"LISTEN {_CHANNEL}")
                    logger.info("job_events_listener: connected and listening")
                    backoff = 1.0
                    async for notify in conn.notifies():
                        if self._stop.is_set():
                            break
                        try:
                            payload = json.loads(notify.payload)
                        except Exception:
                            logger.warning("job_events_listener: bad payload %r", notify.payload)
                            continue
                        await self._fanout(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("job_events_listener: %s — reconnecting in %.1fs", exc, backoff)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 30.0)


pubsub = EventPubSub()
