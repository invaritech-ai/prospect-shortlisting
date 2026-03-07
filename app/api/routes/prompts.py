from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from app.api.schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from app.db.session import get_session
from app.models import Prompt


router = APIRouter(prefix="/v1", tags=["prompts"])


def _as_prompt_read(prompt: Prompt) -> PromptRead:
    return PromptRead.model_validate(prompt, from_attributes=True)


@router.get("/prompts", response_model=list[PromptRead])
def list_prompts(
    session: Session = Depends(get_session),
    enabled_only: bool = Query(default=False),
) -> list[PromptRead]:
    statement = select(Prompt)
    if enabled_only:
        statement = statement.where(col(Prompt.enabled).is_(True))
    prompts = list(session.exec(statement.order_by(col(Prompt.created_at).desc(), col(Prompt.name).asc())))
    return [_as_prompt_read(prompt) for prompt in prompts]


@router.post("/prompts", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
def create_prompt(payload: PromptCreate, session: Session = Depends(get_session)) -> PromptRead:
    prompt = Prompt(
        name=payload.name.strip(),
        prompt_text=payload.prompt_text.strip(),
        enabled=payload.enabled,
    )
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
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

    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return _as_prompt_read(prompt)
