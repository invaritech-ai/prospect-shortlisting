from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, col, select

from app.models import (
    Company,
    ContactFetchJob,
    ContactProviderAttempt,
    Contact,
    TitleMatchRule,
    Upload,
)
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState, ContactProviderAttemptState
from app.services.contact_service import ContactService, _apollo
from app.tasks.beat import reconcile_stuck_jobs
from app.tasks.contacts import fetch_contacts_apollo


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_company(session: Session, *, domain: str) -> Company:
    upload = Upload(filename="apollo.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
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


def _seed_apollo_rule(session: Session) -> None:
    session.add(TitleMatchRule(rule_type="include", keywords="marketing, vice president"))
    session.commit()


def _create_apollo_job(session: Session, company: Company) -> ContactFetchJob:
    job = ContactFetchJob(company_id=company.id, provider="apollo")
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _start_apollo_attempt(sqlite_engine, sqlite_session: Session, job: ContactFetchJob) -> ContactProviderAttempt:
    with patch("app.tasks.contacts.fetch_contacts_apollo_attempt.delay") as attempt_delay:
        started = ContactService().run_apollo_fetch(engine=sqlite_engine, job_id=job.id)

    assert started is not None
    assert started.terminal_state is False
    attempt_delay.assert_called_once()

    attempt = sqlite_session.exec(
        select(ContactProviderAttempt).where(col(ContactProviderAttempt.contact_fetch_job_id) == job.id)
    ).one()
    assert attempt.provider == "apollo"
    assert attempt.state == ContactProviderAttemptState.QUEUED
    return attempt


def _run_apollo_attempt_success(
    sqlite_engine,
    sqlite_session: Session,
    *,
    job: ContactFetchJob,
    attempt: ContactProviderAttempt,
    search_people,
    reveal_email,
) -> ContactFetchJob:
    with (
        patch.object(_apollo, "search_people", side_effect=search_people),
        patch.object(_apollo, "reveal_email", side_effect=reveal_email),
        patch("app.tasks.contacts.fetch_contacts_apollo.delay") as rerun_delay,
    ):
        result = ContactService().run_apollo_attempt(engine=sqlite_engine, attempt_id=attempt.id)

    assert result is not None
    assert rerun_delay.call_count in {0, 1}

    finalized = ContactService().run_apollo_fetch(engine=sqlite_engine, job_id=job.id)

    assert finalized is not None
    assert finalized.terminal_state is True
    assert finalized.state == ContactFetchJobState.SUCCEEDED
    sqlite_session.refresh(job)
    return job


def test_fetch_contacts_apollo_task_invokes_service(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="task-apollo.example")
    job = _create_apollo_job(sqlite_session, company)

    with patch("app.tasks.contacts.get_engine", return_value=sqlite_engine), patch(
        "app.tasks.contacts.ContactService"
    ) as mock_service:
        mock_service.return_value.run_apollo_fetch.return_value = SimpleNamespace(
            terminal_state=True,
            last_error_code=None,
        )
        fetch_contacts_apollo.apply(args=[str(job.id)])

    mock_service.return_value.run_apollo_fetch.assert_called_once()


def test_apollo_provider_attempt_writes_native_discovered_contacts(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="apollo.example")
    job = _create_apollo_job(sqlite_session, company)
    _seed_apollo_rule(sqlite_session)

    existing_contact = Contact(
        company_id=company.id,
        contact_fetch_job_id=job.id,
        source_provider="apollo",
        provider_person_id="apollo-person-1",
        first_name="Old",
        last_name="Person",
        title="Vice President Marketing",
        title_match=False,
        linkedin_url=None,
        source_url=None,
        provider_has_email=False,
        provider_metadata_json={"has_email": False},
        raw_payload_json={"id": "apollo-person-1"},
        is_active=False,
        backfilled=True,
    )
    sqlite_session.add(existing_contact)
    sqlite_session.commit()

    attempt = _start_apollo_attempt(sqlite_engine, sqlite_session, job)
    prospects_page_1 = [
        {
            "id": "apollo-person-1",
            "first_name": "Existing",
            "last_name_obfuscated": "Person",
            "title": "VP Marketing",
            "linkedin_url": "https://linkedin.com/in/existing",
            "has_email": True,
        },
        {
            "id": "apollo-person-2",
            "first_name": "New",
            "last_name_obfuscated": "Person",
            "title": "VP Marketing",
            "linkedin_url": "https://linkedin.com/in/new",
            "has_email": True,
        },
    ]

    def fake_search_people(domain: str, page: int = 1, person_titles: list[str] | None = None) -> list[dict]:
        _apollo.last_error_code = ""
        return prospects_page_1 if page == 1 else []

    def fake_reveal_email(person_id: str) -> dict | None:
        _apollo.last_error_code = ""
        return None

    finalized = _run_apollo_attempt_success(
        sqlite_engine,
        sqlite_session,
        job=job,
        attempt=attempt,
        search_people=fake_search_people,
        reveal_email=fake_reveal_email,
    )

    assert finalized.contacts_found == 2
    assert finalized.title_matched_count == 2
    rows = list(
        sqlite_session.exec(
            select(Contact).where(col(Contact.company_id) == company.id)
        ).all()
    )
    assert len(rows) == 2
    rows_by_id = {row.provider_person_id: row for row in rows}
    assert rows_by_id["apollo-person-1"].is_active is True
    assert rows_by_id["apollo-person-1"].first_name == "Existing"
    assert rows_by_id["apollo-person-1"].title_match is True
    assert rows_by_id["apollo-person-1"].provider_metadata_json == {"has_email": True, "organization_id": None}
    assert rows_by_id["apollo-person-2"].is_active is True
    assert rows_by_id["apollo-person-2"].first_name == "New"
    assert rows_by_id["apollo-person-2"].title_match is True


def test_apollo_provider_attempt_updates_existing_discovered_contact_in_place(
    sqlite_engine,
    sqlite_session: Session,
) -> None:
    company = _make_company(sqlite_session, domain="apollo-dedup.example")
    _seed_apollo_rule(sqlite_session)
    job = _create_apollo_job(sqlite_session, company)

    seeded_contact = Contact(
        company_id=company.id,
        contact_fetch_job_id=job.id,
        source_provider="apollo",
        provider_person_id="apollo-jane",
        first_name="Jane",
        last_name="Doe",
        title="VP Marketing",
        title_match=False,
        linkedin_url="https://linkedin.com/in/jane-doe",
        source_url=None,
        provider_has_email=False,
        provider_metadata_json={"has_email": False},
        raw_payload_json={"id": "apollo-jane"},
        is_active=False,
        backfilled=True,
    )
    sqlite_session.add(seeded_contact)
    sqlite_session.commit()
    sqlite_session.refresh(seeded_contact)

    attempt = _start_apollo_attempt(sqlite_engine, sqlite_session, job)

    def fake_search_people(domain: str, page: int = 1, person_titles: list[str] | None = None) -> list[dict]:
        _apollo.last_error_code = ""
        if page != 1:
            return []
        return [
            {
                "id": "apollo-jane",
                "first_name": "Jane",
                "last_name_obfuscated": "Doe",
                "title": "VP Marketing",
                "linkedin_url": "https://linkedin.com/in/jane-doe",
                "has_email": True,
            }
        ]

    def fake_reveal_email(person_id: str) -> dict | None:
        _apollo.last_error_code = ""
        if person_id != "apollo-jane":
            return None
        return {
            "id": person_id,
            "first_name": "Jane",
            "last_name": "Doe",
            "title": "VP Marketing",
            "linkedin_url": "https://linkedin.com/in/jane-doe",
            "email": "jane@apollo.example",
            "email_status": "verified",
        }

    _run_apollo_attempt_success(
        sqlite_engine,
        sqlite_session,
        job=job,
        attempt=attempt,
        search_people=fake_search_people,
        reveal_email=fake_reveal_email,
    )

    rows = list(
        sqlite_session.exec(
            select(Contact).where(col(Contact.company_id) == company.id)
        ).all()
    )
    assert len(rows) == 1
    merged = rows[0]
    sqlite_session.refresh(merged)
    assert merged.provider_person_id == "apollo-jane"
    assert merged.is_active is True
    assert merged.title_match is True
    assert merged.first_name == "Jane"
    assert merged.provider_metadata_json == {"has_email": True, "organization_id": None}


def test_apollo_provider_attempt_scopes_dedup_by_company(sqlite_engine, sqlite_session: Session) -> None:
    company_a = _make_company(sqlite_session, domain="scope-a.example")
    company_b = _make_company(sqlite_session, domain="scope-b.example")
    _seed_apollo_rule(sqlite_session)
    shared_email = "shared@example.com"

    for company, seed in ((company_b, "b"), (company_a, "a")):
        seeded_job = _create_apollo_job(sqlite_session, company)
        contact = Contact(
            company_id=company.id,
            contact_fetch_job_id=seeded_job.id,
            source_provider="apollo",
            provider_person_id="apollo-scope",
            first_name="Alex",
            last_name="Smith",
            title="VP Marketing",
            title_match=False,
            linkedin_url=None,
            source_url=None,
            provider_has_email=False,
            provider_metadata_json={"seed": seed},
            raw_payload_json={"id": "apollo-scope", "seed": seed},
            is_active=False,
            backfilled=True,
        )
        sqlite_session.add(contact)
        sqlite_session.commit()
        sqlite_session.refresh(contact)

    job = _create_apollo_job(sqlite_session, company_a)
    attempt = _start_apollo_attempt(sqlite_engine, sqlite_session, job)

    def fake_search_people(domain: str, page: int = 1, person_titles: list[str] | None = None) -> list[dict]:
        _apollo.last_error_code = ""
        if page != 1:
            return []
        return [
            {
                "id": "apollo-scope",
                "first_name": "Alex",
                "last_name_obfuscated": "Smith",
                "title": "VP Marketing",
                "linkedin_url": "",
                "has_email": True,
            }
        ]

    def fake_reveal_email(person_id: str) -> dict | None:
        _apollo.last_error_code = ""
        if person_id != "apollo-scope":
            return None
        return {
            "id": person_id,
            "first_name": "Alex",
            "last_name": "Smith",
            "title": "VP Marketing",
            "linkedin_url": "",
            "email": shared_email,
            "email_status": "verified",
        }

    _run_apollo_attempt_success(
        sqlite_engine,
        sqlite_session,
        job=job,
        attempt=attempt,
        search_people=fake_search_people,
        reveal_email=fake_reveal_email,
    )

    rows_a = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company_a.id)).all())
    rows_b = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company_b.id)).all())
    assert len(rows_a) == 1
    assert len(rows_b) == 1


