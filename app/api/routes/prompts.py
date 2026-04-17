from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from app.db.session import get_session
from app.models import Prompt, Run

router = APIRouter(prefix="/v1", tags=["prompts"])


def _as_prompt_read(prompt: Prompt, run_count: int = 0) -> PromptRead:
    return PromptRead.model_validate({**prompt.model_dump(), "run_count": run_count})


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
