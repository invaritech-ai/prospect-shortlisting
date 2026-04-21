from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, col, select

from app.models import Company, ContactFetchJob, ProspectContact, ProspectContactEmail, TitleMatchRule, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState
from app.services.contact_service import ContactService, _apollo, _snov
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


def _make_terminal_job(session: Session, company: Company, *, provider: str = "snov") -> ContactFetchJob:
    job = ContactFetchJob(
        company_id=company.id,
        provider=provider,
        state=ContactFetchJobState.SUCCEEDED,
        terminal_state=True,
        finished_at=_utcnow(),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def test_fetch_contacts_apollo_task_invokes_service(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="task-apollo.example")
    job = ContactFetchJob(company_id=company.id, provider="apollo")
    sqlite_session.add(job)
    sqlite_session.commit()
    sqlite_session.refresh(job)

    with patch("app.tasks.contacts.get_engine", return_value=sqlite_engine), patch(
        "app.tasks.contacts.ContactService"
    ) as mock_service:
        mock_service.return_value.run_apollo_fetch.return_value = SimpleNamespace(
            terminal_state=True,
            last_error_code=None,
        )
        fetch_contacts_apollo.apply(args=[str(job.id)])

    mock_service.return_value.run_apollo_fetch.assert_called_once()


def test_apollo_fetch_skips_duplicate_company_email(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="apollo.example")
    _make_terminal_job(sqlite_session, company, provider="snov")
    apollo_job = ContactFetchJob(company_id=company.id, provider="apollo")
    sqlite_session.add(apollo_job)
    sqlite_session.commit()
    sqlite_session.refresh(apollo_job)

    sqlite_session.add(TitleMatchRule(rule_type="include", keywords="marketing, vice president"))
    sqlite_session.commit()

    duplicate_email = "dup@apollo.example"
    existing_contact = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=_make_terminal_job(sqlite_session, company, provider="snov").id,
        source="snov",
        first_name="Existing",
        last_name="Person",
        title="Vice President Marketing",
        title_match=True,
        linkedin_url=None,
        email=duplicate_email,
        provider_email_status="verified",
        verification_status="unverified",
        snov_confidence=None,
        snov_prospect_raw={"source": "snov"},
        apollo_prospect_raw=None,
        snov_email_raw=None,
    )
    sqlite_session.add(existing_contact)
    sqlite_session.commit()

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
        if person_id == "apollo-person-1":
            return {
                "id": person_id,
                "first_name": "Existing",
                "last_name": "Person",
                "title": "VP Marketing",
                "linkedin_url": "https://linkedin.com/in/existing",
                "email": duplicate_email,
                "email_status": "verified",
            }
        if person_id == "apollo-person-2":
            return {
                "id": person_id,
                "first_name": "New",
                "last_name": "Person",
                "title": "VP Marketing",
                "linkedin_url": "https://linkedin.com/in/new",
                "email": "new@apollo.example",
                "email_status": "verified",
            }
        return None

    with patch.object(_apollo, "search_people", side_effect=fake_search_people), patch.object(
        _apollo, "reveal_email", side_effect=fake_reveal_email
    ):
        result = ContactService().run_apollo_fetch(engine=sqlite_engine, job_id=apollo_job.id)

    assert result is not None
    assert result.terminal_state is True
    assert result.contacts_found == 2
    assert result.title_matched_count == 2

    sqlite_session.expire_all()
    refreshed_job = sqlite_session.get(ContactFetchJob, apollo_job.id)
    assert refreshed_job is not None
    assert refreshed_job.contacts_found == 2
    assert refreshed_job.title_matched_count == 2

    rows = list(
        sqlite_session.exec(
            select(ProspectContact).where(col(ProspectContact.company_id) == company.id)
        ).all()
    )
    assert len(rows) == 2
    sources_by_email = {row.email: row.source for row in rows}
    assert sources_by_email[duplicate_email] == "snov"
    assert sources_by_email["new@apollo.example"] == "apollo"

    new_row = next(row for row in rows if row.email == "new@apollo.example")
    assert new_row.apollo_prospect_raw is not None
    assert new_row.snov_prospect_raw is None
    email_rows = list(
        sqlite_session.exec(
            select(ProspectContactEmail).where(col(ProspectContactEmail.contact_id).in_([row.id for row in rows]))
        ).all()
    )
    assert len(email_rows) >= 2
    assert {email_row.email for email_row in email_rows} >= {"dup@apollo.example", "new@apollo.example"}


