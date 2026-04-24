from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import (
    fetch_contacts_for_company,
    fetch_contacts_selected,
    get_contact_counts,
    list_all_contacts,
    list_contacts_by_company,
    verify_contacts,
)
from app.api.routes.discovered_contacts import (
    list_discovered_contact_ids,
    list_discovered_contacts,
    reveal_discovered_contact_emails,
)
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.contacts import (
    BulkContactFetchRequest,
    ContactRevealRequest,
    ContactVerifyRequest,
)
from app.models import Campaign, Company, ContactFetchJob, DiscoveredContact, ProspectContact, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState


def _seed_company(session: Session, *, campaign: Campaign, domain: str) -> Company:
    upload = Upload(filename=f"{domain}.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0, campaign_id=campaign.id)
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


def _seed_campaign_company(session: Session, *, domain: str, campaign_name: str) -> tuple[Campaign, Company]:
    campaign = create_campaign(payload=CampaignCreate(name=f"{campaign_name} {domain} {uuid4()}"), session=session)
    company = _seed_company(session, campaign=campaign, domain=domain)
    return campaign, company


def _seed_discovered_contact(
    session: Session,
    *,
    company: Company,
    title_match: bool,
    title: str = "Director",
    first_name: str = "Test",
    last_name: str = "Person",
) -> DiscoveredContact:
    contact = DiscoveredContact(
        company_id=company.id,
        provider="snov",
        provider_person_id=f"pid-{uuid4()}",
        first_name=first_name,
        last_name=last_name,
        title=title,
        title_match=title_match,
    )
    session.add(contact)
    session.flush()
    return contact


def _seed_prospect_contact(
    session: Session,
    *,
    company: Company,
    title_match: bool,
    email: str | None,
    verification_status: str = "unverified",
    title: str = "Director",
    first_name: str = "Test",
    last_name: str = "Person",
) -> ProspectContact:
    fetch_job = ContactFetchJob(company_id=company.id, provider="snov", state=ContactFetchJobState.SUCCEEDED, terminal_state=True)
    session.add(fetch_job)
    session.flush()
    contact = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        source="snov",
        first_name=first_name,
        last_name=last_name,
        title=title,
        title_match=title_match,
        email=email,
        verification_status=verification_status,
    )
    session.add(contact)
    session.flush()
    return contact


def test_s3_fetch_routes_only_dispatch_fetch_jobs(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_company(sqlite_session, domain="fetch.example", campaign_name="Fetch Contract")
    sqlite_session.commit()

    with (
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch,
        patch("app.tasks.contacts.reveal_contact_emails.delay") as mock_reveal,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        result_for_company = fetch_contacts_for_company(
            company_id=company.id,
            campaign_id=campaign.id,
            force_refresh=False,
            session=sqlite_session,
        )
        result_selected = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign.id, company_ids=[company.id]),
            session=sqlite_session,
            x_idempotency_key=None,
        )

    assert result_for_company.requested_count == 1
    assert result_selected.requested_count == 1
    assert mock_dispatch.call_count == 2
    mock_reveal.assert_not_called()
    mock_verify.assert_not_called()


