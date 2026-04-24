"""GET /v1/queue-history — unified view of jobs across all pipeline stages."""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.db.session import get_session
from app.models.pipeline import (
    AnalysisJob,
    Company,
    ContactFetchBatch,
    ContactRevealBatch,
    ContactRevealJob,
    ContactFetchJob,
    ContactVerifyJob,
    CrawlJob,
    PipelineRun,
    Upload,
)

router = APIRouter(prefix="/v1", tags=["queue-history"])
logger = logging.getLogger(__name__)

_CRAWL_TERMINAL = {"succeeded", "failed", "dead"}


class QueueHistoryItem(BaseModel):
    id: str
    stage: str          # s1 | s2 | s3 | s4 | s5
    company_domain: str | None
    state: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None


class QueueHistoryResponse(BaseModel):
    items: list[QueueHistoryItem]
    total: int


# ── Per-stage query helpers ────────────────────────────────────────────────────

def _s1_items(session: Session, campaign_id: UUID | None, live: bool, history: bool) -> list[QueueHistoryItem]:
    q = (
        select(CrawlJob, Company)
        .join(Company, CrawlJob.company_id == Company.id)
        .join(Upload, CrawlJob.upload_id == Upload.id)
    )
    if campaign_id:
        q = q.where(col(Upload.campaign_id) == campaign_id)
    if live:
        q = q.where(~col(CrawlJob.state).in_(list(_CRAWL_TERMINAL)))
    elif history:
        q = q.where(col(CrawlJob.state).in_(list(_CRAWL_TERMINAL)))
    rows = session.exec(q).all()
    return [
        QueueHistoryItem(
            id=str(job.id), stage="s1", company_domain=company.domain,
            state=job.state, created_at=job.created_at,
            started_at=job.started_at, finished_at=job.finished_at,
            error_code=job.last_error_code,
        )
        for job, company in rows
    ]


def _s2_items(session: Session, campaign_id: UUID | None, live: bool, history: bool) -> list[QueueHistoryItem]:
    q = (
        select(AnalysisJob, Company)
        .join(Company, AnalysisJob.company_id == Company.id)
        .join(Upload, AnalysisJob.upload_id == Upload.id)
    )
    if campaign_id:
        q = q.where(col(Upload.campaign_id) == campaign_id)
    if live:
        q = q.where(col(AnalysisJob.terminal_state) == False)  # noqa: E712
    elif history:
        q = q.where(col(AnalysisJob.terminal_state) == True)  # noqa: E712
    rows = session.exec(q).all()
    return [
        QueueHistoryItem(
            id=str(job.id), stage="s2", company_domain=company.domain,
            state=job.state, created_at=job.created_at,
            started_at=job.started_at, finished_at=job.finished_at,
            error_code=job.last_error_code,
        )
        for job, company in rows
    ]


def _s3_items(session: Session, campaign_id: UUID | None, live: bool, history: bool) -> list[QueueHistoryItem]:
    q = (
        select(ContactFetchJob, Company)
        .join(Company, ContactFetchJob.company_id == Company.id)
        .join(Upload, Company.upload_id == Upload.id)
    )
    if campaign_id:
        q = q.where(col(Upload.campaign_id) == campaign_id)
    if live:
        q = q.where(col(ContactFetchJob.terminal_state) == False)  # noqa: E712
    elif history:
        q = q.where(col(ContactFetchJob.terminal_state) == True)  # noqa: E712
    rows = session.exec(q).all()
    return [
        QueueHistoryItem(
            id=str(job.id), stage="s3", company_domain=company.domain,
            state=job.state, created_at=job.created_at,
            started_at=job.started_at, finished_at=job.finished_at,
            error_code=job.last_error_code,
        )
        for job, company in rows
    ]


def _s4_items(session: Session, campaign_id: UUID | None, live: bool, history: bool) -> list[QueueHistoryItem]:
    q = (
        select(ContactRevealJob, Company)
        .join(Company, ContactRevealJob.company_id == Company.id)
        .join(ContactRevealBatch, ContactRevealJob.contact_reveal_batch_id == ContactRevealBatch.id)
    )
    if campaign_id:
        q = q.where(col(ContactRevealBatch.campaign_id) == campaign_id)
    if live:
        q = q.where(col(ContactRevealJob.terminal_state) == False)  # noqa: E712
    elif history:
        q = q.where(col(ContactRevealJob.terminal_state) == True)  # noqa: E712
    rows = session.exec(q).all()
    return [
        QueueHistoryItem(
            id=str(job.id), stage="s4", company_domain=company.domain,
            state=job.state, created_at=job.created_at,
            started_at=job.started_at, finished_at=job.finished_at,
            error_code=job.last_error_code,
        )
        for job, company in rows
    ]


def _s5_items(session: Session, campaign_id: UUID | None, live: bool, history: bool) -> list[QueueHistoryItem]:
    q = select(ContactVerifyJob)
    if campaign_id:
        q = (
            q.join(PipelineRun, ContactVerifyJob.pipeline_run_id == PipelineRun.id)
            .where(col(PipelineRun.campaign_id) == campaign_id)
        )
    if live:
        q = q.where(col(ContactVerifyJob.terminal_state) == False)  # noqa: E712
    elif history:
        q = q.where(col(ContactVerifyJob.terminal_state) == True)  # noqa: E712
    rows = session.exec(q).all()
    return [
        QueueHistoryItem(
            id=str(job.id), stage="s5", company_domain=None,
            state=job.state, created_at=job.created_at,
            started_at=job.started_at, finished_at=job.finished_at,
            error_code=job.last_error_code,
        )
        for job in rows
    ]


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/queue-history", response_model=QueueHistoryResponse)
def get_queue_history(
    campaign_id: UUID | None = Query(default=None),
    stage: str = Query(default="all"),          # all | s1 | s2 | s3 | s4 | s5
    view: str = Query(default="all"),           # all | live | history
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> QueueHistoryResponse:
    live = view == "live"
    history = view == "history"

    stage_fns = {
        "s1": _s1_items,
        "s2": _s2_items,
        "s3": _s3_items,
        "s4": _s4_items,
        "s5": _s5_items,
    }

    selected = [stage] if stage in stage_fns else list(stage_fns.keys())
    items: list[QueueHistoryItem] = []
    for key in selected:
        items.extend(stage_fns[key](session, campaign_id, live, history))

    items.sort(key=lambda x: x.created_at, reverse=True)
    total = len(items)
    return QueueHistoryResponse(items=items[offset: offset + limit], total=total)
