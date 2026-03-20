"""HTTP fetch utilities: static/dynamic fetching, DNS resolution, HTML detection."""
from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from scrapling import AsyncFetcher, DynamicFetcher, Selector

from app.core.config import settings
from app.services.url_utils import absolute_url, canonical_internal_url, clean_text


USER_AGENT = "ProspectShortlistingBot/1.0 (+https://example.com)"

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


def header_value(headers: object, key: str) -> str:
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


async def fetch_with_fallback(url: str, use_js: bool) -> FetchResult:
    attempts = [url]
    parsed = urlparse(url)
    if parsed.scheme == "https":
        attempts.append(url.replace("https://", "http://", 1))
    elif parsed.scheme == "http":
        attempts.append(url.replace("http://", "https://", 1))

    last_error = "unknown_fetch_error"
    # Keep the best thin static result across all attempts so we can fall back
    # to it when the dynamic fetcher crashes instead of losing it entirely.
    thin_static_fallback: FetchResult | None = None

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
                # Static returned valid HTML but below the JS-enrichment threshold.
                # Stash it — if the dynamic fetch fails we use this instead of nothing.
                static_error = "thin_static"
                if thin_static_fallback is None:
                    thin_static_fallback = FetchResult(
                        final_url=str(static_response.url),
                        status_code=int(getattr(static_response, "status", 0) or 0),
                        selector=static_response,
                        fetch_mode="static_thin",
                        error_code="",
                        error_message="",
                    )
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

    # All attempts exhausted — return the thin static fallback if we have one.
    if thin_static_fallback is not None:
        return thin_static_fallback

    return FetchResult(
        final_url=url,
        status_code=0,
        selector=None,
        fetch_mode="none",
        error_code=classify_fetch_error(last_error),
        error_message=last_error,
    )
