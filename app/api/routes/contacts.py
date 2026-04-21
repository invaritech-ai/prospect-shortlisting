"""Contact fetching, verification, listing, and title-match rule endpoints."""
from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import Integer, and_, case, func, or_, select as sa_select, text
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.api.schemas.contacts import (
    BulkContactFetchRequest,
    ContactCompanyListResponse,
    ContactCompanySummary,
    ContactCountsResponse,
    ContactFetchResult,
    ContactListResponse,
    ContactVerifyRequest,
    ContactVerifyResult,
    MatchGapFilter,
    ProspectContactRead,
    RematchResult,
    TitleRuleImpactPreview,
    TitleMatchRuleCreate,
    TitleMatchRuleRead,
    TitleRuleSeedResult,
    TitleTestRequest,
    TitleTestResult,
    TitleRuleStatItem,
    TitleRuleStatsResponse,
)
from app.db.session import get_session
from app.models import (
    AnalysisJob,
    Campaign,
    ClassificationResult,
    Company,
    ContactFetchJob,
    ContactVerifyJob,
    ProspectContact,
    ProspectContactEmail,
    Run,
    TitleMatchRule,
    Upload,
)
from app.models.pipeline import (
    AnalysisJobState,
    CompanyPipelineStage,
    ContactVerifyJobState,
    PredictedLabel,
    utcnow,
)
from app.services.contact_service import (
    compute_title_rule_stats,
    rematch_existing_contacts,
    seed_title_rules,
    test_title_match_detailed,
)
from app.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyUnavailableError,
    check_idempotency,
    clear_idempotency_reservation,
    normalize_idempotency_key,
    store_idempotency_response,
)
from app.tasks.contacts import fetch_contacts, fetch_contacts_apollo, verify_contacts_batch

router = APIRouter(prefix="/v1", tags=["contacts"])

_ALLOWED_CONTACT_STAGE_FILTERS = frozenset({"all", "fetched", "verified", "campaign_ready"})
_ALLOWED_MATCH_GAP_FILTERS = frozenset({"all", "contacts_no_match", "matched_no_email", "ready_candidates"})
_IMPACT_SOURCE_VALUES = frozenset({"snov", "apollo", "both"})
_IMPACT_PROVIDER_STALE_DEFAULT_DAYS: dict[str, int] = {"snov": 30, "apollo": 45}


def _validate_contact_stage_filter(stage_filter: str) -> str:
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")
    normalized = (stage_filter or "all").strip().lower()
    if normalized not in _ALLOWED_CONTACT_STAGE_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid stage_filter.")
    return normalized


def _validate_match_gap_filter(value: str) -> MatchGapFilter:
    if not isinstance(value, str):
        value = getattr(value, "default", "all")
    normalized = (value or "all").strip().lower()
    if normalized not in _ALLOWED_MATCH_GAP_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid match_gap_filter.")
    return normalized  # type: ignore[return-value]


def _validate_campaign_upload_scope(
    *,
    session: Session,
    campaign_id: UUID,
    upload_id: UUID | None,
) -> None:
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    if upload_id is None:
        return
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="upload_id is not assigned to the selected campaign.")


def _campaign_upload_scope(campaign_id: UUID):
    return col(Company.upload_id).in_(select(Upload.id).where(col(Upload.campaign_id) == campaign_id))


def _contact_emails_map(session: Session, contacts: list[ProspectContact]) -> dict[UUID, list[str]]:
    contact_ids = [contact.id for contact in contacts if contact.id]
    if not contact_ids:
        return {}
    rows = list(
        session.exec(
            select(
                ProspectContactEmail.contact_id,
                ProspectContactEmail.email,
                ProspectContactEmail.is_primary,
                ProspectContactEmail.updated_at,
            )
            .where(col(ProspectContactEmail.contact_id).in_(contact_ids))
            .order_by(
                col(ProspectContactEmail.contact_id),
                col(ProspectContactEmail.is_primary).desc(),
                col(ProspectContactEmail.updated_at).desc(),
            )
        )
    )
    out: dict[UUID, list[str]] = {contact.id: [] for contact in contacts if contact.id}
    seen_norm: dict[UUID, set[str]] = {contact.id: set() for contact in contacts if contact.id}
    for contact_id, email, _is_primary, _updated_at in rows:
        if not email:
            continue
        bucket = out.setdefault(contact_id, [])
        norm = email.strip().lower()
        if norm and norm not in seen_norm.setdefault(contact_id, set()):
            bucket.append(email)
            seen_norm[contact_id].add(norm)
    for contact in contacts:
        if not contact.id:
            continue
        if contact.email:
            norm = contact.email.strip().lower()
            if norm and norm not in seen_norm.setdefault(contact.id, set()):
                out.setdefault(contact.id, []).insert(0, contact.email)
                seen_norm[contact.id].add(norm)
    return out


