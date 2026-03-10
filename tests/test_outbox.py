"""Transactional outbox tests.

test_outbox_write_and_drain        — job + outbox row created atomically; drain publishes to stream
test_outbox_idempotent_insert      — duplicate (job_id, task_type) insert is ignored
test_outbox_drain_redis_down       — drain fails when Redis is down; row stays pending; drains on recovery
test_outbox_retention_cleanup      — delete_published removes old rows, keeps recent ones
"""
from __future__ import annotations

import json
import time
from datetime import timedelta
from uuid import uuid4

import pytest
from redis import Redis
from sqlmodel import Session, col, select

from app.models.pipeline import JobOutbox, utcnow
from app.services.outbox_service import OutboxService


class TestOutboxWriteAndDrain:
    def test_row_created_and_drained(self, session: Session, db_engine, redis_client: Redis):
        svc = OutboxService()
        job_id = uuid4()

        svc.write(session=session, job_id=job_id, task_type="scrape_run_all", payload={"job_id": str(job_id)})
        session.commit()

        # Row should be pending.
        row = session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == job_id)).first()
        assert row is not None
        assert row.published_at is None

        # Drain to stream.
        published = svc.drain(engine=db_engine, stream_key="jobs:stream", redis_client=redis_client)
        assert published == 1

        # Row should now be marked published.
        session.expire_all()
        row = session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == job_id)).first()
        assert row is not None
        assert row.published_at is not None
        assert row.stream_id is not None
        assert row.publish_attempts == 1

        # Stream should contain the message.
        messages = redis_client.xrange("jobs:stream")
        assert len(messages) == 1
        _, fields = messages[0]
        assert fields["task_type"] == "scrape_run_all"
        payload = json.loads(fields["payload_json"])
        assert payload["job_id"] == str(job_id)


class TestOutboxIdempotentInsert:
    def test_duplicate_pending_insert_is_rejected(self, session: Session):
        from sqlalchemy.exc import IntegrityError

        svc = OutboxService()
        job_id = uuid4()

        svc.write(session=session, job_id=job_id, task_type="scrape_run_all", payload={"job_id": str(job_id)})
        session.commit()

        # Inserting the same (job_id, task_type) while published_at IS NULL should fail.
        svc.write(session=session, job_id=job_id, task_type="scrape_run_all", payload={"job_id": str(job_id)})
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Only one pending row should exist.
        rows = session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == job_id)).all()
        assert len(rows) == 1


class TestOutboxDrainRedisDown:
    def test_row_stays_pending_when_redis_down_then_drains_on_recovery(
        self, session: Session, db_engine, redis_container
    ):
        svc = OutboxService()
        job_id = uuid4()

        # Stop Redis *before* creating the job so outbox is the only delivery mechanism.
        redis_container.stop()
        try:
            svc.write(session=session, job_id=job_id, task_type="scrape_run_all", payload={"job_id": str(job_id)})
            session.commit()

            # Drain should fail (Redis down); row stays pending.
            broken_client = Redis(host="127.0.0.1", port=19999, socket_connect_timeout=1)
            published = svc.drain(engine=db_engine, stream_key="jobs:stream", redis_client=broken_client)
            assert published == 0

            session.expire_all()
            row = session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == job_id)).first()
            assert row is not None
            assert row.published_at is None
            assert row.publish_attempts == 1  # attempt counted even on failure
        finally:
            redis_container.start()
            # Wait for Redis to be ready.
            for _ in range(20):
                try:
                    c = Redis.from_url(redis_container.get_connection_url(), decode_responses=True)
                    c.ping()
                    c.close()
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.5)

        # Now drain should succeed.
        recovered_client = Redis.from_url(redis_container.get_connection_url(), decode_responses=True)
        try:
            published = svc.drain(engine=db_engine, stream_key="jobs:stream", redis_client=recovered_client)
            assert published == 1

            session.expire_all()
            row = session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == job_id)).first()
            assert row is not None
            assert row.published_at is not None
        finally:
            recovered_client.close()


class TestOutboxRetentionCleanup:
    def test_delete_published_removes_old_keeps_recent(self, session: Session, db_engine, redis_client: Redis):
        svc = OutboxService()

        # Create two jobs: one "old" (8 days ago), one recent.
        old_id = uuid4()
        recent_id = uuid4()

        svc.write(session=session, job_id=old_id, task_type="scrape_run_all", payload={"job_id": str(old_id)})
        svc.write(session=session, job_id=recent_id, task_type="scrape_run_all", payload={"job_id": str(recent_id)})
        session.commit()

        # Drain both.
        svc.drain(engine=db_engine, stream_key="jobs:stream", redis_client=redis_client)

        # Manually backdate the old row's published_at.
        session.expire_all()
        old_row = session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == old_id)).first()
        assert old_row is not None
        old_row.published_at = utcnow() - timedelta(days=8)
        session.add(old_row)
        session.commit()

        deleted = svc.delete_published(session=session, ttl_days=7)
        assert deleted == 1

        # Old row gone, recent row still present.
        assert session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == old_id)).first() is None
        assert session.exec(select(JobOutbox).where(col(JobOutbox.job_id) == recent_id)).first() is not None
