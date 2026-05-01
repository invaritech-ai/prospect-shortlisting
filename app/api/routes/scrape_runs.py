from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.schemas.scrape import ScrapeRunRead
from app.db.session import get_session
from app.models.scrape import ScrapeRun

router = APIRouter(prefix="/v1", tags=["scrape-runs"])


@router.get("/scrape-runs/{run_id}", response_model=ScrapeRunRead)
def get_scrape_run(run_id: UUID, session: Session = Depends(get_session)) -> ScrapeRunRead:
    run = session.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scrape run not found.")
    return ScrapeRunRead.model_validate(run, from_attributes=True)
