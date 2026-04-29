from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session

from app.models import Company, Contact, ContactVerifyJob, Upload
from app.models.pipeline import ContactFetchJob, ContactFetchJobState, ContactVerifyJobState
from app.services.contact_verify_service import ContactVerifyService


def _make_contact_for_verify(session: Session, *, email: str, title_match: bool = True) -> Contact:
    upload = Upload(filename="stage.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url="https://stage.example",
        normalized_url="https://stage.example",
        domain="stage.example",
    )
    session.add(company)
    session.flush()
    fetch_job = ContactFetchJob(
        company_id=company.id,
        provider="apollo",
        state=ContactFetchJobState.SUCCEEDED,
        terminal_state=True,
    )
    session.add(fetch_job)
    session.flush()
    contact = Contact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        source_provider="apollo",
        provider_person_id=f"person-{uuid4()}",
        first_name="Alice",
        last_name="Stage",
        title="Marketing Director",
        title_match=title_match,
        email=email,
        verification_status="unverified",
        pipeline_stage="email_revealed",
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


def test_invalid_verification_keeps_contact_at_email_revealed(sqlite_engine, sqlite_session: Session) -> None:
    contact = _make_contact_for_verify(sqlite_session, email="alice@stage.example")
    verify_job = _make_verify_job(sqlite_session, contact)

    with patch("app.services.contact_verify_service._zerobounce") as mock_zb:
        mock_zb.validate_batch.return_value = (
            [{"address": "alice@stage.example", "status": "not_valid"}],
            None,
        )
        result = ContactVerifyService().run_verify_job(engine=sqlite_engine, job_id=verify_job.id)

    assert result is not None
    assert result.state == ContactVerifyJobState.SUCCEEDED

    sqlite_session.refresh(contact)
    assert contact.verification_status == "invalid"
    assert contact.pipeline_stage == "email_revealed"
