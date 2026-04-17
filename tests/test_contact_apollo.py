from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, col, select

from app.models import Company, ContactFetchJob, ProspectContact, TitleMatchRule, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState
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
    assert result.contacts_found == 1
    assert result.title_matched_count == 2

    sqlite_session.expire_all()
    refreshed_job = sqlite_session.get(ContactFetchJob, apollo_job.id)
    assert refreshed_job is not None
    assert refreshed_job.contacts_found == 1
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
