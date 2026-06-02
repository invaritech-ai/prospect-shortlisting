from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.contacts import Contact
from app.models.core import Campaign, UploadedDomain
from app.services.classification_scope import effective_possible_domain_ids_query


class EmailFetchStatusRepairError(ValueError):
    pass


@dataclass(frozen=True)
class EmailFetchStatusRepairSummary:
    campaign_id: UUID
    applied: bool
    scanned_domains: int
    domains_repaired: int
    contacts_visible: int
    emails_visible: int
    possible_domains_repaired: int
    possible_domains_still_pending: int
    failed_domains_with_contacts: int
    succeeded_domains_without_contacts: int


def repair_email_fetch_status(
    *,
    session: Session,
    campaign_id: UUID,
    apply: bool = False,
) -> EmailFetchStatusRepairSummary:
    if session.get(Campaign, campaign_id) is None:
        raise EmailFetchStatusRepairError(f"Campaign not found: {campaign_id}")

    contact_stats_sq = (
        select(
            col(Contact.domain_id).label("domain_id"),
            func.count(col(Contact.id)).label("contacts_found"),
            func.count(col(Contact.selected_email)).label("emails_found"),
        )
        .where(col(Contact.campaign_id) == campaign_id)
        .group_by(col(Contact.domain_id))
        .subquery()
    )
    possible_ids_sq = effective_possible_domain_ids_query(campaign_id).subquery()

    rows = session.execute(
        select(
            UploadedDomain,
            func.coalesce(contact_stats_sq.c.contacts_found, 0),
            func.coalesce(contact_stats_sq.c.emails_found, 0),
            possible_ids_sq.c.domain_id.is_not(None),
        )
        .outerjoin(contact_stats_sq, col(UploadedDomain.id) == contact_stats_sq.c.domain_id)
        .outerjoin(possible_ids_sq, col(UploadedDomain.id) == possible_ids_sq.c.domain_id)
        .where(col(UploadedDomain.campaign_id) == campaign_id)
    ).all()

    repair_domains: list[UploadedDomain] = []
    contacts_visible = 0
    emails_visible = 0
    possible_domains_repaired = 0
    possible_domains_still_pending = 0
    failed_domains_with_contacts = 0
    succeeded_domains_without_contacts = 0

    for domain, raw_contact_count, raw_email_count, is_possible in rows:
        contact_count = int(raw_contact_count or 0)
        email_count = int(raw_email_count or 0)
        possible = bool(is_possible)

        if domain.fetch_status is None and contact_count > 0:
            repair_domains.append(domain)
            contacts_visible += contact_count
            emails_visible += email_count
            if possible:
                possible_domains_repaired += 1
        elif domain.fetch_status is None and contact_count == 0 and possible:
            possible_domains_still_pending += 1

        if domain.fetch_status == "failed" and contact_count > 0:
            failed_domains_with_contacts += 1
        if domain.fetch_status == "succeeded" and contact_count == 0:
            succeeded_domains_without_contacts += 1

    if apply:
        for domain in repair_domains:
            domain.fetch_status = "succeeded"
            session.add(domain)
        session.commit()

    return EmailFetchStatusRepairSummary(
        campaign_id=campaign_id,
        applied=apply,
        scanned_domains=len(rows),
        domains_repaired=len(repair_domains),
        contacts_visible=contacts_visible,
        emails_visible=emails_visible,
        possible_domains_repaired=possible_domains_repaired,
        possible_domains_still_pending=possible_domains_still_pending,
        failed_domains_with_contacts=failed_domains_with_contacts,
        succeeded_domains_without_contacts=succeeded_domains_without_contacts,
    )
