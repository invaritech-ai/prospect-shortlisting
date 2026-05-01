from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, col, delete, select

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import get_contact_counts, list_all_contacts
from app.api.routes.stats import get_stats
from app.api.schemas.campaign import CampaignCreate
from app.models import AnalysisJob, Company, ContactFetchJob, ContactVerifyJob, Contact, PipelineRun, Prompt, Upload
from app.models.pipeline import AnalysisJobState, CompanyPipelineStage, ContactVerifyJobState, PipelineRunStatus, utcnow


def _seed_upload(session: Session, filename: str, *, campaign_id) -> Upload:
    upload = Upload(filename=filename, checksum=str(uuid4()), valid_count=0, invalid_count=0, campaign_id=campaign_id)
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


def _seed_contact(session: Session, *, company: Company, email: str, days_old: int = 0) -> Contact:
    fetch_job = ContactFetchJob(company_id=company.id, provider="snov")
    session.add(fetch_job)
    session.flush()
    contact = Contact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        first_name="Jane",
        last_name="Doe",
        title="Director",
        title_match=True,
        email=email,
        source_provider="snov",
        provider_person_id=f"snov-{uuid4()}",
        verification_status="valid",
    )
    if days_old > 0:
        contact.updated_at = utcnow() - timedelta(days=days_old)
    session.add(contact)
    session.flush()
    return contact


def test_list_contacts_supports_letters_filter(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Contacts Letters"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "letters-contacts.csv", campaign_id=campaign.id)
    try:
        company_a = _seed_company(sqlite_session, upload_id=upload.id, domain="wolf.example")
        company_b = _seed_company(sqlite_session, upload_id=upload.id, domain="apple.example")
        _seed_contact(sqlite_session, company=company_a, email="w@example.com")
        _seed_contact(sqlite_session, company=company_b, email="a@example.com")
        sqlite_session.commit()

        response = list_all_contacts(session=sqlite_session, campaign_id=campaign.id, letters="w", limit=50, offset=0)

        assert response.total == 1
        assert len(response.items) == 1
        assert response.items[0].domain == "wolf.example"
    finally:
        sqlite_session.exec(delete(Contact).where(col(Contact.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_contact_counts_reads_contacts_table_directly(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Contact Counts"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "contact-counts.csv", campaign_id=campaign.id)
    try:
        company = _seed_company(sqlite_session, upload_id=upload.id, domain="counts.example")
        matched = _seed_contact(sqlite_session, company=company, email="", days_old=0)
        matched.title_match = True
        matched.email = None
        fresh_unmatched = _seed_contact(sqlite_session, company=company, email="", days_old=0)
        fresh_unmatched.title_match = False
        fresh_unmatched.email = None
        stale = _seed_contact(sqlite_session, company=company, email="", days_old=45)
        stale.title_match = False
        stale.email = None
        revealed = _seed_contact(sqlite_session, company=company, email="revealed@example.com", days_old=0)
        revealed.title_match = True
        revealed.pipeline_stage = "email_revealed"
        sqlite_session.commit()

        counts = get_contact_counts(session=sqlite_session, campaign_id=campaign.id, upload_id=None)

        assert counts.total == 4
        assert counts.matched == 2
        assert counts.stale == 1
        assert counts.fresh == 3
        assert counts.already_revealed == 1
    finally:
        sqlite_session.exec(delete(Contact).where(col(Contact.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_contacts_invalid_sort_by_raises_422(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Contacts Sort"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "contacts-sort.csv", campaign_id=campaign.id)
    try:
        company = _seed_company(sqlite_session, upload_id=upload.id, domain="sort.example")
        _seed_contact(sqlite_session, company=company, email="sort@example.com")
        sqlite_session.commit()

        with pytest.raises(HTTPException) as excinfo:
            list_all_contacts(session=sqlite_session, campaign_id=campaign.id, sort_by="not_real")
        assert excinfo.value.status_code == 422
        with pytest.raises(HTTPException) as excinfo_dir:
            list_all_contacts(session=sqlite_session, campaign_id=campaign.id, sort_dir="sideways")
        assert excinfo_dir.value.status_code == 422
    finally:
        sqlite_session.exec(delete(Contact).where(col(Contact.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(
            select(Company.id).where(col(Company.upload_id) == upload.id)
        )))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_stats_validation_scope_honors_upload(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Stats Upload Scope"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, "stats-a.csv", campaign_id=campaign.id)
    upload_b = _seed_upload(sqlite_session, "stats-b.csv", campaign_id=campaign.id)
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

        scoped = get_stats(session=sqlite_session, campaign_id=campaign.id, upload_id=upload_a.id)
        unscoped = get_stats(session=sqlite_session, campaign_id=campaign.id, upload_id=None)

        assert scoped.validation.total == 1
        assert unscoped.validation.total >= 2
    finally:
        sqlite_session.exec(delete(ContactVerifyJob))
        sqlite_session.exec(delete(Contact).where(col(Contact.company_id).in_(
            select(Company.id).where(col(Company.upload_id).in_([upload_a.id, upload_b.id]))
        )))
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(
            select(Company.id).where(col(Company.upload_id).in_([upload_a.id, upload_b.id]))
        )))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id).in_([upload_a.id, upload_b.id])))
        sqlite_session.exec(delete(Upload).where(col(Upload.id).in_([upload_a.id, upload_b.id])))
        sqlite_session.commit()


def test_stats_analysis_counts_one_company_once_when_requeued(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Stats Analysis Requeue"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "stats-analysis.csv", campaign_id=campaign.id)
    try:
        company = _seed_company(sqlite_session, upload_id=upload.id, domain="stuck-then-requeued.example")
        prompt = Prompt(name="Prompt", prompt_text="Classify {context}", enabled=True)
        sqlite_session.add(prompt)
        sqlite_session.flush()

        first_run = PipelineRun(
            campaign_id=campaign.id,
            state=PipelineRunStatus.QUEUED,
            company_ids_snapshot=[str(company.id)],
        )
        second_run = PipelineRun(
            campaign_id=campaign.id,
            state=PipelineRunStatus.RUNNING,
            company_ids_snapshot=[str(company.id)],
        )
        sqlite_session.add_all([first_run, second_run])
        sqlite_session.flush()

        sqlite_session.add_all([
            AnalysisJob(
                pipeline_run_id=first_run.id,
                upload_id=upload.id,
                company_id=company.id,
                crawl_artifact_id=uuid4(),
                prompt_id=prompt.id,
                general_model="gpt-4o",
                classify_model="gpt-4o",
                state=AnalysisJobState.QUEUED,
                terminal_state=False,
                prompt_hash="hash-queued",
            ),
            AnalysisJob(
                pipeline_run_id=second_run.id,
                upload_id=upload.id,
                company_id=company.id,
                crawl_artifact_id=uuid4(),
                prompt_id=prompt.id,
                general_model="gpt-4o",
                classify_model="gpt-4o",
                state=AnalysisJobState.RUNNING,
                terminal_state=False,
                prompt_hash="hash-running",
            ),
        ])
        sqlite_session.commit()

        stats = get_stats(session=sqlite_session, campaign_id=campaign.id, upload_id=upload.id)

        assert stats.analysis.total == 1
        assert stats.analysis.running == 1
        assert stats.analysis.queued == 0
        assert stats.analysis.succeeded == 0
        assert stats.analysis.failed == 0
    finally:
        sqlite_session.exec(delete(AnalysisJob))
        sqlite_session.exec(delete(PipelineRun))
        sqlite_session.exec(delete(Prompt))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()
