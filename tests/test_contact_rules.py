from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, col, select

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import (
    create_title_rule,
    delete_title_rule,
    rematch_contacts,
    seed_rules,
)
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.contacts import TitleMatchRuleCreate
from app.models import Campaign, Company, Contact, TitleMatchRule, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJob
from app.services.title_match_service import match_title


def _seed(session: Session, *, domain: str = "example.com") -> tuple[Campaign, Company]:
    campaign = create_campaign(payload=CampaignCreate(name=f"Campaign {domain}"), session=session)
    upload = Upload(filename="t.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0, campaign_id=campaign.id)
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
    session.flush()
    return campaign, company


def _add_discovered(session: Session, *, company: Company, title: str) -> Contact:
    dc = Contact(
        company_id=company.id,
        source_provider="snov",
        provider_person_id=f"pid-{uuid4()}",
        first_name="Test",
        last_name="Person",
        title=title,
        title_match=False,
    )
    session.add(dc)
    session.commit()
    session.refresh(dc)
    return dc


def test_match_title_normalizes_abbreviations() -> None:
    include_rules = [["vice president", "marketing"]]

    assert match_title("VP Marketing", include_rules, []) is True
    assert match_title("Vice President of Marketing", include_rules, []) is True
    assert match_title("GM", [["general manager"]], []) is True


def test_create_title_rule_rematches_discovered_without_fetch(sqlite_session: Session) -> None:
    campaign, company = _seed(sqlite_session, domain="create-rule.example")
    dc = _add_discovered(sqlite_session, company=company, title="VP Marketing")

    with (
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_fetch,
        patch("app.services.contact_reveal_queue_service.ContactRevealQueueService.enqueue_reveals") as mock_reveal,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        result = create_title_rule(
            TitleMatchRuleCreate(campaign_id=campaign.id, rule_type="include", keywords="marketing, vice president"),
            session=sqlite_session,
        )

    assert result.rule_type == "include"
    mock_fetch.assert_not_called()
    mock_reveal.assert_not_called()
    mock_verify.assert_not_called()

    active_jobs = list(sqlite_session.exec(
        select(ContactFetchJob).where(
            col(ContactFetchJob.company_id) == company.id,
            col(ContactFetchJob.terminal_state).is_(False),
        )
    ).all())
    assert len(active_jobs) == 0

    sqlite_session.refresh(dc)
    assert dc.title_match is True


def test_delete_title_rule_rematches_discovered_without_fetch(sqlite_session: Session) -> None:
    campaign, company = _seed(sqlite_session, domain="delete-rule.example")
    rule_include = TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="marketing, vice president")
    rule_exclude = TitleMatchRule(campaign_id=campaign.id, rule_type="exclude", keywords="assistant")
    sqlite_session.add(rule_include)
    sqlite_session.add(rule_exclude)
    sqlite_session.commit()
    sqlite_session.refresh(rule_exclude)
    dc = _add_discovered(sqlite_session, company=company, title="Assistant VP Marketing")

    with (
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_fetch,
        patch("app.services.contact_reveal_queue_service.ContactRevealQueueService.enqueue_reveals") as mock_reveal,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        delete_title_rule(rule_id=rule_exclude.id, campaign_id=campaign.id, session=sqlite_session)

    mock_fetch.assert_not_called()
    mock_reveal.assert_not_called()
    mock_verify.assert_not_called()

    active_jobs = list(sqlite_session.exec(
        select(ContactFetchJob).where(
            col(ContactFetchJob.company_id) == company.id,
            col(ContactFetchJob.terminal_state).is_(False),
        )
    ).all())
    assert len(active_jobs) == 0

    sqlite_session.refresh(dc)
    assert dc.title_match is True


def test_rematch_returns_zero_implicit_fetch_jobs(sqlite_session: Session) -> None:
    campaign, company = _seed(sqlite_session, domain="rematch.example")
    _add_discovered(sqlite_session, company=company, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(campaign_id=campaign.id, rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )

    with (
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_fetch,
        patch("app.services.contact_reveal_queue_service.ContactRevealQueueService.enqueue_reveals") as mock_reveal,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        result = rematch_contacts(campaign_id=campaign.id, session=sqlite_session)

    assert result.updated >= 0
    assert result.fetch_jobs_queued == 0
    mock_fetch.assert_not_called()
    mock_reveal.assert_not_called()
    mock_verify.assert_not_called()


def test_seed_rules_does_not_dispatch_fetch_reveal_or_verify(sqlite_session: Session) -> None:
    campaign, _company = _seed(sqlite_session, domain="seed-rule.example")

    with (
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_fetch,
        patch("app.services.contact_reveal_queue_service.ContactRevealQueueService.enqueue_reveals") as mock_reveal,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        result = seed_rules(campaign_id=campaign.id, session=sqlite_session)

    assert result.inserted > 0
    mock_fetch.assert_not_called()
    mock_reveal.assert_not_called()
    mock_verify.assert_not_called()
