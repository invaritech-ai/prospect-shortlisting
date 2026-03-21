from __future__ import annotations

import logging
from datetime import timedelta

from sqlmodel import Session, col, select

from app.celery_app import app
from app.core.logging import log_event
from app.db.session import get_engine
from app.models import AnalysisJob, ContactFetchJob, ScrapeJob
from app.models.pipeline import AnalysisJobState, ContactFetchJobState

logger = logging.getLogger(__name__)

# Jobs not updated within these windows are considered stuck.
_SCRAPE_STUCK_MINUTES = 35    # normal max runtime ~30 min (soft_time_limit)
_ANALYSIS_STUCK_MINUTES = 20  # normal max runtime < 10 min
_CONTACT_STUCK_MINUTES = 15   # normal max runtime < 10 min (polling)

# After this many reconciler re-queues a scrape job is marked terminal so it
# doesn't cycle forever on sites that consistently hang or fail.
_SCRAPE_MAX_RECONCILE_ATTEMPTS = 3


@app.task(
    name="app.tasks.beat.reconcile_stuck_jobs",
    queue="beat",
)
def reconcile_stuck_jobs() -> None:
    """Periodic safety-net: find non-terminal jobs that haven't progressed and re-enqueue them."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    scrape_cutoff = now - timedelta(minutes=_SCRAPE_STUCK_MINUTES)
    analysis_cutoff = now - timedelta(minutes=_ANALYSIS_STUCK_MINUTES)
    contact_cutoff = now - timedelta(minutes=_CONTACT_STUCK_MINUTES)

    # Import here to avoid circular imports at module load time.
    from app.tasks.scrape import scrape_website
    from app.tasks.analysis import run_analysis_job
    from app.tasks.contacts import fetch_contacts

    engine = get_engine()
    with Session(engine) as session:
        stuck_scrapes = session.exec(
            select(ScrapeJob).where(
                col(ScrapeJob.terminal_state).is_(False),
                col(ScrapeJob.updated_at) < scrape_cutoff,
            )
        ).all()

        stuck_analysis = session.exec(
            select(AnalysisJob).where(
                col(AnalysisJob.terminal_state).is_(False),
                col(AnalysisJob.state).in_([AnalysisJobState.RUNNING.value, AnalysisJobState.QUEUED.value]),
                col(AnalysisJob.updated_at) < analysis_cutoff,
            )
        ).all()

        stuck_contacts = session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.terminal_state).is_(False),
                col(ContactFetchJob.state).in_([
                    ContactFetchJobState.RUNNING.value,
                    ContactFetchJobState.QUEUED.value,
                ]),
                col(ContactFetchJob.updated_at) < contact_cutoff,
            )
        ).all()

        # Capture IDs before commit (objects expire after commit in SQLAlchemy).
        # Only re-queue jobs that were reset (not those just flagged as terminal).
        scrape_ids = [
            str(job.id) for job in stuck_scrapes
            if (job.reconcile_count or 0) <= _SCRAPE_MAX_RECONCILE_ATTEMPTS
        ]
        analysis_ids = [str(job.id) for job in stuck_analysis]
        contact_ids = [str(job.id) for job in stuck_contacts]

        for job in stuck_scrapes:
            job.reconcile_count = (job.reconcile_count or 0) + 1
            if job.reconcile_count > _SCRAPE_MAX_RECONCILE_ATTEMPTS:
                # Site consistently fails to scrape — mark terminal so it is
                # not re-queued again.  Flag for manual review.
                job.status = "failed"
                job.terminal_state = True
                job.last_error_code = "needs_manual_review"
                job.last_error_message = (
                    f"Scrape timed out or was killed {job.reconcile_count} times. "
                    "Site may be permanently inaccessible, bot-protected, or require manual inspection."
                )
                job.finished_at = now
                log_event(logger, "reconciler_flagged_scrape", job_id=str(job.id),
                          reconcile_count=job.reconcile_count)
            else:
                job.status = "created"
                job.lock_token = None
                job.lock_expires_at = None
            job.updated_at = now
            session.add(job)

        for job in stuck_analysis:
            job.state = AnalysisJobState.QUEUED
            job.started_at = None
            job.lock_token = None
            job.lock_expires_at = None
            job.updated_at = now
            session.add(job)

        for job in stuck_contacts:
            job.state = ContactFetchJobState.QUEUED
            job.lock_token = None
            job.lock_expires_at = None
            job.updated_at = now
            session.add(job)

        session.commit()

    for job_id in scrape_ids:
        scrape_website.delay(job_id)
        log_event(logger, "reconciler_requeued_scrape", job_id=job_id)

    for job_id in analysis_ids:
        run_analysis_job.delay(job_id)
        log_event(logger, "reconciler_requeued_analysis", job_id=job_id)

    for job_id in contact_ids:
        fetch_contacts.delay(job_id)
        log_event(logger, "reconciler_requeued_contact", job_id=job_id)

    log_event(
        logger,
        "reconciler_done",
        stuck_scrapes=len(scrape_ids),
        stuck_analysis=len(analysis_ids),
        stuck_contacts=len(contact_ids),
    )
