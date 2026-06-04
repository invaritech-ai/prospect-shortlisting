from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Campaign, Contact, EmailVerificationCache, UploadedDomain, VerificationBatch
from app.models.base import utcnow
from app.services.email_verification_service import (
    EmailVerificationServiceError,
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


@pytest.fixture()
def fk_db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

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


def test_export_valid_emails_only_includes_fresh_current_valid_contacts(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    valid = _contact(db_session, campaign, domain, "Ada@Example.com")
    stale = _contact(db_session, campaign, domain, "stale@example.com")
    changed = _contact(db_session, campaign, domain, "changed@example.com")
    undeliverable = _contact(db_session, campaign, domain, "bad@example.com")
    pending = _contact(db_session, campaign, domain, "pending@example.com")

    now = utcnow()
    for contact in [valid, stale, changed, undeliverable]:
        contact.verified_email_snapshot = contact.selected_email
        contact.verification_applied = True
        contact.verified_at = now - timedelta(days=1)

    valid.first_name = "Ada"
    valid.last_name = "Lovelace"
    valid.title = "Marketing Director"
    valid.linkedin_url = "https://linkedin.com/in/ada"
    valid.verification_status = "valid"

    stale.verification_status = "valid"
    stale.verified_at = now - timedelta(days=31)

    changed.verification_status = "valid"
    changed.verified_email_snapshot = "old@example.com"

    undeliverable.verification_status = "invalid"

    db_session.add_all([valid, stale, changed, undeliverable, pending])
    db_session.commit()

    from app.services.email_verification_service import EmailVerificationService

    rows = EmailVerificationService().list_fresh_valid_email_exports(
        session=db_session,
        campaign_id=campaign.id,
    )

    assert rows == [
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "title": "Marketing Director",
            "company_domain": "example.com",
            "email": "ada@example.com",
            "linkedin_url": "https://linkedin.com/in/ada",
            "verified_at": valid.verified_at,
        }
    ]


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


def test_list_contact_row_serialization_does_not_expose_provider_result_fields(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "bad@example.com")
    contact.verified_email_snapshot = contact.selected_email
    contact.verification_status = "do_not_mail"
    contact.verification_sub_status = "zerobounce_failed"
    contact.verification_applied = True
    contact.verified_at = utcnow()
    db_session.add(contact)
    db_session.commit()

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

    row = out.items[0].model_dump()
    assert row["status"] == "undeliverable"
    assert "raw_status" not in row
    assert "sub_status" not in row


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


def test_preview_counts_duplicate_missing_and_out_of_campaign_ids_as_skipped(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    pending = _contact(db_session, campaign, domain, "pending@example.com")
    other_campaign = _campaign(db_session)
    other_domain = _domain(db_session, other_campaign.id)
    other_contact = _contact(db_session, other_campaign, other_domain, "other@example.com")
    missing_id = uuid4()

    from app.services.email_verification_service import EmailVerificationService

    preview = EmailVerificationService().preview(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[pending.id, pending.id, missing_id, other_contact.id],
    )

    assert preview.selected_count == 4
    assert preview.eligible_count == 1
    assert preview.paid_validation_count == 1
    assert preview.skipped_count == 3
    assert preview.skipped_reasons == {"duplicate": 1, "not_found": 2}


def test_preview_skips_no_email_and_non_actionable_contacts(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    blank = _contact(db_session, campaign, domain, "   ")
    checking = _contact(db_session, campaign, domain, "checking@example.com")
    checking.verification_batch_id = uuid4()
    checking.verified_email_snapshot = checking.selected_email
    checking.verification_applied = False
    db_session.add(checking)
    db_session.commit()

    from app.services.email_verification_service import EmailVerificationService

    preview = EmailVerificationService().preview(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[blank.id, checking.id],
    )

    assert preview.selected_count == 2
    assert preview.eligible_count == 0
    assert preview.skipped_count == 2
    assert preview.skipped_reasons == {"no_email": 1, "not_actionable": 1}


def test_preview_uses_fresh_cache_but_not_stale_cache(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    fresh = _contact(db_session, campaign, domain, "fresh@example.com")
    stale = _contact(db_session, campaign, domain, "stale@example.com")
    db_session.add_all(
        [
            EmailVerificationCache(
                provider="zerobounce",
                normalized_email="fresh@example.com",
                status="valid",
                raw_json={"address": "fresh@example.com", "status": "valid"},
                validated_at=utcnow(),
            ),
            EmailVerificationCache(
                provider="zerobounce",
                normalized_email="stale@example.com",
                status="valid",
                raw_json={"address": "stale@example.com", "status": "valid"},
                validated_at=utcnow() - timedelta(days=31),
            ),
        ]
    )
    db_session.commit()

    from app.services.email_verification_service import EmailVerificationService

    preview = EmailVerificationService().preview(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[fresh.id, stale.id],
    )

    assert preview.selected_count == 2
    assert preview.eligible_count == 2
    assert preview.cached_count == 1
    assert preview.paid_validation_count == 1
    assert preview.skipped_count == 0


def test_preview_counts_duplicate_uncached_email_as_one_paid_validation(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    first = _contact(db_session, campaign, domain, "shared@example.com")
    second = _contact(db_session, campaign, domain, " SHARED@example.com ")

    from app.services.email_verification_service import EmailVerificationService

    preview = EmailVerificationService().preview(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[first.id, second.id],
    )

    assert preview.selected_count == 2
    assert preview.eligible_count == 2
    assert preview.cached_count == 0
    assert preview.paid_validation_count == 1
    assert preview.skipped_count == 0


def test_preview_caps_selected_count_at_max_batch_size(db_session: Session) -> None:
    campaign = _campaign(db_session)

    from app.services.email_verification_service import EmailVerificationService

    preview = EmailVerificationService().preview(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[uuid4() for _ in range(201)],
    )

    assert preview.selected_count == 200
    assert preview.max_batch_size == 200
    assert preview.skipped_count == 200
    assert preview.skipped_reasons == {"not_found": 200}


def test_preview_request_accepts_200_contact_ids_and_rejects_201() -> None:
    from app.api.schemas.email_verification import EmailVerificationPreviewRequest

    campaign_id = uuid4()
    accepted = EmailVerificationPreviewRequest(
        campaign_id=campaign_id,
        contact_ids=[uuid4() for _ in range(200)],
    )

    assert accepted.campaign_id == campaign_id
    assert len(accepted.contact_ids) == 200

    with pytest.raises(ValidationError):
        EmailVerificationPreviewRequest(
            campaign_id=campaign_id,
            contact_ids=[uuid4() for _ in range(201)],
        )


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


class FakeZeroBounce:
    def __init__(
        self,
        results: list[dict],
        error: str = "",
        credential_result: tuple[bool, str, str] = (True, "", "ok"),
    ) -> None:
        self.results = results
        self.error = error
        self.credential_result = credential_result
        self.calls: list[list[str]] = []
        self.credential_checks = 0

    def check_credentials(self) -> tuple[bool, str, str]:
        self.credential_checks += 1
        return self.credential_result

    def validate_batch(self, emails: list[str], *, timeout_sec: int = 45):  # noqa: ANN001
        self.calls.append(emails)
        return self.results, self.error


def test_create_batch_snapshots_contacts_and_marks_checking(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, " Ada@Example.COM ")

    fake = FakeZeroBounce([])
    from app.services.email_verification_service import EmailVerificationService

    batch = EmailVerificationService(zerobounce=fake).create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )

    db_session.refresh(contact)
    assert fake.credential_checks == 1
    assert batch.state == "queued"
    assert batch.selected_count == 1
    assert batch.queued_count == 1
    assert batch.selected_contact_snapshots_json == [
        {"contact_id": str(contact.id), "email": "ada@example.com"}
    ]
    assert batch.result_summary_json == {
        "cached_count": 0,
        "paid_validation_count": 1,
        "skipped_count": 0,
    }
    assert contact.verification_batch_id == batch.id
    assert contact.verified_email_snapshot == "ada@example.com"
    assert contact.verification_applied is False
    assert contact.verification_status is None
    assert contact.verification_sub_status is None
    assert contact.verification_raw_json is None


def test_create_batch_inserts_batch_before_contact_fk_update(fk_db_session: Session) -> None:
    campaign = _campaign(fk_db_session)
    domain = _domain(fk_db_session, campaign.id)
    contact = _contact(fk_db_session, campaign, domain, " fk@example.com ")

    fake = FakeZeroBounce([])
    from app.services.email_verification_service import EmailVerificationService

    batch = EmailVerificationService(zerobounce=fake).create_batch(
        session=fk_db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )

    fk_db_session.refresh(contact)
    assert fk_db_session.get(VerificationBatch, batch.id) is not None
    assert contact.verification_batch_id == batch.id


def test_get_active_batch_finds_older_real_batch_after_newer_orphans(
    db_session: Session,
) -> None:
    from app.services.email_verification_service import EmailVerificationService

    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "active@example.com")
    now = utcnow()
    active_batch = VerificationBatch(
        campaign_id=campaign.id,
        state="queued",
        selected_count=1,
        queued_count=1,
        selected_contact_snapshots_json=[
            {"contact_id": str(contact.id), "email": "active@example.com"}
        ],
        created_at=now - timedelta(hours=1),
    )
    db_session.add(active_batch)
    db_session.flush()
    contact.verification_batch_id = active_batch.id
    contact.verified_email_snapshot = "active@example.com"
    contact.verification_applied = False
    db_session.add(contact)
    db_session.add_all(
        [
            VerificationBatch(
                campaign_id=campaign.id,
                state="queued",
                selected_count=1,
                queued_count=1,
                selected_contact_snapshots_json=[{"contact_id": str(uuid4()), "email": "orphan@example.com"}],
                created_at=now + timedelta(minutes=index),
            )
            for index in range(11)
        ]
    )
    db_session.commit()

    active = EmailVerificationService().get_active_batch(
        session=db_session,
        campaign_id=campaign.id,
    )

    assert active is not None
    assert active.id == active_batch.id


def test_run_batch_applies_fresh_cache_without_provider_call(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "cached@example.com")
    db_session.add(
        EmailVerificationCache(
            provider="zerobounce",
            normalized_email="cached@example.com",
            status="valid",
            sub_status=None,
            raw_json={"address": "cached@example.com", "status": "valid"},
            validated_at=utcnow(),
        )
    )
    db_session.commit()

    fake = FakeZeroBounce([])
    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    finished = service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(contact)
    assert fake.credential_checks == 0
    assert fake.calls == []
    assert finished.state == "succeeded"
    assert finished.verified_count == 1
    assert finished.valid_count == 1
    assert finished.invalid_count == 0
    assert contact.verification_status == "valid"
    assert contact.verification_applied is True
    assert contact.verification_batch_id is None
    assert contact.verification_raw_json == {
        "provider": "zerobounce",
        "source": "cache",
        "result": {"address": "cached@example.com", "status": "valid"},
    }


def test_run_batch_calls_zerobounce_for_paid_misses_and_writes_cache(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "paid@example.com")

    fake = FakeZeroBounce(
        [
            {
                "address": "paid@example.com",
                "status": "catch-all",
                "sub_status": "mailbox_quota_exceeded",
            }
        ]
    )
    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    finished = service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(contact)
    cache = db_session.exec(select(EmailVerificationCache)).one()
    assert fake.credential_checks == 1
    assert fake.calls == [["paid@example.com"]]
    assert finished.state == "succeeded"
    assert finished.verified_count == 1
    assert finished.valid_count == 0
    assert finished.invalid_count == 0
    assert contact.verification_status == "catch_all"
    assert contact.verification_sub_status == "mailbox_quota_exceeded"
    assert contact.verification_applied is True
    assert contact.verification_batch_id is None
    assert contact.verification_raw_json == {
        "provider": "zerobounce",
        "source": "api",
        "result": {
            "address": "paid@example.com",
            "status": "catch-all",
            "sub_status": "mailbox_quota_exceeded",
        },
    }
    assert cache.normalized_email == "paid@example.com"
    assert cache.status == "catch_all"
    assert cache.sub_status == "mailbox_quota_exceeded"


def test_run_batch_skips_writeback_when_selected_email_changed_after_snapshot(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "old@example.com")

    fake = FakeZeroBounce([{"address": "old@example.com", "status": "valid"}])
    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    contact.selected_email = "new@example.com"
    db_session.add(contact)
    db_session.commit()

    finished = service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(contact)
    assert fake.calls == []
    assert finished.state == "succeeded"
    assert finished.verified_count == 0
    assert finished.skipped_count == 1
    assert contact.verification_status is None
    assert contact.verification_applied is False
    assert contact.verification_batch_id is None


def test_run_batch_provider_technical_error_marks_paid_misses_failed_retryably(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "paid@example.com")

    fake = FakeZeroBounce([], error="zerobounce_rate_limited")
    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    finished = service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(contact)
    assert fake.calls == [["paid@example.com"]]
    assert finished.state == "failed"
    assert finished.verified_count == 0
    assert finished.skipped_count == 0
    assert contact.verification_status == "failed"
    assert contact.verification_sub_status == "zerobounce_rate_limited"
    assert contact.verification_applied is False
    assert contact.verification_batch_id is None
    assert contact.verification_raw_json == {
        "provider": "zerobounce",
        "error_code": "zerobounce_rate_limited",
    }


def test_create_batch_all_cache_hit_does_not_require_credentials(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "cached@example.com")
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

    fake = FakeZeroBounce(
        [],
        credential_result=(
            False,
            "zerobounce_api_key_missing",
            "ZeroBounce API key is missing.",
        ),
    )
    from app.services.email_verification_service import EmailVerificationService

    batch = EmailVerificationService(zerobounce=fake).create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )

    assert fake.credential_checks == 0
    assert batch.queued_count == 1
    assert batch.result_summary_json["cached_count"] == 1
    assert batch.result_summary_json["paid_validation_count"] == 0


def test_create_batch_summary_dedupes_paid_validation_count_for_shared_email(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    first = _contact(db_session, campaign, domain, "shared@example.com")
    second = _contact(db_session, campaign, domain, " SHARED@example.com ")
    fake = FakeZeroBounce([])

    from app.services.email_verification_service import EmailVerificationService

    batch = EmailVerificationService(zerobounce=fake).create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[first.id, second.id],
    )

    assert batch.queued_count == 2
    assert batch.result_summary_json["paid_validation_count"] == 1
    assert batch.result_summary_json["skipped_count"] == 0
    assert batch.selected_contact_snapshots_json == [
        {"contact_id": str(first.id), "email": "shared@example.com"},
        {"contact_id": str(second.id), "email": "shared@example.com"},
    ]


def test_run_batch_reuses_one_provider_result_for_duplicate_selected_email(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    first = _contact(db_session, campaign, domain, "shared@example.com")
    second = _contact(db_session, campaign, domain, " SHARED@example.com ")
    fake = FakeZeroBounce(
        [
            {
                "address": "shared@example.com",
                "status": "valid",
            }
        ]
    )

    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[first.id, second.id],
    )
    finished = service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(first)
    db_session.refresh(second)
    cache_rows = db_session.exec(select(EmailVerificationCache)).all()
    assert fake.calls == [["shared@example.com"]]
    assert finished.verified_count == 2
    assert finished.valid_count == 2
    assert first.verification_status == "valid"
    assert first.verification_applied is True
    assert first.verification_batch_id is None
    assert second.verification_status == "valid"
    assert second.verification_applied is True
    assert second.verification_batch_id is None
    assert len(cache_rows) == 1
    assert cache_rows[0].normalized_email == "shared@example.com"


def test_run_batch_preserves_create_time_skipped_count_for_duplicate_selected_id(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "duplicate@example.com")
    fake = FakeZeroBounce(
        [
            {
                "address": "duplicate@example.com",
                "status": "valid",
            }
        ]
    )

    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id, contact.id],
    )
    assert batch.selected_count == 2
    assert batch.queued_count == 1
    assert batch.result_summary_json["skipped_count"] == 1

    finished = service.run_batch(session=db_session, batch_id=batch.id)

    assert finished.verified_count == 1
    assert finished.skipped_count == 1
    assert finished.result_summary_json["skipped_count"] == 1


