from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, SQLModel, create_engine

from app.api.routes.contacts import list_contacts, list_fetched_people
from app.models import Campaign, Contact, FetchedPerson, UploadedDomain


def test_list_contacts_returns_provider_neutral_rows() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(id=uuid4(), name="Contacts Campaign")
        domain = UploadedDomain(
            id=uuid4(),
            campaign_id=campaign.id,
            raw_url="https://example.com",
            normalized_url="https://example.com",
            domain="example.com",
            dedupe_key="example.com",
        )
        contact = Contact(
            campaign_id=campaign.id,
            domain_id=domain.id,
            first_name="Ada",
            last_name="Lovelace",
            title="Marketing Director",
            title_match=True,
            selected_email="ada@example.com",
            selected_email_provider="apollo",
        )
        session.add_all([campaign, domain, contact])
        session.commit()

        out = list_contacts(campaign_id=campaign.id, session=session)

    assert out.total == 1
    assert out.items[0].domain == "example.com"
    assert out.items[0].selected_email == "ada@example.com"
    assert out.items[0].selected_email_provider == "apollo"


def test_list_fetched_people_returns_unpromoted_provider_rows() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(id=uuid4(), name="Fetched Campaign")
        domain = UploadedDomain(
            id=uuid4(),
            campaign_id=campaign.id,
            raw_url="https://example.com",
            normalized_url="https://example.com",
            domain="example.com",
            dedupe_key="example.com",
        )
        matched = FetchedPerson(
            campaign_id=campaign.id,
            domain_id=domain.id,
            provider="snov",
            provider_person_id="s1",
            first_name="Matched",
            last_name="Person",
            title="Marketing Director",
            match_status="qualified_not_used",
            match_reason="Matched but target already filled",
        )
        rejected = FetchedPerson(
            campaign_id=campaign.id,
            domain_id=domain.id,
            provider="snov",
            provider_person_id="s2",
            first_name="Rejected",
            last_name="Person",
            title="Finance Manager",
            match_status="not_matched",
            match_reason="Title did not match",
        )
        session.add_all([campaign, domain, matched, rejected])
        session.commit()

        out = list_fetched_people(
            campaign_id=campaign.id,
            domain_id=domain.id,
            status="not_matched",
            session=session,
        )

    assert out.total == 1
    assert out.items[0].domain == "example.com"
    assert out.items[0].provider == "snov"
    assert out.items[0].match_status == "not_matched"
    assert out.items[0].match_reason == "Title did not match"


def test_list_fetched_people_unused_excludes_rows_already_linked_to_contacts() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign = Campaign(id=uuid4(), name="Fetched Campaign")
        domain = UploadedDomain(
            id=uuid4(),
            campaign_id=campaign.id,
            raw_url="https://example.com",
            normalized_url="https://example.com",
            domain="example.com",
            dedupe_key="example.com",
        )
        contact = Contact(
            campaign_id=campaign.id,
            domain_id=domain.id,
            first_name="Alan",
            last_name="Bragg",
            title="US Service Manager",
        )
        linked = FetchedPerson(
            campaign_id=campaign.id,
            domain_id=domain.id,
            contact_id=contact.id,
            provider="snov",
            provider_person_id="s1",
            first_name="Alan",
            last_name="Bragg",
            title="US Service Manager",
            match_status="not_matched",
            match_reason="Title did not match",
        )
        unlinked = FetchedPerson(
            campaign_id=campaign.id,
            domain_id=domain.id,
            provider="snov",
            provider_person_id="s2",
            first_name="Rejected",
            last_name="Person",
            title="Finance Manager",
            match_status="not_matched",
            match_reason="Title did not match",
        )
        session.add_all([campaign, domain, contact, linked, unlinked])
        session.commit()

        out = list_fetched_people(
            campaign_id=campaign.id,
            domain_id=domain.id,
            status="unused",
            session=session,
        )

    assert out.total == 1
    assert out.items[0].provider_person_id == "s2"
