from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Campaign, Contact, EmailFetchBatch, FetchedPerson, RoleFetchCriteria, UploadedDomain
from app.services.email_fetch_providers import (
    ProviderCandidate,
    ProviderEmailResult,
    ProviderSearchResult,
)
from app.services.email_fetch_service import EmailFetchService, EmailFetchServiceError


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class FakeProvider:
    def __init__(
        self,
        *,
        name: str,
        candidates_by_domain: dict[str, list[ProviderCandidate]] | None = None,
        emails_by_person_id: dict[str, ProviderEmailResult] | None = None,
        search_error: str = "",
    ) -> None:
        self.name = name
        self.candidates_by_domain = candidates_by_domain or {}
        self.emails_by_person_id = emails_by_person_id or {}
        self.search_error = search_error
        self.search_calls: list[tuple[str, int]] = []
        self.email_calls: list[str] = []

    def search_candidates(self, *, domain: str, criteria, limit: int) -> ProviderSearchResult:
        self.search_calls.append((domain, limit))
        if self.search_error:
            return ProviderSearchResult(provider=self.name, candidates=[], error_code=self.search_error)
        return ProviderSearchResult(
            provider=self.name,
            candidates=list(self.candidates_by_domain.get(domain, []))[:limit],
        )

    def fetch_email(self, *, candidate: ProviderCandidate, domain: str) -> ProviderEmailResult:  # noqa: ARG002
        self.email_calls.append(candidate.provider_person_id)
        return self.emails_by_person_id.get(candidate.provider_person_id, ProviderEmailResult(provider=self.name))