def test_apollo_provider_attempt_skips_rows_without_native_ids(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="name-fallback.example")
    _seed_apollo_rule(sqlite_session)
    job = _create_apollo_job(sqlite_session, company)

    seeded = Contact(
        company_id=company.id,
        contact_fetch_job_id=job.id,
        source_provider="apollo",
        provider_person_id="apollo-jordan",
        first_name="Jordan",
        last_name="Lee",
        title="VP Marketing",
        title_match=False,
        linkedin_url=None,
        source_url=None,
        provider_has_email=False,
        provider_metadata_json={"seed": "snov"},
        raw_payload_json={"id": "apollo-jordan"},
        is_active=False,
        backfilled=True,
    )
    sqlite_session.add(seeded)
    sqlite_session.commit()

    attempt = _start_apollo_attempt(sqlite_engine, sqlite_session, job)

    def fake_search_people(domain: str, page: int = 1, person_titles: list[str] | None = None) -> list[dict]:
        _apollo.last_error_code = ""
        if page != 1:
            return []
        return [
            {
                "first_name": "Jordan",
                "last_name_obfuscated": "Lee",
                "title": "VP Marketing",
                "linkedin_url": "",
                "has_email": True,
            },
            {
                "id": "apollo-jordan",
                "first_name": "Jordan",
                "last_name_obfuscated": "Lee",
                "title": "VP Marketing",
                "linkedin_url": "",
                "has_email": True,
            }
        ]

    def fake_reveal_email(person_id: str) -> dict | None:
        _apollo.last_error_code = ""
        if person_id != "apollo-jordan":
            return None
        return {
            "id": person_id,
            "first_name": "Jordan",
            "last_name": "Lee",
            "title": "Chief Technology Officer",
            "linkedin_url": "",
            "email": "jordan@apollo.example",
            "email_status": "verified",
        }

    _run_apollo_attempt_success(
        sqlite_engine,
        sqlite_session,
        job=job,
        attempt=attempt,
        search_people=fake_search_people,
        reveal_email=fake_reveal_email,
    )

    rows = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company.id)).all())
    assert len(rows) == 1
    row = rows[0]
    sqlite_session.refresh(row)
    assert row.provider_person_id == "apollo-jordan"
    assert row.is_active is True


def test_reconciler_resets_stuck_contact_jobs_and_dispatches_orchestrator(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="recon-apollo.example")
    job = ContactFetchJob(
        company_id=company.id,
        provider="apollo",
        state=ContactFetchJobState.RUNNING,
        terminal_state=False,
        started_at=_utcnow() - timedelta(minutes=30),
        updated_at=_utcnow() - timedelta(minutes=30),
    )
    sqlite_session.add(job)
    sqlite_session.commit()
    sqlite_session.refresh(job)

    with patch("app.tasks.beat.get_engine", return_value=sqlite_engine), patch(
        "app.tasks.contacts.dispatch_contact_fetch_jobs.delay"
    ) as dispatch_delay:
        reconcile_stuck_jobs.apply()

    dispatch_delay.assert_called_once()
    sqlite_session.refresh(job)
    assert job.state == ContactFetchJobState.QUEUED
    assert job.started_at is None