def _verification_eligible_condition():
    return (
        col(ProspectContact.title_match).is_(True),
        col(ProspectContact.email).is_not(None),
        col(ProspectContact.verification_status) == "unverified",
    )


def _apply_contact_filters(
    stmt,
    *,
    title_match: bool | None = None,
    verification_status: str | None = None,
    search: str | None = None,
    stage_filter: str = "all",
    stale_days: int | None = None,
    company_id: UUID | None = None,
    company_ids: list[UUID] | None = None,
    letters: list[str] | None = None,
):
    if not isinstance(verification_status, str):
        verification_status = getattr(verification_status, "default", None)
    if not isinstance(search, str):
        search = getattr(search, "default", None)
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")
    if not isinstance(stale_days, int):
        stale_days = getattr(stale_days, "default", None)
    normalized_stage = _validate_contact_stage_filter(stage_filter)
    if company_id:
        stmt = stmt.where(col(ProspectContact.company_id) == company_id)
    if company_ids:
        stmt = stmt.where(col(ProspectContact.company_id).in_(company_ids))
    if title_match is not None:
        stmt = stmt.where(col(ProspectContact.title_match) == title_match)
    if verification_status:
        stmt = stmt.where(col(ProspectContact.verification_status) == verification_status.strip().lower())
    if normalized_stage != "all":
        stmt = stmt.where(col(ProspectContact.pipeline_stage) == normalized_stage)
    if stale_days is not None and stale_days > 0:
        cutoff = utcnow() - timedelta(days=stale_days)
        stmt = stmt.where(
            col(ProspectContact.verification_status) != "unverified",
            col(ProspectContact.pipeline_stage).in_(["verified", "campaign_ready"]),
            col(ProspectContact.updated_at) <= cutoff,
        )
    if letters:
        stmt = stmt.where(_domain_first_letter_expr().in_(letters))
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(ProspectContact.first_name).like(term),
                func.lower(ProspectContact.last_name).like(term),
                func.lower(ProspectContact.email).like(term),
                func.lower(ProspectContact.title).like(term),
                func.lower(Company.domain).like(term),
            )
        )
    return stmt


def _select_verification_contact_ids(session: Session, payload: ContactVerifyRequest) -> list[UUID]:
    explicit_ids = list(dict.fromkeys(payload.contact_ids or []))
    campaign_scope = _campaign_upload_scope(payload.campaign_id)
    if explicit_ids:
        rows = list(
            session.exec(
                select(ProspectContact.id)
                .join(Company, col(Company.id) == col(ProspectContact.company_id))
                .where(
                    col(ProspectContact.id).in_(explicit_ids),
                    campaign_scope,
                    *_verification_eligible_condition(),
                )
            )
        )
        return rows

    company_ids = list(dict.fromkeys(payload.company_ids or []))
    stmt = select(ProspectContact.id).join(Company, col(Company.id) == col(ProspectContact.company_id))
    stmt = _apply_contact_filters(
        stmt,
        title_match=payload.title_match,
        verification_status=payload.verification_status,
        search=payload.search,
        stage_filter=payload.stage_filter or "all",
        company_ids=company_ids or None,
    )
    stmt = stmt.where(campaign_scope, *_verification_eligible_condition())
    return list(session.exec(stmt))


