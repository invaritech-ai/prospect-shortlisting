"""HTTP fetch utilities: static fetch, stealth fetch, DNS resolution, HTML detection.

Fetch strategy (two tiers):
  1. Static (httpx): fast GET, no JS — works for sites without bot protection.
  2. Stealth (StealthyFetcher): Playwright + Cloudflare bypass — for JS-heavy / protected sites.

Stealth mode is **deterministic per worker** — no cross-fallback:
  - Workers with PS_BROWSERLESS_URL set → Browserless CDP only.
  - Workers without PS_BROWSERLESS_URL  → local headless Chromium only.

For multi-page fetches on the same domain, use `stealth_fetch_many()` which keeps
a single browser session alive across all pages (faster + looks more natural to
bot detectors).
"""
from __future__ import annotations

import asyncio
import logging
import random
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx
from scrapling import Selector, StealthyFetcher
from scrapling.engines._browsers._stealth import AsyncStealthySession

from app.core.config import settings
from app.services.url_utils import absolute_url, canonical_internal_url, clean_text

logger = logging.getLogger(__name__)


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
    extra_text: str = ""


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


# Patterns that indicate a bot-protection wall rather than real site content.
_BOT_WALL_PATTERNS: tuple[str, ...] = (
    "incapsula incident id",           # Imperva / Incapsula
    "request unsuccessful",            # Imperva / Incapsula prefix
    "just a moment",                   # Cloudflare interstitial (pre-solve)
    "checking your browser",           # Cloudflare
    "enable javascript and cookies",   # Cloudflare JS challenge
    "please enable cookies",           # Cloudflare
    "ddos-guard",                      # DDoS-Guard
    "ray id:",                         # Cloudflare debug footer
    "access denied",                   # Generic WAF
    "403 forbidden",                   # Generic WAF
    "pardon our interruption",         # Imperva / Incapsula interstitial
    "something about your browser",    # Imperva / Incapsula description
    "verify you are human",            # Generic CAPTCHA gate
    "please verify you",               # Generic CAPTCHA gate
    "are you a robot",                 # Generic bot check
    "unusual traffic",                 # Google / generic rate-limit
    "too many requests",               # HTTP 429 pages
    "rate limit",                      # Generic rate-limit page
)

# Patterns that indicate a parked / for-sale domain with no real content.
_PARKED_DOMAIN_PATTERNS: tuple[str, ...] = (
    "domain for sale",
    "this domain is for sale",
    "buy this domain",
    "domain is available",
    "domain may be for sale",
    "godaddy.com",                     # GoDaddy parking page
    "sedoparking.com",                 # Sedo domain parking
    "dan.com",                         # DAN domain marketplace
    "hugedomains.com",                 # HugeDomains
    "afternic.com",                    # Afternic marketplace
    "namecheap.com",                   # Namecheap parking
    "register this domain",
    "this web page is parked",
    "this domain has been registered",
)


def is_bot_wall(text: str) -> bool:
    """Return True if the page text looks like a WAF/bot-protection page."""
    lowered = text.lower()
    return any(pattern in lowered for pattern in _BOT_WALL_PATTERNS)


def is_parked_domain(text: str) -> bool:
    """Return True if the page looks like a parked / for-sale domain."""
    lowered = text.lower()
    return any(pattern in lowered for pattern in _PARKED_DOMAIN_PATTERNS)


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


_dns_cache: dict[str, tuple[bool, float]] = {}  # domain → (resolved, expires_at)
_DNS_CACHE_TTL = 300.0  # 5 minutes


async def resolve_domain(domain: str, timeout_sec: float = 3.0) -> bool:
    if not domain:
        return False

    now = time.monotonic()
    cached = _dns_cache.get(domain)
    if cached and now < cached[1]:
        return cached[0]

    targets = [domain]
    if not domain.startswith("www."):
        targets.append(f"www.{domain}")
    for target in targets:
        try:
            await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, target, 443), timeout=timeout_sec)
            _dns_cache[domain] = (True, now + _DNS_CACHE_TTL)
            return True
        except Exception:  # noqa: BLE001
            continue
    _dns_cache[domain] = (False, now + _DNS_CACHE_TTL)
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


def _selector_text(selector: object) -> str:
    return clean_text(str(getattr(selector, "get_all_text", lambda **_: "")
                         (separator=" ") if callable(getattr(selector, "get_all_text", None)) else ""))


# ── Static fetch (httpx) ─────────────────────────────────────────────────────

_STATIC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


