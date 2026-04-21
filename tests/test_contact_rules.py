from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import (
    create_title_rule,
    delete_title_rule,
    preview_title_rule_impact,
    queue_title_rule_impact_fetch,
    rematch_contacts,
)
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.contacts import TitleMatchRuleCreate
from app.models import Campaign, Company, ContactFetchJob, ProspectContact, TitleMatchRule, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState
from app.services.contact_service import match_title


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_company(
    session: Session,
    *,
    domain: str = "example.com",
    campaign: Campaign | None = None,
) -> Company:
    scoped_campaign = campaign or create_campaign(
        payload=CampaignCreate(name=f"Campaign {domain}"),
        session=session,
    )
    upload = Upload(
        filename="contacts.csv",
        checksum=str(uuid4()),
        valid_count=1,
        invalid_count=0,
        campaign_id=scoped_campaign.id,
    )
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
    return company


def _make_terminal_contact(
    session: Session,
    *,
    company: Company,
    title: str,
    email: str | None = None,
) -> ProspectContact:
    job = ContactFetchJob(
        company_id=company.id,
        provider="snov",
        state=ContactFetchJobState.SUCCEEDED,
        terminal_state=True,
        finished_at=_utcnow(),
    )
    session.add(job)
    session.flush()

    contact = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=job.id,
        source="snov",
        first_name="Test",
        last_name="Person",
        title=title,
        title_match=False,
        linkedin_url=None,
        email=email,
        verification_status="unverified",
        snov_confidence=None,
        snov_prospect_raw=None,
        apollo_prospect_raw=None,
        snov_email_raw=None,
    )
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


def test_match_title_normalizes_abbreviations() -> None:
    include_rules = [["vice president", "marketing"]]

    assert match_title("VP Marketing", include_rules, []) is True
    assert match_title("Vice President of Marketing", include_rules, []) is True
    assert match_title("GM", [["general manager"]], []) is True


def test_create_title_rule_rematches_without_implicit_fetch(sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="create-rule.example")
    _make_terminal_contact(sqlite_session, company=company, title="VP Marketing")

    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock_delay:
        result = create_title_rule(
            TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
            session=sqlite_session,
        )

    assert result.rule_type == "include"
    assert mock_delay.call_count == 0

    active_jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.company_id) == company.id,
                col(ContactFetchJob.terminal_state).is_(False),
            )
        ).all()
    )
    assert len(active_jobs) == 0

    refreshed_contact = sqlite_session.exec(
        select(ProspectContact).where(col(ProspectContact.company_id) == company.id)
    ).one()
    assert refreshed_contact.title_match is True


def test_delete_title_rule_rematches_without_implicit_fetch(sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="delete-rule.example")
    rule_include = TitleMatchRule(rule_type="include", keywords="marketing, vice president")
    rule_exclude = TitleMatchRule(rule_type="exclude", keywords="assistant")
    sqlite_session.add(rule_include)
    sqlite_session.add(rule_exclude)
    sqlite_session.commit()
    sqlite_session.refresh(rule_include)
    sqlite_session.refresh(rule_exclude)
    _make_terminal_contact(sqlite_session, company=company, title="Assistant VP Marketing")

    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock_delay:
        delete_title_rule(rule_id=rule_exclude.id, session=sqlite_session)

    assert mock_delay.call_count == 0

    active_jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.company_id) == company.id,
                col(ContactFetchJob.terminal_state).is_(False),
            )
        ).all()
    )
    assert len(active_jobs) == 0

    refreshed_contact = sqlite_session.exec(
        select(ProspectContact).where(col(ProspectContact.company_id) == company.id)
    ).one()
    assert refreshed_contact.title_match is True


def test_rematch_returns_zero_implicit_fetch_jobs(sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="rematch.example")
    _make_terminal_contact(sqlite_session, company=company, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )

    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock_delay:
        result = rematch_contacts(session=sqlite_session)

    assert result.updated >= 0
    assert result.fetch_jobs_queued == 0
    assert mock_delay.call_count == 0


