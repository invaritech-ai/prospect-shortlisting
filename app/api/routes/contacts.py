from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.contacts import ContactList, ContactRead, FetchedPersonList, FetchedPersonRead
from app.db.session import get_session
from app.models.contacts import Contact, FetchedPerson
from app.models.core import UploadedDomain

router = APIRouter(prefix="/v1", tags=["contacts"])


@router.get("/contacts", response_model=ContactList)
def list_contacts(
    campaign_id: UUID = Query(...),
    domain_id: UUID | None = Query(default=None),
    has_email: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactList:
    if not isinstance(domain_id, UUID):
        domain_id = None
    if not isinstance(has_email, bool):
        has_email = None
    if not isinstance(limit, int):
        limit = 50
    if not isinstance(offset, int):
        offset = 0

    base_q = (
        select(Contact, UploadedDomain.domain)
        .join(UploadedDomain, col(UploadedDomain.id) == col(Contact.domain_id))
        .where(col(Contact.campaign_id) == campaign_id)
    )
    if domain_id is not None:
        base_q = base_q.where(col(Contact.domain_id) == domain_id)
    if has_email is True:
        base_q = base_q.where(col(Contact.selected_email).is_not(None))
    elif has_email is False:
        base_q = base_q.where(col(Contact.selected_email).is_(None))

    count_q = select(func.count()).select_from(base_q.subquery())
    total = session.exec(count_q).one()
    rows = session.exec(
        base_q.order_by(col(UploadedDomain.domain), col(Contact.last_name), col(Contact.first_name))
        .limit(limit)
        .offset(offset)
    ).all()
    return ContactList(
        total=int(total),
        limit=limit,
        offset=offset,
        items=[
            ContactRead(
                id=contact.id,
                campaign_id=contact.campaign_id,
                domain_id=contact.domain_id,
                domain=domain,
                first_name=contact.first_name,
                last_name=contact.last_name,
                title=contact.title,
                linkedin_url=contact.linkedin_url,
                title_match=contact.title_match,
                selected_email=contact.selected_email,
                selected_email_provider=contact.selected_email_provider,
                verification_status=contact.verification_status,
                criteria_hash=contact.criteria_hash,
                provider_evidence_json=contact.provider_evidence_json,
                created_at=contact.created_at,
                updated_at=contact.updated_at,
            )
            for contact, domain in rows
        ],
    )


@router.get("/fetched-people", response_model=FetchedPersonList)
def list_fetched_people(
    campaign_id: UUID = Query(...),
    domain_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> FetchedPersonList:
    if not isinstance(domain_id, UUID):
        domain_id = None
    if not isinstance(status, str):
        status = None
    if not isinstance(limit, int):
        limit = 50
    if not isinstance(offset, int):
        offset = 0

    base_q = (
        select(FetchedPerson, UploadedDomain.domain)
        .join(UploadedDomain, col(UploadedDomain.id) == col(FetchedPerson.domain_id))
        .where(col(FetchedPerson.campaign_id) == campaign_id)
    )
    if domain_id is not None:
        base_q = base_q.where(col(FetchedPerson.domain_id) == domain_id)
    if status == "unused":
        base_q = base_q.where(
            col(FetchedPerson.match_status) != "qualified_promoted",
            col(FetchedPerson.contact_id).is_(None),
        )
    elif status:
        base_q = base_q.where(col(FetchedPerson.match_status) == status)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = session.exec(count_q).one()
    rows = session.exec(
        base_q.order_by(
            col(UploadedDomain.domain),
            col(FetchedPerson.match_status),
            col(FetchedPerson.last_name),
            col(FetchedPerson.first_name),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return FetchedPersonList(
        total=int(total),
        limit=limit,
        offset=offset,
        items=[
            FetchedPersonRead(
                id=person.id,
                campaign_id=person.campaign_id,
                domain_id=person.domain_id,
                domain=domain,
                email_fetch_batch_id=person.email_fetch_batch_id,
                contact_id=person.contact_id,
                criteria_hash=person.criteria_hash,
                provider=person.provider,
                provider_person_id=person.provider_person_id,
                first_name=person.first_name,
                last_name=person.last_name,
                title=person.title,
                linkedin_url=person.linkedin_url,
                match_status=person.match_status,
                match_reason=person.match_reason,
                email_lookup_attempted=person.email_lookup_attempted,
                email_result=person.email_result,
                email_status=person.email_status,
                email_error_code=person.email_error_code,
                created_at=person.created_at,
                updated_at=person.updated_at,
            )
            for person, domain in rows
        ],
    )
