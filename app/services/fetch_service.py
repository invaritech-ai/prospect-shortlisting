"""HTTP fetch utilities: stealth fetch, DNS resolution, HTML detection.

Fetch strategy (all URLs):
  Stealth (StealthyFetcher): Playwright + Cloudflare bypass.

  Mode is **deterministic per worker** — no cross-fallback:
    - Workers with PS_BROWSERLESS_URL set → Browserless CDP only.
    - Workers without PS_BROWSERLESS_URL  → local headless Chromium only.
  This is designed for split-worker deployment (e.g. 2 browserless + 2 local).

DNS is checked before fetching; unresolvable domains short-circuit immediately.
The fetch is wrapped in asyncio.wait_for() so a hung browser process cannot
block the worker indefinitely.
"""
from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from scrapling import Selector, StealthyFetcher

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


def _selector_text(selector: object) -> str:
    return clean_text(str(getattr(selector, "get_all_text", lambda **_: "")
                         (separator=" ") if callable(getattr(selector, "get_all_text", None)) else ""))


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


async def fetch_with_fallback(url: str, use_js: bool = True, classify_model: str = "") -> FetchResult:
    """Fetch using StealthyFetcher (Playwright + Cloudflare bypass).

    Uses Browserless CDP when PS_BROWSERLESS_URL is set, otherwise local
    Chromium.  No cross-fallback — mode is deterministic per worker.
    """
    timeout_sec = settings.scrape_stealth_timeout_ms / 1000 + 30
    detected_bot_wall = False
    last_error = "stealth_fetch_failed"

    logger.info(
        "fetch_stealth_attempt url=%s timeout_sec=%.1f browserless=%s",
        url, timeout_sec, bool(settings.browserless_url),
    )

    response = await _stealth_fetch(url, timeout_sec)

    if response is not None:
        if not is_html_selector_response(response):
            logger.info("fetch_stealth_non_html url=%s", url)
            last_error = "non_html"
        else:
            t = clean_text(str(response.get_all_text(separator=" ")))
            status = int(getattr(response, "status", 0) or 0)
            is_wall = is_bot_wall(t)
            logger.info(
                "fetch_stealth_result url=%s status=%d text_len=%d is_bot_wall=%s",
                url, status, len(t), is_wall,
            )
            if is_wall:
                detected_bot_wall = True
                last_error = "bot_wall"
                logger.info("fetch_stealth_bot_wall url=%s preview=%.150s", url, t)
            elif len(t) < 250:
                last_error = "too_thin"
                logger.info("fetch_stealth_too_thin url=%s text_len=%d", url, len(t))
            else:
                logger.info("fetch_success url=%s mode=stealth text_len=%d", url, len(t))
                return FetchResult(
                    final_url=str(response.url),
                    status_code=status,
                    selector=response,
                    fetch_mode="stealth",
                    error_code="",
                    error_message="",
                )

    error_code = "bot_protection" if detected_bot_wall else classify_fetch_error(last_error)
    logger.info("fetch_all_failed url=%s last_error=%s error_code=%s", url, last_error, error_code)
    return FetchResult(
        final_url=url,
        status_code=0,
        selector=None,
        fetch_mode="none",
        error_code=error_code,
        error_message=last_error,
    )
