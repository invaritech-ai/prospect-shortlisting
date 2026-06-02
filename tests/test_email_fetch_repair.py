from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Campaign, ClassificationResult, Contact, FetchedPerson, UploadedDomain
from app.services.campaign_stage_counts import build_campaign_stage_counts
from app.services.email_fetch_service import EmailFetchService


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _domain(campaign: Campaign, domain: str, *, fetch_status: str | None = None) -> UploadedDomain:
    return UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        dedupe_key=domain,
        scrape_status="succeeded",
        fetch_status=fetch_status,
    )


def _label(campaign: Campaign, domain: UploadedDomain, label: str) -> ClassificationResult:
    return ClassificationResult(
        campaign_id=campaign.id,
        domain_id=domain.id,
        state="succeeded",
        predicted_label=label,
    )


def test_email_fetch_status_repair_dry_run_summarizes_without_mutating(db_session: Session) -> None:
    from app.services.email_fetch_repair import repair_email_fetch_status

    campaign = Campaign(id=uuid4(), name="Repair Campaign")
    possible_with_email = _domain(campaign, "with-email.example")
    possible_no_email = _domain(campaign, "no-email.example")
    possible_no_contacts = _domain(campaign, "empty.example")
    possible_running = _domain(campaign, "running.example", fetch_status="running")
    possible_failed = _domain(campaign, "failed.example", fetch_status="failed")
    possible_succeeded_empty = _domain(campaign, "succeeded-empty.example", fetch_status="succeeded")
    non_possible_with_contact = _domain(campaign, "crap-with-contact.example")
    db_session.add_all(
        [
            campaign,
            possible_with_email,
            possible_no_email,
            possible_no_contacts,
            possible_running,
            possible_failed,
            possible_succeeded_empty,
            non_possible_with_contact,
        ]
    )
    for domain in [
        possible_with_email,
        possible_no_email,
        possible_no_contacts,
        possible_running,
        possible_failed,
        possible_succeeded_empty,
    ]:
        db_session.add(_label(campaign, domain, "possible"))
    db_session.add(_label(campaign, non_possible_with_contact, "crap"))
    db_session.add_all(
        [
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_with_email.id,
                first_name="Ada",
                last_name="Lovelace",
                title="CEO",
                selected_email="ada@with-email.example",
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_no_email.id,
                first_name="Grace",
                last_name="Hopper",
                title="CTO",
                selected_email=None,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_running.id,
                first_name="Running",
                last_name="Contact",
                title="CEO",
                selected_email=None,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_failed.id,
                first_name="Failed",
                last_name="Contact",
                title="CEO",
                selected_email=None,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=non_possible_with_contact.id,
                first_name="Ignored",
                last_name="Contact",
                title="CEO",
                selected_email=None,
            ),
        ]
    )
    db_session.commit()

    summary = repair_email_fetch_status(session=db_session, campaign_id=campaign.id, apply=False)

    assert summary.applied is False
    assert summary.scanned_domains == 7
    assert summary.domains_repaired == 3
    assert summary.contacts_visible == 3
    assert summary.emails_visible == 1
    assert summary.possible_domains_repaired == 2
    assert summary.possible_domains_still_pending == 1
    assert summary.failed_domains_with_contacts == 1
    assert summary.succeeded_domains_without_contacts == 1

    unchanged = db_session.exec(select(UploadedDomain).where(UploadedDomain.id == possible_with_email.id)).one()
    assert unchanged.fetch_status is None


