"""ScrapeJob lifecycle: create, claim (CAS), run the full scrape pipeline, write results."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select

from app.core.logging import log_event
from app.models import AnalysisJob, ClassificationResult, Company, ScrapeJob, ScrapePage
from app.services.domain_policy import get_default_manager
from app.services.fetch_service import (
    FetchErrorCode,
    FetchResult,  # re-exported for backwards compat
    is_parked_domain,
    needs_stealth_after_static_and_impersonate,
    resolve_domain,
    scrape_page_fetch,
    should_skip_url,
    stealth_fetch_many,
)
from app.services.link_service import apply_page_selection_rules, discover_focus_targets
from app.services.markdown_service import MarkdownService
from app.services.pipeline_service import recompute_company_stages
from app.services.url_utils import canonical_internal_url, clean_text, domain_from_url, normalize_url, rewrite_to_working_origin


logger = logging.getLogger(__name__)

# Re-export so existing importers of scrape_service don't break.
from app.services.fetch_service import SKIP_HINTS  # noqa: E402, F401

# Lock TTL covers the full single-pass scrape (DNS + fetches + markdown).
# Set above the Celery soft_time_limit (30 min) so the lock outlives the task.
_SCRAPE_LOCK_TTL = timedelta(minutes=35)

# Error codes that indicate a permanent, unrecoverable website failure.
PERMANENT_SCRAPE_ERROR_CODES: frozenset[str] = frozenset({
    "dns_not_resolved",
    "tls_error",
    "bot_protection",       # Imperva / WAF that no tier can bypass — not worth retrying
    "not_found",            # HTTP 404 across all tiers
    "access_denied",        # HTTP 403 across all tiers
    "parked_domain",        # Domain is parked / for sale
})

# Page kinds discovered and fetched, in priority order.
_PAGE_KINDS = [
    ("home", 0),
    ("about", 1),
    ("products", 1),
    ("services", 1),
    ("pricing", 2),
    ("contact", 2),
    ("team", 2),
    ("leadership", 2),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Number of consecutive permanent failures before the circuit breaker opens.
_CIRCUIT_BREAKER_THRESHOLD = 3


_ORIGIN_RETRY_ERROR_CODES = frozenset({
    FetchErrorCode.TLS_ERROR,
    FetchErrorCode.ACCESS_DENIED,
    FetchErrorCode.FETCH_FAILED,
    FetchErrorCode.TIMEOUT,
})


def retry_url_for_working_origin(
    *,
    canonical: str,
    working_origin_url: str,
    domain: str,
    error_code: str,
) -> str:
    if not working_origin_url or error_code not in _ORIGIN_RETRY_ERROR_CODES:
        return ""
    rewritten = rewrite_to_working_origin(canonical, working_origin_url, domain)
    if not rewritten or rewritten == canonical:
        return ""
    return rewritten


def classify_scrape_outcome(fetched_pages: list[dict]) -> tuple[str, str]:
    successful = [
        p for p in fetched_pages
        if p.get("success") and int(p.get("text_len") or 0) >= 80
    ]
    failures = [p for p in fetched_pages if not p.get("success")]
    has_home = any(p.get("page_kind") == "home" for p in successful)

    if successful and not failures and has_home:
        return ("full_success", "")
    if has_home and len(successful) >= 2:
        return ("partial_success", "")
    if len(successful) >= 2:
        return ("partial_success", "")

    failure_codes = [
        str(p.get("fetch_error_code") or "")
        for p in failures
        if str(p.get("fetch_error_code") or "")
    ]
    if failure_codes:
        dominant = max(set(failure_codes), key=failure_codes.count)
        return ("failed_gracefully", dominant)
    return ("failed_gracefully", "no_pages_fetched")


class ScrapeJobAlreadyRunningError(ValueError):
    def __init__(self, *, normalized_url: str, existing_job_id: Any) -> None:
        self.normalized_url = normalized_url
        self.existing_job_id = existing_job_id
        super().__init__(f"Scrape already in progress for {normalized_url}.")


class CircuitBreakerOpenError(ValueError):
    def __init__(self, *, domain: str) -> None:
        self.domain = domain
        super().__init__(
            f"Circuit breaker open for {domain}: last {_CIRCUIT_BREAKER_THRESHOLD} "
            "scrape attempts all ended in permanent failure."
        )


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

        # Circuit breaker: if the last N terminal jobs all have permanent error
        # codes, refuse to create a new job to avoid wasting queue capacity.
        recent_terminal = list(session.exec(
            select(ScrapeJob)
            .where(
                col(ScrapeJob.domain) == domain,
                col(ScrapeJob.terminal_state).is_(True),
            )
            .order_by(col(ScrapeJob.created_at).desc())
            .limit(_CIRCUIT_BREAKER_THRESHOLD)
        ).all())
        if (
            len(recent_terminal) >= _CIRCUIT_BREAKER_THRESHOLD
            and all(j.last_error_code in PERMANENT_SCRAPE_ERROR_CODES for j in recent_terminal)
        ):
            raise CircuitBreakerOpenError(domain=domain)

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

    async def run_scrape(
        self,
        *,
        engine: Engine,
        job_id: Any,
        scrape_rules: dict | None = None,
    ) -> None:
        """Single-pass scrape: DNS check → discover pages → fetch → markdown → write.

        Uses a CAS lock so that if Celery re-delivers the task (e.g. after a
        soft_time_limit restart) the second worker detects it lost the race and
        exits without writing duplicate data.
        """
        now = utcnow()
        lock_token = str(uuid4())
        log_event(logger, "scrape_task_start", job_id=str(job_id))

        # ── Phase 1: CAS-claim ──────────────────────────────────────────────
        with Session(engine) as session:
            session.execute(
                sa_update(ScrapeJob)
                .where(
                    col(ScrapeJob.id) == job_id,
                    col(ScrapeJob.terminal_state).is_(False),
                    col(ScrapeJob.state).in_(["created", "running"]),
                    or_(
                        col(ScrapeJob.lock_token).is_(None),
                        col(ScrapeJob.lock_expires_at) < now,
                    ),
                )
                .values(
                    state="running",
                    started_at=now,
                    lock_token=lock_token,
                    lock_expires_at=now + _SCRAPE_LOCK_TTL,
                    updated_at=now,
                )
            )
            session.commit()
            job = session.get(ScrapeJob, job_id)
            if not job:
                log_event(logger, "scrape_skipped_job_not_found", job_id=str(job_id))
                return
            if job.lock_token != lock_token:
                log_event(
                    logger, "scrape_skipped_not_owner", job_id=str(job_id),
                    job_status=job.state, terminal=job.terminal_state,
                    lock_held_by="none" if job.lock_token is None else "other",
                    lock_expires_at=str(job.lock_expires_at),
                )
                return
            domain = job.domain
            normalized_url = job.normalized_url
            js_fallback = job.js_fallback
            include_sitemap = job.include_sitemap
            classify_model = job.classify_model
            log_event(logger, "scrape_lock_acquired", job_id=str(job_id),
                      domain=domain, js_fallback=js_fallback, include_sitemap=include_sitemap)

        # ── Phase 2: DNS check ──────────────────────────────────────────────
        log_event(logger, "scrape_dns_check", job_id=str(job_id), domain=domain)
        if not await resolve_domain(domain):
            log_event(logger, "scrape_dns_failed", job_id=str(job_id), domain=domain)
            with Session(engine) as session:
                job = session.get(ScrapeJob, job_id)
                if job and job.lock_token == lock_token:
                    job.state = "failed"
                    job.failure_reason = "site_unavailable"
                    job.terminal_state = True
                    job.last_error_code = "dns_not_resolved"
                    job.last_error_message = f"{domain} :: dns_not_resolved"
                    job.fetch_failures_count = 1
                    job.finished_at = utcnow()
                    job.updated_at = utcnow()
                    session.add(job)
                    recompute_company_stages(session, normalized_urls=[normalized_url])
                    session.commit()
            return

        # ── Phase 3: clear stale pages ──────────────────────────────────────
        with Session(engine) as session:
            session.exec(delete(ScrapePage).where(col(ScrapePage.job_id) == job_id))
            session.commit()

        # ── Phase 4: discover target URLs (sitemap + LLM) ───────────────────
        log_event(logger, "scrape_discover_start", job_id=str(job_id), domain=domain)
        classifier_prompt_text = (
            str(scrape_rules.get("classifier_prompt_text", "")).strip()
            if scrape_rules and scrape_rules.get("classifier_prompt_text") is not None
            else ""
        )
        requested_page_kinds = (
            [str(k).strip().lower() for k in (scrape_rules.get("page_kinds") or []) if str(k).strip()]
            if scrape_rules
            else []
        )
        targets = await discover_focus_targets(
            start_url=normalized_url,
            domain=domain,
            include_sitemap=include_sitemap,
            use_js_fallback=js_fallback,
            classify_model=classify_model,
            classifier_prompt_text=classifier_prompt_text or None,
            requested_page_kinds=requested_page_kinds or None,
        )
        selected_targets = apply_page_selection_rules(targets=targets, rules=scrape_rules)
        log_event(logger, "scrape_discover_done", job_id=str(job_id), domain=domain,
                  targets={k: v for k, v in selected_targets.items() if v})

        seen_urls: set[str] = set()
        fetched_pages: list[dict] = []
        failure_count = 0

        # ── Phase 5: fetch each target page ─────────────────────────────────
        # Build ordered page list: home first, then remaining pages shuffled
        # to avoid a predictable crawl pattern that bot detectors can fingerprint.
        page_plan: list[tuple[str, str, int]] = []  # (kind, canonical_url, depth)
        for kind, depth in _PAGE_KINDS:
            target_url = selected_targets.get(kind, "")
            canonical = canonical_internal_url(target_url, domain) if target_url else ""
            if not canonical or canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            page_plan.append((kind, canonical, depth))

        log_event(logger, "scrape_fetch_start", job_id=str(job_id), domain=domain,
                  page_count=len(page_plan))

        if len(page_plan) > 1:
            home_entry = page_plan[0] if page_plan[0][0] == "home" else None
            rest = page_plan[1:] if home_entry else page_plan[:]
            random.shuffle(rest)
            page_plan = ([home_entry] if home_entry else []) + rest

        # 5a. Per-page fetch: static → impersonate (curl_cffi) under domain policy,
        # then optional stealth batch for pages that still need a browser.
        from app.core.config import settings as _settings
        policy = get_default_manager()
        static_results: dict[str, FetchResult] = {}
        stealth_fallback_results: dict[str, FetchResult] = {}
        stealth_needed: list[tuple[str, str, int]] = []  # pages that need stealth
        working_origin_url = ""

        for kind, canonical, depth in page_plan:
            tier_result = await scrape_page_fetch(
                canonical, domain, job_id=str(job_id), policy=policy,
            )
            if tier_result.selector is not None:
                static_results[canonical] = tier_result
                if not working_origin_url:
                    working_origin_url = tier_result.final_url
                logger.info(
                    "scrape_tier_hit kind=%s url=%s mode=%s",
                    kind, canonical, tier_result.fetch_mode,
                )
            elif tier_result.error_code == FetchErrorCode.DNS_NOT_RESOLVED:
                static_results[canonical] = tier_result
            else:
                retry_url = retry_url_for_working_origin(
                    canonical=canonical,
                    working_origin_url=working_origin_url,
                    domain=domain,
                    error_code=tier_result.error_code,
                )
                if retry_url:
                    retry_result = await scrape_page_fetch(
                        retry_url, domain, job_id=str(job_id), policy=policy,
                    )
                    if retry_result.selector is not None:
                        static_results[canonical] = retry_result
                        if not working_origin_url:
                            working_origin_url = retry_result.final_url
                        logger.info(
                            "scrape_origin_retry_success kind=%s url=%s retry_url=%s mode=%s",
                            kind, canonical, retry_url, retry_result.fetch_mode,
                        )
                        continue
                    tier_result = retry_result
                if needs_stealth_after_static_and_impersonate(tier_result) and js_fallback:
                    stealth_fallback_results[canonical] = tier_result
                    stealth_needed.append((kind, canonical, depth))
                else:
                    static_results[canonical] = tier_result

        # 5b. Stealth fetch remaining pages in a single browser session
        stealth_results: dict[str, FetchResult] = {}
        if stealth_needed:
            stealth_urls = [canonical for _, canonical, _ in stealth_needed]
            logger.info("scrape_stealth_batch job_id=%s count=%d urls=%s",
                        str(job_id), len(stealth_urls), stealth_urls)
            if not await policy.mark_escalated(domain):
                log_event(
                    logger,
                    "scrape_stealth_batch_skipped",
                    job_id=str(job_id),
                    domain=domain,
                    reason="stealth_cap_reached",
                    count=len(stealth_urls),
                )
                for _, canonical, _ in stealth_needed:
                    static_results[canonical] = stealth_fallback_results[canonical]
            else:
                batch_results = await stealth_fetch_many(
                    stealth_urls,
                    delay_range=(1.5, 3.5),
                    per_page_timeout_sec=_settings.scrape_stealth_timeout_ms / 1000 + 30,
                )
                for url, result in zip(stealth_urls, batch_results, strict=True):
                    stealth_results[url] = result
                    ec = result.error_code or (
                        FetchErrorCode.OK if result.selector else FetchErrorCode.FETCH_FAILED
                    )
                    await policy.record_result(domain, ec, tier="stealth")
                    if result.selector is not None:
                        await policy.maybe_demote(domain)

        # 5c. Process results and apply per-page retry for transient failures
        _RETRY_ERROR_CODES = frozenset({
            FetchErrorCode.FETCH_FAILED,
            FetchErrorCode.TIMEOUT,
            FetchErrorCode.TOO_THIN,
            FetchErrorCode.PARSER_ERROR,
        })

        for kind, canonical, depth in page_plan:
            fetch = static_results.get(canonical) or stealth_results.get(canonical)
            if fetch is None:
                # Should not happen, but guard against it
                fetch = FetchResult(
                    final_url=canonical, status_code=0, selector=None,
                    fetch_mode="none", error_code="fetch_failed",
                    error_message="no_fetch_result",
                )

            # Retry only pages that actually entered the stealth tier so pages
            # skipped by escalation-cap logic do not quietly re-enter a browser path.
            if (fetch.selector is None
                    and fetch.error_code in _RETRY_ERROR_CODES
                    and canonical in stealth_results):
                backoff = random.uniform(5.0, 10.0)
                logger.info("scrape_page_retry kind=%s url=%s error=%s backoff=%.1f",
                            kind, canonical, fetch.error_code, backoff)
                await asyncio.sleep(backoff)
                retry_results = await stealth_fetch_many(
                    [canonical],
                    delay_range=(0, 0),
                    per_page_timeout_sec=_settings.scrape_stealth_timeout_ms / 1000 + 30,
                )
                if retry_results and retry_results[0].selector is not None:
                    fetch = retry_results[0]
                    logger.info("scrape_page_retry_success kind=%s url=%s", kind, canonical)

            if fetch.selector is None:
                failure_count += 1
                error_code = fetch.error_code or "fetch_failed"
                if not error_code or error_code == "fetch_failed":
                    if fetch.status_code == 404:
                        error_code = "not_found"
                    elif fetch.status_code == 403:
                        error_code = "access_denied"
                log_event(
                    logger, "scrape_page_fetch_failed",
                    job_id=str(job_id), kind=kind, url=canonical,
                    status_code=fetch.status_code, error_code=error_code,
                    fetch_mode=fetch.fetch_mode, error_message=fetch.error_message[:200],
                )
                fetched_pages.append({
                    "success": False,
                    "url": canonical,
                    "canonical_url": canonical,
                    "depth": depth,
                    "page_kind": kind,
                    "fetch_mode": fetch.fetch_mode,
                    "status_code": fetch.status_code,
                    "fetch_error_code": error_code,
                    "fetch_error_message": fetch.error_message,
                })
                # If the home page fails with a permanent error, stop trying subpages.
                if kind == "home" and error_code in PERMANENT_SCRAPE_ERROR_CODES:
                    log_event(logger, "scrape_aborted_permanent_home_error",
                              job_id=str(job_id), domain=domain, error_code=error_code)
                    break
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
            if fetch.extra_text:
                text = text + "\n\n" + fetch.extra_text

            # Detect parked / for-sale domains regardless of which tier fetched it.
            if kind == "home" and is_parked_domain(text):
                log_event(logger, "scrape_parked_domain_detected",
                          job_id=str(job_id), url=canonical, text_preview=text[:200])
                failure_count += 1
                fetched_pages.append({
                    "success": False,
                    "url": page_url,
                    "canonical_url": canonical_internal_url(page_url, domain) or canonical,
                    "depth": depth,
                    "page_kind": kind,
                    "fetch_mode": fetch.fetch_mode,
                    "status_code": fetch.status_code,
                    "fetch_error_code": "parked_domain",
                    "fetch_error_message": "Domain is parked or for sale.",
                })
                continue

            log_event(
                logger, "scrape_page_fetched",
                job_id=str(job_id), kind=kind, url=page_url,
                status_code=fetch.status_code, fetch_mode=fetch.fetch_mode, text_len=len(text),
            )
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
        log_event(
            logger, "scrape_fetch_done", job_id=str(job_id), domain=domain,
            pages_fetched=pages_fetched_count, failures=failure_count,
            failed_urls=[
                {"url": p["url"], "kind": p["page_kind"], "code": p.get("fetch_error_code"), "status": p.get("status_code")}
                for p in fetched_pages if not p["success"]
            ],
        )

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
                        job.state = "failed"
                        job.failure_reason = "site_unavailable"
                        job.last_error_code = dominant
                        job.last_error_message = f"All fetches failed with permanent error: {dominant}"
                    else:
                        job.state = "failed"
                        job.failure_reason = "unknown"
                        job.last_error_code = "no_pages_fetched"
                        job.last_error_message = "No pages could be fetched."
                    job.terminal_state = True
                    job.fetch_failures_count = failure_count
                    job.discovered_urls_count = len(seen_urls)
                    job.finished_at = utcnow()
                    job.updated_at = utcnow()
                    session.add(job)
                    recompute_company_stages(session, normalized_urls=[normalized_url])
                    session.commit()
                    zero_page_summary = [
                        {"success": False, "page_kind": p["page_kind"], "text_len": 0, "fetch_error_code": p.get("fetch_error_code", "")}
                        for p in fetched_pages
                    ]
                    _, terminal_code = classify_scrape_outcome(zero_page_summary)
                    log_event(logger, "scrape_completed", job_id=str(job_id), domain=domain,
                              scrape_outcome="failed_gracefully", terminal_code=terminal_code)
            return

        # ── Phase 6: markdown conversion (batched rule-based + LLM) ────────────
        from app.core.config import settings as _cfg
        markdown_pages = 0
        llm_used = 0
        llm_failed = 0

        # Split into eligible (need markdown) and ineligible (failed/thin) pages
        eligible_snaps = [
            snap for snap in fetched_pages
            if snap["success"] and snap["status_code"] < 400 and snap.get("text_len", 0) >= 80
        ]
        # Batch-convert all eligible pages in a single LLM call
        batch_input = [
            {"url": snap["url"], "title": snap.get("title", ""), "page_text": snap.get("raw_text", "")}
            for snap in eligible_snaps
        ]
        batch_results = self.markdown_service.to_markdown_batch(
            pages=batch_input,
            model=_cfg.markdown_model,
        )

        snap_to_markdown: dict[int, tuple[str, bool, str]] = {}
        for i, (snap, result) in enumerate(zip(eligible_snaps, batch_results)):
            snap_to_markdown[id(snap)] = result
            _, used_llm_flag, llm_error = result
            markdown_pages += 1
            if used_llm_flag:
                llm_used += 1
            if llm_error:
                llm_failed += 1

        page_updates: list[dict] = []
        for snap in fetched_pages:
            if id(snap) in snap_to_markdown:
                markdown, _, _ = snap_to_markdown[id(snap)]
                page_updates.append({"snap": snap, "markdown_content": markdown[:50000]})
            else:
                page_updates.append({"snap": snap, "markdown_content": ""})

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

            fetched_pages_summary = [
                {
                    "success": bool(snap.get("text_len") and snap["text_len"] > 0),
                    "page_kind": snap.get("page_kind", ""),
                    "text_len": snap.get("text_len") or 0,
                    "fetch_error_code": snap.get("fetch_error_code") or "",
                }
                for snap in fetched_pages
            ]
            scrape_outcome, terminal_code = classify_scrape_outcome(fetched_pages_summary)

            if markdown_pages == 0:
                job.state = "failed"
                job.failure_reason = "unknown"
                job.last_error_code = "no_markdown_produced"
                job.last_error_message = "Scrape completed but produced no markdown pages."
            else:
                job.state = "succeeded"
                job.failure_reason = None
                job.last_error_code = None
                job.last_error_message = None

                # Mark existing ClassificationResults stale: newer scrape content
                # is available so prior analysis should be re-run.
                company_ids_subq = select(Company.id).where(col(Company.domain) == domain)
                aj_ids_subq = select(AnalysisJob.id).where(
                    col(AnalysisJob.company_id).in_(company_ids_subq)
                )
                session.execute(
                    sa_update(ClassificationResult)
                    .where(
                        col(ClassificationResult.analysis_job_id).in_(aj_ids_subq),
                        col(ClassificationResult.is_stale).is_(False),
                    )
                    .values(is_stale=True)
                )

            session.add(job)
            recompute_company_stages(session, normalized_urls=[normalized_url])
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
                scrape_outcome=scrape_outcome,
            )


ScrapeJobManager = ScrapeService
