from __future__ import annotations

import asyncio
import logging

from billiard.exceptions import SoftTimeLimitExceeded  # type: ignore[import]

from app.celery_app import app
from app.core.logging import log_event
from app.db.session import get_engine
from app.services.scrape_service import ScrapeService

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="app.tasks.scrape.scrape_website",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=1800,
    time_limit=1860,
    max_retries=2,
    queue="scrape",
)
def scrape_website(self, job_id: str, scrape_rules: dict | None = None) -> None:  # type: ignore[misc]
    """Celery task: run the full scrape pipeline for a single ScrapeJob."""
    import time
    log_event(logger, "scrape_celery_task_received",
              job_id=job_id, worker=self.request.hostname, retries=self.request.retries)
    engine = get_engine()

    # Fast-exit: skip jobs already in terminal state (cancelled, done, failed).
    # Avoids expensive asyncio.run + ScrapeService setup for stale queue entries.
    if _is_terminal(engine, job_id):
        log_event(logger, "scrape_task_skip_terminal", job_id=job_id)
        return

    service = ScrapeService()
    t_start = time.monotonic()
    try:
        asyncio.run(service.run_scrape(engine=engine, job_id=job_id, scrape_rules=scrape_rules))
        elapsed = time.monotonic() - t_start
        log_event(logger, "scrape_celery_task_done", job_id=job_id, elapsed_sec=round(elapsed, 1))
    except SoftTimeLimitExceeded:
        elapsed = time.monotonic() - t_start
        log_event(logger, "scrape_task_timeout", job_id=job_id, elapsed_sec=round(elapsed, 1))
        _mark_failed(job_id, "timeout", "Task exceeded 30-minute soft time limit")
        raise
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t_start
        log_event(logger, "scrape_task_error", job_id=job_id,
                  error=str(exc)[:500], elapsed_sec=round(elapsed, 1))
        _mark_failed(job_id, "task_exception", str(exc)[:500])
        raise


def _is_terminal(engine, job_id: str) -> bool:  # type: ignore[type-arg]
    """Lightweight check: is this job already in a terminal state?"""
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT terminal_state FROM scrapejob WHERE id = :jid"),
            {"jid": job_id},
        ).first()
        return bool(row and row[0])


def _mark_failed(job_id: str, error_code: str, error_message: str) -> None:
    from datetime import datetime, timezone
    from uuid import UUID

    from sqlalchemy import update as sa_update
    from sqlmodel import Session, col

    from app.db.session import get_engine
    from app.models import ScrapeJob
    from app.services.pipeline_service import recompute_company_stages

    now = datetime.now(timezone.utc)
    engine = get_engine()
    with Session(engine) as session:
        job = session.get(ScrapeJob, UUID(job_id))
        normalized_url = job.normalized_url if job else None
        session.exec(
            sa_update(ScrapeJob)
            .where(col(ScrapeJob.id) == job_id)
            .values(
                status="failed",
                terminal_state=True,
                last_error_code=error_code,
                last_error_message=error_message,
                finished_at=now,
                updated_at=now,
            )
        )
        if normalized_url:
            recompute_company_stages(session, normalized_urls=[normalized_url])
        session.commit()
