from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, func, or_
from sqlmodel import Session, col, delete, select

from app.models import (
    AnalysisJob,
    ClassificationResult,
    Company,
    CompanyFeedback,
    Contact,
    ContactFetchJob,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    ScrapeJob,
    Upload,
)

# ---------------------------------------------------------------------------
# Filter constants
# ---------------------------------------------------------------------------

_ALLOWED_DECISION_FILTERS = frozenset({"all", "unlabeled", "possible", "unknown", "crap", "labeled"})
_SCRAPE_FILTER_ALIASES: dict[str, str] = {
    "all": "all",
    "done": "done",
    "failed": "soft",
    "none": "not-started",
    "pending": "not-started",
    "not-started": "not-started",
    "active": "in-progress",
    "in-progress": "in-progress",
    "cancelled": "cancelled",
    "permanent": "permanent",
    "permanent-fail": "permanent",
    "permanent-failures": "permanent",
    "soft": "soft",
    "soft-fail": "soft",
    "soft-failures": "soft",
}
_STATUS_FILTER_ALIASES: dict[str, str] = {
    "all": "all",
    "not-started": "not-started",
    "in-progress": "in-progress",
    "cancelled": "cancelled",
    "complete": "complete",
    "has-failures": "has-failures",
    "permanent": "permanent-failures",
    "permanent-failures": "permanent-failures",
    "soft": "soft-failures",
    "soft-failures": "soft-failures",
}
_ALLOWED_STAGE_FILTERS = frozenset({"all", "uploaded", "scraped", "classified", "contact_ready", "has_scrape"})
_COMPANY_SORT_FIELDS = frozenset({
    "domain", "created_at", "last_activity", "decision", "confidence",
    "scrape_status", "contact_count", "discovered_contact_count",
    "scrape_updated_at", "analysis_updated_at", "contact_fetch_updated_at",
})
_ACTIVITY_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Filters dataclass
# ---------------------------------------------------------------------------

@dataclass
class CompanyFilters:
    decision_filter: str = "all"
    scrape_filter: str = "all"
    stage_filter: str = "all"
    status_filter: str = "all"
    search: str | None = None
    letter: str | None = None
    letter_values: list[str] = field(default_factory=list)
    sort_by: str = "last_activity"
    sort_dir: str = "desc"
    upload_id: UUID | None = None
    include_total: bool = False


@dataclass(frozen=True)
class CompanyQueryContext:
    latest_classification: Any
    latest_scrape: Any
    latest_analysis: Any
    contact_counts: Any
    latest_contact_fetch: Any
    latest_decision_text: Any
    latest_confidence: Any
    effective_decision: Any
    decision_lower: Any
    last_activity: Any
    decision_rank: Any


def validate_company_filters(
    *,
    decision_filter: str = "all",
    scrape_filter: str = "all",
    stage_filter: str = "all",
    status_filter: str = "all",
    search: str | None = None,
    letter: str | None = None,
    letters: str | None = None,
    sort_by: str = "last_activity",
    sort_dir: str = "desc",
    upload_id: UUID | None = None,
    include_total: bool = False,
) -> CompanyFilters:
    ndf = decision_filter.strip().lower()
    if ndf not in _ALLOWED_DECISION_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid decision_filter.")

    normalized_scrape = scrape_filter.strip().lower()
    if normalized_scrape not in _SCRAPE_FILTER_ALIASES:
        raise HTTPException(status_code=422, detail="Invalid scrape_filter.")

    ngf = stage_filter.strip().lower()
    if ngf not in _ALLOWED_STAGE_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid stage_filter.")

    normalized_status = status_filter.strip().lower()
    if normalized_status not in _STATUS_FILTER_ALIASES:
        raise HTTPException(status_code=422, detail="Invalid status_filter.")

    nsb = sort_by.strip().lower()
    if nsb not in _COMPANY_SORT_FIELDS:
        raise HTTPException(status_code=422, detail="Invalid sort_by.")

    nsd = sort_dir.strip().lower()
    if nsd not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid sort_dir.")

    letter_values: list[str] = []
    if letters:
        letter_values = sorted({p.strip().lower() for p in letters.split(",") if p.strip()})
        letter_values = [lv for lv in letter_values if len(lv) == 1 and "a" <= lv <= "z"]

    return CompanyFilters(
        decision_filter=ndf,
        scrape_filter=_SCRAPE_FILTER_ALIASES[normalized_scrape],
        stage_filter=ngf,
        status_filter=_STATUS_FILTER_ALIASES[normalized_status],
        search=search.strip() if search else None,
        letter=letter.lower() if letter else None,
        letter_values=letter_values,
        sort_by=nsb,
        sort_dir=nsd,
        upload_id=upload_id,
        include_total=include_total,
    )


