"""Cross-stage queue history.

Unions job rows from S1 (CrawlJob), S2 (AnalysisJob), S3 (ContactFetchJob),
S4 (ContactRevealJob), and S5 (ContactVerifyJob) so the QueueHistoryView in
the SPA can show one timeline of work across the whole pipeline.

Performance notes
-----------------
- State filter (live/history) is applied in SQL, not Python — avoids
  hydrating terminal rows just to discard them on a Live tab fetch.
- Each per-stage query is `ORDER BY created_at DESC LIMIT (limit + offset)`
  so we never pull more than we could possibly return after merging.
- For `view=history`, we default to a 7-day window. Override with
  ?since=<iso8601> or ?days=<n> if you need older rows.
- Campaign scoping uses a JOIN through companies/uploads instead of a
  large `WHERE company_id IN (...)` clause.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

_LIVE_STATES = ("queued", "running")
_DEFAULT_HISTORY_DAYS = 7


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


@router.get("/queue-history", response_model=QueueHistoryResponse)
def get_queue_history(
    campaign_id: UUID = Query(...),
    stage: str = Query("all"),
    view: str = Query("all"),  # "live" | "history" | "all"
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    days: int | None = Query(None, ge=1, le=90),
    session: Session = Depends(get_session),
) -> QueueHistoryResponse:
    stage = (stage or "all").lower()
    view = (view or "all").lower()

    # Default time floor: 7d for history, none for live (live rows are by
    # definition recent). Caller can override with ?days=N.
    floor: datetime | None = None
    if days is not None:
        floor = datetime.now(timezone.utc) - timedelta(days=days)
    elif view == "history":
        floor = datetime.now(timezone.utc) - timedelta(days=_DEFAULT_HISTORY_DAYS)

    fetch_cap = limit + offset  # we never need more than this from any one stage

    items: list[QueueHistoryItem] = []

    def _apply_view_filter(stmt: Any, model: Any) -> Any:
        if view == "live":
            return stmt.where(col(model.state).in_(_LIVE_STATES))
        if view == "history":
            return stmt.where(col(model.state).notin_(_LIVE_STATES))
        return stmt

    def _collect_with_company(stage_label: str, model: Any) -> None:
        if stage != "all" and stage != stage_label:
            return
        stmt = (
            select(model, Company.domain)
            .join(Company, col(Company.id) == col(model.company_id))
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(col(Upload.campaign_id) == campaign_id)
        )
        stmt = _apply_view_filter(stmt, model)
        if floor is not None:
            stmt = stmt.where(col(model.created_at) >= floor)
        stmt = stmt.order_by(col(model.created_at).desc()).limit(fetch_cap)
        for row, domain in session.exec(stmt):
            items.append(
                QueueHistoryItem(
                    id=row.id,
                    stage=stage_label,
                    company_domain=domain,
                    state=_state_value(row.state),
                    created_at=row.created_at,
                    started_at=getattr(row, "started_at", None),
                    finished_at=getattr(row, "finished_at", None),
                    error_code=getattr(row, "last_error_code", None),
                )
            )

    def _collect_no_company(stage_label: str, model: Any) -> None:
        # S5 has no company FK and no campaign FK either — surface all rows.
        if stage != "all" and stage != stage_label:
            return
        stmt = select(model)
        stmt = _apply_view_filter(stmt, model)
        if floor is not None:
            stmt = stmt.where(col(model.created_at) >= floor)
        stmt = stmt.order_by(col(model.created_at).desc()).limit(fetch_cap)
        for row in session.exec(stmt):
            items.append(
                QueueHistoryItem(
                    id=row.id,
                    stage=stage_label,
                    company_domain=None,
                    state=_state_value(row.state),
                    created_at=row.created_at,
                    started_at=getattr(row, "started_at", None),
                    finished_at=getattr(row, "finished_at", None),
                    error_code=getattr(row, "last_error_code", None),
                )
            )

    _collect_with_company("s1", CrawlJob)
    _collect_with_company("s2", AnalysisJob)
    _collect_with_company("s3", ContactFetchJob)
    _collect_with_company("s4", ContactRevealJob)
    _collect_no_company("s5", ContactVerifyJob)

    items.sort(key=lambda it: it.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    total = len(items)
    items = items[offset : offset + limit]
    return QueueHistoryResponse(items=items, total=total)
