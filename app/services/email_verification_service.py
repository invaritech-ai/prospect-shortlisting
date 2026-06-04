from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Contact

VERIFICATION_STALE_AFTER_DAYS = 30
MAX_EMAILS_PER_BATCH = 200


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def is_fresh_verified_at(verified_at: datetime | None, *, now: datetime) -> bool:
    if verified_at is None:
        return False
    return now - verified_at <= timedelta(days=VERIFICATION_STALE_AFTER_DAYS)


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
