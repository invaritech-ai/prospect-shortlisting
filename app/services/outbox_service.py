from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import UUID, uuid4

from redis import Redis
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models.pipeline import JobOutbox, utcnow


logger = logging.getLogger(__name__)


class OutboxService:
    """Write job rows to the transactional outbox and drain them to a Redis Stream."""

    def write(
        self,
        *,
        session: Session,
        job_id: UUID,
        task_type: str,
        payload: dict,
    ) -> None:
        """Add one outbox row to *session*. Caller is responsible for committing.

        The unique partial index ``uq_job_outbox_pending`` on ``(job_id, task_type)
        WHERE published_at IS NULL`` silently deduplicates if the API is retried
        before the dispatcher runs.
        """
        row = JobOutbox(
            id=uuid4(),
            job_id=job_id,
            task_type=task_type,
            payload_json=payload,
        )
        session.add(row)

    def drain(
        self,
        *,
        engine: Engine,
        stream_key: str,
        redis_client: Redis,
    ) -> int:
        """Publish up to 100 pending outbox rows to *stream_key*.

        Flow per row:
          1. XADD to stream first (enqueue before marking published).
          2. On success: mark ``published_at``, set ``stream_id``, increment
             ``publish_attempts`` — commit.
          3. On XADD failure: increment ``publish_attempts`` only — commit.
             Row stays pending and retries next loop.

        The FOR UPDATE SKIP LOCKED read is committed before any Redis I/O to
        avoid holding DB row locks across network calls.

        Returns the number of rows successfully published.
        """
        # Step A: read pending rows and immediately release the FOR UPDATE locks.
        with Session(engine) as read_session:
            rows = list(
                read_session.exec(
                    select(JobOutbox)
                    .where(col(JobOutbox.published_at).is_(None))
                    .order_by(col(JobOutbox.created_at))
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            )
            row_snapshots = [
                {"id": r.id, "task_type": r.task_type, "payload_json": r.payload_json}
                for r in rows
            ]
            read_session.commit()  # releases FOR UPDATE locks

        if not row_snapshots:
            return 0

        # Step B: for each row, XADD then update outbox (separate per-row tx).
        published = 0
        now = utcnow()
        for snap in row_snapshots:
            stream_id: str | None = None
            xadd_ok = False
            try:
                raw_sid = redis_client.xadd(
                    stream_key,
                    {
                        "task_type": snap["task_type"],
                        "payload_json": json.dumps(snap["payload_json"]),
                    },
                )
                stream_id = raw_sid.decode() if isinstance(raw_sid, bytes) else raw_sid
                xadd_ok = True
                published += 1
            except Exception as exc:  # noqa: BLE001
                log_event(
                    logger,
                    "outbox_xadd_failed",
                    outbox_id=str(snap["id"]),
                    task_type=snap["task_type"],
                    error=str(exc),
                )

            # Update the outbox row regardless (published_at only on XADD success).
            try:
                with Session(engine) as write_session:
                    row = write_session.get(JobOutbox, snap["id"])
                    if row is None:
                        continue
                    row.publish_attempts += 1
                    if xadd_ok:
                        row.published_at = now
                        row.stream_id = stream_id
                    write_session.add(row)
                    write_session.commit()
            except Exception as exc:  # noqa: BLE001
                log_event(
                    logger,
                    "outbox_update_failed",
                    outbox_id=str(snap["id"]),
                    error=str(exc),
                )

        return published

    def delete_published(self, *, session: Session, ttl_days: int = 7) -> int:
        """Delete published outbox rows older than *ttl_days*. Returns deleted count."""
        cutoff = utcnow() - timedelta(days=ttl_days)
        rows = list(
            session.exec(
                select(JobOutbox).where(
                    col(JobOutbox.published_at).is_not(None)
                    & (col(JobOutbox.published_at) < cutoff)
                )
            )
        )
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)
