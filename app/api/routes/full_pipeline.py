from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.schemas.full_pipeline import FullPipelineCompanyList
from app.db.session import get_session
from app.services.full_pipeline_service import FullPipelineService

router = APIRouter(prefix="/v1/full-pipeline", tags=["full-pipeline"])


def _service() -> FullPipelineService:
    return FullPipelineService()


@router.get("/companies", response_model=FullPipelineCompanyList)
def list_full_pipeline_companies(
    campaign_id: UUID = Query(...),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> FullPipelineCompanyList:
    if not isinstance(search, str):
        search = None
    if not isinstance(limit, int):
        limit = 50
    if not isinstance(offset, int):
        offset = 0
    return _service().list_companies(
        session=session,
        campaign_id=campaign_id,
        search=search,
        limit=limit,
        offset=offset,
    )
