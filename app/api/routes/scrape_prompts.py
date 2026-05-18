"""Scrape settings — append-only per-campaign config for S1 scraping."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, select

from app.api.schemas.scrape import (
    DEFAULT_STRUCTURED_RULES,
    ScrapeSettingsCreate,
    ScrapeSettingsRead,
)
from app.db.session import get_session
from app.models.scrape import ScrapeSettings

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

    return ScrapeSettingsRead.model_validate(row)


@router.post("/scrape-settings", response_model=ScrapeSettingsRead, status_code=201)
def create_scrape_settings(
    body: ScrapeSettingsCreate,
    session: Session = Depends(get_session),
) -> ScrapeSettingsRead:
    """Create new settings row and deactivate the previous active row for this campaign."""
    structured = body.structured_rules_json or DEFAULT_STRUCTURED_RULES
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
    return ScrapeSettingsRead.model_validate(new_row)