def test_s3_read_routes_do_not_touch_provider_work(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_company(sqlite_session, domain="read.example", campaign_name="Read Contract")
    _seed_prospect_contact(sqlite_session, company=company, title_match=True, email="test@read.example")
    sqlite_session.commit()

    with (
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch,
        patch("app.tasks.contacts.reveal_contact_emails.delay") as mock_reveal,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        contacts = list_all_contacts(session=sqlite_session, campaign_id=campaign.id)
        companies = list_contacts_by_company(session=sqlite_session, campaign_id=campaign.id)
        counts = get_contact_counts(session=sqlite_session, campaign_id=campaign.id)

    assert contacts.total == 1
    assert companies.total == 1
    assert counts.total == 1
    mock_dispatch.assert_not_called()
    mock_reveal.assert_not_called()
    mock_verify.assert_not_called()


def test_s4_reveal_route_scopes_to_title_matched_discovered_contacts(sqlite_session: Session) -> None:
    campaign_a, company_a = _seed_campaign_company(sqlite_session, domain="reveal-a.example", campaign_name="Reveal A")
    campaign_b, company_b = _seed_campaign_company(sqlite_session, domain="reveal-b.example", campaign_name="Reveal B")
    matched = _seed_discovered_contact(sqlite_session, company=company_a, title_match=True, title="Director")
    other_campaign = _seed_discovered_contact(sqlite_session, company=company_b, title_match=True, title="Director")
    sqlite_session.commit()

    fake_result = SimpleNamespace(
        batch_id=uuid4(),
        selected_count=1,
        queued_count=1,
        already_revealing_count=0,
        skipped_revealed_count=0,
    )

    with (
        patch("app.api.routes.discovered_contacts.ContactRevealQueueService.enqueue_reveals", return_value=fake_result) as mock_enqueue,
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        result = reveal_discovered_contact_emails(
            ContactRevealRequest(
                campaign_id=campaign_a.id,
                discovered_contact_ids=[matched.id, other_campaign.id],
            ),
            session=sqlite_session,
            x_idempotency_key=None,
        )

    assert result.selected_count == 1
    assert result.queued_count == 1
    call_kwargs = mock_enqueue.call_args.kwargs
    assert call_kwargs["campaign_id"] == campaign_a.id
    assert [contact.id for contact in call_kwargs["discovered_contacts"]] == [matched.id]
    assert call_kwargs["reveal_scope"] == "selected"
    mock_dispatch.assert_not_called()
    mock_verify.assert_not_called()


def test_s4_list_route_handles_utc_freshness(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_company(sqlite_session, domain="list-fresh.example", campaign_name="List Fresh")
    _seed_discovered_contact(sqlite_session, company=company, title_match=True, title="Director")
    sqlite_session.commit()

    result = list_discovered_contacts(
        campaign_id=campaign.id,
        title_match=None,
        provider=None,
        company_id=None,
        search=None,
        limit=50,
        offset=0,
        letters=None,
        count_by_letters=False,
        session=sqlite_session,
    )

    assert result.total == 1
    assert result.items[0].freshness_status == "fresh"
    assert result.items[0].last_seen_at.tzinfo is not None
    assert result.items[0].created_at.tzinfo is not None


def test_s4_list_route_honors_sorting(sqlite_session: Session) -> None:
    campaign, company_a = _seed_campaign_company(sqlite_session, domain="beta.example", campaign_name="Sort A")
    company_b = _seed_company(sqlite_session, campaign=campaign, domain="alpha.example")
    _seed_discovered_contact(sqlite_session, company=company_a, title_match=True, first_name="Beta")
    _seed_discovered_contact(sqlite_session, company=company_b, title_match=True, first_name="Alpha")
    sqlite_session.commit()

    result = list_discovered_contacts(
        campaign_id=campaign.id,
        title_match=True,
        provider=None,
        company_id=None,
        search=None,
        limit=50,
        offset=0,
        sort_by="first_name",
        sort_dir="asc",
        letters=None,
        count_by_letters=False,
        session=sqlite_session,
    )

    assert [item.first_name for item in result.items] == ["Alpha", "Beta"]


def test_s4_ids_route_matches_list_filters_and_campaign_scope(sqlite_session: Session) -> None:
    campaign_a, company_a = _seed_campaign_company(sqlite_session, domain="alpha.example", campaign_name="Reveal Filter A")
    company_b = _seed_company(sqlite_session, campaign=campaign_a, domain="bravo.example")
    _, company_c = _seed_campaign_company(sqlite_session, domain="alpha-other.example", campaign_name="Reveal Filter Other")
    matched = _seed_discovered_contact(sqlite_session, company=company_a, title_match=True, first_name="Alice")
    _seed_discovered_contact(sqlite_session, company=company_b, title_match=True, first_name="Alice")
    _seed_discovered_contact(sqlite_session, company=company_a, title_match=False, first_name="Alice")
    _seed_discovered_contact(sqlite_session, company=company_c, title_match=True, first_name="Alice")
    sqlite_session.commit()

    filtered_list = list_discovered_contacts(
        campaign_id=campaign_a.id,
        title_match=True,
        provider=None,
        company_id=None,
        search="alice",
        limit=50,
        offset=0,
        sort_by="first_name",
        sort_dir="asc",
        letters="a",
        count_by_letters=False,
        session=sqlite_session,
    )
    filtered_ids = list_discovered_contact_ids(
        campaign_id=campaign_a.id,
        title_match=True,
        provider=None,
        company_id=None,
        search="alice",
        letters="a",
        session=sqlite_session,
    )

    assert filtered_ids.total == 1
    assert filtered_ids.ids == [matched.id]
    assert [item.id for item in filtered_list.items] == filtered_ids.ids


def test_s4_list_route_returns_letter_counts(sqlite_session: Session) -> None:
    campaign, company_a = _seed_campaign_company(sqlite_session, domain="alpha.example", campaign_name="Letter Counts A")
    company_b = _seed_company(sqlite_session, campaign=campaign, domain="bravo.example")
    _seed_discovered_contact(sqlite_session, company=company_a, title_match=True, first_name="Alice")
    _seed_discovered_contact(sqlite_session, company=company_b, title_match=True, first_name="Bob")
    sqlite_session.commit()

    result = list_discovered_contacts(
        campaign_id=campaign.id,
        title_match=True,
        provider=None,
        company_id=None,
        search=None,
        limit=1,
        offset=0,
        sort_by="last_seen_at",
        sort_dir="desc",
        letters=None,
        count_by_letters=True,
        session=sqlite_session,
    )

    assert result.letter_counts is not None
    assert result.letter_counts["a"] == 1
    assert result.letter_counts["b"] == 1


def test_s4_reveal_route_rejects_ineligible_contacts(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_company(sqlite_session, domain="reveal-reject.example", campaign_name="Reveal Reject")
    ineligible = _seed_discovered_contact(sqlite_session, company=company, title_match=False, title="Director")
    sqlite_session.commit()

    with (
        patch("app.api.routes.discovered_contacts.ContactRevealQueueService.enqueue_reveals") as mock_enqueue,
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch,
        patch("app.tasks.contacts.verify_contacts_batch.delay") as mock_verify,
    ):
        with pytest.raises(HTTPException) as excinfo:
            reveal_discovered_contact_emails(
                ContactRevealRequest(
                    campaign_id=campaign.id,
                    discovered_contact_ids=[ineligible.id],
                ),
                session=sqlite_session,
                x_idempotency_key=None,
            )

    assert excinfo.value.status_code == 422
    mock_enqueue.assert_not_called()
    mock_dispatch.assert_not_called()
    mock_verify.assert_not_called()


def test_s5_verify_route_scopes_to_eligible_contacts(sqlite_session: Session) -> None:
    campaign_a, company_a = _seed_campaign_company(sqlite_session, domain="verify-a.example", campaign_name="Verify A")
    campaign_b, company_b = _seed_campaign_company(sqlite_session, domain="verify-b.example", campaign_name="Verify B")
    eligible = _seed_prospect_contact(sqlite_session, company=company_a, title_match=True, email="eligible@verify.example")
    other_campaign = _seed_prospect_contact(sqlite_session, company=company_b, title_match=True, email="other@verify.example")
    sqlite_session.commit()

    with (
        patch("app.api.routes.contacts.verify_contacts_batch.delay") as mock_verify,
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch,
        patch("app.tasks.contacts.reveal_contact_emails.delay") as mock_reveal,
    ):
        result = verify_contacts(
            ContactVerifyRequest(
                campaign_id=campaign_a.id,
                contact_ids=[eligible.id, other_campaign.id],
            ),
            session=sqlite_session,
            x_idempotency_key=None,
        )

    assert result.selected_count == 1
    mock_verify.assert_called_once()
    mock_dispatch.assert_not_called()
    mock_reveal.assert_not_called()


def test_s5_verify_route_rejects_ineligible_contacts(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_company(sqlite_session, domain="verify-reject.example", campaign_name="Verify Reject")
    ineligible = _seed_prospect_contact(sqlite_session, company=company, title_match=False, email="ineligible@verify.example")
    sqlite_session.commit()

    with (
        patch("app.api.routes.contacts.verify_contacts_batch.delay") as mock_verify,
        patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch,
        patch("app.tasks.contacts.reveal_contact_emails.delay") as mock_reveal,
    ):
        with pytest.raises(HTTPException) as excinfo:
            verify_contacts(
                ContactVerifyRequest(
                    campaign_id=campaign.id,
                    contact_ids=[ineligible.id],
                ),
                session=sqlite_session,
                x_idempotency_key=None,
            )

    assert excinfo.value.status_code == 422
    mock_verify.assert_not_called()
    mock_dispatch.assert_not_called()
    mock_reveal.assert_not_called()
