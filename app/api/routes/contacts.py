"""Contact fetching, verification, listing, and title-match rule endpoints."""
from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Integer, case, func, or_, select as sa_select, text
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
    ProspectContactRead,
    RematchResult,
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
    ClassificationResult,
    Company,
    ContactFetchJob,
    ContactVerifyJob,
    ProspectContact,
    Run,
    TitleMatchRule,
)
from app.models.pipeline import (
    AnalysisJobState,
    CompanyPipelineStage,
    ContactVerifyJobState,
    PredictedLabel,
)
from app.services.contact_service import (
    compute_title_rule_stats,
    rematch_existing_contacts,
    seed_title_rules,
    test_title_match_detailed,
)
from app.tasks.contacts import fetch_contacts, fetch_contacts_apollo, verify_contacts_batch

router = APIRouter(prefix="/v1", tags=["contacts"])

_ALLOWED_CONTACT_STAGE_FILTERS = frozenset({"all", "fetched", "verified", "campaign_ready"})


def _validate_contact_stage_filter(stage_filter: str) -> str:
    normalized = (stage_filter or "all").strip().lower()
    if normalized not in _ALLOWED_CONTACT_STAGE_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid stage_filter.")
    return normalized


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
    company_id: UUID | None = None,
    company_ids: list[UUID] | None = None,
):
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
    if explicit_ids:
        rows = list(
            session.exec(
                select(ProspectContact.id)
                .join(Company, col(Company.id) == col(ProspectContact.company_id))
                .where(
                    col(ProspectContact.id).in_(explicit_ids),
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
    stmt = stmt.where(*_verification_eligible_condition())
    return list(session.exec(stmt))


def _enqueue_contact_fetches(
    *,
    session: Session,
    companies: list[Company],
    provider: str = "snov",
) -> ContactFetchResult:
    eligible_companies = [company for company in companies if company.pipeline_stage == CompanyPipelineStage.CONTACT_READY]
    if not eligible_companies:
        return ContactFetchResult(
            requested_count=len(companies),
            queued_count=0,
            already_fetching_count=0,
            queued_job_ids=[],
        )

    company_ids = [c.id for c in eligible_companies]
    active_company_ids: set[UUID] = set(
        session.exec(
            select(ContactFetchJob.company_id).where(
                col(ContactFetchJob.company_id).in_(company_ids),
                col(ContactFetchJob.terminal_state).is_(False),
                ContactFetchJob.provider == provider,
            )
        ).all()
    )

    jobs_to_create: list[ContactFetchJob] = []
    for company in eligible_companies:
        if company.id in active_company_ids:
            continue
        jobs_to_create.append(ContactFetchJob(company_id=company.id, provider=provider))

    if jobs_to_create:
        session.add_all(jobs_to_create)
        session.commit()

    queued_job_ids: list[UUID] = []
    task = fetch_contacts_apollo if provider == "apollo" else fetch_contacts
    for job in jobs_to_create:
        if job.id:
            task.delay(str(job.id))
            queued_job_ids.append(job.id)

    return ContactFetchResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        already_fetching_count=len(active_company_ids),
        queued_job_ids=queued_job_ids,
    )


@router.post(
    "/companies/{company_id}/fetch-contacts",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_contacts_for_company(
    company_id: UUID,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    return _enqueue_contact_fetches(session=session, companies=[company], provider="snov")


@router.post(
    "/companies/{company_id}/fetch-contacts/apollo",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_apollo_contacts_for_company(
    company_id: UUID,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    return _enqueue_contact_fetches(session=session, companies=[company], provider="apollo")


@router.post(
    "/runs/{run_id}/fetch-contacts",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_contacts_for_run(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

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
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

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
) -> ContactFetchResult:
    requested_ids = list(dict.fromkeys(payload.company_ids))
    companies = list(
        session.exec(select(Company).where(col(Company.id).in_(requested_ids)))
    )
    if not companies:
        raise HTTPException(status_code=404, detail="No matching companies found.")

    providers: list[str] = ["snov", "apollo"] if payload.source == "both" else [payload.source]
    total_queued, total_already_fetching = 0, 0
    all_job_ids: list[UUID] = []

    for provider in providers:
        r = _enqueue_contact_fetches(session=session, companies=companies, provider=provider)
        total_queued += r.queued_count
        total_already_fetching = max(total_already_fetching, r.already_fetching_count)
        all_job_ids.extend(r.queued_job_ids)

    return ContactFetchResult(
        requested_count=len(companies),
        queued_count=total_queued,
        already_fetching_count=total_already_fetching,
        queued_job_ids=all_job_ids,
    )


@router.get("/companies/{company_id}/contacts", response_model=ContactListResponse)
def list_company_contacts(
    company_id: UUID,
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

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

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=[ProspectContactRead.model_validate({**c.__dict__, "domain": company.domain}) for c in items],
    )


@router.get("/contacts/companies", response_model=ContactCompanyListResponse)
def list_contacts_by_company(
    search: str | None = Query(default=None),
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactCompanyListResponse:
    normalized_stage = _validate_contact_stage_filter(stage_filter)
    stmt = (
        sa_select(
            col(Company.id).label("company_id"),
            col(Company.domain).label("domain"),
            func.count(col(ProspectContact.id)).label("total_count"),
            func.coalesce(func.sum(col(ProspectContact.title_match).cast(Integer)), 0).label("title_matched_count"),
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
        )
        .select_from(Company)
        .join(ProspectContact, col(ProspectContact.company_id) == col(Company.id))
        .group_by(col(Company.id), col(Company.domain))
    )
    if search:
        stmt = stmt.where(func.lower(col(Company.domain)).like(f"%{search.lower()}%"))
    if title_match is not None:
        stmt = stmt.where(col(ProspectContact.title_match) == title_match)
    if verification_status:
        stmt = stmt.where(col(ProspectContact.verification_status) == verification_status.strip().lower())
    if normalized_stage != "all":
        stmt = stmt.where(col(ProspectContact.pipeline_stage) == normalized_stage)

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
                email_count=row.email_count,
                fetched_count=row.fetched_count,
                verified_count=row.verified_count,
                campaign_ready_count=row.campaign_ready_count,
                eligible_verify_count=row.eligible_verify_count,
            )
            for row in rows
        ],
    )


_CONTACT_SORT_FIELDS = frozenset(
    {"domain", "created_at", "first_name", "last_name", "title", "verification_status", "pipeline_stage"}
)


@router.get("/contacts", response_model=ContactListResponse)
def list_all_contacts(
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="domain"),
    sort_dir: str = Query(default="asc"),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    q = select(ProspectContact, Company.domain).join(
        Company, col(Company.id) == col(ProspectContact.company_id)
    )
    q = _apply_contact_filters(
        q,
        title_match=title_match,
        verification_status=verification_status,
        search=search,
        stage_filter=stage_filter,
    )

    total = session.exec(select(func.count()).select_from(q.subquery())).one()

    _sb = sort_by if sort_by in _CONTACT_SORT_FIELDS else "domain"
    _sd = "desc" if sort_dir.lower() == "desc" else "asc"
    _contact_sort_map = {
        "domain": col(Company.domain),
        "created_at": col(ProspectContact.created_at),
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
    for contact, domain in rows:
        items.append(ProspectContactRead.model_validate({**contact.__dict__, "domain": domain}))

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get("/contacts/counts", response_model=ContactCountsResponse)
def get_contact_counts(session: Session = Depends(get_session)) -> ContactCountsResponse:
    row = session.exec(
        select(
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
        ).select_from(ProspectContact)
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
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    company_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
) -> Response:
    q = select(ProspectContact, Company.domain).join(
        Company, col(Company.id) == col(ProspectContact.company_id)
    )
    q = _apply_contact_filters(
        q,
        title_match=title_match,
        verification_status=verification_status,
        stage_filter=stage_filter,
        company_id=company_id,
    )

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
) -> ContactVerifyResult:
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

    return ContactVerifyResult(
        job_id=job.id,
        selected_count=len(contact_ids),
        message=f"Queued ZeroBounce verification for {len(contact_ids)} contacts.",
    )


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
    _, company_ids = rematch_existing_contacts(session)
    if company_ids:
        companies = list(session.exec(select(Company).where(col(Company.id).in_(company_ids))))
        _enqueue_contact_fetches(session=session, companies=companies, provider="snov")
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
    _, company_ids = rematch_existing_contacts(session)
    if company_ids:
        companies = list(session.exec(select(Company).where(col(Company.id).in_(company_ids))))
        _enqueue_contact_fetches(session=session, companies=companies, provider="snov")


@router.post("/title-match-rules/rematch", response_model=RematchResult)
def rematch_contacts(session: Session = Depends(get_session)) -> RematchResult:
    updated, company_ids = rematch_existing_contacts(session)
    fetch_result = ContactFetchResult(
        requested_count=0,
        queued_count=0,
        already_fetching_count=0,
        queued_job_ids=[],
    )
    if company_ids:
        companies = list(session.exec(select(Company).where(col(Company.id).in_(company_ids))))
        fetch_result = _enqueue_contact_fetches(session=session, companies=companies, provider="snov")
    return RematchResult(
        updated=updated,
        fetch_jobs_queued=fetch_result.queued_count,
        message=(
            f"Re-evaluated all contacts; {updated} title_match flags changed, "
            f"{fetch_result.queued_count} email fetch jobs queued."
        ),
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
