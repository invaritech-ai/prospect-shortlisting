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
from app.models.pipeline import CompanyPipelineStage
from app.services.pipeline_service import recompute_company_stages

router = APIRouter(prefix="/v1", tags=["companies"])


def _domain_first_letter_expr():
    return func.lower(func.substr(Company.domain, 1, 1))


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
    activity_ts = func.coalesce(ScrapeJob.updated_at, ScrapeJob.created_at)
    return (
        select(
            ScrapeJob.normalized_url.label("normalized_url"),
            ScrapeJob.id.label("job_id"),
            ScrapeJob.status.label("status"),
            ScrapeJob.terminal_state.label("terminal_state"),
            ScrapeJob.last_error_code.label("last_error_code"),
            activity_ts.label("scrape_updated_at"),
        )
        .distinct(ScrapeJob.normalized_url)
        .order_by(ScrapeJob.normalized_url, activity_ts.desc())
        .subquery()
    )


def _latest_analysis_subquery():
    activity_ts = func.coalesce(AnalysisJob.updated_at, AnalysisJob.created_at)
    return (
        select(
            AnalysisJob.company_id.label("company_id"),
            AnalysisJob.id.label("analysis_job_id"),
            AnalysisJob.run_id.label("run_id"),
            cast(AnalysisJob.state, String()).label("state"),
            AnalysisJob.terminal_state.label("terminal_state"),
            activity_ts.label("analysis_updated_at"),
        )
        .distinct(AnalysisJob.company_id)
        .order_by(AnalysisJob.company_id, activity_ts.desc())
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
    activity_ts = func.coalesce(ContactFetchJob.updated_at, ContactFetchJob.created_at)
    return (
        select(
            ContactFetchJob.company_id.label("company_id"),
            cast(ContactFetchJob.state, String()).label("state"),
            activity_ts.label("contact_fetch_updated_at"),
        )
        .distinct(ContactFetchJob.company_id)
        .order_by(ContactFetchJob.company_id, activity_ts.desc())
        .subquery()
    )


_ALLOWED_DECISION_FILTERS = frozenset({"all", "unlabeled", "possible", "unknown", "crap", "labeled"})
_ALLOWED_SCRAPE_FILTERS = frozenset({"all", "done", "failed", "none"})
_ALLOWED_STAGE_FILTERS = frozenset({"all", "uploaded", "scraped", "classified", "contact_ready", "has_scrape"})


def _validate_filters(decision_filter: str, scrape_filter: str, stage_filter: str) -> tuple[str, str, str]:
    if not isinstance(decision_filter, str):
        decision_filter = getattr(decision_filter, "default", "all")
    if not isinstance(scrape_filter, str):
        scrape_filter = getattr(scrape_filter, "default", "all")
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")
    ndf = decision_filter.strip().lower()
    nsf = scrape_filter.strip().lower()
    ngf = stage_filter.strip().lower()
    from fastapi import HTTPException as _HTTPException
    if ndf not in _ALLOWED_DECISION_FILTERS:
        raise _HTTPException(status_code=422, detail="Invalid decision_filter.")
    if nsf not in _ALLOWED_SCRAPE_FILTERS:
        raise _HTTPException(status_code=422, detail="Invalid scrape_filter.")
    if ngf not in _ALLOWED_STAGE_FILTERS:
        raise _HTTPException(status_code=422, detail="Invalid stage_filter.")
    return ndf, nsf, ngf


def _apply_decision_filter(stmt, decision_lower, normalized_filter: str):
    if normalized_filter == "unlabeled":
        return stmt.where(decision_lower == "")
    if normalized_filter == "labeled":
        return stmt.where(decision_lower.in_(["possible", "unknown", "crap"]))
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


def _apply_stage_filter(stmt, normalized_stage_filter: str):
    if normalized_stage_filter == "all":
        return stmt
    if normalized_stage_filter == "has_scrape":
        return stmt.where(col(Company.pipeline_stage).in_(["scraped", "classified", "contact_ready"]))
    return stmt.where(col(Company.pipeline_stage) == normalized_stage_filter)


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


# ---------------------------------------------------------------------------
# Company listing, filtering, counts
# ---------------------------------------------------------------------------

_COMPANY_SORT_FIELDS = frozenset(
    {
        "domain",
        "created_at",
        "last_activity",
        "decision",
        "confidence",
        "scrape_status",
        "contact_count",
    }
)

_ACTIVITY_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _greatest_datetime(*parts):
    """Row-wise max over coalesced datetimes (SQLite has no GREATEST; PG does)."""
    acc = parts[0]
    for p in parts[1:]:
        acc = case((acc >= p, acc), else_=p)
    return acc


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
    sort_by: str = Query(default="last_activity"),
    sort_dir: str = Query(default="desc"),
    upload_id: UUID | None = Query(default=None),
) -> CompanyList:
    if not isinstance(limit, int):
        limit = int(getattr(limit, "default", 25))
    if not isinstance(offset, int):
        offset = int(getattr(offset, "default", 0))
    if not isinstance(include_total, bool):
        include_total = bool(getattr(include_total, "default", False))
    if not isinstance(letter, str):
        letter = getattr(letter, "default", None)
    if not isinstance(letters, str):
        letters = getattr(letters, "default", None)
    if not isinstance(sort_by, str):
        sort_by = getattr(sort_by, "default", "last_activity")
    if not isinstance(sort_dir, str):
        sort_dir = getattr(sort_dir, "default", "desc")
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    letter_values: list[str] = []
    if letters:
        letter_values = sorted({part.strip().lower() for part in letters.split(",") if part.strip()})
        letter_values = [ltr for ltr in letter_values if len(ltr) == 1 and "a" <= ltr <= "z"]

    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    latest_analysis = _latest_analysis_subquery()
    contact_counts = _contact_count_subquery()
    latest_contact_fetch = _latest_contact_fetch_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    latest_confidence = latest_classification.c.confidence
    last_activity_expr = _greatest_datetime(
        col(Company.created_at),
        func.coalesce(latest_scrape.c.scrape_updated_at, _ACTIVITY_EPOCH),
        func.coalesce(latest_analysis.c.analysis_updated_at, _ACTIVITY_EPOCH),
        func.coalesce(latest_contact_fetch.c.contact_fetch_updated_at, _ACTIVITY_EPOCH),
        func.coalesce(CompanyFeedback.updated_at, _ACTIVITY_EPOCH),
    )
    # manual_label overrides LLM decision for filtering and ordering
    effective_decision = func.coalesce(CompanyFeedback.manual_label, latest_decision_text)
    decision_lower = func.lower(func.coalesce(effective_decision, ""))
    decision_rank = case(
        (decision_lower == "", 0),
        (decision_lower == "possible", 1),
        (decision_lower == "unknown", 2),
        (decision_lower == "crap", 3),
        else_=4,
    )
    normalized_filter, normalized_scrape_filter, normalized_stage_filter = _validate_filters(
        decision_filter, scrape_filter, stage_filter
    )
    statement = (
        select(
            Company.id,
            Company.upload_id,
            Upload.filename,
            Company.raw_url,
            Company.normalized_url,
            Company.domain,
            Company.pipeline_stage,
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
            CompanyFeedback.manual_label,
            latest_scrape.c.last_error_code,
            func.coalesce(contact_counts.c.contact_count, 0),
            latest_contact_fetch.c.state,
            last_activity_expr.label("last_activity"),
        )
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .outerjoin(latest_analysis, latest_analysis.c.company_id == Company.id)
        .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
        .outerjoin(contact_counts, contact_counts.c.company_id == Company.id)
        .outerjoin(latest_contact_fetch, latest_contact_fetch.c.company_id == Company.id)
    )
    statement = statement.where(col(Upload.campaign_id) == campaign_id)
    if upload_id is not None:
        statement = statement.where(col(Company.upload_id) == upload_id)
    statement = _apply_decision_filter(statement, decision_lower, normalized_filter)
    statement = _apply_scrape_filter(statement, latest_scrape, normalized_scrape_filter)
    statement = _apply_stage_filter(statement, normalized_stage_filter)
    if letter_values:
        statement = statement.where(_domain_first_letter_expr().in_(letter_values))
    elif letter is not None:
        statement = statement.where(_domain_first_letter_expr() == letter.lower())

    # Build sort expression
    if sort_by not in _COMPANY_SORT_FIELDS:
        raise HTTPException(status_code=422, detail="Invalid sort_by.")
    _sort_by = sort_by
    _sort_dir_normalized = sort_dir.strip().lower()
    if _sort_dir_normalized not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid sort_dir.")
    _sort_dir = _sort_dir_normalized

    _sort_col_map = {
        "domain": col(Company.domain),
        "created_at": col(Company.created_at),
        "last_activity": last_activity_expr,
        "decision": decision_rank,
        "confidence": latest_confidence,
        "scrape_status": latest_scrape.c.status,
        "contact_count": func.coalesce(contact_counts.c.contact_count, 0),
    }
    _primary = _sort_col_map[_sort_by]
    _primary_expr = _primary.desc() if _sort_dir == "desc" else _primary.asc()
    order = statement.order_by(_primary_expr, col(Company.domain).asc())

    rows = list(session.exec(order.offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    total: int | None = None
    if include_total:
        total_stmt = (
            select(func.count())
            .select_from(Company)
            .join(Upload, Upload.id == Company.upload_id)
            .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
            .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
            .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
        )
        total_stmt = total_stmt.where(col(Upload.campaign_id) == campaign_id)
        if upload_id is not None:
            total_stmt = total_stmt.where(col(Company.upload_id) == upload_id)
        total_stmt = _apply_decision_filter(total_stmt, decision_lower, normalized_filter)
        total_stmt = _apply_scrape_filter(total_stmt, latest_scrape, normalized_scrape_filter)
        total_stmt = _apply_stage_filter(total_stmt, normalized_stage_filter)
        if letter_values:
            total_stmt = total_stmt.where(_domain_first_letter_expr().in_(letter_values))
        elif letter is not None:
            total_stmt = total_stmt.where(_domain_first_letter_expr() == letter.lower())
        total = session.exec(total_stmt).one()
    items = [
        CompanyListItem(
            id=row[0],
            upload_id=row[1],
            upload_filename=row[2],
            raw_url=row[3],
            normalized_url=row[4],
            domain=row[5],
            pipeline_stage=str(row[6]),
            created_at=row[7],
            latest_decision=str(row[8]).lower() if row[8] is not None else None,
            latest_confidence=row[9],
            latest_scrape_job_id=row[10],
            latest_scrape_status=str(row[11]) if row[11] is not None else None,
            latest_scrape_terminal=row[12],
            latest_analysis_run_id=row[13],
            latest_analysis_status=str(row[14]) if row[14] is not None else None,
            latest_analysis_terminal=row[15],
            latest_analysis_job_id=row[16],
            feedback_thumbs=str(row[17]) if row[17] is not None else None,
            feedback_comment=str(row[18]) if row[18] is not None else None,
            feedback_manual_label=str(row[19]) if row[19] is not None else None,
            latest_scrape_error_code=str(row[20]) if row[20] is not None else None,
            contact_count=int(row[21]) if row[21] is not None else 0,
            contact_fetch_status=str(row[22]) if row[22] is not None else None,
            last_activity=row[23],
        )
        for row in page_rows
    ]
    return CompanyList(total=total, has_more=has_more, limit=limit, offset=offset, items=items)


@router.get("/companies/ids", response_model=CompanyIdsResult)
def list_company_ids(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    letter: str | None = Query(default=None, min_length=1, max_length=1),
    letters: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    upload_id: UUID | None = Query(default=None),
) -> CompanyIdsResult:
    if not isinstance(letter, str):
        letter = getattr(letter, "default", None)
    if not isinstance(letters, str):
        letters = getattr(letters, "default", None)
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    letter_values: list[str] = []
    if letters:
        letter_values = sorted({part.strip().lower() for part in letters.split(",") if part.strip()})
        letter_values = [ltr for ltr in letter_values if len(ltr) == 1 and "a" <= ltr <= "z"]

    """Return all company IDs matching the given filters (no pagination) for bulk selection."""
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    effective_decision = func.coalesce(CompanyFeedback.manual_label, latest_decision_text)
    decision_lower = func.lower(func.coalesce(effective_decision, ""))
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    normalized_filter, normalized_scrape_filter, normalized_stage_filter = _validate_filters(
        decision_filter, scrape_filter, stage_filter
    )
    statement = (
        select(Company.id)
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
    )
    statement = statement.where(col(Upload.campaign_id) == campaign_id)
    if upload_id is not None:
        statement = statement.where(col(Company.upload_id) == upload_id)
    statement = _apply_decision_filter(statement, decision_lower, normalized_filter)
    statement = _apply_scrape_filter(statement, latest_scrape, normalized_scrape_filter)
    statement = _apply_stage_filter(statement, normalized_stage_filter)
    if letter_values:
        statement = statement.where(_domain_first_letter_expr().in_(letter_values))
    elif letter is not None:
        statement = statement.where(_domain_first_letter_expr() == letter.lower())

    ids = list(session.exec(statement))
    return CompanyIdsResult(ids=ids, total=len(ids))


@router.get("/companies/letter-counts", response_model=LetterCounts)
def get_letter_counts(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    stage_filter: str = Query(default="all"),
    upload_id: UUID | None = Query(default=None),
) -> LetterCounts:
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    effective_decision = func.coalesce(CompanyFeedback.manual_label, latest_decision_text)
    decision_lower = func.lower(func.coalesce(effective_decision, ""))
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    normalized_filter, normalized_scrape_filter, normalized_stage_filter = _validate_filters(
        decision_filter, scrape_filter, stage_filter
    )
    letter_expr = _domain_first_letter_expr()
    stmt = (
        select(letter_expr.label("letter"), func.count().label("cnt"))
        .select_from(Company)
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
        .where(letter_expr.between("a", "z"))
        .group_by(letter_expr)
    )
    stmt = stmt.where(col(Upload.campaign_id) == campaign_id)
    if upload_id is not None:
        stmt = stmt.where(col(Company.upload_id) == upload_id)
    stmt = _apply_decision_filter(stmt, decision_lower, normalized_filter)
    stmt = _apply_scrape_filter(stmt, latest_scrape, normalized_scrape_filter)
    stmt = _apply_stage_filter(stmt, normalized_stage_filter)

    rows = session.exec(stmt).all()
    counts: dict[str, int] = {chr(ord("a") + i): 0 for i in range(26)}
    for ltr, cnt in rows:
        if ltr in counts:
            counts[ltr] = int(cnt)
    return LetterCounts(counts=counts)


@router.get("/companies/counts", response_model=CompanyCounts)
def get_company_counts(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
) -> CompanyCounts:
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)
    latest_classification = _latest_classification_subquery()
    latest_scrape = _latest_scrape_subquery()
    effective_decision = func.coalesce(CompanyFeedback.manual_label, latest_classification.c.predicted_label)
    decision_lower = func.lower(func.coalesce(effective_decision, ""))
    scrape_status = latest_scrape.c.status

    counts_stmt = (
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
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == Company.normalized_url)
        .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
    )
    counts_stmt = counts_stmt.where(col(Upload.campaign_id) == campaign_id)
    if upload_id is not None:
        counts_stmt = counts_stmt.where(col(Company.upload_id) == upload_id)
    row = session.exec(counts_stmt).one()

    stage_stmt = (
        select(
        func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.UPLOADED, 1), else_=0)).label("uploaded"),
        func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.SCRAPED, 1), else_=0)).label("scraped"),
        func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.CLASSIFIED, 1), else_=0)).label("classified"),
        func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.CONTACT_READY, 1), else_=0)).label("contact_ready"),
    )
        .select_from(Company)
        .join(Upload, Upload.id == Company.upload_id)
        .where(col(Upload.campaign_id) == campaign_id)
    )
    if upload_id is not None:
        stage_stmt = stage_stmt.where(col(Company.upload_id) == upload_id)
    stage_row = session.exec(stage_stmt).one()

    return CompanyCounts(
        total=row[0] or 0,
        uploaded=stage_row.uploaded or 0,
        scraped=stage_row.scraped or 0,
        classified=stage_row.classified or 0,
        contact_ready=stage_row.contact_ready or 0,
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
def export_companies_csv(
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
) -> Response:
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)
    latest_classification = _latest_classification_subquery()
    latest_decision_text = latest_classification.c.predicted_label
    effective_decision = func.coalesce(CompanyFeedback.manual_label, latest_decision_text)
    rows_stmt = (
        select(
            Company.raw_url,
            func.coalesce(effective_decision, "Unknown"),
        )
        .join(Upload, Upload.id == Company.upload_id)
        .outerjoin(latest_classification, latest_classification.c.company_id == Company.id)
        .outerjoin(CompanyFeedback, CompanyFeedback.company_id == Company.id)
        .where(col(Upload.campaign_id) == campaign_id)
        .order_by(
            col(Upload.created_at).asc(),
            case((col(Company.source_row_number).is_(None), 1), else_=0).asc(),
            col(Company.source_row_number).asc(),
            col(Company.created_at).asc(),
        )
    )
    if upload_id is not None:
        rows_stmt = rows_stmt.where(col(Company.upload_id) == upload_id)
    rows = session.exec(rows_stmt).all()

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
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == payload.campaign_id,
                col(Company.id).in_(requested_ids),
            )
        )
    )
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

        # Clean up contacts and feedback before deleting companies.
        session.exec(delete(ProspectContact).where(col(ProspectContact.company_id).in_(company_ids)))
        session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(company_ids)))
        session.exec(delete(CompanyFeedback).where(col(CompanyFeedback.company_id).in_(company_ids)))

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
