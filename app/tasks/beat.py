from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.celery_app import app
from app.core.logging import log_event
from app.db.session import get_engine
from app.models import AiUsageEvent, AnalysisJob, ContactFetchJob, ContactVerifyJob, ScrapeJob
from app.models.pipeline import AnalysisJobState, ContactFetchJobState, ContactVerifyJobState

logger = logging.getLogger(__name__)

# Jobs not updated within these windows are considered stuck.
_SCRAPE_STUCK_MINUTES = 35    # normal max runtime ~30 min (soft_time_limit)
_ANALYSIS_STUCK_MINUTES = 35  # lock TTL is 35 min; must match
_CONTACT_STUCK_MINUTES = 15   # normal max runtime < 10 min (polling)
_VERIFY_STUCK_MINUTES = 15

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
    verify_cutoff = now - timedelta(minutes=_VERIFY_STUCK_MINUTES)

    # Import here to avoid circular imports at module load time.
    from app.tasks.scrape import scrape_website
    from app.tasks.analysis import run_analysis_job
    from app.tasks.contacts import fetch_contacts, fetch_contacts_apollo, verify_contacts_batch

    engine = get_engine()
    with Session(engine) as session:
        # ── Scrape jobs ──────────────────────────────────────────────
        # "Never started" = still waiting in the queue (started_at IS NULL).
        # Re-enqueue without incrementing reconcile_count since they may
        # have simply fallen off Redis.
        never_started_scrapes = session.exec(
            select(ScrapeJob).where(
                col(ScrapeJob.terminal_state).is_(False),
                col(ScrapeJob.started_at).is_(None),
                col(ScrapeJob.updated_at) < scrape_cutoff,
            )
        ).all()

        # "Started but stalled" = worker claimed but never finished.
        stuck_scrapes = session.exec(
            select(ScrapeJob).where(
                col(ScrapeJob.terminal_state).is_(False),
                col(ScrapeJob.started_at).is_not(None),
                col(ScrapeJob.updated_at) < scrape_cutoff,
            )
        ).all()

        # ── Analysis jobs ────────────────────────────────────────────
        never_started_analysis = session.exec(
            select(AnalysisJob).where(
                col(AnalysisJob.terminal_state).is_(False),
                col(AnalysisJob.state).in_([AnalysisJobState.QUEUED.value]),
                col(AnalysisJob.started_at).is_(None),
                col(AnalysisJob.updated_at) < analysis_cutoff,
            )
        ).all()

        stuck_analysis = session.exec(
            select(AnalysisJob).where(
                col(AnalysisJob.terminal_state).is_(False),
                col(AnalysisJob.state).in_([AnalysisJobState.RUNNING.value, AnalysisJobState.QUEUED.value]),
                col(AnalysisJob.started_at).is_not(None),
                col(AnalysisJob.updated_at) < analysis_cutoff,
            )
        ).all()

        # ── Contact jobs ─────────────────────────────────────────────
        never_started_contacts = session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.terminal_state).is_(False),
                col(ContactFetchJob.state).in_([ContactFetchJobState.QUEUED.value]),
                col(ContactFetchJob.started_at).is_(None),
                col(ContactFetchJob.updated_at) < contact_cutoff,
            )
        ).all()

        stuck_contacts = session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.terminal_state).is_(False),
                col(ContactFetchJob.state).in_([
                    ContactFetchJobState.RUNNING.value,
                    ContactFetchJobState.QUEUED.value,
                ]),
                col(ContactFetchJob.started_at).is_not(None),
                col(ContactFetchJob.updated_at) < contact_cutoff,
            )
        ).all()

        never_started_verify = session.exec(
            select(ContactVerifyJob).where(
                col(ContactVerifyJob.terminal_state).is_(False),
                col(ContactVerifyJob.state).in_([ContactVerifyJobState.QUEUED.value]),
                col(ContactVerifyJob.started_at).is_(None),
                col(ContactVerifyJob.updated_at) < verify_cutoff,
            )
        ).all()

        stuck_verify = session.exec(
            select(ContactVerifyJob).where(
                col(ContactVerifyJob.terminal_state).is_(False),
                col(ContactVerifyJob.state).in_([
                    ContactVerifyJobState.RUNNING.value,
                    ContactVerifyJobState.QUEUED.value,
                ]),
                col(ContactVerifyJob.started_at).is_not(None),
                col(ContactVerifyJob.updated_at) < verify_cutoff,
            )
        ).all()

        # Capture IDs before commit (objects expire after commit).
        # Never-started jobs: re-enqueue without penalty.
        ns_scrape_ids = [str(job.id) for job in never_started_scrapes]
        # Stuck jobs: only re-queue those under the max reconcile attempts.
        stuck_scrape_ids = [
            str(job.id) for job in stuck_scrapes
            if (job.reconcile_count or 0) <= _SCRAPE_MAX_RECONCILE_ATTEMPTS
        ]
        ns_analysis_ids = [str(job.id) for job in never_started_analysis]
        stuck_analysis_ids = [str(job.id) for job in stuck_analysis]
        ns_contact_jobs = [(str(job.id), str(job.provider or "snov")) for job in never_started_contacts]
        stuck_contact_jobs = [(str(job.id), str(job.provider or "snov")) for job in stuck_contacts]
        ns_verify_ids = [str(job.id) for job in never_started_verify]
        stuck_verify_ids = [str(job.id) for job in stuck_verify]

        # Reset never-started scrapes (no reconcile_count increment).
        for job in never_started_scrapes:
            job.status = "created"
            job.lock_token = None
            job.lock_expires_at = None
            job.updated_at = now
            session.add(job)

        # Reset stuck scrapes (increment reconcile_count, may mark terminal).
        for job in stuck_scrapes:
            job.reconcile_count = (job.reconcile_count or 0) + 1
            if job.reconcile_count > _SCRAPE_MAX_RECONCILE_ATTEMPTS:
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

        for job in never_started_analysis + stuck_analysis:
            job.state = AnalysisJobState.QUEUED
            job.started_at = None
            job.lock_token = None
            job.lock_expires_at = None
            job.updated_at = now
            session.add(job)

        for job in never_started_contacts + stuck_contacts:
            job.state = ContactFetchJobState.QUEUED
            job.lock_token = None
            job.lock_expires_at = None
            job.updated_at = now
            session.add(job)

        for job in never_started_verify + stuck_verify:
            job.state = ContactVerifyJobState.QUEUED
            job.lock_token = None
            job.lock_expires_at = None
            job.updated_at = now
            session.add(job)

        session.commit()

    # Enqueue after commit.
    for job_id in ns_scrape_ids + stuck_scrape_ids:
        scrape_website.delay(job_id)
        log_event(logger, "reconciler_requeued_scrape", job_id=job_id)

    for job_id in ns_analysis_ids + stuck_analysis_ids:
        run_analysis_job.delay(job_id)
        log_event(logger, "reconciler_requeued_analysis", job_id=job_id)

    for job_id, provider in ns_contact_jobs + stuck_contact_jobs:
        if provider == "apollo":
            fetch_contacts_apollo.delay(job_id)
        else:
            fetch_contacts.delay(job_id)
        log_event(logger, "reconciler_requeued_contact", job_id=job_id, provider=provider)

    for job_id in ns_verify_ids + stuck_verify_ids:
        verify_contacts_batch.delay(job_id)
        log_event(logger, "reconciler_requeued_contact_verify", job_id=job_id)

    total_scrape = len(ns_scrape_ids) + len(stuck_scrape_ids)
    total_analysis = len(ns_analysis_ids) + len(stuck_analysis_ids)
    total_contacts = len(ns_contact_jobs) + len(stuck_contact_jobs)
    total_verify = len(ns_verify_ids) + len(stuck_verify_ids)
    log_event(
        logger,
        "reconciler_done",
        never_started_scrapes=len(ns_scrape_ids),
        stuck_scrapes=len(stuck_scrape_ids),
        never_started_analysis=len(ns_analysis_ids),
        stuck_analysis=len(stuck_analysis_ids),
        never_started_contacts=len(ns_contact_jobs),
        stuck_contacts=len(stuck_contact_jobs),
        never_started_verify=len(ns_verify_ids),
        stuck_verify=len(stuck_verify_ids),
        total_requeued=total_scrape + total_analysis + total_contacts + total_verify,
    )


