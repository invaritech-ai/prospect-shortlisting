from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.prompts import create_prompt, delete_prompt, list_prompts, update_prompt
from app.api.schemas.prompt import PromptCreate, PromptUpdate
from app.models import AnalysisJob, Campaign, Company, CrawlArtifact, CrawlJob, Prompt, Upload
from app.models.pipeline import AnalysisJobState, CompanyPipelineStage


def _prompt(session: Session, *, name: str = "Test") -> Prompt:
    p = Prompt(name=name, prompt_text="Analyze.", enabled=True)
    session.add(p)
    session.flush()
    return p


def _analysis_dependencies(session: Session) -> tuple[Upload, Company, CrawlArtifact]:
    campaign = Campaign(name=f"Prompt Runs {uuid4()}")
    session.add(campaign)
    session.flush()
    upload = Upload(
        campaign_id=campaign.id,
        filename=f"{uuid4()}.csv",
        checksum=str(uuid4()),
        valid_count=1,
        invalid_count=0,
    )
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url="https://prompt-runs.example",
        normalized_url=f"https://prompt-runs-{uuid4()}.example",
        domain=f"prompt-runs-{uuid4()}.example",
        pipeline_stage=CompanyPipelineStage.SCRAPED,
    )
    session.add(company)
    session.flush()
    crawl_job = CrawlJob(upload_id=upload.id, company_id=company.id)
    session.add(crawl_job)
    session.flush()
    artifact = CrawlArtifact(company_id=company.id, crawl_job_id=crawl_job.id)
    session.add(artifact)
    session.flush()
    return upload, company, artifact


def test_list_prompts_includes_run_count(db_session: Session) -> None:
    p = _prompt(db_session)
    db_session.commit()
    results = list_prompts(session=db_session)
    found = next(r for r in results if r.id == p.id)
    assert found.run_count == 0


def test_delete_prompt_no_runs(db_session: Session) -> None:
    p = _prompt(db_session)
    db_session.commit()
    delete_prompt(p.id, session=db_session)
    remaining = list_prompts(session=db_session)
    assert not any(r.id == p.id for r in remaining)


def test_delete_prompt_with_runs_raises_409(db_session: Session) -> None:
    from fastapi import HTTPException

    p = _prompt(db_session)
    upload, company, artifact = _analysis_dependencies(db_session)
    job = AnalysisJob(
        upload_id=upload.id,
        company_id=company.id,
        crawl_artifact_id=artifact.id,
        prompt_id=p.id,
        general_model="gpt-4o",
        classify_model="gpt-4o",
        state=AnalysisJobState.SUCCEEDED,
        prompt_hash="hash",
    )
    db_session.add(job)
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        delete_prompt(p.id, session=db_session)
    assert exc.value.status_code == 409


def test_run_count_reflects_actual_runs(db_session: Session) -> None:
    p = _prompt(db_session, name="WithRuns")
    upload, company, artifact = _analysis_dependencies(db_session)
    job = AnalysisJob(
        upload_id=upload.id,
        company_id=company.id,
        crawl_artifact_id=artifact.id,
        prompt_id=p.id,
        general_model="gpt-4o",
        classify_model="gpt-4o",
        state=AnalysisJobState.SUCCEEDED,
        prompt_hash="hash",
    )
    db_session.add(job)
    db_session.commit()
    results = list_prompts(session=db_session)
    found = next(r for r in results if r.id == p.id)
    assert found.run_count == 1


def test_create_prompt_persists_core_fields_only(db_session: Session) -> None:
    created = create_prompt(
        PromptCreate(
            name="S2 Prompt",
            prompt_text="Rubric",
            enabled=True,
        ),
        session=db_session,
    )
    assert created.name == "S2 Prompt"
    assert created.prompt_text == "Rubric"
    assert created.enabled is True


def test_update_prompt_updates_core_fields_only(db_session: Session) -> None:
    prompt = _prompt(db_session, name="Editable")
    db_session.commit()
    updated = update_prompt(
        prompt.id,
        PromptUpdate(name="Updated", prompt_text="Updated rubric", enabled=False),
        session=db_session,
    )
    assert updated.name == "Updated"
    assert updated.prompt_text == "Updated rubric"
    assert updated.enabled is False
