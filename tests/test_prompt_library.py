from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.prompts import create_prompt, delete_prompt, list_prompts, update_prompt
from app.api.schemas.prompt import PromptCreate, PromptUpdate
from app.models import Prompt, Run, Upload
from app.models.pipeline import RunStatus


def _prompt(session: Session, *, name: str = "Test") -> Prompt:
    p = Prompt(name=name, prompt_text="Analyze.", enabled=True)
    session.add(p)
    session.flush()
    return p


def test_list_prompts_includes_run_count(sqlite_session: Session) -> None:
    p = _prompt(sqlite_session)
    sqlite_session.commit()
    results = list_prompts(session=sqlite_session)
    found = next(r for r in results if r.id == p.id)
    assert found.run_count == 0


def test_delete_prompt_no_runs(sqlite_session: Session) -> None:
    p = _prompt(sqlite_session)
    sqlite_session.commit()
    delete_prompt(p.id, session=sqlite_session)
    remaining = list_prompts(session=sqlite_session)
    assert not any(r.id == p.id for r in remaining)


def test_delete_prompt_with_runs_raises_409(sqlite_session: Session) -> None:
    from fastapi import HTTPException

    p = _prompt(sqlite_session)
    upload = Upload(filename="t.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
    sqlite_session.add(upload)
    sqlite_session.flush()
    run = Run(
        upload_id=upload.id,
        prompt_id=p.id,
        general_model="gpt-4o",
        classify_model="gpt-4o",
        status=RunStatus.COMPLETED,
    )
    sqlite_session.add(run)
    sqlite_session.commit()
    with pytest.raises(HTTPException) as exc:
        delete_prompt(p.id, session=sqlite_session)
    assert exc.value.status_code == 409


def test_run_count_reflects_actual_runs(sqlite_session: Session) -> None:
    p = _prompt(sqlite_session, name="WithRuns")
    upload = Upload(filename="t2.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
    sqlite_session.add(upload)
    sqlite_session.flush()
    run = Run(
        upload_id=upload.id,
        prompt_id=p.id,
        general_model="gpt-4o",
        classify_model="gpt-4o",
        status=RunStatus.COMPLETED,
    )
    sqlite_session.add(run)
    sqlite_session.commit()
    results = list_prompts(session=sqlite_session)
    found = next(r for r in results if r.id == p.id)
    assert found.run_count == 1


def test_create_prompt_persists_scrape_intent_and_structured_rules(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.prompts.format_scrape_intent_to_rules",
        lambda intent: (
            {"page_kinds": ["pricing", "products"], "fallback_enabled": True, "fallback_limit": 1},
            "",
        ),
    )
    created = create_prompt(
        PromptCreate(
            name="Intent Prompt",
            prompt_text="Rubric",
            scrape_pages_intent_text="Look for product catalog and pricing pages.",
            enabled=True,
        ),
        session=sqlite_session,
    )
    assert created.scrape_pages_intent_text == "Look for product catalog and pricing pages."
    assert created.scrape_rules_structured is not None
    assert created.scrape_rules_structured.page_kinds == ["pricing", "products"]


def test_update_prompt_recomputes_rules_from_updated_intent(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt = _prompt(sqlite_session, name="Editable")
    sqlite_session.commit()
    calls: list[str | None] = []

    def _fake_formatter(intent: str | None) -> tuple[dict, str]:
        calls.append(intent)
        return ({"page_kinds": ["contact"], "fallback_enabled": True, "fallback_limit": 1}, "")

    monkeypatch.setattr("app.api.routes.prompts.format_scrape_intent_to_rules", _fake_formatter)
    updated = update_prompt(
        prompt.id,
        PromptUpdate(scrape_pages_intent_text="Find contact and support pages"),
        session=sqlite_session,
    )
    assert calls == ["Find contact and support pages"]
    assert updated.scrape_pages_intent_text == "Find contact and support pages"
    assert updated.scrape_rules_structured is not None
    assert updated.scrape_rules_structured.page_kinds == ["contact"]
