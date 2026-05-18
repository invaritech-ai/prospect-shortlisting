from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.api.schemas.scrape import LetterCountsResponse
from app.api.schemas.upload import DomainList, DomainRead
from app.db.session import get_session
from app.models.core import UploadedDomain

router = APIRouter(prefix="/v1", tags=["domains"])


def _apply_scrape_status_filter(q, scrape_status: str | None):
    """Apply scrape_status filter to a UploadedDomain query."""
    if scrape_status is None or scrape_status == "all":
        return q
    if scrape_status == "pending":
        return q.where(col(UploadedDomain.scrape_status).is_(None))
    if scrape_status == "running":
        return q.where(col(UploadedDomain.scrape_status).in_(["queued", "running"]))
    if scrape_status == "done":
        return q.where(col(UploadedDomain.scrape_status) == "succeeded")
    if scrape_status == "failed":
        return q.where(col(UploadedDomain.scrape_status) == "failed")
    return q


def _apply_letter_filter(q, letter: str | None):
    """Apply first-letter filter to a UploadedDomain query."""
    if not letter or letter == "all":
        return q
    if letter == "#":
        return q.where(
            ~func.upper(func.left(col(UploadedDomain.domain), 1)).between("A", "Z")
        )
    return q.where(
        func.upper(func.left(col(UploadedDomain.domain), 1)) == letter.upper()
    )


@router.get("/companies", response_model=DomainList)
def list_domains(
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
    scrape_status: str | None = Query(default=None),
    letter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DomainList:
    base_q = select(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id)

    if upload_id is not None:
        base_q = base_q.where(col(UploadedDomain.upload_id) == upload_id)

    base_q = _apply_scrape_status_filter(base_q, scrape_status)
    base_q = _apply_letter_filter(base_q, letter)

    if search and search.strip():
        base_q = base_q.where(col(UploadedDomain.domain).ilike(f"%{search.strip()}%"))

    total = session.exec(select(func.count()).select_from(base_q.subquery())).one()
    items = session.exec(
        base_q.order_by(col(UploadedDomain.domain).asc()).limit(limit).offset(offset)
    ).all()

    return DomainList(
        total=total,
        limit=limit,
        offset=offset,
        items=[DomainRead.model_validate(d) for d in items],
    )


@router.get("/domains/letter-counts", response_model=LetterCountsResponse)
def get_letter_counts(
    campaign_id: UUID = Query(...),
    scrape_status: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> LetterCountsResponse:
    """Return per-letter domain counts for the # A B C … pill strip."""
    base_q = select(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id)
    base_q = _apply_scrape_status_filter(base_q, scrape_status)

    # Count per first letter
    letter_expr = func.upper(func.left(col(UploadedDomain.domain), 1))
    rows = session.exec(
        select(letter_expr, func.count()).select_from(base_q.subquery()).group_by(letter_expr)
    ).all()

    counts: dict[str, int] = {}
    for first_char, count in rows:
        if first_char and first_char.isalpha():
            counts[first_char] = count
        else:
            counts["#"] = counts.get("#", 0) + count

    return LetterCountsResponse(counts=counts)