@app.task(
    name="app.tasks.beat.reconcile_openrouter_costs",
    queue="beat",
)
def reconcile_openrouter_costs() -> None:
    """Placeholder reconciler: mark billable OpenRouter events as reconciled."""
    engine = get_engine()
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(AiUsageEvent).where(
                    col(AiUsageEvent.provider) == "openrouter",
                    col(AiUsageEvent.billed_cost_usd).is_not(None),
                )
            )
        )
        updated = 0
        for row in rows:
            if row.reconciliation_status != "reconciled":
                row.reconciliation_status = "reconciled"
                session.add(row)
                updated += 1
        session.commit()

        pending_count = session.exec(
            select(func.count(AiUsageEvent.id)).where(
                col(AiUsageEvent.provider) == "openrouter",
                col(AiUsageEvent.reconciliation_status) == "pending",
            )
        ).one()
        reconciled_count = session.exec(
            select(func.count(AiUsageEvent.id)).where(
                col(AiUsageEvent.provider) == "openrouter",
                col(AiUsageEvent.reconciliation_status) == "reconciled",
            )
        ).one()

    log_event(
        logger,
        "openrouter_cost_reconciliation_done",
        scanned=len(rows),
        updated=updated,
        pending_count=int(pending_count or 0),
        reconciled_count=int(reconciled_count or 0),
    )
