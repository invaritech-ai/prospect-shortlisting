from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.analysis import FeedbackRead, FeedbackUpsert
from app.api.schemas.upload import (
    CompanyList,
    CompanyListItem,
    CompanyScrapeRequest,
    CompanyScrapeResult,
    LetterCounts,
)
from app.db.session import get_engine, get_session
from app.jobs._priority import BULK_PIPELINE, BULK_USER
from app.jobs.scrape import scrape_website
from app.models import Company, CompanyFeedback, ScrapeJob, Upload
from app.models.pipeline import utcnow
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
_DEFAULT_GENERAL_MODEL = "openai/gpt-4.1-nano"
_DEFAULT_CLASSIFY_MODEL = "inception/mercury-2"


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
            contact_count=int(row[21]) if row[21] is not None else 0,
            revealed_contact_count=int(row[21]) if row[21] is not None else 0,
            discovered_contact_count=int(row[21]) if row[21] is not None else 0,
            discovered_title_matched_count=int(row[22]) if row[22] is not None else 0,
            contact_fetch_status=str(row[23]) if row[23] is not None else None,
            last_activity=row[24],
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


@router.post("/companies/scrape-selected", response_model=CompanyScrapeResult)
async def scrape_selected_companies(
    payload: CompanyScrapeRequest,
    session: Session = Depends(get_session),
) -> CompanyScrapeResult:
    validate_campaign_upload_scope(
        session=session,
        campaign_id=payload.campaign_id,
        upload_id=payload.upload_id,
    )
    engine = get_engine()
    company_ids = payload.company_ids
    queue_depth = current_depth(engine, "scrape")
    can_enqueue = available_slots(engine, "scrape", len(company_ids))
    to_enqueue = company_ids[:can_enqueue]
    skipped_capacity = company_ids[can_enqueue:]

    queued_job_ids: list[UUID] = []
    failed_company_ids: list[UUID] = list(skipped_capacity)

    for company_id in to_enqueue:
        company = session.get(Company, company_id)
        if company is None:
            failed_company_ids.append(company_id)
            continue
        try:
            job = _scrape_manager.create_job(
                session=session,
                website_url=company.normalized_url,
                js_fallback=True,
                include_sitemap=True,
                general_model=_DEFAULT_GENERAL_MODEL,
                classify_model=_DEFAULT_CLASSIFY_MODEL,
            )
            session.commit()
            await scrape_website.defer_async(
                job_id=str(job.id),
                scrape_rules=payload.scrape_rules.model_dump() if payload.scrape_rules else None,
                priority=BULK_USER,
            )
            queued_job_ids.append(job.id)
        except (ScrapeJobAlreadyRunningError, CircuitBreakerOpenError, ValueError):
            session.rollback()
            failed_company_ids.append(company_id)

    return CompanyScrapeResult(
        requested_count=len(company_ids),
        queued_count=len(queued_job_ids),
        skipped_count=len(failed_company_ids),
        queue_depth=queue_depth,
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids,
    )


@router.post("/companies/scrape-all", response_model=CompanyScrapeResult)
async def scrape_all_companies(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> CompanyScrapeResult:
    """Queue scrape jobs for every company in the campaign with no active scrape."""
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

    for company in to_enqueue:
        try:
            job = _scrape_manager.create_job(
                session=session,
                website_url=company.normalized_url,
                js_fallback=True,
                include_sitemap=True,
                general_model=_DEFAULT_GENERAL_MODEL,
                classify_model=_DEFAULT_CLASSIFY_MODEL,
            )
            session.commit()
            await scrape_website.defer_async(
                job_id=str(job.id),
                priority=BULK_PIPELINE,
            )
            queued_job_ids.append(job.id)
        except (ScrapeJobAlreadyRunningError, CircuitBreakerOpenError, ValueError):
            session.rollback()
            failed_company_ids.append(company.id)

    failed_company_ids.extend(company.id for company in companies[can_enqueue:])
    return CompanyScrapeResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        skipped_count=len(failed_company_ids),
        queue_depth=queue_depth,
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids,
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
