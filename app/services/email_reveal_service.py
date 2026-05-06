from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Company, Contact, ContactRevealBatch, Upload
from app.models.pipeline import ContactFetchBatchState
from app.services.contact_reveal import reveal_email_for_person, smtp_to_confidence

logger = logging.getLogger(__name__)

_REVEAL_FRESHNESS_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_eligible(contact: Contact) -> bool:
    if not contact.title_match:
        return False
    # Retry path for the merged S3+S4 flow: contacts that matched rules but
    # didn't get an email during the inline reveal are flagged fetched_no_email.
    if contact.pipeline_stage == "fetched_no_email":
        return True
    if contact.email is None:
        return True
    stale_cutoff = _utcnow() - timedelta(days=_REVEAL_FRESHNESS_DAYS)
    return contact.updated_at < stale_cutoff


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

        if provider not in ("snov", "apollo"):
            logger.warning("reveal_email: unknown source_provider %r for contact %s", provider, cid)
            return

        result = reveal_email_for_person(
            provider=provider,
            person_id=provider_person_id,
            first_name=first_name,
            last_name=last_name,
            domain=domain,
        )

        if result.error_code:
            logger.warning("reveal_email: provider error %r for contact %s", result.error_code, cid)
            raise RuntimeError(f"email_reveal_provider_error:{result.error_code}")

        if not result.found:
            return

        email = result.email
        smtp_status = result.smtp_status
        raw = result.raw or {}
        confidence = smtp_to_confidence(smtp_status)

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
