from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import String, case, cast, func
from sqlmodel import Session, col, delete, select

from app.api.schemas.analysis import FeedbackRead, FeedbackUpsert
from app.api.schemas.upload import (
    CompanyCounts,
    CompanyDeleteRequest,
    CompanyDeleteResult,
    CompanyIdsResult,
    CompanyList,
    CompanyListItem,
    CompanyRead,
    LetterCounts,
    UploadCompanyList,
)
from app.db.session import get_session
from app.models import (
    AnalysisJob,
    ClassificationResult,
    Company,
    CompanyFeedback,
    ContactFetchJob,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    ProspectContact,
    ScrapeJob,
    Upload,
)
from app.models.pipeline import utcnow

router = APIRouter(prefix="/v1", tags=["companies"])


# ---------------------------------------------------------------------------
# Shared subquery helpers
# ---------------------------------------------------------------------------

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


def _contact_count_subquery():
    return (
        select(
            ProspectContact.company_id.label("company_id"),
            func.count().label("contact_count"),
        )
        .group_by(ProspectContact.company_id)
        .subquery()
    )


def _latest_contact_fetch_subquery():
    return (
        select(
            ContactFetchJob.company_id.label("company_id"),
            cast(ContactFetchJob.state, String()).label("state"),
        )
        .distinct(ContactFetchJob.company_id)
        .order_by(ContactFetchJob.company_id, ContactFetchJob.created_at.desc())
        .subquery()
    )


_ALLOWED_DECISION_FILTERS = frozenset({"all", "unlabeled", "possible", "unknown", "crap"})
_ALLOWED_SCRAPE_FILTERS = frozenset({"all", "done", "failed", "none"})


def _validate_filters(decision_filter: str, scrape_filter: str) -> tuple[str, str]:
    ndf = decision_filter.strip().lower()
    nsf = scrape_filter.strip().lower()
    from fastapi import HTTPException as _HTTPException
    if ndf not in _ALLOWED_DECISION_FILTERS:
        raise _HTTPException(status_code=422, detail="Invalid decision_filter.")
    if nsf not in _ALLOWED_SCRAPE_FILTERS:
        raise _HTTPException(status_code=422, detail="Invalid scrape_filter.")
    return ndf, nsf


def _apply_decision_filter(stmt, decision_lower, normalized_filter: str):
    if normalized_filter == "unlabeled":
        return stmt.where(decision_lower == "")
    if normalized_filter in {"possible", "unknown", "crap"}:
        return stmt.where(decision_lower == normalized_filter)
    return stmt


def _apply_scrape_filter(stmt, latest_scrape, normalized_scrape_filter: str):
    if normalized_scrape_filter == "done":
        return stmt.where(latest_scrape.c.status == "completed")
    if normalized_scrape_filter == "failed":
        return stmt.where(latest_scrape.c.status.like("%failed%"))
    if normalized_scrape_filter == "none":
        return stmt.where(latest_scrape.c.job_id.is_(None))
    return stmt


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

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
            created_at=now,
            updated_at=now,
        )
        session.add(feedback)
    else:
        feedback.thumbs = payload.thumbs
        feedback.comment = payload.comment
        feedback.updated_at = now
        session.add(feedback)

    session.commit()
    session.refresh(feedback)
    return FeedbackRead(
        thumbs=feedback.thumbs,
        comment=feedback.comment,
        updated_at=feedback.updated_at,
    )


