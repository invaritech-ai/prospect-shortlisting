from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.analysis import FeedbackRead, FeedbackUpsert
from app.api.schemas.contacts import (
    BulkContactFetchRequest,
    ContactFetchResult,
    ContactListResponse,
    ContactRead,
)
from app.api.schemas.scrape import ScrapeRunRead
from app.api.schemas.upload import (
    CompanyIdsResult,
    CompanyList,
    CompanyListItem,
    CompanyScrapeRequest,
    CompanyScrapeResult,
    LetterCounts,
)
from app.db.session import get_engine, get_session
from app.jobs._defaults import DEFAULT_CLASSIFY_MODEL, DEFAULT_GENERAL_MODEL
from app.jobs._priority import BULK_PIPELINE
from app.jobs.scrape import defer_scrape_website_bulk, dispatch_scrape_run
from app.jobs.contact_fetch import fetch_contacts as _fetch_contacts_task
from app.models import Company, CompanyFeedback, Contact, ScrapeJob, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState

_S3_ELIGIBLE_STAGES = frozenset({
    CompanyPipelineStage.SCRAPED,
    CompanyPipelineStage.CLASSIFIED,
    CompanyPipelineStage.CONTACT_READY,
})
from app.services.contact_fetch_service import ContactFetchService
from app.services.contact_query_service import (
    apply_contact_filters as _apply_contact_filters,
    campaign_upload_scope as _campaign_upload_scope,
    contact_emails_map as _contact_emails_map,
)

_contact_fetch_service = ContactFetchService()
from app.models.pipeline import utcnow
from app.models.scrape import ScrapeRun, ScrapeRunItem
from app.services.queue_guard import available_slots, current_depth
from app.services.company_service import (
    CompanyFilters,
    apply_company_filters,
    build_company_query_context,
    build_company_count_stmt,
    build_company_list_stmt,
    validate_campaign_upload_scope,
    validate_company_filters,
)
from app.services.pipeline_service import recompute_company_stages
from app.services.scrape_service import (
    CircuitBreakerOpenError,
    ScrapeJobAlreadyRunningError,
    ScrapeJobManager,
)

router = APIRouter(prefix="/v1", tags=["companies"])
_scrape_manager = ScrapeJobManager()


