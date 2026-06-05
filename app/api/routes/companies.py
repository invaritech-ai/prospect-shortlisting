from __future__ import annotations

import time
from logging import getLogger
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func
from sqlmodel import Session, col, select

from app.api.schemas.scrape import LetterCountsResponse, ScrapeCountsResponse
from app.api.schemas.upload import DomainList, DomainRead
from app.db.session import get_session
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeResult

router = APIRouter(prefix="/v1", tags=["domains"])
logger = getLogger(__name__)


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
            ~func.upper(func.substr(col(UploadedDomain.domain), 1, 1)).between("A", "Z")
        )
    return q.where(
        func.upper(func.substr(col(UploadedDomain.domain), 1, 1)) == letter.upper()
    )


def _build_domains_response(
    *,
    session: Session,
    campaign_id: UUID,
    base_q,
    limit: int,
    offset: int,
    sort_by: str | None = None,
    sort_dir: str | None = None,
) -> DomainList:
    total = session.exec(select(func.count()).select_from(base_q.subquery())).one()
    sorted_q = _apply_domain_sort(base_q, campaign_id=campaign_id, sort_by=sort_by, sort_dir=sort_dir)
    items = session.exec(
        sorted_q.limit(limit).offset(offset)
    ).all()
    domain_ids = [d.id for d in items]
    latest_by_domain: dict[UUID, tuple[UUID, str | None, object, str | None, bool | None, str | None]] = {}
    if domain_ids:
        latest_ts_sq = (
            select(
                col(ScrapeResult.domain_id).label("domain_id"),
                func.max(col(ScrapeResult.updated_at)).label("latest_updated_at"),
            )
            .where(
                col(ScrapeResult.campaign_id) == campaign_id,
                col(ScrapeResult.domain_id).in_(domain_ids),
            )
            .group_by(col(ScrapeResult.domain_id))
            .subquery()
        )
        latest_rows = session.exec(
            select(
                col(ScrapeResult.domain_id),
                col(ScrapeResult.id),
                col(ScrapeResult.error_code),
                col(ScrapeResult.updated_at),
                col(ScrapeResult.failure_class),
                col(ScrapeResult.retryable),
                col(ScrapeResult.final_url),
            )
            .join(
                latest_ts_sq,
                (
                    col(ScrapeResult.domain_id) == latest_ts_sq.c.domain_id
                ) & (
                    col(ScrapeResult.updated_at) == latest_ts_sq.c.latest_updated_at
                ),
            )
        ).all()
        latest_by_domain = {
            row[0]: (row[1], row[2], row[3], row[4], row[5], row[6])
            for row in latest_rows
        }

    return DomainList(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            DomainRead.model_validate(
                {
                    **d.model_dump(),
                    "latest_scrape_result_id": latest_by_domain.get(d.id, (None, None, None, None, None, None))[0],
                    "latest_scrape_error_code": latest_by_domain.get(d.id, (None, None, None, None, None, None))[1],
                    "latest_scrape_updated_at": latest_by_domain.get(d.id, (None, None, None, None, None, None))[2],
                    "latest_scrape_failure_class": latest_by_domain.get(d.id, (None, None, None, None, None, None))[3],
                    "latest_scrape_retryable": latest_by_domain.get(d.id, (None, None, None, None, None, None))[4],
                    "latest_scrape_final_url": latest_by_domain.get(d.id, (None, None, None, None, None, None))[5],
                }
            )
            for d in items
        ],
    )


def _sort_desc(sort_dir: str | None) -> bool:
    return (sort_dir or "").strip().lower() == "desc"


def _ordered(expr, *, descending: bool):
    return expr.desc() if descending else expr.asc()


def _apply_domain_sort(q, *, campaign_id: UUID, sort_by: str | None, sort_dir: str | None):
    descending = _sort_desc(sort_dir)
    normalized = (sort_by or "").strip().lower()
    if normalized == "domain":
        return q.order_by(_ordered(col(UploadedDomain.domain), descending=descending), col(UploadedDomain.id).asc())
    if normalized == "status":
        status_expr = func.coalesce(col(UploadedDomain.scrape_status), "pending")
        return q.order_by(_ordered(status_expr, descending=descending), col(UploadedDomain.domain).asc())
    if normalized == "updated":
        latest_scrape_updated_at = (
            select(func.max(col(ScrapeResult.updated_at)))
            .where(
                col(ScrapeResult.campaign_id) == campaign_id,
                col(ScrapeResult.domain_id) == col(UploadedDomain.id),
            )
            .scalar_subquery()
        )
        updated_expr = func.coalesce(latest_scrape_updated_at, col(UploadedDomain.created_at))
        return q.order_by(_ordered(updated_expr, descending=descending), col(UploadedDomain.domain).asc())
    return q.order_by(col(UploadedDomain.domain).asc())


