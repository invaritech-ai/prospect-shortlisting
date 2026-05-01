"""Contact listing and title-match rule endpoints."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Response as FastAPIResponse
from sqlalchemy import case, func
from sqlmodel import Session, col, select

from app.api.schemas.contacts import (
    ContactCompanyListResponse,
    ContactCompanySummary,
    ContactCountsResponse,
    ContactIdsResult,
    ContactListResponse,
    ContactRead,
    ContactRevealRequest,
    ContactRevealResult,
    ContactRematchRequest,
    ContactRematchResult,
    ContactVerifyRequest,
    ContactVerifyResult,
    RematchResult,
    TitleMatchRuleCreate,
    TitleMatchRuleRead,
    TitleRuleSeedResult,
    TitleTestRequest,
    TitleTestResult,
    TitleRuleStatsResponse,
)
from app.core.config import settings
from app.db.session import get_session
from app.models import (
    Campaign,
    Company,
    Contact,
    TitleMatchRule,
    Upload,
)
from app.jobs.email_reveal import reveal_email as _reveal_email_task
from app.jobs.validation import verify_contacts as _verify_contacts_task
from app.services.contact_query_service import (
    apply_contact_filters as _apply_contact_filters,
    campaign_upload_scope as _campaign_upload_scope,
    contact_emails_map as _contact_emails_map,
    domain_first_letter_expr as _domain_first_letter_expr,
    parse_letters as _parse_letters,
    validate_campaign_upload_scope as _validate_campaign_upload_scope,
)
from app.services.contact_verify_service import ContactVerifyService
from app.services.email_reveal_service import EmailRevealService
from app.services.title_match_service import (
    compute_title_rule_stats,
    rematch_contacts as _rematch_contacts,
    seed_title_rules,
    test_title_match_detailed,
)

router = APIRouter(prefix="/v1", tags=["contacts"])
_email_reveal_service = EmailRevealService()
_contact_verify_service = ContactVerifyService()


def _discovered_group_key(contact: Contact) -> str:
    linkedin = (contact.linkedin_url or "").strip().lower()
    if linkedin:
        return f"linkedin:{linkedin}"
    first_name = (contact.first_name or "").strip().lower()
    last_name = (contact.last_name or "").strip().lower()
    title = (contact.title or "").strip().lower()
    if first_name and last_name and title:
        return f"name_title:{first_name}|{last_name}|{title}"
    return f"provider:{contact.source_provider}:{contact.provider_person_id}"


def _campaign_or_404(session: Session, campaign_id: UUID) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


_CONTACT_SORT_FIELDS = frozenset(
    {
        "domain",
        "created_at",
        "updated_at",
        "first_name",
        "last_name",
        "title",
        "title_match",
        "provider",
        "source_provider",
        "last_seen_at",
        "provider_has_email",
        "verification_status",
        "pipeline_stage",
    }
)

@router.get("/contacts", response_model=ContactListResponse)
def list_all_contacts(
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    stale_days: int | None = Query(default=None, ge=1, le=365),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_dir: str = Query(default="desc"),
    letters: str | None = Query(default=None),
    count_by_letters: bool = Query(default=False),
    upload_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    if not isinstance(title_match, bool):
        title_match = getattr(title_match, "default", None)
    if not isinstance(verification_status, str):
        verification_status = getattr(verification_status, "default", None)
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")
    if not isinstance(stale_days, int):
        stale_days = getattr(stale_days, "default", None)
    if not isinstance(search, str):
        search = getattr(search, "default", None)
    if not isinstance(limit, int):
        limit = int(getattr(limit, "default", 50))
    if not isinstance(offset, int):
        offset = int(getattr(offset, "default", 0))
    if not isinstance(sort_by, str):
        sort_by = getattr(sort_by, "default", "updated_at")
    if not isinstance(sort_dir, str):
        sort_dir = getattr(sort_dir, "default", "desc")
    if not isinstance(count_by_letters, bool):
        count_by_letters = bool(getattr(count_by_letters, "default", False))
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    letter_values = _parse_letters(letters)
    q = select(Contact, Company.domain).join(
        Company, col(Company.id) == col(Contact.company_id)
    )
    q = q.where(_campaign_upload_scope(campaign_id))
    q = _apply_contact_filters(
        q,
        title_match=title_match,
        verification_status=verification_status,
        search=search,
        stage_filter=stage_filter,
        stale_days=stale_days,
        letters=letter_values or None,
    )
    if upload_id is not None:
        q = q.where(col(Company.upload_id) == upload_id)

    total = session.exec(select(func.count()).select_from(q.subquery())).one()

    if sort_by not in _CONTACT_SORT_FIELDS:
        raise HTTPException(status_code=422, detail="Invalid sort_by.")
    _sb = sort_by
    _sort_dir_normalized = sort_dir.strip().lower()
    if _sort_dir_normalized not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid sort_dir.")
    _sd = _sort_dir_normalized
    _contact_sort_map = {
        "domain": col(Company.domain),
        "created_at": col(Contact.created_at),
        "updated_at": col(Contact.updated_at),
        "first_name": col(Contact.first_name),
        "last_name": col(Contact.last_name),
        "title": col(Contact.title),
        "title_match": col(Contact.title_match),
        "provider": col(Contact.source_provider),
        "source_provider": col(Contact.source_provider),
        "last_seen_at": col(Contact.last_seen_at),
        "provider_has_email": col(Contact.provider_has_email),
        "verification_status": col(Contact.verification_status),
        "pipeline_stage": col(Contact.pipeline_stage),
    }
    _sort_expr: Any = _contact_sort_map[_sb]
    _sort_expr = _sort_expr.desc() if _sd == "desc" else _sort_expr.asc()

    rows = list(
        session.exec(
            q.order_by(_sort_expr, col(Contact.created_at).desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )

    items = []
    contacts_only = [contact for contact, _domain in rows]
    email_map = _contact_emails_map(session, contacts_only)
    for contact, domain in rows:
        items.append(
            ContactRead.model_validate(
                {
                    **contact.__dict__,
                    "domain": domain,
                    "emails": email_map.get(contact.id, []),
                    "freshness_status": "fresh",
                    "group_key": _discovered_group_key(contact),
                    "last_seen_at": contact.last_seen_at,
                    "provider_has_email": contact.provider_has_email,
                    "source_provider": contact.source_provider,
                }
            )
        )

    letter_counts: dict[str, int] | None = None
    if count_by_letters:
        letter_expr = _domain_first_letter_expr()
        letter_stmt = (
            select(letter_expr.label("letter"), func.count().label("cnt"))
            .select_from(Contact)
            .join(Company, col(Company.id) == col(Contact.company_id))
            .where(letter_expr.between("a", "z"))
            .group_by(letter_expr)
        )
        letter_stmt = letter_stmt.where(_campaign_upload_scope(campaign_id))
        letter_stmt = _apply_contact_filters(
            letter_stmt,
            title_match=title_match,
            verification_status=verification_status,
            search=search,
            stage_filter=stage_filter,
            stale_days=stale_days,
        )
        if upload_id is not None:
            letter_stmt = letter_stmt.where(col(Company.upload_id) == upload_id)
        letter_counts = {chr(ord("a") + i): 0 for i in range(26)}
        for ltr, cnt in session.exec(letter_stmt).all():
            if ltr in letter_counts:
                letter_counts[ltr] = int(cnt)

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=items,
        letter_counts=letter_counts,
    )


@router.get("/contacts/counts", response_model=ContactCountsResponse)
def get_contact_counts(
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ContactCountsResponse:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.contact_discovery_freshness_days)
    stmt = (
        select(  # type: ignore[call-overload]
            func.count(col(Contact.id)).label("total"),
            func.coalesce(func.sum(case((col(Contact.title_match).is_(True), 1), else_=0)), 0).label("matched"),
            func.coalesce(
                func.sum(case((col(Contact.updated_at) <= stale_cutoff, 1), else_=0)),
                0,
            ).label("stale"),
            func.coalesce(
                func.sum(case((col(Contact.updated_at) > stale_cutoff, 1), else_=0)),
                0,
            ).label("fresh"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (col(Contact.email).is_not(None))
                            | col(Contact.pipeline_stage).in_(["email_revealed", "campaign_ready"]),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("already_revealed"),
        )
        .select_from(Contact)
        .join(Company, col(Company.id) == col(Contact.company_id))
        .where(_campaign_upload_scope(campaign_id), col(Contact.is_active).is_(True))
    )
    if upload_id is not None:
        stmt = stmt.where(col(Company.upload_id) == upload_id)

    row = session.exec(stmt).one()
    return ContactCountsResponse(
        total=int(row[0] or 0),
        matched=int(row[1] or 0),
        stale=int(row[2] or 0),
        fresh=int(row[3] or 0),
        already_revealed=int(row[4] or 0),
    )


@router.post("/contacts/rematch", response_model=ContactRematchResult)
def rematch_contacts_endpoint(
    payload: ContactRematchRequest,
    session: Session = Depends(get_session),
) -> ContactRematchResult:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    # _rematch_contacts returns int (count of updated title_match flags)
    updated = _rematch_contacts(session, campaign_id=payload.campaign_id)
    # total_count: all contacts for this campaign
    total = session.exec(
        select(func.count(col(Contact.id)))
        .join(Company, col(Company.id) == col(Contact.company_id))
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(col(Upload.campaign_id) == payload.campaign_id)
    ).one()
    return ContactRematchResult(
        campaign_id=payload.campaign_id,
        matched_count=updated,
        total_count=int(total),
    )


@router.get("/contacts/export.csv")
def export_contacts_csv(
    campaign_id: UUID = Query(...),
    include_statuses: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> FastAPIResponse:
    query = (
        select(  # type: ignore[call-overload]
            col(Company.domain),
            col(Contact.first_name),
            col(Contact.last_name),
            col(Contact.title),
            col(Contact.email),
            col(Contact.verification_status),
            col(Contact.source_provider),
            col(Contact.email_provider),
        )
        .join(Company, col(Company.id) == col(Contact.company_id))
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(
            col(Upload.campaign_id) == campaign_id,
            col(Contact.email).is_not(None),
            col(Contact.is_active).is_(True),
        )
        .order_by(col(Company.domain).asc(), col(Contact.last_name).asc())
    )
    if include_statuses:
        query = query.where(col(Contact.verification_status).in_(include_statuses))

    rows = session.exec(query).all()  # type: ignore[call-overload]

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["domain", "first_name", "last_name", "title", "email",
                     "verification_status", "source_provider", "email_provider"])
    for row in rows:
        writer.writerow(list(row))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return FastAPIResponse(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="contacts-{timestamp}.csv"'},
    )


@router.get("/contacts/companies", response_model=ContactCompanyListResponse)
def list_contacts_companies(
    campaign_id: UUID = Query(...),
    search: str | None = Query(default=None),
    title_match: bool | None = Query(default=None),
    match_gap_filter: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactCompanyListResponse:
    from sqlalchemy import case as sa_case
    from app.services.contact_query_service import (
        validate_match_gap_filter as _vmgf,
        campaign_upload_scope as _cup_scope,
    )
    _campaign_or_404(session=session, campaign_id=campaign_id)
    mgf = _vmgf(match_gap_filter)

    subq = (
        select(
            col(Contact.company_id),
            func.count(col(Contact.id)).label("total_count"),
            func.coalesce(func.sum(sa_case((col(Contact.title_match).is_(True), 1), else_=0)), 0).label("title_matched_count"),
            func.coalesce(func.sum(sa_case((col(Contact.email).is_not(None), 1), else_=0)), 0).label("email_count"),
            func.coalesce(func.sum(sa_case((col(Contact.pipeline_stage) == "fetched", 1), else_=0)), 0).label("fetched_count"),
            func.coalesce(func.sum(sa_case((col(Contact.verification_status) == "valid", 1), else_=0)), 0).label("verified_count"),
            func.coalesce(func.sum(sa_case((col(Contact.pipeline_stage) == "campaign_ready", 1), else_=0)), 0).label("campaign_ready_count"),
            func.max(col(Contact.created_at)).label("last_contact_attempted_at"),
        )
        .join(Company, col(Company.id) == col(Contact.company_id))
        .where(_cup_scope(campaign_id), col(Contact.is_active).is_(True))
        .group_by(col(Contact.company_id))
        .subquery()
    )

    stmt = (
        select(Company.id, Company.domain, subq)
        .join(subq, col(Company.id) == subq.c.company_id)
    )

    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(func.lower(col(Company.domain)).like(term))
    if title_match is not None:
        if title_match:
            stmt = stmt.where(subq.c.title_matched_count > 0)
        else:
            stmt = stmt.where(subq.c.title_matched_count == 0)
    if mgf == "contacts_no_match":
        stmt = stmt.where(subq.c.title_matched_count == 0)
    elif mgf == "matched_no_email":
        stmt = stmt.where(subq.c.title_matched_count > 0, subq.c.email_count == 0)
    elif mgf == "ready_candidates":
        stmt = stmt.where(subq.c.campaign_ready_count > 0)

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = list(session.exec(stmt.order_by(col(Company.domain)).offset(offset).limit(limit)).all())

    items = [
        ContactCompanySummary(
            company_id=row[0],
            domain=row[1],
            total_count=int(row[3]),
            title_matched_count=int(row[4]),
            unmatched_count=int(row[3]) - int(row[4]),
            matched_no_email_count=max(0, int(row[4]) - int(row[5])),
            email_count=int(row[5]),
            fetched_count=int(row[6]),
            verified_count=int(row[7]),
            campaign_ready_count=int(row[8]),
            eligible_verify_count=int(row[4]),
            last_contact_attempted_at=row[9],
        )
        for row in rows
    ]

    return ContactCompanyListResponse(
        total=int(total),
        has_more=(offset + len(items)) < int(total),
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get("/contacts/ids", response_model=ContactIdsResult)
def list_contact_ids(
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    stale_days: int | None = Query(default=None, ge=1, le=365),
    letters: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ContactIdsResult:
    from app.services.contact_query_service import (
        apply_contact_filters as _acf,
        campaign_upload_scope as _cup_scope,
        parse_letters as _parse_letters,
    )
    _campaign_or_404(session=session, campaign_id=campaign_id)
    letter_values = _parse_letters(letters)

    q = select(Contact.id).join(Company, col(Company.id) == col(Contact.company_id))
    q = q.where(_cup_scope(campaign_id))
    q = _acf(q, title_match=title_match, search=search, stale_days=stale_days, letters=letter_values or None)

    ids = list(session.exec(q).all())
    return ContactIdsResult(ids=ids, total=len(ids))


@router.post("/contacts/reveal", response_model=ContactRevealResult)
async def reveal_contacts(
    payload: ContactRevealRequest,
    session: Session = Depends(get_session),
) -> ContactRevealResult:
    _campaign_or_404(session=session, campaign_id=payload.campaign_id)

    contact_ids = list(payload.discovered_contact_ids or [])
    if not contact_ids:
        return ContactRevealResult(
            selected_count=0,
            queued_count=0,
            already_revealing_count=0,
            skipped_revealed_count=0,
            message="No contacts selected.",
        )

    batch, eligible_ids, skipped = _email_reveal_service.enqueue(
        session=session,
        campaign_id=payload.campaign_id,
        contact_ids=contact_ids,
    )
    session.commit()
    session.refresh(batch)

    defer_failed = 0
    for contact_id in eligible_ids:
        try:
            await _reveal_email_task.defer_async(contact_id=str(contact_id))
        except Exception:
            defer_failed += 1

    queued = len(eligible_ids) - defer_failed
    return ContactRevealResult(
        batch_id=batch.id,
        selected_count=len(contact_ids),
        queued_count=queued,
        already_revealing_count=0,
        skipped_revealed_count=skipped,
        message=f"Queued email reveal for {queued} contact(s). {skipped} skipped.",
    )


@router.post("/contacts/verify", response_model=ContactVerifyResult)
async def verify_contacts(
    payload: ContactVerifyRequest,
    session: Session = Depends(get_session),
) -> ContactVerifyResult:
    _campaign_or_404(session=session, campaign_id=payload.campaign_id)

    contact_ids = list(payload.contact_ids or [])

    job, skipped = _contact_verify_service.enqueue(
        session=session,
        campaign_id=payload.campaign_id,
        contact_ids=contact_ids,
    )
    session.commit()
    session.refresh(job)

    try:
        await _verify_contacts_task.defer_async(job_id=str(job.id))
    except Exception:
        pass

    queued = len(job.contact_ids_json or [])
    return ContactVerifyResult(
        job_id=job.id,
        selected_count=job.selected_count,
        message=f"Queued verification for {queued} contact(s). {skipped} skipped.",
    )


@router.get("/title-match-rules", response_model=list[TitleMatchRuleRead])
def list_title_rules(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> list[TitleMatchRuleRead]:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    rules = list(
        session.exec(
            select(TitleMatchRule)
            .where(col(TitleMatchRule.campaign_id) == campaign_id)
            .order_by(col(TitleMatchRule.rule_type), col(TitleMatchRule.created_at))
        ).all()
    )
    return [TitleMatchRuleRead.model_validate(rule, from_attributes=True) for rule in rules]


@router.post("/title-match-rules", response_model=TitleMatchRuleRead, status_code=status.HTTP_201_CREATED)
def create_title_rule(
    payload: TitleMatchRuleCreate,
    session: Session = Depends(get_session),
) -> TitleMatchRuleRead:
    _campaign_or_404(session=session, campaign_id=payload.campaign_id)
    rule = TitleMatchRule(
        campaign_id=payload.campaign_id,
        rule_type=payload.rule_type,
        keywords=payload.keywords,
        match_type=payload.match_type,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    _rematch_contacts(session, campaign_id=payload.campaign_id)
    return TitleMatchRuleRead.model_validate(rule, from_attributes=True)


@router.delete("/title-match-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_title_rule(
    rule_id: UUID,
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> None:
    rule = session.get(TitleMatchRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    if rule.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="rule_id is not assigned to the selected campaign.")
    session.delete(rule)
    session.commit()
    _rematch_contacts(session, campaign_id=campaign_id)


@router.post("/title-match-rules/rematch", response_model=RematchResult)
def rematch_contacts(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> RematchResult:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    updated = _rematch_contacts(session, campaign_id=campaign_id)
    return RematchResult(
        updated=updated,
        fetch_jobs_queued=0,
        message=(
            f"Re-evaluated discovered contacts for this campaign; {updated} title_match flags changed."
        ),
    )


@router.post("/title-match-rules/seed", response_model=TitleRuleSeedResult)
def seed_rules(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> TitleRuleSeedResult:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    inserted = seed_title_rules(session, campaign_id=campaign_id)
    return TitleRuleSeedResult(
        inserted=inserted,
        message=f"Inserted {inserted} new rules (duplicates skipped).",
    )


@router.post("/title-match-rules/test", response_model=TitleTestResult)
def run_title_test(
    payload: TitleTestRequest,
    session: Session = Depends(get_session),
) -> TitleTestResult:
    _campaign_or_404(session=session, campaign_id=payload.campaign_id)
    result = test_title_match_detailed(payload.title, session, campaign_id=payload.campaign_id)
    return TitleTestResult.model_validate(result)


@router.get("/title-match-rules/stats", response_model=TitleRuleStatsResponse)
def get_title_rule_stats(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> TitleRuleStatsResponse:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    result = compute_title_rule_stats(session, campaign_id=campaign_id)
    return TitleRuleStatsResponse.model_validate(result)
