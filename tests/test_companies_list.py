from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, col, delete

from app.api.routes.campaigns import create_campaign
from app.api.routes.companies import get_company_ids, get_letter_counts, list_companies
from app.api.routes.stats import get_company_counts
from app.api.schemas.campaign import CampaignCreate
from app.models import AnalysisJob, ClassificationResult, Company, CompanyFeedback, ContactFetchJob, Contact, PipelineRun, Prompt, ScrapeJob, Upload
from app.models.pipeline import AnalysisJobState, CompanyPipelineStage, ContactFetchJobState, PipelineRunStatus, PredictedLabel, utcnow


def _list_companies(session: Session, *, campaign_id, **overrides):
    params = {
        "session": session,
        "campaign_id": campaign_id,
        "limit": 25,
        "offset": 0,
        "decision_filter": "all",
        "scrape_filter": "all",
        "include_total": False,
        "letter": None,
        "letters": None,
        "stage_filter": "all",
        "status_filter": "all",
        "search": None,
        "sort_by": "last_activity",
        "sort_dir": "desc",
        "upload_id": None,
    }
    params.update(overrides)
    return list_companies(**params)


def _get_company_counts(session: Session, *, campaign_id, upload_id=None):
    return get_company_counts(session=session, campaign_id=campaign_id, upload_id=upload_id)


def _get_company_ids(session: Session, *, campaign_id, **overrides):
    params = {
        "session": session,
        "campaign_id": campaign_id,
        "decision_filter": "all",
        "scrape_filter": "all",
        "letter": None,
        "letters": None,
        "stage_filter": "all",
        "status_filter": "all",
        "search": None,
        "upload_id": None,
    }
    params.update(overrides)
    return get_company_ids(**params)


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
        pipeline_stage=CompanyPipelineStage.UPLOADED,
    )
    session.add(company)
    session.flush()
    return company


def _seed_scrape_job(session: Session, *, company: Company, status: str, terminal_state: bool) -> ScrapeJob:
    job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        status=status,
        terminal_state=terminal_state,
    )
    session.add(job)
    session.flush()
    return job