@router.get("/companies", response_model=DomainList)
def list_domains(
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
    scrape_status: str | None = Query(default=None),
    letter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DomainList:
    started = time.perf_counter()
    base_q = select(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id)

    if not isinstance(upload_id, UUID):
        upload_id = None
    if not isinstance(sort_by, str):
        sort_by = None
    if not isinstance(sort_dir, str):
        sort_dir = None

    if upload_id is not None:
        base_q = base_q.where(col(UploadedDomain.upload_id) == upload_id)

    base_q = _apply_scrape_status_filter(base_q, scrape_status)
    base_q = _apply_letter_filter(base_q, letter)

    if search and search.strip():
        base_q = base_q.where(col(UploadedDomain.domain).ilike(f"%{search.strip()}%"))

    response = _build_domains_response(
        session=session,
        campaign_id=campaign_id,
        base_q=base_q,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "poll_companies campaign_id=%s scrape_status=%s letter=%s search=%s limit=%s offset=%s total=%s items=%s elapsed_ms=%s",
        campaign_id,
        scrape_status,
        letter,
        bool(search and search.strip()),
        limit,
        offset,
        response.total,
        len(response.items),
        elapsed_ms,
    )
    return response


@router.get("/domains/ai-decidable", response_model=DomainList)
def list_ai_decidable_domains(
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
    letter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DomainList:
    started = time.perf_counter()
    base_q = select(UploadedDomain).where(
        col(UploadedDomain.campaign_id) == campaign_id,
        col(UploadedDomain.scrape_status) == "succeeded",
    )
    if upload_id is not None:
        base_q = base_q.where(col(UploadedDomain.upload_id) == upload_id)
    base_q = _apply_letter_filter(base_q, letter)
    if search and search.strip():
        base_q = base_q.where(col(UploadedDomain.domain).ilike(f"%{search.strip()}%"))

    response = _build_domains_response(
        session=session,
        campaign_id=campaign_id,
        base_q=base_q,
        limit=limit,
        offset=offset,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "poll_ai_decidable_domains campaign_id=%s letter=%s search=%s limit=%s offset=%s total=%s items=%s elapsed_ms=%s",
        campaign_id,
        letter,
        bool(search and search.strip()),
        limit,
        offset,
        response.total,
        len(response.items),
        elapsed_ms,
    )
    return response


@router.get("/domains/letter-counts", response_model=LetterCountsResponse)
def get_letter_counts(
    campaign_id: UUID = Query(...),
    scrape_status: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> LetterCountsResponse:
    started = time.perf_counter()
    """Return per-letter domain counts for the # A B C … pill strip."""
    base_q = select(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id)
    base_q = _apply_scrape_status_filter(base_q, scrape_status)

    # Count per first letter — build a direct aggregate query (no subquery wrapping,
    # which would cause the column reference to escape the subquery scope).
    letter_expr = func.upper(func.substr(col(UploadedDomain.domain), 1, 1))
    count_q = select(letter_expr, func.count(UploadedDomain.id)).where(
        col(UploadedDomain.campaign_id) == campaign_id
    )
    count_q = _apply_scrape_status_filter(count_q, scrape_status)
    count_q = count_q.group_by(letter_expr)
    rows = session.exec(count_q).all()

    counts: dict[str, int] = {}
    for first_char, count in rows:
        if first_char and first_char.isalpha():
            counts[first_char] = count
        else:
            counts["#"] = counts.get("#", 0) + count

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "poll_letter_counts campaign_id=%s scrape_status=%s buckets=%s elapsed_ms=%s",
        campaign_id,
        scrape_status,
        len(counts),
        elapsed_ms,
    )
    return LetterCountsResponse(counts=counts)


@router.get("/domains/scrape-counts", response_model=ScrapeCountsResponse)
def get_scrape_counts(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ScrapeCountsResponse:
    """Return S1 badge/progress counts for one campaign."""
    status_rows = session.exec(
        select(col(UploadedDomain.scrape_status), func.count(UploadedDomain.id))
        .where(col(UploadedDomain.campaign_id) == campaign_id)
        .group_by(col(UploadedDomain.scrape_status))
    ).all()
    by_status = {status: count for status, count in status_rows}

    latest_ts_sq = (
        select(
            col(ScrapeResult.domain_id).label("domain_id"),
            func.max(col(ScrapeResult.updated_at)).label("latest_updated_at"),
        )
        .where(col(ScrapeResult.campaign_id) == campaign_id)
        .group_by(col(ScrapeResult.domain_id))
        .subquery()
    )
    retryable_failed = session.exec(
        select(func.count(func.distinct(ScrapeResult.domain_id)))
        .join(
            latest_ts_sq,
            and_(
                col(ScrapeResult.domain_id) == latest_ts_sq.c.domain_id,
                col(ScrapeResult.updated_at) == latest_ts_sq.c.latest_updated_at,
            ),
        )
        .join(UploadedDomain, col(UploadedDomain.id) == col(ScrapeResult.domain_id))
        .where(
            col(UploadedDomain.campaign_id) == campaign_id,
            col(UploadedDomain.scrape_status) == "failed",
            col(ScrapeResult.retryable).is_(True),
        )
    ).one()

    pending = by_status.get(None, 0)
    queued = by_status.get("queued", 0)
    running = by_status.get("running", 0)
    succeeded = by_status.get("succeeded", 0)
    failed = by_status.get("failed", 0)
    total = sum(by_status.values())

    return ScrapeCountsResponse(
        total=total,
        pending=pending,
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        retryable_failed=retryable_failed,
        remaining_work=pending + queued + running + retryable_failed,
    )