def _enqueue_contact_fetches(
    *,
    session: Session,
    companies: list[Company],
    provider: str = "snov",
    next_provider: str | None = None,
) -> ContactFetchResult:
    if not companies:
        return ContactFetchResult(
            requested_count=0,
            queued_count=0,
            already_fetching_count=0,
            queued_job_ids=[],
        )

    company_ids = [c.id for c in companies]
    # Lock target companies while deciding queue actions so concurrent requests
    # do not double-enqueue the same provider chain on databases that support it.
    session.exec(
        select(Company.id).where(col(Company.id).in_(company_ids)).with_for_update()
    ).all()
    active_jobs = list(
        session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.company_id).in_(company_ids),
                col(ContactFetchJob.terminal_state).is_(False),
                ContactFetchJob.provider == provider,
            )
        )
    )
    stale_active_company_ids: set[UUID] = set()
    active_company_ids: set[UUID] = set()
    active_updated = False
    normalized_next_provider = (next_provider or "").strip().lower() or None
    for active_job in active_jobs:
        session.refresh(active_job)
        company_id = active_job.company_id
        if not company_id:
            continue
        if active_job.terminal_state:
            stale_active_company_ids.add(company_id)
            continue
        active_company_ids.add(company_id)
        if normalized_next_provider and normalized_next_provider in {"snov", "apollo"}:
            current_next = (active_job.next_provider or "").strip().lower() or None
            if current_next != normalized_next_provider:
                update_result = session.execute(
                    sa_update(ContactFetchJob)
                    .where(
                        col(ContactFetchJob.id) == active_job.id,
                        col(ContactFetchJob.terminal_state).is_(False),
                    )
                    .values(next_provider=normalized_next_provider)
                )
                if update_result.rowcount and update_result.rowcount > 0:
                    active_updated = True
                else:
                    active_company_ids.discard(company_id)
                    stale_active_company_ids.add(company_id)

    jobs_to_create: list[ContactFetchJob] = []
    for company in companies:
        if company.id in active_company_ids:
            continue
        if company.id in stale_active_company_ids:
            continue
        jobs_to_create.append(
            ContactFetchJob(
                company_id=company.id,
                provider=provider,
                next_provider=normalized_next_provider,
            )
        )

    if jobs_to_create or active_updated:
        session.add_all(jobs_to_create)
        session.commit()

    queued_job_ids: list[UUID] = []
    task = fetch_contacts_apollo if provider == "apollo" else fetch_contacts
    for job in jobs_to_create:
        if job.id:
            task.delay(str(job.id))
            queued_job_ids.append(job.id)

    followup_already_fetching = 0
    if stale_active_company_ids and normalized_next_provider:
        followup_companies = [company for company in companies if company.id in stale_active_company_ids]
        followup_result = _enqueue_contact_fetches(
            session=session,
            companies=followup_companies,
            provider=normalized_next_provider,
        )
        followup_already_fetching = followup_result.already_fetching_count
        queued_job_ids.extend(followup_result.queued_job_ids)

    return ContactFetchResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        already_fetching_count=len(active_company_ids) + followup_already_fetching,
        queued_job_ids=queued_job_ids,
    )


def _campaign_or_404(session: Session, campaign_id: UUID) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


def _normalize_impact_source(source: str | None) -> Literal["snov", "apollo", "both"]:
    if not isinstance(source, str):
        source = getattr(source, "default", "snov")
    normalized = source.strip().lower() if source else "snov"
    if normalized not in _IMPACT_SOURCE_VALUES:
        raise HTTPException(status_code=422, detail="Invalid source.")
    return normalized  # type: ignore[return-value]


def _build_stale_condition(
    *,
    source: Literal["snov", "apollo", "both"],
    stale_days: int | None,
):
    source_expr = func.lower(func.coalesce(col(ProspectContact.source), ""))
    if stale_days is not None:
        stale_cutoff = utcnow() - timedelta(days=stale_days)
        stale_base = and_(
            col(ProspectContact.title_match).is_(True),
            col(ProspectContact.email).is_not(None),
            col(ProspectContact.updated_at) <= stale_cutoff,
        )
        if source == "both":
            return stale_base
        return and_(stale_base, source_expr == source)

    snov_cutoff = utcnow() - timedelta(days=_IMPACT_PROVIDER_STALE_DEFAULT_DAYS["snov"])
    apollo_cutoff = utcnow() - timedelta(days=_IMPACT_PROVIDER_STALE_DEFAULT_DAYS["apollo"])
    snov_stale = and_(
        source_expr == "snov",
        col(ProspectContact.updated_at) <= snov_cutoff,
    )
    apollo_stale = and_(
        source_expr == "apollo",
        col(ProspectContact.updated_at) <= apollo_cutoff,
    )
    fallback_stale = and_(
        source_expr.notin_(["snov", "apollo"]),
        col(ProspectContact.updated_at) <= snov_cutoff,
    )
    stale_by_source = (
        snov_stale
        if source == "snov"
        else apollo_stale
        if source == "apollo"
        else or_(snov_stale, apollo_stale, fallback_stale)
    )
    return and_(
        col(ProspectContact.title_match).is_(True),
        col(ProspectContact.email).is_not(None),
        stale_by_source,
    )


