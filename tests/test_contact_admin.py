from __future__ import annotations

from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.routes.queue_admin import (
    get_contact_backlog,
    get_contact_runtime_control,
    replay_deferred_contact_attempts,
    retry_failed_contact_companies,
    update_contact_runtime_control,
)
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.contacts import (
    ContactReplayDeferredRequest,
    ContactRetryFailedRequest,
    ContactRuntimeControlUpdate,
)
from app.models import Company, ContactFetchJob, ContactProviderAttempt, ContactRevealBatch, Contact, Upload
from app.models.pipeline import (
    CompanyPipelineStage,
    ContactFetchJobState,
    ContactProviderAttemptState,
)
from app.services.contact_reveal_queue_service import ContactRevealQueueService


def _campaign_company(session: Session, *, domain: str) -> tuple[UUID, Company]:
    campaign = create_campaign(payload=CampaignCreate(name=f"Campaign {domain}"), session=session)
    upload = Upload(filename="contacts.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0, campaign_id=campaign.id)
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=CompanyPipelineStage.CONTACT_READY,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return campaign.id, company


def test_contact_runtime_control_can_be_read_and_updated(sqlite_session: Session) -> None:
    control = get_contact_runtime_control(session=sqlite_session)
    assert control.auto_enqueue_enabled is True

    with (
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as dispatch_delay,
        patch("app.tasks.contacts.reveal_contact_emails.delay") as reveal_delay,
    ):
        updated = update_contact_runtime_control(
            payload=ContactRuntimeControlUpdate(
                auto_enqueue_enabled=True,
                auto_enqueue_paused=True,
                auto_enqueue_max_batch_size=7,
                auto_enqueue_max_active_per_run=3,
                dispatcher_batch_size=11,
            ),
            session=sqlite_session,
        )

    dispatch_delay.assert_not_called()
    reveal_delay.assert_not_called()
    assert updated.auto_enqueue_paused is True
    assert updated.auto_enqueue_max_batch_size == 7
    assert updated.auto_enqueue_max_active_per_run == 3
    assert updated.dispatcher_batch_size == 11


def test_contact_reveal_batch_tracks_selected_and_grouped_counts(sqlite_session: Session) -> None:
    campaign_id, company = _campaign_company(sqlite_session, domain="reveal-metrics.example")
    contact_a = Contact(
        company_id=company.id,
        source_provider="snov",
        provider_person_id=f"pid-{uuid4()}-a",
        first_name="Test",
        last_name="Person",
        title="Director",
        title_match=True,
        linkedin_url="https://linkedin.example/shared",
    )
    contact_b = Contact(
        company_id=company.id,
        source_provider="apollo",
        provider_person_id=f"pid-{uuid4()}-b",
        first_name="Test",
        last_name="Person",
        title="Director",
        title_match=True,
        linkedin_url="https://linkedin.example/shared",
    )
    sqlite_session.add_all([contact_a, contact_b])
    sqlite_session.commit()

    with patch("app.tasks.contacts.reveal_contact_emails.delay") as reveal_delay:
        result = ContactRevealQueueService().enqueue_reveals(
            session=sqlite_session,
            campaign_id=campaign_id,
            discovered_contacts=[contact_a, contact_b],
            reveal_scope="selected",
        )

    assert result.selected_count == 2
    assert result.queued_count == 1
    assert result.batch_id is not None
    reveal_delay.assert_called_once()

    batch = sqlite_session.get(ContactRevealBatch, result.batch_id)
    assert batch is not None
    assert batch.selected_count == 2
    assert batch.requested_count == 1
    assert batch.queued_count == 1


def test_retry_failed_contact_companies_creates_new_batch(sqlite_session: Session) -> None:
    campaign_id, company = _campaign_company(sqlite_session, domain="retry.example")
    failed_job = ContactFetchJob(
        company_id=company.id,
        provider="snov",
        state=ContactFetchJobState.FAILED,
        terminal_state=True,
    )
    sqlite_session.add(failed_job)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as dispatch_delay:
        result = retry_failed_contact_companies(
            payload=ContactRetryFailedRequest(campaign_id=campaign_id, provider_mode="both"),
            session=sqlite_session,
        )

    dispatch_delay.assert_called_once()
    assert result.requested_count == 1
    assert result.queued_count == 1
    assert result.batch_id is not None


def test_replay_deferred_contact_attempts_requeues_parent_jobs(sqlite_session: Session) -> None:
    _campaign_id, company = _campaign_company(sqlite_session, domain="replay.example")
    job = ContactFetchJob(
        company_id=company.id,
        provider="snov",
        state=ContactFetchJobState.QUEUED,
        terminal_state=False,
    )
    sqlite_session.add(job)
    sqlite_session.commit()
    sqlite_session.refresh(job)

    attempt = ContactProviderAttempt(
        contact_fetch_job_id=job.id,
        provider="apollo",
        state=ContactProviderAttemptState.DEFERRED,
        terminal_state=False,
        deferred_reason="apollo_rate_limited",
    )
    sqlite_session.add(attempt)
    sqlite_session.commit()
    sqlite_session.refresh(attempt)

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as dispatch_delay:
        result = replay_deferred_contact_attempts(
            payload=ContactReplayDeferredRequest(provider="both", limit=10),
            session=sqlite_session,
        )

    dispatch_delay.assert_called_once()
    assert result.replayed_attempt_count == 1
    assert result.scheduled_job_count == 1
    sqlite_session.refresh(attempt)
    sqlite_session.refresh(job)
    assert attempt.state == ContactProviderAttemptState.QUEUED
    assert attempt.next_retry_at is None
    assert job.state == ContactFetchJobState.QUEUED


def test_contact_backlog_reports_job_and_attempt_counts(sqlite_session: Session) -> None:
    before = get_contact_backlog(session=sqlite_session)
    _campaign_id, company = _campaign_company(sqlite_session, domain="backlog.example")
    sqlite_session.add(
        ContactFetchJob(company_id=company.id, provider="snov", state=ContactFetchJobState.RUNNING, terminal_state=False)
    )
    sqlite_session.commit()

    summary = get_contact_backlog(session=sqlite_session)
    assert summary.job_counts.get("running", 0) == before.job_counts.get("running", 0) + 1
