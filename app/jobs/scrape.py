"""Procrastinate tasks: run a single ScrapeJob; dispatch scrape run batches."""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from procrastinate import RetryStrategy
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from app.db.session import get_engine
from app.jobs._defaults import DEFAULT_CLASSIFY_MODEL, DEFAULT_GENERAL_MODEL
from app.jobs._priority import BULK_PIPELINE, BULK_USER  # noqa: F401
from app.models.pipeline import Company
from app.models.scrape import (
    ScrapeJob,
    ScrapeRun,
    ScrapeRunItem,
    ScrapeRunItemStatus,
    ScrapeRunStatus,
    utcnow,
)
from app.queue import app
from app.services.queue_guard import available_slots
from app.services.scrape_service import (
    CircuitBreakerOpenError,
    ScrapeJobAlreadyRunningError,
    ScrapeJobManager,
)

logger = logging.getLogger(__name__)

_manager = ScrapeJobManager()

DISPATCH_BATCH_SIZE = 100


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


async def defer_scrape_website_bulk(
    *,
    priority: int,
    job_ids: list[UUID],
    scrape_rules: dict | None,
) -> list[BaseException | None]:
    """Defer scrape_website tasks; returns per-job result (None=success, Exception=failure).

    Uses return_exceptions=True so a single defer failure doesn't lose the rest.
    Callers must check each result and handle partial failures.
    """
    if not job_ids:
        return []
    task = scrape_website.configure(priority=priority)
    return list(
        await asyncio.gather(
            *(task.defer_async(job_id=str(jid), scrape_rules=scrape_rules) for jid in job_ids),
            return_exceptions=True,
        )
    )


def _pending_stmt(engine: Engine, run_id: UUID):
    stmt = (
        select(ScrapeRunItem)
        .where(
            col(ScrapeRunItem.run_id) == run_id,
            col(ScrapeRunItem.status).in_([
                ScrapeRunItemStatus.PENDING,
                ScrapeRunItemStatus.JOB_CREATED,
            ]),
        )
        .order_by(col(ScrapeRunItem.created_at), col(ScrapeRunItem.id))
    )
    if engine.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    stmt = stmt.limit(DISPATCH_BATCH_SIZE)
    return stmt


@app.task(
    name="dispatch_scrape_run",
    queue="scrape",
    retry=RetryStrategy(max_attempts=5, wait=30),
)
async def dispatch_scrape_run(run_id: str) -> None:
    engine = get_engine()
    run_uuid = UUID(run_id)

    with Session(engine) as session:
        row = session.get(ScrapeRun, run_uuid)
        if row is None or row.status in (ScrapeRunStatus.COMPLETED, ScrapeRunStatus.FAILED):
            return
        row.status = ScrapeRunStatus.DISPATCHING
        if row.started_at is None:
            row.started_at = utcnow()
        session.add(row)
        session.commit()

    while True:
        with Session(engine) as session:
            pending = list(session.exec(_pending_stmt(engine, run_uuid)))

            if not pending:
                run = session.get(ScrapeRun, run_uuid)
                if run is not None and run.status != ScrapeRunStatus.FAILED:
                    run.status = ScrapeRunStatus.COMPLETED
                    run.finished_at = utcnow()
                    session.add(run)
                    session.commit()
                return

            slots = available_slots(engine, "scrape", len(pending))
            if slots == 0:
                # Fix: schedule_in goes via .configure(), not as a task kwarg
                await dispatch_scrape_run.configure(
                    schedule_in={"seconds": 60}
                ).defer_async(run_id=run_id)
                return

            batch = pending[:slots]
            run_row = session.get(ScrapeRun, run_uuid)
            scrape_rules_val = run_row.scrape_rules if run_row else None

            cids = [item.company_id for item in batch]
            companies_by_id = {
                c.id: c
                for c in session.exec(select(Company).where(col(Company.id).in_(cids))).all()
            }

            now_ts = utcnow()
            # job_id → item_id: store UUIDs only to avoid DetachedInstanceError
            # across session boundaries when we later update statuses post-defer.
            job_id_to_item_id: dict[UUID, UUID] = {}
            skipped_inc = failed_inc = 0

            for item in batch:
                if item.scrape_job_id is not None:
                    # Resume case: ScrapeJob already exists, only need to (re-)defer
                    job_id_to_item_id[item.scrape_job_id] = item.id
                    continue

                company = companies_by_id.get(item.company_id)
                if company is None:
                    item.status = ScrapeRunItemStatus.FAILED
                    item.error_code = "company_not_found"
                    item.updated_at = now_ts
                    session.add(item)
                    failed_inc += 1
                    continue

                try:
                    with session.begin_nested():
                        job = _manager.create_job(
                            session=session,
                            website_url=company.normalized_url,
                            js_fallback=True,
                            include_sitemap=True,
                            general_model=DEFAULT_GENERAL_MODEL,
                            classify_model=DEFAULT_CLASSIFY_MODEL,
                        )
                    # Fix: JOB_CREATED, not QUEUED — defer hasn't happened yet
                    item.scrape_job_id = job.id
                    item.status = ScrapeRunItemStatus.JOB_CREATED
                    item.updated_at = now_ts
                    session.add(item)
                    job_id_to_item_id[job.id] = item.id
                except (ScrapeJobAlreadyRunningError, CircuitBreakerOpenError, ValueError) as exc:
                    item.status = ScrapeRunItemStatus.SKIPPED
                    item.error_code = type(exc).__name__
                    item.updated_at = now_ts
                    session.add(item)
                    skipped_inc += 1

            # Commit JOB_CREATED / SKIPPED / FAILED before attempting defers
            session.commit()

        if not job_id_to_item_id:
            # Entire batch was skipped/failed; update counters and continue loop
            with Session(engine) as session:
                run = session.get(ScrapeRun, run_uuid)
                if run is not None:
                    run.skipped_count += skipped_inc
                    run.failed_count += failed_inc
                    session.add(run)
                    session.commit()
            continue

        job_ids = list(job_id_to_item_id.keys())
        results = await defer_scrape_website_bulk(
            priority=BULK_USER,
            job_ids=job_ids,
            scrape_rules=scrape_rules_val,
        )
        if results is None:
            results = [None] * len(job_ids)

        queued_inc = defer_failed_count = 0
        with Session(engine) as session:
            now_ts = utcnow()
            for jid, result in zip(job_ids, results):
                item_id = job_id_to_item_id[jid]
                db_item = session.get(ScrapeRunItem, item_id)
                if db_item is None:
                    continue
                if isinstance(result, Exception):
                    # Leave JOB_CREATED — next dispatcher invocation will retry the defer
                    logger.warning("defer failed for job %s: %s", jid, result)
                    defer_failed_count += 1
                else:
                    db_item.status = ScrapeRunItemStatus.QUEUED
                    db_item.updated_at = now_ts
                    session.add(db_item)
                    queued_inc += 1

            run = session.get(ScrapeRun, run_uuid)
            if run is not None:
                run.queued_count += queued_inc
                run.skipped_count += skipped_inc
                run.failed_count += failed_inc
                session.add(run)
            session.commit()

        if defer_failed_count > 0:
            logger.warning(
                "dispatch_scrape_run %s: %d defer(s) failed; items remain job_created for retry",
                run_id,
                defer_failed_count,
            )
