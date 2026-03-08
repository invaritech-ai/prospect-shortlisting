from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright
from scrapling import AsyncFetcher, DynamicFetcher, Selector
from sqlmodel import Session, col, delete, select

from app.core.config import settings
from app.core.logging import log_event
from app.models import ScrapeJob, ScrapePage
from app.services.markdown_service import MarkdownService
from app.services.ocr_service import OCRService
from app.services.url_utils import absolute_url, canonical_internal_url, clean_text, domain_from_url, normalize_url


logger = logging.getLogger(__name__)
USER_AGENT = "ProspectShortlistingBot/1.0 (+https://example.com)"

SKIP_HINTS = (
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
)


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


def classify_links_with_llm(*, domain: str, candidates: list[str], model: str) -> tuple[str, str]:
    api_key = (settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
    if not api_key or not candidates:
        return "", ""

    links_block = "\n".join(f"- {url}" for url in candidates[:200])
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify links for one company website. "
                    "Return strict JSON with best_about and best_products only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Domain: {domain}\n"
                    "Task:\n"
                    "- Choose best_about URL (about/company/team)\n"
                    "- Choose best_products URL (products/catalog/shop/linecard)\n"
                    "- Ignore auth, legal, policy, cart, search, testimonial pages\n\n"
                    "Links:\n"
                    f"{links_block}\n\n"
                    'Return JSON: {"best_about":"", "best_products":""}'
                ),
            },
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        url=f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.openrouter_site_url,
            "X-Title": settings.openrouter_app_name,
        },
    )
    try:
        with urlopen(request, context=ssl.create_default_context(), timeout=60) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="ignore")
        decoded = json.loads(raw)
        content = decoded["choices"][0]["message"]["content"]
        parsed = json.loads(content) if isinstance(content, str) else {}
        about = str(parsed.get("best_about", "") or "").strip()
        products = str(parsed.get("best_products", "") or "").strip()
        return about, products
    except Exception:  # noqa: BLE001
        return "", ""


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
                if not use_js or len(static_text) >= 250:
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
                    network_idle=False,
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
    home = canonical_internal_url(start_url, domain)
    if not home:
        return {"home": "", "about": "", "products": ""}

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

    about_raw, products_raw = classify_links_with_llm(
        domain=domain,
        candidates=deduped,
        model=classify_model,
    )
    about = canonical_internal_url(about_raw, domain) if about_raw else ""
    products = canonical_internal_url(products_raw, domain) if products_raw else ""
    if not about:
        about = canonical_internal_url(f"https://{domain}/about", domain) or ""
    if not products:
        products = canonical_internal_url(f"https://{domain}/products", domain) or ""
    return {"home": home, "about": about, "products": products}


def capture_page_screenshot(url: str, path: Path) -> tuple[str, str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 2200})
            page.goto(url, wait_until="domcontentloaded", timeout=settings.scrape_screenshot_timeout_ms)
            page.wait_for_timeout(settings.scrape_screenshot_settle_ms)
            page.screenshot(path=str(path), full_page=True)
            browser.close()
        return str(path), ""
    except Exception as exc:  # noqa: BLE001
        return "", str(exc)


def should_convert_to_markdown(page: ScrapePage) -> bool:
    if page.status_code >= 400:
        return False
    if page.text_len < 80:
        return False
    return True