# ---------------------------------------------------------------------------
# Company listing, filtering, counts
# ---------------------------------------------------------------------------

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
    contact_counts = _contact_count_subquery()
    latest_contact_fetch = _latest_contact_fetch_subquery()
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
    normalized_filter, normalized_scrape_filter = _validate_filters(decision_filter, scrape_filter)
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
            func.coalesce(contact_counts.c.contact_count, 0),
            latest_contact_fetch.c.state,
        )
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .outerjoin(latest_analysis, latest_analysis.c.company_id == Company.id)
        .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
        .outerjoin(contact_counts, contact_counts.c.company_id == Company.id)
        .outerjoin(latest_contact_fetch, latest_contact_fetch.c.company_id == Company.id)
    )
    statement = _apply_decision_filter(statement, decision_lower, normalized_filter)
    statement = _apply_scrape_filter(statement, latest_scrape, normalized_scrape_filter)
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

    rows = list(session.exec(order.offset(offset).limit(limit + 1)))
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
        total_stmt = _apply_decision_filter(total_stmt, decision_lower, normalized_filter)
        total_stmt = _apply_scrape_filter(total_stmt, latest_scrape, normalized_scrape_filter)
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
            contact_count=int(row[18]) if row[18] is not None else 0,
            contact_fetch_status=str(row[19]) if row[19] is not None else None,
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

    normalized_filter, normalized_scrape_filter = _validate_filters(decision_filter, scrape_filter)
    statement = (
        select(Company.id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
    )
    statement = _apply_decision_filter(statement, decision_lower, normalized_filter)
    statement = _apply_scrape_filter(statement, latest_scrape, normalized_scrape_filter)
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
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    decision_lower = func.lower(func.coalesce(latest_decision_text, ""))

    normalized_filter, normalized_scrape_filter = _validate_filters(decision_filter, scrape_filter)
    letter_expr = func.lower(func.left(Company.domain, 1))
    stmt = (
        select(letter_expr.label("letter"), func.count().label("cnt"))
        .select_from(Company)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .where(letter_expr.between("a", "z"))
        .group_by(letter_expr)
    )
    stmt = _apply_decision_filter(stmt, decision_lower, normalized_filter)
    stmt = _apply_scrape_filter(stmt, latest_scrape, normalized_scrape_filter)

    rows = session.exec(stmt).all()
    counts: dict[str, int] = {chr(ord("a") + i): 0 for i in range(26)}
    for ltr, cnt in rows:
        if ltr in counts:
            counts[ltr] = int(cnt)
    return LetterCounts(counts=counts)


@router.get("/companies/counts", response_model=CompanyCounts)
def get_company_counts(session: Session = Depends(get_session)) -> CompanyCounts:
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


# ---------------------------------------------------------------------------
# Export + delete
# ---------------------------------------------------------------------------

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

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="prospects-{timestamp}.csv"'},
    )


@router.post("/companies/delete", response_model=CompanyDeleteResult)
def delete_companies(
    payload: CompanyDeleteRequest,
    session: Session = Depends(get_session),
) -> CompanyDeleteResult:
    requested_ids = list(dict.fromkeys(payload.company_ids))
    companies = list(session.exec(select(Company).where(col(Company.id).in_(requested_ids))))
    found_ids = {company.id for company in companies}
    missing_ids = [company_id for company_id in requested_ids if company_id not in found_ids]

    if companies:
        company_ids = [company.id for company in companies]
        upload_delete_counts: dict[UUID, int] = {}
        for company in companies:
            upload_delete_counts[company.upload_id] = upload_delete_counts.get(company.upload_id, 0) + 1

        crawl_job_ids = list(
            session.exec(select(CrawlJob.id).where(col(CrawlJob.company_id).in_(company_ids)))
        )
        analysis_job_ids = list(
            session.exec(select(AnalysisJob.id).where(col(AnalysisJob.company_id).in_(company_ids)))
        )

        if analysis_job_ids:
            session.exec(delete(ClassificationResult).where(col(ClassificationResult.analysis_job_id).in_(analysis_job_ids)))
            session.exec(delete(JobEvent).where((col(JobEvent.job_type) == "analysis") & col(JobEvent.job_id).in_(analysis_job_ids)))
            session.exec(delete(AnalysisJob).where(col(AnalysisJob.id).in_(analysis_job_ids)))

        if crawl_job_ids:
            session.exec(delete(JobEvent).where((col(JobEvent.job_type) == "crawl") & col(JobEvent.job_id).in_(crawl_job_ids)))
            session.exec(delete(CrawlArtifact).where(col(CrawlArtifact.crawl_job_id).in_(crawl_job_ids)))
            session.exec(delete(CrawlJob).where(col(CrawlJob.id).in_(crawl_job_ids)))

        session.exec(delete(Company).where(col(Company.id).in_(company_ids)))

        uploads = list(session.exec(select(Upload).where(col(Upload.id).in_(list(upload_delete_counts.keys())))))
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
