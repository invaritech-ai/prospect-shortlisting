from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.upload import DomainList, DomainRead
from app.db.session import get_session
from app.models.core import UploadedDomain

router = APIRouter(prefix="/v1", tags=["domains"])


@router.get("/companies", response_model=DomainList)
def list_domains(
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DomainList:
    """List uploaded domains for a campaign, optionally filtered by upload."""
    base_q = select(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id)
    if upload_id is not None:
        base_q = base_q.where(col(UploadedDomain.upload_id) == upload_id)
    total = session.exec(select(func.count()).select_from(base_q.subquery())).one()
    items = session.exec(
        base_q.order_by(col(UploadedDomain.created_at).desc()).limit(limit).offset(offset)
    ).all()
    return DomainList(
        total=total,
        limit=limit,
        offset=offset,
        items=[DomainRead.model_validate(d) for d in items],
    )