def _title_rule_impact_targets(
    *,
    session: Session,
    campaign_id: UUID,
    source: Literal["snov", "apollo", "both"] = "snov",
    include_stale: bool = False,
    stale_days: int | None = None,
    force_refresh: bool = False,
) -> tuple[list[Company], int, int]:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    scope = _campaign_upload_scope(campaign_id)
    stale_condition = _build_stale_condition(
        source=source,
        stale_days=stale_days,
    )
    if force_refresh:
        target_condition = col(ProspectContact.title_match).is_(True)
    elif include_stale:
        target_condition = or_(
            col(ProspectContact.email).is_(None),
            stale_condition,
        )
    else:
        target_condition = col(ProspectContact.email).is_(None)
    impacted_contacts_stmt = (
        select(func.count(ProspectContact.id))
        .join(Company, col(Company.id) == col(ProspectContact.company_id))
        .where(
            scope,
            col(ProspectContact.title_match).is_(True),
            target_condition,
        )
    )
    impacted_contact_count = session.exec(impacted_contacts_stmt).one() or 0
    stale_contact_count_stmt = (
        select(func.count(ProspectContact.id))
        .join(Company, col(Company.id) == col(ProspectContact.company_id))
        .where(
            scope,
            stale_condition,
        )
    )
    stale_contact_count = session.exec(stale_contact_count_stmt).one() or 0
    impacted_company_ids = list(
        session.exec(
            select(ProspectContact.company_id)
            .join(Company, col(Company.id) == col(ProspectContact.company_id))
            .where(
                scope,
                col(ProspectContact.title_match).is_(True),
                target_condition,
            )
            .group_by(ProspectContact.company_id)
        )
    )
    companies = (
        list(
            session.exec(
                select(Company)
                .where(col(Company.id).in_(impacted_company_ids))
                .order_by(col(Company.domain).asc())
            )
        )
        if impacted_company_ids
        else []
    )
    return companies, int(impacted_contact_count), int(stale_contact_count)


