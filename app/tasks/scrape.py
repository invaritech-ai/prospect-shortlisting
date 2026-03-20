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
def scrape_website(self, job_id: str) -> None:  # type: ignore[misc]
    """Celery task: run the full scrape pipeline for a single ScrapeJob."""
    engine = get_engine()
    service = ScrapeService()
    try:
        asyncio.run(service.run_scrape(engine=engine, job_id=job_id))
    except SoftTimeLimitExceeded:
        log_event(logger, "scrape_task_timeout", job_id=job_id)
        _mark_failed(job_id, "timeout", "Task exceeded 30-minute limit")
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "scrape_task_error", job_id=job_id, error=str(exc))
        _mark_failed(job_id, "task_exception", str(exc)[:500])
        raise


def _mark_failed(job_id: str, error_code: str, error_message: str) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import update as sa_update
    from sqlmodel import col

    from app.db.session import get_engine
    from app.models import ScrapeJob

    now = datetime.now(timezone.utc)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
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
