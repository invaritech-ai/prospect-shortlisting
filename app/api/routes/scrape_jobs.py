"""ScrapeJob REST endpoints: create, get, pages-content."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.api.schemas.scrape import ScrapeJobCreate, ScrapeJobRead, ScrapePageContentRead
from app.db.session import get_session
from app.jobs._priority import USER_ACTION
from app.jobs.scrape import scrape_website
from app.models import ScrapeJob, ScrapePage
from app.models.scrape import ScrapeRun, ScrapeRunItem
from app.services.scrape_service import (
    CircuitBreakerOpenError,
    ScrapeJobAlreadyRunningError,
    ScrapeJobManager,
)

router = APIRouter(prefix="/v1", tags=["scrape-jobs"])
_manager = ScrapeJobManager()

_DEFAULT_GENERAL_MODEL = "openai/gpt-4.1-nano"
_DEFAULT_CLASSIFY_MODEL = "inception/mercury-2"


@router.post("/scrape-jobs", response_model=ScrapeJobRead, status_code=201)
async def create_scrape_job(
    payload: ScrapeJobCreate,
    session: Session = Depends(get_session),
) -> ScrapeJobRead:
    try:
        job = _manager.create_job(
            session=session,
            website_url=payload.website_url,
            js_fallback=payload.js_fallback,
            include_sitemap=payload.include_sitemap,
            general_model=payload.general_model or _DEFAULT_GENERAL_MODEL,
            classify_model=payload.classify_model or _DEFAULT_CLASSIFY_MODEL,
        )
        session.commit()
    except ScrapeJobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CircuitBreakerOpenError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await scrape_website.configure(priority=USER_ACTION).defer_async(
            job_id=str(job.id),
            scrape_rules=payload.scrape_rules.model_dump() if payload.scrape_rules else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {exc}") from exc
    return ScrapeJobRead.model_validate(job, from_attributes=True)


@router.get("/scrape-jobs", response_model=list[ScrapeJobRead])
def list_scrape_jobs(
    campaign_id: UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ScrapeJobRead]:
    """Recent scrape jobs scoped to a campaign via ScrapeRunItem → ScrapeRun.

    Used by the Operations Log to surface scrape activity alongside analysis runs.
    """
    stmt = (
        select(ScrapeJob)
        .join(ScrapeRunItem, col(ScrapeRunItem.scrape_job_id) == col(ScrapeJob.id))
        .join(ScrapeRun, col(ScrapeRun.id) == col(ScrapeRunItem.run_id))
        .where(col(ScrapeRun.campaign_id) == campaign_id)
        .order_by(col(ScrapeJob.updated_at).desc())
        .limit(limit)
    )
    rows = list(session.exec(stmt).all())
    # Deduplicate (same ScrapeJob can appear under multiple ScrapeRunItems)
    seen: set[UUID] = set()
    unique: list[ScrapeJob] = []
    for job in rows:
        if job.id in seen:
            continue
        seen.add(job.id)
        unique.append(job)
    return [ScrapeJobRead.model_validate(job, from_attributes=True) for job in unique]


@router.get("/scrape-jobs/{job_id}", response_model=ScrapeJobRead)
def get_scrape_job(
    job_id: UUID,
    session: Session = Depends(get_session),
) -> ScrapeJobRead:
    job = session.get(ScrapeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ScrapeJob not found.")
    return ScrapeJobRead.model_validate(job, from_attributes=True)


@router.get("/scrape-jobs/{job_id}/pages-content", response_model=list[ScrapePageContentRead])
def list_scrape_job_pages(
    job_id: UUID,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> list[ScrapePageContentRead]:
    if session.get(ScrapeJob, job_id) is None:
        raise HTTPException(status_code=404, detail="ScrapeJob not found.")
    pages = list(
        session.exec(
            select(ScrapePage)
            .where(col(ScrapePage.job_id) == job_id)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return [ScrapePageContentRead.model_validate(page, from_attributes=True) for page in pages]
