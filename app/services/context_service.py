"""Context assembly: fetch scrape data and build LLM prompt context for analysis jobs."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import (
    Company,
    CrawlArtifact,
    CrawlJob,
    ScrapeJob,
    ScrapePage,
)
from app.models.pipeline import CrawlJobState


# Controls context assembly order for the classification prompt.
# Pages are sorted by this order; any page kind not listed is appended after.
ANALYSIS_PAGE_ORDER = ("home", "about", "products", "contact", "team", "leadership", "services")

MAX_CHARS_PER_PAGE = 12000
MAX_TOTAL_CONTEXT_CHARS = 30000


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bulk_latest_completed_scrape_jobs(
    *, session: Session, normalized_urls: list[str]
) -> dict[str, ScrapeJob]:
    """Return a map of normalized_url → latest completed ScrapeJob for all given URLs."""
    if not normalized_urls:
        return {}
    rows = list(
        session.exec(
            select(ScrapeJob)
            .where(
                col(ScrapeJob.normalized_url).in_(normalized_urls)
                & (col(ScrapeJob.status) == "completed")
            )
            .order_by(col(ScrapeJob.created_at).desc())
        )
    )
    result: dict[str, ScrapeJob] = {}
    for job in rows:
        if job.normalized_url not in result:
            result[job.normalized_url] = job
    return result


def latest_completed_scrape_job(*, session: Session, normalized_url: str) -> ScrapeJob | None:
    return session.exec(
        select(ScrapeJob)
        .where(
            (col(ScrapeJob.normalized_url) == normalized_url)
            & (col(ScrapeJob.status) == "completed")
        )
        .order_by(col(ScrapeJob.created_at).desc())
    ).first()


def analysis_pages_for_job(*, session: Session, job_id: UUID) -> list[ScrapePage]:
    pages = list(
        session.exec(
            select(ScrapePage)
            .where(col(ScrapePage.job_id) == job_id)
            .order_by(col(ScrapePage.depth).asc(), col(ScrapePage.id).asc())
        )
    )
    by_kind: dict[str, list[ScrapePage]] = {}
    for page in pages:
        by_kind.setdefault(page.page_kind, []).append(page)
    ordered: list[ScrapePage] = []
    for page_kind in ANALYSIS_PAGE_ORDER:
        ordered.extend(by_kind.pop(page_kind, []))
    for remaining in by_kind.values():
        ordered.extend(remaining)
    return ordered


def build_context(pages: list[ScrapePage]) -> str:
    parts: list[str] = []
    total_chars = 0
    for page in pages:
        markdown = (page.markdown_content or "").strip()
        if not markdown:
            continue
        chunk = markdown[:MAX_CHARS_PER_PAGE]
        block = f"## {page.page_kind.upper()} PAGE\nURL: {page.url}\n\n{chunk}"
        projected = total_chars + len(block)
        if projected > MAX_TOTAL_CONTEXT_CHARS and parts:
            break
        parts.append(block)
        total_chars += len(block)
    return "\n\n".join(parts).strip()


def render_prompt(*, prompt_text: str, domain: str, context: str) -> str:
    rendered = prompt_text.replace("{domain}", domain)
    rendered = rendered.replace("{org}", domain)
    rendered = rendered.replace("{context}", context)
    return rendered


def bulk_ensure_crawl_adapters(
    *,
    session: Session,
    companies: list[Company],
    scrape_map: dict[str, ScrapeJob],
) -> dict[UUID, CrawlArtifact]:
    """Upsert CrawlJob + CrawlArtifact for all companies in bulk.

    Returns a map of company_id → CrawlArtifact.
    """
    if not companies:
        return {}

    company_ids = [c.id for c in companies]
    now = utcnow()

    # 1. Bulk-fetch existing CrawlJobs.
    existing_crawl_jobs: dict[UUID, CrawlJob] = {
        cj.company_id: cj
        for cj in session.exec(
            select(CrawlJob).where(col(CrawlJob.company_id).in_(company_ids))
        ).all()
    }

    # 2. Bulk-fetch all ScrapePages for all relevant scrape job IDs.
    scrape_job_ids = list({
        scrape_map[c.normalized_url].id
        for c in companies
        if c.normalized_url and c.normalized_url in scrape_map
    })
    pages_by_job: dict[UUID, dict[str, ScrapePage]] = {}
    if scrape_job_ids:
        for page in session.exec(
            select(ScrapePage).where(col(ScrapePage.job_id).in_(scrape_job_ids))
        ).all():
            pages_by_job.setdefault(page.job_id, {})[page.page_kind] = page

    # 3. Build CrawlJob objects (create or update).
    crawl_jobs_to_save: list[CrawlJob] = []
    crawl_job_by_company: dict[UUID, CrawlJob] = {}
    for company in companies:
        scrape_job = scrape_map.get(company.normalized_url)
        if not scrape_job:
            continue
        actual_state = (
            CrawlJobState.SUCCEEDED
            if scrape_job.status == "completed" and (scrape_job.pages_fetched_count or 0) > 0
            else CrawlJobState.FAILED
        )
        cj = existing_crawl_jobs.get(company.id)
        if cj is None:
            cj = CrawlJob(
                upload_id=company.upload_id,
                company_id=company.id,
                state=actual_state,
                attempt_count=1,
                started_at=scrape_job.started_at or scrape_job.created_at,
                finished_at=scrape_job.finished_at or scrape_job.updated_at,
            )
        else:
            cj.state = actual_state
            cj.finished_at = scrape_job.finished_at or scrape_job.updated_at
            cj.updated_at = now
        crawl_jobs_to_save.append(cj)
        crawl_job_by_company[company.id] = cj

    session.add_all(crawl_jobs_to_save)
    session.flush()

    # 4. Bulk-fetch existing CrawlArtifacts.
    crawl_job_ids = [cj.id for cj in crawl_jobs_to_save if cj.id]
    existing_artifacts: dict[UUID, CrawlArtifact] = {}
    if crawl_job_ids:
        existing_artifacts = {
            ca.crawl_job_id: ca
            for ca in session.exec(
                select(CrawlArtifact).where(col(CrawlArtifact.crawl_job_id).in_(crawl_job_ids))
            ).all()
        }

    # 5. Build CrawlArtifact objects (create or update).
    artifacts_to_save: list[CrawlArtifact] = []
    artifact_by_company: dict[UUID, CrawlArtifact] = {}
    for company in companies:
        cj = crawl_job_by_company.get(company.id)
        if not cj or not cj.id:
            continue
        scrape_job = scrape_map.get(company.normalized_url)
        pages_by_kind = pages_by_job.get(scrape_job.id, {}) if scrape_job else {}

        artifact = existing_artifacts.get(cj.id)
        if artifact is None:
            artifact = CrawlArtifact(company_id=company.id, crawl_job_id=cj.id)
        home = pages_by_kind.get("home")
        about = pages_by_kind.get("about")
        products = pages_by_kind.get("products")
        artifact.home_url = home.url if home else None
        artifact.about_url = about.url if about else None
        artifact.product_url = products.url if products else None
        artifact.home_status = home.status_code if home else None
        artifact.about_status = about.status_code if about else None
        artifact.product_status = products.status_code if products else None
        artifacts_to_save.append(artifact)
        artifact_by_company[company.id] = artifact

    session.add_all(artifacts_to_save)
    session.flush()
    return artifact_by_company
