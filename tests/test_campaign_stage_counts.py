from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.models import Campaign, ClassificationResult, Contact, UploadedDomain
from app.models.base import utcnow
from app.models.scrape import ScrapeResult


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _domain(campaign: Campaign, domain: str, *, scrape_status: str | None) -> UploadedDomain:
    return UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        dedupe_key=domain,
        scrape_status=scrape_status,
    )


def test_campaign_stage_counts_use_shared_real_pipeline_state(db_session: Session) -> None:
    from app.api.routes.campaigns import get_campaign_stage_counts

    campaign = Campaign(id=uuid4(), name="Counts Campaign")
    pending = _domain(campaign, "pending.example", scrape_status=None)
    queued = _domain(campaign, "queued.example", scrape_status="queued")
    running = _domain(campaign, "running.example", scrape_status="running")
    retryable = _domain(campaign, "retryable.example", scrape_status="failed")
    failed = _domain(campaign, "failed.example", scrape_status="failed")
    unclassified = _domain(campaign, "unclassified.example", scrape_status="succeeded")
    possible_pending = _domain(campaign, "possible-pending.example", scrape_status="succeeded")
    possible_running = _domain(campaign, "possible-running.example", scrape_status="succeeded")
    possible_done = _domain(campaign, "possible-done.example", scrape_status="succeeded")
    possible_no_match = _domain(campaign, "possible-no-match.example", scrape_status="succeeded")
    crap = _domain(campaign, "crap.example", scrape_status="succeeded")
    unknown = _domain(campaign, "unknown.example", scrape_status="succeeded")
    db_session.add_all(
        [
            campaign,
            pending,
            queued,
            running,
            retryable,
            failed,
            unclassified,
            possible_pending,
            possible_running,
            possible_done,
            possible_no_match,
            crap,
            unknown,
        ]
    )
    db_session.add_all(
        [
            ScrapeResult(campaign_id=campaign.id, domain_id=retryable.id, state="failed", retryable=True),
            ScrapeResult(campaign_id=campaign.id, domain_id=failed.id, state="failed", retryable=False),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=possible_pending.id,
                state="succeeded",
                predicted_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=possible_running.id,
                state="succeeded",
                predicted_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=possible_done.id,
                state="succeeded",
                predicted_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=possible_no_match.id,
                state="succeeded",
                predicted_label="crap",
                manual_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=crap.id,
                state="succeeded",
                predicted_label="crap",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=unknown.id,
                state="succeeded",
                predicted_label="unknown",
            ),
        ]
    )
    db_session.add_all(
        [
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_done.id,
                first_name="Done",
                last_name="Contact",
                selected_email="done@possible-done.example",
                verification_applied=False,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_done.id,
                first_name="Valid",
                last_name="Contact",
                selected_email="valid@possible-done.example",
                verification_status="valid",
                verification_applied=True,
                verified_email_snapshot="valid@possible-done.example",
                verified_at=utcnow(),
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=crap.id,
                first_name="Stale",
                last_name="Contact",
                selected_email="stale@crap.example",
                verification_status="valid",
                verification_applied=True,
                verified_email_snapshot="stale@crap.example",
                verified_at=utcnow() - timedelta(days=31),
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=crap.id,
                first_name="Failed",
                last_name="Contact",
                selected_email="failed@crap.example",
                verification_status="failed",
                verification_sub_status="zerobounce_failed",
                verification_applied=False,
                verified_email_snapshot="failed@crap.example",
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=unknown.id,
                first_name="Catch",
                last_name="All",
                selected_email="catch@unknown.example",
                verification_status="catch-all",
                verification_applied=True,
                verified_email_snapshot="catch@unknown.example",
                verified_at=utcnow(),
            ),
        ]
    )
    possible_running.fetch_status = "running"
    possible_done.fetch_status = "succeeded"
    possible_no_match.fetch_status = "succeeded"
    db_session.commit()

    out = get_campaign_stage_counts(campaign_id=campaign.id, session=db_session)

    assert out.scraping.badge == 4
    assert out.scraping.pending == 1
    assert out.scraping.queued == 1
    assert out.scraping.running == 1
    assert out.scraping.retryable_failed == 1
    assert out.ai_review.badge == 1
    assert out.ai_review.all == 7
    assert out.ai_review.unclassified == 1
    assert out.ai_review.possible == 4
    assert out.ai_review.crap == 1
    assert out.ai_review.unknown == 1
    assert out.contacts.all == 4
    assert out.contacts.pending == 1
    assert out.contacts.running == 1
    assert out.contacts.done == 1
    assert out.contacts.no_match == 1
    assert out.contacts.badge == 3
    assert out.contacts.contacts_found == 2
    assert out.contacts.emails_found == 2
    assert out.validation.total == 5
    assert out.validation.checking == 0
    assert out.validation.running == out.validation.checking
    assert out.validation.pending == 1
    assert out.validation.valid == 1
    assert out.validation.stale == 1
    assert out.validation.failed == 1
    assert out.validation.catch_all == 1
    assert out.validation.invalid == out.validation.undeliverable
    assert out.validation.badge == 3


def test_validation_counts_ignore_blank_selected_emails(db_session: Session) -> None:
    from app.api.routes.campaigns import get_campaign_stage_counts

    campaign = Campaign(id=uuid4(), name="Blank Email Counts")
    domain = _domain(campaign, "blank.example", scrape_status="succeeded")
    db_session.add_all([campaign, domain])
    db_session.add_all(
        [
            Contact(
                campaign_id=campaign.id,
                domain_id=domain.id,
                first_name="Pending",
                last_name="Contact",
                selected_email="pending@blank.example",
                verification_applied=False,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=domain.id,
                first_name="Blank",
                last_name="Contact",
                selected_email="",
                verification_applied=False,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=domain.id,
                first_name="Whitespace",
                last_name="Contact",
                selected_email="   ",
                verification_batch_id=uuid4(),
                verification_applied=False,
            ),
        ]
    )
    db_session.commit()

    out = get_campaign_stage_counts(campaign_id=campaign.id, session=db_session)

    assert out.validation.total == 1
    assert out.validation.pending == 1
    assert out.validation.badge == 1


def test_campaign_stage_counts_missing_campaign_404(db_session: Session) -> None:
    from app.api.routes.campaigns import get_campaign_stage_counts

    with pytest.raises(HTTPException) as exc:
        get_campaign_stage_counts(campaign_id=uuid4(), session=db_session)

    assert exc.value.status_code == 404