class ScrapeService:
    def __init__(self) -> None:
        self.ocr_service = OCRService()
        self.markdown_service = MarkdownService()

    def create_job(
        self,
        *,
        session: Session,
        website_url: str,
        max_pages: int,
        max_depth: int,
        js_fallback: bool,
        include_sitemap: bool,
        general_model: str,
        classify_model: str,
        ocr_model: str,
        enable_ocr: bool,
        max_images_per_page: int,
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
            max_pages=max_pages,
            max_depth=max_depth,
            js_fallback=js_fallback,
            include_sitemap=include_sitemap,
            general_model=general_model,
            classify_model=classify_model,
            ocr_model=ocr_model,
            enable_ocr=enable_ocr,
            max_images_per_page=max_images_per_page,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    async def run_step1(self, *, session: Session, job: ScrapeJob) -> ScrapeJob:
        job.status = "running_step1"
        job.stage1_status = "running"
        job.terminal_state = False
        job.step1_started_at = utcnow()
        job.updated_at = utcnow()
        session.add(job)
        session.commit()

        if not await resolve_domain(job.domain):
            job.status = "step1_failed"
            job.stage1_status = "failed"
            job.stage2_status = "skipped"
            job.terminal_state = True
            job.last_error_code = "dns_not_resolved"
            job.last_error_message = f"{job.domain} :: dns_not_resolved"
            job.fetch_failures_count = 1
            job.step1_finished_at = utcnow()
            job.updated_at = utcnow()
            session.add(job)
            session.commit()
            return job

        session.exec(delete(ScrapePage).where(col(ScrapePage.job_id) == job.id))
        session.commit()
        job.pages_fetched_count = 0
        failure_count = 0

        targets = await discover_focus_targets(
            start_url=job.normalized_url,
            domain=job.domain,
            include_sitemap=job.include_sitemap,
            use_js_fallback=job.js_fallback,
            classify_model=job.classify_model,
        )

        ordered_targets = [("home", 0), ("about", 1), ("products", 1)]
        seen: set[str] = set()
        for kind, depth in ordered_targets:
            target_url = targets.get(kind, "")
            canonical = canonical_internal_url(target_url, job.domain) if target_url else ""
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)

            fetch = await fetch_with_fallback(canonical, use_js=job.js_fallback)
            if fetch.selector is None:
                failure_count += 1
                session.add(
                    ScrapePage(
                        job_id=job.id,
                        url=canonical,
                        canonical_url=canonical,
                        depth=depth,
                        page_kind=kind,
                        fetch_mode=fetch.fetch_mode,
                        status_code=fetch.status_code,
                        fetch_error_code=fetch.error_code or "fetch_failed",
                        fetch_error_message=fetch.error_message,
                    )
                )
                continue

            selector = fetch.selector
            page_url = str(selector.url or canonical)
            title = clean_text(str(selector.css("title::text").get(default="")))[:300]
            description = clean_text(str(selector.css("meta[name='description']::attr(content)").get(default="")))[:800]
            text = clean_text(str(selector.get_all_text(separator=" ")))
            html_body = getattr(selector, "body", b"")
            html_snapshot = (
                html_body.decode("utf-8", errors="ignore")
                if isinstance(html_body, (bytes, bytearray))
                else str(html_body or "")
            )
            session.add(
                ScrapePage(
                    job_id=job.id,
                    url=page_url,
                    canonical_url=canonical_internal_url(page_url, job.domain) or canonical,
                    depth=depth,
                    page_kind=kind,
                    fetch_mode=fetch.fetch_mode,
                    status_code=fetch.status_code,
                    title=title,
                    description=description,
                    text_len=len(text),
                    raw_text=text[:40000],
                    html_snapshot=html_snapshot[:200000],
                    image_urls_json="[]",
                    fetch_error_code="",
                    fetch_error_message="",
                )
            )
            job.pages_fetched_count += 1

        job.discovered_urls_count = len(seen)
        job.fetch_failures_count = failure_count
        job.stage1_status = "completed"
        job.status = "step1_completed"
        job.step1_finished_at = utcnow()
        job.updated_at = utcnow()
        if job.pages_fetched_count == 0:
            job.status = "step1_failed"
            job.stage1_status = "failed"
            job.stage2_status = "skipped"
            job.terminal_state = True
            job.last_error_code = "no_pages_fetched"
            job.last_error_message = "No pages fetched in step1."
        session.add(job)
        session.commit()
        session.refresh(job)

        log_event(
            logger,
            "step1_completed",
            job_id=str(job.id),
            domain=job.domain,
            pages_fetched=job.pages_fetched_count,
            failures=job.fetch_failures_count,
        )
        return job

    def run_step2(self, *, session: Session, job: ScrapeJob) -> ScrapeJob:
        job.status = "running_step2"
        job.stage2_status = "running"
        job.step2_started_at = utcnow()
        job.updated_at = utcnow()
        session.add(job)
        session.commit()

        pages = list(
            session.exec(
                select(ScrapePage)
                .where(col(ScrapePage.job_id) == job.id)
                .order_by(col(ScrapePage.depth), col(ScrapePage.id))
            )
        )
        screenshot_dir = Path("data/scrape_screenshots") / str(job.id).replace("-", "")
        markdown_pages = 0
        ocr_images = 0
        llm_used = 0
        llm_failed = 0

        for page in pages:
            if not should_convert_to_markdown(page):
                page.markdown_content = ""
                page.updated_at = utcnow()
                session.add(page)
                continue

            screenshot_path = ""
            screenshot_error = ""
            if page.id is not None:
                screenshot_path, screenshot_error = capture_page_screenshot(
                    page.url,
                    screenshot_dir / f"{page.page_kind}_{page.id}.png",
                )

            ocr_text = ""
            if job.enable_ocr and screenshot_path:
                ocr_text, ocr_error = self.ocr_service.extract_text_from_file(
                    screenshot_path,
                    model=job.ocr_model,
                )
                if ocr_text:
                    ocr_images += 1
                elif ocr_error:
                    screenshot_error = screenshot_error or ocr_error

            ocr_payload = ocr_text.strip()
            if screenshot_path:
                prefix = f"[SCREENSHOT_PATH] {screenshot_path}"
                ocr_payload = f"{prefix}\n\n{ocr_payload}" if ocr_payload else prefix
            if screenshot_error:
                ocr_payload = f"{ocr_payload}\n\n[SCREENSHOT_ERROR] {screenshot_error}".strip()

            markdown, used_llm, llm_error = self.markdown_service.to_markdown(
                url=page.url,
                title=page.title,
                page_text=page.raw_text,
                ocr_text=ocr_payload,
                model=job.general_model,
            )
            page.ocr_text = ocr_payload[:16000]
            page.markdown_content = markdown[:50000]
            page.updated_at = utcnow()
            session.add(page)

            markdown_pages += 1
            if used_llm:
                llm_used += 1
            if llm_error:
                llm_failed += 1

        job.markdown_pages_count = markdown_pages
        job.ocr_images_processed_count = ocr_images
        job.llm_used_count = llm_used
        job.llm_failed_count = llm_failed
        job.stage2_status = "completed"
        job.status = "completed"
        job.terminal_state = True
        job.step2_finished_at = utcnow()
        job.updated_at = utcnow()
        session.add(job)
        session.commit()
        session.refresh(job)

        log_event(
            logger,
            "step2_completed",
            job_id=str(job.id),
            domain=job.domain,
            markdown_pages=job.markdown_pages_count,
            ocr_images=job.ocr_images_processed_count,
            llm_used=job.llm_used_count,
            llm_failed=job.llm_failed_count,
        )
        return job
