from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import Session, col, delete, select

from app.api.routes.pipeline_runs import (
    get_cost_reconciliation_summary,
    get_campaign_costs,
    get_pipeline_run_costs,
    get_pipeline_run_progress,
    start_pipeline_run,
)
from app.api.schemas.pipeline_run import PipelineRunStartRequest
from app.models import (
    AiUsageEvent,
    ClassificationResult,
    CrawlArtifact,
    CrawlJob,
    Campaign,
    Company,
    Prompt,
    Run,
    PipelineRun,
    PipelineRunEvent,
    ProspectContact,
    ScrapePage,
    Upload,
)
from app.models.pipeline import (
    AnalysisJob,
    AnalysisJobState,
    CompanyPipelineStage,
    ContactFetchJob,
    ContactFetchJobState,
    ContactVerifyJob,
    ContactVerifyJobState,
    CrawlJobState,
    PipelineRunStatus,
    PredictedLabel,
    RunStatus,
)
from app.models.scrape import ScrapeJob
from app.services.analysis_service import AnalysisService
from app.services.contact_runtime_service import ContactRuntimeService
from app.services.pipeline_run_orchestrator import (
    enqueue_s2_for_scrape_success,
    enqueue_s3_for_analysis_success,
    enqueue_s4_for_contact_success,
)


@pytest.fixture(autouse=True)
def _stub_scrape_task(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyTask:
        @staticmethod
        def delay(*args, **kwargs):  # noqa: ANN002,ANN003
            return None

    monkeypatch.setattr("app.api.routes.scrape_actions.scrape_website", _DummyTask())


def _clear_pipeline_test_rows(session: Session) -> None:
    session.exec(delete(AiUsageEvent))
    session.exec(delete(ProspectContact))
    session.exec(delete(ScrapePage))
    session.exec(delete(ContactVerifyJob))
    session.exec(delete(ContactFetchJob))
    session.exec(delete(AnalysisJob))
    session.exec(delete(ScrapeJob))
    session.exec(delete(Prompt))
    session.exec(delete(PipelineRunEvent))
    session.exec(delete(PipelineRun))
    session.exec(delete(Company))
    session.exec(delete(Upload))
    session.exec(delete(Campaign))
    session.commit()


@pytest.fixture(autouse=True)
def _reset_pipeline_tables(sqlite_session: Session) -> None:
    _clear_pipeline_test_rows(sqlite_session)
    yield
    _clear_pipeline_test_rows(sqlite_session)


def _seed_campaign_with_company(session: Session) -> tuple[Campaign, Company]:
    campaign = Campaign(name="Pipeline Campaign")
    session.add(campaign)
    session.flush()
    upload = Upload(
        filename="companies.csv",
        checksum=f"ck-{uuid4()}",
        row_count=1,
        valid_count=1,
        invalid_count=0,
        campaign_id=campaign.id,
    )
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
    )
    session.add(company)
    session.commit()
    session.refresh(campaign)
    session.refresh(company)
    return campaign, company


def _seed_analysis_prompt(session: Session) -> Prompt:
    prompt = Prompt(name="Pipeline Prompt", enabled=True, prompt_text="Classify {domain}")
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt


def _seed_campaign_with_companies(session: Session, count: int) -> tuple[Campaign, list[Company]]:
    campaign = Campaign(name="Pipeline Campaign")
    session.add(campaign)
    session.flush()
    upload = Upload(
        filename="companies.csv",
        checksum=f"ck-{uuid4()}",
        row_count=count,
        valid_count=count,
        invalid_count=0,
        campaign_id=campaign.id,
    )
    session.add(upload)
    session.flush()
    companies: list[Company] = []
    for idx in range(count):
        company = Company(
            upload_id=upload.id,
            raw_url=f"https://example-{idx}.com",
            normalized_url=f"https://example-{idx}.com",
            domain=f"example-{idx}.com",
        )
        session.add(company)
        companies.append(company)
    session.commit()
    session.refresh(campaign)
    for company in companies:
        session.refresh(company)
    return campaign, companies


