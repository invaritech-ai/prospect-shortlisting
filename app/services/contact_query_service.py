from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.api.schemas.contacts import ContactVerifyRequest, MatchGapFilter
from app.models import Company, Contact, Upload
from app.models.pipeline import utcnow

_ALLOWED_CONTACT_STAGE_FILTERS = frozenset({"all", "fetched", "email_revealed", "campaign_ready"})
_ALLOWED_MATCH_GAP_FILTERS = frozenset({"all", "contacts_no_match", "matched_no_email", "ready_candidates"})


def validate_contact_stage_filter(stage_filter: str) -> str:
    if not isinstance(stage_filter, str):
        stage_filter = getattr(stage_filter, "default", "all")
    normalized = (stage_filter or "all").strip().lower()
    if normalized not in _ALLOWED_CONTACT_STAGE_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid stage_filter.")
    return normalized


def validate_match_gap_filter(value: str) -> MatchGapFilter:
    if not isinstance(value, str):
        value = getattr(value, "default", "all")
    normalized = (value or "all").strip().lower()
    if normalized not in _ALLOWED_MATCH_GAP_FILTERS:
        raise HTTPException(status_code=422, detail="Invalid match_gap_filter.")
    return normalized  # type: ignore[return-value]


def validate_campaign_upload_scope(
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


def campaign_upload_scope(campaign_id: UUID):
    return col(Company.upload_id).in_(select(Upload.id).where(col(Upload.campaign_id) == campaign_id))


def contact_emails_map(session: Session, contacts: list[Contact]) -> dict[UUID, list[str]]:  # noqa: ARG001
    """Return a map of contact_id → list of emails. Email lives directly on Contact."""
    out: dict[UUID, list[str]] = {}
    for contact in contacts:
        if not contact.id:
            continue
        emails: list[str] = []
        if contact.email and contact.email.strip():
            emails.append(contact.email.strip())
        out[contact.id] = emails
    return out


def verification_eligible_condition():
    return (
        col(Contact.title_match).is_(True),
        col(Contact.email).is_not(None),
        col(Contact.verification_status) == "unverified",
    )


def domain_first_letter_expr():
    return func.lower(func.substr(Company.domain, 1, 1))


def parse_letters(letters: str | None) -> list[str]:
    if not isinstance(letters, str):
        letters = getattr(letters, "default", None)
    if not letters:
        return []
    normalized = sorted({part.strip().lower() for part in letters.split(",") if part.strip()})
    return [ltr for ltr in normalized if len(ltr) == 1 and "a" <= ltr <= "z"]


def apply_contact_filters(
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
    normalized_stage = validate_contact_stage_filter(stage_filter)
    if company_id:
        stmt = stmt.where(col(Contact.company_id) == company_id)
    if company_ids:
        stmt = stmt.where(col(Contact.company_id).in_(company_ids))
    if title_match is not None:
        stmt = stmt.where(col(Contact.title_match) == title_match)
    if verification_status:
        stmt = stmt.where(col(Contact.verification_status) == verification_status.strip().lower())
    if normalized_stage != "all":
        stmt = stmt.where(col(Contact.pipeline_stage) == normalized_stage)
    if stale_days is not None and stale_days > 0:
        cutoff = utcnow() - timedelta(days=stale_days)
        stmt = stmt.where(
            col(Contact.verification_status) != "unverified",
            col(Contact.pipeline_stage).in_(["email_revealed", "campaign_ready"]),
            col(Contact.updated_at) <= cutoff,
        )
    if letters:
        stmt = stmt.where(domain_first_letter_expr().in_(letters))
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Contact.first_name).like(term),
                func.lower(Contact.last_name).like(term),
                func.lower(Contact.email).like(term),
                func.lower(Contact.title).like(term),
                func.lower(Company.domain).like(term),
            )
        )
    return stmt


def select_verification_contact_ids(session: Session, payload: ContactVerifyRequest) -> list[UUID]:
    explicit_ids = list(dict.fromkeys(payload.contact_ids or []))
    campaign_scope = campaign_upload_scope(payload.campaign_id)
    if explicit_ids:
        rows = list(
            session.exec(
                select(Contact.id)
                .join(Company, col(Company.id) == col(Contact.company_id))
                .where(
                    col(Contact.id).in_(explicit_ids),
                    campaign_scope,
                    *verification_eligible_condition(),
                )
            )
        )
        return rows

    company_ids = list(dict.fromkeys(payload.company_ids or []))
    stmt = select(Contact.id).join(Company, col(Company.id) == col(Contact.company_id))
    stmt = apply_contact_filters(
        stmt,
        title_match=payload.title_match,
        verification_status=payload.verification_status,
        search=payload.search,
        stage_filter=payload.stage_filter or "all",
        company_ids=company_ids or None,
    )
    stmt = stmt.where(campaign_scope, *verification_eligible_condition())
    return list(session.exec(stmt))