def validate_campaign_upload_scope(
    *,
    session: Session,
    campaign_id: UUID,
    upload_id: UUID | None,
) -> None:
    if upload_id is None:
        return
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="upload_id is not assigned to the selected campaign.")


# ---------------------------------------------------------------------------
# Subquery helpers
# ---------------------------------------------------------------------------

def latest_classification_subquery() -> Any:
    return (
        select(  # type: ignore[call-overload]
            col(AnalysisJob.company_id).label("company_id"),
            cast(col(ClassificationResult.predicted_label), String()).label("predicted_label"),
            col(ClassificationResult.confidence).label("confidence"),
        )
        .join(AnalysisJob, col(AnalysisJob.id) == col(ClassificationResult.analysis_job_id))
        .distinct(col(AnalysisJob.company_id))
        .order_by(col(AnalysisJob.company_id), col(ClassificationResult.created_at).desc())
        .subquery()
    )


def latest_scrape_subquery() -> Any:
    activity_ts = func.coalesce(col(ScrapeJob.updated_at), col(ScrapeJob.created_at))
    return (
        select(  # type: ignore[call-overload]
            col(ScrapeJob.normalized_url).label("normalized_url"),
            col(ScrapeJob.id).label("job_id"),
            col(ScrapeJob.state).label("state"),
            col(ScrapeJob.terminal_state).label("terminal_state"),
            col(ScrapeJob.last_error_code).label("last_error_code"),
            col(ScrapeJob.failure_reason).label("failure_reason"),
            activity_ts.label("scrape_updated_at"),
        )
        .distinct(col(ScrapeJob.normalized_url))
        .order_by(col(ScrapeJob.normalized_url), activity_ts.desc())
        .subquery()
    )


def _latest_analysis_subquery() -> Any:
    activity_ts = func.coalesce(col(AnalysisJob.updated_at), col(AnalysisJob.created_at))
    return (
        select(  # type: ignore[call-overload]
            col(AnalysisJob.company_id).label("company_id"),
            col(AnalysisJob.id).label("analysis_job_id"),
            col(AnalysisJob.run_id).label("run_id"),
            cast(col(AnalysisJob.state), String()).label("state"),
            col(AnalysisJob.terminal_state).label("terminal_state"),
            activity_ts.label("analysis_updated_at"),
        )
        .distinct(col(AnalysisJob.company_id))
        .order_by(col(AnalysisJob.company_id), activity_ts.desc())
        .subquery()
    )


def _contact_count_subquery() -> Any:
    return (
        select(
            col(Contact.company_id).label("company_id"),
            func.count().label("contact_count"),
            func.coalesce(
                func.sum(case((col(Contact.title_match).is_(True), 1), else_=0)),
                0,
            ).label("title_matched_count"),
        )
        .where(col(Contact.is_active).is_(True))
        .group_by(col(Contact.company_id))
        .subquery()
    )


def _latest_contact_fetch_subquery() -> Any:
    activity_ts = func.coalesce(col(ContactFetchJob.updated_at), col(ContactFetchJob.created_at))
    return (
        select(
            col(ContactFetchJob.company_id).label("company_id"),
            cast(col(ContactFetchJob.state), String()).label("state"),
            activity_ts.label("contact_fetch_updated_at"),
        )
        .distinct(col(ContactFetchJob.company_id))
        .order_by(col(ContactFetchJob.company_id), activity_ts.desc())
        .subquery()
    )


# ---------------------------------------------------------------------------
# Filter-apply helpers
# ---------------------------------------------------------------------------

def _apply_decision_filter(stmt: Any, decision_lower: Any, normalized_filter: str) -> Any:
    if normalized_filter == "unlabeled":
        return stmt.where(decision_lower == "")
    if normalized_filter == "labeled":
        return stmt.where(decision_lower.in_(["possible", "unknown", "crap"]))
    if normalized_filter in {"possible", "unknown", "crap"}:
        return stmt.where(decision_lower == normalized_filter)
    return stmt


