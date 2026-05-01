from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Company, Contact, ContactRevealBatch, Upload
from app.models.pipeline import ContactFetchBatchState

logger = logging.getLogger(__name__)

_REVEAL_FRESHNESS_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_eligible(contact: Contact) -> bool:
    if not contact.title_match:
        return False
    if contact.email is None:
        return True
    stale_cutoff = _utcnow() - timedelta(days=_REVEAL_FRESHNESS_DAYS)
    return contact.updated_at < stale_cutoff


def _smtp_to_confidence(smtp_status: str) -> float:
    if smtp_status == "valid":
        return 1.0
    if smtp_status == "unknown":
        return 0.5
    return 0.0


def _best_email(emails: list[dict]) -> dict:
    order = {"valid": 0, "unknown": 1}
    return min(emails, key=lambda email: order.get(email.get("smtp_status", ""), 2))


class EmailRevealService:
    def enqueue(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        contact_ids: list[UUID],
    ) -> tuple[ContactRevealBatch, list[UUID], int]:
        contacts = list(
            session.exec(
                select(Contact)
                .join(Company, col(Company.id) == col(Contact.company_id))
                .join(Upload, col(Upload.id) == col(Company.upload_id))
                .where(
                    col(Contact.id).in_(contact_ids),
                    col(Upload.campaign_id) == campaign_id,
                )
            )
        )

        eligible: list[UUID] = []
        skipped = 0
        eligible_set: set[UUID] = set()

        for contact in contacts:
            if _is_eligible(contact):
                eligible.append(contact.id)
                eligible_set.add(contact.id)
            else:
                skipped += 1

        skipped += sum(1 for contact_id in contact_ids if contact_id not in eligible_set and all(contact.id != contact_id for contact in contacts))

        batch = ContactRevealBatch(
            campaign_id=campaign_id,
            trigger_source="manual",
            reveal_scope="selected",
            state=ContactFetchBatchState.QUEUED,
            selected_count=len(contact_ids),
            requested_count=len(eligible),
            queued_count=len(eligible),
            skipped_revealed_count=skipped,
        )
        session.add(batch)
        session.flush()

        return batch, eligible, skipped

    def run_reveal(self, *, engine: Any, contact_id: str) -> None:
        cid = UUID(contact_id)

        with Session(engine) as session:
            contact = session.get(Contact, cid)
            if contact is None:
                logger.warning("reveal_email: contact %s not found", cid)
                return

            provider = contact.source_provider
            provider_person_id = contact.provider_person_id
            first_name = contact.first_name
            last_name = contact.last_name
            company_id = contact.company_id

        with Session(engine) as session:
            company = session.get(Company, company_id)
            domain = company.domain if company else ""

        email: str | None = None
        smtp_status: str | None = None
        raw: dict = {}
        err = ""

        if provider == "snov":
            from app.services.snov_client import SnovClient

            client = SnovClient()
            emails, err = client.search_prospect_email(provider_person_id)
            if not err and emails:
                best = _best_email(emails)
                email = best.get("email")
                smtp_status = best.get("smtp_status")
                raw = best
            elif not err:
                emails, err = client.find_email_by_name(first_name, last_name, domain)
                if not err and emails:
                    best = _best_email(emails)
                    email = best.get("email")
                    smtp_status = best.get("smtp_status")
                    raw = best
        elif provider == "apollo":
            from app.services.apollo_client import ApolloClient

            client = ApolloClient()
            person = client.reveal_email(provider_person_id)
            if person:
                email = person.get("email") or None
                smtp_status = "valid" if email else None
                raw = person
            err = client.last_error_code if not person else ""
        else:
            logger.warning("reveal_email: unknown source_provider %r for contact %s", provider, cid)
            return

        if err:
            logger.warning("reveal_email: provider error %r for contact %s", err, cid)
            return

        if not email:
            return

        confidence = _smtp_to_confidence(smtp_status or "")

        with Session(engine) as session:
            contact = session.get(Contact, cid)
            if contact is None:
                return
            contact.email = email
            contact.email_provider = provider
            contact.email_confidence = confidence
            contact.provider_email_status = smtp_status
            contact.reveal_raw_json = raw
            contact.pipeline_stage = "email_revealed"
            contact.updated_at = _utcnow()
            session.add(contact)
            session.commit()
