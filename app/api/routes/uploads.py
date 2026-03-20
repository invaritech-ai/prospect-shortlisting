from __future__ import annotations

import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import String, case, cast, func
from sqlmodel import Session, col, delete, select

from app.api.schemas.upload import (
    CompanyCounts,
    CompanyDeleteRequest,
    CompanyDeleteResult,
    CompanyIdsResult,
    CompanyList,
    CompanyListItem,
    CompanyRead,
    CompanyScrapeRequest,
    CompanyScrapeResult,
    LetterCounts,
    UploadCompanyList,
    UploadCreateResult,
    UploadDetail,
    UploadList,
    UploadRead,
    UploadValidationError,
)
from app.db.session import get_session
from app.models import (
    AnalysisJob,
    ClassificationResult,
    Company,
    CompanyFeedback,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    ScrapeJob,
    Upload,
)
from app.services.scrape_service import ScrapeService
from app.services.upload_service import UploadIssue, UploadService
from app.tasks.scrape import scrape_website


router = APIRouter(prefix="/v1", tags=["uploads"])
upload_service = UploadService()
scrape_service = ScrapeService()
SCRAPE_DEFAULTS = {
    "js_fallback": True,
    "include_sitemap": True,
    "general_model": "openai/gpt-5-nano",
    "classify_model": "inception/mercury-2",
}


def _latest_classification_subquery():
    return (
        select(
            AnalysisJob.company_id.label("company_id"),
            cast(ClassificationResult.predicted_label, String()).label("predicted_label"),
            ClassificationResult.confidence.label("confidence"),
        )
        .join(AnalysisJob, AnalysisJob.id == ClassificationResult.analysis_job_id)
        .distinct(AnalysisJob.company_id)
        .order_by(AnalysisJob.company_id, ClassificationResult.created_at.desc())
        .subquery()
    )


def _latest_scrape_subquery():
    return (
        select(
            ScrapeJob.normalized_url.label("normalized_url"),
            ScrapeJob.id.label("job_id"),
            ScrapeJob.status.label("status"),
            ScrapeJob.terminal_state.label("terminal_state"),
        )
        .distinct(ScrapeJob.normalized_url)
        .order_by(ScrapeJob.normalized_url, ScrapeJob.created_at.desc())
        .subquery()
    )


def _latest_analysis_subquery():
    return (
        select(
            AnalysisJob.company_id.label("company_id"),
            AnalysisJob.id.label("analysis_job_id"),
            AnalysisJob.run_id.label("run_id"),
            cast(AnalysisJob.state, String()).label("state"),
            AnalysisJob.terminal_state.label("terminal_state"),
        )
        .distinct(AnalysisJob.company_id)
        .order_by(AnalysisJob.company_id, AnalysisJob.created_at.desc())
        .subquery()
    )


def _enqueue_scrapes_for_companies(*, session: Session, companies: list[Company]) -> CompanyScrapeResult:
    from app.services.url_utils import domain_from_url, normalize_url

    # Resolve normalized URLs upfront; collect failures immediately.
    failed_company_ids: list[UUID] = []
    valid: list[tuple[Company, str, str]] = []  # (company, normalized_url, domain)
    for company in companies:
        normalized = normalize_url(company.normalized_url or company.website_url or "")
        if not normalized:
            failed_company_ids.append(company.id)
            continue
        domain = domain_from_url(normalized)
        if not domain:
            failed_company_ids.append(company.id)
            continue
        valid.append((company, normalized, domain))

    if not valid:
        return CompanyScrapeResult(
            requested_count=len(companies),
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=failed_company_ids,
        )

    # Single bulk query: find all URLs that already have a non-terminal job.
    all_normalized = [v[1] for v in valid]
    active_urls: set[str] = set(
        session.exec(
            select(ScrapeJob.normalized_url)
            .where(
                col(ScrapeJob.normalized_url).in_(all_normalized)
                & col(ScrapeJob.terminal_state).is_(False)
            )
        ).all()
    )

    # Build new ScrapeJob objects for URLs that don't already have one.
    jobs_to_create: list[ScrapeJob] = []
    company_by_url: dict[str, UUID] = {}
    for company, normalized, domain in valid:
        if normalized in active_urls:
            # Skip silently — already queued/running.
            continue
        jobs_to_create.append(
            ScrapeJob(
                website_url=company.normalized_url,
                normalized_url=normalized,
                domain=domain,
                js_fallback=SCRAPE_DEFAULTS["js_fallback"],
                include_sitemap=SCRAPE_DEFAULTS["include_sitemap"],
                general_model=SCRAPE_DEFAULTS["general_model"],
                classify_model=SCRAPE_DEFAULTS["classify_model"],
            )
        )
        company_by_url[normalized] = company.id

    if not jobs_to_create:
        return CompanyScrapeResult(
            requested_count=len(companies),
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=failed_company_ids,
        )

    # Single bulk insert + single commit.
    session.add_all(jobs_to_create)
    try:
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        # Fall back to individual inserts so partial success is preserved.
        for job in jobs_to_create:
            try:
                session.add(job)
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
                company_id = company_by_url.get(job.normalized_url)
                if company_id:
                    failed_company_ids.append(company_id)
        jobs_to_create = [j for j in jobs_to_create if j.id is not None]

    # Refresh to get DB-assigned IDs, then fire all Celery messages.
    queued_job_ids: list[UUID] = []
    for job in jobs_to_create:
        if job.id is None:
            continue
        scrape_website.delay(str(job.id))
        queued_job_ids.append(job.id)

    return CompanyScrapeResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids,
    )


