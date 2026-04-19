from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.api.schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from app.db.session import get_session
from app.models import Prompt, Run
from app.services.scrape_intent_formatter import format_scrape_intent_to_rules

router = APIRouter(prefix="/v1", tags=["prompts"])
logger = logging.getLogger(__name__)


def _as_prompt_read(prompt: Prompt, run_count: int = 0) -> PromptRead:
    return PromptRead.model_validate({**prompt.model_dump(), "run_count": run_count})


def _normalize_intent(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


@router.get("/prompts", response_model=list[PromptRead])
def list_prompts(
    session: Session = Depends(get_session),
    enabled_only: bool = Query(default=False),
) -> list[PromptRead]:
    statement = select(Prompt)
    if enabled_only:
        statement = statement.where(col(Prompt.enabled).is_(True))
    prompts = list(session.exec(statement.order_by(col(Prompt.created_at).desc(), col(Prompt.name).asc())))
    if not prompts:
        return []
    prompt_ids = [p.id for p in prompts]
    run_count_rows = list(
        session.exec(
            select(Run.prompt_id, func.count(Run.id).label("cnt"))
            .where(col(Run.prompt_id).in_(prompt_ids))
            .group_by(Run.prompt_id)
        ).all()
    )
    run_count_map: dict = {row[0]: int(row[1]) for row in run_count_rows}
    return [_as_prompt_read(p, run_count_map.get(p.id, 0)) for p in prompts]


@router.post("/prompts", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
def create_prompt(payload: PromptCreate, session: Session = Depends(get_session)) -> PromptRead:
    normalized_intent = _normalize_intent(payload.scrape_pages_intent_text)
    scrape_rules_structured, formatter_error = format_scrape_intent_to_rules(normalized_intent)
    prompt = Prompt(
        name=payload.name.strip(),
        prompt_text=payload.prompt_text.strip(),
        enabled=payload.enabled,
        scrape_pages_intent_text=normalized_intent,
        scrape_rules_structured=scrape_rules_structured,
    )
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    if formatter_error:
        log_event(
            logger,
            "prompt_scrape_rules_fallback_used",
            prompt_id=str(prompt.id),
            formatter_error=formatter_error,
        )
    return _as_prompt_read(prompt)


@router.patch("/prompts/{prompt_id}", response_model=PromptRead)
def update_prompt(prompt_id: UUID, payload: PromptUpdate, session: Session = Depends(get_session)) -> PromptRead:
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        prompt.name = str(updates["name"]).strip()
    if "prompt_text" in updates:
        prompt.prompt_text = str(updates["prompt_text"]).strip()
    if "enabled" in updates:
        prompt.enabled = bool(updates["enabled"])
    if "scrape_pages_intent_text" in updates:
        normalized_intent = _normalize_intent(updates["scrape_pages_intent_text"])
        prompt.scrape_pages_intent_text = normalized_intent
        scrape_rules_structured, formatter_error = format_scrape_intent_to_rules(normalized_intent)
        prompt.scrape_rules_structured = scrape_rules_structured
        if formatter_error:
            log_event(
                logger,
                "prompt_scrape_rules_fallback_used",
                prompt_id=str(prompt.id),
                formatter_error=formatter_error,
            )

    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    run_count = int(
        session.exec(select(func.count(Run.id)).where(col(Run.prompt_id) == prompt_id)).one()
    )
    return _as_prompt_read(prompt, run_count)


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(prompt_id: UUID, session: Session = Depends(get_session)) -> None:
    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    run_count = int(
        session.exec(select(func.count(Run.id)).where(col(Run.prompt_id) == prompt_id)).one()
    )
    if run_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: prompt has {run_count} associated run(s). Disable it instead.",
        )
    session.delete(prompt)
    session.commit()
