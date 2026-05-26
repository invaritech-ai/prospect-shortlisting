"""Scrape batch API — create and query S1 scrape batches."""
from __future__ import annotations

import math
import time
from logging import getLogger
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.scrape import (
    DEFAULT_STRUCTURED_RULES,
    ScrapeBatchCreate,
    ScrapeBatchList,
    ScrapeBatchRead,
    ScrapeJobStatusRead,
    ScrapeResultRead,
)
from app.db.session import get_engine, get_session
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeBatch, ScrapeResult, ScrapeSettings
from app.services.queue_guard import is_procrastinate_schema_ready
from app.services.scrape_job_status import build_scrape_job_status
from app.services.scrape_prompt_compiler import build_scrape_rules_snapshot

router = APIRouter(prefix="/v1", tags=["scrape-batches"])
logger = getLogger(__name__)

_ACTIVE_STATES = ("queued", "dispatching", "running")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_eta(batch: ScrapeBatch) -> float | None:
    done = batch.success_count + batch.failed_count
    remaining = batch.selected_domain_count - done
    if remaining <= 0:
        return 0.0
    elapsed_secs = (_utcnow() - batch.created_at).total_seconds()
    if elapsed_secs < 5 or done == 0:
        return None
    rate_per_sec = done / elapsed_secs
    if rate_per_sec <= 0:
        return None
    return math.ceil(remaining / rate_per_sec)


def _batch_read(batch: ScrapeBatch) -> ScrapeBatchRead:
    return ScrapeBatchRead(
        id=batch.id,
        campaign_id=batch.campaign_id,
        state=batch.state,
        selected_domain_count=batch.selected_domain_count,
        queued_count=batch.queued_count,
        success_count=batch.success_count,
        failed_count=batch.failed_count,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
        eta_seconds=_compute_eta(batch) if batch.state in _ACTIVE_STATES else None,
    )


def _status_to_batch_read(batch: ScrapeBatch, status: ScrapeJobStatusRead) -> ScrapeBatchRead:
    return ScrapeBatchRead(
        id=batch.id,
        campaign_id=batch.campaign_id,
        state=status.state,
        selected_domain_count=status.selected,
        queued_count=status.queued + status.running,
        success_count=status.succeeded,
        failed_count=status.failed,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
        eta_seconds=status.eta_seconds,
    )


def _resolve_domains(
    session: Session,
    campaign_id: UUID,
    body: ScrapeBatchCreate,
) -> list[UploadedDomain]:
    """Resolve the union of explicit domain_ids + filter criteria."""
    seen_ids: set[UUID] = set()
    domains: list[UploadedDomain] = []

    if body.filter:
        q = select(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id)
        s = body.filter.scrape_status
        if s == "pending":
            q = q.where(col(UploadedDomain.scrape_status).is_(None))
        elif s == "failed":
            q = q.where(col(UploadedDomain.scrape_status) == "failed")
        elif s == "done":
            q = q.where(col(UploadedDomain.scrape_status) == "succeeded")
        elif s == "running":
            q = q.where(col(UploadedDomain.scrape_status).in_(["queued", "running"]))

        letter = body.filter.letter
        if letter and letter != "all":
            if letter == "#":
                q = q.where(
                    ~func.upper(func.left(col(UploadedDomain.domain), 1)).between("A", "Z")
                )
            else:
                q = q.where(
                    func.upper(func.left(col(UploadedDomain.domain), 1)) == letter.upper()
                )

        for d in session.exec(q).all():
            if d.id not in seen_ids:
                seen_ids.add(d.id)
                domains.append(d)

    if body.domain_ids:
        explicit = session.exec(
            select(UploadedDomain).where(
                col(UploadedDomain.id).in_(body.domain_ids),
                col(UploadedDomain.campaign_id) == campaign_id,
            )
        ).all()
        for d in explicit:
            if d.id not in seen_ids:
                seen_ids.add(d.id)
                domains.append(d)

    return domains


async def _enqueue_scrape_results(result_ids: list[UUID]) -> None:
    from app.jobs.scrape import scrape_domain
    for result_id in result_ids:
        await scrape_domain.defer_async(result_id=str(result_id))


def _active_batch_for_campaign(*, session: Session, campaign_id: UUID) -> ScrapeBatch | None:
    rows = session.exec(
        select(ScrapeBatch)
        .where(col(ScrapeBatch.campaign_id) == campaign_id)
        .order_by(col(ScrapeBatch.created_at).desc())
        .limit(20)
    ).all()
    for batch in rows:
        status = build_scrape_job_status(session=session, batch_id=batch.id)
        if status and status.state in {"queued", "running"}:
            return batch
    return None


