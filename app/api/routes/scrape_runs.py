"""Scrape batch API — create and query S1 scrape batches."""
from __future__ import annotations

import math
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
    ScrapeResultRead,
)
from app.db.session import get_session
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeBatch, ScrapeResult, ScrapeSettings

router = APIRouter(prefix="/v1", tags=["scrape-batches"])

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


@router.post("/scrape-batches", response_model=ScrapeBatchRead, status_code=201)
async def create_scrape_batch(
    body: ScrapeBatchCreate,
    session: Session = Depends(get_session),
) -> ScrapeBatchRead:
    # 1. Reject if an active batch already exists for this campaign
    active = session.exec(
        select(ScrapeBatch).where(
            col(ScrapeBatch.campaign_id) == body.campaign_id,
            col(ScrapeBatch.state).in_(list(_ACTIVE_STATES)),
        ).limit(1)
    ).first()
    if active:
        raise HTTPException(
            status_code=409,
            detail="A scrape batch is already active for this campaign. Wait for it to finish.",
        )

    # 2. Resolve matching domains
    domains = _resolve_domains(session, body.campaign_id, body)
    if not domains:
        raise HTTPException(status_code=400, detail="No matching domains found.")

    # 3. Load active settings (fall back to baked-in defaults)
    settings_row = session.exec(
        select(ScrapeSettings).where(
            col(ScrapeSettings.campaign_id) == body.campaign_id,
            col(ScrapeSettings.is_active).is_(True),
        ).order_by(col(ScrapeSettings.created_at).desc()).limit(1)
    ).first()

    settings_snapshot = (
        settings_row.structured_rules_json if settings_row else DEFAULT_STRUCTURED_RULES
    )

    # 4. Create batch row
    batch = ScrapeBatch(
        campaign_id=body.campaign_id,
        scrape_settings_id=settings_row.id if settings_row else None,
        settings_snapshot_json=settings_snapshot,
        state="queued",
        selected_domain_count=len(domains),
    )
    session.add(batch)
    session.flush()  # populate batch.id

    # 5. Create one ScrapeResult per domain + mark domain status queued
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

    # 6. Defer dispatcher task
    from app.jobs.scrape import dispatch_scrape_batch
    await dispatch_scrape_batch.defer_async(batch_id=str(batch.id))

    return _batch_read(batch)


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
    batch = session.exec(
        select(ScrapeBatch).where(
            col(ScrapeBatch.campaign_id) == campaign_id,
            col(ScrapeBatch.state).in_(list(_ACTIVE_STATES)),
        ).order_by(col(ScrapeBatch.created_at).desc()).limit(1)
    ).first()
    return _batch_read(batch) if batch else None


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
