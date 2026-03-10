"""CAS (compare-and-set) ownership tests.

test_cas_duplicate_claim     — two threads claim same job; only one wins
test_cas_lock_expiry_reclaim — backdated lock; new worker claims successfully
test_list_to_stream_migration — old list entries migrate to stream at startup
"""
from __future__ import annotations

import threading
from datetime import timedelta, timezone
from uuid import uuid4

import pytest
from redis import Redis
from sqlmodel import Session, select

from app.models import ScrapeJob
from app.models.pipeline import utcnow
from app.services.queue_service import QueueService, STREAM_KEY


def _make_scrape_job(session: Session, *, url: str = "https://example.com") -> ScrapeJob:
    from app.services.url_utils import normalize_url, domain_from_url
    normalized = normalize_url(url) or url
    domain = domain_from_url(normalized) or normalized
    job = ScrapeJob(
        website_url=url,
        normalized_url=normalized,
        domain=domain,
        max_pages=10,
        max_depth=2,
        js_fallback=False,
        include_sitemap=False,
        general_model="test",
        classify_model="test",
        ocr_model="test",
        enable_ocr=False,
        max_images_per_page=0,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


class TestCasDuplicateClaim:
    """Two threads attempt to CAS-claim the same job simultaneously.

    Only one should win; both should complete without producing a double write.
    """

    def test_only_one_winner(self, session: Session, db_engine):
        from sqlalchemy import Engine
        from app.services.scrape_service import ScrapeService

        job = _make_scrape_job(session)
        job_id = job.id

        winners: list[str] = []
        lock = threading.Lock()

        def attempt_claim(token_label: str):
            from datetime import timedelta
            from uuid import uuid4
            from sqlalchemy import update as sa_update
            from sqlmodel import Session as S, col
            now = utcnow()
            lock_token = str(uuid4())
            with S(db_engine) as s:
                result = s.execute(
                    sa_update(ScrapeJob)
                    .where(
                        ScrapeJob.id == job_id,
                        col(ScrapeJob.terminal_state).is_(False),
                        col(ScrapeJob.status) == "created",
                        (col(ScrapeJob.lock_token).is_(None) | (col(ScrapeJob.lock_expires_at) < now)),
                    )
                    .values(
                        status="running_step1",
                        lock_token=lock_token,
                        lock_expires_at=now + timedelta(minutes=5),
                    )
                    .execution_options(synchronize_session=False)
                )
                s.commit()
                if result.rowcount == 1:
                    with lock:
                        winners.append(token_label)

        t1 = threading.Thread(target=attempt_claim, args=("thread-1",))
        t2 = threading.Thread(target=attempt_claim, args=("thread-2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(winners) == 1, f"Expected exactly 1 winner, got: {winners}"


class TestCasLockExpiryReclaim:
    """A job with a backdated (expired) lock can be claimed by a new worker."""

    def test_expired_lock_is_reclaimable(self, session: Session, db_engine):
        from sqlalchemy import update as sa_update
        from sqlmodel import Session as S, col
        from uuid import uuid4

        job = _make_scrape_job(session, url="https://expired-lock-test.com")
        job_id = job.id

        # Simulate a worker that claimed the job but its lock expired.
        stale_token = str(uuid4())
        past = utcnow() - timedelta(hours=1)
        with S(db_engine) as s:
            s.execute(
                sa_update(ScrapeJob)
                .where(ScrapeJob.id == job_id)
                .values(
                    status="running_step1",
                    lock_token=stale_token,
                    lock_expires_at=past,
                )
                .execution_options(synchronize_session=False)
            )
            s.commit()

        # New worker should be able to claim it.
        new_token = str(uuid4())
        now = utcnow()
        with S(db_engine) as s:
            result = s.execute(
                sa_update(ScrapeJob)
                .where(
                    ScrapeJob.id == job_id,
                    col(ScrapeJob.terminal_state).is_(False),
                    (col(ScrapeJob.lock_token).is_(None) | (col(ScrapeJob.lock_expires_at) < now)),
                )
                .values(
                    status="running_step1",
                    lock_token=new_token,
                    lock_expires_at=now + timedelta(minutes=30),
                )
                .execution_options(synchronize_session=False)
            )
            s.commit()
            assert result.rowcount == 1

        with S(db_engine) as s:
            j = s.get(ScrapeJob, job_id)
            assert j is not None
            assert j.lock_token == new_token


class TestListToStreamMigration:
    """Old Redis list entries are migrated to the stream at startup."""

    def test_migration_moves_entries(self, redis_container, db_engine):
        import json
        from unittest.mock import patch
        from redis import Redis as R
        from app.services.queue_service import QueueService, STREAM_KEY

        client = R.from_url(redis_container.get_connection_url(), decode_responses=True)

        old_key = "prospect:jobs"
        # Seed the old list with two tasks.
        for i in range(2):
            client.rpush(old_key, json.dumps({
                "task_id": str(uuid4()),
                "task_type": "scrape_run_all",
                "payload": {"job_id": str(uuid4())},
            }))

        # Patch settings so migration guard key is cleared between test runs.
        guard_key = "jobs:list_migration_done"
        client.delete(guard_key)
        # Also clear any existing stream so we can count freshly.
        client.delete(STREAM_KEY)

        with patch("app.core.config.settings.redis_url", redis_container.get_connection_url()), \
             patch("app.core.config.settings.redis_queue_key", old_key):
            from app.worker import _migrate_list_to_stream
            queue = QueueService(consumer_name="test")
            # Patch the queue's stream key to point to our test client.
            queue._stream_key = STREAM_KEY
            queue._client = client
            _migrate_list_to_stream(queue)

        # Old list should be empty; stream should have 2 entries.
        assert client.llen(old_key) == 0
        stream_len = client.xlen(STREAM_KEY)
        assert stream_len == 2

        # Running migration again should be a no-op (guard key set).
        client.rpush(old_key, json.dumps({"task_id": str(uuid4()), "task_type": "noop", "payload": {}}))
        _migrate_list_to_stream(queue)
        assert client.xlen(STREAM_KEY) == 2  # unchanged

        client.close()