@router.post(
    "/companies/{company_id}/fetch-contacts",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_contacts_for_company(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    upload = session.get(Upload, company.upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="company_id is not assigned to the selected campaign.")
    return _enqueue_contact_fetches(session=session, companies=[company], provider="snov")


@router.post(
    "/companies/{company_id}/fetch-contacts/apollo",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_apollo_contacts_for_company(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    upload = session.get(Upload, company.upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="company_id is not assigned to the selected campaign.")
    return _enqueue_contact_fetches(session=session, companies=[company], provider="apollo")


@router.post(
    "/runs/{run_id}/fetch-contacts",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_contacts_for_run(
    run_id: UUID,
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    upload = session.get(Upload, run.upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="run_id is not assigned to the selected campaign.")

    companies = list(
        session.exec(
            select(Company)
            .join(AnalysisJob, col(AnalysisJob.company_id) == col(Company.id))
            .join(ClassificationResult, col(ClassificationResult.analysis_job_id) == col(AnalysisJob.id))
            .where(
                col(AnalysisJob.run_id) == run_id,
                col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED,
                col(ClassificationResult.predicted_label) == PredictedLabel.POSSIBLE,
                col(Company.pipeline_stage) == CompanyPipelineStage.CONTACT_READY,
            )
        ).all()
    )
    return _enqueue_contact_fetches(session=session, companies=companies, provider="snov")


@router.post(
    "/runs/{run_id}/fetch-contacts/apollo",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_apollo_contacts_for_run(
    run_id: UUID,
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    upload = session.get(Upload, run.upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="run_id is not assigned to the selected campaign.")

    companies = list(
        session.exec(
            select(Company)
            .join(AnalysisJob, col(AnalysisJob.company_id) == col(Company.id))
            .join(ClassificationResult, col(ClassificationResult.analysis_job_id) == col(AnalysisJob.id))
            .where(
                col(AnalysisJob.run_id) == run_id,
                col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED,
                col(ClassificationResult.predicted_label) == PredictedLabel.POSSIBLE,
                col(Company.pipeline_stage) == CompanyPipelineStage.CONTACT_READY,
            )
        ).all()
    )
    return _enqueue_contact_fetches(session=session, companies=companies, provider="apollo")


@router.post(
    "/companies/fetch-contacts-selected",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_contacts_selected(
    payload: BulkContactFetchRequest,
    session: Session = Depends(get_session),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> ContactFetchResult:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    try:
        idempotency_key = normalize_idempotency_key(x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request_payload = payload.model_dump(mode="json", exclude_none=True)
    request_payload["route"] = "companies/fetch-contacts-selected"
    try:
        replay = check_idempotency(
            namespace="contacts-fetch-selected",
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
        return ContactFetchResult(**response_payload)

    try:
        requested_ids = list(dict.fromkeys(payload.company_ids))
        companies = list(
            session.exec(
                select(Company)
                .join(Upload, col(Upload.id) == col(Company.upload_id))
                .where(
                    col(Company.id).in_(requested_ids),
                    col(Upload.campaign_id) == payload.campaign_id,
                )
            )
        )
        if not companies:
            raise HTTPException(status_code=404, detail="No matching companies found.")

        if payload.source == "both":
            r = _enqueue_contact_fetches(
                session=session,
                companies=companies,
                provider="snov",
                next_provider="apollo",
            )
            total_queued = r.queued_count
            total_already_fetching = r.already_fetching_count
            all_job_ids = list(r.queued_job_ids)
        else:
            r = _enqueue_contact_fetches(session=session, companies=companies, provider=payload.source)
            total_queued = r.queued_count
            total_already_fetching = r.already_fetching_count
            all_job_ids = list(r.queued_job_ids)

        result = ContactFetchResult(
            requested_count=len(companies),
            queued_count=total_queued,
            already_fetching_count=total_already_fetching,
            queued_job_ids=all_job_ids,
            idempotency_key=idempotency_key,
            idempotency_replayed=False,
        )
        store_idempotency_response(
            namespace="contacts-fetch-selected",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        clear_idempotency_reservation(
            namespace="contacts-fetch-selected",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
        raise


@router.get("/companies/{company_id}/contacts", response_model=ContactListResponse)
def list_company_contacts(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    if not isinstance(title_match, bool):
        title_match = getattr(title_match, "default", None)
    if not isinstance(verification_status, str):
        verification_status = getattr(verification_status, "default", None)
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")
    if not isinstance(limit, int):
        limit = int(getattr(limit, "default", 50))
    if not isinstance(offset, int):
        offset = int(getattr(offset, "default", 0))

    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    upload = session.get(Upload, company.upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="company_id is not assigned to the selected campaign.")

    q = select(ProspectContact).join(Company, col(Company.id) == col(ProspectContact.company_id))
    q = _apply_contact_filters(
        q,
        title_match=title_match,
        verification_status=verification_status,
        stage_filter=stage_filter,
        company_id=company_id,
    )
    total = session.exec(select(func.count()).select_from(q.subquery())).one()
    items = list(
        session.exec(
            q.order_by(
                col(ProspectContact.pipeline_stage).desc(),
                col(ProspectContact.title_match).desc(),
                col(ProspectContact.created_at).desc(),
            ).offset(offset).limit(limit)
        ).all()
    )
    email_map = _contact_emails_map(session, items)

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=[
            ProspectContactRead.model_validate(
                {**c.__dict__, "domain": company.domain, "emails": email_map.get(c.id, [])}
            )
            for c in items
        ],
    )


@router.get("/contacts/companies", response_model=ContactCompanyListResponse)
def list_contacts_by_company(
    campaign_id: UUID = Query(...),
    search: str | None = Query(default=None),
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    match_gap_filter: str = Query(default="all"),
    upload_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactCompanyListResponse:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    if not isinstance(search, str):
        search = getattr(search, "default", None)
    if not isinstance(verification_status, str):
        verification_status = getattr(verification_status, "default", None)
    if not isinstance(title_match, bool):
        title_match = getattr(title_match, "default", None)
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)
    if not isinstance(limit, int):
        limit = int(getattr(limit, "default", 50))
    if not isinstance(offset, int):
        offset = int(getattr(offset, "default", 0))

    normalized_stage = _validate_contact_stage_filter(stage_filter)
    normalized_gap = _validate_match_gap_filter(match_gap_filter)
    latest_contact_attempt = (
        sa_select(
            col(ContactFetchJob.company_id).label("company_id"),
            func.max(func.coalesce(col(ContactFetchJob.updated_at), col(ContactFetchJob.created_at))).label("last_attempted_at"),
        )
        .group_by(col(ContactFetchJob.company_id))
        .subquery()
    )
    stmt = (
        sa_select(
            col(Company.id).label("company_id"),
            col(Company.domain).label("domain"),
            func.count(col(ProspectContact.id)).label("total_count"),
            func.coalesce(func.sum(col(ProspectContact.title_match).cast(Integer)), 0).label("title_matched_count"),
            (
                func.count(col(ProspectContact.id))
                - func.coalesce(func.sum(col(ProspectContact.title_match).cast(Integer)), 0)
            ).label("unmatched_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            col(ProspectContact.title_match).is_(True)
                            & col(ProspectContact.email).is_(None),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("matched_no_email_count"),
            func.count(col(ProspectContact.email)).label("email_count"),
            func.coalesce(func.sum(case((col(ProspectContact.pipeline_stage) == "fetched", 1), else_=0)), 0).label("fetched_count"),
            func.coalesce(func.sum(case((col(ProspectContact.pipeline_stage) == "verified", 1), else_=0)), 0).label("verified_count"),
            func.coalesce(func.sum(case((col(ProspectContact.pipeline_stage) == "campaign_ready", 1), else_=0)), 0).label("campaign_ready_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            col(ProspectContact.title_match).is_(True)
                            & col(ProspectContact.email).is_not(None)
                            & (col(ProspectContact.verification_status) == "unverified"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("eligible_verify_count"),
            latest_contact_attempt.c.last_attempted_at.label("last_contact_attempted_at"),
        )
        .select_from(Company)
        .join(ProspectContact, col(ProspectContact.company_id) == col(Company.id))
        .outerjoin(latest_contact_attempt, latest_contact_attempt.c.company_id == col(Company.id))
        .group_by(col(Company.id), col(Company.domain), latest_contact_attempt.c.last_attempted_at)
    )
    stmt = stmt.where(_campaign_upload_scope(campaign_id))
    if upload_id is not None:
        stmt = stmt.where(col(Company.upload_id) == upload_id)
    if search:
        stmt = stmt.where(func.lower(col(Company.domain)).like(f"%{search.lower()}%"))
    if title_match is not None:
        stmt = stmt.where(col(ProspectContact.title_match) == title_match)
    if verification_status:
        stmt = stmt.where(col(ProspectContact.verification_status) == verification_status.strip().lower())
    if normalized_stage != "all":
        stmt = stmt.where(col(ProspectContact.pipeline_stage) == normalized_stage)
    if normalized_gap == "contacts_no_match":
        stmt = stmt.having(func.coalesce(func.sum(col(ProspectContact.title_match).cast(Integer)), 0) == 0)
    elif normalized_gap == "matched_no_email":
        stmt = stmt.having(
            func.coalesce(
                func.sum(
                    case(
                        (
                            col(ProspectContact.title_match).is_(True)
                            & col(ProspectContact.email).is_(None),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ) > 0
        )
    elif normalized_gap == "ready_candidates":
        stmt = stmt.having(
            func.coalesce(func.sum(case((col(ProspectContact.pipeline_stage) == "campaign_ready", 1), else_=0)), 0) > 0
        )

    total = session.execute(sa_select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(
        stmt.order_by(text("campaign_ready_count DESC, verified_count DESC, total_count DESC")).offset(offset).limit(limit)
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


_CONTACT_SORT_FIELDS = frozenset(
    {
        "domain",
        "created_at",
        "updated_at",
        "first_name",
        "last_name",
        "title",
        "verification_status",
        "pipeline_stage",
    }
)


def _domain_first_letter_expr():
    return func.lower(func.substr(Company.domain, 1, 1))


def _parse_letters(letters: str | None) -> list[str]:
    if not isinstance(letters, str):
        letters = getattr(letters, "default", None)
    if not letters:
        return []
    normalized = sorted({part.strip().lower() for part in letters.split(",") if part.strip()})
    return [ltr for ltr in normalized if len(ltr) == 1 and "a" <= ltr <= "z"]


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
    q = select(ProspectContact, Company.domain).join(
        Company, col(Company.id) == col(ProspectContact.company_id)
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
        "created_at": col(ProspectContact.created_at),
        "updated_at": col(ProspectContact.updated_at),
        "first_name": col(ProspectContact.first_name),
        "last_name": col(ProspectContact.last_name),
        "title": col(ProspectContact.title),
        "verification_status": col(ProspectContact.verification_status),
        "pipeline_stage": col(ProspectContact.pipeline_stage),
    }
    _sort_expr = _contact_sort_map[_sb]
    _sort_expr = _sort_expr.desc() if _sd == "desc" else _sort_expr.asc()

    rows = list(
        session.exec(
            q.order_by(_sort_expr, col(ProspectContact.created_at).desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )

    items = []
    contacts_only = [contact for contact, _domain in rows]
    email_map = _contact_emails_map(session, contacts_only)
    for contact, domain in rows:
        items.append(
            ProspectContactRead.model_validate(
                {**contact.__dict__, "domain": domain, "emails": email_map.get(contact.id, [])}
            )
        )

    letter_counts: dict[str, int] | None = None
    if count_by_letters:
        letter_expr = _domain_first_letter_expr()
        letter_stmt = (
            select(letter_expr.label("letter"), func.count().label("cnt"))
            .select_from(ProspectContact)
            .join(Company, col(Company.id) == col(ProspectContact.company_id))
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
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
) -> ContactCountsResponse:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)
    statement = select(
        func.count().label("total"),
        func.coalesce(func.sum(case((col(ProspectContact.pipeline_stage) == "fetched", 1), else_=0)), 0).label("fetched"),
        func.coalesce(func.sum(case((col(ProspectContact.pipeline_stage) == "verified", 1), else_=0)), 0).label("verified"),
        func.coalesce(func.sum(case((col(ProspectContact.pipeline_stage) == "campaign_ready", 1), else_=0)), 0).label("campaign_ready"),
        func.coalesce(
            func.sum(
                case(
                    (
                        col(ProspectContact.title_match).is_(True)
                        & col(ProspectContact.email).is_not(None)
                        & (col(ProspectContact.verification_status) == "unverified"),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("eligible_verify"),
    ).select_from(ProspectContact).join(Company, col(Company.id) == col(ProspectContact.company_id))
    statement = statement.where(_campaign_upload_scope(campaign_id))
    if upload_id is not None:
        statement = statement.where(col(Company.upload_id) == upload_id)
    row = session.exec(
        statement
    ).one()

    return ContactCountsResponse(
        total=row.total or 0,
        fetched=row.fetched or 0,
        verified=row.verified or 0,
        campaign_ready=row.campaign_ready or 0,
        eligible_verify=row.eligible_verify or 0,
    )


@router.get("/contacts/export.csv")
def export_contacts_csv(
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    company_id: UUID | None = Query(default=None),
    upload_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
) -> Response:
    _campaign_or_404(session=session, campaign_id=campaign_id)
    if not isinstance(title_match, bool):
        title_match = getattr(title_match, "default", None)
    if not isinstance(verification_status, str):
        verification_status = getattr(verification_status, "default", None)
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")
    if not isinstance(company_id, UUID):
        company_id = getattr(company_id, "default", None)
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)
    q = select(ProspectContact, Company.domain).join(
        Company, col(Company.id) == col(ProspectContact.company_id)
    )
    q = q.where(_campaign_upload_scope(campaign_id))
    q = _apply_contact_filters(
        q,
        title_match=title_match,
        verification_status=verification_status,
        stage_filter=stage_filter,
        company_id=company_id,
    )
    if upload_id is not None:
        q = q.where(col(Company.upload_id) == upload_id)

    rows = list(session.exec(q.order_by(col(ProspectContact.created_at).desc())).all())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "domain",
        "first_name",
        "last_name",
        "title",
        "title_match",
        "pipeline_stage",
        "email",
        "verification_status",
        "provider_email_status",
        "snov_confidence",
        "linkedin_url",
    ])
    for contact, domain in rows:
        writer.writerow([
            domain,
            contact.first_name,
            contact.last_name,
            contact.title or "",
            contact.title_match,
            contact.pipeline_stage,
            contact.email or "",
            contact.verification_status,
            contact.provider_email_status or "",
            contact.snov_confidence or "",
            contact.linkedin_url or "",
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/contacts/verify", response_model=ContactVerifyResult, status_code=status.HTTP_201_CREATED)
def verify_contacts(
    payload: ContactVerifyRequest,
    session: Session = Depends(get_session),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> ContactVerifyResult:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    try:
        idempotency_key = normalize_idempotency_key(x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request_payload = payload.model_dump(mode="json", exclude_none=True)
    request_payload["route"] = "contacts/verify"
    try:
        replay = check_idempotency(
            namespace="contacts-verify",
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
        return ContactVerifyResult(**response_payload)

    try:
        contact_ids = _select_verification_contact_ids(session, payload)
        if not contact_ids:
            raise HTTPException(status_code=422, detail="No eligible contacts to verify.")

        job = ContactVerifyJob(
            state=ContactVerifyJobState.QUEUED,
            terminal_state=False,
            filter_snapshot_json=payload.model_dump(mode="json", exclude_none=True),
            contact_ids_json=[str(contact_id) for contact_id in contact_ids],
            selected_count=len(contact_ids),
            verified_count=0,
            skipped_count=0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        try:
            verify_contacts_batch.delay(str(job.id))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"Queue unavailable: {exc}") from exc

        result = ContactVerifyResult(
            job_id=job.id,
            selected_count=len(contact_ids),
            message=f"Queued ZeroBounce verification for {len(contact_ids)} contacts.",
            idempotency_key=idempotency_key,
            idempotency_replayed=False,
        )
        store_idempotency_response(
            namespace="contacts-verify",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        clear_idempotency_reservation(
            namespace="contacts-verify",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
        raise


@router.get("/title-match-rules", response_model=list[TitleMatchRuleRead])
def list_title_rules(session: Session = Depends(get_session)) -> list[TitleMatchRuleRead]:
    rules = list(
        session.exec(
            select(TitleMatchRule).order_by(col(TitleMatchRule.rule_type), col(TitleMatchRule.created_at))
        ).all()
    )
    return [TitleMatchRuleRead.model_validate(rule, from_attributes=True) for rule in rules]


@router.post("/title-match-rules", response_model=TitleMatchRuleRead, status_code=status.HTTP_201_CREATED)
def create_title_rule(
    payload: TitleMatchRuleCreate,
    session: Session = Depends(get_session),
) -> TitleMatchRuleRead:
    rule = TitleMatchRule(rule_type=payload.rule_type, keywords=payload.keywords, match_type=payload.match_type)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    rematch_existing_contacts(session)
    return TitleMatchRuleRead.model_validate(rule, from_attributes=True)


@router.delete("/title-match-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_title_rule(
    rule_id: UUID,
    session: Session = Depends(get_session),
) -> None:
    rule = session.get(TitleMatchRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    session.delete(rule)
    session.commit()
    rematch_existing_contacts(session)


@router.post("/title-match-rules/rematch", response_model=RematchResult)
def rematch_contacts(session: Session = Depends(get_session)) -> RematchResult:
    updated, _company_ids = rematch_existing_contacts(session)
    return RematchResult(
        updated=updated,
        fetch_jobs_queued=0,
        message=(
            f"Re-evaluated all contacts; {updated} title_match flags changed, no fetch jobs queued."
        ),
    )


@router.get("/title-match-rules/impact-preview", response_model=TitleRuleImpactPreview)
def preview_title_rule_impact(
    campaign_id: UUID = Query(...),
    source: str = Query(default="snov"),
    include_stale: bool = Query(default=False),
    stale_days: int | None = Query(default=None, ge=1, le=365),
    force_refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> TitleRuleImpactPreview:
    normalized_source = _normalize_impact_source(source)
    if not isinstance(include_stale, bool):
        include_stale = bool(getattr(include_stale, "default", False))
    if not isinstance(stale_days, int):
        stale_days = getattr(stale_days, "default", None)
    if not isinstance(force_refresh, bool):
        force_refresh = bool(getattr(force_refresh, "default", False))
    companies, affected_contact_count, stale_contact_count = _title_rule_impact_targets(
        session=session,
        campaign_id=campaign_id,
        source=normalized_source,
        include_stale=include_stale,
        stale_days=stale_days,
        force_refresh=force_refresh,
    )
    return TitleRuleImpactPreview(
        campaign_id=campaign_id,
        source=normalized_source,
        include_stale=include_stale,
        stale_days=(
            stale_days
            if stale_days is not None
            else (
                None
                if normalized_source == "both"
                else _IMPACT_PROVIDER_STALE_DEFAULT_DAYS[normalized_source]
            )
        ),
        stale_days_override=stale_days,
        provider_default_days=dict(_IMPACT_PROVIDER_STALE_DEFAULT_DAYS),
        force_refresh=force_refresh,
        affected_company_count=len(companies),
        affected_contact_count=affected_contact_count,
        stale_contact_count=stale_contact_count,
        affected_company_ids=[company.id for company in companies],
    )


@router.post(
    "/title-match-rules/impact-fetch",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def queue_title_rule_impact_fetch(
    campaign_id: UUID = Query(...),
    source: str = Query(default="snov"),
    include_stale: bool = Query(default=False),
    stale_days: int | None = Query(default=None, ge=1, le=365),
    force_refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    if not isinstance(include_stale, bool):
        include_stale = bool(getattr(include_stale, "default", False))
    if not isinstance(stale_days, int):
        stale_days = getattr(stale_days, "default", None)
    if not isinstance(force_refresh, bool):
        force_refresh = bool(getattr(force_refresh, "default", False))
    normalized_source = _normalize_impact_source(source)
    companies, _affected_contact_count, _stale_contact_count = _title_rule_impact_targets(
        session=session,
        campaign_id=campaign_id,
        source=normalized_source,
        include_stale=include_stale,
        stale_days=stale_days,
        force_refresh=force_refresh,
    )
    if normalized_source == "both":
        result = _enqueue_contact_fetches(
            session=session,
            companies=companies,
            provider="snov",
            next_provider="apollo",
        )
        total_queued = result.queued_count
        total_already_fetching = result.already_fetching_count
        all_job_ids = list(result.queued_job_ids)
    else:
        result = _enqueue_contact_fetches(session=session, companies=companies, provider=normalized_source)
        total_queued = result.queued_count
        total_already_fetching = result.already_fetching_count
        all_job_ids = list(result.queued_job_ids)
    return ContactFetchResult(
        requested_count=len(companies),
        queued_count=total_queued,
        already_fetching_count=total_already_fetching,
        queued_job_ids=all_job_ids,
    )


@router.post("/title-match-rules/seed", response_model=TitleRuleSeedResult)
def seed_rules(session: Session = Depends(get_session)) -> TitleRuleSeedResult:
    inserted = seed_title_rules(session)
    return TitleRuleSeedResult(
        inserted=inserted,
        message=f"Inserted {inserted} new rules (duplicates skipped).",
    )


@router.post("/title-match-rules/test", response_model=TitleTestResult)
def run_title_test(
    payload: TitleTestRequest,
    session: Session = Depends(get_session),
) -> TitleTestResult:
    result = test_title_match_detailed(payload.title, session)
    return TitleTestResult.model_validate(result)


@router.get("/title-match-rules/stats", response_model=TitleRuleStatsResponse)
def get_title_rule_stats(session: Session = Depends(get_session)) -> TitleRuleStatsResponse:
    result = compute_title_rule_stats(session)
    return TitleRuleStatsResponse.model_validate(result)
