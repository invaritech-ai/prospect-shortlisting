from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlmodel import Session, col, select

from app.models.base import utcnow
from app.models.contacts import FetchedPerson
from app.models.core import Campaign
from app.services.contact_reconciliation import find_reconciled_contact


class FetchedPeopleRepairError(ValueError):
    pass


@dataclass(frozen=True)
class FetchedPeopleLinkRepairSummary:
    campaign_id: UUID
    applied: bool
    scanned_fetched_people: int
    linked: int
    ambiguous: int
    unmatched: int


def link_fetched_people_contacts(
    *,
    session: Session,
    campaign_id: UUID,
    apply: bool = False,
) -> FetchedPeopleLinkRepairSummary:
    if session.get(Campaign, campaign_id) is None:
        raise FetchedPeopleRepairError(f"Campaign not found: {campaign_id}")

    fetched_people = session.exec(
        select(FetchedPerson).where(
            col(FetchedPerson.campaign_id) == campaign_id,
            col(FetchedPerson.contact_id).is_(None),
        )
    ).all()

    linked = 0
    ambiguous = 0
    unmatched = 0
    for person in fetched_people:
        match = find_reconciled_contact(
            session=session,
            campaign_id=campaign_id,
            domain_id=person.domain_id,
            provider=person.provider,
            provider_person_id=person.provider_person_id,
            first_name=person.first_name,
            last_name=person.last_name,
            title=person.title,
            linkedin_url=person.linkedin_url,
        )
        if match.contact:
            linked += 1
            if apply:
                person.contact_id = match.contact.id
                person.updated_at = utcnow()
                session.add(person)
        elif match.ambiguous:
            ambiguous += 1
        else:
            unmatched += 1

    if apply:
        session.commit()

    return FetchedPeopleLinkRepairSummary(
        campaign_id=campaign_id,
        applied=apply,
        scanned_fetched_people=len(fetched_people),
        linked=linked,
        ambiguous=ambiguous,
        unmatched=unmatched,
    )
