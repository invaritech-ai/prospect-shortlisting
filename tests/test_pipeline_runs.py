from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.pipeline_run import PipelineRunStartRequest
from app.models import AnalysisJob, Company, PipelineRun, Prompt, ScrapeJob, ScrapePage, Upload
from app.models.pipeline import PipelineRunStatus


def _seed_upload(session: Session, *, campaign_id) -> Upload:
    upload = Upload(
        campaign_id=campaign_id,
        filename="s2.csv",
        checksum=str(uuid4()),
        row_count=2,
        valid_count=2,
        invalid_count=0,
    )
    session.add(upload)
    session.flush()
    return upload


def _seed_company(session: Session, *, upload_id, domain: str) -> Company:
    company = Company(
        upload_id=upload_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
    )
    session.add(company)
    session.flush()
    return company


def _seed_prompt(session: Session, *, enabled: bool = True) -> Prompt:
    prompt = Prompt(
        name="ICP v1",
        prompt_text="Classify {domain}\n\n{context}",
        enabled=enabled,
    )
    session.add(prompt)
    session.flush()
    return prompt


def _seed_scrape(session: Session, *, company: Company) -> None:
    job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        state="succeeded",
        terminal_state=True,
        markdown_pages_count=1,
        pages_fetched_count=1,
    )
    session.add(job)
    session.flush()
    session.add(
        ScrapePage(
            job_id=job.id,
            url=company.normalized_url,
            canonical_url=company.normalized_url,
            page_kind="home",
            markdown_content="# Home",
        )
    )
    session.flush()


@pytest.mark.asyncio
async def test_start_pipeline_run_only_enqueues_companies_with_scraped_info(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.pipeline_runs import get_pipeline_run_progress, start_pipeline_run
    from app.jobs import ai_decision as ai_decision_mod

    campaign = create_campaign(payload=CampaignCreate(name="S2"), session=db_session)
    upload = _seed_upload(db_session, campaign_id=campaign.id)
    eligible = _seed_company(db_session, upload_id=upload.id, domain="eligible.example")
    skipped = _seed_company(db_session, upload_id=upload.id, domain="skipped.example")
    prompt = _seed_prompt(db_session)
    _seed_scrape(db_session, company=eligible)
    db_session.commit()

    deferred: list[dict] = []

    async def fake_defer_async(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(ai_decision_mod.run_ai_decision, "defer_async", fake_defer_async)

    result = await start_pipeline_run(
        payload=PipelineRunStartRequest(
            campaign_id=campaign.id,
            company_ids=[str(eligible.id), str(skipped.id)],
            analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
        ),
        session=db_session,
    )

    assert result.requested_count == 2
    assert result.queued_count == 1
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert len(deferred) == 1

    run = db_session.get(PipelineRun, result.pipeline_run_id)
    assert run is not None
    jobs = list(db_session.exec(select(AnalysisJob).where(AnalysisJob.pipeline_run_id == run.id)))
    assert len(jobs) == 1
    assert jobs[0].company_id == eligible.id

    progress = get_pipeline_run_progress(run.id, session=db_session)
    assert progress.pipeline_run_id == run.id
    assert progress.requested_count == 2
    assert progress.queued_count == 1
    assert progress.skipped_count == 1
    assert progress.state in (PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING)
    assert progress.stages["analysis"].total == 1


@pytest.mark.asyncio
async def test_start_pipeline_run_rejects_disabled_prompt(
    db_session: Session,
) -> None:
    from fastapi import HTTPException

    from app.api.routes.pipeline_runs import start_pipeline_run

    campaign = create_campaign(payload=CampaignCreate(name="S2"), session=db_session)
    upload = _seed_upload(db_session, campaign_id=campaign.id)
    company = _seed_company(db_session, upload_id=upload.id, domain="eligible.example")
    prompt = _seed_prompt(db_session, enabled=False)
    _seed_scrape(db_session, company=company)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await start_pipeline_run(
            payload=PipelineRunStartRequest(
                campaign_id=campaign.id,
                company_ids=[str(company.id)],
                analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
            ),
            session=db_session,
        )

    assert exc.value.status_code == 400
