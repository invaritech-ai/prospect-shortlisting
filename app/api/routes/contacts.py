"""Contact listing and title-match rule endpoints."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Response as FastAPIResponse
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.contacts import (
    ContactFetchQueued,
    ContactFetchRequest,
    ContactListResponse,
    ContactRead,
    ContactRematchRequest,
    ContactRematchResult,
    ContactRevealQueued,
    ContactRevealRequest,
    ContactVerifyQueued,
    ContactVerifyRequest,
    RematchResult,
    TitleMatchRuleCreate,
    TitleMatchRuleRead,
    TitleRuleSeedResult,
    TitleTestRequest,
    TitleTestResult,
    TitleRuleStatsResponse,
)
from app.db.session import get_session
from app.models import (
    Campaign,
    Company,
    Contact,
    ContactVerifyJob,
    TitleMatchRule,
    Upload,
)
from app.services.contact_query_service import (
    apply_contact_filters as _apply_contact_filters,
    campaign_upload_scope as _campaign_upload_scope,
    contact_emails_map as _contact_emails_map,
    domain_first_letter_expr as _domain_first_letter_expr,
    parse_letters as _parse_letters,
    validate_campaign_upload_scope as _validate_campaign_upload_scope,
)
from app.services.contact_queue_service import ContactQueueService
from app.services.contact_reveal_queue_service import ContactRevealQueueService
from app.services.contact_verify_service import is_contact_verification_eligible
from app.services.title_match_service import (
    compute_title_rule_stats,
    rematch_contacts as _rematch_contacts,
    seed_title_rules,
    test_title_match_detailed,
)
from app.tasks.contacts import verify_contacts_batch

router = APIRouter(prefix="/v1", tags=["contacts"])


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
        "provider": col(Contact.provider),
        "last_seen_at": col(Contact.last_seen_at),
        "provider_has_email": col(Contact.provider_has_email),
        "verification_status": col(Contact.verification_status),
        "pipeline_stage": col(Contact.pipeline_stage),
    }
    _sort_expr = _contact_sort_map[_sb]
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
                    "last_seen_at": contact.last_seen_at,
                    "provider_has_email": contact.provider_has_email,
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


@router.post("/contacts/fetch", response_model=ContactFetchQueued, status_code=202)
def fetch_contacts_endpoint(
    payload: ContactFetchRequest,
    session: Session = Depends(get_session),
) -> ContactFetchQueued:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    query = (
        select(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(
            col(Upload.campaign_id) == payload.campaign_id,
            col(Company.pipeline_stage) == "contact_ready",
        )
    )
    if payload.company_ids:
        query = query.where(col(Company.id).in_(payload.company_ids))

    companies = list(session.exec(query).all())
    if not companies:
        raise HTTPException(status_code=422, detail="No contact_ready companies found for this campaign.")

    queue_service = ContactQueueService()
    result = queue_service.enqueue_fetches(
        session=session,
        companies=companies,
        provider_mode="both",
        campaign_id=payload.campaign_id,
        trigger_source="manual",
    )
    # Adapter: ContactEnqueueResult uses queued_job_ids, not job_ids
    return ContactFetchQueued(
        queued_count=result.queued_count,
        job_ids=result.queued_job_ids,
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
        select(func.count(Contact.id))
        .join(Company, col(Company.id) == col(Contact.company_id))
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(col(Upload.campaign_id) == payload.campaign_id)
    ).one()
    return ContactRematchResult(
        campaign_id=payload.campaign_id,
        matched_count=updated,
        total_count=int(total),
    )


@router.post("/contacts/reveal", response_model=ContactRevealQueued, status_code=202)
def reveal_contacts_endpoint(
    payload: ContactRevealRequest,
    session: Session = Depends(get_session),
) -> ContactRevealQueued:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    # Fetch title-matched contacts that have not yet been revealed
    contacts_to_reveal = list(
        session.exec(
            select(Contact)
            .join(Company, col(Company.id) == col(Contact.company_id))
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == payload.campaign_id,
                col(Contact.title_match).is_(True),
                col(Contact.is_active).is_(True),
                col(Contact.email).is_(None),
            )
        ).all()
    )
    if not contacts_to_reveal:
        raise HTTPException(status_code=422, detail="No revealable contacts found for this campaign.")

    reveal_service = ContactRevealQueueService()
    result = reveal_service.enqueue_reveals(
        session=session,
        campaign_id=payload.campaign_id,
        discovered_contacts=contacts_to_reveal,
        reveal_scope="campaign",
        trigger_source="manual",
    )
    if result.batch_id is None:
        raise HTTPException(status_code=422, detail="Reveal is disabled or paused.")
    # Adapter: ContactRevealEnqueueResult uses queued_job_ids; response schema uses job_id (batch)
    return ContactRevealQueued(
        queued_count=result.queued_count,
        job_id=result.batch_id,
    )


@router.post("/contacts/verify", response_model=ContactVerifyQueued, status_code=202)
def verify_contacts_endpoint(
    payload: ContactVerifyRequest,
    session: Session = Depends(get_session),
) -> ContactVerifyQueued:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    eligible_contacts = list(
        session.exec(
            select(Contact)
            .join(Company, col(Company.id) == col(Contact.company_id))
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == payload.campaign_id,
                col(Contact.title_match).is_(True),
                col(Contact.is_active).is_(True),
                col(Contact.verification_status) == "unverified",
                col(Contact.email).is_not(None),
            )
        ).all()
    )
    eligible_contacts = [c for c in eligible_contacts if is_contact_verification_eligible(c)]
    if not eligible_contacts:
        raise HTTPException(status_code=422, detail="No verification-eligible contacts found for this campaign.")

    job = ContactVerifyJob(
        contact_ids_json=[str(c.id) for c in eligible_contacts],
        selected_count=len(eligible_contacts),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    verify_contacts_batch.delay(str(job.id))

    return ContactVerifyQueued(
        queued_count=len(eligible_contacts),
        job_id=job.id,
    )


@router.get("/contacts/export.csv")
def export_contacts_csv(
    campaign_id: UUID = Query(...),
    include_statuses: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> FastAPIResponse:
    query = (
        select(
            col(Company.domain),
            col(Contact.first_name),
            col(Contact.last_name),
            col(Contact.title),
            col(Contact.email),
            col(Contact.verification_status),
            col(Contact.provider),
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
                     "verification_status", "fetch_provider", "email_provider"])
    for row in rows:
        writer.writerow(list(row))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return FastAPIResponse(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="contacts-{timestamp}.csv"'},
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
