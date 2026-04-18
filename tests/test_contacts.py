from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, col, delete, select

from app.api.routes.contacts import list_all_contacts
from app.api.routes.stats import get_stats
from app.models import Company, ContactFetchJob, ContactVerifyJob, ProspectContact, Upload
from app.models.pipeline import CompanyPipelineStage, ContactVerifyJobState, utcnow


def _seed_upload(session: Session, filename: str) -> Upload:
    upload = Upload(filename=filename, checksum=str(uuid4()), valid_count=0, invalid_count=0)
    session.add(upload)
    session.flush()
    return upload


def _seed_company(session: Session, *, upload_id, domain: str) -> Company:
    company = Company(
        upload_id=upload_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=CompanyPipelineStage.CONTACT_READY,
    )
    session.add(company)
    session.flush()
    return company


def _seed_contact(session: Session, *, company: Company, email: str, days_old: int = 0) -> ProspectContact:
    fetch_job = ContactFetchJob(company_id=company.id, provider="snov")
    session.add(fetch_job)
    session.flush()
    contact = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        first_name="Jane",
        last_name="Doe",
        title="Director",
        title_match=True,
        email=email,
        source="snov",
        verification_status="valid",
    )
    if days_old > 0:
        contact.updated_at = utcnow() - timedelta(days=days_old)
    session.add(contact)
    session.flush()
    return contact


def test_list_contacts_supports_letters_filter(sqlite_session: Session) -> None:
    upload = _seed_upload(sqlite_session, "letters-contacts.csv")
    try:
        company_a = _seed_company(sqlite_session, upload_id=upload.id, domain="wolf.example")
        company_b = _seed_company(sqlite_session, upload_id=upload.id, domain="apple.example")
        _seed_contact(sqlite_session, company=company_a, email="w@example.com")
        _seed_contact(sqlite_session, company=company_b, email="a@example.com")
        sqlite_session.commit()

        response = list_all_contacts(session=sqlite_session, letters="w", limit=50, offset=0)

        assert response.total == 1
        assert len(response.items) == 1
        assert response.items[0].domain == "wolf.example"
    finally:
        sqlite_session.exec(delete(ProspectContact).where(col(ProspectContact.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_contacts_invalid_sort_by_raises_422(sqlite_session: Session) -> None:
    upload = _seed_upload(sqlite_session, "contacts-sort.csv")
    try:
        company = _seed_company(sqlite_session, upload_id=upload.id, domain="sort.example")
        _seed_contact(sqlite_session, company=company, email="sort@example.com")
        sqlite_session.commit()

        with pytest.raises(HTTPException) as excinfo:
            list_all_contacts(session=sqlite_session, sort_by="not_real")
        assert excinfo.value.status_code == 422
        with pytest.raises(HTTPException) as excinfo_dir:
            list_all_contacts(session=sqlite_session, sort_dir="sideways")
        assert excinfo_dir.value.status_code == 422
    finally:
        sqlite_session.exec(delete(ProspectContact).where(col(ProspectContact.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_stats_validation_scope_honors_upload(sqlite_session: Session) -> None:
    upload_a = _seed_upload(sqlite_session, "stats-a.csv")
    upload_b = _seed_upload(sqlite_session, "stats-b.csv")
    try:
        company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="scope-a.example")
        company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="scope-b.example")
        contact_a = _seed_contact(sqlite_session, company=company_a, email="a@example.com")
        contact_b = _seed_contact(sqlite_session, company=company_b, email="b@example.com")

        sqlite_session.add(
            ContactVerifyJob(
                state=ContactVerifyJobState.SUCCEEDED,
                terminal_state=True,
                contact_ids_json=[str(contact_a.id)],
                selected_count=1,
                verified_count=1,
                skipped_count=0,
            )
        )
        sqlite_session.add(
            ContactVerifyJob(
                state=ContactVerifyJobState.SUCCEEDED,
                terminal_state=True,
                contact_ids_json=[str(contact_b.id)],
                selected_count=1,
                verified_count=1,
                skipped_count=0,
            )
        )
        sqlite_session.commit()

        scoped = get_stats(session=sqlite_session, upload_id=upload_a.id)
        unscoped = get_stats(session=sqlite_session, upload_id=None)

        assert scoped.validation.total == 1
        assert unscoped.validation.total >= 2
    finally:
        sqlite_session.exec(delete(ContactVerifyJob))
        sqlite_session.exec(delete(ProspectContact).where(col(ProspectContact.company_id).in_(
            select(Company.id).where(col(Company.upload_id).in_([upload_a.id, upload_b.id]))
        )))
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(
            select(Company.id).where(col(Company.upload_id).in_([upload_a.id, upload_b.id]))
        )))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id).in_([upload_a.id, upload_b.id])))
        sqlite_session.exec(delete(Upload).where(col(Upload.id).in_([upload_a.id, upload_b.id])))
        sqlite_session.commit()
