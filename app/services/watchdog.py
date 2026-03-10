from __future__ import annotations

import logging
import threading
import time

from redis import Redis

from app.core.config import settings
from app.core.logging import log_event
from app.services.queue_service import GROUP_NAME, STREAM_KEY


logger = logging.getLogger(__name__)

# Messages idle longer than this are assumed to belong to a crashed worker.
# Must exceed the longest possible task duration (scrape step1 can take ~25 min).
_REAPER_IDLE_MS = 30 * 60 * 1000  # 30 minutes
_REAPER_COUNT = 200


class WatchdogThread(threading.Thread):
    """Background thread (slot-0 worker) that reclaims un-ACKed PEL entries.

    Uses XAUTOCLAIM (Redis 6.2+) to atomically find and re-deliver messages
    that have been idle longer than ``_REAPER_IDLE_MS``.  The re-delivery is
    done by XADDing a fresh stream message and then XACKing the original, so
    the task is handled by the normal worker main loop rather than inline here.

    Safety order: XADD new message *before* XACK original.  If XADD fails the
    original stays in PEL; if XACK fails the message is re-claimed next cycle
    (duplicate delivery — harmless because CAS guards dedup at the job level).
    """

    def __init__(self, *, interval_sec: float = 300.0) -> None:
        super().__init__(name="watchdog-reaper", daemon=True)
        self._interval = interval_sec
        self._running = True
        self._redis = Redis.from_url(settings.redis_url, decode_responses=True)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        log_event(logger, "watchdog_started", idle_threshold_ms=_REAPER_IDLE_MS)
        while self._running:
            # Sleep first so we don't reap on startup before workers have had a
            # chance to process messages that are merely slow, not crashed.
            time.sleep(self._interval)
            if not self._running:
                break
            self._reap()
        log_event(logger, "watchdog_stopped")

    def _reap(self) -> None:
        try:
            # XAUTOCLAIM returns (next_start_id, [(msg_id, fields), ...], deleted_ids)
            result = self._redis.xautoclaim(
                STREAM_KEY,
                GROUP_NAME,
                "reaper",
                min_idle_time=_REAPER_IDLE_MS,
                start_id="0-0",
                count=_REAPER_COUNT,
            )
            _, entries, _ = result
            if not entries:
                return

            redelivered = 0
            for msg_id, fields in entries:
                try:
                    # Step 1: XADD new message first — if this fails, original stays in PEL.
                    self._redis.xadd(STREAM_KEY, fields)
                    # Step 2: XACK original only after re-add succeeds.
                    self._redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    redelivered += 1
                    log_event(
                        logger,
                        "watchdog_redelivered",
                        original_msg_id=msg_id,
                        task_type=fields.get("task_type", "unknown"),
                    )
                except Exception as exc:  # noqa: BLE001
                    log_event(
                        logger,
                        "watchdog_redeliver_failed",
                        original_msg_id=msg_id,
                        error=str(exc),
                    )

            log_event(logger, "watchdog_reap_done", redelivered=redelivered, total=len(entries))
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "watchdog_reap_failed", error=str(exc))
