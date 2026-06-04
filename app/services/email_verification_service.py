from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
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
from app.models import Campaign, Contact, EmailVerificationCache, UploadedDomain, VerificationBatch
from app.models.base import coerce_utc_datetime, utcnow
from app.services.zerobounce_client import ZeroBounceClient

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
    def __init__(self, zerobounce: Any | None = None) -> None:
        self.zerobounce = zerobounce or ZeroBounceClient()

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
        eligible_count = 0
        cached_count = 0
        paid_validation_emails: set[str] = set()
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

            eligible_count += 1
            if normalized_email in fresh_cache_emails:
                cached_count += 1
            else:
                paid_validation_emails.add(normalized_email)

        paid_validation_count = len(paid_validation_emails)
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

    def create_batch(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        contact_ids: list[UUID],
    ) -> VerificationBatch:
        preview = self.preview(
            session=session,
            campaign_id=campaign_id,
            contact_ids=contact_ids,
        )
        if preview.eligible_count <= 0:
            raise EmailVerificationServiceError(
                "no_eligible_contacts",
                "No eligible contacts were selected for email verification.",
            )
        self._check_paid_credentials(preview.paid_validation_count)

        selected_ids = list(contact_ids[:MAX_EMAILS_PER_BATCH])
        eligible_snapshots = self._eligible_contact_snapshots(
            session=session,
            campaign_id=campaign_id,
            contact_ids=selected_ids,
        )
        if not eligible_snapshots:
            raise EmailVerificationServiceError(
                "no_eligible_contacts",
                "No eligible contacts were selected for email verification.",
            )

        batch = VerificationBatch(
            campaign_id=campaign_id,
            state="queued",
            selected_count=len(selected_ids),
            queued_count=len(eligible_snapshots),
            selected_contact_snapshots_json=[
                {"contact_id": str(contact.id), "email": normalized_email}
                for contact, normalized_email in eligible_snapshots
            ],
            result_summary_json={
                "cached_count": preview.cached_count,
                "paid_validation_count": preview.paid_validation_count,
                "skipped_count": preview.skipped_count,
            },
        )
        now = utcnow()
        session.add(batch)
        for contact, normalized_email in eligible_snapshots:
            contact.verification_batch_id = batch.id
            contact.verified_email_snapshot = normalized_email
            contact.verification_applied = False
            contact.verification_status = None
            contact.verification_sub_status = None
            contact.verification_raw_json = None
            contact.updated_at = now
            session.add(contact)

        session.commit()
        session.refresh(batch)
        return batch

    def get_batch(self, *, session: Session, batch_id: UUID) -> VerificationBatch:
        batch = session.get(VerificationBatch, batch_id)
        if batch is None:
            raise EmailVerificationServiceError(
                "batch_not_found",
                "Verification batch not found.",
            )
        return batch

    def get_active_batch(
        self,
        *,
        session: Session,
        campaign_id: UUID,
    ) -> VerificationBatch | None:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        batches = session.exec(
            select(VerificationBatch)
            .where(
                col(VerificationBatch.campaign_id) == campaign_id,
                col(VerificationBatch.state).in_(["queued", "running"]),
            )
            .order_by(col(VerificationBatch.created_at).desc())
        ).all()
        for batch in batches:
            if self._batch_has_active_contacts(session=session, batch=batch):
                return batch
        return None

    def run_batch(
        self,
        *,
        session: Session,
        batch_id: UUID,
    ) -> VerificationBatch:
        batch = session.get(VerificationBatch, batch_id)
        if batch is None:
            raise EmailVerificationServiceError("batch_not_found", "Verification batch not found.")
        if batch.state in {"succeeded", "failed"}:
            return batch

        batch.state = "running"
        session.add(batch)
        session.commit()
        session.refresh(batch)

        previous_summary = batch.result_summary_json if isinstance(batch.result_summary_json, dict) else {}
        initial_skipped_count = self._coerce_nonnegative_int(previous_summary.get("skipped_count"))

        remaining: list[tuple[Contact, str]] = []
        runtime_skipped_count = 0
        for snapshot in batch.selected_contact_snapshots_json or []:
            contact_id = self._snapshot_contact_id(snapshot)
            normalized_email = normalize_email(str(snapshot.get("email") or ""))
            if contact_id is None or not normalized_email:
                runtime_skipped_count += 1
                continue

            contact = session.get(Contact, contact_id)
            if contact is None or contact.campaign_id != batch.campaign_id:
                runtime_skipped_count += 1
                continue

            current_email = normalize_email(contact.selected_email)
            if not current_email or current_email != normalized_email:
                if contact.verification_batch_id == batch.id:
                    contact.verification_batch_id = None
                    contact.updated_at = utcnow()
                    session.add(contact)
                runtime_skipped_count += 1
                continue

            remaining.append((contact, normalized_email))

        run_started_at = utcnow()
        cache_by_email = self._fresh_caches_by_email(
            session=session,
            emails=[email for _contact, email in remaining],
            now=run_started_at,
        )

        verified_count = 0
        valid_count = 0
        invalid_count = 0
        cache_result_count = 0
        api_result_count = 0
        technical_failed_count = 0

        paid_misses: list[tuple[Contact, str]] = []
        for contact, normalized_email in remaining:
            cache = cache_by_email.get(normalized_email)
            if cache is None:
                paid_misses.append((contact, normalized_email))
                continue

            if self._apply_cache_result_to_contact(
                session=session,
                batch=batch,
                contact=contact,
                normalized_email=normalized_email,
                cache=cache,
            ):
                verified_count += 1
                cache_result_count += 1
                status = normalize_zerobounce_status(cache.status)
                if status in RESULT_VALID:
                    valid_count += 1
                if status in RESULT_UNDELIVERABLE:
                    invalid_count += 1
            else:
                runtime_skipped_count += 1

        api_results_by_email: dict[str, dict[str, Any]] = {}
        provider_error_code = ""
        paid_emails = list(dict.fromkeys(email for _contact, email in paid_misses))
        if paid_emails:
            provider_results, provider_error_code = self.zerobounce.validate_batch(paid_emails)
            if provider_error_code:
                for contact, normalized_email in paid_misses:
                    if self._mark_contact_technical_failed(
                        session=session,
                        batch=batch,
                        contact=contact,
                        normalized_email=normalized_email,
                        error_code=provider_error_code,
                    ):
                        technical_failed_count += 1
                    else:
                        runtime_skipped_count += 1
            else:
                validated_at = utcnow()
                api_results_by_email = self._upsert_provider_results(
                    session=session,
                    results=provider_results,
                    validated_at=validated_at,
                )

                for contact, normalized_email in paid_misses:
                    result = api_results_by_email.get(normalized_email)
                    if result is None:
                        if contact.verification_batch_id == batch.id:
                            contact.verification_batch_id = None
                            contact.updated_at = utcnow()
                            session.add(contact)
                        runtime_skipped_count += 1
                        continue
                    cache = self._cache_for_email(
                        session=session,
                        normalized_email=normalized_email,
                    )
                    if cache is None:
                        runtime_skipped_count += 1
                        continue
                    if self._apply_api_result_to_contact(
                        session=session,
                        batch=batch,
                        contact=contact,
                        normalized_email=normalized_email,
                        cache=cache,
                        result=result,
                    ):
                        verified_count += 1
                        api_result_count += 1
                        status = normalize_zerobounce_status(result.get("status"))
                        if status in RESULT_VALID:
                            valid_count += 1
                        if status in RESULT_UNDELIVERABLE:
                            invalid_count += 1
                    else:
                        runtime_skipped_count += 1

        total_skipped_count = initial_skipped_count + runtime_skipped_count
        batch.verified_count = verified_count
        batch.valid_count = valid_count
        batch.invalid_count = invalid_count
        batch.skipped_count = total_skipped_count
        batch.queued_count = 0
        batch.state = (
            "failed"
            if provider_error_code and verified_count == 0 and paid_misses
            else "succeeded"
        )
        batch.finished_at = utcnow()
        batch.result_summary_json = {
            **previous_summary,
            "cache_result_count": cache_result_count,
            "api_result_count": api_result_count,
            "skipped_count": total_skipped_count,
            "technical_failed_count": technical_failed_count,
        }
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return batch

    def _ensure_campaign(self, *, session: Session, campaign_id: UUID) -> None:
        if session.get(Campaign, campaign_id) is None:
            raise EmailVerificationServiceError("campaign_not_found", "Campaign not found.")

    def _check_paid_credentials(self, paid_count: int) -> None:
        if paid_count <= 0:
            return
        ok, error_code, message = self.zerobounce.check_credentials()
        if ok:
            return
        raise EmailVerificationServiceError(
            error_code or "zerobounce_failed",
            message or "ZeroBounce credential check failed.",
        )

    def _coerce_nonnegative_int(self, value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _eligible_contact_snapshots(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        contact_ids: list[UUID],
    ) -> list[tuple[Contact, str]]:
        contacts_by_id = self._contacts_by_id(
            session=session,
            campaign_id=campaign_id,
            contact_ids=contact_ids,
        )
        now = utcnow()
        seen: set[UUID] = set()
        snapshots: list[tuple[Contact, str]] = []
        for contact_id in contact_ids:
            if contact_id in seen:
                continue
            seen.add(contact_id)
            contact = contacts_by_id.get(contact_id)
            if contact is None:
                continue
            normalized_email = normalize_email(contact.selected_email)
            if not normalized_email:
                continue
            if contact_verification_bucket(contact, now=now) not in ACTIONABLE_BUCKETS:
                continue
            snapshots.append((contact, normalized_email))
        return snapshots

    def _snapshot_contact_id(self, snapshot: dict[str, Any]) -> UUID | None:
        try:
            return UUID(str(snapshot.get("contact_id")))
        except (TypeError, ValueError):
            return None

    def _batch_has_active_contacts(self, *, session: Session, batch: VerificationBatch) -> bool:
        snapshot_emails_by_id: dict[UUID, str] = {}
        for snapshot in batch.selected_contact_snapshots_json or []:
            contact_id = self._snapshot_contact_id(snapshot)
            normalized_email = normalize_email(str(snapshot.get("email") or ""))
            if contact_id is not None and normalized_email:
                snapshot_emails_by_id[contact_id] = normalized_email

        query = select(Contact).where(
            col(Contact.campaign_id) == batch.campaign_id,
            col(Contact.verification_batch_id) == batch.id,
            col(Contact.verification_applied).is_(False),
        )
        if snapshot_emails_by_id:
            query = query.where(col(Contact.id).in_(list(snapshot_emails_by_id)))

        contacts = session.exec(query.limit(MAX_EMAILS_PER_BATCH)).all()
        if not snapshot_emails_by_id:
            return bool(contacts)

        return any(
            normalize_email(contact.selected_email) == snapshot_emails_by_id.get(contact.id)
            for contact in contacts
        )

    def _fresh_caches_by_email(
        self,
        *,
        session: Session,
        emails: list[str],
        now: datetime,
    ) -> dict[str, EmailVerificationCache]:
        unique_emails = list(dict.fromkeys(email for email in emails if email))
        if not unique_emails:
            return {}
        rows = session.exec(
            select(EmailVerificationCache).where(
                col(EmailVerificationCache.provider) == "zerobounce",
                col(EmailVerificationCache.normalized_email).in_(unique_emails),
            )
        ).all()
        return {
            cache.normalized_email: cache
            for cache in rows
            if is_fresh_verified_at(cache.validated_at, now=now)
        }

    def _cache_result_payload(self, cache: EmailVerificationCache) -> dict[str, Any]:
        if isinstance(cache.raw_json, dict):
            return cache.raw_json
        result: dict[str, Any] = {
            "address": cache.normalized_email,
            "status": cache.status,
        }
        if cache.sub_status:
            result["sub_status"] = cache.sub_status
        return result

    def _apply_cache_result_to_contact(
        self,
        *,
        session: Session,
        batch: VerificationBatch,
        contact: Contact,
        normalized_email: str,
        cache: EmailVerificationCache,
    ) -> bool:
        result = self._cache_result_payload(cache)
        status = normalize_zerobounce_status(str(result.get("status") or cache.status))
        sub_status = result.get("sub_status") or cache.sub_status
        return self._apply_result_to_contact(
            session=session,
            batch=batch,
            contact=contact,
            normalized_email=normalized_email,
            status=status,
            sub_status=str(sub_status) if sub_status else None,
            raw_json={
                "provider": "zerobounce",
                "source": "cache",
                "result": result,
            },
            verified_at=cache.validated_at,
        )

    def _apply_api_result_to_contact(
        self,
        *,
        session: Session,
        batch: VerificationBatch,
        contact: Contact,
        normalized_email: str,
        cache: EmailVerificationCache,
        result: dict[str, Any],
    ) -> bool:
        status = normalize_zerobounce_status(str(result.get("status") or cache.status))
        sub_status = result.get("sub_status") or cache.sub_status
        return self._apply_result_to_contact(
            session=session,
            batch=batch,
            contact=contact,
            normalized_email=normalized_email,
            status=status,
            sub_status=str(sub_status) if sub_status else None,
            raw_json={
                "provider": "zerobounce",
                "source": "api",
                "result": result,
            },
            verified_at=cache.validated_at,
        )

    def _apply_result_to_contact(
        self,
        *,
        session: Session,
        batch: VerificationBatch,
        contact: Contact,
        normalized_email: str,
        status: str,
        sub_status: str | None,
        raw_json: dict[str, Any],
        verified_at: datetime,
    ) -> bool:
        session.refresh(contact)
        if (
            contact.campaign_id != batch.campaign_id
            or normalize_email(contact.selected_email) != normalized_email
        ):
            if contact.verification_batch_id == batch.id:
                contact.verification_batch_id = None
                contact.updated_at = utcnow()
                session.add(contact)
            return False

        contact.verification_status = status
        contact.verification_sub_status = sub_status
        contact.verification_raw_json = raw_json
        contact.verification_applied = True
        contact.verified_at = verified_at
        contact.verified_email_snapshot = normalized_email
        contact.verification_batch_id = None
        contact.updated_at = utcnow()
        session.add(contact)
        return True

    def _mark_contact_technical_failed(
        self,
        *,
        session: Session,
        batch: VerificationBatch,
        contact: Contact,
        normalized_email: str,
        error_code: str,
    ) -> bool:
        session.refresh(contact)
        if (
            contact.campaign_id != batch.campaign_id
            or normalize_email(contact.selected_email) != normalized_email
        ):
            if contact.verification_batch_id == batch.id:
                contact.verification_batch_id = None
                contact.updated_at = utcnow()
                session.add(contact)
            return False

        contact.verification_status = "failed"
        contact.verification_sub_status = error_code
        contact.verification_raw_json = {
            "provider": "zerobounce",
            "error_code": error_code,
        }
        contact.verification_applied = False
        contact.verified_email_snapshot = normalized_email
        contact.verification_batch_id = None
        contact.updated_at = utcnow()
        session.add(contact)
        return True

    def _upsert_provider_results(
        self,
        *,
        session: Session,
        results: list[dict[str, Any]],
        validated_at: datetime,
    ) -> dict[str, dict[str, Any]]:
        results_by_email: dict[str, dict[str, Any]] = {}
        for result in results:
            normalized_email = normalize_email(
                str(result.get("address") or result.get("email_address") or "")
            )
            if not normalized_email:
                continue
            status = normalize_zerobounce_status(str(result.get("status") or ""))
            sub_status = result.get("sub_status")
            cache = self._cache_for_email(
                session=session,
                normalized_email=normalized_email,
            )
            now = utcnow()
            if cache is None:
                cache = EmailVerificationCache(
                    provider="zerobounce",
                    normalized_email=normalized_email,
                    status=status,
                    sub_status=str(sub_status) if sub_status else None,
                    raw_json=result,
                    validated_at=validated_at,
                    updated_at=now,
                )
            else:
                cache.status = status
                cache.sub_status = str(sub_status) if sub_status else None
                cache.raw_json = result
                cache.validated_at = validated_at
                cache.updated_at = now
            session.add(cache)
            results_by_email[normalized_email] = result
        session.flush()
        return results_by_email

    def _cache_for_email(
        self,
        *,
        session: Session,
        normalized_email: str,
    ) -> EmailVerificationCache | None:
        return session.exec(
            select(EmailVerificationCache).where(
                col(EmailVerificationCache.provider) == "zerobounce",
                col(EmailVerificationCache.normalized_email) == normalized_email,
            )
        ).first()

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