@router.get("/companies", response_model=CompanyList)
def list_companies(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    include_total: bool = Query(default=False),
    letter: str | None = Query(default=None, min_length=1, max_length=1),
    letters: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    search: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="last_activity"),
    sort_dir: str = Query(default="desc"),
    upload_id: UUID | None = Query(default=None),
) -> CompanyList:
    filters: CompanyFilters = validate_company_filters(
        decision_filter=decision_filter,
        scrape_filter=scrape_filter,
        stage_filter=stage_filter,
        status_filter=status_filter,
        search=search,
        letter=letter,
        letters=letters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        upload_id=upload_id,
        include_total=include_total,
    )
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    stmt = build_company_list_stmt(campaign_id, filters)
    rows = list(session.exec(stmt.offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    total: int | None = None
    if include_total:
        total = session.exec(build_company_count_stmt(campaign_id, filters)).one()

    items = [
        CompanyListItem(
            id=row[0], upload_id=row[1], upload_filename=row[2],
            raw_url=row[3], normalized_url=row[4], domain=row[5],
            pipeline_stage=str(row[6]), created_at=row[7],
            latest_decision=str(row[8]).lower() if row[8] is not None else None,
            latest_confidence=row[9],
            latest_scrape_job_id=row[10],
            latest_scrape_status=str(row[11]) if row[11] is not None else None,
            latest_scrape_terminal=row[12],
            latest_analysis_pipeline_run_id=row[13],
            latest_analysis_status=str(row[14]) if row[14] is not None else None,
            latest_analysis_terminal=row[15],
            latest_analysis_job_id=row[16],
            feedback_thumbs=str(row[17]) if row[17] is not None else None,
            feedback_comment=str(row[18]) if row[18] is not None else None,
            feedback_manual_label=str(row[19]) if row[19] is not None else None,
            latest_scrape_error_code=str(row[20]) if row[20] is not None else None,
            latest_scrape_failure_reason=str(row[21]) if row[21] is not None else None,
            contact_count=int(row[22]) if row[22] is not None else 0,
            revealed_contact_count=int(row[22]) if row[22] is not None else 0,
            discovered_contact_count=int(row[22]) if row[22] is not None else 0,
            discovered_title_matched_count=int(row[23]) if row[23] is not None else 0,
            contact_fetch_status=str(row[24]) if row[24] is not None else None,
            last_activity=row[25],
        )
        for row in page_rows
    ]
    return CompanyList(total=total, has_more=has_more, limit=limit, offset=offset, items=items)


@router.get("/companies/letter-counts", response_model=LetterCounts)
def get_letter_counts(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    stage_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    search: str | None = Query(default=None, max_length=200),
    upload_id: UUID | None = Query(default=None),
) -> LetterCounts:
    filters = validate_company_filters(
        decision_filter=decision_filter,
        scrape_filter=scrape_filter,
        stage_filter=stage_filter,
        status_filter=status_filter,
        search=search,
        letter=None,
        letters=None,
        upload_id=upload_id,
    )
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    ctx = build_company_query_context()
    letter_expr = func.lower(func.substr(Company.domain, 1, 1))
    stmt = (
        select(letter_expr.label("letter"), func.count().label("count"))
        .select_from(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .outerjoin(ctx.latest_classification, ctx.latest_classification.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_scrape, ctx.latest_scrape.c.normalized_url == col(Company.normalized_url))
        .outerjoin(ctx.latest_analysis, ctx.latest_analysis.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_contact_fetch, ctx.latest_contact_fetch.c.company_id == col(Company.id))
        .outerjoin(CompanyFeedback, col(CompanyFeedback.company_id) == col(Company.id))
        .where(col(Upload.campaign_id) == campaign_id)
        .where(letter_expr.between("a", "z"))
        .group_by(letter_expr)
    )
    stmt = apply_company_filters(stmt, filters, ctx)

    counts = {chr(ord("a") + i): 0 for i in range(26)}
    for letter, count in session.exec(stmt):
        if letter in counts:
            counts[letter] = int(count or 0)
    return LetterCounts(counts=counts)


@router.get("/companies/ids", response_model=CompanyIdsResult)
def get_company_ids(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    letter: str | None = Query(default=None, min_length=1, max_length=1),
    letters: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    search: str | None = Query(default=None, max_length=200),
    upload_id: UUID | None = Query(default=None),
) -> CompanyIdsResult:
    filters = validate_company_filters(
        decision_filter=decision_filter,
        scrape_filter=scrape_filter,
        stage_filter=stage_filter,
        status_filter=status_filter,
        search=search,
        letter=letter,
        letters=letters,
        upload_id=upload_id,
    )
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    ctx = build_company_query_context()
    stmt = (
        select(col(Company.id))
        .select_from(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .outerjoin(ctx.latest_classification, ctx.latest_classification.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_scrape, ctx.latest_scrape.c.normalized_url == col(Company.normalized_url))
        .outerjoin(ctx.latest_analysis, ctx.latest_analysis.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_contact_fetch, ctx.latest_contact_fetch.c.company_id == col(Company.id))
        .outerjoin(CompanyFeedback, col(CompanyFeedback.company_id) == col(Company.id))
        .where(col(Upload.campaign_id) == campaign_id)
    )
    stmt = apply_company_filters(stmt, filters, ctx).order_by(col(Company.domain).asc())
    ids = list(session.exec(stmt))
    return CompanyIdsResult(ids=ids, total=len(ids))


@router.post("/companies/scrape-selected", response_model=ScrapeRunRead)
async def scrape_selected_companies(
    payload: CompanyScrapeRequest,
    session: Session = Depends(get_session),
) -> ScrapeRunRead:
    validate_campaign_upload_scope(
        session=session,
        campaign_id=payload.campaign_id,
        upload_id=payload.upload_id,
    )
    company_ids = payload.company_ids
    scrape_rules_kw = payload.scrape_rules.model_dump() if payload.scrape_rules else None

    # Validate all submitted IDs belong to this campaign (and upload if scoped).
    # 400 rather than silent drop: the caller must know if their selection was stale.
    scope_q = (
        select(col(Company.id))
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(col(Upload.campaign_id) == payload.campaign_id)
    )
    if payload.upload_id is not None:
        scope_q = scope_q.where(col(Upload.id) == payload.upload_id)
    authorized = {row for row in session.exec(scope_q)}
    invalid = [cid for cid in company_ids if cid not in authorized]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "company_ids_out_of_scope",
                "invalid_ids": [str(i) for i in invalid],
            },
        )

    run = ScrapeRun(
        campaign_id=payload.campaign_id,
        requested_count=len(company_ids),
        scrape_rules=scrape_rules_kw,
    )
    session.add(run)

    items = [
        ScrapeRunItem(run_id=run.id, company_id=cid)
        for cid in company_ids
    ]
    session.add_all(items)
    session.commit()
    session.refresh(run)

    await dispatch_scrape_run.defer_async(run_id=str(run.id))

    return ScrapeRunRead.model_validate(run, from_attributes=True)


@router.post("/companies/scrape-all", response_model=CompanyScrapeResult)
async def scrape_all_companies(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> CompanyScrapeResult:
    """Queue scrape jobs for every company in the campaign with no active scrape.

    TODO: migrate to ScrapeRun + dispatch_scrape_run pattern (same as scrape-selected).
    """
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=None)
    engine = get_engine()
    queue_depth = current_depth(engine, "scrape")

    active_subq = (
        select(col(ScrapeJob.domain))
        .where(col(ScrapeJob.terminal_state).is_(False))
        .scalar_subquery()
    )
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == campaign_id,
                col(Company.domain).not_in(active_subq),
            )
        ).all()
    )

    can_enqueue = available_slots(engine, "scrape", len(companies))
    to_enqueue = companies[:can_enqueue]

    queued_job_ids: list[UUID] = []
    failed_company_ids: list[UUID] = []

    if to_enqueue:
        for company in to_enqueue:
            try:
                with session.begin_nested():
                    job = _scrape_manager.create_job(
                        session=session,
                        website_url=company.normalized_url,
                        js_fallback=True,
                        include_sitemap=True,
                        general_model=DEFAULT_GENERAL_MODEL,
                        classify_model=DEFAULT_CLASSIFY_MODEL,
                    )
                queued_job_ids.append(job.id)
            except (ScrapeJobAlreadyRunningError, CircuitBreakerOpenError, ValueError):
                failed_company_ids.append(company.id)
        session.commit()
        await defer_scrape_website_bulk(
            priority=BULK_PIPELINE,
            job_ids=queued_job_ids,
            scrape_rules=None,
        )

    failed_company_ids.extend(company.id for company in companies[can_enqueue:])
    return CompanyScrapeResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        skipped_count=len(failed_company_ids),
        queue_depth=queue_depth,
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids,
    )


