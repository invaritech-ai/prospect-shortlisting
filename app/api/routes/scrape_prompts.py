from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from app.api.schemas.scrape_prompt import ScrapePromptCreate, ScrapePromptRead, ScrapePromptUpdate
from app.db.session import get_session
from app.models import ScrapePrompt
from app.services.scrape_prompt_compiler import compile_scrape_prompt

router = APIRouter(prefix="/v1", tags=["scrape-prompts"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_scrape_prompt_read(prompt: ScrapePrompt) -> ScrapePromptRead:
    return ScrapePromptRead.model_validate(prompt, from_attributes=True)


def _next_enabled_prompt(session: Session, *, exclude_id: UUID | None = None) -> ScrapePrompt | None:
    prompts = list(
        session.exec(
            select(ScrapePrompt)
            .where(col(ScrapePrompt.enabled).is_(True))
            .order_by(col(ScrapePrompt.is_system_default).desc(), col(ScrapePrompt.created_at).asc())
        )
    )
    for prompt in prompts:
        if exclude_id is None or prompt.id != exclude_id:
            return prompt
    return None


def _active_prompt(session: Session) -> ScrapePrompt | None:
    return session.exec(select(ScrapePrompt).where(col(ScrapePrompt.is_active).is_(True))).first()


def _set_active_prompt(session: Session, prompt: ScrapePrompt) -> None:
    for row in session.exec(select(ScrapePrompt).where(col(ScrapePrompt.is_active).is_(True))).all():
        if row.id != prompt.id:
            row.is_active = False
            row.updated_at = _utcnow()
            session.add(row)
    prompt.is_active = True
    prompt.updated_at = _utcnow()
    session.add(prompt)


@router.get("/scrape-prompts", response_model=list[ScrapePromptRead])
def list_scrape_prompts(
    session: Session = Depends(get_session),
    enabled_only: bool = Query(default=False),
) -> list[ScrapePromptRead]:
    statement = select(ScrapePrompt)
    if enabled_only:
        statement = statement.where(col(ScrapePrompt.enabled).is_(True))
    prompts = list(
        session.exec(
            statement.order_by(
                col(ScrapePrompt.is_active).desc(),
                col(ScrapePrompt.is_system_default).desc(),
                col(ScrapePrompt.created_at).desc(),
            )
        )
    )
    return [_as_scrape_prompt_read(prompt) for prompt in prompts]


@router.post("/scrape-prompts", response_model=ScrapePromptRead, status_code=status.HTTP_201_CREATED)
def create_scrape_prompt(
    payload: ScrapePromptCreate,
    session: Session = Depends(get_session),
) -> ScrapePromptRead:
    normalized_intent = (payload.intent_text or "").strip() or None
    compiled = compile_scrape_prompt(normalized_intent)
    prompt = ScrapePrompt(
        name=payload.name.strip(),
        enabled=payload.enabled,
        is_system_default=False,
        is_active=False,
        intent_text=normalized_intent,
        compiled_prompt_text=compiled.compiled_prompt_text,
        scrape_rules_structured=compiled.scrape_rules_structured,
    )
    if payload.set_active and not prompt.enabled:
        raise HTTPException(status_code=409, detail="Cannot activate a disabled scrape prompt.")

    session.add(prompt)
    session.flush()

    has_active = _active_prompt(session) is not None
    if payload.set_active or (prompt.enabled and not has_active):
        _set_active_prompt(session, prompt)

    session.commit()
    session.refresh(prompt)
    return _as_scrape_prompt_read(prompt)


@router.patch("/scrape-prompts/{prompt_id}", response_model=ScrapePromptRead)
def update_scrape_prompt(
    prompt_id: UUID,
    payload: ScrapePromptUpdate,
    session: Session = Depends(get_session),
) -> ScrapePromptRead:
    prompt = session.get(ScrapePrompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Scrape prompt not found.")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        prompt.name = str(updates["name"]).strip()

    if "intent_text" in updates:
        normalized_intent = (updates["intent_text"] or "").strip() or None
        compiled = compile_scrape_prompt(normalized_intent)
        prompt.intent_text = normalized_intent
        prompt.compiled_prompt_text = compiled.compiled_prompt_text
        prompt.scrape_rules_structured = compiled.scrape_rules_structured

    if "enabled" in updates:
        new_enabled = bool(updates["enabled"])
        if not new_enabled and prompt.is_active:
            fallback = _next_enabled_prompt(session, exclude_id=prompt.id)
            if fallback is None:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot disable the active scrape prompt: no enabled fallback prompt exists.",
                )
            prompt.is_active = False
            _set_active_prompt(session, fallback)
        prompt.enabled = new_enabled

    if prompt.enabled and _active_prompt(session) is None:
        _set_active_prompt(session, prompt)

    prompt.updated_at = _utcnow()
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return _as_scrape_prompt_read(prompt)


@router.delete("/scrape-prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scrape_prompt(prompt_id: UUID, session: Session = Depends(get_session)) -> None:
    prompt = session.get(ScrapePrompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Scrape prompt not found.")
    if prompt.is_system_default:
        raise HTTPException(status_code=409, detail="System default scrape prompt cannot be deleted.")

    if prompt.is_active:
        fallback = _next_enabled_prompt(session, exclude_id=prompt.id)
        if fallback is None:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete the active scrape prompt: no enabled fallback prompt exists.",
            )
        _set_active_prompt(session, fallback)

    session.delete(prompt)
    session.commit()


@router.post("/scrape-prompts/{prompt_id}/activate", response_model=ScrapePromptRead)
def activate_scrape_prompt(prompt_id: UUID, session: Session = Depends(get_session)) -> ScrapePromptRead:
    prompt = session.get(ScrapePrompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Scrape prompt not found.")
    if not prompt.enabled:
        raise HTTPException(status_code=409, detail="Cannot activate a disabled scrape prompt.")

    _set_active_prompt(session, prompt)
    session.commit()
    session.refresh(prompt)
    return _as_scrape_prompt_read(prompt)