def _apply_search_filter(stmt: Any, search: str | None) -> Any:
    if not search:
        return stmt
    return stmt.where(func.lower(col(Company.domain)).like(f"%{search.lower()}%"))


def _apply_scrape_filter(stmt: Any, latest_scrape: Any, normalized_scrape_filter: str) -> Any:
    if normalized_scrape_filter == "not-started":
        return stmt.where(latest_scrape.c.job_id.is_(None))
    if normalized_scrape_filter == "in-progress":
        return stmt.where(latest_scrape.c.state.in_(["created", "running"]))
    if normalized_scrape_filter == "done":
        return stmt.where(latest_scrape.c.state == "succeeded")
    if normalized_scrape_filter == "cancelled":
        return stmt.where(latest_scrape.c.state == "cancelled")
    if normalized_scrape_filter == "permanent":
        return stmt.where(latest_scrape.c.failure_reason == "site_unavailable")
    if normalized_scrape_filter == "soft":
        return stmt.where(latest_scrape.c.state.in_(["failed", "dead"]))
    return stmt


def _apply_stage_filter(stmt: Any, normalized_stage_filter: str) -> Any:
    if normalized_stage_filter == "all":
        return stmt
    if normalized_stage_filter == "has_scrape":
        return stmt.where(col(Company.pipeline_stage).in_(["scraped", "classified", "contact_ready"]))
    return stmt.where(col(Company.pipeline_stage) == normalized_stage_filter)


def _apply_pipeline_status_filter(
    stmt: Any,
    latest_scrape: Any,
    latest_analysis: Any,
    latest_contact_fetch: Any,
    latest_decision_text: Any,
    normalized_status_filter: str,
) -> Any:
    if normalized_status_filter == "all":
        return stmt
    scrape_status = func.coalesce(latest_scrape.c.state, "")
    analysis_status = func.coalesce(latest_analysis.c.state, "")
    contact_status = func.coalesce(latest_contact_fetch.c.state, "")
    decision_present = func.coalesce(col(CompanyFeedback.manual_label), latest_decision_text)

    if normalized_status_filter == "not-started":
        return stmt.where(latest_scrape.c.job_id.is_(None))
    if normalized_status_filter == "in-progress":
        return stmt.where(or_(
            scrape_status.in_(["created", "running"]),
            analysis_status.in_(["queued", "running"]),
            contact_status.in_(["queued", "running"]),
        ))
    if normalized_status_filter == "cancelled":
        return stmt.where(scrape_status == "cancelled")
    if normalized_status_filter == "complete":
        return stmt.where(and_(scrape_status == "succeeded", func.coalesce(decision_present, "") != ""))
    if normalized_status_filter == "has-failures":
        return stmt.where(or_(
            scrape_status.in_(["failed", "dead"]),
            analysis_status.in_(["failed", "dead"]),
            contact_status == "failed",
        ))
    if normalized_status_filter == "permanent-failures":
        return stmt.where(latest_scrape.c.failure_reason == "site_unavailable")
    if normalized_status_filter == "soft-failures":
        return stmt.where(or_(
            scrape_status.in_(["failed", "dead"]),
            analysis_status.in_(["failed", "dead"]),
            contact_status == "failed",
        ))
    return stmt


def _domain_first_letter_expr() -> Any:
    return func.lower(func.substr(Company.domain, 1, 1))


def _greatest_datetime(*parts: Any) -> Any:
    acc = parts[0]
    for p in parts[1:]:
        acc = case((acc >= p, acc), else_=p)
    return acc


# ---------------------------------------------------------------------------
# Public query builders
# ---------------------------------------------------------------------------

