from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.models import Campaign, Company, Contact, ContactVerifyJob, Upload
from app.models.pipeline import ContactVerifyJobState


def _seed_campaign(session: Session) -> Campaign:
    c = Campaign(name="test")
    session.add(c)
    session.flush()
    return c


def _seed_company(session: Session, campaign: Campaign) -> Company:
    u = Upload(
        campaign_id=campaign.id,
        filename="f.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    session.add(u)
    session.flush()
    co = Company(
        upload_id=u.id,
        raw_url="https://acme.com",
        normalized_url="https://acme.com",
        domain="acme.com",
    )
    session.add(co)
    session.flush()
    return co


def _seed_contact(
    session: Session,
    company: Company,
    *,
    title_match: bool = True,
    email: str | None = "alice@acme.com",
    verification_status: str = "unverified",
) -> Contact:
    c = Contact(
        company_id=company.id,
        source_provider="snov",
        provider_person_id=str(uuid4()),
        first_name="Alice",
        last_name="Smith",
        title_match=title_match,
        email=email,
        verification_status=verification_status,
        pipeline_stage="email_revealed",
    )
    session.add(c)
    session.flush()
    return c


# ── Task 1: enqueue ───────────────────────────────────────────────────────────

def test_enqueue_creates_job_with_eligible_contacts(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c1 = _seed_contact(sqlite_session, company)
    sqlite_session.commit()

    job, skipped = ContactVerifyService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c1.id],
    )
    sqlite_session.commit()

    assert job.state == ContactVerifyJobState.QUEUED
    assert job.selected_count == 1
    assert job.skipped_count == 0
    assert str(c1.id) in job.contact_ids_json
    assert skipped == 0


def test_enqueue_skips_no_title_match(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(sqlite_session, company, title_match=False)
    sqlite_session.commit()

    job, skipped = ContactVerifyService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert job.contact_ids_json == []
    assert job.skipped_count == 1
    assert skipped == 1


def test_enqueue_skips_no_email(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(sqlite_session, company, email=None)
    sqlite_session.commit()

    job, skipped = ContactVerifyService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert job.contact_ids_json == []
    assert skipped == 1


def test_enqueue_skips_already_verified(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(sqlite_session, company, verification_status="valid")
    sqlite_session.commit()

    job, skipped = ContactVerifyService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert job.contact_ids_json == []
    assert skipped == 1


# ── Task 2: run_verify (wraps existing run_verify_job) ───────────────────────
# ZeroBounce batch response uses "address" field (not "email_address").

def _make_job(session: Session, campaign: Campaign, company: Company) -> tuple[Contact, ContactVerifyJob]:
    from app.services.contact_verify_service import ContactVerifyService
    contact = _seed_contact(session, company)
    session.commit()
    job, _ = ContactVerifyService().enqueue(
        session=session, campaign_id=campaign.id, contact_ids=[contact.id]
    )
    session.commit()
    return contact, job


def test_run_verify_writes_valid_status(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: ([{"address": "alice@acme.com", "status": "valid"}], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact, job = _make_job(sqlite_session, campaign, company)

    ContactVerifyService().run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    sqlite_session.refresh(contact)
    assert contact.verification_status == "valid"
    assert contact.verification_provider == "zerobounce"
    assert contact.pipeline_stage == "campaign_ready"
    assert contact.zerobounce_raw is not None

    sqlite_session.refresh(job)
    assert job.state == ContactVerifyJobState.SUCCEEDED
    assert job.verified_count == 1
    assert job.terminal_state is True
    assert job.finished_at is not None


def test_run_verify_invalid_does_not_set_campaign_ready(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: ([{"address": "alice@acme.com", "status": "invalid"}], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact, job = _make_job(sqlite_session, campaign, company)

    ContactVerifyService().run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    sqlite_session.refresh(contact)
    assert contact.verification_status == "invalid"
    assert contact.pipeline_stage == "email_revealed"


def test_run_verify_api_error_leaves_contacts_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: ([], "zerobounce_failed"),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact, job = _make_job(sqlite_session, campaign, company)

    ContactVerifyService().run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    sqlite_session.refresh(contact)
    assert contact.verification_status == "unverified"

    sqlite_session.refresh(job)
    assert job.state == ContactVerifyJobState.FAILED


def test_run_verify_empty_job_succeeds_without_api_call(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    called: list = []
    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: called.append(emails) or ([], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    # ineligible contact → empty job
    contact = _seed_contact(sqlite_session, company, title_match=False)
    sqlite_session.commit()
    job, _ = ContactVerifyService().enqueue(
        session=sqlite_session, campaign_id=campaign.id, contact_ids=[contact.id]
    )
    sqlite_session.commit()

    ContactVerifyService().run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    assert called == []
    sqlite_session.refresh(job)
    assert job.state == ContactVerifyJobState.SUCCEEDED


# ── Task 3: job stub signature ────────────────────────────────────────────────

def test_verify_contacts_task_accepts_job_id() -> None:
    import inspect
    from app.jobs.validation import verify_contacts

    fn = getattr(verify_contacts, "original_func", verify_contacts)
    sig = inspect.signature(fn)
    assert "job_id" in sig.parameters
    assert "contact_id" not in sig.parameters