def _campaign(session: Session) -> Campaign:
    campaign = Campaign(name="S3 Campaign")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def _criteria(
    session: Session,
    campaign_id: UUID,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> RoleFetchCriteria:
    row = RoleFetchCriteria(
        campaign_id=campaign_id,
        name="Current targeting",
        include_rules_json=[{"title": value} for value in (include or ["Marketing Director"])],
        exclude_rules_json=[{"title": value} for value in (exclude or ["Assistant"])],
        criteria_hash="seed",
        is_active=True,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _domain(session: Session, campaign_id: UUID, domain: str) -> UploadedDomain:
    row = UploadedDomain(
        campaign_id=campaign_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        dedupe_key=domain,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _candidate(
    provider: str,
    person_id: str,
    *,
    title: str = "Marketing Director",
    first_name: str | None = None,
    last_name: str | None = None,
    linkedin_url: str | None = None,
) -> ProviderCandidate:
    return ProviderCandidate(
        provider=provider,
        provider_person_id=person_id,
        first_name=first_name or person_id.title(),
        last_name=last_name or "Person",
        title=title,
        linkedin_url=linkedin_url,
        raw_summary={"id": person_id},
    )


def _email(provider: str, value: str, status: str = "valid") -> ProviderEmailResult:
    return ProviderEmailResult(provider=provider, email=value, status=status, raw_summary={"email": value})


def test_preview_uses_apollo_search_without_revealing_or_calling_snov(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id)
    domain = _domain(db_session, campaign.id, "example.com")
    apollo = FakeProvider(
        name="apollo",
        candidates_by_domain={"example.com": [_candidate("apollo", "a1")]},
        emails_by_person_id={"a1": _email("apollo", "a1@example.com")},
    )
    snov = FakeProvider(name="snov")
    service = EmailFetchService(apollo_provider=apollo, snov_provider=snov)

    preview = service.preview(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])

    assert preview.selected_domain_count == 1
    assert preview.estimated_apollo_reveals == 1
    assert preview.estimated_snov_fallback_min == 2
    assert apollo.search_calls == [("example.com", 12)]
    assert apollo.email_calls == []
    assert snov.search_calls == []
    assert snov.email_calls == []
    assert db_session.exec(select(FetchedPerson)).all() == []


def test_preview_returns_credit_plan_without_persisting_provider_candidates(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id, include=[f"Title {i}" for i in range(1, 25)])
    domain = _domain(db_session, campaign.id, "example.com")
    apollo = FakeProvider(
        name="apollo",
        candidates_by_domain={"example.com": [_candidate("apollo", "a1", title="Title 12")]},
        emails_by_person_id={"a1": _email("apollo", "a1@example.com")},
    )
    snov = FakeProvider(name="snov")
    service = EmailFetchService(apollo_provider=apollo, snov_provider=snov)

    preview = service.preview(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])

    assert preview.credit_plan["apollo_preview_is_free"] is True
    assert preview.credit_plan["estimated_apollo_reveals"] == 1
    assert preview.credit_plan["estimated_snov_discovery_searches"] == 3
    assert preview.credit_plan["snov_title_chunks_per_company"] == 3
    assert preview.credit_plan["estimated_snov_email_lookups"] == 2
    assert db_session.exec(select(FetchedPerson)).all() == []


def test_run_batch_fills_three_contacts_with_apollo_and_skips_snov(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id)
    domain = _domain(db_session, campaign.id, "example.com")
    apollo_candidates = [_candidate("apollo", f"a{i}") for i in range(1, 4)]
    apollo = FakeProvider(
        name="apollo",
        candidates_by_domain={"example.com": apollo_candidates},
        emails_by_person_id={f"a{i}": _email("apollo", f"a{i}@example.com") for i in range(1, 4)},
    )
    snov = FakeProvider(name="snov", search_error="snov_should_not_run")
    service = EmailFetchService(apollo_provider=apollo, snov_provider=snov)

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    contacts = db_session.exec(select(Contact).where(Contact.domain_id == domain.id)).all()
    assert sorted(contact.selected_email for contact in contacts) == [
        "a1@example.com",
        "a2@example.com",
        "a3@example.com",
    ]
    assert {contact.selected_email_provider for contact in contacts} == {"apollo"}
    assert snov.search_calls == []
    db_session.refresh(batch)
    db_session.refresh(domain)
    assert batch.success_count == 1
    assert batch.failed_count == 0
    assert domain.fetch_status == "succeeded"


def test_run_batch_uses_snov_only_for_remaining_gap(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id)
    domain = _domain(db_session, campaign.id, "example.com")
    apollo = FakeProvider(
        name="apollo",
        candidates_by_domain={"example.com": [_candidate("apollo", "a1")]},
        emails_by_person_id={"a1": _email("apollo", "a1@example.com")},
    )
    snov_candidates = [_candidate("snov", f"s{i}") for i in range(1, 4)]
    snov = FakeProvider(
        name="snov",
        candidates_by_domain={"example.com": snov_candidates},
        emails_by_person_id={
            "s1": _email("snov", "s1@example.com", "unknown"),
            "s2": _email("snov", "s2@example.com", "valid"),
            "s3": _email("snov", "s3@example.com", "valid"),
        },
    )
    service = EmailFetchService(apollo_provider=apollo, snov_provider=snov)

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    contacts = db_session.exec(select(Contact).where(Contact.domain_id == domain.id)).all()
    emails_by_provider: dict[str, list[str]] = defaultdict(list)
    for contact in contacts:
        emails_by_provider[contact.selected_email_provider or ""].append(contact.selected_email or "")
    assert sorted(emails_by_provider["apollo"]) == ["a1@example.com"]
    assert sorted(emails_by_provider["snov"]) == ["s1@example.com", "s2@example.com"]
    assert snov.search_calls == [("example.com", 8)]
    assert snov.email_calls == ["s1", "s2"]


def test_run_batch_stores_unmatched_snov_prospects_without_email_lookup(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id, include=["Marketing Director"], exclude=["Assistant"])
    domain = _domain(db_session, campaign.id, "example.com")
    apollo = FakeProvider(name="apollo")
    snov = FakeProvider(
        name="snov",
        candidates_by_domain={
            "example.com": [
                _candidate("snov", "s1", title="Finance Manager"),
                _candidate("snov", "s2", title="Assistant Marketing Director"),
            ]
        },
        emails_by_person_id={
            "s1": _email("snov", "s1@example.com"),
            "s2": _email("snov", "s2@example.com"),
        },
    )
    service = EmailFetchService(apollo_provider=apollo, snov_provider=snov)

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    fetched = db_session.exec(select(FetchedPerson).where(FetchedPerson.domain_id == domain.id)).all()
    assert [(row.provider, row.provider_person_id, row.match_status, row.match_reason) for row in fetched] == [
        ("snov", "s1", "not_matched", "Title did not match"),
        ("snov", "s2", "excluded", "Excluded by Assistant"),
    ]
    assert {row.email_lookup_attempted for row in fetched} == {False}
    assert db_session.exec(select(Contact).where(Contact.domain_id == domain.id)).all() == []
    assert snov.email_calls == []


def test_run_batch_updates_fetch_timestamp_when_no_people_are_found(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id, include=["Marketing Director"], exclude=[])
    domain = _domain(db_session, campaign.id, "empty.example")
    service = EmailFetchService(
        apollo_provider=FakeProvider(name="apollo"),
        snov_provider=FakeProvider(name="snov"),
    )

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(domain)
    assert domain.fetch_status == "succeeded"
    assert domain.fetch_updated_at is not None


def test_run_batch_links_rejected_provider_observation_to_existing_contact(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id, include=["Marketing Director"], exclude=[])
    domain = _domain(db_session, campaign.id, "example.com")
    domain.fetch_status = "succeeded"
    db_session.add(domain)
    db_session.commit()
    db_session.refresh(domain)
    legacy_contact = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Duncan",
        last_name="Crundwell",
        title="Systems Architect",
        selected_email=None,
    )
    db_session.add(legacy_contact)
    db_session.commit()
    db_session.refresh(legacy_contact)
    apollo = FakeProvider(name="apollo")
    snov = FakeProvider(
        name="snov",
        candidates_by_domain={
            "example.com": [
                _candidate(
                    "snov",
                    "new-snov-id",
                    first_name="Duncan",
                    last_name="Crundwell",
                    title="Systems Architect",
                ),
            ]
        },
    )
    service = EmailFetchService(apollo_provider=apollo, snov_provider=snov)

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id], mode="refetch")
    service.run_batch(session=db_session, batch_id=batch.id)

    contacts = db_session.exec(select(Contact).where(Contact.domain_id == domain.id)).all()
    fetched = db_session.exec(select(FetchedPerson).where(FetchedPerson.domain_id == domain.id)).one()
    assert contacts == [legacy_contact]
    assert fetched.match_status == "not_matched"
    assert fetched.match_reason == "Title did not match"
    assert fetched.email_lookup_attempted is False
    assert fetched.contact_id == legacy_contact.id