def build_company_query_context() -> CompanyQueryContext:
    latest_classification = latest_classification_subquery()
    latest_scrape = latest_scrape_subquery()
    latest_analysis = _latest_analysis_subquery()
    contact_counts = _contact_count_subquery()
    latest_contact_fetch = _latest_contact_fetch_subquery()

    latest_decision_text = latest_classification.c.predicted_label
    latest_confidence = latest_classification.c.confidence
    effective_decision = func.coalesce(col(CompanyFeedback.manual_label), latest_decision_text)
    decision_lower = func.lower(func.coalesce(effective_decision, ""))
    last_activity = _greatest_datetime(
        col(Company.created_at),
        func.coalesce(latest_scrape.c.scrape_updated_at, _ACTIVITY_EPOCH),
        func.coalesce(latest_analysis.c.analysis_updated_at, _ACTIVITY_EPOCH),
        func.coalesce(latest_contact_fetch.c.contact_fetch_updated_at, _ACTIVITY_EPOCH),
        func.coalesce(col(CompanyFeedback.updated_at), _ACTIVITY_EPOCH),
    )
    decision_rank = case(
        (decision_lower == "", 0),
        (decision_lower == "possible", 1),
        (decision_lower == "unknown", 2),
        (decision_lower == "crap", 3),
        else_=4,
    )
    return CompanyQueryContext(
        latest_classification=latest_classification,
        latest_scrape=latest_scrape,
        latest_analysis=latest_analysis,
        contact_counts=contact_counts,
        latest_contact_fetch=latest_contact_fetch,
        latest_decision_text=latest_decision_text,
        latest_confidence=latest_confidence,
        effective_decision=effective_decision,
        decision_lower=decision_lower,
        last_activity=last_activity,
        decision_rank=decision_rank,
    )


def build_company_base_stmt(campaign_id: UUID, ctx: CompanyQueryContext) -> Any:
    stmt = (
        select(  # type: ignore[call-overload]
            col(Company.id), col(Company.upload_id), col(Upload.filename),
            col(Company.raw_url), col(Company.normalized_url), col(Company.domain),
            col(Company.pipeline_stage), col(Company.created_at),
            ctx.latest_decision_text, ctx.latest_confidence,
            ctx.latest_scrape.c.job_id, ctx.latest_scrape.c.state, ctx.latest_scrape.c.terminal_state,
            ctx.latest_analysis.c.run_id, ctx.latest_analysis.c.state,
            ctx.latest_analysis.c.terminal_state, ctx.latest_analysis.c.analysis_job_id,
            col(CompanyFeedback.thumbs), col(CompanyFeedback.comment), col(CompanyFeedback.manual_label),
            ctx.latest_scrape.c.last_error_code,
            func.coalesce(ctx.contact_counts.c.contact_count, 0),
            func.coalesce(ctx.contact_counts.c.title_matched_count, 0),
            ctx.latest_contact_fetch.c.state,
            ctx.last_activity.label("last_activity"),
        )
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .outerjoin(ctx.latest_classification, ctx.latest_classification.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_scrape, ctx.latest_scrape.c.normalized_url == col(Company.normalized_url))
        .outerjoin(ctx.latest_analysis, ctx.latest_analysis.c.company_id == col(Company.id))
        .outerjoin(CompanyFeedback, col(CompanyFeedback.company_id) == col(Company.id))
        .outerjoin(ctx.contact_counts, ctx.contact_counts.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_contact_fetch, ctx.latest_contact_fetch.c.company_id == col(Company.id))
        .where(col(Upload.campaign_id) == campaign_id)
    )
    return stmt


