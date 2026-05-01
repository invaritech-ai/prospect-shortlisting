from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import Session, col, select

from app.models import Campaign, Company, Contact, Upload


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_campaign(session: Session) -> Campaign:
    campaign = Campaign(name="test")
    session.add(campaign)
    session.flush()
    return campaign


def _seed_company(session: Session, campaign: Campaign) -> Company:
    upload = Upload(
        campaign_id=campaign.id,
        filename="f.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url="https://acme.com",
        normalized_url="https://acme.com",
        domain="acme.com",
    )
    session.add(company)
    session.flush()
    return company


def _seed_contact(
    session: Session,
    company: Company,
    *,
    title_match: bool = True,
    email: str | None = None,
    updated_at: datetime | None = None,
    source_provider: str = "snov",
    provider_person_id: str | None = None,
) -> Contact:
    contact = Contact(
        company_id=company.id,
        source_provider=source_provider,
        provider_person_id=provider_person_id or str(uuid4()),
        first_name="Alice",
        last_name="Smith",
        title="CMO",
        title_match=title_match,
        email=email,
    )
    session.add(contact)
    session.flush()
    if updated_at is not None:
        session.execute(
            __import__("sqlalchemy").update(Contact)
            .where(col(Contact.id) == contact.id)
            .values(updated_at=updated_at)
        )
        session.flush()
        session.refresh(contact)
    return contact


def test_enqueue_creates_batch_and_returns_eligible(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, title_match=True, email=None)
    sqlite_session.commit()

    batch, contact_ids, skipped = EmailRevealService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    sqlite_session.commit()

    assert batch.campaign_id == campaign.id
    assert len(contact_ids) == 1
    assert contact_ids[0] == contact.id
    assert skipped == 0


def test_enqueue_skips_no_title_match(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, title_match=False, email=None)
    sqlite_session.commit()

    batch, contact_ids, skipped = EmailRevealService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    sqlite_session.commit()

    assert len(contact_ids) == 0
    assert skipped == 1
    assert batch.skipped_revealed_count == 1


def test_enqueue_skips_fresh_email(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session,
        company,
        title_match=True,
        email="alice@acme.com",
        updated_at=_utcnow() - timedelta(days=5),
    )
    sqlite_session.commit()

    _batch, contact_ids, skipped = EmailRevealService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    sqlite_session.commit()

    assert len(contact_ids) == 0
    assert skipped == 1


def test_enqueue_includes_stale_email(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session,
        company,
        title_match=True,
        email="alice@acme.com",
        updated_at=_utcnow() - timedelta(days=31),
    )
    sqlite_session.commit()

    _batch, contact_ids, skipped = EmailRevealService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    sqlite_session.commit()

    assert len(contact_ids) == 1
    assert skipped == 0


def test_run_reveal_snov_writes_email(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: ([{"email": "alice@acme.com", "smtp_status": "valid"}], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session,
        company,
        source_provider="snov",
        provider_person_id="snov-hash-1",
    )
    sqlite_session.commit()

    EmailRevealService().run_reveal(engine=sqlite_session.bind, contact_id=str(contact.id))

    sqlite_session.refresh(contact)
    assert contact.email == "alice@acme.com"
    assert contact.email_provider == "snov"
    assert contact.email_confidence == 1.0
    assert contact.provider_email_status == "valid"
    assert contact.pipeline_stage == "email_revealed"


def test_run_reveal_snov_fallback_to_find_email_by_name(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: ([], ""),
    )
    monkeypatch.setattr(
        snov_mod.SnovClient,
        "find_email_by_name",
        lambda self, first, last, domain: ([{"email": "alice@acme.com", "smtp_status": "unknown"}], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session,
        company,
        source_provider="snov",
        provider_person_id="snov-hash-1",
    )
    sqlite_session.commit()

    EmailRevealService().run_reveal(engine=sqlite_session.bind, contact_id=str(contact.id))

    sqlite_session.refresh(contact)
    assert contact.email == "alice@acme.com"
    assert contact.email_confidence == 0.5
    assert contact.pipeline_stage == "email_revealed"


def test_run_reveal_snov_no_email_leaves_contact_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: ([], ""),
    )
    monkeypatch.setattr(
        snov_mod.SnovClient,
        "find_email_by_name",
        lambda self, first, last, domain: ([], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, source_provider="snov")
    sqlite_session.commit()

    EmailRevealService().run_reveal(engine=sqlite_session.bind, contact_id=str(contact.id))

    sqlite_session.refresh(contact)
    assert contact.email is None
    assert contact.pipeline_stage == "fetched"


def test_run_reveal_snov_api_error_leaves_contact_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: ([], "snov_rate_limited"),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, source_provider="snov")
    sqlite_session.commit()

    EmailRevealService().run_reveal(engine=sqlite_session.bind, contact_id=str(contact.id))

    sqlite_session.refresh(contact)
    assert contact.email is None


def test_run_reveal_apollo_writes_email(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        apollo_mod.ApolloClient,
        "reveal_email",
        lambda self, person_id: {"id": person_id, "email": "bob@acme.com"},
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "last_error_code", "", raising=False)

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session,
        company,
        source_provider="apollo",
        provider_person_id="apollo-id-1",
    )
    sqlite_session.commit()

    EmailRevealService().run_reveal(engine=sqlite_session.bind, contact_id=str(contact.id))

    sqlite_session.refresh(contact)
    assert contact.email == "bob@acme.com"
    assert contact.email_provider == "apollo"
    assert contact.email_confidence == 1.0
    assert contact.pipeline_stage == "email_revealed"


def test_run_reveal_apollo_no_email_leaves_contact_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        apollo_mod.ApolloClient,
        "reveal_email",
        lambda self, person_id: {"id": person_id, "email": None},
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "last_error_code", "", raising=False)

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, source_provider="apollo")
    sqlite_session.commit()

    EmailRevealService().run_reveal(engine=sqlite_session.bind, contact_id=str(contact.id))

    sqlite_session.refresh(contact)
    assert contact.email is None
    assert contact.pipeline_stage == "fetched"


def test_reveal_email_task_accepts_contact_id() -> None:
    import inspect
    from app.jobs.email_reveal import reveal_email

    fn = getattr(reveal_email, "original_func", reveal_email)
    sig = inspect.signature(fn)
    assert "contact_id" in sig.parameters


def test_enqueue_ignores_out_of_scope_contacts(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    other_campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    other_company = _seed_company(sqlite_session, other_campaign)
    contact = _seed_contact(sqlite_session, company)
    other_contact = _seed_contact(sqlite_session, other_company)
    sqlite_session.commit()

    batch, contact_ids, skipped = EmailRevealService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id, other_contact.id],
    )
    sqlite_session.commit()

    assert batch.selected_count == 2
    assert contact_ids == [contact.id]
    assert skipped == 1

