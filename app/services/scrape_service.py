from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import ssl
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from scrapling import AsyncFetcher, DynamicFetcher, Selector
from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select

from app.core.logging import log_event
from app.models import ScrapeJob, ScrapePage
from app.services.llm_client import LLMClient
from app.services.markdown_service import MarkdownService
from app.services.url_utils import absolute_url, canonical_internal_url, clean_text, domain_from_url, normalize_url


logger = logging.getLogger(__name__)
USER_AGENT = "ProspectShortlistingBot/1.0 (+https://example.com)"

# Lock TTL covers the full single-pass scrape (DNS + fetches + markdown).
# Set above the Celery soft_time_limit (30 min) so the lock outlives the task.
_SCRAPE_LOCK_TTL = timedelta(minutes=35)

# Error codes that indicate a permanent, unrecoverable website failure.
# Jobs that fail only due to these codes get status="site_unavailable" rather
# than status="failed", and are not re-enqueued by the reconciler.
PERMANENT_SCRAPE_ERROR_CODES: frozenset[str] = frozenset({"dns_not_resolved", "tls_error"})

# Page kinds discovered and fetched, in priority order.
# "home" is always the seed URL; the rest are discovered via LLM/sitemap.
_PAGE_KINDS = [
    ("home", 0),
    ("about", 1),
    ("products", 1),
    ("contact", 2),
    ("team", 2),
    ("leadership", 2),
    ("pricing", 2),
]

SKIP_HINTS: frozenset[str] = frozenset({
    "/login",
    "/signin",
    "/account",
    "/checkout",
    "/cart",
    "/privacy",
    "/terms",
    "/cookie",
    "/search",
    "/testimonial",
})


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    selector: Selector | None
    fetch_mode: str
    error_code: str
    error_message: str


class ScrapeJobAlreadyRunningError(ValueError):
    def __init__(self, *, normalized_url: str, existing_job_id: Any) -> None:
        self.normalized_url = normalized_url
        self.existing_job_id = existing_job_id
        super().__init__(f"Scrape already in progress for {normalized_url}.")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def header_value(headers: Any, key: str) -> str:
    if not isinstance(headers, dict):
        return ""
    wanted = key.lower()
    for k, v in headers.items():
        if str(k).lower() == wanted:
            return str(v)
    return ""


def is_html_selector_response(response: Selector) -> bool:
    ctype = header_value(getattr(response, "headers", {}), "content-type").lower()
    if "text/html" in ctype or "application/xhtml+xml" in ctype:
        return True
    if "application/json" in ctype or "text/plain" in ctype:
        return False
    if len(response.css("html")) > 0:
        return True
    return len(clean_text(str(response.get_all_text(separator=" ")))) > 40


def classify_fetch_error(message: str) -> str:
    lowered = (message or "").lower()
    if "dns" in lowered or "resolve host" in lowered or "name_not_resolved" in lowered:
        return "dns_not_resolved"
    if "timeout" in lowered:
        return "timeout"
    if "ssl" in lowered or "tls" in lowered or "certificate" in lowered:
        return "tls_error"
    if "non_html" in lowered:
        return "non_html"
    return "fetch_failed"


async def resolve_domain(domain: str, timeout_sec: float = 3.0) -> bool:
    if not domain:
        return False
    targets = [domain]
    if not domain.startswith("www."):
        targets.append(f"www.{domain}")
    for target in targets:
        try:
            await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, target, 443), timeout=timeout_sec)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def should_skip_url(url: str) -> bool:
    lowered = (url or "").lower().strip()
    if not lowered:
        return True
    parsed = urlparse(lowered)
    if parsed.query:
        return True
    path = parsed.path or "/"
    if path.endswith(".xml"):
        return True
    if any(token in lowered for token in SKIP_HINTS):
        return True
    return False


