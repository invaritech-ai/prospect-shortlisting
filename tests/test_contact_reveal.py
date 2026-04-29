"""Tests for S4 reveal pipeline: queue service, grouping, and state machine."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, col, select

from app.models import (
    Campaign,
    Company,
    ContactRevealAttempt,
    ContactRevealBatch,
    ContactRevealJob,
    Contact,
    Upload,
)
from app.models.pipeline import ContactFetchBatchState, ContactFetchJobState, ContactProviderAttemptState
from app.services.contact_reveal_queue_service import ContactRevealQueueService, discovered_group_key
from app.services.contact_reveal_service import ContactRevealService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_company(session: Session, *, domain: str) -> Company:
    upload = Upload(filename="reveal.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
    session.add(upload)
    session.flush()
    company = Company(upload_id=upload.id, raw_url=f"https://{domain}", normalized_url=f"https://{domain}", domain=domain)
    session.add(company)
    session.flush()
    return company


def _make_campaign(session: Session) -> Campaign:
    campaign = Campaign(name="Test Campaign")
    session.add(campaign)
    session.flush()
    return campaign


def _make_discovered(
    session: Session,
    *,
    company: Company,
    provider: str = "apollo",
    first_name: str = "Alice",
    last_name: str = "Smith",
    title: str = "VP Engineering",
    linkedin_url: str | None = None,
    title_match: bool = True,
) -> Contact:
    contact = Contact(
        company_id=company.id,
        source_provider=provider,
        provider_person_id=str(uuid4()),
        first_name=first_name,
        last_name=last_name,
        title=title,
        title_match=title_match,
        linkedin_url=linkedin_url,
        is_active=True,
    )
    session.add(contact)
    session.flush()
    return contact


def _enable_reveal(session: Session) -> None:
    from app.services.contact_runtime_service import ContactRuntimeService
    ctrl = ContactRuntimeService().get_or_create_control(session)
    ctrl.reveal_enabled = True
    ctrl.reveal_paused = False
    session.add(ctrl)
    session.flush()


# ---------------------------------------------------------------------------
# discovered_group_key() — pure function
# ---------------------------------------------------------------------------


def test_group_key_prefers_linkedin():
    contact = Contact(
        company_id=uuid4(),
        source_provider="apollo",
        provider_person_id="p1",
        first_name="Alice",
        last_name="Smith",
        title="VP Engineering",
        linkedin_url="https://linkedin.com/in/alice",
    )
    key = discovered_group_key(contact)
    assert key == "linkedin:https://linkedin.com/in/alice"


def test_group_key_falls_back_to_name_title():
    contact = Contact(
        company_id=uuid4(),
        source_provider="apollo",
        provider_person_id="p1",
        first_name="Alice",
        last_name="Smith",
        title="VP Engineering",
        linkedin_url=None,
    )
    key = discovered_group_key(contact)
    assert key == "name_title:alice|smith|vp engineering"


def test_group_key_falls_back_to_provider_id():
    contact = Contact(
        company_id=uuid4(),
        source_provider="apollo",
        provider_person_id="person-abc",
        first_name="Alice",
        last_name="",
        title=None,
        linkedin_url=None,
    )
    key = discovered_group_key(contact)
    assert key == "provider:apollo:person-abc"


# ---------------------------------------------------------------------------
# ContactRevealQueueService.enqueue_reveals()
# ---------------------------------------------------------------------------


def test_reveal_batch_queues_jobs_for_campaign(sqlite_engine, sqlite_session: Session):
    _enable_reveal(sqlite_session)
    campaign = _make_campaign(sqlite_session)
    company = _make_company(sqlite_session, domain="reveal-test.com")
    contact = _make_discovered(sqlite_session, company=company)
    sqlite_session.commit()

    with patch.object(ContactRevealQueueService, "_dispatch_jobs"):
        result = ContactRevealQueueService().enqueue_reveals(
            session=sqlite_session,
            campaign_id=campaign.id,
            discovered_contacts=[contact],
            reveal_scope="selected",
        )

    assert result.selected_count == 1
    assert result.queued_count == 1
    assert result.batch_id is not None

    batch = sqlite_session.get(ContactRevealBatch, result.batch_id)
    assert batch is not None
    assert batch.state == ContactFetchBatchState.QUEUED
    assert batch.queued_count == 1


def test_reveal_job_groups_contacts_by_linkedin_url(sqlite_engine, sqlite_session: Session):
    _enable_reveal(sqlite_session)
    campaign = _make_campaign(sqlite_session)
    company = _make_company(sqlite_session, domain="group-linkedin.com")
    linkedin = "https://linkedin.com/in/shared-profile"
    c1 = _make_discovered(sqlite_session, company=company, provider="apollo", linkedin_url=linkedin)
    c2 = _make_discovered(sqlite_session, company=company, provider="snov", linkedin_url=linkedin)
    sqlite_session.commit()

    with patch.object(ContactRevealQueueService, "_dispatch_jobs"):
        result = ContactRevealQueueService().enqueue_reveals(
            session=sqlite_session,
            campaign_id=campaign.id,
            discovered_contacts=[c1, c2],
            reveal_scope="selected",
        )

    assert result.selected_count == 2
    assert result.queued_count == 1, "Two contacts with same LinkedIn → one reveal job"

    job = sqlite_session.exec(
        select(ContactRevealJob).where(col(ContactRevealJob.contact_reveal_batch_id) == result.batch_id)
    ).first()
    assert job is not None
    assert job.group_key == f"linkedin:{linkedin}"
    assert len(job.discovered_contact_ids_json) == 2


def test_reveal_job_groups_by_name_title_when_no_linkedin(sqlite_engine, sqlite_session: Session):
    _enable_reveal(sqlite_session)
    campaign = _make_campaign(sqlite_session)
    company = _make_company(sqlite_session, domain="group-nametitle.com")
    c1 = _make_discovered(sqlite_session, company=company, provider="apollo", first_name="Bob", last_name="Jones", title="CTO")
    c2 = _make_discovered(sqlite_session, company=company, provider="snov", first_name="Bob", last_name="Jones", title="CTO")
    sqlite_session.commit()

    with patch.object(ContactRevealQueueService, "_dispatch_jobs"):
        result = ContactRevealQueueService().enqueue_reveals(
            session=sqlite_session,
            campaign_id=campaign.id,
            discovered_contacts=[c1, c2],
            reveal_scope="selected",
        )

    assert result.queued_count == 1
    job = sqlite_session.exec(
        select(ContactRevealJob).where(col(ContactRevealJob.contact_reveal_batch_id) == result.batch_id)
    ).first()
    assert job is not None
    assert job.group_key.startswith("name_title:")


def test_reveal_batch_skips_already_active_reveal_job(sqlite_engine, sqlite_session: Session):
    _enable_reveal(sqlite_session)
    campaign = _make_campaign(sqlite_session)
    company = _make_company(sqlite_session, domain="skip-active.com")
    contact = _make_discovered(sqlite_session, company=company, linkedin_url="https://linkedin.com/in/active")

    existing_batch = ContactRevealBatch(
        campaign_id=campaign.id,
        trigger_source="manual",
        reveal_scope="selected",
        state=ContactFetchBatchState.RUNNING,
        selected_count=1,
        requested_count=1,
        queued_count=1,
        already_revealing_count=0,
        skipped_revealed_count=0,
    )
    sqlite_session.add(existing_batch)
    sqlite_session.flush()
    existing_job = ContactRevealJob(
        contact_reveal_batch_id=existing_batch.id,
        company_id=company.id,
        group_key=f"linkedin:{contact.linkedin_url}",
        discovered_contact_ids_json=[str(contact.id)],
        requested_providers_json=["apollo"],
        state=ContactFetchJobState.RUNNING,
        terminal_state=False,
    )
    sqlite_session.add(existing_job)
    sqlite_session.commit()

    with patch.object(ContactRevealQueueService, "_dispatch_jobs"):
        result = ContactRevealQueueService().enqueue_reveals(
            session=sqlite_session,
            campaign_id=campaign.id,
            discovered_contacts=[contact],
            reveal_scope="selected",
        )

    assert result.queued_count == 0
    assert result.already_revealing_count == 1


def test_reveal_batch_skips_already_revealed_contacts(sqlite_engine, sqlite_session: Session):
    _enable_reveal(sqlite_session)
    campaign = _make_campaign(sqlite_session)
    company = _make_company(sqlite_session, domain="skip-revealed.com")
    contact = _make_discovered(sqlite_session, company=company, first_name="Dana", last_name="Lee", title="CEO")

    from app.models import ContactFetchJob
    fetch_job = ContactFetchJob(company_id=company.id, provider="apollo", state=ContactFetchJobState.SUCCEEDED, terminal_state=True)
    sqlite_session.add(fetch_job)
    sqlite_session.flush()
    existing_prospect = Contact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        source_provider="apollo",
        provider_person_id=f"apollo-{uuid4()}",
        first_name="Dana",
        last_name="Lee",
        title="CEO",
        email="dana@skip-revealed.com",
    )
    sqlite_session.add(existing_prospect)
    sqlite_session.commit()

    with patch.object(ContactRevealQueueService, "_dispatch_jobs"):
        result = ContactRevealQueueService().enqueue_reveals(
            session=sqlite_session,
            campaign_id=campaign.id,
            discovered_contacts=[contact],
            reveal_scope="selected",
        )

    assert result.queued_count == 0
    assert result.skipped_revealed_count == 1


# ---------------------------------------------------------------------------
# ContactRevealService state machine
# ---------------------------------------------------------------------------


def test_reveal_batch_completes_when_all_jobs_succeed(sqlite_engine, sqlite_session: Session):
    campaign = _make_campaign(sqlite_session)
    company = _make_company(sqlite_session, domain="batch-complete.com")

    batch = ContactRevealBatch(
        campaign_id=campaign.id,
        trigger_source="manual",
        reveal_scope="selected",
        state=ContactFetchBatchState.RUNNING,
        selected_count=1,
        requested_count=1,
        queued_count=1,
        already_revealing_count=0,
        skipped_revealed_count=0,
    )
    sqlite_session.add(batch)
    sqlite_session.flush()

    job = ContactRevealJob(
        contact_reveal_batch_id=batch.id,
        company_id=company.id,
        group_key="linkedin:https://linkedin.com/in/batch-test",
        discovered_contact_ids_json=[str(uuid4())],
        requested_providers_json=["apollo"],
        state=ContactFetchJobState.RUNNING,
        terminal_state=False,
    )
    sqlite_session.add(job)
    sqlite_session.flush()

    attempt = ContactRevealAttempt(
        contact_reveal_job_id=job.id,
        provider="apollo",
        sequence_index=0,
        state=ContactProviderAttemptState.SUCCEEDED,
        terminal_state=True,
        revealed_count=1,
    )
    sqlite_session.add(attempt)
    sqlite_session.commit()

    svc = ContactRevealService()
    finalized = svc._finalize_reveal_job(session=sqlite_session, job=job)
    svc._refresh_reveal_batch_state(sqlite_session, batch_id=batch.id)
    sqlite_session.commit()

    assert finalized.state == ContactFetchJobState.SUCCEEDED
    assert finalized.terminal_state is True
    assert finalized.revealed_count == 1

    sqlite_session.refresh(batch)
    assert batch.state == ContactFetchBatchState.SUCCEEDED


def test_reveal_batch_fails_when_all_jobs_dead(sqlite_engine, sqlite_session: Session):
    campaign = _make_campaign(sqlite_session)
    company = _make_company(sqlite_session, domain="batch-fail.com")

    batch = ContactRevealBatch(
        campaign_id=campaign.id,
        trigger_source="manual",
        reveal_scope="selected",
        state=ContactFetchBatchState.RUNNING,
        selected_count=1,
        requested_count=1,
        queued_count=1,
        already_revealing_count=0,
        skipped_revealed_count=0,
    )
    sqlite_session.add(batch)
    sqlite_session.flush()

    job = ContactRevealJob(
        contact_reveal_batch_id=batch.id,
        company_id=company.id,
        group_key="provider:apollo:xyz",
        discovered_contact_ids_json=[str(uuid4())],
        requested_providers_json=["apollo"],
        state=ContactFetchJobState.RUNNING,
        terminal_state=False,
    )
    sqlite_session.add(job)
    sqlite_session.flush()

    attempt = ContactRevealAttempt(
        contact_reveal_job_id=job.id,
        provider="apollo",
        sequence_index=0,
        state=ContactProviderAttemptState.DEAD,
        terminal_state=True,
        revealed_count=0,
        last_error_code="no_email_found",
    )
    sqlite_session.add(attempt)
    sqlite_session.commit()

    svc = ContactRevealService()
    finalized = svc._finalize_reveal_job(session=sqlite_session, job=job)
    svc._refresh_reveal_batch_state(sqlite_session, batch_id=batch.id)
    sqlite_session.commit()

    assert finalized.state == ContactFetchJobState.DEAD
    assert finalized.terminal_state is True

    sqlite_session.refresh(batch)
    assert batch.state == ContactFetchBatchState.FAILED
