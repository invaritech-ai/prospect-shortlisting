from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.contacts import Contact


_SPACES_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ContactReconciliationMatch:
    contact: Contact | None
    method: str = ""
    ambiguous: bool = False


def normalize_contact_token(value: str | None) -> str:
    return _SPACES_RE.sub(" ", str(value or "").strip()).lower()


def find_reconciled_contact(
    *,
    session: Session,
    campaign_id: UUID,
    domain_id: UUID,
    provider: str,
    provider_person_id: str,
    first_name: str,
    last_name: str,
    title: str | None,
    linkedin_url: str | None,
) -> ContactReconciliationMatch:
    provider_person_id = str(provider_person_id or "").strip()
    provider_column = Contact.apollo_person_id if provider == "apollo" else Contact.snov_person_id
    if provider_person_id:
        by_provider = session.exec(
            select(Contact)
            .where(
                col(Contact.campaign_id) == campaign_id,
                col(Contact.domain_id) == domain_id,
                provider_column == provider_person_id,
            )
            .limit(1)
        ).first()
        if by_provider:
            return ContactReconciliationMatch(contact=by_provider, method="provider_id")

    linkedin = str(linkedin_url or "").strip()
    if linkedin:
        by_linkedin = session.exec(
            select(Contact)
            .where(
                col(Contact.campaign_id) == campaign_id,
                col(Contact.domain_id) == domain_id,
                func.lower(Contact.linkedin_url) == linkedin.lower(),
            )
            .limit(1)
        ).first()
        if by_linkedin:
            return ContactReconciliationMatch(contact=by_linkedin, method="linkedin_url")

    first = normalize_contact_token(first_name)
    last = normalize_contact_token(last_name)
    if not first or not last:
        return ContactReconciliationMatch(contact=None)

    name_matches = session.exec(
        select(Contact).where(
            col(Contact.campaign_id) == campaign_id,
            col(Contact.domain_id) == domain_id,
            func.lower(Contact.first_name) == first,
            func.lower(Contact.last_name) == last,
        )
    ).all()
    if not name_matches:
        return ContactReconciliationMatch(contact=None)

    normalized_title = normalize_contact_token(title)
    if normalized_title:
        title_matches = [contact for contact in name_matches if normalize_contact_token(contact.title) == normalized_title]
        if len(title_matches) == 1:
            return ContactReconciliationMatch(contact=title_matches[0], method="name_title")
        if len(title_matches) > 1:
            return ContactReconciliationMatch(contact=None, ambiguous=True)

    if len(name_matches) == 1:
        return ContactReconciliationMatch(contact=name_matches[0], method="unique_name")
    return ContactReconciliationMatch(contact=None, ambiguous=True)
