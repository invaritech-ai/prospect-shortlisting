from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session

from app.api.routes.contacts import get_title_rule_stats, run_title_test
from app.api.schemas.contacts import TitleTestRequest
from app.models import Company, ContactFetchJob, Contact, TitleMatchRule, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _add_rules(session: Session) -> None:
    session.add(TitleMatchRule(rule_type="include", keywords="marketing, director"))
    session.add(TitleMatchRule(rule_type="exclude", keywords="assistant"))
    session.commit()


def _make_contact(session: Session, *, title: str, title_match: bool = False) -> Contact:
    upload = Upload(filename="t.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        pipeline_stage=CompanyPipelineStage.CONTACT_READY,
    )
    session.add(company)
    session.flush()
    job = ContactFetchJob(
        company_id=company.id,
        provider="snov",
        state=ContactFetchJobState.SUCCEEDED,
        terminal_state=True,
        finished_at=_utcnow(),
    )
    session.add(job)
    session.flush()
    contact = Contact(
        company_id=company.id,
        contact_fetch_job_id=job.id,
        source_provider="snov",
        provider_person_id=f"snov-{uuid4()}",
        first_name="Jane",
        last_name="Smith",
        title=title,
        title_match=title_match,
        verification_status="unverified",
    )
    session.add(contact)
    session.commit()
    return contact


def test_title_test_matched(db_session: Session) -> None:
    _add_rules(db_session)
    result = run_title_test(TitleTestRequest(title="Director of Marketing"), session=db_session)
    assert result.matched is True
    assert len(result.matching_rules) > 0
    assert "marketing, director" in result.matching_rules


def test_title_test_excluded(db_session: Session) -> None:
    _add_rules(db_session)
    result = run_title_test(TitleTestRequest(title="Marketing Assistant"), session=db_session)
    assert result.matched is False
    assert "assistant" in result.excluded_by


def test_title_test_no_match(db_session: Session) -> None:
    _add_rules(db_session)
    result = run_title_test(TitleTestRequest(title="Software Engineer"), session=db_session)
    assert result.matched is False
    assert result.excluded_by == []
    assert result.matching_rules == []


def test_stats_returns_counts(db_session: Session) -> None:
    _add_rules(db_session)
    _make_contact(db_session, title="Director of Marketing", title_match=True)
    result = get_title_rule_stats(session=db_session)
    assert result.total_contacts >= 1
    assert result.total_matched >= 1
    include_stat = next(r for r in result.rules if r.rule_type == "include" and r.keywords == "marketing, director")
    assert include_stat.contact_match_count >= 1
