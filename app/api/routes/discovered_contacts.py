from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import Integer, case, func, or_, select as sa_select, text
from sqlmodel import Session, col, select

from app.api.schemas.contacts import (
    ContactRevealRequest,
    ContactRevealResult,
    ContactCompanyListResponse,
    ContactCompanySummary,
    DiscoveredContactCountsResponse,
    DiscoveredContactListResponse,
    DiscoveredContactRead,
    MatchGapFilter,
)
from app.core.config import settings
from app.db.session import get_session
from app.models import Campaign, Company, DiscoveredContact, ProspectContact, Upload
from app.models.pipeline import coerce_utc_datetime, utcnow
from app.services.contact_reveal_queue_service import ContactRevealQueueService, discovered_group_key
from app.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyUnavailableError,
    check_idempotency,
    clear_idempotency_reservation,
    normalize_idempotency_key,
    store_idempotency_response,
)

router = APIRouter(prefix="/v1", tags=["discovered-contacts"])

_ALLOWED_MATCH_GAP_FILTERS = frozenset({"all", "contacts_no_match", "matched_no_email", "ready_candidates"})


def _campaign_or_404(session: Session, campaign_id: UUID) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


def _campaign_upload_scope(campaign_id: UUID):
    return col(Company.upload_id).in_(select(Upload.id).where(col(Upload.campaign_id) == campaign_id))


def _freshness_cutoff() -> datetime:
    return utcnow() - timedelta(days=max(1, int(settings.contact_discovery_freshness_days)))


def _validate_match_gap_filter(value: str) -> MatchGapFilter:
    normalized = (value or "all").strip().lower()
    if normalized not in _ALLOWED_MATCH_GAP_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid match_gap_filter.")
    return normalized  # type: ignore[return-value]


def _domain_first_letter_expr():
    return func.lower(func.substr(Company.domain, 1, 1))


def _parse_letters(letters: str | None) -> list[str]:
    if not letters:
        return []
    normalized = sorted({part.strip().lower() for part in letters.split(",") if part.strip()})
    return [ltr for ltr in normalized if len(ltr) == 1 and "a" <= ltr <= "z"]


def _apply_discovered_filters(
    stmt,
    *,
    title_match: bool | None = None,
    provider: str | None = None,
    search: str | None = None,
    company_id: UUID | None = None,
    company_ids: list[UUID] | None = None,
    letters: list[str] | None = None,
):
    stmt = stmt.where(col(DiscoveredContact.is_active).is_(True))
    if title_match is not None:
        stmt = stmt.where(col(DiscoveredContact.title_match) == title_match)
    if provider:
        stmt = stmt.where(col(DiscoveredContact.provider) == provider.strip().lower())
    if company_id is not None:
        stmt = stmt.where(col(DiscoveredContact.company_id) == company_id)
    if company_ids:
        stmt = stmt.where(col(DiscoveredContact.company_id).in_(company_ids))
    if letters:
        stmt = stmt.where(_domain_first_letter_expr().in_(letters))
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(DiscoveredContact.first_name).like(term),
                func.lower(DiscoveredContact.last_name).like(term),
                func.lower(DiscoveredContact.title).like(term),
                func.lower(Company.domain).like(term),
            )
        )
    return stmt