def test_preview_title_rule_impact_scopes_campaign(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Campaign A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Campaign B"), session=sqlite_session)
    company_a = _make_company(sqlite_session, domain="a-impact.example", campaign=campaign_a)
    company_b = _make_company(sqlite_session, domain="b-impact.example", campaign=campaign_b)

    _make_terminal_contact(sqlite_session, company=company_a, title="VP Marketing")
    _make_terminal_contact(sqlite_session, company=company_b, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )

    preview_a = preview_title_rule_impact(campaign_id=campaign_a.id, session=sqlite_session)
    preview_b = preview_title_rule_impact(campaign_id=campaign_b.id, session=sqlite_session)

    assert preview_a.affected_company_count == 1
    assert preview_b.affected_company_count == 1
    assert preview_a.affected_contact_count == 1
    assert preview_b.affected_contact_count == 1
    assert company_a.id in preview_a.affected_company_ids
    assert company_b.id in preview_b.affected_company_ids


def test_queue_title_rule_impact_fetch_scopes_campaign(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Queue Campaign A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Queue Campaign B"), session=sqlite_session)
    company_a = _make_company(sqlite_session, domain="a-queue.example", campaign=campaign_a)
    _make_company(sqlite_session, domain="b-queue.example", campaign=campaign_b)

    _make_terminal_contact(sqlite_session, company=company_a, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )

    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock_delay:
        result = queue_title_rule_impact_fetch(campaign_id=campaign_a.id, session=sqlite_session)

    assert result.requested_count == 1
    assert result.queued_count == 1
    assert mock_delay.call_count == 1


def test_queue_title_rule_impact_fetch_supports_apollo_source(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Apollo Impact Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="apollo-impact.example", campaign=campaign)
    _make_terminal_contact(sqlite_session, company=company, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )

    with patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as mock_delay:
        result = queue_title_rule_impact_fetch(campaign_id=campaign.id, source="apollo", session=sqlite_session)

    assert result.requested_count == 1
    assert result.queued_count == 1
    assert mock_delay.call_count == 1


def test_queue_title_rule_impact_fetch_both_queues_snov_chain_only(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Both Chain Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="both-chain.example", campaign=campaign)
    _make_terminal_contact(sqlite_session, company=company, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )

    with (
        patch("app.api.routes.contacts.fetch_contacts.delay") as snov_delay,
        patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as apollo_delay,
    ):
        result = queue_title_rule_impact_fetch(campaign_id=campaign.id, source="both", session=sqlite_session)

    assert result.requested_count == 1
    assert result.queued_count == 1
    assert result.already_fetching_count == 0
    assert snov_delay.call_count == 1
    assert apollo_delay.call_count == 0
    jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(col(ContactFetchJob.company_id) == company.id).order_by(col(ContactFetchJob.created_at))
        )
    )
    assert jobs
    assert jobs[-1].provider == "snov"
    assert jobs[-1].next_provider == "apollo"


def test_queue_title_rule_impact_fetch_both_counts_snov_chain_activity(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Both Impact Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="both-impact.example", campaign=campaign)
    _make_terminal_contact(sqlite_session, company=company, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )
    sqlite_session.add(ContactFetchJob(company_id=company.id, provider="snov", state=ContactFetchJobState.RUNNING, terminal_state=False))
    sqlite_session.add(ContactFetchJob(company_id=company.id, provider="apollo", state=ContactFetchJobState.RUNNING, terminal_state=False))
    sqlite_session.commit()

    with (
        patch("app.api.routes.contacts.fetch_contacts.delay") as snov_delay,
        patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as apollo_delay,
    ):
        result = queue_title_rule_impact_fetch(campaign_id=campaign.id, source="both", session=sqlite_session)

    assert result.requested_count == 1
    assert result.queued_count == 0
    assert result.already_fetching_count == 1
    assert snov_delay.call_count == 0
    assert apollo_delay.call_count == 0


def test_queue_title_rule_impact_fetch_both_updates_active_snov_followup(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Both Active Chain Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="both-active-chain.example", campaign=campaign)
    _make_terminal_contact(sqlite_session, company=company, title="VP Marketing")
    create_title_rule(
        TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
        session=sqlite_session,
    )
    active = ContactFetchJob(company_id=company.id, provider="snov", state=ContactFetchJobState.RUNNING, terminal_state=False)
    sqlite_session.add(active)
    sqlite_session.commit()
    sqlite_session.refresh(active)

    with (
        patch("app.api.routes.contacts.fetch_contacts.delay") as snov_delay,
        patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as apollo_delay,
    ):
        result = queue_title_rule_impact_fetch(campaign_id=campaign.id, source="both", session=sqlite_session)

    assert result.requested_count == 1
    assert result.queued_count == 0
    assert result.already_fetching_count == 1
    assert snov_delay.call_count == 0
    assert apollo_delay.call_count == 0
    sqlite_session.refresh(active)
    assert active.next_provider == "apollo"


