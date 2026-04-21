from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import delete
from sqlmodel import Session, select

from app.models import (
    AiUsageEvent,
    AnalysisJob,
    Campaign,
    Company,
    CrawlArtifact,
    CrawlJob,
    PipelineRun,
    Prompt,
    Run,
    ScrapeJob,
    ScrapePage,
    Upload,
)
from app.models.pipeline import AnalysisJobState, CrawlJobState, PipelineRunStatus, RunStatus
from app.services.analysis_service import AnalysisService


def _clear_analysis_usage_rows(session: Session) -> None:
    session.exec(delete(AiUsageEvent))
    session.exec(delete(AnalysisJob))
    session.exec(delete(Run))
    session.exec(delete(CrawlArtifact))
    session.exec(delete(CrawlJob))
    session.exec(delete(ScrapePage))
    session.exec(delete(ScrapeJob))
    session.exec(delete(PipelineRun))
    session.exec(delete(Prompt))
    session.exec(delete(Company))
    session.exec(delete(Upload))
    session.exec(delete(Campaign))
    session.commit()


@pytest.fixture(autouse=True)
def _reset_analysis_usage_tables(sqlite_session: Session):
    _clear_analysis_usage_rows(sqlite_session)
    yield
    _clear_analysis_usage_rows(sqlite_session)


def test_run_analysis_job_records_ai_usage_event_on_success(
    sqlite_engine,
    sqlite_session: Session,
    monkeypatch,
) -> None:
    campaign = Campaign(name="Campaign")
    sqlite_session.add(campaign)
    sqlite_session.flush()

    upload = Upload(
        filename="companies.csv",
        checksum=f"ck-{uuid4()}",
        row_count=1,
        valid_count=1,
        invalid_count=0,
        campaign_id=campaign.id,
    )
    sqlite_session.add(upload)
    sqlite_session.flush()

    company = Company(
        upload_id=upload.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
    )
    sqlite_session.add(company)
    sqlite_session.flush()

    prompt = Prompt(name="p1", enabled=True, prompt_text="Classify {domain}\n{context}")
    sqlite_session.add(prompt)
    sqlite_session.flush()

    run = Run(
        upload_id=upload.id,
        prompt_id=prompt.id,
        general_model="openai/gpt-4o-mini",
        classify_model="openai/gpt-4o-mini",
        status=RunStatus.RUNNING,
        total_jobs=1,
        completed_jobs=0,
        failed_jobs=0,
    )
    sqlite_session.add(run)
    sqlite_session.flush()

    pipeline_run = PipelineRun(
        campaign_id=campaign.id,
        status=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
    )
    sqlite_session.add(pipeline_run)
    sqlite_session.flush()

    crawl_job = CrawlJob(
        upload_id=upload.id,
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
        upload_id=upload.id,
        company_id=company.id,
        crawl_artifact_id=artifact.id,
        state=AnalysisJobState.QUEUED,
        terminal_state=False,
        prompt_hash="hash-1",
        pipeline_run_id=pipeline_run.id,
    )
    sqlite_session.add(analysis_job)
    sqlite_session.flush()

    scrape_job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        status="completed",
        terminal_state=True,
        pipeline_run_id=pipeline_run.id,
        pages_fetched_count=1,
    )
    sqlite_session.add(scrape_job)
    sqlite_session.flush()

    scrape_page = ScrapePage(
        job_id=scrape_job.id,
        url=company.normalized_url,
        canonical_url=company.normalized_url,
        page_kind="home",
        markdown_content="# Example page",
    )
    sqlite_session.add(scrape_page)
    sqlite_session.commit()

    class _DummyRunService:
        @staticmethod
        def refresh_run_status(*, session, run_id):  # noqa: ANN001, ARG004
            return None

    class _DummyLlm:
        @staticmethod
        def chat_with_usage(**kwargs):  # noqa: ANN003, ARG004
            return (
                '{"predicted_label":"possible","confidence":0.91,"evidence":["home"]}',
                "",
                {
                    "provider": "openrouter",
                    "model": "openai/gpt-4o-mini",
                    "request_id": "req_1",
                    "openrouter_generation_id": "gen_1",
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "billed_cost_usd": 0.0042,
                },
            )

    monkeypatch.setattr("app.services.analysis_service._analysis_llm", _DummyLlm())
    monkeypatch.setattr(
        "app.services.analysis_service.enqueue_s3_for_analysis_success",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.analysis_service.recompute_company_stages",
        lambda *args, **kwargs: None,
    )

    service = AnalysisService()
    service._run_service = _DummyRunService()  # noqa: SLF001
    result = service.run_analysis_job(engine=sqlite_engine, analysis_job_id=analysis_job.id)
    assert result is not None

    usage_events = list(sqlite_session.exec(select(AiUsageEvent)))
    assert len(usage_events) == 1
    usage = usage_events[0]
    assert usage.pipeline_run_id == pipeline_run.id
    assert usage.campaign_id == campaign.id
    assert usage.company_id == company.id
    assert usage.stage == "s2_analysis"
    assert usage.attempt_number == 1
    assert usage.provider == "openrouter"
    assert usage.model == "openai/gpt-4o-mini"
    assert usage.request_id == "req_1"
    assert usage.openrouter_generation_id == "gen_1"
    assert usage.input_tokens == 120
    assert usage.output_tokens == 30
    assert usage.billed_cost_usd == Decimal("0.0042")
