from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.api.schemas.email_verification import (
    EmailVerificationContactIds,
    EmailVerificationContactList,
    EmailVerificationContactRow,
    EmailVerificationCounts,
    EmailVerificationPreviewRead,
)
from app.models import Campaign, Contact, EmailVerificationCache, UploadedDomain
from app.models.base import coerce_utc_datetime, utcnow

VERIFICATION_STALE_AFTER_DAYS = 30
MAX_EMAILS_PER_BATCH = 200

RESULT_UNDELIVERABLE = {"invalid", "do_not_mail", "spamtrap", "abuse"}
RESULT_VALID = {"valid", "deliverable"}
RESULT_CATCH_ALL = {"catch-all", "catch_all"}
RESULT_UNKNOWN = {"unknown"}
ACTIONABLE_BUCKETS = {"pending", "stale", "failed"}
STATUS_BUCKETS = (
    "pending",
    "checking",
    "stale",
    "valid",
    "undeliverable",
    "catch_all",
    "unknown",
    "failed",
)


class EmailVerificationServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_zerobounce_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value == "catch-all":
        return "catch_all"
    return value or "unknown"


def is_fresh_verified_at(verified_at: datetime | None, *, now: datetime) -> bool:
    if verified_at is None:
        return False
    verified_at_utc = coerce_utc_datetime(verified_at)
    now_utc = coerce_utc_datetime(now)
    return now_utc - verified_at_utc <= timedelta(days=VERIFICATION_STALE_AFTER_DAYS)


def contact_verification_bucket(contact: Contact, *, now: datetime) -> str:
    selected = normalize_email(contact.selected_email)
    if not selected:
        return "no_email"
    snapshot = normalize_email(contact.verified_email_snapshot)
    status = normalize_zerobounce_status(contact.verification_status)
    if snapshot and snapshot != selected:
        return "pending"
    if status == "failed" and contact.verification_applied is False:
        return "failed"
    if contact.verification_batch_id and contact.verification_applied is False:
        return "checking"
    if not contact.verification_applied or not snapshot:
        return "pending"
    if not is_fresh_verified_at(contact.verified_at, now=now):
        return "stale"
    if status in RESULT_VALID:
        return "valid"
    if status in RESULT_UNDELIVERABLE:
        return "undeliverable"
    if status in RESULT_CATCH_ALL:
        return "catch_all"
    if status in RESULT_UNKNOWN:
        return "unknown"
    return "unknown"


def is_campaign_ready_contact(contact: Contact, *, now: datetime) -> bool:
    selected_email = normalize_email(contact.selected_email)
    if not selected_email:
        return False
    if not contact.verification_applied:
        return False
    if (contact.verification_status or "").lower() != "valid":
        return False
    if normalize_email(contact.verified_email_snapshot) != selected_email:
        return False
    return is_fresh_verified_at(contact.verified_at, now=now)


