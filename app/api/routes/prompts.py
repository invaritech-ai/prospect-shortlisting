from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.decision_settings import (
    DecisionSettingsCreate,
    DecisionSettingsList,
    DecisionSettingsRead,
    DecisionSettingsUpdate,
)
from app.db.session import get_session
from app.models.classification import DecisionSettings

router = APIRouter(prefix="/v1", tags=["decision-settings"])


def _settings_hash(instruction_text: str, model: str) -> str:
    payload = json.dumps(
        {"instruction_text": instruction_text, "model": model},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


@router.get("/decision-settings", response_model=DecisionSettingsList)
def list_decision_settings(
    campaign_id: UUID = Query(...),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DecisionSettingsList:
    q = select(DecisionSettings).where(col(DecisionSettings.campaign_id) == campaign_id)
    if is_active is not None:
        q = q.where(col(DecisionSettings.is_active).is_(is_active))

    total = session.exec(select(func.count()).select_from(q.subquery())).one()
    rows = session.exec(
        q.order_by(col(DecisionSettings.created_at).desc()).limit(limit).offset(offset)
    ).all()
    return DecisionSettingsList(
        total=total,
        items=[DecisionSettingsRead.model_validate(row, from_attributes=True) for row in rows],
    )


@router.get("/decision-settings/active", response_model=DecisionSettingsRead | None)
def get_active_decision_settings(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> DecisionSettingsRead | None:
    row = session.exec(
        select(DecisionSettings)
        .where(
            col(DecisionSettings.campaign_id) == campaign_id,
            col(DecisionSettings.is_active).is_(True),
        )
        .order_by(col(DecisionSettings.created_at).desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return DecisionSettingsRead.model_validate(row, from_attributes=True)


@router.get("/decision-settings/{settings_id}", response_model=DecisionSettingsRead)
def get_decision_settings_by_id(
    settings_id: UUID,
    session: Session = Depends(get_session),
) -> DecisionSettingsRead:
    row = session.get(DecisionSettings, settings_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Decision settings not found.")
    if row.campaign_id is None:
        raise HTTPException(status_code=404, detail="Decision settings not found.")
    return DecisionSettingsRead.model_validate(row, from_attributes=True)


@router.post("/decision-settings", response_model=DecisionSettingsRead, status_code=201)
def create_decision_settings(
    body: DecisionSettingsCreate,
    session: Session = Depends(get_session),
) -> DecisionSettingsRead:
    if body.is_active:
        active_rows = session.exec(
            select(DecisionSettings).where(
                col(DecisionSettings.campaign_id) == body.campaign_id,
                col(DecisionSettings.is_active).is_(True),
            )
        ).all()
        for row in active_rows:
            row.is_active = False
            session.add(row)

    row = DecisionSettings(
        campaign_id=body.campaign_id,
        name=body.name,
        instruction_text=body.instruction_text,
        model=body.model,
        settings_hash=_settings_hash(body.instruction_text, body.model),
        is_active=body.is_active,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return DecisionSettingsRead.model_validate(row, from_attributes=True)


@router.put("/decision-settings/{settings_id}", response_model=DecisionSettingsRead)
def update_decision_settings(
    settings_id: UUID,
    body: DecisionSettingsUpdate,
    session: Session = Depends(get_session),
) -> DecisionSettingsRead:
    row = session.get(DecisionSettings, settings_id)
    if row is None or row.campaign_id is None:
        raise HTTPException(status_code=404, detail="Decision settings not found.")

    if body.name is not None:
        row.name = body.name
    if body.instruction_text is not None:
        row.instruction_text = body.instruction_text
    if body.model is not None:
        row.model = body.model

    if row.instruction_text is None or not row.instruction_text.strip():
        raise HTTPException(status_code=422, detail="instruction_text must not be empty")

    if body.is_active is True:
        active_rows = session.exec(
            select(DecisionSettings).where(
                col(DecisionSettings.campaign_id) == row.campaign_id,
                col(DecisionSettings.is_active).is_(True),
                col(DecisionSettings.id) != row.id,
            )
        ).all()
        for active in active_rows:
            active.is_active = False
            session.add(active)
        row.is_active = True
    elif body.is_active is False:
        row.is_active = False

    row.settings_hash = _settings_hash(row.instruction_text, row.model)
    session.add(row)
    session.commit()
    session.refresh(row)
    return DecisionSettingsRead.model_validate(row, from_attributes=True)


@router.delete("/decision-settings/{settings_id}", status_code=204)
def delete_decision_settings(
    settings_id: UUID,
    session: Session = Depends(get_session),
) -> None:
    row = session.get(DecisionSettings, settings_id)
    if row is None or row.campaign_id is None:
        raise HTTPException(status_code=404, detail="Decision settings not found.")
    session.delete(row)
    session.commit()
