from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from app.api.schemas.scrape import (
    JobEnqueueResult,
    ScrapeJobCreate,
    ScrapeJobRead,
    ScrapePageContentRead,
    ScrapePageRead,
)
from app.db.session import get_session
from app.models import ScrapeJob, ScrapePage
from app.services.scrape_service import CircuitBreakerOpenError, ScrapeJobAlreadyRunningError, ScrapeService
from app.core.config import settings
from app.tasks.scrape import scrape_website


router = APIRouter(prefix="/v1", tags=["scrape-jobs"])
scrape_service = ScrapeService()


def _as_job_read(job: ScrapeJob) -> ScrapeJobRead:
    return ScrapeJobRead.model_validate(job, from_attributes=True)


@router.post("/scrape-jobs", response_model=ScrapeJobRead, status_code=status.HTTP_201_CREATED)
def create_scrape_job(payload: ScrapeJobCreate, session: Session = Depends(get_session)) -> ScrapeJobRead:
    try:
        job = scrape_service.create_job(
            session=session,
            website_url=payload.website_url,
            js_fallback=payload.js_fallback,
            include_sitemap=payload.include_sitemap,
            general_model=payload.general_model or settings.general_model,
            classify_model=payload.classify_model or settings.classify_model,
        )
    except ScrapeJobAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "existing_job_id": str(exc.existing_job_id)},
        ) from exc
    except CircuitBreakerOpenError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "error": "circuit_breaker_open", "domain": exc.domain},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Commit before enqueuing so the worker can find the row.
    session.commit()
    try:
        scrape_website.delay(str(job.id))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {exc}") from exc
    return _as_job_read(job)


@router.get("/scrape-jobs", response_model=list[ScrapeJobRead])
def list_scrape_jobs(
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: Literal["all", "active", "completed", "failed"] = Query(default="all"),
    search: str | None = Query(default=None, max_length=200),
) -> list[ScrapeJobRead]:
    statement = select(ScrapeJob)
    if status_filter == "active":
        statement = statement.where(col(ScrapeJob.terminal_state).is_(False))
    elif status_filter == "completed":
        statement = statement.where(col(ScrapeJob.status) == "completed")
    elif status_filter == "failed":
        statement = statement.where(col(ScrapeJob.status) == "failed")
    if search:
        statement = statement.where(col(ScrapeJob.domain).ilike(f"%{search.strip()}%"))

    jobs = list(
        session.exec(
            statement.order_by(col(ScrapeJob.created_at).desc()).offset(offset).limit(limit)
        )
    )
    return [_as_job_read(job) for job in jobs]


@router.get("/scrape-jobs/{job_id}", response_model=ScrapeJobRead)
def get_scrape_job(job_id: UUID, session: Session = Depends(get_session)) -> ScrapeJobRead:
    job = session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _as_job_read(job)


@router.get("/scrape-jobs/{job_id}/pages", response_model=list[ScrapePageRead])
def list_job_pages(
    job_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> list[ScrapePageRead]:
    job = session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    pages = list(
        session.exec(
            select(ScrapePage)
            .where(col(ScrapePage.job_id) == job_id)
            .order_by(col(ScrapePage.depth).asc(), col(ScrapePage.id).asc())
            .offset(offset)
            .limit(limit)
        )
    )
    return [ScrapePageRead.model_validate(page, from_attributes=True) for page in pages if page.id is not None]


@router.get("/scrape-jobs/{job_id}/pages-content", response_model=list[ScrapePageContentRead])
def list_job_page_contents(
    job_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> list[ScrapePageContentRead]:
    job = session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    pages = list(
        session.exec(
            select(ScrapePage)
            .where(col(ScrapePage.job_id) == job_id)
            .order_by(col(ScrapePage.depth).asc(), col(ScrapePage.id).asc())
            .offset(offset)
            .limit(limit)
        )
    )

    return [
        ScrapePageContentRead(
            id=page.id,
            job_id=page.job_id,
            url=page.url,
            page_kind=page.page_kind,
            status_code=page.status_code,
            markdown_content=page.markdown_content,
            fetch_error_code=page.fetch_error_code,
            fetch_error_message=page.fetch_error_message,
            updated_at=page.updated_at,
        )
        for page in pages
        if page.id is not None
    ]


@router.post("/scrape-jobs/{job_id}/enqueue", response_model=JobEnqueueResult)
def enqueue_scrape_job(job_id: UUID, session: Session = Depends(get_session)) -> JobEnqueueResult:
    """Re-enqueue an existing scrape job (retry a failed/terminal job)."""
    job = session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.terminal_state:
        raise HTTPException(status_code=409, detail="Job is still active. Cannot retry a non-terminal job.")

    # Reset job state for retry.
    job.status = "created"
    job.terminal_state = False
    job.lock_token = None
    job.lock_expires_at = None
    job.last_error_code = None
    job.last_error_message = None
    job.reconcile_count = 0
    job.started_at = None
    job.finished_at = None
    session.add(job)
    session.commit()

    try:
        result = scrape_website.delay(str(job_id))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {exc}") from exc
    return JobEnqueueResult(
        job_id=job_id,
        celery_task_id=result.id,
        message="Scrape job re-enqueued for retry.",
    )