def test_apollo_fetch_dedups_same_contact_and_keeps_multiple_emails(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="apollo-dedup.example")
    snov_job = ContactFetchJob(company_id=company.id, provider="snov")
    sqlite_session.add(snov_job)
    sqlite_session.commit()
    sqlite_session.refresh(snov_job)
    seeded_contact = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=snov_job.id,
        source="snov",
        first_name="Jane",
        last_name="Doe",
        title="VP Marketing",
        title_match=True,
        linkedin_url="https://linkedin.com/in/jane-doe",
        email="jane@snov.example",
        provider_email_status="verified",
        verification_status="unverified",
        snov_confidence=None,
        snov_prospect_raw={"source": "snov"},
        apollo_prospect_raw=None,
        snov_email_raw=None,
    )
    sqlite_session.add(seeded_contact)
    sqlite_session.commit()
    sqlite_session.refresh(seeded_contact)
    sqlite_session.add(
        ProspectContactEmail(
            contact_id=seeded_contact.id,
            source="snov",
            email="jane@snov.example",
            email_normalized="jane@snov.example",
            provider_email_status="verified",
            is_primary=True,
        )
    )
    sqlite_session.commit()

    apollo_job = ContactFetchJob(company_id=company.id, provider="apollo")
    sqlite_session.add(apollo_job)
    sqlite_session.commit()
    sqlite_session.refresh(apollo_job)
    sqlite_session.add(TitleMatchRule(rule_type="include", keywords="marketing, vice president"))
    sqlite_session.commit()

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

    with patch.object(_apollo, "search_people", side_effect=fake_search_people), patch.object(
        _apollo, "reveal_email", side_effect=fake_reveal_email
    ):
        result = ContactService().run_apollo_fetch(engine=sqlite_engine, job_id=apollo_job.id)

    assert result is not None
    assert result.terminal_state is True
    rows = list(
        sqlite_session.exec(
            select(ProspectContact).where(col(ProspectContact.company_id) == company.id)
        ).all()
    )
    assert len(rows) == 1
    merged = rows[0]
    assert merged.email == "jane@snov.example"
    email_rows = list(
        sqlite_session.exec(
            select(ProspectContactEmail).where(col(ProspectContactEmail.contact_id) == merged.id)
        ).all()
    )
    assert {email_row.email for email_row in email_rows} == {"jane@snov.example", "jane@apollo.example"}


def test_apollo_fetch_email_lookup_scopes_dedup_by_company(sqlite_engine, sqlite_session: Session) -> None:
    company_a = _make_company(sqlite_session, domain="scope-a.example")
    company_b = _make_company(sqlite_session, domain="scope-b.example")
    sqlite_session.add(TitleMatchRule(rule_type="include", keywords="marketing, vice president"))
    sqlite_session.commit()

    shared_email = "shared@example.com"
    # Seed company B first with shared email.
    job_b = ContactFetchJob(company_id=company_b.id, provider="snov")
    sqlite_session.add(job_b)
    sqlite_session.commit()
    sqlite_session.refresh(job_b)
    contact_b = ProspectContact(
        company_id=company_b.id,
        contact_fetch_job_id=job_b.id,
        source="snov",
        first_name="Alex",
        last_name="Smith",
        title="VP Marketing",
        title_match=True,
        linkedin_url=None,
        email=shared_email,
        provider_email_status="verified",
        verification_status="unverified",
        snov_confidence=None,
        snov_prospect_raw={"seed": "b"},
        apollo_prospect_raw=None,
        snov_email_raw=None,
    )
    sqlite_session.add(contact_b)
    sqlite_session.commit()
    sqlite_session.refresh(contact_b)
    sqlite_session.add(
        ProspectContactEmail(
            contact_id=contact_b.id,
            source="snov",
            email=shared_email,
            email_normalized=shared_email,
            provider_email_status="verified",
            is_primary=True,
        )
    )

    # Seed company A with same email to ensure lookup merges in correct company.
    job_a_seed = ContactFetchJob(company_id=company_a.id, provider="snov")
    sqlite_session.add(job_a_seed)
    sqlite_session.commit()
    sqlite_session.refresh(job_a_seed)
    contact_a = ProspectContact(
        company_id=company_a.id,
        contact_fetch_job_id=job_a_seed.id,
        source="snov",
        first_name="Alex",
        last_name="Smith",
        title="VP Marketing",
        title_match=True,
        linkedin_url=None,
        email=shared_email,
        provider_email_status="verified",
        verification_status="unverified",
        snov_confidence=None,
        snov_prospect_raw={"seed": "a"},
        apollo_prospect_raw=None,
        snov_email_raw=None,
    )
    sqlite_session.add(contact_a)
    sqlite_session.commit()
    sqlite_session.refresh(contact_a)
    sqlite_session.add(
        ProspectContactEmail(
            contact_id=contact_a.id,
            source="snov",
            email=shared_email,
            email_normalized=shared_email,
            provider_email_status="verified",
            is_primary=True,
        )
    )
    sqlite_session.commit()

    apollo_job = ContactFetchJob(company_id=company_a.id, provider="apollo")
    sqlite_session.add(apollo_job)
    sqlite_session.commit()
    sqlite_session.refresh(apollo_job)

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

    with patch.object(_apollo, "search_people", side_effect=fake_search_people), patch.object(
        _apollo, "reveal_email", side_effect=fake_reveal_email
    ):
        result = ContactService().run_apollo_fetch(engine=sqlite_engine, job_id=apollo_job.id)

    assert result is not None
    rows_a = list(sqlite_session.exec(select(ProspectContact).where(col(ProspectContact.company_id) == company_a.id)).all())
    rows_b = list(sqlite_session.exec(select(ProspectContact).where(col(ProspectContact.company_id) == company_b.id)).all())
    assert len(rows_a) == 1
    assert len(rows_b) == 1


