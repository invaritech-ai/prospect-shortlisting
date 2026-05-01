from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.prompts import create_prompt, delete_prompt, list_prompts, update_prompt
from app.api.schemas.prompt import PromptCreate, PromptUpdate
from app.models import AnalysisJob, Prompt
from app.models.pipeline import AnalysisJobState


def _prompt(session: Session, *, name: str = "Test") -> Prompt:
    p = Prompt(name=name, prompt_text="Analyze.", enabled=True)
    session.add(p)
    session.flush()
    return p


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
    job = AnalysisJob(
        upload_id=uuid4(),
        company_id=uuid4(),
        crawl_artifact_id=uuid4(),
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
    job = AnalysisJob(
        upload_id=uuid4(),
        company_id=uuid4(),
        crawl_artifact_id=uuid4(),
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