async def _create_scrape_job_impl(
    *,
    body: ScrapeBatchCreate,
    session: Session,
) -> ScrapeBatchRead:
    if not is_procrastinate_schema_ready(get_engine()):
        raise HTTPException(
            status_code=503,
            detail=(
                "Queue schema is not initialized. Run "
                "`uv run python scripts/apply_procrastinate_schema_maybe.py` "
                "and start the scrape worker (`./scripts/run_worker.sh scrape 2`)."
            ),
        )

    active = _active_batch_for_campaign(session=session, campaign_id=body.campaign_id)
    if active:
        raise HTTPException(
            status_code=409,
            detail="A scrape batch is already active for this campaign. Wait for it to finish.",
        )

    domains = _resolve_domains(session, body.campaign_id, body)
    if not domains:
        raise HTTPException(status_code=400, detail="No matching domains found.")

    settings_row = session.exec(
        select(ScrapeSettings).where(
            col(ScrapeSettings.campaign_id) == body.campaign_id,
            col(ScrapeSettings.is_active).is_(True),
        ).order_by(col(ScrapeSettings.created_at).desc()).limit(1)
    ).first()

    settings_snapshot = build_scrape_rules_snapshot(
        instruction_text=settings_row.instruction_text if settings_row else None,
        structured_rules=settings_row.structured_rules_json if settings_row else None,
        default_rules=DEFAULT_STRUCTURED_RULES,
    )

    batch = ScrapeBatch(
        campaign_id=body.campaign_id,
        scrape_settings_id=settings_row.id if settings_row else None,
        settings_snapshot_json=settings_snapshot,
        state="queued",
        selected_domain_count=len(domains),
    )
    session.add(batch)
    session.flush()

    results = [
        ScrapeResult(
            campaign_id=body.campaign_id,
            domain_id=d.id,
            scrape_batch_id=batch.id,
            state="queued",
        )
        for d in domains
    ]
    session.add_all(results)

    for d in domains:
        d.scrape_status = "queued"
        session.add(d)

    session.commit()
    session.refresh(batch)

    result_ids = [result.id for result in results]
    await _enqueue_scrape_results(result_ids)
    batch.queued_count = len(result_ids)
    session.add(batch)
    session.commit()
    session.refresh(batch)

    return _batch_read(batch)


@router.post("/scrape-jobs", response_model=ScrapeBatchRead, status_code=201)
async def create_scrape_job(
    body: ScrapeBatchCreate,
    session: Session = Depends(get_session),
) -> ScrapeBatchRead:
    return await _create_scrape_job_impl(body=body, session=session)


@router.post("/scrape-batches", response_model=ScrapeBatchRead, status_code=201)
async def create_scrape_batch(
    body: ScrapeBatchCreate,
    session: Session = Depends(get_session),
) -> ScrapeBatchRead:
    return await _create_scrape_job_impl(body=body, session=session)


@router.get("/scrape-batches", response_model=ScrapeBatchList)
def list_scrape_batches(
    campaign_id: UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> ScrapeBatchList:
    rows = session.exec(
        select(ScrapeBatch)
        .where(col(ScrapeBatch.campaign_id) == campaign_id)
        .order_by(col(ScrapeBatch.created_at).desc())
        .limit(limit)
    ).all()
    total = session.exec(
        select(func.count()).where(col(ScrapeBatch.campaign_id) == campaign_id)
    ).one()
    return ScrapeBatchList(total=total, items=[_batch_read(b) for b in rows])


@router.get("/scrape-batches/active", response_model=ScrapeBatchRead | None)
def get_active_batch(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ScrapeBatchRead | None:
    started = time.perf_counter()
    rows = session.exec(
        select(ScrapeBatch)
        .where(col(ScrapeBatch.campaign_id) == campaign_id)
        .order_by(col(ScrapeBatch.created_at).desc())
        .limit(20)
    ).all()
    for batch in rows:
        status = build_scrape_job_status(session=session, batch_id=batch.id)
        if status and status.state in {"queued", "running"}:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "poll_active_batch campaign_id=%s active=true batch_id=%s elapsed_ms=%s",
                campaign_id,
                batch.id,
                elapsed_ms,
            )
            return _status_to_batch_read(batch, status)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "poll_active_batch campaign_id=%s active=false elapsed_ms=%s",
        campaign_id,
        elapsed_ms,
    )
    return None


@router.get("/scrape-jobs/{batch_id}/status", response_model=ScrapeJobStatusRead)
def get_scrape_job_status(
    batch_id: UUID,
    session: Session = Depends(get_session),
) -> ScrapeJobStatusRead:
    started = time.perf_counter()
    status = build_scrape_job_status(session=session, batch_id=batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "poll_scrape_job_status batch_id=%s state=%s selected=%s terminal=%s queued=%s running=%s elapsed_ms=%s",
        batch_id,
        status.state,
        status.selected,
        status.terminal,
        status.queued,
        status.running,
        elapsed_ms,
    )
    return status


@router.get("/scrape-batches/{batch_id}", response_model=ScrapeBatchRead)
def get_scrape_batch(
    batch_id: UUID,
    session: Session = Depends(get_session),
) -> ScrapeBatchRead:
    batch = session.get(ScrapeBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return _batch_read(batch)


@router.get("/scrape-results", response_model=ScrapeResultRead | None)
def get_scrape_result_for_domain(
    campaign_id: UUID = Query(...),
    domain_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ScrapeResultRead | None:
    """Return the most recent scrape result for a domain (for the content drawer)."""
    result = session.exec(
        select(ScrapeResult)
        .where(
            col(ScrapeResult.campaign_id) == campaign_id,
            col(ScrapeResult.domain_id) == domain_id,
            col(ScrapeResult.state) == "succeeded",
        )
        .order_by(col(ScrapeResult.created_at).desc())
        .limit(1)
    ).first()
    if result is None:
        return None
    return ScrapeResultRead.model_validate(result, from_attributes=True)