def test_apollo_fetch_name_fallback_requires_exact_title_match(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="name-fallback.example")
    sqlite_session.add(TitleMatchRule(rule_type="include", keywords="marketing, vice president"))
    sqlite_session.commit()

    snov_job = ContactFetchJob(company_id=company.id, provider="snov")
    sqlite_session.add(snov_job)
    sqlite_session.commit()
    sqlite_session.refresh(snov_job)
    seeded = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=snov_job.id,
        source="snov",
        first_name="Jordan",
        last_name="Lee",
        title="VP Marketing",
        title_match=True,
        linkedin_url=None,
        email="jordan@snov.example",
        provider_email_status="verified",
        verification_status="unverified",
        snov_confidence=None,
        snov_prospect_raw={"seed": "snov"},
        apollo_prospect_raw=None,
        snov_email_raw=None,
    )
    sqlite_session.add(seeded)
    sqlite_session.commit()

    apollo_job = ContactFetchJob(company_id=company.id, provider="apollo")
    sqlite_session.add(apollo_job)
    sqlite_session.commit()
    sqlite_session.refresh(apollo_job)

    def fake_search_people(domain: str, page: int = 1, person_titles: list[str] | None = None) -> list[dict]:
        _apollo.last_error_code = ""
        if page != 1:
            return []
        return [
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

    with patch.object(_apollo, "search_people", side_effect=fake_search_people), patch.object(
        _apollo, "reveal_email", side_effect=fake_reveal_email
    ):
        result = ContactService().run_apollo_fetch(engine=sqlite_engine, job_id=apollo_job.id)

    assert result is not None
    rows = list(sqlite_session.exec(select(ProspectContact).where(col(ProspectContact.company_id) == company.id)).all())
    assert len(rows) == 2


def test_snov_chain_enqueues_apollo_followup_and_defers_s4(sqlite_engine, sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="chain-followup.example")
    snov_job = ContactFetchJob(company_id=company.id, provider="snov", next_provider="apollo")
    sqlite_session.add(snov_job)
    sqlite_session.commit()
    sqlite_session.refresh(snov_job)

    with (
        patch.object(_snov, "get_domain_email_count", return_value=(0, None)),
        patch("app.services.contact_service.enqueue_s4_for_contact_success") as s4_enqueue,
        patch("app.tasks.contacts.fetch_contacts_apollo.delay") as apollo_delay,
    ):
        result = ContactService().run_contact_fetch(engine=sqlite_engine, job_id=snov_job.id)

    assert result is not None
    assert result.terminal_state is True
    assert result.provider == "snov"
    s4_enqueue.assert_not_called()
    apollo_delay.assert_called_once()

    followups = list(
        sqlite_session.exec(
            select(ContactFetchJob)
            .where(col(ContactFetchJob.company_id) == company.id, col(ContactFetchJob.provider) == "apollo")
            .order_by(col(ContactFetchJob.created_at))
        ).all()
    )
    assert len(followups) == 1
    assert followups[0].next_provider is None
    assert followups[0].terminal_state is False


def test_reconciler_routes_apollo_jobs_to_apollo_task(sqlite_engine, sqlite_session: Session) -> None:
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
        "app.tasks.contacts.fetch_contacts.delay"
    ) as snov_delay, patch("app.tasks.contacts.fetch_contacts_apollo.delay") as apollo_delay:
        reconcile_stuck_jobs.apply()

    apollo_delay.assert_called_once_with(str(job.id))
    snov_delay.assert_not_called()
