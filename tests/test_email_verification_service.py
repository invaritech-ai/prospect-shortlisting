from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Campaign, Contact, EmailVerificationCache, UploadedDomain
from app.models.base import utcnow
from app.services.email_verification_service import (
    is_campaign_ready_contact,
    is_fresh_verified_at,
    normalize_email,
)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _campaign(session: Session) -> Campaign:
    campaign = Campaign(name="S4 Campaign")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def _domain(session: Session, campaign_id: UUID) -> UploadedDomain:
    domain = UploadedDomain(
        campaign_id=campaign_id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        dedupe_key="example.com",
    )
    session.add(domain)
    session.commit()
    session.refresh(domain)
    return domain


def _contact(
    session: Session,
    campaign: Campaign,
    domain: UploadedDomain,
    email: str | None = "ada@example.com",
) -> Contact:
    contact = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Ada",
        last_name="Lovelace",
        title="Marketing Director",
        title_match=True,
        selected_email=email,
    )
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


def test_email_verification_cache_persists_normalized_email(db_session: Session) -> None:
    cache = EmailVerificationCache(
        normalized_email=normalize_email("  PERSON@Example.COM  "),
        status="valid",
        sub_status=None,
        raw_json={"address": "PERSON@Example.COM", "status": "valid"},
    )

    db_session.add(cache)
    db_session.commit()

    saved = db_session.exec(select(EmailVerificationCache)).one()
    assert saved.provider == "zerobounce"
    assert saved.normalized_email == "person@example.com"
    assert saved.status == "valid"
    assert saved.raw_json == {"address": "PERSON@Example.COM", "status": "valid"}


def test_contact_ready_rule_uses_current_email_snapshot(db_session: Session) -> None:
    now = utcnow()
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        selected_email="current@example.com",
        verification_applied=True,
        verification_status="VALID",
        verified_email_snapshot="old@example.com",
        verified_at=now - timedelta(days=1),
    )

    assert is_campaign_ready_contact(contact, now=now) is False

    contact.verified_email_snapshot = " CURRENT@example.com "
    assert is_campaign_ready_contact(contact, now=now) is True

    contact.verified_at = now - timedelta(days=31)
    assert is_campaign_ready_contact(contact, now=now) is False


def test_fresh_verified_at_normalizes_naive_and_aware_datetimes_at_boundary() -> None:
    aware_now = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)

    assert is_fresh_verified_at(datetime(2026, 5, 5, 12, 0), now=aware_now) is True
    assert is_fresh_verified_at(datetime(2026, 5, 5, 11, 59, 59), now=aware_now) is False


