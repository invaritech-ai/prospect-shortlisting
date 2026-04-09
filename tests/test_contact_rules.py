from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, col, select

from app.api.routes.contacts import create_title_rule, delete_title_rule
from app.api.schemas.contacts import TitleMatchRuleCreate
from app.models import Company, ContactFetchJob, ProspectContact, TitleMatchRule, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState
from app.services.contact_service import match_title


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_company(session: Session, *, domain: str = "example.com") -> Company:
    upload = Upload(filename="contacts.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
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


def test_create_title_rule_requeues_new_matches(sqlite_session: Session) -> None:
    company = _make_company(sqlite_session, domain="create-rule.example")
    _make_terminal_contact(sqlite_session, company=company, title="VP Marketing")

    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock_delay:
        result = create_title_rule(
            TitleMatchRuleCreate(rule_type="include", keywords="marketing, vice president"),
            session=sqlite_session,
        )

    assert result.rule_type == "include"
    assert mock_delay.call_count == 1

    active_jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.company_id) == company.id,
                col(ContactFetchJob.terminal_state).is_(False),
            )
        ).all()
    )
    assert len(active_jobs) == 1
    assert active_jobs[0].provider == "snov"

    refreshed_contact = sqlite_session.exec(
        select(ProspectContact).where(col(ProspectContact.company_id) == company.id)
    ).one()
    assert refreshed_contact.title_match is True


def test_delete_title_rule_requeues_new_matches(sqlite_session: Session) -> None:
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

    assert mock_delay.call_count == 1

    active_jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.company_id) == company.id,
                col(ContactFetchJob.terminal_state).is_(False),
            )
        ).all()
    )
    assert len(active_jobs) == 1
    assert active_jobs[0].provider == "snov"

    refreshed_contact = sqlite_session.exec(
        select(ProspectContact).where(col(ProspectContact.company_id) == company.id)
    ).one()
    assert refreshed_contact.title_match is True
