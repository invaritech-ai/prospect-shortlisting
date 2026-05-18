"""ScrapeService: run the full scrape pipeline for a single ScrapeResult row."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import update as sa_update
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeBatch, ScrapeResult
from app.services.domain_policy import get_default_manager
from app.services.fetch_service import (
    FetchErrorCode,
    FetchResult,  # noqa: F401 — re-exported for callers
    is_parked_domain,
    needs_stealth_after_static_and_impersonate,
    resolve_domain,
    scrape_page_fetch,
    should_skip_url,
    stealth_fetch_many,
)
from app.services.link_service import apply_page_selection_rules, discover_focus_targets
from app.services.markdown_service import MarkdownService
from app.services.url_utils import (
    canonical_internal_url,
    clean_text,
    rewrite_to_working_origin,
)

logger = logging.getLogger(__name__)

PERMANENT_SCRAPE_ERROR_CODES: frozenset[str] = frozenset({
    "dns_not_resolved",
    "tls_error",
    "bot_protection",
    "not_found",
    "access_denied",
    "parked_domain",
})

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

_ORIGIN_RETRY_ERROR_CODES = frozenset({
    FetchErrorCode.TLS_ERROR,
    FetchErrorCode.ACCESS_DENIED,
    FetchErrorCode.FETCH_FAILED,
    FetchErrorCode.TIMEOUT,
})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _retry_url_for_working_origin(
    *, canonical: str, working_origin_url: str, domain: str, error_code: str,
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


def _increment_batch_counter(
    session: Session,
    batch_id: UUID,
    *,
    success: int = 0,
    failed: int = 0,
) -> None:
    """Atomically increment batch success/failed counters and mark completed if done."""
    batch = session.get(ScrapeBatch, batch_id)
    if batch is None:
        return
    batch.success_count += success
    batch.failed_count += failed
    done = batch.success_count + batch.failed_count
    if done >= batch.selected_domain_count and batch.state not in ("completed", "failed"):
        batch.state = "completed"
        batch.finished_at = _utcnow()
    session.add(batch)


class ScrapeService:
    def __init__(self) -> None:
        self.markdown_service = MarkdownService()

    async def run_scrape(
        self,
        *,
        engine: Engine,
        result_id: UUID,
    ) -> None:
        """Full single-pass scrape for one ScrapeResult row.

        Optimistic lock: transitions state queued → running via a conditional
        UPDATE. If another worker already claimed the row, this exits silently.
        """
        log_event(logger, "scrape_task_start", result_id=str(result_id))

        # ── Claim ──────────────────────────────────────────────────────────────
        with Session(engine) as session:
            updated = session.execute(
                sa_update(ScrapeResult)
                .where(
                    col(ScrapeResult.id) == result_id,
                    col(ScrapeResult.state) == "queued",
                )
                .values(state="running", updated_at=_utcnow())
                .returning(ScrapeResult.id)
            )
            session.commit()
            if not updated.first():
                log_event(logger, "scrape_skipped_already_claimed", result_id=str(result_id))
                return

        # ── Load domain info ────────────────────────────────────────────────────
        with Session(engine) as session:
            result = session.get(ScrapeResult, result_id)
            if result is None:
                return
            domain_row = session.get(UploadedDomain, result.domain_id)
            if domain_row is None:
                return
            batch_id = result.scrape_batch_id
            domain = domain_row.domain
            normalized_url = domain_row.normalized_url
            scrape_rules: dict[str, Any] | None = None
            if batch_id:
                batch = session.get(ScrapeBatch, batch_id)
                if batch:
                    scrape_rules = batch.settings_snapshot_json

        js_fallback = bool((scrape_rules or {}).get("js_fallback", True))
        include_sitemap = bool((scrape_rules or {}).get("include_sitemap", True))

        # ── DNS check ──────────────────────────────────────────────────────────
        log_event(logger, "scrape_dns_check", result_id=str(result_id), domain=domain)
        if not await resolve_domain(domain):
            log_event(logger, "scrape_dns_failed", result_id=str(result_id), domain=domain)
            with Session(engine) as session:
                self._write_failure(
                    session, result_id, domain_row.id, batch_id,
                    error_code="dns_not_resolved",
                    fetched_pages=[],
                )
            return

        # ── Discover target URLs ────────────────────────────────────────────────
        classify_model = None
        classifier_prompt_text = (
            str(scrape_rules.get("classifier_prompt_text", "")).strip()
            if scrape_rules and scrape_rules.get("classifier_prompt_text") is not None
            else ""
        )
        requested_page_kinds = (
            [str(k).strip().lower() for k in (scrape_rules.get("page_kinds") or []) if str(k).strip()]
            if scrape_rules else []
        )

        from app.jobs._defaults import DEFAULT_CLASSIFY_MODEL
        classify_model = DEFAULT_CLASSIFY_MODEL

        log_event(logger, "scrape_discover_start", result_id=str(result_id), domain=domain)
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
        log_event(logger, "scrape_discover_done", result_id=str(result_id), domain=domain,
                  targets={k: v for k, v in selected_targets.items() if v})

        seen_urls: set[str] = set()
        fetched_pages: list[dict] = []
        failure_count = 0

        # ── Build page plan ────────────────────────────────────────────────────
        page_plan: list[tuple[str, str, int]] = []
        for kind, depth in _PAGE_KINDS:
            target_url = selected_targets.get(kind, "")
            canonical = canonical_internal_url(target_url, domain) if target_url else ""
            if not canonical or canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            page_plan.append((kind, canonical, depth))

        if len(page_plan) > 1:
            home_entry = page_plan[0] if page_plan[0][0] == "home" else None
            rest = page_plan[1:] if home_entry else page_plan[:]
            random.shuffle(rest)
            page_plan = ([home_entry] if home_entry else []) + rest

        # ── Fetch pages (static → impersonate → stealth) ───────────────────────
        from app.core.config import settings as _settings
        policy = get_default_manager()
        static_results: dict[str, FetchResult] = {}
        stealth_fallback_results: dict[str, FetchResult] = {}
        stealth_needed: list[tuple[str, str, int]] = []
        working_origin_url = ""

        for kind, canonical, depth in page_plan:
            tier_result = await scrape_page_fetch(
                canonical, domain, job_id=str(result_id), policy=policy,
            )
            if tier_result.selector is not None:
                static_results[canonical] = tier_result
                if not working_origin_url:
                    working_origin_url = tier_result.final_url
            elif tier_result.error_code == FetchErrorCode.DNS_NOT_RESOLVED:
                static_results[canonical] = tier_result
            else:
                retry_url = _retry_url_for_working_origin(
                    canonical=canonical,
                    working_origin_url=working_origin_url,
                    domain=domain,
                    error_code=tier_result.error_code,
                )
                if retry_url:
                    retry_result = await scrape_page_fetch(
                        retry_url, domain, job_id=str(result_id), policy=policy,
                    )
                    if retry_result.selector is not None:
                        static_results[canonical] = retry_result
                        if not working_origin_url:
                            working_origin_url = retry_result.final_url
                        continue
                    tier_result = retry_result
                if needs_stealth_after_static_and_impersonate(tier_result) and js_fallback:
                    stealth_fallback_results[canonical] = tier_result
                    stealth_needed.append((kind, canonical, depth))
                else:
                    static_results[canonical] = tier_result

        if stealth_needed:
            stealth_urls = [canonical for _, canonical, _ in stealth_needed]
            if not await policy.mark_escalated(domain):
                for _, canonical, _ in stealth_needed:
                    static_results[canonical] = stealth_fallback_results[canonical]
            else:
                batch_stealth = await stealth_fetch_many(
                    stealth_urls,
                    delay_range=(1.5, 3.5),
                    per_page_timeout_sec=_settings.scrape_stealth_timeout_ms / 1000 + 30,
                )
                for url, result in zip(stealth_urls, batch_stealth, strict=True):
                    ec = result.error_code or (
                        FetchErrorCode.OK if result.selector else FetchErrorCode.FETCH_FAILED
                    )
                    await policy.record_result(domain, ec, tier="stealth")
                    if result.selector is not None:
                        await policy.maybe_demote(domain)
                    static_results[url] = result

        _RETRY_ERROR_CODES = frozenset({
            FetchErrorCode.FETCH_FAILED,
            FetchErrorCode.TIMEOUT,
            FetchErrorCode.TOO_THIN,
            FetchErrorCode.PARSER_ERROR,
        })

        for kind, canonical, depth in page_plan:
            fetch = static_results.get(canonical)
            if fetch is None:
                fetch = FetchResult(
                    final_url=canonical, status_code=0, selector=None,
                    fetch_mode="none", error_code="fetch_failed",
                    error_message="no_fetch_result",
                )

            if (fetch.selector is None
                    and fetch.error_code in _RETRY_ERROR_CODES
                    and canonical in (r.final_url for r in (static_results.get(c) for c in [canonical]) if r)):
                backoff = random.uniform(5.0, 10.0)
                await asyncio.sleep(backoff)
                retry_results = await stealth_fetch_many(
                    [canonical], delay_range=(0, 0),
                    per_page_timeout_sec=_settings.scrape_stealth_timeout_ms / 1000 + 30,
                )
                if retry_results and retry_results[0].selector is not None:
                    fetch = retry_results[0]

            if fetch.selector is None:
                failure_count += 1
                error_code = fetch.error_code or "fetch_failed"
                if not error_code or error_code == "fetch_failed":
                    if fetch.status_code == 404:
                        error_code = "not_found"
                    elif fetch.status_code == 403:
                        error_code = "access_denied"
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
                if kind == "home" and error_code in PERMANENT_SCRAPE_ERROR_CODES:
                    break
                continue

            selector = fetch.selector
            page_url = str(selector.url or canonical)
            if should_skip_url(page_url):
                continue

            final_canonical = canonical_internal_url(page_url, domain) or page_url
            if final_canonical != canonical and final_canonical in seen_urls:
                continue
            seen_urls.add(final_canonical)

            title = clean_text(str(selector.css("title::text").get(default="")))[:300]
            description = clean_text(
                str(selector.css("meta[name='description']::attr(content)").get(default=""))
            )[:800]
            text = clean_text(str(selector.get_all_text(separator=" ")))
            if fetch.extra_text:
                text = text + "\n\n" + fetch.extra_text

            if kind == "home" and is_parked_domain(text):
                failure_count += 1
                fetched_pages.append({
                    "success": False,
                    "url": page_url,
                    "canonical_url": final_canonical,
                    "depth": depth,
                    "page_kind": kind,
                    "fetch_mode": fetch.fetch_mode,
                    "status_code": fetch.status_code,
                    "fetch_error_code": "parked_domain",
                    "fetch_error_message": "Domain is parked or for sale.",
                })
                continue

            fetched_pages.append({
                "success": True,
                "url": page_url,
                "canonical_url": final_canonical,
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
            failure_codes = [
                p.get("fetch_error_code", "") for p in fetched_pages if not p["success"]
            ]
            all_permanent = bool(failure_codes) and all(
                c in PERMANENT_SCRAPE_ERROR_CODES for c in failure_codes
            )
            dominant = (
                max(set(failure_codes), key=failure_codes.count) if failure_codes else "no_pages_fetched"
            )
            with Session(engine) as session:
                self._write_failure(
                    session, result_id, domain_row.id, batch_id,
                    error_code=dominant,
                    fetched_pages=fetched_pages,
                )
            return

        # ── Markdown conversion ────────────────────────────────────────────────
        from app.core.config import settings as _cfg
        eligible_snaps = [
            snap for snap in fetched_pages
            if snap["success"] and snap["status_code"] < 400 and snap.get("text_len", 0) >= 80
        ]
        batch_input = [
            {"url": snap["url"], "title": snap.get("title", ""), "page_text": snap.get("raw_text", "")}
            for snap in eligible_snaps
        ]
        batch_results = self.markdown_service.to_markdown_batch(
            pages=batch_input,
            model=_cfg.markdown_model,
        )
        snap_to_markdown: dict[int, tuple[str, bool, str]] = {
            id(snap): result
            for snap, result in zip(eligible_snaps, batch_results)
        }

        markdown_pages = 0
        scraped_pages_json: list[dict[str, Any]] = []
        for snap in fetched_pages:
            entry: dict[str, Any] = {
                "kind": snap.get("page_kind", ""),
                "url": snap["url"],
                "fetch_mode": snap.get("fetch_mode", ""),
                "success": snap["success"],
                "status_code": snap.get("status_code", 0),
                "error_code": snap.get("fetch_error_code") or None,
            }
            if snap["success"]:
                md_tuple = snap_to_markdown.get(id(snap))
                if md_tuple:
                    markdown, _, _ = md_tuple
                    entry["markdown"] = markdown[:50000]
                    if markdown.strip():
                        markdown_pages += 1
                else:
                    entry["markdown"] = ""
            scraped_pages_json.append(entry)

        # ── Write results ──────────────────────────────────────────────────────
        with Session(engine) as session:
            result_row = session.get(ScrapeResult, result_id)
            if result_row is None or result_row.state != "running":
                log_event(logger, "scrape_results_skipped_not_owner", result_id=str(result_id))
                return

            now = _utcnow()
            final_state = "succeeded" if markdown_pages > 0 else "failed"
            dominant_error = None
            if final_state == "failed":
                fc = [p.get("fetch_error_code", "") for p in fetched_pages if not p["success"]]
                dominant_error = max(set(fc), key=fc.count) if fc else "no_markdown_produced"

            result_row.state = final_state
            result_row.pages_attempted_count = len(fetched_pages)
            result_row.pages_success_count = pages_fetched_count
            result_row.markdown_pages_count = markdown_pages
            result_row.scraped_pages_json = scraped_pages_json
            result_row.error_code = dominant_error
            result_row.updated_at = now
            session.add(result_row)

            domain_row_db = session.get(UploadedDomain, result_row.domain_id)
            if domain_row_db:
                domain_row_db.scrape_status = final_state
                session.add(domain_row_db)

            if batch_id:
                _increment_batch_counter(
                    session, batch_id,
                    success=1 if final_state == "succeeded" else 0,
                    failed=1 if final_state == "failed" else 0,
                )

            session.commit()

        log_event(
            logger, "scrape_completed",
            result_id=str(result_id), domain=domain,
            pages_fetched=pages_fetched_count, markdown_pages=markdown_pages,
            final_state=final_state,
        )

    def _write_failure(
        self,
        session: Session,
        result_id: UUID,
        domain_id: UUID,
        batch_id: UUID | None,
        *,
        error_code: str,
        fetched_pages: list[dict],
    ) -> None:
        now = _utcnow()
        scraped_pages_json = [
            {
                "kind": p.get("page_kind", ""),
                "url": p["url"],
                "fetch_mode": p.get("fetch_mode", ""),
                "success": False,
                "status_code": p.get("status_code", 0),
                "error_code": p.get("fetch_error_code") or error_code,
            }
            for p in fetched_pages
        ]

        result_row = session.get(ScrapeResult, result_id)
        if result_row and result_row.state == "running":
            result_row.state = "failed"
            result_row.error_code = error_code
            result_row.pages_attempted_count = len(fetched_pages)
            result_row.scraped_pages_json = scraped_pages_json if scraped_pages_json else None
            result_row.updated_at = now
            session.add(result_row)

        domain_row = session.get(UploadedDomain, domain_id)
        if domain_row:
            domain_row.scrape_status = "failed"
            session.add(domain_row)

        if batch_id:
            _increment_batch_counter(session, batch_id, failed=1)

        session.commit()