async def _static_fetch(url: str, timeout_sec: float = 12.0) -> FetchResult:
    """Fast static GET via httpx. No JS execution — works for simple sites."""
    try:
        async with httpx.AsyncClient(
            headers=_STATIC_HEADERS,
            follow_redirects=True,
            timeout=timeout_sec,
            verify=True,
        ) as client:
            resp = await client.get(url)

        ctype = resp.headers.get("content-type", "").lower()
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            return FetchResult(
                final_url=str(resp.url), status_code=resp.status_code,
                selector=None, fetch_mode="static",
                error_code="non_html", error_message="non_html response",
            )

        text = clean_text(resp.text)

        if resp.status_code >= 400:
            return FetchResult(
                final_url=str(resp.url), status_code=resp.status_code,
                selector=None, fetch_mode="static",
                error_code="fetch_failed", error_message=f"HTTP {resp.status_code}",
            )

        if is_bot_wall(text):
            return FetchResult(
                final_url=str(resp.url), status_code=resp.status_code,
                selector=None, fetch_mode="static",
                error_code="bot_protection", error_message="bot_wall",
            )

        if len(text) < 250:
            return FetchResult(
                final_url=str(resp.url), status_code=resp.status_code,
                selector=None, fetch_mode="static",
                error_code="too_thin", error_message="too_thin",
            )

        selector = Selector(text=resp.text)
        selector.url = str(resp.url)  # type: ignore[attr-defined]
        selector.status = resp.status_code  # type: ignore[attr-defined]
        logger.info("fetch_static_success url=%s status=%d text_len=%d", url, resp.status_code, len(text))
        return FetchResult(
            final_url=str(resp.url), status_code=resp.status_code,
            selector=selector, fetch_mode="static",
            error_code="", error_message="",
        )

    except httpx.TimeoutException:
        logger.info("fetch_static_timeout url=%s", url)
        return FetchResult(
            final_url=url, status_code=0, selector=None,
            fetch_mode="static", error_code="timeout", error_message="static_timeout",
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("fetch_static_error url=%s error=%.200s", url, str(exc))
        return FetchResult(
            final_url=url, status_code=0, selector=None,
            fetch_mode="static", error_code=classify_fetch_error(str(exc)),
            error_message=str(exc)[:500],
        )


async def _recover_https_tls_error(url: str) -> FetchResult | None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return None

    fallback_url = urlunparse(parsed._replace(scheme="http"))
    timeout_sec = settings.scrape_stealth_timeout_ms / 1000 + 30

    results = await stealth_fetch_many(
        [fallback_url],
        delay_range=(0, 0),
        per_page_timeout_sec=timeout_sec,
    )
    if not results:
        return None

    result = results[0]
    if result.selector is not None:
        return result

    return None


# ── Stealth fetch (single page, kept for backward compat) ────────────────────

async def _stealth_fetch(url: str, timeout_sec: float) -> Selector | None:
    """Run StealthyFetcher via Browserless CDP *or* local Chromium.

    The mode is deterministic — based solely on whether PS_BROWSERLESS_URL is
    set.  Workers are split by environment: browserless workers set the URL,
    local workers leave it blank.  No cross-fallback between the two.
    """
    _timeout_ms: int = settings.scrape_stealth_timeout_ms
    fetch_kwargs: dict = {
        "headless": True,
        "timeout": _timeout_ms,
        "network_idle": True,
        "solve_cloudflare": True,
        "block_webrtc": True,
        "hide_canvas": True,
    }

    mode = "browserless" if settings.browserless_url else "local"
    if settings.browserless_url:
        fetch_kwargs["cdp_url"] = settings.browserless_url

    try:
        logger.info("fetch_stealth_%s url=%s", mode, url)
        return await asyncio.wait_for(
            StealthyFetcher.async_fetch(url, **fetch_kwargs),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        logger.warning("fetch_stealth_%s_timeout url=%s timeout_sec=%.1f", mode, url, timeout_sec)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_stealth_%s_error url=%s error=%.200s", mode, url, str(exc))
    return None


def _validate_stealth_response(url: str, response: Selector | None) -> FetchResult:
    """Validate a stealth response and return a FetchResult."""
    if response is None:
        return FetchResult(
            final_url=url, status_code=0, selector=None,
            fetch_mode="stealth", error_code="fetch_failed",
            error_message="stealth_fetch_failed",
        )

    if not is_html_selector_response(response):
        return FetchResult(
            final_url=str(response.url), status_code=0, selector=None,
            fetch_mode="stealth", error_code="non_html",
            error_message="non_html",
        )

    t = clean_text(str(response.get_all_text(separator=" ")))
    status = int(getattr(response, "status", 0) or 0)

    if is_bot_wall(t):
        logger.info("fetch_stealth_bot_wall url=%s preview=%.150s", url, t)
        return FetchResult(
            final_url=str(response.url), status_code=status, selector=None,
            fetch_mode="stealth", error_code="bot_protection",
            error_message="bot_wall",
        )

    if len(t) < 250:
        return FetchResult(
            final_url=str(response.url), status_code=status, selector=None,
            fetch_mode="stealth", error_code="too_thin",
            error_message="too_thin",
        )

    logger.info("fetch_success url=%s mode=stealth text_len=%d", url, len(t))
    return FetchResult(
        final_url=str(response.url), status_code=status, selector=response,
        fetch_mode="stealth", error_code="", error_message="",
    )


# ── Session-reusing stealth multi-fetch ───────────────────────────────────────

def _stealth_session_kwargs() -> dict:
    """Build kwargs for AsyncStealthySession from settings."""
    _timeout_ms: int = settings.scrape_stealth_timeout_ms
    kwargs: dict = {
        "headless": True,
        "timeout": _timeout_ms,
        "network_idle": True,
        "solve_cloudflare": True,
        "block_webrtc": True,
        "hide_canvas": True,
    }
    if settings.browserless_url:
        kwargs["cdp_url"] = settings.browserless_url
    # Add parser config the same way StealthyFetcher.async_fetch does
    kwargs["selector_config"] = {**StealthyFetcher._generate_parser_arguments()}
    return kwargs


async def stealth_fetch_many(
    urls: list[str],
    *,
    delay_range: tuple[float, float] = (1.5, 3.5),
    per_page_timeout_sec: float = 150.0,
) -> list[FetchResult]:
    """Fetch multiple URLs in a single browser session (same context/cookies).

    Opens one browser, fetches each URL sequentially with a randomized delay
    between pages. This is faster (no browser restart per page) and looks more
    natural to bot detectors.
    """
    if not urls:
        return []

    mode = "browserless" if settings.browserless_url else "local"
    session_kwargs = _stealth_session_kwargs()
    results: list[FetchResult] = []

    try:
        async with AsyncStealthySession(**session_kwargs) as engine:
            for i, url in enumerate(urls):
                # Jittered delay between pages (skip first)
                if i > 0:
                    delay = random.uniform(*delay_range)
                    await asyncio.sleep(delay)

                logger.info("fetch_stealth_session_%s url=%s page=%d/%d", mode, url, i + 1, len(urls))
                try:
                    response = await asyncio.wait_for(
                        engine.fetch(url),
                        timeout=per_page_timeout_sec,
                    )
                    result = _validate_stealth_response(url, response)
                except asyncio.TimeoutError:
                    logger.warning("fetch_stealth_session_timeout url=%s", url)
                    result = FetchResult(
                        final_url=url, status_code=0, selector=None,
                        fetch_mode="stealth", error_code="timeout",
                        error_message="stealth_session_timeout",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("fetch_stealth_session_error url=%s error=%.200s", url, str(exc))
                    result = FetchResult(
                        final_url=url, status_code=0, selector=None,
                        fetch_mode="stealth", error_code=classify_fetch_error(str(exc)),
                        error_message=str(exc)[:500],
                    )
                results.append(result)

    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_stealth_session_start_error error=%.200s", str(exc))
        # If the session itself fails to start, return failures for all remaining URLs
        for url in urls[len(results):]:
            results.append(FetchResult(
                final_url=url, status_code=0, selector=None,
                fetch_mode="stealth", error_code=classify_fetch_error(str(exc)),
                error_message=str(exc)[:500],
            ))

    return results


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_with_fallback(url: str, use_js: bool = True, classify_model: str = "") -> FetchResult:
    """Fetch a single URL: try static first, fall back to stealth if needed."""
    # Tier 1: static fetch (fast, ~1-2s)
    static_result = await _static_fetch(url, timeout_sec=settings.scrape_static_timeout_sec)
    if static_result.selector is not None:
        return static_result

    if static_result.error_code == "tls_error":
        recovered = await _recover_https_tls_error(url)
        if recovered is not None:
            return recovered
        return static_result

    # Static failed — if it's a permanent error (DNS), don't bother with stealth
    if static_result.error_code == "dns_not_resolved":
        return static_result

    # Tier 2: stealth fetch (browser, ~30-60s)
    timeout_sec = settings.scrape_stealth_timeout_ms / 1000 + 30
    logger.info(
        "fetch_stealth_attempt url=%s timeout_sec=%.1f browserless=%s",
        url, timeout_sec, bool(settings.browserless_url),
    )
    response = await _stealth_fetch(url, timeout_sec)
    return _validate_stealth_response(url, response)