def test_run_batch_preserves_create_time_skipped_count_for_non_actionable_selection(
    db_session: Session,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    pending = _contact(db_session, campaign, domain, "pending@example.com")
    already_verified = _contact(db_session, campaign, domain, "valid@example.com")
    already_verified.verified_email_snapshot = "valid@example.com"
    already_verified.verification_status = "valid"
    already_verified.verification_applied = True
    already_verified.verified_at = utcnow()
    db_session.add(already_verified)
    db_session.commit()

    fake = FakeZeroBounce(
        [
            {
                "address": "pending@example.com",
                "status": "valid",
            }
        ]
    )

    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[pending.id, already_verified.id],
    )
    assert batch.selected_count == 2
    assert batch.queued_count == 1
    assert batch.result_summary_json["skipped_count"] == 1

    finished = service.run_batch(session=db_session, batch_id=batch.id)

    assert finished.verified_count == 1
    assert finished.skipped_count == 1
    assert finished.result_summary_json["skipped_count"] == 1


@pytest.mark.parametrize(
    ("credential_result", "expected_code"),
    [
        (
            (
                False,
                "zerobounce_api_key_missing",
                "ZeroBounce API key is missing.",
            ),
            "zerobounce_api_key_missing",
        ),
        (
            (
                False,
                "zerobounce_auth_failed",
                "ZeroBounce rejected the API key.",
            ),
            "zerobounce_auth_failed",
        ),
    ],
)
def test_create_batch_with_paid_validations_checks_credentials_and_maps_failures(
    db_session: Session,
    credential_result: tuple[bool, str, str],
    expected_code: str,
) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "paid@example.com")
    fake = FakeZeroBounce([], credential_result=credential_result)

    from app.services.email_verification_service import EmailVerificationService

    with pytest.raises(EmailVerificationServiceError) as exc_info:
        EmailVerificationService(zerobounce=fake).create_batch(
            session=db_session,
            campaign_id=campaign.id,
            contact_ids=[contact.id],
        )

    assert fake.credential_checks == 1
    assert exc_info.value.code == expected_code


def test_create_batch_rejects_zero_eligible_contacts(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = _contact(db_session, campaign, domain, "valid@example.com")
    contact.verified_email_snapshot = "valid@example.com"
    contact.verification_status = "valid"
    contact.verification_applied = True
    contact.verified_at = utcnow()
    db_session.add(contact)
    db_session.commit()

    fake = FakeZeroBounce([])
    from app.services.email_verification_service import EmailVerificationService

    with pytest.raises(EmailVerificationServiceError) as exc_info:
        EmailVerificationService(zerobounce=fake).create_batch(
            session=db_session,
            campaign_id=campaign.id,
            contact_ids=[contact.id],
        )

    assert fake.credential_checks == 0
    assert exc_info.value.code == "no_eligible_contacts"
