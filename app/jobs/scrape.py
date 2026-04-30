"""Procrastinate task: run a single ScrapeJob."""
from __future__ import annotations

import logging
from uuid import UUID

from procrastinate import RetryStrategy
from sqlmodel import Session

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.models import ScrapeJob
from app.queue import app
from app.services.scrape_service import ScrapeJobManager

logger = logging.getLogger(__name__)

_manager = ScrapeJobManager()


@app.task(
    name="scrape_website",
    queue="scrape",
    retry=RetryStrategy(max_attempts=2, wait=60),
)
async def scrape_website(job_id: str, scrape_rules: dict | None = None) -> None:
    engine = get_engine()
    with Session(engine) as session:
        job = session.get(ScrapeJob, UUID(job_id))
    if job is None or job.terminal_state:
        logger.info("scrape_website skipped: job %s already terminal", job_id)
        return
    await _manager.run_scrape(engine=engine, job_id=UUID(job_id), scrape_rules=scrape_rules)