def test_queue_title_rule_impact_fetch_invalid_source_raises_422(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Invalid Source Campaign"), session=sqlite_session)
    with pytest.raises(HTTPException) as exc:
        queue_title_rule_impact_fetch(campaign_id=campaign.id, source="invalid", session=sqlite_session)
    assert exc.value.status_code == 422


def test_preview_title_rule_impact_missing_campaign_raises_404(sqlite_session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        preview_title_rule_impact(campaign_id=uuid4(), session=sqlite_session)
    assert exc.value.status_code == 404


def test_preview_title_rule_impact_include_stale_toggle(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Stale Preview Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="stale-preview.example", campaign=campaign)
    contact = _make_terminal_contact(
        sqlite_session,
        company=company,
        title="VP Marketing",
        email="vp@stale-preview.example",
    )
    contact.title_match = True
    contact.updated_at = _utcnow() - timedelta(days=45)
    sqlite_session.add(contact)
    sqlite_session.commit()

    without_stale = preview_title_rule_impact(campaign_id=campaign.id, session=sqlite_session)
    with_stale = preview_title_rule_impact(
        campaign_id=campaign.id,
        include_stale=True,
        stale_days=30,
        session=sqlite_session,
    )

    assert without_stale.affected_company_count == 0
    assert with_stale.affected_company_count == 1
    assert with_stale.stale_contact_count == 1


def test_queue_title_rule_impact_fetch_include_stale_queues_company(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Stale Queue Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="stale-queue.example", campaign=campaign)
    contact = _make_terminal_contact(
        sqlite_session,
        company=company,
        title="VP Marketing",
        email="vp@stale-queue.example",
    )
    contact.title_match = True
    contact.updated_at = _utcnow() - timedelta(days=60)
    sqlite_session.add(contact)
    sqlite_session.commit()

    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock_delay:
        result = queue_title_rule_impact_fetch(
            campaign_id=campaign.id,
            source="snov",
            include_stale=True,
            stale_days=30,
            session=sqlite_session,
        )

    assert result.requested_count == 1
    assert result.queued_count == 1
    assert mock_delay.call_count == 1


def test_preview_title_rule_impact_force_refresh_includes_fresh_emails(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Force Refresh Preview Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="force-preview.example", campaign=campaign)
    contact = _make_terminal_contact(
        sqlite_session,
        company=company,
        title="VP Marketing",
        email="vp@force-preview.example",
    )
    contact.title_match = True
    contact.updated_at = _utcnow()
    sqlite_session.add(contact)
    sqlite_session.commit()

    without_force = preview_title_rule_impact(campaign_id=campaign.id, session=sqlite_session)
    with_force = preview_title_rule_impact(campaign_id=campaign.id, force_refresh=True, session=sqlite_session)

    assert without_force.affected_company_count == 0
    assert with_force.affected_company_count == 1
    assert with_force.affected_contact_count == 1


def test_queue_title_rule_impact_fetch_force_refresh_queues_company(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Force Refresh Queue Campaign"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="force-queue.example", campaign=campaign)
    contact = _make_terminal_contact(
        sqlite_session,
        company=company,
        title="VP Marketing",
        email="vp@force-queue.example",
    )
    contact.title_match = True
    contact.updated_at = _utcnow()
    sqlite_session.add(contact)
    sqlite_session.commit()

    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock_delay:
        result = queue_title_rule_impact_fetch(
            campaign_id=campaign.id,
            source="snov",
            force_refresh=True,
            session=sqlite_session,
        )

    assert result.requested_count == 1
    assert result.queued_count == 1
    assert mock_delay.call_count == 1


def test_preview_title_rule_impact_source_defaults_for_apollo(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Apollo Freshness Defaults"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="apollo-freshness.example", campaign=campaign)
    contact = _make_terminal_contact(
        sqlite_session,
        company=company,
        title="VP Marketing",
        email="vp@apollo-freshness.example",
    )
    contact.title_match = True
    contact.source = "apollo"
    contact.updated_at = _utcnow() - timedelta(days=40)
    sqlite_session.add(contact)
    sqlite_session.commit()

    with_defaults = preview_title_rule_impact(
        campaign_id=campaign.id,
        source="apollo",
        include_stale=True,
        session=sqlite_session,
    )
    with_override = preview_title_rule_impact(
        campaign_id=campaign.id,
        source="apollo",
        include_stale=True,
        stale_days=30,
        session=sqlite_session,
    )

    assert with_defaults.affected_company_count == 0
    assert with_override.affected_company_count == 1


def test_preview_title_rule_impact_source_defaults_for_both(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Both Freshness Defaults"), session=sqlite_session)
    company = _make_company(sqlite_session, domain="both-freshness.example", campaign=campaign)
    snov_contact = _make_terminal_contact(
        sqlite_session,
        company=company,
        title="VP Marketing",
        email="snov@both-freshness.example",
    )
    apollo_contact = _make_terminal_contact(
        sqlite_session,
        company=company,
        title="VP Marketing",
        email="apollo@both-freshness.example",
    )
    snov_contact.title_match = True
    snov_contact.source = "snov"
    snov_contact.updated_at = _utcnow() - timedelta(days=35)
    apollo_contact.title_match = True
    apollo_contact.source = "apollo"
    apollo_contact.updated_at = _utcnow() - timedelta(days=35)
    sqlite_session.add(snov_contact)
    sqlite_session.add(apollo_contact)
    sqlite_session.commit()

    preview = preview_title_rule_impact(
        campaign_id=campaign.id,
        source="both",
        include_stale=True,
        session=sqlite_session,
    )

    assert preview.affected_company_count == 1
    assert preview.stale_contact_count == 1
    assert preview.stale_days is None
    assert preview.provider_default_days == {"snov": 30, "apollo": 45}
