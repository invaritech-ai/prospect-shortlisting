from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import AnalysisJob, ClassificationResult, Company, CompanyFeedback, ProspectContact, ScrapeJob
from app.models.pipeline import CompanyPipelineStage, ContactPipelineStage


def normalize_label(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    return value or None


def normalize_verification_status(raw: str | None) -> str:
    value = normalize_label(raw) or "unverified"
    if value in {"catch-all", "catch_all"}:
        return "catch_all"
    if value in {"not_valid", "not valid"}:
        return "invalid"
    return value


def effective_company_label(session: Session, company_id: UUID) -> str | None:
    feedback = session.get(CompanyFeedback, company_id)
    if feedback and feedback.manual_label:
        return normalize_label(feedback.manual_label)

    row = session.exec(
        select(ClassificationResult.predicted_label)
        .join(AnalysisJob, AnalysisJob.id == ClassificationResult.analysis_job_id)
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
            col(ScrapeJob.status) == "completed",
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


def contact_stage_for_contact(contact: ProspectContact) -> ContactPipelineStage:
    verification_status = normalize_verification_status(contact.verification_status)
    if (
        contact.title_match
        and bool((contact.email or "").strip())
        and verification_status == "valid"
    ):
        return ContactPipelineStage.CAMPAIGN_READY
    if verification_status != "unverified":
        return ContactPipelineStage.VERIFIED
    return ContactPipelineStage.FETCHED


def recompute_contact_stages(
    session: Session,
    *,
    contact_ids: Iterable[UUID] | None = None,
    company_ids: Iterable[UUID] | None = None,
) -> int:
    statement = select(ProspectContact)
    ids = _coerce_ids(contact_ids)
    owner_ids = _coerce_ids(company_ids)
    if ids:
        statement = statement.where(col(ProspectContact.id).in_(ids))
    elif owner_ids:
        statement = statement.where(col(ProspectContact.company_id).in_(owner_ids))

    contacts = list(session.exec(statement))
    changed = 0
    for contact in contacts:
        next_stage = contact_stage_for_contact(contact)
        next_status = normalize_verification_status(contact.verification_status)
        if contact.verification_status != next_status:
            contact.verification_status = next_status
            session.add(contact)
            changed += 1
        if contact.pipeline_stage != next_stage:
            contact.pipeline_stage = next_stage
            session.add(contact)
            changed += 1
    return changed


def recompute_all_stages(session: Session) -> tuple[int, int]:
    company_changed = recompute_company_stages(session)
    contact_changed = recompute_contact_stages(session)
    return company_changed, contact_changed