@router.get("/discovered-contacts", response_model=DiscoveredContactListResponse)
def list_discovered_contacts(
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    provider: str | None = Query(default=None),
    company_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    letters: str | None = Query(default=None),
    count_by_letters: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> DiscoveredContactListResponse:
    _campaign_or_404(session, campaign_id)
    letter_values = _parse_letters(letters)
    cutoff = _freshness_cutoff()

    stmt = select(DiscoveredContact, Company.domain).join(Company, col(Company.id) == col(DiscoveredContact.company_id))
    stmt = stmt.where(_campaign_upload_scope(campaign_id))
    stmt = _apply_discovered_filters(
        stmt,
        title_match=title_match,
        provider=provider,
        search=search,
        company_id=company_id,
        letters=letter_values or None,
    )

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = list(
        session.exec(
            stmt.order_by(
                col(DiscoveredContact.title_match).desc(),
                col(DiscoveredContact.last_seen_at).desc(),
                col(DiscoveredContact.created_at).desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )
    items = [
        DiscoveredContactRead.model_validate(
            {
                **contact.model_dump(),
                "domain": domain,
                "freshness_status": "fresh" if coerce_utc_datetime(contact.last_seen_at) >= cutoff else "stale",
                "group_key": discovered_group_key(contact),
            }
        )
        for contact, domain in rows
    ]

    letter_counts: dict[str, int] | None = None
    if count_by_letters:
        letter_stmt = (
            select(_domain_first_letter_expr().label("letter"), func.count().label("cnt"))
            .select_from(DiscoveredContact)
            .join(Company, col(Company.id) == col(DiscoveredContact.company_id))
            .where(_campaign_upload_scope(campaign_id), _domain_first_letter_expr().between("a", "z"))
        )
        letter_stmt = _apply_discovered_filters(
            letter_stmt,
            title_match=title_match,
            provider=provider,
            search=search,
            company_id=company_id,
        )
        letter_stmt = letter_stmt.group_by(_domain_first_letter_expr())
        letter_counts = {chr(ord("a") + i): 0 for i in range(26)}
        for letter, count in session.exec(letter_stmt):
            if letter in letter_counts:
                letter_counts[letter] = int(count)

    return DiscoveredContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=items,
        letter_counts=letter_counts,
    )


@router.get("/companies/{company_id}/discovered-contacts", response_model=DiscoveredContactListResponse)
def list_company_discovered_contacts(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    provider: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DiscoveredContactListResponse:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return list_discovered_contacts(
        campaign_id=campaign_id,
        title_match=title_match,
        provider=provider,
        company_id=company_id,
        search=search,
        limit=limit,
        offset=offset,
        letters=None,
        count_by_letters=False,
        session=session,
    )


@router.get("/discovered-contacts/counts", response_model=DiscoveredContactCountsResponse)
def get_discovered_contact_counts(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> DiscoveredContactCountsResponse:
    _campaign_or_404(session, campaign_id)
    cutoff = _freshness_cutoff()
    statement = select(
        func.count().label("total"),
        func.coalesce(func.sum(case((col(DiscoveredContact.title_match).is_(True), 1), else_=0)), 0).label("matched"),
        func.coalesce(func.sum(case((col(DiscoveredContact.last_seen_at) < cutoff, 1), else_=0)), 0).label("stale"),
        func.coalesce(func.sum(case((col(DiscoveredContact.last_seen_at) >= cutoff, 1), else_=0)), 0).label("fresh"),
    ).select_from(DiscoveredContact).join(Company, col(Company.id) == col(DiscoveredContact.company_id))
    statement = statement.where(
        _campaign_upload_scope(campaign_id),
        col(DiscoveredContact.is_active).is_(True),
    )
    row = session.exec(statement).one()
    already_revealed = session.exec(
        select(func.count(ProspectContact.id))
        .join(Company, col(Company.id) == col(ProspectContact.company_id))
        .where(
            _campaign_upload_scope(campaign_id),
            col(ProspectContact.email).is_not(None),
        )
    ).one() or 0
    return DiscoveredContactCountsResponse(
        total=row.total or 0,
        matched=row.matched or 0,
        stale=row.stale or 0,
        fresh=row.fresh or 0,
        already_revealed=already_revealed or 0,
    )


@router.get("/discovered-contacts/companies", response_model=ContactCompanyListResponse)
def list_discovered_companies(
    campaign_id: UUID = Query(...),
    search: str | None = Query(default=None),
    title_match: bool | None = Query(default=None),
    match_gap_filter: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactCompanyListResponse:
    _campaign_or_404(session, campaign_id)
    gap_filter = _validate_match_gap_filter(match_gap_filter)
    latest_contact_attempt = (
        sa_select(
            col(DiscoveredContact.company_id).label("company_id"),
            func.max(col(DiscoveredContact.last_seen_at)).label("last_attempted_at"),
        )
        .where(col(DiscoveredContact.is_active).is_(True))
        .group_by(col(DiscoveredContact.company_id))
        .subquery()
    )
    revealed_count = (
        sa_select(
            col(ProspectContact.company_id).label("company_id"),
            func.count(col(ProspectContact.id)).label("revealed_count"),
        )
        .where(col(ProspectContact.email).is_not(None))
        .group_by(col(ProspectContact.company_id))
        .subquery()
    )
    stmt = (
        sa_select(
            col(Company.id).label("company_id"),
            col(Company.domain).label("domain"),
            func.count(col(DiscoveredContact.id)).label("total_count"),
            func.coalesce(func.sum(col(DiscoveredContact.title_match).cast(Integer)), 0).label("title_matched_count"),
            (
                func.count(col(DiscoveredContact.id))
                - func.coalesce(func.sum(col(DiscoveredContact.title_match).cast(Integer)), 0)
            ).label("unmatched_count"),
            func.greatest(
                func.coalesce(func.sum(col(DiscoveredContact.title_match).cast(Integer)), 0)
                - func.coalesce(revealed_count.c.revealed_count, 0),
                0,
            ).label("matched_no_email_count"),
            func.coalesce(revealed_count.c.revealed_count, 0).label("email_count"),
            func.coalesce(revealed_count.c.revealed_count, 0).label("fetched_count"),
            func.cast(0, Integer).label("verified_count"),
            func.cast(0, Integer).label("campaign_ready_count"),
            func.cast(0, Integer).label("eligible_verify_count"),
            latest_contact_attempt.c.last_attempted_at.label("last_contact_attempted_at"),
        )
        .select_from(Company)
        .join(DiscoveredContact, col(DiscoveredContact.company_id) == col(Company.id))
        .outerjoin(latest_contact_attempt, latest_contact_attempt.c.company_id == col(Company.id))
        .outerjoin(revealed_count, revealed_count.c.company_id == col(Company.id))
        .where(_campaign_upload_scope(campaign_id), col(DiscoveredContact.is_active).is_(True))
        .group_by(
            col(Company.id),
            col(Company.domain),
            latest_contact_attempt.c.last_attempted_at,
            revealed_count.c.revealed_count,
        )
    )
    if search:
        stmt = stmt.where(func.lower(col(Company.domain)).like(f"%{search.lower()}%"))
    if title_match is not None:
        stmt = stmt.where(col(DiscoveredContact.title_match) == title_match)
    if gap_filter == "contacts_no_match":
        stmt = stmt.having(func.coalesce(func.sum(col(DiscoveredContact.title_match).cast(Integer)), 0) == 0)
    elif gap_filter == "matched_no_email":
        stmt = stmt.having(
            func.greatest(
                func.coalesce(func.sum(col(DiscoveredContact.title_match).cast(Integer)), 0)
                - func.coalesce(revealed_count.c.revealed_count, 0),
                0,
            ) > 0
        )
    total = session.execute(sa_select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(
        stmt.order_by(text("title_matched_count DESC, total_count DESC")).offset(offset).limit(limit)
    ).all()
    return ContactCompanyListResponse(
        total=total,
        has_more=(offset + len(rows)) < total,
        limit=limit,
        offset=offset,
        items=[
            ContactCompanySummary(
                company_id=row.company_id,
                domain=row.domain,
                total_count=row.total_count,
                title_matched_count=row.title_matched_count,
                unmatched_count=row.unmatched_count,
                matched_no_email_count=row.matched_no_email_count,
                email_count=row.email_count,
                fetched_count=row.fetched_count,
                verified_count=row.verified_count,
                campaign_ready_count=row.campaign_ready_count,
                eligible_verify_count=row.eligible_verify_count,
                last_contact_attempted_at=row.last_contact_attempted_at,
            )
            for row in rows
        ],
    )


@router.post("/discovered-contacts/reveal-emails", response_model=ContactRevealResult, status_code=status.HTTP_201_CREATED)
def reveal_discovered_contact_emails(
    payload: ContactRevealRequest,
    session: Session = Depends(get_session),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> ContactRevealResult:
    _campaign_or_404(session, payload.campaign_id)
    try:
        idempotency_key = normalize_idempotency_key(x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request_payload = payload.model_dump(mode="json", exclude_none=True)
    request_payload["route"] = "discovered-contacts/reveal-emails"
    try:
        replay = check_idempotency(
            namespace="discovered-contacts-reveal",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
    except IdempotencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if replay.replayed and replay.response is not None:
        response_payload = dict(replay.response)
        response_payload["idempotency_replayed"] = True
        return ContactRevealResult(**response_payload)

    try:
        discovered_stmt = select(DiscoveredContact).join(
            Company, col(Company.id) == col(DiscoveredContact.company_id)
        ).where(
            _campaign_upload_scope(payload.campaign_id),
            col(DiscoveredContact.is_active).is_(True),
            col(DiscoveredContact.title_match).is_(True),
        )
        if payload.discovered_contact_ids:
            reveal_scope = "selected"
            discovered_stmt = discovered_stmt.where(col(DiscoveredContact.id).in_(payload.discovered_contact_ids))
        else:
            reveal_scope = "all_matched"
            company_ids = list(dict.fromkeys(payload.company_ids or []))
            if not company_ids:
                raise HTTPException(status_code=422, detail="Provide discovered_contact_ids or company_ids.")
            discovered_stmt = discovered_stmt.where(col(DiscoveredContact.company_id).in_(company_ids))

        discovered_contacts = list(session.exec(discovered_stmt))
        if not discovered_contacts:
            raise HTTPException(status_code=422, detail="No eligible discovered contacts to reveal.")

        result = ContactRevealQueueService().enqueue_reveals(
            session=session,
            campaign_id=payload.campaign_id,
            discovered_contacts=discovered_contacts,
            reveal_scope=reveal_scope,
            trigger_source="manual",
        )
        response = ContactRevealResult(
            batch_id=result.batch_id,
            selected_count=result.selected_count,
            queued_count=result.queued_count,
            already_revealing_count=result.already_revealing_count,
            skipped_revealed_count=result.skipped_revealed_count,
            message=(
                f"Queued reveal for {result.queued_count} contact group"
                f"{'' if result.queued_count == 1 else 's'}."
            ),
            idempotency_key=idempotency_key,
            idempotency_replayed=False,
        )
        store_idempotency_response(
            namespace="discovered-contacts-reveal",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        clear_idempotency_reservation(
            namespace="discovered-contacts-reveal",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
        raise