def test_list_companies_multi_letters_is_server_filtered(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Letters Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "letters.csv", campaign_id=campaign.id)
    try:
        _seed_company(sqlite_session, upload_id=upload.id, domain="wolf.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="xeno.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="apple.example")
        sqlite_session.commit()

        response = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            letters="w,x",
            include_total=True,
            limit=25,
            offset=0,
        )

        assert response.total == 2
        assert {item.domain for item in response.items} == {"wolf.example", "xeno.example"}
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_companies_search_is_server_filtered(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Search Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "search.csv", campaign_id=campaign.id)
    try:
        _seed_company(sqlite_session, upload_id=upload.id, domain="alpha-search.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="beta-search.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="gamma.example")
        sqlite_session.commit()

        response = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            search="search",
            include_total=True,
            limit=25,
            offset=0,
        )

        assert response.total == 2
        assert {item.domain for item in response.items} == {"alpha-search.example", "beta-search.example"}

    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_company_ids_honor_search_and_multi_letter_filters(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Select All Matching Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "select-all.csv", campaign_id=campaign.id)
    try:
        wolf = _seed_company(sqlite_session, upload_id=upload.id, domain="wolf-match.example")
        xeno = _seed_company(sqlite_session, upload_id=upload.id, domain="xeno-match.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="apple-match.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="wolf-other.example")
        sqlite_session.commit()

        response = _get_company_ids(
            session=sqlite_session,
            campaign_id=campaign.id,
            letters="w,x",
            search="match",
        )

        assert response.total == 2
        assert set(response.ids) == {wolf.id, xeno.id}
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_company_letter_counts_honor_filters(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Letter Count Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "letter-counts.csv", campaign_id=campaign.id)
    try:
        _seed_company(sqlite_session, upload_id=upload.id, domain="alpha-search.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="apex.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="beta-search.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="gamma.example")
        sqlite_session.commit()

        counts = get_letter_counts(
            session=sqlite_session,
            campaign_id=campaign.id,
            decision_filter="all",
            scrape_filter="all",
            stage_filter="all",
            status_filter="all",
            search="search",
            upload_id=None,
        )

        assert counts.counts["a"] == 1
        assert counts.counts["b"] == 1
        assert counts.counts["g"] == 0
        assert set(counts.counts) == {chr(ord("a") + i) for i in range(26)}
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_companies_exposes_discovered_and_revealed_contact_counts(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Company Contact Count Split"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "contact-count-split.csv", campaign_id=campaign.id)
    try:
        discovered_only = _seed_company(sqlite_session, upload_id=upload.id, domain="discovered-only.example")
        revealed = _seed_company(sqlite_session, upload_id=upload.id, domain="revealed.example")
        discovered_job = ContactFetchJob(company_id=discovered_only.id, provider="snov")
        revealed_job = ContactFetchJob(company_id=revealed.id, provider="snov")
        sqlite_session.add_all([discovered_job, revealed_job])
        sqlite_session.flush()
        sqlite_session.add_all(
            [
                Contact(
                    company_id=discovered_only.id,
                    contact_fetch_job_id=discovered_job.id,
                    source_provider="snov",
                    provider_person_id="disc-1",
                    first_name="Dana",
                    last_name="Discovery",
                    title="Marketing Director",
                    title_match=True,
                ),
                Contact(
                    company_id=discovered_only.id,
                    contact_fetch_job_id=discovered_job.id,
                    source_provider="snov",
                    provider_person_id="disc-2",
                    first_name="Uma",
                    last_name="Unmatched",
                    title="Assistant",
                    title_match=False,
                ),
                Contact(
                    company_id=revealed.id,
                    contact_fetch_job_id=revealed_job.id,
                    source_provider="snov",
                    provider_person_id="rev-1",
                    first_name="Rae",
                    last_name="Reveal",
                    title="Marketing Director",
                    title_match=True,
                ),
                Contact(
                    company_id=revealed.id,
                    contact_fetch_job_id=revealed_job.id,
                    source_provider="snov",
                    provider_person_id="rev-2",
                    first_name="Rae",
                    last_name="Reveal",
                    title="Marketing Director",
                    title_match=True,
                    email="rae@revealed.example",
                ),
            ]
        )
        sqlite_session.commit()

        response = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            include_total=True,
            limit=25,
            offset=0,
        )

        by_domain = {item.domain: item for item in response.items}
        assert by_domain["discovered-only.example"].contact_count == 0
        assert by_domain["discovered-only.example"].revealed_contact_count == 0
        assert by_domain["discovered-only.example"].discovered_contact_count == 2
        assert by_domain["discovered-only.example"].discovered_title_matched_count == 1
        assert by_domain["revealed.example"].contact_count == 1
        assert by_domain["revealed.example"].revealed_contact_count == 1
        assert by_domain["revealed.example"].discovered_contact_count == 1
        assert by_domain["revealed.example"].discovered_title_matched_count == 1
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_company_counts_honors_upload_scope(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Count Scope"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, "scope-a.csv", campaign_id=campaign.id)
    upload_b = _seed_upload(sqlite_session, "scope-b.csv", campaign_id=campaign.id)
    try:
        _seed_company(sqlite_session, upload_id=upload_a.id, domain="scope-a.example")
        _seed_company(sqlite_session, upload_id=upload_b.id, domain="scope-b.example")
        sqlite_session.commit()

        scoped = _get_company_counts(session=sqlite_session, campaign_id=campaign.id, upload_id=upload_a.id)
        scoped_b = _get_company_counts(session=sqlite_session, campaign_id=campaign.id, upload_id=upload_b.id)
        unscoped = _get_company_counts(session=sqlite_session, campaign_id=campaign.id)

        assert scoped.total == 1
        assert scoped_b.total == 1
        assert unscoped.total >= (scoped.total + scoped_b.total)
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id).in_([upload_a.id, upload_b.id])))
        sqlite_session.exec(delete(Upload).where(col(Upload.id).in_([upload_a.id, upload_b.id])))
        sqlite_session.commit()


