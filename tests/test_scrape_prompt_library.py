from __future__ import annotations

import pytest
from sqlmodel import Session, delete, select

from app.api.routes.scrape_prompts import (
    activate_scrape_prompt,
    create_scrape_prompt,
    delete_scrape_prompt,
    update_scrape_prompt,
)
from app.api.schemas.scrape_prompt import ScrapePromptCreate, ScrapePromptUpdate
from app.models import ScrapePrompt


def _prompt(
    session: Session,
    *,
    name: str,
    enabled: bool = True,
    is_system_default: bool = False,
    is_active: bool = False,
) -> ScrapePrompt:
    prompt = ScrapePrompt(
        name=name,
        enabled=enabled,
        is_system_default=is_system_default,
        is_active=is_active,
        intent_text="Find relevant pages.",
        compiled_prompt_text="Find the best URL for each of these page types:\n- about",
        scrape_rules_structured={"page_kinds": ["about"]},
    )
    session.add(prompt)
    session.flush()
    return prompt


def _reset_prompts(session: Session) -> None:
    session.exec(delete(ScrapePrompt))
    session.commit()


def test_system_default_prompt_cannot_be_deleted(db_session: Session) -> None:
    from fastapi import HTTPException

    _reset_prompts(db_session)
    default_prompt = _prompt(
        db_session,
        name="Default",
        enabled=True,
        is_system_default=True,
        is_active=True,
    )
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        delete_scrape_prompt(default_prompt.id, session=db_session)
    assert exc.value.status_code == 409


def test_activate_scrape_prompt_sets_single_active(db_session: Session) -> None:
    _reset_prompts(db_session)
    old_active = _prompt(db_session, name="Old", enabled=True, is_active=True)
    new_prompt = _prompt(db_session, name="New", enabled=True, is_active=False)
    db_session.commit()

    activate_scrape_prompt(new_prompt.id, session=db_session)
    db_session.refresh(old_active)
    db_session.refresh(new_prompt)

    assert old_active.is_active is False
    assert new_prompt.is_active is True


def test_disabling_active_prompt_falls_back_to_enabled_prompt(db_session: Session) -> None:
    _reset_prompts(db_session)
    active_prompt = _prompt(db_session, name="Active", enabled=True, is_active=True)
    fallback_prompt = _prompt(db_session, name="Fallback", enabled=True, is_active=False)
    db_session.commit()

    update_scrape_prompt(
        active_prompt.id,
        ScrapePromptUpdate(enabled=False),
        session=db_session,
    )

    db_session.refresh(active_prompt)
    db_session.refresh(fallback_prompt)
    assert active_prompt.enabled is False
    assert active_prompt.is_active is False
    assert fallback_prompt.is_active is True


def test_disabling_only_active_prompt_is_rejected(db_session: Session) -> None:
    from fastapi import HTTPException

    _reset_prompts(db_session)
    active_prompt = _prompt(db_session, name="Only", enabled=True, is_active=True)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_scrape_prompt(
            active_prompt.id,
            ScrapePromptUpdate(enabled=False),
            session=db_session,
        )
    assert exc.value.status_code == 409


def test_create_scrape_prompt_can_become_active(db_session: Session) -> None:
    _reset_prompts(db_session)
    existing_active = _prompt(db_session, name="Current", enabled=True, is_active=True)
    db_session.commit()

    created = create_scrape_prompt(
        ScrapePromptCreate(
            name="New Active",
            intent_text="Find pricing and contact pages.",
            enabled=True,
            set_active=True,
        ),
        session=db_session,
    )
    db_session.refresh(existing_active)
    assert existing_active.is_active is False
    assert created.is_active is True
    assert created.scrape_rules_structured is not None

    active_ids = list(db_session.exec(select(ScrapePrompt.id).where(ScrapePrompt.is_active)).all())
    assert active_ids == [created.id]
