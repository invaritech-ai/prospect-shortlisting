"""Scrape trigger endpoints: enqueue scrapes for selected or all companies."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.api.schemas.upload import CompanyScrapeRequest, CompanyScrapeResult
from app.db.session import get_session
from app.models import Company, ScrapeJob
from app.services.url_utils import domain_from_url, normalize_url
from app.tasks.scrape import scrape_website


router = APIRouter(prefix="/v1", tags=["companies"])

SCRAPE_DEFAULTS = {
    "js_fallback": True,
    "include_sitemap": True,
    "general_model": "openai/gpt-5-nano",
    "classify_model": "inception/mercury-2",
}


def _enqueue_scrapes_for_companies(*, session: Session, companies: list[Company]) -> CompanyScrapeResult:
    failed_company_ids: list[UUID] = []
    valid: list[tuple[Company, str, str]] = []
    for company in companies:
        normalized = normalize_url(company.normalized_url or company.website_url or "")
        if not normalized:
            failed_company_ids.append(company.id)
            continue
        domain = domain_from_url(normalized)
        if not domain:
            failed_company_ids.append(company.id)
            continue
        valid.append((company, normalized, domain))

    if not valid:
        return CompanyScrapeResult(
            requested_count=len(companies),
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=failed_company_ids,
        )

    all_normalized = [v[1] for v in valid]
    active_urls: set[str] = set(
        session.exec(
            select(ScrapeJob.normalized_url)
            .where(
                col(ScrapeJob.normalized_url).in_(all_normalized)
                & col(ScrapeJob.terminal_state).is_(False)
            )
        ).all()
    )

    jobs_to_create: list[ScrapeJob] = []
    company_by_url: dict[str, UUID] = {}
    for company, normalized, domain in valid:
        if normalized in active_urls:
            continue
        jobs_to_create.append(
            ScrapeJob(
                website_url=company.normalized_url,
                normalized_url=normalized,
                domain=domain,
                js_fallback=SCRAPE_DEFAULTS["js_fallback"],
                include_sitemap=SCRAPE_DEFAULTS["include_sitemap"],
                general_model=SCRAPE_DEFAULTS["general_model"],
                classify_model=SCRAPE_DEFAULTS["classify_model"],
            )
        )
        company_by_url[normalized] = company.id

    if not jobs_to_create:
        return CompanyScrapeResult(
            requested_count=len(companies),
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=failed_company_ids,
        )

    session.add_all(jobs_to_create)
    try:
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        for job in jobs_to_create:
            try:
                session.add(job)
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
                company_id = company_by_url.get(job.normalized_url)
                if company_id:
                    failed_company_ids.append(company_id)
        jobs_to_create = [j for j in jobs_to_create if j.id is not None]

    queued_job_ids: list[UUID] = []
    for job in jobs_to_create:
        if job.id is None:
            continue
        scrape_website.delay(str(job.id))
        queued_job_ids.append(job.id)

    return CompanyScrapeResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids,
    )


@router.post("/companies/scrape-selected", response_model=CompanyScrapeResult)
def scrape_selected_companies(
    payload: CompanyScrapeRequest,
    session: Session = Depends(get_session),
) -> CompanyScrapeResult:
    requested_ids = list(dict.fromkeys(payload.company_ids))
    companies = list(session.exec(select(Company).where(col(Company.id).in_(requested_ids))))
    if not companies:
        return CompanyScrapeResult(
            requested_count=0,
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=requested_ids,
        )
    return _enqueue_scrapes_for_companies(session=session, companies=companies)


@router.post("/companies/scrape-all", response_model=CompanyScrapeResult)
def scrape_all_companies(session: Session = Depends(get_session)) -> CompanyScrapeResult:
    companies = list(session.exec(select(Company).order_by(col(Company.created_at).asc())))
    if not companies:
        return CompanyScrapeResult(
            requested_count=0,
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=[],
        )
    return _enqueue_scrapes_for_companies(session=session, companies=companies)