def _as_upload_read(upload: Upload) -> UploadRead:
    return UploadRead.model_validate(upload, from_attributes=True)


def _as_issues(items: list[UploadIssue]) -> list[UploadValidationError]:
    return [
        UploadValidationError(
            row_number=item.row_number,
            raw_value=item.raw_value,
            error_code=item.error_code,
            error_message=item.error_message,
        )
        for item in items
    ]


def _issues_from_upload(upload: Upload) -> list[UploadValidationError]:
    items: list[UploadValidationError] = []
    for raw in upload.validation_errors_json or []:
        try:
            row_number = int(raw.get("row_number", 0))
            if row_number < 1:
                continue
            items.append(
                UploadValidationError(
                    row_number=row_number,
                    raw_value=str(raw.get("raw_value", "") or ""),
                    error_code=str(raw.get("error_code", "") or ""),
                    error_message=str(raw.get("error_message", "") or ""),
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return items


@router.post("/uploads", response_model=UploadCreateResult, status_code=status.HTTP_201_CREATED)
async def create_upload(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> UploadCreateResult:
    try:
        raw_bytes = await file.read()
        upload, issues = upload_service.create_upload_from_file(
            session=session,
            filename=file.filename or "upload",
            raw_bytes=raw_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadCreateResult(upload=_as_upload_read(upload), validation_errors=_as_issues(issues))


@router.get("/uploads", response_model=UploadList)
def list_uploads(
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UploadList:
    items = list(
        session.exec(
            select(Upload)
            .order_by(col(Upload.created_at).desc())
            .offset(offset)
            .limit(limit)
        )
    )
    total = session.exec(select(func.count()).select_from(Upload)).one()
    return UploadList(
        total=total,
        limit=limit,
        offset=offset,
        items=[_as_upload_read(item) for item in items],
    )


@router.get("/uploads/{upload_id}", response_model=UploadDetail)
def get_upload(upload_id: UUID, session: Session = Depends(get_session)) -> UploadDetail:
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return UploadDetail(upload=_as_upload_read(upload), validation_errors=_issues_from_upload(upload))


@router.get("/uploads/{upload_id}/companies", response_model=UploadCompanyList)
def list_upload_companies(
    upload_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UploadCompanyList:
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")

    items = list(
        session.exec(
            select(Company)
            .where(col(Company.upload_id) == upload_id)
            .order_by(
                case((col(Company.source_row_number).is_(None), 1), else_=0).asc(),
                col(Company.source_row_number).asc(),
                col(Company.created_at).asc(),
                col(Company.domain).asc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )

    return UploadCompanyList(
        upload_id=upload_id,
        total=upload.valid_count,
        limit=limit,
        offset=offset,
        items=[CompanyRead.model_validate(item, from_attributes=True) for item in items],
    )


@router.get("/companies", response_model=CompanyList)
def list_companies(
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    include_total: bool = Query(default=False),
    letter: str | None = Query(default=None, min_length=1, max_length=1),
) -> CompanyList:
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    latest_analysis = _latest_analysis_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    latest_confidence = latest_classification.c.confidence
    decision_lower = func.lower(func.coalesce(latest_decision_text, ""))
    decision_rank = case(
        (decision_lower == "", 0),
        (decision_lower == "possible", 1),
        (decision_lower == "unknown", 2),
        (decision_lower == "crap", 3),
        else_=4,
    )
    normalized_filter = decision_filter.strip().lower()
    allowed_filters = {"all", "unlabeled", "possible", "unknown", "crap"}
    if normalized_filter not in allowed_filters:
        raise HTTPException(status_code=422, detail="Invalid decision_filter.")
    normalized_scrape_filter = scrape_filter.strip().lower()
    allowed_scrape_filters = {"all", "done", "failed", "none"}
    if normalized_scrape_filter not in allowed_scrape_filters:
        raise HTTPException(status_code=422, detail="Invalid scrape_filter.")
    statement = (
        select(
            Company.id,
            Company.upload_id,
            Upload.filename,
            Company.raw_url,
            Company.normalized_url,
            Company.domain,
            Company.created_at,
            latest_decision_text,
            latest_confidence,
            latest_scrape.c.job_id,
            latest_scrape.c.status,
            latest_scrape.c.terminal_state,
            latest_analysis.c.run_id,
            latest_analysis.c.state,
            latest_analysis.c.terminal_state,
            latest_analysis.c.analysis_job_id,
            CompanyFeedback.thumbs,
            CompanyFeedback.comment,
        )
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .outerjoin(latest_analysis, latest_analysis.c.company_id == Company.id)
        .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
    )
    if normalized_filter == "unlabeled":
        statement = statement.where(decision_lower == "")
    elif normalized_filter in {"possible", "unknown", "crap"}:
        statement = statement.where(decision_lower == normalized_filter)
    if normalized_scrape_filter == "done":
        statement = statement.where(latest_scrape.c.status == "completed")
    elif normalized_scrape_filter == "failed":
        statement = statement.where(latest_scrape.c.status.like("%failed%"))
    elif normalized_scrape_filter == "none":
        statement = statement.where(latest_scrape.c.job_id.is_(None))
    if letter is not None:
        statement = statement.where(func.lower(func.left(Company.domain, 1)) == letter.lower())

    if letter is not None:
        order = statement.order_by(col(Company.domain).asc())
    else:
        order = statement.order_by(
            decision_rank.asc(),
            col(Company.created_at).desc(),
            col(Company.domain).asc(),
        )

    rows = list(
        session.exec(
            order
            .offset(offset)
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    total: int | None = None
    if include_total:
        total_stmt = (
            select(func.count())
            .select_from(Company)
            .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
            .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        )
        if normalized_filter == "unlabeled":
            total_stmt = total_stmt.where(decision_lower == "")
        elif normalized_filter in {"possible", "unknown", "crap"}:
            total_stmt = total_stmt.where(decision_lower == normalized_filter)
        if normalized_scrape_filter == "done":
            total_stmt = total_stmt.where(latest_scrape.c.status == "completed")
        elif normalized_scrape_filter == "failed":
            total_stmt = total_stmt.where(latest_scrape.c.status.like("%failed%"))
        elif normalized_scrape_filter == "none":
            total_stmt = total_stmt.where(latest_scrape.c.job_id.is_(None))
        if letter is not None:
            total_stmt = total_stmt.where(func.lower(func.left(Company.domain, 1)) == letter.lower())
        total = session.exec(total_stmt).one()
    items = [
        CompanyListItem(
            id=row[0],
            upload_id=row[1],
            upload_filename=row[2],
            raw_url=row[3],
            normalized_url=row[4],
            domain=row[5],
            created_at=row[6],
            latest_decision=str(row[7]) if row[7] is not None else None,
            latest_confidence=row[8],
            latest_scrape_job_id=row[9],
            latest_scrape_status=str(row[10]) if row[10] is not None else None,
            latest_scrape_terminal=row[11],
            latest_analysis_run_id=row[12],
            latest_analysis_status=str(row[13]) if row[13] is not None else None,
            latest_analysis_terminal=row[14],
            latest_analysis_job_id=row[15],
            feedback_thumbs=str(row[16]) if row[16] is not None else None,
            feedback_comment=str(row[17]) if row[17] is not None else None,
        )
        for row in page_rows
    ]
    return CompanyList(total=total, has_more=has_more, limit=limit, offset=offset, items=items)


@router.get("/companies/ids", response_model=CompanyIdsResult)
def list_company_ids(
    session: Session = Depends(get_session),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    letter: str | None = Query(default=None, min_length=1, max_length=1),
) -> CompanyIdsResult:
    """Return all company IDs matching the given filters (no pagination) for bulk selection."""
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    decision_lower = func.lower(func.coalesce(latest_decision_text, ""))

    normalized_filter = decision_filter.strip().lower()
    allowed_filters = {"all", "unlabeled", "possible", "unknown", "crap"}
    if normalized_filter not in allowed_filters:
        raise HTTPException(status_code=422, detail="Invalid decision_filter.")
    normalized_scrape_filter = scrape_filter.strip().lower()
    allowed_scrape_filters = {"all", "done", "failed", "none"}
    if normalized_scrape_filter not in allowed_scrape_filters:
        raise HTTPException(status_code=422, detail="Invalid scrape_filter.")

    statement = (
        select(Company.id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
    )
    if normalized_filter == "unlabeled":
        statement = statement.where(decision_lower == "")
    elif normalized_filter in {"possible", "unknown", "crap"}:
        statement = statement.where(decision_lower == normalized_filter)
    if normalized_scrape_filter == "done":
        statement = statement.where(latest_scrape.c.status == "completed")
    elif normalized_scrape_filter == "failed":
        statement = statement.where(latest_scrape.c.status.like("%failed%"))
    elif normalized_scrape_filter == "none":
        statement = statement.where(latest_scrape.c.job_id.is_(None))
    if letter is not None:
        statement = statement.where(func.lower(func.left(Company.domain, 1)) == letter.lower())

    ids = list(session.exec(statement))
    return CompanyIdsResult(ids=ids, total=len(ids))


@router.get("/companies/letter-counts", response_model=LetterCounts)
def get_letter_counts(
    session: Session = Depends(get_session),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
) -> LetterCounts:
    """Return per-letter company counts for the A–Z navigation strip."""
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    decision_lower = func.lower(func.coalesce(latest_decision_text, ""))

    normalized_filter = decision_filter.strip().lower()
    allowed_filters = {"all", "unlabeled", "possible", "unknown", "crap"}
    if normalized_filter not in allowed_filters:
        raise HTTPException(status_code=422, detail="Invalid decision_filter.")
    normalized_scrape_filter = scrape_filter.strip().lower()
    allowed_scrape_filters = {"all", "done", "failed", "none"}
    if normalized_scrape_filter not in allowed_scrape_filters:
        raise HTTPException(status_code=422, detail="Invalid scrape_filter.")

    letter_expr = func.lower(func.left(Company.domain, 1))
    stmt = (
        select(letter_expr.label("letter"), func.count().label("cnt"))
        .select_from(Company)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .where(letter_expr.between("a", "z"))
        .group_by(letter_expr)
    )
    if normalized_filter == "unlabeled":
        stmt = stmt.where(decision_lower == "")
    elif normalized_filter in {"possible", "unknown", "crap"}:
        stmt = stmt.where(decision_lower == normalized_filter)
    if normalized_scrape_filter == "done":
        stmt = stmt.where(latest_scrape.c.status == "completed")
    elif normalized_scrape_filter == "failed":
        stmt = stmt.where(latest_scrape.c.status.like("%failed%"))
    elif normalized_scrape_filter == "none":
        stmt = stmt.where(latest_scrape.c.job_id.is_(None))

    rows = session.exec(stmt).all()
    counts: dict[str, int] = {chr(ord("a") + i): 0 for i in range(26)}
    for ltr, cnt in rows:
        if ltr in counts:
            counts[ltr] = int(cnt)
    return LetterCounts(counts=counts)


@router.get("/companies/counts", response_model=CompanyCounts)
def get_company_counts(session: Session = Depends(get_session)) -> CompanyCounts:
    """Return all filter counts in a single query for display in the UI."""
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    decision_lower = func.lower(func.coalesce(latest_classification.c.predicted_label, ""))
    scrape_status = latest_scrape.c.status

    row = session.exec(
        select(
            func.count().label("total"),
            func.sum(case((decision_lower == "", 1), else_=0)).label("unlabeled"),
            func.sum(case((decision_lower == "possible", 1), else_=0)).label("possible"),
            func.sum(case((decision_lower == "unknown", 1), else_=0)).label("unknown"),
            func.sum(case((decision_lower == "crap", 1), else_=0)).label("crap"),
            func.sum(case((scrape_status == "completed", 1), else_=0)).label("scrape_done"),
            func.sum(case((scrape_status.like("%failed%"), 1), else_=0)).label("scrape_failed"),
            func.sum(case((latest_scrape.c.job_id.is_(None), 1), else_=0)).label("not_scraped"),
        )
        .select_from(Company)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
    ).one()

    return CompanyCounts(
        total=row[0] or 0,
        unlabeled=row[1] or 0,
        possible=row[2] or 0,
        unknown=row[3] or 0,
        crap=row[4] or 0,
        scrape_done=row[5] or 0,
        scrape_failed=row[6] or 0,
        not_scraped=row[7] or 0,
    )


@router.get("/companies/export.csv")
def export_companies_csv(session: Session = Depends(get_session)) -> Response:
    latest_classification = _latest_classification_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    rows = session.exec(
        select(
            Company.raw_url,
            func.coalesce(latest_decision_text, "Unknown"),
        )
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .order_by(
            col(Upload.created_at).asc(),
            case((col(Company.source_row_number).is_(None), 1), else_=0).asc(),
            col(Company.source_row_number).asc(),
            col(Company.created_at).asc(),
        )
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["website", "classification"])
    for raw_url, classification in rows:
        writer.writerow([raw_url, classification])

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="prospects-{timestamp}.csv"',
        },
    )


@router.post("/companies/scrape-selected", response_model=CompanyScrapeResult)
def scrape_selected_companies(
    payload: CompanyScrapeRequest,
    session: Session = Depends(get_session),
) -> CompanyScrapeResult:
    requested_ids = list(dict.fromkeys(payload.company_ids))
    companies = list(session.exec(select(Company).where(col(Company.id).in_(requested_ids))))
    if not companies:
        return CompanyScrapeResult(
            requested_count=0,
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=requested_ids,
        )
    return _enqueue_scrapes_for_companies(session=session, companies=companies)


@router.post("/companies/scrape-all", response_model=CompanyScrapeResult)
def scrape_all_companies(session: Session = Depends(get_session)) -> CompanyScrapeResult:
    companies = list(session.exec(select(Company).order_by(col(Company.created_at).asc())))
    if not companies:
        return CompanyScrapeResult(
            requested_count=0,
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=[],
        )
    return _enqueue_scrapes_for_companies(session=session, companies=companies)


@router.post("/companies/delete", response_model=CompanyDeleteResult)
def delete_companies(
    payload: CompanyDeleteRequest,
    session: Session = Depends(get_session),
) -> CompanyDeleteResult:
    requested_ids = list(dict.fromkeys(payload.company_ids))
    companies = list(
        session.exec(select(Company).where(col(Company.id).in_(requested_ids)))
    )
    found_ids = {company.id for company in companies}
    missing_ids = [company_id for company_id in requested_ids if company_id not in found_ids]

    if companies:
        company_ids = [company.id for company in companies]
        upload_delete_counts: dict[UUID, int] = {}
        for company in companies:
            upload_delete_counts[company.upload_id] = upload_delete_counts.get(company.upload_id, 0) + 1

        crawl_job_ids = list(
            session.exec(
                select(CrawlJob.id).where(col(CrawlJob.company_id).in_(company_ids))
            )
        )
        analysis_job_ids = list(
            session.exec(
                select(AnalysisJob.id).where(col(AnalysisJob.company_id).in_(company_ids))
            )
        )

        if analysis_job_ids:
            session.exec(
                delete(ClassificationResult).where(col(ClassificationResult.analysis_job_id).in_(analysis_job_ids))
            )
            session.exec(
                delete(JobEvent).where(
                    (col(JobEvent.job_type) == "analysis") & col(JobEvent.job_id).in_(analysis_job_ids)
                )
            )
            session.exec(
                delete(AnalysisJob).where(col(AnalysisJob.id).in_(analysis_job_ids))
            )

        if crawl_job_ids:
            session.exec(
                delete(JobEvent).where(
                    (col(JobEvent.job_type) == "crawl") & col(JobEvent.job_id).in_(crawl_job_ids)
                )
            )
            session.exec(
                delete(CrawlArtifact).where(col(CrawlArtifact.crawl_job_id).in_(crawl_job_ids))
            )
            session.exec(
                delete(CrawlJob).where(col(CrawlJob.id).in_(crawl_job_ids))
            )

        session.exec(delete(Company).where(col(Company.id).in_(company_ids)))

        uploads = list(
            session.exec(select(Upload).where(col(Upload.id).in_(list(upload_delete_counts.keys()))))
        )
        for upload in uploads:
            decrement = upload_delete_counts.get(upload.id, 0)
            upload.valid_count = max(upload.valid_count - decrement, 0)
            session.add(upload)

        session.commit()

    deleted_ids = [company_id for company_id in requested_ids if company_id in found_ids]
    return CompanyDeleteResult(
        requested_count=len(requested_ids),
        deleted_count=len(deleted_ids),
        deleted_ids=deleted_ids,
        missing_ids=missing_ids,
    )
