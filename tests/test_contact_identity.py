from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, col, select

from app.models import Company, ContactFetchJob, DiscoveredContact, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState
from app.services.contact_service import ContactService, _provider_native_person_id


def _company_and_job(session: Session, *, domain: str) -> tuple[Company, ContactFetchJob]:
    upload = Upload(filename=f"{domain}.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
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

    job = ContactFetchJob(company_id=company.id, provider="apollo", state=ContactFetchJobState.SUCCEEDED, terminal_state=True)
    session.add(job)
    session.flush()
    return company, job


def test_provider_native_person_id_requires_native_identifiers() -> None:
    assert _provider_native_person_id("apollo", {"id": "apollo-123"}) == "apollo-123"
    assert _provider_native_person_id("apollo", {"linkedin_url": "https://linkedin.example/in/apollo"}) == ""
    assert _provider_native_person_id("snov", {"id": "snov-123"}) == "snov-123"
    assert _provider_native_person_id("snov", {"user_id": "snov-user-456"}) == "snov-user-456"
    assert _provider_native_person_id("snov", {"search_emails_start": "snov-hash-789"}) == "snov-hash-789"
    assert _provider_native_person_id("snov", {"source_page": "https://example.com/profile"}) == ""
    assert _provider_native_person_id("unknown", {"id": "ignored"}) == ""


def test_discovered_persistence_skips_synthetic_ids_and_reactivates_native_matches(sqlite_engine, sqlite_session: Session) -> None:
    company, job = _company_and_job(sqlite_session, domain="native-identity.example")
    sqlite_session.add(
        DiscoveredContact(
            company_id=company.id,
            contact_fetch_job_id=job.id,
            provider="apollo",
            provider_person_id="apollo-123",
            first_name="Old",
            last_name="Person",
            title="Director",
            title_match=False,
            is_active=False,
            backfilled=True,
        )
    )
    sqlite_session.commit()

    contacts_to_write = [
        {
            "provider_person_id": "apollo-123",
            "first_name": "New",
            "last_name": "Person",
            "title": "Director",
            "title_match": True,
            "linkedin_url": "https://linkedin.example/in/apollo-123",
            "source_url": "https://apollo.example/profile/123",
            "provider_has_email": True,
            "provider_metadata_json": {"has_email": True},
            "raw_payload_json": {"id": "apollo-123"},
        },
        {
            "provider_person_id": "",
            "first_name": "Synthetic",
            "last_name": "Fallback",
            "title": "Director",
            "title_match": True,
            "linkedin_url": None,
            "source_url": None,
            "provider_has_email": None,
            "provider_metadata_json": None,
            "raw_payload_json": {"source_page": "https://example.com/profile"},
        },
    ]

    written = ContactService()._persist_discovered_contacts(
        engine=sqlite_engine,
        job_id=job.id,
        company_id=company.id,
        provider="apollo",
        contacts_to_write=contacts_to_write,
    )
    assert written == 1

    row = sqlite_session.exec(
        select(DiscoveredContact).where(
            col(DiscoveredContact.company_id) == company.id,
            col(DiscoveredContact.provider) == "apollo",
            col(DiscoveredContact.provider_person_id) == "apollo-123",
        )
    ).one()
    assert row.is_active is True
    assert row.backfilled is True
    assert row.first_name == "New"
    assert row.title_match is True

    written_again = ContactService()._persist_discovered_contacts(
        engine=sqlite_engine,
        job_id=job.id,
        company_id=company.id,
        provider="apollo",
        contacts_to_write=contacts_to_write,
    )
    assert written_again == 1

    rows = list(
        sqlite_session.exec(
            select(DiscoveredContact).where(
                col(DiscoveredContact.company_id) == company.id,
                col(DiscoveredContact.provider) == "apollo",
            )
        )
    )
    assert len(rows) == 1