@router.post("/companies/fetch-contacts-selected", response_model=ContactFetchResult)
async def fetch_contacts_selected(
    payload: BulkContactFetchRequest,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == payload.campaign_id,
                col(Company.id).in_(payload.company_ids),
            )
        )
    )
    if {c.id for c in companies} != set(payload.company_ids):
        raise HTTPException(status_code=400, detail="One or more company_ids are outside campaign scope.")

    eligible_ids = [c.id for c in companies if c.pipeline_stage in _S3_ELIGIBLE_STAGES]
    skipped_ineligible = len(payload.company_ids) - len(eligible_ids)

    batch, jobs, reused = _contact_fetch_service.enqueue(
        session=session,
        campaign_id=payload.campaign_id,
        company_ids=eligible_ids,
        force_refresh=payload.force_refresh,
    )
    session.commit()
    session.refresh(batch)

    new_jobs = [j for j in jobs if j.contact_fetch_batch_id == batch.id]
    defer_failed = 0
    for job in new_jobs:
        try:
            await _fetch_contacts_task.defer_async(contact_fetch_job_id=str(job.id))
        except Exception:
            defer_failed += 1

    return ContactFetchResult(
        requested_count=len(payload.company_ids),
        queued_count=len(new_jobs) - defer_failed,
        already_fetching_count=reused,
        queued_job_ids=[j.id for j in new_jobs if j.state == ContactFetchJobState.QUEUED],
        reused_count=reused,
        batch_id=batch.id,
    )