def build_company_count_base_stmt(campaign_id: UUID, ctx: CompanyQueryContext) -> Any:
    return (
        select(func.count())
        .select_from(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .outerjoin(ctx.latest_classification, ctx.latest_classification.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_scrape, ctx.latest_scrape.c.normalized_url == col(Company.normalized_url))
        .outerjoin(ctx.latest_analysis, ctx.latest_analysis.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_contact_fetch, ctx.latest_contact_fetch.c.company_id == col(Company.id))
        .outerjoin(CompanyFeedback, col(CompanyFeedback.company_id) == col(Company.id))
        .where(col(Upload.campaign_id) == campaign_id)
    )


def apply_company_filters(stmt: Any, filters: CompanyFilters, ctx: CompanyQueryContext) -> Any:
    if filters.upload_id is not None:
        stmt = stmt.where(col(Company.upload_id) == filters.upload_id)

    stmt = _apply_decision_filter(stmt, ctx.decision_lower, filters.decision_filter)
    stmt = _apply_scrape_filter(stmt, ctx.latest_scrape, filters.scrape_filter)
    stmt = _apply_pipeline_status_filter(
        stmt,
        ctx.latest_scrape,
        ctx.latest_analysis,
        ctx.latest_contact_fetch,
        ctx.latest_decision_text,
        filters.status_filter,
    )
    stmt = _apply_stage_filter(stmt, filters.stage_filter)
    stmt = _apply_search_filter(stmt, filters.search)

    if filters.letter_values:
        stmt = stmt.where(_domain_first_letter_expr().in_(filters.letter_values))
    elif filters.letter is not None:
        stmt = stmt.where(_domain_first_letter_expr() == filters.letter)

    return stmt


def apply_company_sort(stmt: Any, filters: CompanyFilters, ctx: CompanyQueryContext) -> Any:
    sort_col_map = {
        "domain": col(Company.domain),
        "created_at": col(Company.created_at),
        "last_activity": ctx.last_activity,
        "decision": ctx.decision_rank,
        "confidence": ctx.latest_confidence,
        "scrape_status": ctx.latest_scrape.c.state,
        "contact_count": func.coalesce(ctx.contact_counts.c.contact_count, 0),
        "discovered_contact_count": func.coalesce(ctx.contact_counts.c.contact_count, 0),
        "scrape_updated_at": func.coalesce(ctx.latest_scrape.c.scrape_updated_at, _ACTIVITY_EPOCH),
        "analysis_updated_at": func.coalesce(ctx.latest_analysis.c.analysis_updated_at, _ACTIVITY_EPOCH),
        "contact_fetch_updated_at": func.coalesce(ctx.latest_contact_fetch.c.contact_fetch_updated_at, _ACTIVITY_EPOCH),
    }
    primary = sort_col_map[filters.sort_by]
    primary_expr = primary.desc() if filters.sort_dir == "desc" else primary.asc()
    return stmt.order_by(primary_expr, col(Company.domain).asc())


def build_company_list_stmt(campaign_id: UUID, filters: CompanyFilters) -> Any:
    ctx = build_company_query_context()
    stmt = build_company_base_stmt(campaign_id, ctx)
    stmt = apply_company_filters(stmt, filters, ctx)
    return apply_company_sort(stmt, filters, ctx)


def build_company_count_stmt(campaign_id: UUID, filters: CompanyFilters) -> Any:
    ctx = build_company_query_context()
    stmt = build_company_count_base_stmt(campaign_id, ctx)
    return apply_company_filters(stmt, filters, ctx)


# ---------------------------------------------------------------------------
# Cascade delete (called by background task only)
# ---------------------------------------------------------------------------

def cascade_delete_companies(
    session: Session,
    company_ids: list[UUID],
    campaign_id: UUID,
) -> None:
    """Full cascade delete for a list of companies. Must run in a background task."""
    if not company_ids:
        return

    # Verify all IDs belong to this campaign
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == campaign_id,
                col(Company.id).in_(company_ids),
            )
        )
    )
    if not companies:
        return

    confirmed_ids = [c.id for c in companies]

    # Collect dependent job IDs before deletion
    crawl_job_ids = list(
        session.exec(select(CrawlJob.id).where(col(CrawlJob.company_id).in_(confirmed_ids)))
    )
    analysis_job_ids = list(
        session.exec(select(AnalysisJob.id).where(col(AnalysisJob.company_id).in_(confirmed_ids)))
    )

    if analysis_job_ids:
        session.exec(delete(ClassificationResult).where(col(ClassificationResult.analysis_job_id).in_(analysis_job_ids)))
        session.exec(delete(JobEvent).where((col(JobEvent.job_type) == "analysis") & col(JobEvent.job_id).in_(analysis_job_ids)))
        session.exec(delete(AnalysisJob).where(col(AnalysisJob.id).in_(analysis_job_ids)))

    if crawl_job_ids:
        session.exec(delete(JobEvent).where((col(JobEvent.job_type) == "crawl") & col(JobEvent.job_id).in_(crawl_job_ids)))
        session.exec(delete(CrawlArtifact).where(col(CrawlArtifact.crawl_job_id).in_(crawl_job_ids)))
        session.exec(delete(CrawlJob).where(col(CrawlJob.id).in_(crawl_job_ids)))

    session.exec(delete(Contact).where(col(Contact.company_id).in_(confirmed_ids)))
    session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(confirmed_ids)))
    session.exec(delete(CompanyFeedback).where(col(CompanyFeedback.company_id).in_(confirmed_ids)))
    session.exec(delete(Company).where(col(Company.id).in_(confirmed_ids)))

    # Decrement upload.valid_count per upload
    upload_decrements: dict[UUID, int] = {}
    for company in companies:
        upload_decrements[company.upload_id] = upload_decrements.get(company.upload_id, 0) + 1

    for upload_id, decrement in upload_decrements.items():
        upload = session.get(Upload, upload_id)
        if upload is not None:
            upload.valid_count = max(upload.valid_count - decrement, 0)
            session.add(upload)

    session.commit()
