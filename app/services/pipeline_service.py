from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import AnalysisJob, ClassificationResult, Company, CompanyFeedback, ScrapeJob
from app.models.pipeline import CompanyPipelineStage


def normalize_label(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    return value or None


def effective_company_label(session: Session, company_id: UUID) -> str | None:
    feedback = session.get(CompanyFeedback, company_id)
    if feedback and feedback.manual_label:
        return normalize_label(feedback.manual_label)

    row = session.exec(
        select(ClassificationResult.predicted_label)
        .join(AnalysisJob, col(AnalysisJob.id) == col(ClassificationResult.analysis_job_id))
        .where(
            col(AnalysisJob.company_id) == company_id,
            col(ClassificationResult.is_stale).is_(False),
        )
        .order_by(col(ClassificationResult.created_at).desc())
    ).first()
    return normalize_label(str(row) if row is not None else None)


def latest_usable_scrape(session: Session, normalized_url: str) -> ScrapeJob | None:
    if not normalized_url:
        return None
    return session.exec(
        select(ScrapeJob)
        .where(
            col(ScrapeJob.normalized_url) == normalized_url,
            col(ScrapeJob.state) == "succeeded",
            col(ScrapeJob.markdown_pages_count) > 0,
        )
        .order_by(col(ScrapeJob.created_at).desc())
    ).first()


def company_stage_for_company(session: Session, company: Company) -> CompanyPipelineStage:
    if latest_usable_scrape(session, company.normalized_url) is None:
        return CompanyPipelineStage.UPLOADED

    effective_label = effective_company_label(session, company.id)
    if effective_label is None:
        return CompanyPipelineStage.SCRAPED
    if effective_label == "possible":
        return CompanyPipelineStage.CONTACT_READY
    return CompanyPipelineStage.CLASSIFIED


def _coerce_ids(items: Iterable[UUID] | None) -> list[UUID]:
    if items is None:
        return []
    return list(dict.fromkeys(items))


def recompute_company_stages(
    session: Session,
    *,
    company_ids: Iterable[UUID] | None = None,
    normalized_urls: Iterable[str] | None = None,
) -> int:
    statement = select(Company)
    ids = _coerce_ids(company_ids)
    urls = list(dict.fromkeys([u for u in (normalized_urls or []) if u]))
    if ids:
        statement = statement.where(col(Company.id).in_(ids))
    elif urls:
        statement = statement.where(col(Company.normalized_url).in_(urls))

    companies = list(session.exec(statement))
    changed = 0
    for company in companies:
        next_stage = company_stage_for_company(session, company)
        if company.pipeline_stage != next_stage:
            company.pipeline_stage = next_stage
            session.add(company)
            changed += 1
    return changed