def discover_internal_links(selector: Selector, base_url: str, domain: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for href_value in selector.css("a::attr(href)").getall():
        href = str(href_value).strip()
        if not href or href.startswith("#") or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = absolute_url(base_url, href)
        if should_skip_url(absolute):
            continue
        canonical = canonical_internal_url(absolute, domain)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        links.append(canonical)
    return links


_classify_llm = LLMClient(purpose="classify_links", max_retries=2, default_timeout=60)

_PAGE_KIND_KEYS = ("about", "products", "contact", "team", "leadership", "services")


def classify_links_with_llm(*, domain: str, candidates: list[str], model: str) -> dict[str, str]:
    """Ask an LLM to pick the best URL for each page kind from *candidates*.

    Returns a dict with keys matching _PAGE_KIND_KEYS.
    Missing or unmatched kinds are set to "".
    """
    if not candidates:
        return {}

    links_block = "\n".join(f"- {url}" for url in candidates[:200])
    content, error = _classify_llm.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify links for one company website. "
                    "Return strict JSON with the best URL for each page type, or empty string if not found."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Domain: {domain}\n"
                    "Find the best URL for each of these page types:\n"
                    "- about: company overview/about-us/who-we-are page (best source for canonical company name, founded year, HQ)\n"
                    "- products: products/services/solutions/catalog/linecard page\n"
                    "- contact: contact/get-in-touch page (phone, email, address)\n"
                    "- team: general team/people/staff page\n"
                    "- leadership: executive team/leadership/management/board/C-suite page\n"
                    "- services: services/capabilities/what-we-do page\n"
                    "Ignore auth, legal, policy, cart, search, testimonial pages.\n\n"
                    f"Links:\n{links_block}\n\n"
                    'Return JSON: {"about":"","products":"","contact":"","team":"","leadership":"","services":""}'
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    if error:
        return {}
    try:
        parsed = json.loads(content) if content else {}
        return {k: str(parsed.get(k, "") or "").strip() for k in _PAGE_KIND_KEYS}
    except Exception:  # noqa: BLE001
        return {}


async def fetch_with_fallback(url: str, use_js: bool) -> FetchResult:
    attempts = [url]
    parsed = urlparse(url)
    if parsed.scheme == "https":
        attempts.append(url.replace("https://", "http://", 1))
    elif parsed.scheme == "http":
        attempts.append(url.replace("http://", "https://", 1))

    last_error = "unknown_fetch_error"
    for attempt in attempts:
        static_error = ""
        try:
            static_response = await AsyncFetcher.get(
                attempt,
                follow_redirects=True,
                timeout=settings.scrape_static_timeout_sec,
                retries=settings.scrape_static_retries,
                verify=False,
                headers={"user-agent": USER_AGENT},
            )
            if is_html_selector_response(static_response):
                static_text = clean_text(str(static_response.get_all_text(separator=" ")))
                # Raise threshold to 600 chars when JS fallback is available.
                # Loading screens often have 200-400 chars of boilerplate/spinner
                # text that would otherwise pass the lower threshold and get accepted
                # as real content, preventing the JS fetch from running.
                min_static_chars = 600 if use_js else 250
                if not use_js or len(static_text) >= min_static_chars:
                    return FetchResult(
                        final_url=str(static_response.url),
                        status_code=int(getattr(static_response, "status", 0) or 0),
                        selector=static_response,
                        fetch_mode="static",
                        error_code="",
                        error_message="",
                    )
                static_error = "thin_static"
            else:
                static_error = "non_html"
        except Exception as exc:  # noqa: BLE001
            static_error = str(exc)

        if use_js:
            try:
                dynamic_response = await DynamicFetcher.async_fetch(
                    attempt,
                    headless=True,
                    timeout=settings.scrape_dynamic_timeout_ms,
                    wait=settings.scrape_dynamic_wait_ms,
                    network_idle=True,
                    disable_resources=False,
                    load_dom=True,
                    retries=settings.scrape_dynamic_retries,
                    retry_delay=1,
                    extra_headers={"user-agent": USER_AGENT},
                )
                if is_html_selector_response(dynamic_response):
                    return FetchResult(
                        final_url=str(dynamic_response.url),
                        status_code=int(getattr(dynamic_response, "status", 0) or 0),
                        selector=dynamic_response,
                        fetch_mode="dynamic",
                        error_code="",
                        error_message="",
                    )
                last_error = "non_html_dynamic"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc) or static_error or "dynamic_fetch_failed"
        else:
            last_error = static_error or "fetch_failed"

    return FetchResult(
        final_url=url,
        status_code=0,
        selector=None,
        fetch_mode="none",
        error_code=classify_fetch_error(last_error),
        error_message=last_error,
    )


async def fetch_sitemap_urls(domain: str, limit: int = 200) -> list[str]:
    sitemap_url = f"https://{domain}/sitemap.xml"
    result = await fetch_with_fallback(sitemap_url, use_js=False)
    if result.selector is None:
        return []
    body = getattr(result.selector, "body", b"")
    if not body:
        return []
    try:
        content = body.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return []
    urls = re.findall(r"<loc>(.*?)</loc>", content, flags=re.IGNORECASE)
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        canonical = canonical_internal_url(clean_text(raw), domain)
        if not canonical or canonical in seen or should_skip_url(canonical):
            continue
        seen.add(canonical)
        out.append(canonical)
        if len(out) >= limit:
            break
    return out


async def discover_focus_targets(
    start_url: str,
    domain: str,
    include_sitemap: bool,
    use_js_fallback: bool,
    classify_model: str,
) -> dict[str, str]:
    """Return a mapping of page_kind → URL for pages worth scraping.

    Always includes "home".  Attempts to discover about, products, contact,
    team, and pricing by combining sitemap URLs and home-page link extraction,
    then asking an LLM to pick the best match for each kind.
    """
    home = canonical_internal_url(start_url, domain)
    if not home:
        return {"home": ""}

    candidates: list[str] = []
    if include_sitemap:
        candidates.extend(await fetch_sitemap_urls(domain))

    home_fetch = await fetch_with_fallback(home, use_js=use_js_fallback)
    if home_fetch.selector is not None:
        candidates.extend(discover_internal_links(home_fetch.selector, str(home_fetch.selector.url or home), domain))

    deduped: list[str] = []
    seen: set[str] = {home}
    for c in candidates:
        canonical = canonical_internal_url(c, domain)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        deduped.append(canonical)

    kind_urls = classify_links_with_llm(domain=domain, candidates=deduped, model=classify_model)

    result: dict[str, str] = {"home": home}
    for kind in ("about", "products", "contact", "team", "leadership", "pricing"):
        raw_url = kind_urls.get(kind, "")
        canonical_kind = canonical_internal_url(raw_url, domain) if raw_url else ""
        if not canonical_kind and kind in ("about", "products"):
            # Fallback guesses for the two most important kinds.
            canonical_kind = canonical_internal_url(f"https://{domain}/{kind}", domain) or ""
        result[kind] = canonical_kind

    return result


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

        # Fast-path check for an existing active job.
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
        fetched_pages: list[dict[str, Any]] = []
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

            # Skip if the redirect landed on a login/auth page.
            if should_skip_url(page_url):
                log_event(logger, "scrape_skipped_login_redirect", kind=kind, url=canonical, final_url=page_url)
                continue

            # Skip if the redirect landed on a URL we already scraped (e.g. /about → /).
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
                    # Determine if all fetch failures were genuinely permanent
                    # (DNS / TLS) vs transient (timeout, generic fetch error).
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
        # Done outside any DB session — no connection held during LLM calls.
        page_updates: list[dict[str, Any]] = []
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
