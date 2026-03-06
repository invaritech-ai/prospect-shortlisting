from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from app.api.schemas.scrape import (
    JobActionResult,
    ScrapeJobCreate,
    ScrapeJobRead,
    ScrapePageContentRead,
    ScrapePageRead,
)
from app.db.session import get_session
from app.models import ScrapeJob, ScrapePage
from app.services.scrape_service import ScrapeService


router = APIRouter(prefix="/v1", tags=["scrape-jobs"])
scrape_service = ScrapeService()


def _as_job_read(job: ScrapeJob) -> ScrapeJobRead:
    return ScrapeJobRead.model_validate(job, from_attributes=True)


def _extract_screenshot_path(ocr_text: str) -> str:
    prefix = "[SCREENSHOT_PATH] "
    for line in (ocr_text or "").splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


@router.post("/scrape-jobs", response_model=ScrapeJobRead, status_code=status.HTTP_201_CREATED)
def create_scrape_job(payload: ScrapeJobCreate, session: Session = Depends(get_session)) -> ScrapeJobRead:
    try:
        job = scrape_service.create_job(
            session=session,
            website_url=payload.website_url,
            max_pages=payload.max_pages,
            max_depth=payload.max_depth,
            js_fallback=payload.js_fallback,
            include_sitemap=payload.include_sitemap,
            general_model=payload.general_model,
            classify_model=payload.classify_model,
            ocr_model=payload.ocr_model,
            enable_ocr=payload.enable_ocr,
            max_images_per_page=payload.max_images_per_page,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _as_job_read(job)


@router.get("/scrape-jobs", response_model=list[ScrapeJobRead])
def list_scrape_jobs(
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ScrapeJobRead]:
    jobs = list(
        session.exec(
            select(ScrapeJob).order_by(col(ScrapeJob.created_at).desc()).offset(offset).limit(limit)
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

    results: list[ScrapePageContentRead] = []
    for page in pages:
        if page.id is None:
            continue
        screenshot_path = _extract_screenshot_path(page.ocr_text)
        screenshot_exists = bool(screenshot_path) and Path(screenshot_path).exists()
        results.append(
            ScrapePageContentRead(
                id=page.id,
                job_id=page.job_id,
                url=page.url,
                page_kind=page.page_kind,
                status_code=page.status_code,
                screenshot_path=screenshot_path,
                screenshot_exists=screenshot_exists,
                markdown_content=page.markdown_content,
                ocr_text=page.ocr_text,
                fetch_error_code=page.fetch_error_code,
                fetch_error_message=page.fetch_error_message,
                updated_at=page.updated_at,
            )
        )
    return results


@router.post("/scrape-jobs/{job_id}/run-step1", response_model=JobActionResult)
def run_step1(job_id: UUID, session: Session = Depends(get_session)) -> JobActionResult:
    job = session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    job = asyncio.run(scrape_service.run_step1(session=session, job=job))
    return JobActionResult(job=_as_job_read(job), message="Step 1 completed.")


@router.post("/scrape-jobs/{job_id}/run-step2", response_model=JobActionResult)
def run_step2(job_id: UUID, session: Session = Depends(get_session)) -> JobActionResult:
    job = session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.stage1_status != "completed":
        raise HTTPException(status_code=409, detail="Step 1 must complete before Step 2.")
    job = scrape_service.run_step2(session=session, job=job)
    return JobActionResult(job=_as_job_read(job), message="Step 2 completed.")


@router.post("/scrape-jobs/{job_id}/run-all", response_model=JobActionResult)
def run_all(job_id: UUID, session: Session = Depends(get_session)) -> JobActionResult:
    job = session.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    job = asyncio.run(scrape_service.run_step1(session=session, job=job))
    if job.stage1_status != "completed":
        return JobActionResult(job=_as_job_read(job), message="Step 1 failed. Step 2 skipped.")
    job = scrape_service.run_step2(session=session, job=job)
    return JobActionResult(job=_as_job_read(job), message="Step 1 + Step 2 completed.")
