"""Tests for S4 verify pipeline: ContactVerifyService state transitions."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session

from app.models import ContactFetchJob, ContactVerifyJob, Contact, Upload, Company
from app.models.pipeline import ContactFetchJobState, ContactVerifyJobState
from app.services.contact_verify_service import (
    ContactVerifyService,
    is_contact_verification_eligible,
    normalize_zerobounce_status,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_normalize_zerobounce_status_catch_all():
    assert normalize_zerobounce_status("catch-all") == "catch_all"
    assert normalize_zerobounce_status("catch_all") == "catch_all"


def test_normalize_zerobounce_status_invalid():
    assert normalize_zerobounce_status("not_valid") == "invalid"
    assert normalize_zerobounce_status("not valid") == "invalid"


def test_normalize_zerobounce_status_passthrough():
    assert normalize_zerobounce_status("valid") == "valid"
    assert normalize_zerobounce_status("spamtrap") == "spamtrap"
    assert normalize_zerobounce_status(None) == "unknown"


def test_is_contact_verification_eligible_true():
    contact = Contact(
        company_id=uuid4(),
        contact_fetch_job_id=uuid4(),
        source_provider="apollo",
        provider_person_id="apollo-alice",
        first_name="Alice",
        last_name="Smith",
        title_match=True,
        email="alice@example.com",
        verification_status="unverified",
    )
    assert is_contact_verification_eligible(contact) is True


def test_is_contact_verification_eligible_requires_title_match():
    contact = Contact(
        company_id=uuid4(),
        contact_fetch_job_id=uuid4(),
        source_provider="apollo",
        provider_person_id="apollo-bob",
        first_name="Bob",
        last_name="Jones",
        title_match=False,
        email="bob@example.com",
        verification_status="unverified",
    )
    assert is_contact_verification_eligible(contact) is False


def test_is_contact_verification_eligible_requires_email():
    contact = Contact(
        company_id=uuid4(),
        contact_fetch_job_id=uuid4(),
        source_provider="apollo",
        provider_person_id="apollo-carol",
        first_name="Carol",
        last_name="White",
        title_match=True,
        email=None,
        verification_status="unverified",
    )
    assert is_contact_verification_eligible(contact) is False


def test_is_contact_verification_eligible_skips_already_verified():
    contact = Contact(
        company_id=uuid4(),
        contact_fetch_job_id=uuid4(),
        source_provider="apollo",
        provider_person_id="apollo-dave",
        first_name="Dave",
        last_name="Green",
        title_match=True,
        email="dave@example.com",
        verification_status="valid",
    )
    assert is_contact_verification_eligible(contact) is False


# ---------------------------------------------------------------------------
# ContactVerifyService state machine
# ---------------------------------------------------------------------------


def _make_company(session: Session) -> Company:
    upload = Upload(filename="verify.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url="https://verify-test.com",
        normalized_url="https://verify-test.com",
        domain="verify-test.com",
    )
    session.add(company)
    session.flush()
    return company


def _make_fetch_job(session: Session, company: Company) -> ContactFetchJob:
    job = ContactFetchJob(company_id=company.id, provider="apollo", state=ContactFetchJobState.SUCCEEDED, terminal_state=True)
    session.add(job)
    session.flush()
    return job


def _make_contact(
    session: Session,
    company: Company,
    fetch_job: ContactFetchJob,
    *,
    email: str = "alice@verify-test.com",
    title_match: bool = True,
    verification_status: str = "unverified",
) -> Contact:
    contact = Contact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        source_provider="apollo",
        provider_person_id=f"apollo-{uuid4()}",
        first_name="Alice",
        last_name="Smith",
        title_match=title_match,
        email=email,
        verification_status=verification_status,
    )
    session.add(contact)
    session.flush()
    return contact


def _make_verify_job(session: Session, contact: Contact) -> ContactVerifyJob:
    job = ContactVerifyJob(
        state=ContactVerifyJobState.QUEUED,
        terminal_state=False,
        contact_ids_json=[str(contact.id)],
    )
    session.add(job)
    session.commit()
    return job


def test_verify_job_marks_valid_contact_as_verified(sqlite_engine, sqlite_session: Session):
    company = _make_company(sqlite_session)
    fetch_job = _make_fetch_job(sqlite_session, company)
    contact = _make_contact(sqlite_session, company, fetch_job)
    verify_job = _make_verify_job(sqlite_session, contact)

    mock_results = [{"address": "alice@verify-test.com", "status": "valid"}]
    with patch("app.services.contact_verify_service._zerobounce") as mock_zb:
        mock_zb.validate_batch.return_value = (mock_results, None)
        result = ContactVerifyService().run_verify_job(engine=sqlite_engine, job_id=verify_job.id)

    assert result is not None
    assert result.state == ContactVerifyJobState.SUCCEEDED
    assert result.verified_count == 1
    assert result.skipped_count == 0

    sqlite_session.refresh(contact)
    assert contact.verification_status == "valid"


def test_verify_job_skips_already_verified_contacts(sqlite_engine, sqlite_session: Session):
    company = _make_company(sqlite_session)
    fetch_job = _make_fetch_job(sqlite_session, company)
    contact = _make_contact(sqlite_session, company, fetch_job, verification_status="valid")
    verify_job = _make_verify_job(sqlite_session, contact)

    with patch("app.services.contact_verify_service._zerobounce") as mock_zb:
        result = ContactVerifyService().run_verify_job(engine=sqlite_engine, job_id=verify_job.id)

    assert result is not None
    assert result.state == ContactVerifyJobState.SUCCEEDED
    assert result.verified_count == 0
    assert result.skipped_count == 1
    mock_zb.validate_batch.assert_not_called()


def test_verify_job_requeues_on_transient_error(sqlite_engine, sqlite_session: Session):
    company = _make_company(sqlite_session)
    fetch_job = _make_fetch_job(sqlite_session, company)
    contact = _make_contact(sqlite_session, company, fetch_job)
    verify_job = _make_verify_job(sqlite_session, contact)

    with patch("app.services.contact_verify_service._zerobounce") as mock_zb:
        mock_zb.validate_batch.return_value = ([], "zerobounce_rate_limited")
        result = ContactVerifyService().run_verify_job(engine=sqlite_engine, job_id=verify_job.id)

    assert result is not None
    assert result.state == ContactVerifyJobState.QUEUED
    assert result.terminal_state is False
    assert result.last_error_code == "zerobounce_rate_limited"


def test_verify_job_fails_terminally_on_auth_error(sqlite_engine, sqlite_session: Session):
    from app.services.zerobounce_client import ERR_ZEROBOUNCE_AUTH_FAILED

    company = _make_company(sqlite_session)
    fetch_job = _make_fetch_job(sqlite_session, company)
    contact = _make_contact(sqlite_session, company, fetch_job)
    verify_job = _make_verify_job(sqlite_session, contact)

    with patch("app.services.contact_verify_service._zerobounce") as mock_zb:
        mock_zb.validate_batch.return_value = ([], ERR_ZEROBOUNCE_AUTH_FAILED)
        result = ContactVerifyService().run_verify_job(engine=sqlite_engine, job_id=verify_job.id)

    assert result is not None
    assert result.state == ContactVerifyJobState.FAILED
    assert result.terminal_state is True
