from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from uuid import uuid4

from redis import Redis
from redis.exceptions import ResponseError

from app.core.config import settings
from app.core.logging import log_event


logger = logging.getLogger(__name__)

STREAM_KEY = "jobs:stream"
GROUP_NAME = "workers"


@dataclass
class QueueTask:
    task_id: str
    task_type: str
    payload: dict[str, str]
    # Stream message ID used for XACK; None when task was not read from a stream
    # (e.g. created in tests or via direct enqueue). Not serialised to Redis.
    _stream_msg_id: str | None = field(default=None, repr=False, compare=False)


class QueueService:
    def __init__(self, *, consumer_name: str = "worker-standalone") -> None:
        self._client = Redis.from_url(settings.redis_url, decode_responses=True)
        self._stream_key = STREAM_KEY
        self._group = GROUP_NAME
        self._consumer = consumer_name
        # Legacy list key — still read by the startup migration helper.
        self.queue_key = settings.redis_queue_key
        self._ensure_group()

    def _ensure_group(self) -> None:
        """Create the consumer group idempotently. MKSTREAM creates the stream key."""
        try:
            self._client.xgroup_create(self._stream_key, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def enqueue(self, *, task_type: str, payload: dict[str, str]) -> QueueTask:
        """Directly enqueue a task to the stream.

        Used by recovery/reset endpoints and worker retry logic.
        Job *creation* endpoints must write to the outbox instead.
        """
        task_id = str(uuid4())
        self._client.xadd(
            self._stream_key,
            {
                "task_id": task_id,
                "task_type": task_type,
                "payload_json": json.dumps(payload, ensure_ascii=True),
            },
        )
        return QueueTask(task_id=task_id, task_type=task_type, payload=payload)

    def pop(self, *, timeout_sec: int) -> QueueTask | None:
        """Block-read one undelivered message from the consumer group.

        Returns ``None`` on timeout or parse error.
        The message stays in the PEL until ``ack()`` is called.
        """
        try:
            results = self._client.xreadgroup(
                self._group,
                self._consumer,
                {self._stream_key: ">"},
                count=1,
                block=timeout_sec * 1000,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "queue_xreadgroup_error", error=str(exc))
            return None

        if not results:
            return None

        _, messages = results[0]
        msg_id, msg_fields = messages[0]

        try:
            payload_raw = json.loads(msg_fields.get("payload_json", "{}"))
            payload = {str(k): str(v) for k, v in payload_raw.items()} if isinstance(payload_raw, dict) else {}
            task_id = msg_fields.get("task_id") or msg_id
            task_type = msg_fields.get("task_type", "")
            return QueueTask(
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                _stream_msg_id=msg_id,
            )
        except Exception:  # noqa: BLE001
            log_event(
                logger,
                "queue_message_parse_error",
                msg_id=msg_id,
                raw_fields=str(msg_fields)[:500],
            )
            # ACK malformed messages so they don't clog the PEL.
            self._client.xack(self._stream_key, self._group, msg_id)
            return None

    def ack(self, msg_id: str) -> None:
        """Acknowledge a stream message, removing it from the PEL."""
        self._client.xack(self._stream_key, self._group, msg_id)
