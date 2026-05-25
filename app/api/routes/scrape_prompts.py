"""Scrape settings — append-only per-campaign config for S1 scraping."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.scrape import (
    DEFAULT_STRUCTURED_RULES,
    ScrapeSettingsCreate,
    ScrapeSettingsList,
    ScrapeSettingsRead,
    ScrapeSettingsUpdate,
)
from app.db.session import get_session
from app.models.scrape import ScrapeSettings
from app.services.scrape_prompt_compiler import build_scrape_rules_snapshot

router = APIRouter(prefix="/v1", tags=["scrape-settings"])


def _settings_hash(structured_rules: dict | None, instruction_text: str | None) -> str:
    payload = json.dumps(
        {"rules": structured_rules, "instruction": instruction_text}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


@router.get("/scrape-settings", response_model=ScrapeSettingsRead | None)
def get_scrape_settings(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ScrapeSettingsRead | None:
    """Return the active settings row for a campaign, or None if not configured."""
    row = session.exec(
        select(ScrapeSettings)
        .where(
            col(ScrapeSettings.campaign_id) == campaign_id,
            col(ScrapeSettings.is_active).is_(True),
        )
        .order_by(col(ScrapeSettings.created_at).desc())
        .limit(1)
    ).first()

    if row is None:
        return None

    return ScrapeSettingsRead.model_validate(row, from_attributes=True)


@router.get("/scrape-settings/history", response_model=ScrapeSettingsList)
def list_scrape_settings(
    campaign_id: UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ScrapeSettingsList:
    q = select(ScrapeSettings).where(col(ScrapeSettings.campaign_id) == campaign_id)
    total = session.exec(select(func.count()).select_from(q.subquery())).one()
    rows = session.exec(
        q.order_by(col(ScrapeSettings.created_at).desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ScrapeSettingsList(
        total=total,
        items=[ScrapeSettingsRead.model_validate(row, from_attributes=True) for row in rows],
    )


@router.get("/scrape-settings/{settings_id}", response_model=ScrapeSettingsRead)
def get_scrape_settings_by_id(
    settings_id: UUID,
    session: Session = Depends(get_session),
) -> ScrapeSettingsRead:
    row = session.get(ScrapeSettings, settings_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scrape settings not found.")
    return ScrapeSettingsRead.model_validate(row, from_attributes=True)


@router.post("/scrape-settings", response_model=ScrapeSettingsRead, status_code=201)
def create_scrape_settings(
    body: ScrapeSettingsCreate,
    session: Session = Depends(get_session),
) -> ScrapeSettingsRead:
    """Create new settings row and deactivate the previous active row for this campaign."""
    structured = build_scrape_rules_snapshot(
        instruction_text=body.instruction_text,
        structured_rules=body.structured_rules_json,
        default_rules=DEFAULT_STRUCTURED_RULES,
    )
    h = _settings_hash(structured, body.instruction_text)

    # Deactivate existing active rows for this campaign
    existing = session.exec(
        select(ScrapeSettings).where(
            col(ScrapeSettings.campaign_id) == body.campaign_id,
            col(ScrapeSettings.is_active).is_(True),
        )
    ).all()
    for row in existing:
        row.is_active = False
        session.add(row)

    new_row = ScrapeSettings(
        campaign_id=body.campaign_id,
        name=body.name,
        instruction_text=body.instruction_text,
        structured_rules_json=structured,
        settings_hash=h,
        is_active=True,
    )
    session.add(new_row)
    session.commit()
    session.refresh(new_row)
    return ScrapeSettingsRead.model_validate(new_row, from_attributes=True)


@router.put("/scrape-settings/{settings_id}", response_model=ScrapeSettingsRead)
def update_scrape_settings(
    settings_id: UUID,
    body: ScrapeSettingsUpdate,
    session: Session = Depends(get_session),
) -> ScrapeSettingsRead:
    """Create a revised settings row from an existing row, preserving history."""
    existing = session.get(ScrapeSettings, settings_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Scrape settings not found.")

    instruction_text = (
        body.instruction_text
        if body.instruction_text is not None
        else existing.instruction_text
    )
    structured = build_scrape_rules_snapshot(
        instruction_text=instruction_text,
        structured_rules=(
            body.structured_rules_json
            if body.structured_rules_json is not None
            else existing.structured_rules_json
        ),
        default_rules=DEFAULT_STRUCTURED_RULES,
    )
    name = body.name if body.name is not None else existing.name
    make_active = True if body.is_active is None else body.is_active
    h = _settings_hash(structured, instruction_text)

    if make_active:
        active_rows = session.exec(
            select(ScrapeSettings).where(
                col(ScrapeSettings.campaign_id) == existing.campaign_id,
                col(ScrapeSettings.is_active).is_(True),
            )
        ).all()
        for row in active_rows:
            row.is_active = False
            session.add(row)

    new_row = ScrapeSettings(
        campaign_id=existing.campaign_id,
        name=name,
        instruction_text=instruction_text,
        structured_rules_json=structured,
        settings_hash=h,
        is_active=make_active,
    )
    session.add(new_row)
    session.commit()
    session.refresh(new_row)
    return ScrapeSettingsRead.model_validate(new_row, from_attributes=True)


@router.delete("/scrape-settings/{settings_id}", status_code=204)
def delete_scrape_settings(
    settings_id: UUID,
    session: Session = Depends(get_session),
) -> None:
    """Deactivate a settings row without deleting history."""
    row = session.get(ScrapeSettings, settings_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scrape settings not found.")
    row.is_active = False
    session.add(row)
    session.commit()