def test_email_fetch_status_repair_marks_only_null_status_contact_domains(db_session: Session) -> None:
    from app.services.email_fetch_repair import repair_email_fetch_status

    campaign = Campaign(id=uuid4(), name="Apply Repair Campaign")
    possible_with_email = _domain(campaign, "with-email.example")
    possible_no_email = _domain(campaign, "no-email.example")
    possible_no_contacts = _domain(campaign, "empty.example")
    possible_running = _domain(campaign, "running.example", fetch_status="running")
    possible_failed = _domain(campaign, "failed.example", fetch_status="failed")
    possible_succeeded_empty = _domain(campaign, "succeeded-empty.example", fetch_status="succeeded")
    non_possible_with_contact = _domain(campaign, "crap-with-contact.example")
    db_session.add_all(
        [
            campaign,
            possible_with_email,
            possible_no_email,
            possible_no_contacts,
            possible_running,
            possible_failed,
            possible_succeeded_empty,
            non_possible_with_contact,
        ]
    )
    for domain in [
        possible_with_email,
        possible_no_email,
        possible_no_contacts,
        possible_running,
        possible_failed,
        possible_succeeded_empty,
    ]:
        db_session.add(_label(campaign, domain, "possible"))
    db_session.add(_label(campaign, non_possible_with_contact, "crap"))
    db_session.add_all(
        [
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_with_email.id,
                first_name="Ada",
                last_name="Lovelace",
                title="CEO",
                selected_email="ada@with-email.example",
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_no_email.id,
                first_name="Grace",
                last_name="Hopper",
                title="CTO",
                selected_email=None,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_running.id,
                first_name="Running",
                last_name="Contact",
                title="CEO",
                selected_email=None,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_failed.id,
                first_name="Failed",
                last_name="Contact",
                title="CEO",
                selected_email=None,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=non_possible_with_contact.id,
                first_name="Ignored",
                last_name="Contact",
                title="CEO",
                selected_email=None,
            ),
        ]
    )
    db_session.commit()

    summary = repair_email_fetch_status(session=db_session, campaign_id=campaign.id, apply=True)

    assert summary.applied is True
    assert summary.domains_repaired == 3
    by_domain = {
        domain.domain: domain.fetch_status
        for domain in db_session.exec(select(UploadedDomain).where(UploadedDomain.campaign_id == campaign.id)).all()
    }
    assert by_domain["with-email.example"] == "succeeded"
    assert by_domain["no-email.example"] == "succeeded"
    assert by_domain["crap-with-contact.example"] == "succeeded"
    assert by_domain["empty.example"] is None
    assert by_domain["running.example"] == "running"
    assert by_domain["failed.example"] == "failed"
    assert by_domain["succeeded-empty.example"] == "succeeded"

    stage_counts = build_campaign_stage_counts(session=db_session, campaign_id=campaign.id)
    assert stage_counts is not None
    assert stage_counts.contacts.done == 2
    assert stage_counts.contacts.pending == 1
    assert stage_counts.contacts.running == 1
    assert stage_counts.contacts.failed == 1
    assert stage_counts.contacts.no_match == 1
    assert stage_counts.contacts.contacts_found == 4
    assert stage_counts.contacts.emails_found == 1

    company_rows = EmailFetchService().list_companies(session=db_session, campaign_id=campaign.id).items
    by_domain_row = {row.domain: row for row in company_rows}
    assert by_domain_row["with-email.example"].status == "done"
    assert by_domain_row["with-email.example"].emails_found == 1
    assert by_domain_row["no-email.example"].status == "done"
    assert by_domain_row["no-email.example"].contacts_found == 1
    assert by_domain_row["no-email.example"].emails_found == 0


def test_fetched_people_contact_link_repair_dry_run_and_apply(db_session: Session) -> None:
    from app.services.fetched_people_repair import link_fetched_people_contacts

    campaign = Campaign(id=uuid4(), name="Fetched Link Repair Campaign")
    domain = _domain(campaign, "example.com", fetch_status="succeeded")
    db_session.add_all([campaign, domain])
    exact_contact = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Alan",
        last_name="Bragg",
        title="US Service Manager",
    )
    ambiguous_one = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Sam",
        last_name="Smith",
        title="Operations Lead",
    )
    ambiguous_two = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Sam",
        last_name="Smith",
        title="Sales Lead",
    )
    exact_fetched = FetchedPerson(
        campaign_id=campaign.id,
        domain_id=domain.id,
        provider="snov",
        provider_person_id="s1",
        first_name="Alan",
        last_name="Bragg",
        title="US Service Manager",
        match_status="not_matched",
        match_reason="Title did not match",
    )
    ambiguous_fetched = FetchedPerson(
        campaign_id=campaign.id,
        domain_id=domain.id,
        provider="snov",
        provider_person_id="s2",
        first_name="Sam",
        last_name="Smith",
        title="",
        match_status="not_matched",
        match_reason="Title did not match",
    )
    db_session.add_all([exact_contact, ambiguous_one, ambiguous_two, exact_fetched, ambiguous_fetched])
    db_session.commit()
    db_session.refresh(exact_contact)
    db_session.refresh(exact_fetched)
    db_session.refresh(ambiguous_fetched)

    dry_run = link_fetched_people_contacts(session=db_session, campaign_id=campaign.id, apply=False)

    assert dry_run.applied is False
    assert dry_run.scanned_fetched_people == 2
    assert dry_run.linked == 1
    assert dry_run.ambiguous == 1
    assert dry_run.unmatched == 0
    assert db_session.get(FetchedPerson, exact_fetched.id).contact_id is None

    applied = link_fetched_people_contacts(session=db_session, campaign_id=campaign.id, apply=True)

    assert applied.applied is True
    assert applied.linked == 1
    assert db_session.get(FetchedPerson, exact_fetched.id).contact_id == exact_contact.id
    assert db_session.get(FetchedPerson, ambiguous_fetched.id).contact_id is None
