from __future__ import annotations

import logging
import threading
import time

from redis import Redis
from sqlalchemy import Engine

from app.core.config import settings
from app.core.logging import log_event
from app.services.outbox_service import OutboxService
from app.services.queue_service import STREAM_KEY


logger = logging.getLogger(__name__)


class OutboxDispatcher(threading.Thread):
    """Background thread (slot-0 worker) that drains job_outbox rows to the Redis Stream."""

    def __init__(self, *, engine: Engine, interval_sec: float = 1.0) -> None:
        super().__init__(name="outbox-dispatcher", daemon=True)
        self._engine = engine
        self._interval = interval_sec
        self._running = True
        self._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self._outbox = OutboxService()

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        log_event(logger, "outbox_dispatcher_started", stream_key=STREAM_KEY)
        while self._running:
            try:
                n = self._outbox.drain(
                    engine=self._engine,
                    stream_key=STREAM_KEY,
                    redis_client=self._redis,
                )
                if n:
                    log_event(logger, "outbox_drained", count=n)
            except Exception as exc:  # noqa: BLE001
                log_event(logger, "outbox_drain_failed", error=str(exc))
            time.sleep(self._interval)
        log_event(logger, "outbox_dispatcher_stopped")