@router.post("/companies/{company_id}/fetch-contacts", response_model=ContactFetchResult)
async def fetch_contacts_for_company(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    force_refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    upload = session.get(Upload, company.upload_id)
    if upload is None or upload.campaign_id != campaign_id:
        raise HTTPException(status_code=400, detail="Company is not in the selected campaign.")
    if company.pipeline_stage not in _S3_ELIGIBLE_STAGES:
        raise HTTPException(status_code=400, detail="Company has not been scraped yet and is not eligible for contact discovery.")

    batch, jobs, reused = _contact_fetch_service.enqueue(
        session=session,
        campaign_id=campaign_id,
        company_ids=[company_id],
        force_refresh=force_refresh,
    )
    session.commit()
    session.refresh(batch)
    for j in jobs:
        session.refresh(j)

    new_jobs = [j for j in jobs if j.contact_fetch_batch_id == batch.id]
    defer_failed = 0
    for job in new_jobs:
        try:
            await _fetch_contacts_task.defer_async(contact_fetch_job_id=str(job.id))
        except Exception:
            defer_failed += 1

    return ContactFetchResult(
        requested_count=1,
        queued_count=len(new_jobs) - defer_failed,
        already_fetching_count=reused,
        queued_job_ids=[j.id for j in new_jobs if j.state == ContactFetchJobState.QUEUED],
        reused_count=reused,
        batch_id=batch.id,
    )


@router.get("/companies/{company_id}/contacts", response_model=ContactListResponse)
def list_company_contacts(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    from sqlalchemy import func as _func

    if not isinstance(title_match, bool):
        title_match = getattr(title_match, "default", None)
    if not isinstance(verification_status, str):
        verification_status = getattr(verification_status, "default", None)
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")

    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    upload = session.get(Upload, company.upload_id)
    if upload is None or upload.campaign_id != campaign_id:
        raise HTTPException(status_code=400, detail="Company is not in the selected campaign.")

    q = select(Contact, Company.domain).join(Company, col(Company.id) == col(Contact.company_id))
    q = q.where(_campaign_upload_scope(campaign_id), col(Contact.company_id) == company_id)
    q = _apply_contact_filters(
        q,
        title_match=title_match,
        verification_status=verification_status,
        stage_filter=stage_filter,
    )

    total = session.exec(select(_func.count()).select_from(q.subquery())).one()
    rows = list(session.exec(q.order_by(col(Contact.created_at).desc()).offset(offset).limit(limit)).all())

    email_map = _contact_emails_map(session, [c for c, _ in rows])
    items = [
        ContactRead.model_validate({
            **c.__dict__,
            "domain": domain,
            "emails": email_map.get(c.id, []),
            "freshness_status": "fresh",
            "group_key": str(c.id),
            "last_seen_at": c.last_seen_at,
            "provider_has_email": c.provider_has_email,
            "source_provider": c.source_provider,
        })
        for c, domain in rows
    ]

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.put("/companies/{company_id}/feedback", response_model=FeedbackRead)
def upsert_company_feedback(
    company_id: UUID,
    payload: FeedbackUpsert,
    session: Session = Depends(get_session),
) -> FeedbackRead:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    feedback = session.get(CompanyFeedback, company_id)
    now = utcnow()
    if feedback is None:
        feedback = CompanyFeedback(
            company_id=company_id,
            thumbs=payload.thumbs,
            comment=payload.comment,
            manual_label=payload.manual_label,
            created_at=now,
            updated_at=now,
        )
        session.add(feedback)
    else:
        feedback.thumbs = payload.thumbs
        feedback.comment = payload.comment
        feedback.manual_label = payload.manual_label
        feedback.updated_at = now
        session.add(feedback)

    recompute_company_stages(session, company_ids=[company_id])
    session.commit()
    session.refresh(feedback)
    return FeedbackRead(
        thumbs=feedback.thumbs,
        comment=feedback.comment,
        manual_label=feedback.manual_label,
        updated_at=feedback.updated_at,
    )