class EmailVerificationService:
    def list_contacts(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        status: str = "all",
        search: str | None = None,
        letter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> EmailVerificationContactList:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        now = utcnow()
        rows = self._contact_domain_rows(
            session=session,
            campaign_id=campaign_id,
            search=search,
            letter=letter,
        )
        counts = self._counts_for_rows(rows=rows, now=now)
        filtered: list[tuple[Contact, UploadedDomain, str]] = []
        for contact, domain in rows:
            bucket = contact_verification_bucket(contact, now=now)
            if self._status_matches(bucket, status):
                filtered.append((contact, domain, bucket))
        total = len(filtered)
        capped_limit = max(1, limit)
        safe_offset = max(0, offset)
        page = filtered[safe_offset : safe_offset + capped_limit]
        return EmailVerificationContactList(
            total=total,
            limit=capped_limit,
            offset=safe_offset,
            counts=counts,
            items=[
                self._contact_row(contact=contact, domain=domain, bucket=bucket)
                for contact, domain, bucket in page
            ],
        )

    def list_contact_ids(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        status: str = "all",
        search: str | None = None,
        letter: str | None = None,
        actionable_only: bool = False,
        limit: int = MAX_EMAILS_PER_BATCH,
        offset: int = 0,
    ) -> EmailVerificationContactIds:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        now = utcnow()
        rows = self._contact_domain_rows(
            session=session,
            campaign_id=campaign_id,
            search=search,
            letter=letter,
        )
        filtered: list[Contact] = []
        for contact, _domain in rows:
            bucket = contact_verification_bucket(contact, now=now)
            if not self._status_matches(bucket, status):
                continue
            if actionable_only and bucket not in ACTIONABLE_BUCKETS:
                continue
            filtered.append(contact)

        capped_limit = max(1, min(limit, MAX_EMAILS_PER_BATCH))
        safe_offset = max(0, offset)
        page = filtered[safe_offset : safe_offset + capped_limit]
        return EmailVerificationContactIds(
            ids=[contact.id for contact in page],
            total=len(filtered),
            limit=capped_limit,
            offset=safe_offset,
        )

    def get_letter_counts(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        status: str = "all",
        search: str | None = None,
    ) -> dict[str, int]:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        now = utcnow()
        rows = self._contact_domain_rows(
            session=session,
            campaign_id=campaign_id,
            search=search,
            letter=None,
        )
        counts: dict[str, int] = {}
        for contact, domain in rows:
            bucket = contact_verification_bucket(contact, now=now)
            if not self._status_matches(bucket, status):
                continue
            letter_bucket = self._letter_bucket(domain.domain)
            counts[letter_bucket] = counts.get(letter_bucket, 0) + 1
        return counts

    def preview(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        contact_ids: list[UUID],
    ) -> EmailVerificationPreviewRead:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        selected_ids = list(contact_ids[:MAX_EMAILS_PER_BATCH])
        selected_count = len(selected_ids)
        contacts_by_id = self._contacts_by_id(
            session=session,
            campaign_id=campaign_id,
            contact_ids=selected_ids,
        )
        now = utcnow()
        fresh_cache_emails = self._fresh_cache_emails(
            session=session,
            emails=[
                normalize_email(contact.selected_email)
                for contact in contacts_by_id.values()
                if normalize_email(contact.selected_email)
            ],
            now=now,
        )

        seen: set[UUID] = set()
        cached_count = 0
        paid_validation_count = 0
        skipped_reasons: dict[str, int] = {}
        for contact_id in selected_ids:
            if contact_id in seen:
                self._increment_reason(skipped_reasons, "duplicate")
                continue
            seen.add(contact_id)

            contact = contacts_by_id.get(contact_id)
            if contact is None:
                self._increment_reason(skipped_reasons, "not_found")
                continue

            normalized_email = normalize_email(contact.selected_email)
            if not normalized_email:
                self._increment_reason(skipped_reasons, "no_email")
                continue

            bucket = contact_verification_bucket(contact, now=now)
            if bucket not in ACTIONABLE_BUCKETS:
                reason = (
                    "already_verified"
                    if bucket in {"valid", "undeliverable", "catch_all", "unknown"}
                    else "not_actionable"
                )
                self._increment_reason(skipped_reasons, reason)
                continue

            if normalized_email in fresh_cache_emails:
                cached_count += 1
            else:
                paid_validation_count += 1

        eligible_count = cached_count + paid_validation_count
        return EmailVerificationPreviewRead(
            campaign_id=campaign_id,
            selected_count=selected_count,
            eligible_count=eligible_count,
            cached_count=cached_count,
            paid_validation_count=paid_validation_count,
            skipped_count=selected_count - eligible_count,
            skipped_reasons=skipped_reasons,
            max_batch_size=MAX_EMAILS_PER_BATCH,
        )

    def _ensure_campaign(self, *, session: Session, campaign_id: UUID) -> None:
        if session.get(Campaign, campaign_id) is None:
            raise EmailVerificationServiceError("campaign_not_found", "Campaign not found.")

    def _contact_domain_rows(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        search: str | None,
        letter: str | None,
    ) -> list[tuple[Contact, UploadedDomain]]:
        query = (
            select(Contact, UploadedDomain)
            .join(UploadedDomain, col(Contact.domain_id) == col(UploadedDomain.id))
            .where(
                col(Contact.campaign_id) == campaign_id,
                col(UploadedDomain.campaign_id) == campaign_id,
                col(Contact.selected_email).is_not(None),
                func.trim(col(Contact.selected_email)) != "",
            )
        )

        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    col(UploadedDomain.domain).ilike(pattern),
                    col(Contact.first_name).ilike(pattern),
                    col(Contact.last_name).ilike(pattern),
                    col(Contact.title).ilike(pattern),
                    col(Contact.selected_email).ilike(pattern),
                )
            )

        if letter and letter != "all":
            first_char = func.upper(func.substr(col(UploadedDomain.domain), 1, 1))
            normalized_letter = letter.upper()
            if normalized_letter == "#":
                query = query.where(or_(first_char < "A", first_char > "Z"))
            else:
                query = query.where(first_char == normalized_letter)

        rows = session.exec(
            query.order_by(
                col(UploadedDomain.domain).asc(),
                col(Contact.created_at).asc(),
                col(Contact.id).asc(),
            )
        ).all()
        return [(contact, domain) for contact, domain in rows]

    def _counts_for_rows(
        self,
        *,
        rows: list[tuple[Contact, UploadedDomain]],
        now: datetime,
    ) -> EmailVerificationCounts:
        counts = dict.fromkeys(STATUS_BUCKETS, 0)
        total = 0
        for contact, _domain in rows:
            bucket = contact_verification_bucket(contact, now=now)
            if bucket not in counts:
                continue
            counts[bucket] += 1
            total += 1
        return EmailVerificationCounts(all=total, **counts)

    def _status_matches(self, bucket: str, status: str | None) -> bool:
        if bucket not in STATUS_BUCKETS:
            return False
        if not status or status == "all":
            return True
        return bucket == status

    def _contact_row(
        self,
        *,
        contact: Contact,
        domain: UploadedDomain,
        bucket: str,
    ) -> EmailVerificationContactRow:
        return EmailVerificationContactRow(
            contact_id=contact.id,
            campaign_id=contact.campaign_id,
            domain_id=contact.domain_id,
            domain=domain.domain,
            first_name=contact.first_name,
            last_name=contact.last_name,
            title=contact.title,
            linkedin_url=contact.linkedin_url,
            selected_email=normalize_email(contact.selected_email),
            status=bucket,
            verified_at=contact.verified_at,
            updated_at=contact.updated_at,
            action_label=self._action_label(bucket),
        )

    def _action_label(self, bucket: str) -> str | None:
        if bucket == "stale":
            return "Revalidate"
        if bucket in {"pending", "failed"}:
            return "Validate"
        return None

    def _contacts_by_id(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        contact_ids: list[UUID],
    ) -> dict[UUID, Contact]:
        unique_ids = list(dict.fromkeys(contact_ids))
        if not unique_ids:
            return {}
        rows = session.exec(
            select(Contact).where(
                col(Contact.campaign_id) == campaign_id,
                col(Contact.id).in_(unique_ids),
            )
        ).all()
        return {contact.id: contact for contact in rows}

    def _fresh_cache_emails(
        self,
        *,
        session: Session,
        emails: list[str],
        now: datetime,
    ) -> set[str]:
        unique_emails = list(dict.fromkeys(email for email in emails if email))
        if not unique_emails:
            return set()
        rows = session.exec(
            select(EmailVerificationCache).where(
                col(EmailVerificationCache.provider) == "zerobounce",
                col(EmailVerificationCache.normalized_email).in_(unique_emails),
            )
        ).all()
        return {
            cache.normalized_email
            for cache in rows
            if is_fresh_verified_at(cache.validated_at, now=now)
        }

    def _letter_bucket(self, domain: str) -> str:
        first_char = domain[:1].upper()
        return first_char if "A" <= first_char <= "Z" else "#"

    def _increment_reason(self, reasons: dict[str, int], reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1
