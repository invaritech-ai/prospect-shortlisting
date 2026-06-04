from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Contact
from app.models.base import coerce_utc_datetime

VERIFICATION_STALE_AFTER_DAYS = 30
MAX_EMAILS_PER_BATCH = 200

RESULT_UNDELIVERABLE = {"invalid", "do_not_mail", "spamtrap", "abuse"}
RESULT_VALID = {"valid", "deliverable"}
RESULT_CATCH_ALL = {"catch-all", "catch_all"}
RESULT_UNKNOWN = {"unknown"}
ACTIONABLE_BUCKETS = {"pending", "stale", "failed"}


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
