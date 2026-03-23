"""HTTP fetch utilities: static/dynamic/stealth tiers, DNS resolution, HTML detection.

Fetch strategy (per URL, when use_js=True):
  Tier 1 — Static  (AsyncFetcher): fast, no JS.  Keep best result.
  Tier 2 — Dynamic (DynamicFetcher): JS-rendered.  Upgrade if more content.
  Tier 3 — Stealth (StealthyFetcher): Playwright + Cloudflare bypass.
            Only triggered when Tier 1+2 both produced < 600 chars of text.
            When PS_BROWSERLESS_URL is set, connects to a remote real-Chrome
            instance via CDP (better fingerprint, different egress IP) and falls
            back to local headless Chromium if the connection fails.

When use_js=False only Tier 1 runs.

Each Playwright tier is wrapped in asyncio.wait_for() so a hung browser
process cannot block the worker indefinitely — Scrapling's internal timeout
controls page navigation, the asyncio timeout is a hard backstop.
"""
from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from scrapling import AsyncFetcher, DynamicFetcher, Selector, StealthyFetcher

from app.core.config import settings
from app.services.llm_client import LLMClient
from app.services.url_utils import absolute_url, canonical_internal_url, clean_text

logger = logging.getLogger(__name__)

# Lightweight LLM client used only for tier-upgrade decisions.
# 1 retry, 15-second timeout — fast fail so it never slows a page fetch.
_tier_llm = LLMClient(purpose="fetch_tier_decision", max_retries=1, default_timeout=15)

_TIER_DECISION_PROMPT = """\
You are evaluating a web page to decide if it needs a more powerful fetch method.

URL: {url}

Content ({char_count} chars total, showing first 1500):
---
{preview}
---

Respond with JSON only — no explanation:
{{"status": "good" | "needs_js" | "blocked"}}

- "good"     → real website content (company info, products, services, about, team, etc.)
- "needs_js" → near-empty shell, spinner, or redirect that needs JavaScript to render
- "blocked"  → bot-protection wall, CAPTCHA, Cloudflare challenge, access-denied, or parked domain\
"""


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

# Stealth tier is triggered when cumulative content is below this threshold.
_STEALTH_CONTENT_THRESHOLD = 600


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    selector: Selector | None
    fetch_mode: str
    error_code: str
    error_message: str
    # Cleaned text from other tiers (e.g. static text kept alongside dynamic).
    # Concatenated into raw_text in the scrape service so the LLM sees all content.
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