def test_company_counts_scrape_buckets_reconcile(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Scrape Buckets"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "scrape-buckets.csv", campaign_id=campaign.id)
    try:
        _not_started = _seed_company(sqlite_session, upload_id=upload.id, domain="not-started.example")
        in_progress = _seed_company(sqlite_session, upload_id=upload.id, domain="in-progress.example")
        done = _seed_company(sqlite_session, upload_id=upload.id, domain="done.example")
        cancelled = _seed_company(sqlite_session, upload_id=upload.id, domain="cancelled.example")
        permanent = _seed_company(sqlite_session, upload_id=upload.id, domain="permanent.example")
        soft = _seed_company(sqlite_session, upload_id=upload.id, domain="soft.example")
        sqlite_session.add_all(
            [
                _seed_scrape_job(sqlite_session, company=in_progress, status="running", terminal_state=False),
                _seed_scrape_job(sqlite_session, company=done, status="completed", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=cancelled, status="cancelled", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=permanent, status="site_unavailable", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=soft, status="failed", terminal_state=True),
            ]
        )
        sqlite_session.commit()

        counts = _get_company_counts(session=sqlite_session, campaign_id=campaign.id, upload_id=upload.id)
        assert counts.total == 6
        assert counts.scrape_not_started == 1
        assert counts.scrape_in_progress == 1
        assert counts.scrape_done == 1
        assert counts.scrape_cancelled == 1
        assert counts.scrape_permanent_fail == 1
        assert counts.scrape_soft_fail == 1
        assert counts.not_scraped == 1
        assert counts.scrape_not_started + counts.scrape_in_progress + counts.scrape_done + counts.scrape_cancelled + counts.scrape_permanent_fail + counts.scrape_soft_fail == counts.total

        not_started_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            scrape_filter="not-started",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in not_started_rows.items] == ["not-started.example"]

        in_progress_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            scrape_filter="in-progress",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in in_progress_rows.items] == ["in-progress.example"]

        done_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            scrape_filter="done",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in done_rows.items] == ["done.example"]

        cancelled_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            scrape_filter="cancelled",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in cancelled_rows.items] == ["cancelled.example"]

        permanent_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            scrape_filter="permanent",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in permanent_rows.items] == ["permanent.example"]

        soft_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            scrape_filter="soft",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in soft_rows.items] == ["soft.example"]
    finally:
        sqlite_session.exec(delete(ScrapeJob))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_companies_pipeline_status_filter_is_server_filtered(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Pipeline Status Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "pipeline-status.csv", campaign_id=campaign.id)
    try:
        _not_started = _seed_company(sqlite_session, upload_id=upload.id, domain="not-started.example")
        in_progress_scrape = _seed_company(sqlite_session, upload_id=upload.id, domain="scrape-running.example")
        in_progress_contact = _seed_company(sqlite_session, upload_id=upload.id, domain="contact-running.example")
        complete = _seed_company(sqlite_session, upload_id=upload.id, domain="complete.example")
        cancelled = _seed_company(sqlite_session, upload_id=upload.id, domain="cancelled.example")
        permanent = _seed_company(sqlite_session, upload_id=upload.id, domain="permanent.example")
        soft = _seed_company(sqlite_session, upload_id=upload.id, domain="soft.example")
        failed_contact = _seed_company(sqlite_session, upload_id=upload.id, domain="contact-failed.example")

        sqlite_session.add_all(
            [
                _seed_scrape_job(sqlite_session, company=in_progress_scrape, status="running", terminal_state=False),
                _seed_scrape_job(sqlite_session, company=in_progress_contact, status="completed", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=complete, status="completed", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=cancelled, status="cancelled", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=permanent, status="site_unavailable", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=soft, status="failed", terminal_state=True),
                _seed_scrape_job(sqlite_session, company=failed_contact, status="completed", terminal_state=True),
            ]
        )
        sqlite_session.add(
            ContactFetchJob(company_id=in_progress_contact.id, provider="snov", state=ContactFetchJobState.RUNNING, terminal_state=False)
        )
        sqlite_session.add(
            ContactFetchJob(company_id=failed_contact.id, provider="snov", state=ContactFetchJobState.FAILED, terminal_state=True)
        )
        sqlite_session.add(
            CompanyFeedback(company_id=complete.id, manual_label="possible")
        )
        sqlite_session.commit()

        in_progress_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            status_filter="in-progress",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert {item.domain for item in in_progress_rows.items} == {"scrape-running.example", "contact-running.example"}

        complete_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            status_filter="complete",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in complete_rows.items] == ["complete.example"]

        cancelled_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            status_filter="cancelled",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert [item.domain for item in cancelled_rows.items] == ["cancelled.example"]

        soft_rows = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            status_filter="soft-failures",
            include_total=True,
            limit=25,
            offset=0,
        )
        assert {item.domain for item in soft_rows.items} == {"soft.example", "contact-failed.example"}

    finally:
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_([in_progress_contact.id, failed_contact.id])))
        sqlite_session.exec(delete(CompanyFeedback).where(col(CompanyFeedback.company_id) == complete.id))
        sqlite_session.exec(delete(ScrapeJob))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_companies_invalid_sort_by_raises_422(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Sort Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "sort.csv", campaign_id=campaign.id)
    try:
        _seed_company(sqlite_session, upload_id=upload.id, domain="sort.example")
        sqlite_session.commit()

        with pytest.raises(HTTPException) as excinfo:
            _list_companies(session=sqlite_session, campaign_id=campaign.id, sort_by="not_a_real_field")
        assert excinfo.value.status_code == 422
        with pytest.raises(HTTPException) as excinfo_dir:
            _list_companies(session=sqlite_session, campaign_id=campaign.id, sort_dir="sideways")
        assert excinfo_dir.value.status_code == 422
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_company_counts_stage_buckets_are_exact(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Stage Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "stages.csv", campaign_id=campaign.id)
    try:
        for domain, stage in [
            ("up.example", CompanyPipelineStage.UPLOADED),
            ("sc.example", CompanyPipelineStage.SCRAPED),
            ("cl.example", CompanyPipelineStage.CLASSIFIED),
            ("cr.example", CompanyPipelineStage.CONTACT_READY),
        ]:
            company = _seed_company(sqlite_session, upload_id=upload.id, domain=domain)
            company.pipeline_stage = stage
            sqlite_session.add(company)
        sqlite_session.commit()

        counts = _get_company_counts(session=sqlite_session, campaign_id=campaign.id, upload_id=upload.id)
        assert counts.total == 4
        assert counts.uploaded == 1
        assert counts.scraped == 1
        assert counts.classified == 1
        assert counts.contact_ready == 1
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_companies_review_job_id_tracks_displayed_decision(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Review Detail Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "review-detail.csv", campaign_id=campaign.id)
    try:
        company = _seed_company(sqlite_session, upload_id=upload.id, domain="review-detail.example")
        prompt = Prompt(name="Prompt", prompt_text="Classify {context}", enabled=True)
        sqlite_session.add(prompt)
        sqlite_session.flush()

        prior_run = PipelineRun(
            campaign_id=campaign.id,
            state=PipelineRunStatus.SUCCEEDED,
            company_ids_snapshot=[str(company.id)],
        )
        rerun = PipelineRun(
            campaign_id=campaign.id,
            state=PipelineRunStatus.RUNNING,
            company_ids_snapshot=[str(company.id)],
        )
        sqlite_session.add_all([prior_run, rerun])
        sqlite_session.flush()

        completed_job = AnalysisJob(
            pipeline_run_id=prior_run.id,
            upload_id=upload.id,
            company_id=company.id,
            crawl_artifact_id=uuid4(),
            prompt_id=prompt.id,
            general_model="gpt-4o",
            classify_model="gpt-4o",
            state=AnalysisJobState.SUCCEEDED,
            terminal_state=True,
            prompt_hash="hash-complete",
        )
        queued_job = AnalysisJob(
            pipeline_run_id=rerun.id,
            upload_id=upload.id,
            company_id=company.id,
            crawl_artifact_id=uuid4(),
            prompt_id=prompt.id,
            general_model="gpt-4o",
            classify_model="gpt-4o",
            state=AnalysisJobState.QUEUED,
            terminal_state=False,
            prompt_hash="hash-queued",
        )
        sqlite_session.add_all([completed_job, queued_job])
        sqlite_session.flush()

        sqlite_session.add(
            ClassificationResult(
                analysis_job_id=completed_job.id,
                predicted_label=PredictedLabel.CRAP,
                confidence=0.91,
                reasoning_json={"signals": {"fit": False}},
                evidence_json={"evidence": ["not relevant"]},
                input_hash="input-1",
                from_cache=False,
            )
        )
        sqlite_session.commit()

        response = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            upload_id=upload.id,
            include_total=True,
            limit=25,
            offset=0,
        )

        item = next(item for item in response.items if item.domain == company.domain)
        assert item.latest_decision == "crap"
        assert item.latest_analysis_job_id == completed_job.id
        assert item.latest_analysis_pipeline_run_id == prior_run.id
        assert item.latest_analysis_status == "queued"
    finally:
        sqlite_session.exec(delete(ClassificationResult))
        sqlite_session.exec(delete(AnalysisJob))
        sqlite_session.exec(delete(PipelineRun))
        sqlite_session.exec(delete(Prompt))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_companies_uses_latest_contact_fetch_activity_timestamp(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Activity Scope"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "activity.csv", campaign_id=campaign.id)
    company = _seed_company(sqlite_session, upload_id=upload.id, domain="activity.example")
    try:
        older_but_updated = ContactFetchJob(company_id=company.id, provider="snov", state=ContactFetchJobState.RUNNING)
        older_but_updated.created_at = utcnow() - timedelta(days=2)
        older_but_updated.updated_at = utcnow()
        newer_but_stale = ContactFetchJob(company_id=company.id, provider="apollo", state=ContactFetchJobState.QUEUED)
        newer_but_stale.created_at = utcnow() - timedelta(days=1)
        newer_but_stale.updated_at = utcnow() - timedelta(days=1)
        sqlite_session.add(older_but_updated)
        sqlite_session.add(newer_but_stale)
        sqlite_session.commit()

        response = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            include_total=True,
            limit=25,
            offset=0,
        )

        assert response.items[0].contact_fetch_status == ContactFetchJobState.RUNNING.value
        expected_last_activity = older_but_updated.updated_at.replace(
            tzinfo=response.items[0].last_activity.tzinfo,
        )
        assert response.items[0].last_activity == expected_last_activity
    finally:
        sqlite_session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id) == company.id))
        sqlite_session.exec(delete(Company).where(col(Company.id) == company.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_list_companies_sort_scrape_updated_at_desc(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Scrape Sort"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "scrape-sort.csv", campaign_id=campaign.id)
    c_old = _seed_company(sqlite_session, upload_id=upload.id, domain="aa.example")
    c_new = _seed_company(sqlite_session, upload_id=upload.id, domain="zz.example")
    try:
        j_old = _seed_scrape_job(sqlite_session, company=c_old, status="completed", terminal_state=True)
        j_old.updated_at = utcnow() - timedelta(hours=3)
        j_new = _seed_scrape_job(sqlite_session, company=c_new, status="completed", terminal_state=True)
        j_new.updated_at = utcnow()
        sqlite_session.commit()

        response = _list_companies(
            session=sqlite_session,
            campaign_id=campaign.id,
            include_total=True,
            limit=25,
            offset=0,
            sort_by="scrape_updated_at",
            sort_dir="desc",
        )

        assert response.total == 2
        assert response.items[0].domain == "zz.example"
        assert response.items[1].domain == "aa.example"
    finally:
        sqlite_session.exec(delete(ScrapeJob).where(col(ScrapeJob.normalized_url).in_([c_old.normalized_url, c_new.normalized_url])))
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()
