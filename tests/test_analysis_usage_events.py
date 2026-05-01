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
    ScrapeJob,
    ScrapePage,
    Upload,
)
from app.models.pipeline import AnalysisJobState, CrawlJobState, PipelineRunStatus
from app.services.analysis_service import AnalysisService


def _clear_analysis_usage_rows(session: Session) -> None:
    session.exec(delete(AiUsageEvent))
    session.exec(delete(AnalysisJob))
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
def _reset_analysis_usage_tables(db_session: Session):
    _clear_analysis_usage_rows(db_session)
    yield


def test_run_analysis_job_records_ai_usage_event_on_success(
    db_engine,
    db_session: Session,
    monkeypatch,
) -> None:
    campaign = Campaign(name="Campaign")
    db_session.add(campaign)
    db_session.flush()

    upload = Upload(
        filename="companies.csv",
        checksum=f"ck-{uuid4()}",
        row_count=1,
        valid_count=1,
        invalid_count=0,
        campaign_id=campaign.id,
    )
    db_session.add(upload)
    db_session.flush()

    company = Company(
        upload_id=upload.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
    )
    db_session.add(company)
    db_session.flush()

    prompt = Prompt(name="p1", enabled=True, prompt_text="Classify {domain}\n{context}")
    db_session.add(prompt)
    db_session.flush()

    pipeline_run = PipelineRun(
        campaign_id=campaign.id,
        state=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
    )
    db_session.add(pipeline_run)
    db_session.flush()

    crawl_job = CrawlJob(
        upload_id=upload.id,
        company_id=company.id,
        state=CrawlJobState.SUCCEEDED,
        terminal_state=True,
    )
    db_session.add(crawl_job)
    db_session.flush()

    artifact = CrawlArtifact(company_id=company.id, crawl_job_id=crawl_job.id)
    db_session.add(artifact)
    db_session.flush()

    analysis_job = AnalysisJob(
        upload_id=upload.id,
        company_id=company.id,
        crawl_artifact_id=artifact.id,
        prompt_id=prompt.id,
        general_model="openai/gpt-4o-mini",
        classify_model="openai/gpt-4o-mini",
        state=AnalysisJobState.QUEUED,
        terminal_state=False,
        prompt_hash="hash-1",
        pipeline_run_id=pipeline_run.id,
    )
    db_session.add(analysis_job)
    db_session.flush()

    scrape_job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        state="succeeded",
        terminal_state=True,
        pipeline_run_id=pipeline_run.id,
        pages_fetched_count=1,
    )
    db_session.add(scrape_job)
    db_session.flush()

    scrape_page = ScrapePage(
        job_id=scrape_job.id,
        url=company.normalized_url,
        canonical_url=company.normalized_url,
        page_kind="home",
        markdown_content="# Example page",
    )
    db_session.add(scrape_page)
    db_session.commit()

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
        "app.services.analysis_service.recompute_company_stages",
        lambda *args, **kwargs: None,
    )

    service = AnalysisService()
    service._run_service = _DummyRunService()  # noqa: SLF001
    result = service.run_analysis_job(engine=db_engine, analysis_job_id=analysis_job.id)
    assert result is not None

    usage_events = list(db_session.exec(select(AiUsageEvent)))
    assert len(usage_events) == 1
    usage = usage_events[0]
    assert usage.pipeline_run_id == pipeline_run.id
    assert usage.campaign_id == campaign.id
    assert usage.company_id == company.id
    assert usage.stage == "analysis"
    assert usage.attempt_number == 1
    assert usage.provider == "openrouter"
    assert usage.model == "openai/gpt-4o-mini"
    assert usage.request_id == "req_1"
    assert usage.openrouter_generation_id == "gen_1"
    assert usage.input_tokens == 120
    assert usage.output_tokens == 30
    assert usage.billed_cost_usd == Decimal("0.0042")


def test_run_analysis_job_completes_without_s3_enqueue_hook(
    db_engine,
    db_session: Session,
    monkeypatch,
) -> None:
    campaign = Campaign(name="Campaign")
    db_session.add(campaign)
    db_session.flush()

    upload = Upload(
        filename="companies.csv",
        checksum=f"ck-{uuid4()}",
        row_count=1,
        valid_count=1,
        invalid_count=0,
        campaign_id=campaign.id,
    )
    db_session.add(upload)
    db_session.flush()

    company = Company(
        upload_id=upload.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
    )
    db_session.add(company)
    db_session.flush()

    prompt = Prompt(name="p1", enabled=True, prompt_text="Classify {domain}\n{context}")
    db_session.add(prompt)
    db_session.flush()

    pipeline_run = PipelineRun(
        campaign_id=campaign.id,
        state=PipelineRunStatus.RUNNING,
        company_ids_snapshot=[str(company.id)],
    )
    db_session.add(pipeline_run)
    db_session.flush()

    crawl_job = CrawlJob(
        upload_id=upload.id,
        company_id=company.id,
        state=CrawlJobState.SUCCEEDED,
        terminal_state=True,
    )
    db_session.add(crawl_job)
    db_session.flush()

    artifact = CrawlArtifact(company_id=company.id, crawl_job_id=crawl_job.id)
    db_session.add(artifact)
    db_session.flush()

    analysis_job = AnalysisJob(
        upload_id=upload.id,
        company_id=company.id,
        crawl_artifact_id=artifact.id,
        prompt_id=prompt.id,
        general_model="openai/gpt-4o-mini",
        classify_model="openai/gpt-4o-mini",
        state=AnalysisJobState.QUEUED,
        terminal_state=False,
        prompt_hash="hash-1",
        pipeline_run_id=pipeline_run.id,
    )
    db_session.add(analysis_job)
    db_session.flush()

    scrape_job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        state="succeeded",
        terminal_state=True,
        pipeline_run_id=pipeline_run.id,
        pages_fetched_count=1,
        markdown_pages_count=1,
    )
    db_session.add(scrape_job)
    db_session.flush()

    db_session.add(
        ScrapePage(
            job_id=scrape_job.id,
            url=company.normalized_url,
            canonical_url=company.normalized_url,
            page_kind="home",
            markdown_content="# Example page",
        )
    )
    db_session.commit()

    class _DummyLlm:
        @staticmethod
        def chat_with_usage(**kwargs):  # noqa: ANN003, ARG004
            return (
                '{"predicted_label":"possible","confidence":0.91,"evidence":["home"]}',
                "",
                {
                    "provider": "openrouter",
                    "model": "openai/gpt-4o-mini",
                    "request_id": "req_2",
                    "openrouter_generation_id": "gen_2",
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "billed_cost_usd": 0.0042,
                },
            )

    monkeypatch.setattr("app.services.analysis_service._analysis_llm", _DummyLlm())
    monkeypatch.setattr(
        "app.services.analysis_service.recompute_company_stages",
        lambda *args, **kwargs: None,
    )

    service = AnalysisService()
    result = service.run_analysis_job(engine=db_engine, analysis_job_id=analysis_job.id)

    assert result is not None
    assert result.state == AnalysisJobState.SUCCEEDED
    assert result.terminal_state is True