def _url_variants(url: str) -> list[str]:
    """Return [url, http_or_https_counterpart] for fallback attempts."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return [url, url.replace("https://", "http://", 1)]
    if parsed.scheme == "http":
        return [url, url.replace("http://", "https://", 1)]
    return [url]


async def _decide_tier(text: str, url: str, model: str) -> str:
    """Ask the LLM whether the fetched content is usable or needs a better tier.

    Returns one of: "good", "needs_js", "blocked".
    Falls back to a char-count heuristic if the LLM call fails.
    """
    import json as _json

    prompt = _TIER_DECISION_PROMPT.format(
        url=url,
        char_count=len(text),
        preview=text[:1500],
    )
    try:
        raw, err = await asyncio.to_thread(
            _tier_llm.chat,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=15,
        )
        if not err:
            parsed = _json.loads(raw)
            status = parsed.get("status", "")
            if status in ("good", "needs_js", "blocked"):
                logger.info("fetch_tier_decision url=%s model=%s status=%s", url, model, status)
                return status
    except Exception:  # noqa: BLE001
        pass

    # Fallback: char count heuristic
    fallback = "good" if len(text) >= _STEALTH_CONTENT_THRESHOLD else "needs_js"
    logger.info("fetch_tier_decision_fallback url=%s text_len=%d status=%s", url, len(text), fallback)
    return fallback


async def _stealth_fetch(url: str, timeout_sec: float) -> object | None:
    """Run StealthyFetcher, preferring Browserless CDP when configured.

    If PS_BROWSERLESS_URL is set, attempt to connect via CDP (real Chrome,
    different egress IP).  On any connection failure fall back to a local
    headless Chromium session so the tier always has a best-effort attempt.
    Returns the raw scrapling Response, or None on total failure.
    """
    _common = dict(
        headless=True,
        timeout=settings.scrape_stealth_timeout_ms,
        network_idle=True,
        solve_cloudflare=True,
        block_webrtc=True,
        hide_canvas=True,
    )

    if settings.browserless_url:
        try:
            logger.info("fetch_stealth_browserless url=%s", url)
            return await asyncio.wait_for(
                StealthyFetcher.async_fetch(url, cdp_url=settings.browserless_url, **_common),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning("fetch_stealth_browserless_timeout url=%s", url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch_stealth_browserless_error url=%s error=%.200s", url, str(exc))
        logger.info("fetch_stealth_browserless_fallback url=%s", url)

    # Local Chromium fallback (or primary path when browserless_url not set).
    try:
        return await asyncio.wait_for(
            StealthyFetcher.async_fetch(url, **_common),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        logger.warning("fetch_stealth_timeout url=%s timeout_sec=%.1f", url, timeout_sec)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_stealth_error url=%s error=%.200s", url, str(exc))
    return None


async def fetch_with_fallback(url: str, use_js: bool, classify_model: str = "") -> FetchResult:
    """Fetch in up to three tiers; keep both static and dynamic results.

    Strategy:
      Tier 1 (Static)  — always runs; result is kept.
      Tier 2 (Dynamic) — runs when use_js=True; result is kept alongside static.
      Tier 3 (Stealth) — runs only when use_js=True AND both static AND dynamic
                         individually produced < _STEALTH_CONTENT_THRESHOLD chars.

    The returned FetchResult uses the highest-tier selector that succeeded
    (stealth > dynamic > static) for URL/CSS metadata queries.
    The text from ALL successful tiers is preserved in extra_text so the LLM
    canonicalization step can combine it.
    """
    last_error = "unknown_fetch_error"
    detected_bot_wall = False
    variants = _url_variants(url)

    static_result: FetchResult | None = None
    static_text: str = ""
    dynamic_result: FetchResult | None = None
    dynamic_text: str = ""
    dynamic_timed_out: bool = False

    # ── Tier 1: Static ──────────────────────────────────────────────────────
    for attempt in variants:
        try:
            static_response = await AsyncFetcher.get(
                attempt,
                follow_redirects=True,
                timeout=settings.scrape_static_timeout_sec,
                retries=settings.scrape_static_retries,
                verify=False,
            )
            if not is_html_selector_response(static_response):
                last_error = "non_html_static"
                logger.info(
                    "fetch_static_non_html url=%s status=%s",
                    attempt, getattr(static_response, "status", "?"),
                )
                continue

            t = clean_text(str(static_response.get_all_text(separator=" ")))
            status = int(getattr(static_response, "status", 0) or 0)
            is_wall = is_bot_wall(t)
            logger.info(
                "fetch_static_result url=%s status=%d text_len=%d is_bot_wall=%s",
                attempt, status, len(t), is_wall,
            )

            if is_wall:
                last_error = "bot_wall_static"
                detected_bot_wall = True
                logger.info("fetch_static_bot_wall url=%s preview=%.150s", attempt, t)
                continue  # try http variant

            static_text = t
            static_result = FetchResult(
                final_url=str(static_response.url),
                status_code=status,
                selector=static_response,
                fetch_mode="static",
                error_code="",
                error_message="",
            )
            break

        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.info("fetch_static_error url=%s error=%.300s", attempt, last_error)

    logger.info(
        "fetch_after_static url=%s result=%s text_len=%d",
        url, "ok" if static_result else "none", len(static_text),
    )

    # ── Tier 2: Dynamic ─────────────────────────────────────────────────────
    # Ask the LLM if static content is good enough, falling back to char count.
    # Dynamic (Playwright) is expensive; only pay for it when needed.
    _static_decision = "needs_js"  # default: always try dynamic
    if use_js and static_result and static_text:
        _model = classify_model or settings.classify_model
        _static_decision = await _decide_tier(static_text, url, _model)
        logger.info("fetch_static_decision url=%s decision=%s", url, _static_decision)

    if use_js and _static_decision == "good":
        logger.info("fetch_dynamic_skipped url=%s reason=llm_good static_len=%d", url, len(static_text))
    if use_js and _static_decision != "good":
        _dynamic_timeout_sec = settings.scrape_dynamic_timeout_ms / 1000 + 30
        for attempt in variants:
            try:
                logger.info("fetch_dynamic_attempt url=%s timeout_sec=%.1f", attempt, _dynamic_timeout_sec)
                dynamic_response = await asyncio.wait_for(
                    DynamicFetcher.async_fetch(
                        attempt,
                        headless=True,
                        timeout=settings.scrape_dynamic_timeout_ms,
                        wait=settings.scrape_dynamic_wait_ms,
                        network_idle=True,
                        disable_resources=False,
                        load_dom=True,
                        retries=settings.scrape_dynamic_retries,
                        retry_delay=1,
                    ),
                    timeout=_dynamic_timeout_sec,
                )
                if not is_html_selector_response(dynamic_response):
                    last_error = "non_html_dynamic"
                    logger.info(
                        "fetch_dynamic_non_html url=%s status=%s",
                        attempt, getattr(dynamic_response, "status", "?"),
                    )
                    continue

                t = clean_text(str(dynamic_response.get_all_text(separator=" ")))
                status = int(getattr(dynamic_response, "status", 0) or 0)
                is_wall = is_bot_wall(t)
                logger.info(
                    "fetch_dynamic_result url=%s status=%d text_len=%d is_bot_wall=%s",
                    attempt, status, len(t), is_wall,
                )

                if is_wall:
                    last_error = "bot_wall_dynamic"
                    detected_bot_wall = True
                    logger.info("fetch_dynamic_bot_wall url=%s preview=%.150s", attempt, t)
                    continue

                dynamic_text = t
                dynamic_result = FetchResult(
                    final_url=str(dynamic_response.url),
                    status_code=status,
                    selector=dynamic_response,
                    fetch_mode="dynamic",
                    error_code="",
                    error_message="",
                )
                break

            except asyncio.TimeoutError:
                last_error = "dynamic_fetch_timeout"
                dynamic_timed_out = True
                logger.warning(
                    "fetch_dynamic_timeout url=%s timeout_sec=%.1f", attempt, _dynamic_timeout_sec,
                )
                # Timeout means the server is hung/unreachable — the HTTP
                # variant will also time out.  Stop trying variants.
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc) or "dynamic_fetch_failed"
                logger.warning("fetch_dynamic_error url=%s error=%.300s", attempt, last_error)

        logger.info(
            "fetch_after_dynamic url=%s result=%s text_len=%d",
            url, "ok" if dynamic_result else "none", len(dynamic_text),
        )

    # ── Tier 3: Stealth ─────────────────────────────────────────────────────
    stealth_result: FetchResult | None = None
    stealth_text: str = ""

    if use_js:
        # Ask LLM if dynamic content is good enough; fall back on timeout.
        _best_text = dynamic_text or static_text
        _dynamic_decision = "needs_js"  # default: run stealth if dynamic ran
        if dynamic_result and _best_text:
            _model = classify_model or settings.classify_model
            _dynamic_decision = await _decide_tier(_best_text, url, _model)
            logger.info("fetch_dynamic_decision url=%s decision=%s", url, _dynamic_decision)
        elif not dynamic_result:
            # Dynamic never ran (static was "good" or static failed) — no stealth needed.
            _dynamic_decision = "good"

        if _dynamic_decision == "good":
            logger.info("fetch_stealth_skipped url=%s reason=llm_good", url)
        elif dynamic_timed_out:
            # Dynamic timed out → server is hung or unreachable.  Stealth uses
            # the same network path and will also time out.  Skip to fail fast.
            logger.info(
                "fetch_stealth_skipped_timeout url=%s dynamic_timed_out=True",
                url,
            )
        else:
            _stealth_timeout_sec = settings.scrape_stealth_timeout_ms / 1000 + 30
            logger.info(
                "fetch_stealth_attempt url=%s static_len=%d dynamic_len=%d threshold=%d timeout_sec=%.1f browserless=%s",
                url, s_len, d_len, _STEALTH_CONTENT_THRESHOLD, _stealth_timeout_sec,
                bool(settings.browserless_url),
            )
            stealth_response = await _stealth_fetch(url, _stealth_timeout_sec)
            if stealth_response is not None:
                if not is_html_selector_response(stealth_response):
                    logger.info("fetch_stealth_non_html url=%s", url)
                else:
                    t = clean_text(str(stealth_response.get_all_text(separator=" ")))
                    status = int(getattr(stealth_response, "status", 0) or 0)
                    is_wall = is_bot_wall(t)
                    logger.info(
                        "fetch_stealth_result url=%s status=%d text_len=%d is_bot_wall=%s",
                        url, status, len(t), is_wall,
                    )
                    if is_wall:
                        detected_bot_wall = True
                        logger.info("fetch_stealth_bot_wall url=%s preview=%.150s", url, t)
                    elif len(t) < 250:
                        logger.info("fetch_stealth_too_thin url=%s text_len=%d", url, len(t))
                    else:
                        stealth_text = t
                        stealth_result = FetchResult(
                            final_url=str(stealth_response.url),
                            status_code=status,
                            selector=stealth_response,
                            fetch_mode="stealth",
                            error_code="",
                            error_message="",
                        )

    # ── Assemble final result ────────────────────────────────────────────────
    # Primary selector: stealth > dynamic > static (highest tier that succeeded).
    # extra_text: text from all OTHER successful tiers so the LLM can combine.
    primary = stealth_result or dynamic_result or static_result
    if primary is not None:
        all_texts = {
            "static": static_text,
            "dynamic": dynamic_text,
            "stealth": stealth_text,
        }
        extra = "\n\n".join(
            t for mode, t in all_texts.items()
            if t and mode != primary.fetch_mode
        )
        primary.extra_text = extra
        logger.info(
            "fetch_success url=%s primary_mode=%s primary_len=%d extra_len=%d",
            url, primary.fetch_mode,
            len(all_texts.get(primary.fetch_mode, "") or primary.extra_text),
            len(extra),
        )
        return primary

    error_code = (
        "bot_protection"
        if detected_bot_wall
        else classify_fetch_error(last_error)
    )
    logger.info(
        "fetch_all_failed url=%s last_error=%.300s error_code=%s",
        url, last_error, error_code,
    )
    return FetchResult(
        final_url=url,
        status_code=0,
        selector=None,
        fetch_mode="none",
        error_code=error_code,
        error_message=last_error,
    )
