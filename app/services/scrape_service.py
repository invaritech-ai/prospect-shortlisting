"""ScrapeJob lifecycle: create, claim (CAS), run the full scrape pipeline, write results."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select

from app.core.logging import log_event
from app.models import ScrapeJob, ScrapePage
from app.services.fetch_service import (
    FetchResult,  # re-exported for backwards compat
    fetch_with_fallback,
    resolve_domain,
    should_skip_url,
)
from app.services.link_service import discover_focus_targets
from app.services.markdown_service import MarkdownService
from app.services.url_utils import canonical_internal_url, clean_text, domain_from_url, normalize_url


logger = logging.getLogger(__name__)

# Re-export so existing importers of scrape_service don't break.
from app.services.fetch_service import SKIP_HINTS, USER_AGENT  # noqa: E402, F401

# Lock TTL covers the full single-pass scrape (DNS + fetches + markdown).
# Set above the Celery soft_time_limit (30 min) so the lock outlives the task.
_SCRAPE_LOCK_TTL = timedelta(minutes=35)

# Error codes that indicate a permanent, unrecoverable website failure.
PERMANENT_SCRAPE_ERROR_CODES: frozenset[str] = frozenset({
    "dns_not_resolved",
    "tls_error",
    "bot_protection",   # Imperva / WAF that no tier can bypass — not worth retrying
})

# Page kinds discovered and fetched, in priority order.
_PAGE_KINDS = [
    ("home", 0),
    ("about", 1),
    ("products", 1),
    ("contact", 2),
    ("team", 2),
    ("leadership", 2),
    ("pricing", 2),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScrapeJobAlreadyRunningError(ValueError):
    def __init__(self, *, normalized_url: str, existing_job_id: Any) -> None:
        self.normalized_url = normalized_url
        self.existing_job_id = existing_job_id
        super().__init__(f"Scrape already in progress for {normalized_url}.")


class ScrapeService:
    def __init__(self) -> None:
        self.markdown_service = MarkdownService()

    def create_job(
        self,
        *,
        session: Session,
        website_url: str,
        js_fallback: bool,
        include_sitemap: bool,
        general_model: str,
        classify_model: str,
    ) -> ScrapeJob:
        normalized = normalize_url(website_url)
        if not normalized:
            raise ValueError("Invalid website URL.")
        domain = domain_from_url(normalized)
        if not domain:
            raise ValueError("Could not derive domain from URL.")

        active_job = session.exec(
            select(ScrapeJob)
            .where(
                (col(ScrapeJob.normalized_url) == normalized)
                & (col(ScrapeJob.terminal_state).is_(False))
            )
            .order_by(col(ScrapeJob.created_at).desc())
            .limit(1)
        ).first()
        if active_job:
            raise ScrapeJobAlreadyRunningError(
                normalized_url=normalized,
                existing_job_id=active_job.id,
            )

        job = ScrapeJob(
            website_url=website_url,
            normalized_url=normalized,
            domain=domain,
            js_fallback=js_fallback,
            include_sitemap=include_sitemap,
            general_model=general_model,
            classify_model=classify_model,
        )
        session.add(job)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            conflicting = session.exec(
                select(ScrapeJob)
                .where(
                    (col(ScrapeJob.normalized_url) == normalized)
                    & (col(ScrapeJob.terminal_state).is_(False))
                )
                .order_by(col(ScrapeJob.created_at).desc())
                .limit(1)
            ).first()
            raise ScrapeJobAlreadyRunningError(
                normalized_url=normalized,
                existing_job_id=conflicting.id if conflicting else None,
            ) from None
        session.refresh(job)
        return job

    async def run_scrape(self, *, engine: Engine, job_id: Any) -> None:
        """Single-pass scrape: DNS check → discover pages → fetch → markdown → write.

        Uses a CAS lock so that if Celery re-delivers the task (e.g. after a
        soft_time_limit restart) the second worker detects it lost the race and
        exits without writing duplicate data.
        """
        now = utcnow()
        lock_token = str(uuid4())

        # ── Phase 1: CAS-claim ──────────────────────────────────────────────
        with Session(engine) as session:
            session.execute(
                sa_update(ScrapeJob)
                .where(
                    col(ScrapeJob.id) == job_id,
                    col(ScrapeJob.terminal_state).is_(False),
                    col(ScrapeJob.status).in_(["created", "running"]),
                    or_(
                        col(ScrapeJob.lock_token).is_(None),
                        col(ScrapeJob.lock_expires_at) < now,
                    ),
                )
                .values(
                    status="running",
                    started_at=now,
                    lock_token=lock_token,
                    lock_expires_at=now + _SCRAPE_LOCK_TTL,
                    updated_at=now,
                )
            )
            session.commit()
            job = session.get(ScrapeJob, job_id)
            if not job or job.lock_token != lock_token:
                log_event(logger, "scrape_skipped_not_owner", job_id=str(job_id))
                return
            domain = job.domain
            normalized_url = job.normalized_url
            js_fallback = job.js_fallback
            include_sitemap = job.include_sitemap
            classify_model = job.classify_model
            general_model = job.general_model

        # ── Phase 2: DNS check ──────────────────────────────────────────────
        if not await resolve_domain(domain):
            with Session(engine) as session:
                job = session.get(ScrapeJob, job_id)
                if job and job.lock_token == lock_token:
                    job.status = "site_unavailable"
                    job.terminal_state = True
                    job.last_error_code = "dns_not_resolved"
                    job.last_error_message = f"{domain} :: dns_not_resolved"
                    job.fetch_failures_count = 1
                    job.finished_at = utcnow()
                    job.updated_at = utcnow()
                    session.add(job)
                    session.commit()
            return

        # ── Phase 3: clear stale pages ──────────────────────────────────────
        with Session(engine) as session:
            session.exec(delete(ScrapePage).where(col(ScrapePage.job_id) == job_id))
            session.commit()

        # ── Phase 4: discover target URLs (sitemap + LLM) ───────────────────
        targets = await discover_focus_targets(
            start_url=normalized_url,
            domain=domain,
            include_sitemap=include_sitemap,
            use_js_fallback=js_fallback,
            classify_model=classify_model,
        )

        seen_urls: set[str] = set()
        fetched_pages: list[dict] = []
        failure_count = 0

        # ── Phase 5: fetch each target page ─────────────────────────────────
        for kind, depth in _PAGE_KINDS:
            target_url = targets.get(kind, "")
            canonical = canonical_internal_url(target_url, domain) if target_url else ""
            if not canonical or canonical in seen_urls:
                continue
            seen_urls.add(canonical)

            fetch = await fetch_with_fallback(canonical, use_js=js_fallback)
            if fetch.selector is None:
                failure_count += 1
                fetched_pages.append({
                    "success": False,
                    "url": canonical,
                    "canonical_url": canonical,
                    "depth": depth,
                    "page_kind": kind,
                    "fetch_mode": fetch.fetch_mode,
                    "status_code": fetch.status_code,
                    "fetch_error_code": fetch.error_code or "fetch_failed",
                    "fetch_error_message": fetch.error_message,
                })
                continue

            selector = fetch.selector
            page_url = str(selector.url or canonical)

            if should_skip_url(page_url):
                log_event(logger, "scrape_skipped_login_redirect", kind=kind, url=canonical, final_url=page_url)
                continue

            final_canonical = canonical_internal_url(page_url, domain) or page_url
            if final_canonical != canonical and final_canonical in seen_urls:
                log_event(logger, "scrape_skipped_redirect_duplicate", kind=kind, url=canonical, final_url=final_canonical)
                continue
            seen_urls.add(final_canonical)

            title = clean_text(str(selector.css("title::text").get(default="")))[:300]
            description = clean_text(str(selector.css("meta[name='description']::attr(content)").get(default="")))[:800]
            text = clean_text(str(selector.get_all_text(separator=" ")))
            fetched_pages.append({
                "success": True,
                "url": page_url,
                "canonical_url": canonical_internal_url(page_url, domain) or canonical,
                "depth": depth,
                "page_kind": kind,
                "fetch_mode": fetch.fetch_mode,
                "status_code": fetch.status_code,
                "title": title,
                "description": description,
                "text_len": len(text),
                "raw_text": text[:40000],
            })

        pages_fetched_count = sum(1 for p in fetched_pages if p["success"])

        if pages_fetched_count == 0:
            with Session(engine) as session:
                job = session.get(ScrapeJob, job_id)
                if job and job.lock_token == lock_token:
                    # Persist page-level errors so we can diagnose why fetches failed.
                    for snap in fetched_pages:
                        if not snap["success"]:
                            session.add(ScrapePage(
                                job_id=job_id,
                                url=snap["url"],
                                canonical_url=snap["canonical_url"],
                                depth=snap["depth"],
                                page_kind=snap["page_kind"],
                                fetch_mode=snap["fetch_mode"],
                                status_code=snap["status_code"],
                                fetch_error_code=snap["fetch_error_code"],
                                fetch_error_message=snap.get("fetch_error_message", "")[:500],
                            ))

                    failure_codes = [
                        p.get("fetch_error_code", "")
                        for p in fetched_pages
                        if not p["success"]
                    ]
                    all_permanent = bool(failure_codes) and all(
                        c in PERMANENT_SCRAPE_ERROR_CODES for c in failure_codes
                    )
                    if all_permanent:
                        dominant = max(set(failure_codes), key=failure_codes.count)
                        job.status = "site_unavailable"
                        job.last_error_code = dominant
                        job.last_error_message = f"All fetches failed with permanent error: {dominant}"
                    else:
                        job.status = "failed"
                        job.last_error_code = "no_pages_fetched"
                        job.last_error_message = "No pages could be fetched."
                    job.terminal_state = True
                    job.fetch_failures_count = failure_count
                    job.discovered_urls_count = len(seen_urls)
                    job.finished_at = utcnow()
                    job.updated_at = utcnow()
                    session.add(job)
                    session.commit()
            return

        # ── Phase 6: markdown conversion (rule-based + LLM fallback) ────────
        page_updates: list[dict] = []
        markdown_pages = 0
        llm_used = 0
        llm_failed = 0

        for snap in fetched_pages:
            if not snap["success"] or snap["status_code"] >= 400 or snap.get("text_len", 0) < 80:
                page_updates.append({"snap": snap, "markdown_content": ""})
                continue

            markdown, used_llm, llm_error = self.markdown_service.to_markdown(
                url=snap["url"],
                title=snap.get("title", ""),
                page_text=snap.get("raw_text", ""),
                model=general_model,
            )
            page_updates.append({"snap": snap, "markdown_content": markdown[:50000]})
            markdown_pages += 1
            if used_llm:
                llm_used += 1
            if llm_error:
                llm_failed += 1

        # ── Phase 7: write all results ───────────────────────────────────────
        with Session(engine) as session:
            now_finish = utcnow()
            job = session.get(ScrapeJob, job_id)
            if not job or job.lock_token != lock_token:
                log_event(logger, "scrape_results_skipped_not_owner", job_id=str(job_id))
                return

            for pu in page_updates:
                snap = pu["snap"]
                if snap["success"]:
                    session.add(ScrapePage(
                        job_id=job_id,
                        url=snap["url"],
                        canonical_url=snap["canonical_url"],
                        depth=snap["depth"],
                        page_kind=snap["page_kind"],
                        fetch_mode=snap["fetch_mode"],
                        status_code=snap["status_code"],
                        title=snap.get("title", ""),
                        description=snap.get("description", ""),
                        text_len=snap.get("text_len", 0),
                        raw_text=snap.get("raw_text", ""),
                        fetch_error_code="",
                        fetch_error_message="",
                        markdown_content=pu["markdown_content"],
                    ))
                else:
                    session.add(ScrapePage(
                        job_id=job_id,
                        url=snap["url"],
                        canonical_url=snap["canonical_url"],
                        depth=snap["depth"],
                        page_kind=snap["page_kind"],
                        fetch_mode=snap["fetch_mode"],
                        status_code=snap["status_code"],
                        fetch_error_code=snap["fetch_error_code"],
                        fetch_error_message=snap["fetch_error_message"],
                    ))

            job.discovered_urls_count = len(seen_urls)
            job.pages_fetched_count = pages_fetched_count
            job.fetch_failures_count = failure_count
            job.markdown_pages_count = markdown_pages
            job.llm_used_count = llm_used
            job.llm_failed_count = llm_failed
            job.terminal_state = True
            job.finished_at = now_finish
            job.updated_at = now_finish
            job.lock_token = None
            job.lock_expires_at = None

            if markdown_pages == 0:
                job.status = "failed"
                job.last_error_code = "no_markdown_produced"
                job.last_error_message = "Scrape completed but produced no markdown pages."
            else:
                job.status = "completed"
                job.last_error_code = None
                job.last_error_message = None

            session.add(job)
            session.commit()

            log_event(
                logger,
                "scrape_completed",
                job_id=str(job_id),
                domain=domain,
                pages_fetched=pages_fetched_count,
                failures=failure_count,
                markdown_pages=markdown_pages,
                llm_used=llm_used,
            )