def test_start_pipeline_run_creates_run_and_queues_scrapes(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    prompt = _seed_analysis_prompt(sqlite_session)

    response = start_pipeline_run(
        payload=PipelineRunStartRequest(
            campaign_id=campaign.id,
            analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
        ),
        session=sqlite_session,
        x_idempotency_key=None,
    )

    run = sqlite_session.get(PipelineRun, response.pipeline_run_id)
    assert run is not None
    assert run.campaign_id == campaign.id
    assert run.status == PipelineRunStatus.RUNNING
    assert response.requested_count == 1
    assert response.queued_count == 1
    assert response.reused_count == 0
    assert response.skipped_count == 0
    assert response.failed_count == 0
    assert run.company_ids_snapshot == [str(company.id)]


def test_start_pipeline_run_reuses_completed_scrape_jobs(sqlite_session: Session) -> None:
    campaign, companies = _seed_campaign_with_companies(sqlite_session, 2)
    prompt = _seed_analysis_prompt(sqlite_session)
    reused_company = companies[0]
    queued_company = companies[1]
    sqlite_session.add(
        ScrapeJob(
            website_url=reused_company.normalized_url,
            normalized_url=reused_company.normalized_url,
            domain=reused_company.domain,
            status="completed",
            terminal_state=True,
            pages_fetched_count=1,
        )
    )
    sqlite_session.commit()

    response = start_pipeline_run(
        payload=PipelineRunStartRequest(
            campaign_id=campaign.id,
            analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
        ),
        session=sqlite_session,
        x_idempotency_key=None,
    )

    assert response.requested_count == 2
    assert response.reused_count == 1
    assert response.queued_count == 1
    queued_jobs = list(
        sqlite_session.exec(
            select(ScrapeJob).where(col(ScrapeJob.pipeline_run_id) == response.pipeline_run_id)
        )
    )
    assert len(queued_jobs) == 1
    assert queued_jobs[0].normalized_url.startswith(queued_company.normalized_url)


def test_start_pipeline_run_with_selected_company_ids_scopes_run(sqlite_session: Session) -> None:
    campaign, companies = _seed_campaign_with_companies(sqlite_session, 2)
    prompt = _seed_analysis_prompt(sqlite_session)

    response = start_pipeline_run(
        payload=PipelineRunStartRequest(
            campaign_id=campaign.id,
            company_ids=[str(companies[0].id)],
            analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
        ),
        session=sqlite_session,
        x_idempotency_key=None,
    )

    assert response.requested_count == 1
    assert response.queued_count == 1
    run = sqlite_session.get(PipelineRun, response.pipeline_run_id)
    assert run is not None
    assert run.company_ids_snapshot == [str(companies[0].id)]


def test_orchestrator_s1_to_s2_creates_analysis_jobs_and_enqueues(monkeypatch: pytest.MonkeyPatch, sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    prompt = Prompt(name="p1", enabled=True, prompt_text="Classify {domain}")
    sqlite_session.add(prompt)
    run = PipelineRun(
        campaign_id=campaign.id,
        status=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
        analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
    )
    sqlite_session.add(run)
    sqlite_session.commit()
    sqlite_session.refresh(run)
    sqlite_session.refresh(prompt)

    scrape_job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        status="completed",
        terminal_state=True,
        pages_fetched_count=1,
        pipeline_run_id=run.id,
    )
    sqlite_session.add(scrape_job)
    sqlite_session.flush()
    sqlite_session.add(
        ScrapePage(
            job_id=scrape_job.id,
            url=company.normalized_url,
            canonical_url=company.normalized_url,
            page_kind="home",
            fetch_mode="static",
            status_code=200,
            markdown_content="hello",
        )
    )
    sqlite_session.commit()
    sqlite_session.refresh(scrape_job)

    queued_ids: list[str] = []

    class _DummyTask:
        @staticmethod
        def delay(job_id: str) -> None:
            queued_ids.append(job_id)

    monkeypatch.setattr("app.tasks.analysis.run_analysis_job", _DummyTask())

    enqueue_s2_for_scrape_success(engine=sqlite_session.get_bind(), scrape_job_id=scrape_job.id)

    analysis_jobs = list(
        sqlite_session.exec(select(AnalysisJob).where(col(AnalysisJob.pipeline_run_id) == run.id))
    )
    assert len(analysis_jobs) == 1
    assert queued_ids == [str(analysis_jobs[0].id)]


def test_orchestrator_s2_to_s3_creates_contact_fetch_job(monkeypatch: pytest.MonkeyPatch, sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    run = PipelineRun(
        campaign_id=campaign.id,
        status=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
    )
    sqlite_session.add(run)
    sqlite_session.commit()
    sqlite_session.refresh(run)

    analysis_job = AnalysisJob(
        run_id=uuid4(),
        upload_id=company.upload_id,
        company_id=company.id,
        crawl_artifact_id=uuid4(),
        state=AnalysisJobState.SUCCEEDED,
        terminal_state=True,
        prompt_hash="h",
        pipeline_run_id=run.id,
    )
    sqlite_session.add(analysis_job)
    company.pipeline_stage = CompanyPipelineStage.CONTACT_READY
    sqlite_session.add(company)
    sqlite_session.add(
        ClassificationResult(
            analysis_job_id=analysis_job.id,
            predicted_label=PredictedLabel.POSSIBLE,
        )
    )
    sqlite_session.commit()
    sqlite_session.refresh(analysis_job)
    sqlite_session.refresh(company)

    dispatched: list[str] = []

    class _DummyTask:
        @staticmethod
        def delay() -> None:
            dispatched.append("dispatch")

    monkeypatch.setattr("app.tasks.contacts.dispatch_contact_fetch_jobs", _DummyTask())
    ContactRuntimeService().update_control(
        sqlite_session,
        auto_enqueue_enabled=True,
        auto_enqueue_paused=False,
        auto_enqueue_max_batch_size=25,
        auto_enqueue_max_active_per_run=10,
        dispatcher_batch_size=50,
    )

    enqueue_s3_for_analysis_success(engine=sqlite_session.get_bind(), analysis_job_id=analysis_job.id)

    contact_jobs = list(
        sqlite_session.exec(select(ContactFetchJob).where(col(ContactFetchJob.pipeline_run_id) == run.id))
    )
    assert len(contact_jobs) == 1
    assert contact_jobs[0].company_id == company.id
    assert contact_jobs[0].requested_providers_json == ["snov", "apollo"]
    assert contact_jobs[0].contact_fetch_batch_id is not None
    assert dispatched == ["dispatch"]


def test_orchestrator_s3_to_s4_creates_verify_job(monkeypatch: pytest.MonkeyPatch, sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    run = PipelineRun(
        campaign_id=campaign.id,
        status=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
    )
    sqlite_session.add(run)
    sqlite_session.flush()
    fetch_job = ContactFetchJob(
        company_id=company.id,
        state=ContactFetchJobState.SUCCEEDED,
        terminal_state=True,
        pipeline_run_id=run.id,
        provider="snov",
    )
    sqlite_session.add(fetch_job)
    sqlite_session.flush()
    contact = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        source="snov",
        first_name="A",
        last_name="B",
        title="CTO",
        title_match=True,
        email="a@b.com",
        verification_status="unverified",
    )
    sqlite_session.add(contact)
    sqlite_session.commit()
    sqlite_session.refresh(fetch_job)
    sqlite_session.refresh(contact)

    queued_ids: list[str] = []

    class _DummyTask:
        @staticmethod
        def delay(job_id: str) -> None:
            queued_ids.append(job_id)

    monkeypatch.setattr("app.tasks.contacts.verify_contacts_batch", _DummyTask())

    enqueue_s4_for_contact_success(engine=sqlite_session.get_bind(), contact_fetch_job_id=fetch_job.id)

    verify_jobs = list(
        sqlite_session.exec(select(ContactVerifyJob).where(col(ContactVerifyJob.pipeline_run_id) == run.id))
    )
    assert len(verify_jobs) == 1
    assert verify_jobs[0].contact_ids_json == [str(contact.id)]
    assert queued_ids == [str(verify_jobs[0].id)]


def test_pipeline_run_progress_returns_stage_counters(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    run = PipelineRun(
        campaign_id=campaign.id,
        status=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
    )
    sqlite_session.add(run)
    sqlite_session.flush()

    sqlite_session.add(
        ScrapeJob(
            website_url="https://example.com",
            normalized_url="https://example.com",
            domain="example.com",
            status="completed",
            terminal_state=True,
            pipeline_run_id=run.id,
        )
    )
    sqlite_session.add(
        AnalysisJob(
            run_id=uuid4(),
            upload_id=uuid4(),
            company_id=company.id,
            crawl_artifact_id=uuid4(),
            state=AnalysisJobState.FAILED,
            terminal_state=True,
            prompt_hash="h1",
            pipeline_run_id=run.id,
        )
    )
    sqlite_session.add(
        ContactFetchJob(
            company_id=company.id,
            state=ContactFetchJobState.RUNNING,
            pipeline_run_id=run.id,
        )
    )
    sqlite_session.add(
        ContactVerifyJob(
            state=ContactVerifyJobState.QUEUED,
            pipeline_run_id=run.id,
        )
    )
    sqlite_session.commit()

    progress = get_pipeline_run_progress(run_id=run.id, session=sqlite_session)

    assert progress.pipeline_run_id == run.id
    assert progress.status == PipelineRunStatus.RUNNING
    assert progress.stages["s1_scrape"].completed == 1
    assert progress.stages["s2_analysis"].failed == 1
    assert progress.stages["s3_contacts"].running == 1
    assert progress.stages["s4_validation"].queued == 1


def test_pipeline_run_costs_aggregate_by_stage(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    run = PipelineRun(campaign_id=campaign.id, status=PipelineRunStatus.QUEUED, company_ids_snapshot=[str(company.id)])
    sqlite_session.add(run)
    sqlite_session.flush()
    sqlite_session.add_all(
        [
            AiUsageEvent(
                pipeline_run_id=run.id,
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s2_analysis",
                billed_cost_usd=Decimal("0.120000"),
            ),
            AiUsageEvent(
                pipeline_run_id=run.id,
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s2_analysis",
                billed_cost_usd=Decimal("0.080000"),
            ),
            AiUsageEvent(
                pipeline_run_id=run.id,
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s3_contacts",
                billed_cost_usd=Decimal("0.050000"),
            ),
        ]
    )
    sqlite_session.commit()

    result = get_pipeline_run_costs(run_id=run.id, session=sqlite_session)
    assert result.total_cost_usd == Decimal("0.250000")
    assert result.by_stage["s2_analysis"].cost_usd == Decimal("0.200000")
    assert result.by_stage["s3_contacts"].cost_usd == Decimal("0.050000")


def test_campaign_costs_aggregate_by_stage(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    sqlite_session.add_all(
        [
            AiUsageEvent(
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s2_analysis",
                billed_cost_usd=Decimal("0.110000"),
            ),
            AiUsageEvent(
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s4_validation",
                billed_cost_usd=Decimal("0.090000"),
            ),
        ]
    )
    sqlite_session.commit()

    result = get_campaign_costs(campaign_id=campaign.id, session=sqlite_session)
    assert result.total_cost_usd == Decimal("0.200000")
    assert result.by_stage["s2_analysis"].cost_usd == Decimal("0.110000")
    assert result.by_stage["s4_validation"].cost_usd == Decimal("0.090000")


def test_cost_reconciliation_summary_counts_statuses(sqlite_session: Session) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    sqlite_session.add_all(
        [
            AiUsageEvent(
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s2_analysis",
                billed_cost_usd=Decimal("0.010000"),
                reconciliation_status="pending",
            ),
            AiUsageEvent(
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s2_analysis",
                billed_cost_usd=Decimal("0.020000"),
                reconciliation_status="reconciled",
            ),
            AiUsageEvent(
                campaign_id=campaign.id,
                company_id=company.id,
                stage="s2_analysis",
                billed_cost_usd=Decimal("0.030000"),
                reconciliation_status="reconciled",
            ),
        ]
    )
    sqlite_session.commit()

    summary = get_cost_reconciliation_summary(session=sqlite_session)
    assert summary.total_events == 3
    assert summary.by_status["pending"] == 1
    assert summary.by_status["reconciled"] == 2


def test_analysis_service_records_ai_usage_event(sqlite_engine, sqlite_session: Session, monkeypatch) -> None:
    campaign, company = _seed_campaign_with_company(sqlite_session)
    prompt = Prompt(name="p-ai-usage", enabled=True, prompt_text="Classify {domain}\n{context}")
    sqlite_session.add(prompt)
    sqlite_session.flush()

    run = Run(
        upload_id=company.upload_id,
        prompt_id=prompt.id,
        general_model="openai/gpt-4o-mini",
        classify_model="openai/gpt-4o-mini",
        status=RunStatus.RUNNING,
        total_jobs=1,
        completed_jobs=0,
        failed_jobs=0,
    )
    sqlite_session.add(run)
    pipeline_run = PipelineRun(
        campaign_id=campaign.id,
        status=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
    )
    sqlite_session.add(pipeline_run)
    sqlite_session.flush()

    crawl_job = CrawlJob(
        upload_id=company.upload_id,
        company_id=company.id,
        state=CrawlJobState.SUCCEEDED,
        terminal_state=True,
    )
    sqlite_session.add(crawl_job)
    sqlite_session.flush()
    artifact = CrawlArtifact(company_id=company.id, crawl_job_id=crawl_job.id)
    sqlite_session.add(artifact)
    sqlite_session.flush()

    analysis_job = AnalysisJob(
        run_id=run.id,
        upload_id=company.upload_id,
        company_id=company.id,
        crawl_artifact_id=artifact.id,
        state=AnalysisJobState.QUEUED,
        terminal_state=False,
        prompt_hash="usage-hash",
        pipeline_run_id=pipeline_run.id,
    )
    sqlite_session.add(analysis_job)

    scrape_job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        status="completed",
        terminal_state=True,
        pages_fetched_count=1,
        pipeline_run_id=pipeline_run.id,
    )
    sqlite_session.add(scrape_job)
    sqlite_session.flush()
    sqlite_session.add(
        ScrapePage(
            job_id=scrape_job.id,
            url=company.normalized_url,
            canonical_url=company.normalized_url,
            page_kind="home",
            markdown_content="hello",
        )
    )
    sqlite_session.commit()

    class _DummyLlm:
        @staticmethod
        def chat_with_usage(**kwargs):  # noqa: ANN003, ARG004
            return (
                '{"predicted_label":"possible","confidence":0.9}',
                "",
                {
                    "provider": "openrouter",
                    "model": "openai/gpt-4o-mini",
                    "request_id": "req-1",
                    "openrouter_generation_id": "gen-1",
                    "prompt_tokens": 12,
                    "completion_tokens": 34,
                    "billed_cost_usd": 0.0042,
                },
            )

    class _DummyRunService:
        @staticmethod
        def refresh_run_status(*, session, run_id):  # noqa: ANN001, ARG004
            return None

    monkeypatch.setattr("app.services.analysis_service._analysis_llm", _DummyLlm())
    monkeypatch.setattr("app.services.analysis_service.enqueue_s3_for_analysis_success", lambda **kwargs: None)
    monkeypatch.setattr("app.services.analysis_service.recompute_company_stages", lambda *args, **kwargs: None)

    svc = AnalysisService()
    svc._run_service = _DummyRunService()  # noqa: SLF001
    result = svc.run_analysis_job(engine=sqlite_engine, analysis_job_id=analysis_job.id)
    assert result is not None

    event = sqlite_session.exec(select(AiUsageEvent).where(col(AiUsageEvent.company_id) == company.id)).one()
    assert event.pipeline_run_id == pipeline_run.id
    assert event.company_id == company.id
    assert event.stage == "s2_analysis"