def test_status_bucket_pending_stale_and_checking(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    pending = _contact(db_session, campaign, domain, "pending@example.com")
    checking = _contact(db_session, campaign, domain, "checking@example.com")
    stale = _contact(db_session, campaign, domain, "stale@example.com")

    checking.verification_batch_id = uuid4()
    checking.verified_email_snapshot = "checking@example.com"
    checking.verification_applied = False

    stale.verified_email_snapshot = "stale@example.com"
    stale.verification_status = "valid"
    stale.verification_applied = True
    stale.verified_at = utcnow() - timedelta(days=31)
    db_session.add_all([pending, checking, stale])
    db_session.commit()

    from app.services.email_verification_service import contact_verification_bucket

    now = utcnow()
    assert contact_verification_bucket(pending, now=now) == "pending"
    assert contact_verification_bucket(checking, now=now) == "checking"
    assert contact_verification_bucket(stale, now=now) == "stale"


def test_status_bucket_maps_zerobounce_results(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    valid = _contact(db_session, campaign, domain, "valid@example.com")
    invalid = _contact(db_session, campaign, domain, "invalid@example.com")
    catch_all = _contact(db_session, campaign, domain, "catch@example.com")
    unknown = _contact(db_session, campaign, domain, "unknown@example.com")
    failed = _contact(db_session, campaign, domain, "failed@example.com")

    for contact, status in [
        (valid, "valid"),
        (invalid, "do_not_mail"),
        (catch_all, "catch-all"),
        (unknown, ""),
    ]:
        contact.verified_email_snapshot = contact.selected_email
        contact.verification_status = status
        contact.verification_applied = True
        contact.verified_at = utcnow()

    failed.verified_email_snapshot = failed.selected_email
    failed.verification_status = "failed"
    failed.verification_sub_status = "zerobounce_failed"
    failed.verification_applied = False

    db_session.add_all([valid, invalid, catch_all, unknown, failed])
    db_session.commit()

    from app.services.email_verification_service import (
        contact_verification_bucket,
        normalize_zerobounce_status,
    )

    now = utcnow()
    assert normalize_zerobounce_status("catch-all") == "catch_all"
    assert normalize_zerobounce_status(" ") == "unknown"
    assert contact_verification_bucket(valid, now=now) == "valid"
    assert contact_verification_bucket(invalid, now=now) == "undeliverable"
    assert contact_verification_bucket(catch_all, now=now) == "catch_all"
    assert contact_verification_bucket(unknown, now=now) == "unknown"
    assert contact_verification_bucket(failed, now=now) == "failed"


def test_status_bucket_failed_with_batch_id_returns_failed(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    failed = _contact(db_session, campaign, domain, "failed@example.com")
    failed.verification_batch_id = uuid4()
    failed.verified_email_snapshot = failed.selected_email
    failed.verification_status = "failed"
    failed.verification_sub_status = "zerobounce_failed"
    failed.verification_applied = False
    db_session.add(failed)
    db_session.commit()

    from app.services.email_verification_service import contact_verification_bucket

    assert contact_verification_bucket(failed, now=utcnow()) == "failed"


def test_status_bucket_snapshot_mismatch_with_batch_id_returns_pending(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    changed = _contact(db_session, campaign, domain, "new@example.com")
    changed.verification_batch_id = uuid4()
    changed.verified_email_snapshot = "old@example.com"
    changed.verification_status = "valid"
    changed.verification_applied = False
    db_session.add(changed)
    db_session.commit()

    from app.services.email_verification_service import contact_verification_bucket

    assert contact_verification_bucket(changed, now=utcnow()) == "pending"


def test_list_contacts_shows_only_contacts_with_email_and_filters_by_domain_letter(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    _contact(db_session, campaign, domain, "ada@example.com")
    _contact(db_session, campaign, domain, None)

    from app.services.email_verification_service import EmailVerificationService

    out = EmailVerificationService().list_contacts(
        session=db_session,
        campaign_id=campaign.id,
        status="all",
        search=None,
        letter="E",
        limit=50,
        offset=0,
    )

    assert out.total == 1
    assert out.counts.all == 1
    assert out.items[0].selected_email == "ada@example.com"
    assert out.items[0].domain == "example.com"
    assert out.items[0].status == "pending"


def test_preview_reports_cached_paid_and_skipped_counts(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    pending = _contact(db_session, campaign, domain, "pending@example.com")
    cached = _contact(db_session, campaign, domain, "cached@example.com")
    valid = _contact(db_session, campaign, domain, "valid@example.com")

    valid.verified_email_snapshot = "valid@example.com"
    valid.verification_status = "valid"
    valid.verification_applied = True
    valid.verified_at = utcnow()
    db_session.add(valid)
    db_session.add(
        EmailVerificationCache(
            provider="zerobounce",
            normalized_email="cached@example.com",
            status="valid",
            raw_json={"address": "cached@example.com", "status": "valid"},
            validated_at=utcnow(),
        )
    )
    db_session.commit()

    from app.services.email_verification_service import EmailVerificationService

    preview = EmailVerificationService().preview(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[pending.id, cached.id, valid.id],
    )

    assert preview.selected_count == 3
    assert preview.eligible_count == 2
    assert preview.cached_count == 1
    assert preview.paid_validation_count == 1
    assert preview.skipped_count == 1


def test_list_contact_ids_returns_actionable_filtered_ids(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    pending = _contact(db_session, campaign, domain, "pending@example.com")
    failed = _contact(db_session, campaign, domain, "failed@example.com")
    valid = _contact(db_session, campaign, domain, "valid@example.com")

    failed.verified_email_snapshot = failed.selected_email
    failed.verification_status = "failed"
    failed.verification_sub_status = "zerobounce_failed"
    failed.verification_applied = False

    valid.verified_email_snapshot = valid.selected_email
    valid.verification_status = "valid"
    valid.verification_applied = True
    valid.verified_at = utcnow()
    db_session.add_all([failed, valid])
    db_session.commit()

    from app.services.email_verification_service import EmailVerificationService

    out = EmailVerificationService().list_contact_ids(
        session=db_session,
        campaign_id=campaign.id,
        status="all",
        search=None,
        letter="E",
        actionable_only=True,
        limit=200,
        offset=0,
    )

    assert out.total == 2
    assert out.ids == [pending.id, failed.id]


def test_get_letter_counts_applies_status_and_search_filters(db_session: Session) -> None:
    campaign = _campaign(db_session)
    example = _domain(db_session, campaign.id)
    alpha = UploadedDomain(
        campaign_id=campaign.id,
        raw_url="https://alpha.com",
        normalized_url="https://alpha.com",
        domain="alpha.com",
        dedupe_key="alpha.com",
    )
    db_session.add(alpha)
    db_session.commit()
    db_session.refresh(alpha)

    _contact(db_session, campaign, example, "pending@example.com")
    stale = _contact(db_session, campaign, alpha, "stale@alpha.com")
    stale.title = "Operations Lead"
    stale.verified_email_snapshot = stale.selected_email
    stale.verification_status = "valid"
    stale.verification_applied = True
    stale.verified_at = utcnow() - timedelta(days=31)
    db_session.add(stale)
    db_session.commit()

    from app.services.email_verification_service import EmailVerificationService

    counts = EmailVerificationService().get_letter_counts(
        session=db_session,
        campaign_id=campaign.id,
        status="stale",
        search="operations",
    )

    assert counts == {"A": 1}
