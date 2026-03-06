from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from redis import Redis

from app.core.config import settings


@dataclass
class QueueTask:
    task_id: str
    task_type: str
    payload: dict[str, str]


class QueueService:
    def __init__(self) -> None:
        self._client = Redis.from_url(settings.redis_url, decode_responses=True)
        self._queue_key = settings.redis_queue_key

    @property
    def queue_key(self) -> str:
        return self._queue_key

    def enqueue(self, *, task_type: str, payload: dict[str, str]) -> QueueTask:
        task = QueueTask(
            task_id=str(uuid4()),
            task_type=task_type,
            payload=payload,
        )
        body = json.dumps(
            {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "payload": task.payload,
            },
            ensure_ascii=True,
        )
        self._client.rpush(self._queue_key, body)
        return task

    def pop(self, *, timeout_sec: int) -> QueueTask | None:
        item = self._client.blpop(self._queue_key, timeout=timeout_sec)
        if not item:
            return None
        _, raw = item
        try:
            decoded = json.loads(raw)
            task_id = str(decoded.get("task_id", "") or "")
            task_type = str(decoded.get("task_type", "") or "")
            payload_raw = decoded.get("payload", {})
            payload = payload_raw if isinstance(payload_raw, dict) else {}
            return QueueTask(task_id=task_id, task_type=task_type, payload={str(k): str(v) for k, v in payload.items()})
        except Exception:  # noqa: BLE001
            return None
