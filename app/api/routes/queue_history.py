"""Cross-stage queue history.

Unions job rows from S1 (CrawlJob), S2 (AnalysisJob), S3 (ContactFetchJob),
S4 (ContactRevealJob), and S5 (ContactVerifyJob) so the QueueHistoryView in
the SPA can show one timeline of work across the whole pipeline.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.db.session import get_session
from app.models import (
    AnalysisJob,
    Company,
    ContactFetchJob,
    ContactVerifyJob,
    CrawlJob,
    Upload,
)
from app.models.pipeline import ContactRevealJob

router = APIRouter(prefix="/v1", tags=["queue-history"])

_LIVE_STATES = {"queued", "running"}


class QueueHistoryItem(BaseModel):
    id: UUID
    stage: str  # s1 | s2 | s3 | s4 | s5
    company_domain: str | None = None
    state: str
    created_at: Any
    started_at: Any | None = None
    finished_at: Any | None = None
    error_code: str | None = None


class QueueHistoryResponse(BaseModel):
    items: list[QueueHistoryItem]
    total: int


def _state_value(value: Any) -> str:
    return getattr(value, "value", str(value))


def _passes_view(state_str: str, view: str) -> bool:
    if view == "live":
        return state_str in _LIVE_STATES
    if view == "history":
        return state_str not in _LIVE_STATES
    return True  # "all"


@router.get("/queue-history", response_model=QueueHistoryResponse)
def get_queue_history(
    campaign_id: UUID = Query(...),
    stage: str = Query("all"),
    view: str = Query("all"),  # "live" | "history" | "all"
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> QueueHistoryResponse:
    stage = (stage or "all").lower()
    view = (view or "all").lower()

    # Resolve company_id → domain for the four stages with a company FK.
    company_rows = list(
        session.exec(
            select(Company.id, Company.domain)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(col(Upload.campaign_id) == campaign_id)
        )
    )
    company_ids = [row[0] for row in company_rows]
    domain_by_company: dict[UUID, str] = {row[0]: row[1] for row in company_rows}
    if not company_ids:
        return QueueHistoryResponse(items=[], total=0)

    items: list[QueueHistoryItem] = []

    def _collect(stage_label: str, model: Any, has_company: bool = True) -> None:
        if stage != "all" and stage != stage_label:
            return
        stmt = select(model)
        if has_company:
            stmt = stmt.where(col(model.company_id).in_(company_ids))
        for row in session.exec(stmt):
            state_str = _state_value(getattr(row, "state", ""))
            if not _passes_view(state_str, view):
                continue
            cid = getattr(row, "company_id", None)
            items.append(
                QueueHistoryItem(
                    id=row.id,
                    stage=stage_label,
                    company_domain=domain_by_company.get(cid) if cid else None,
                    state=state_str,
                    created_at=getattr(row, "created_at", None),
                    started_at=getattr(row, "started_at", None),
                    finished_at=getattr(row, "finished_at", None),
                    error_code=getattr(row, "last_error_code", None),
                )
            )

    _collect("s1", CrawlJob)
    _collect("s2", AnalysisJob)
    _collect("s3", ContactFetchJob)
    _collect("s4", ContactRevealJob)
    # S5 has no company_id (bulk job over many contacts); we still surface it
    # but with no domain. There is no campaign FK either, so we include all
    # ContactVerifyJob rows when stage=all|s5 — acceptable today since S5 jobs
    # are scoped to the active campaign in practice.
    _collect("s5", ContactVerifyJob, has_company=False)

    # Sort newest-first by created_at (None last).
    items.sort(key=lambda it: it.created_at or "", reverse=True)
    total = len(items)
    items = items[offset : offset + limit]
    return QueueHistoryResponse(items=items, total=total)