def test_get_active_batch_ignores_orphan_batch_without_active_domains(db_session: Session) -> None:
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id, "orphan.example")

    batch = EmailFetchBatch(
        campaign_id=campaign.id,
        selected_domain_ids_json=[str(domain.id)],
        selected_domain_count=1,
        queued_count=1,
        state="queued",
    )
    db_session.add(batch)
    db_session.commit()

    assert EmailFetchService().get_active_batch(session=db_session, campaign_id=campaign.id) is None


def test_run_batch_links_promoted_contacts_to_fetched_people(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id, include=["Marketing Director"], exclude=[])
    domain = _domain(db_session, campaign.id, "example.com")
    apollo = FakeProvider(
        name="apollo",
        candidates_by_domain={"example.com": [_candidate("apollo", "a1", title="Marketing Director")]},
        emails_by_person_id={"a1": _email("apollo", "a1@example.com")},
    )
    service = EmailFetchService(apollo_provider=apollo, snov_provider=FakeProvider(name="snov"))

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    contact = db_session.exec(select(Contact).where(Contact.domain_id == domain.id)).one()
    fetched = db_session.exec(select(FetchedPerson).where(FetchedPerson.domain_id == domain.id)).one()
    assert fetched.match_status == "qualified_promoted"
    assert fetched.email_lookup_attempted is True
    assert fetched.email_result == "a1@example.com"
    assert fetched.email_status == "valid"
    assert fetched.contact_id == contact.id


def test_exclude_rules_prevent_paid_reveals(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id, include=["Marketing Director"], exclude=["Assistant"])
    domain = _domain(db_session, campaign.id, "example.com")
    apollo = FakeProvider(
        name="apollo",
        candidates_by_domain={
            "example.com": [
                _candidate("apollo", "a1", title="Assistant Marketing Director"),
            ]
        },
        emails_by_person_id={"a1": _email("apollo", "a1@example.com")},
    )
    snov = FakeProvider(name="snov")
    service = EmailFetchService(apollo_provider=apollo, snov_provider=snov)

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    assert db_session.exec(select(Contact)).all() == []
    assert apollo.email_calls == []
    assert snov.search_calls == [("example.com", 12)]


def test_batch_uses_original_criteria_snapshot_after_campaign_criteria_changes(db_session: Session) -> None:
    campaign = _campaign(db_session)
    criteria = _criteria(db_session, campaign.id, include=["Marketing Director"], exclude=[])
    domain = _domain(db_session, campaign.id, "example.com")
    apollo = FakeProvider(
        name="apollo",
        candidates_by_domain={"example.com": [_candidate("apollo", "a1", title="Marketing Director")]},
        emails_by_person_id={"a1": _email("apollo", "a1@example.com")},
    )
    service = EmailFetchService(apollo_provider=apollo, snov_provider=FakeProvider(name="snov"))

    batch = service.create_batch(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id])
    criteria.include_rules_json = [{"title": "Sales Director"}]
    criteria.criteria_hash = "changed"
    db_session.add(criteria)
    db_session.commit()

    service.run_batch(session=db_session, batch_id=batch.id)

    contacts = db_session.exec(select(Contact).where(Contact.domain_id == domain.id)).all()
    assert [contact.selected_email for contact in contacts] == ["a1@example.com"]
    assert batch.criteria_snapshot_json["include_titles"] == ["Marketing Director"]


def test_preview_rejects_more_than_two_hundred_domains(db_session: Session) -> None:
    campaign = _campaign(db_session)
    _criteria(db_session, campaign.id)
    domains = [_domain(db_session, campaign.id, f"example{i}.com") for i in range(201)]
    service = EmailFetchService(
        apollo_provider=FakeProvider(name="apollo"),
        snov_provider=FakeProvider(name="snov"),
    )

    with pytest.raises(EmailFetchServiceError) as exc:
        service.preview(session=db_session, campaign_id=campaign.id, domain_ids=[domain.id for domain in domains])

    assert exc.value.code == "too_many_domains"
