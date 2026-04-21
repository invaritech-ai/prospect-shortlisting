"""Link classification and page discovery: sitemap parsing, LLM link picking."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re

from app.services.fetch_service import fetch_with_fallback, should_skip_url
from app.services.llm_client import LLMClient
from app.services.redis_client import get_redis
from app.services.url_utils import canonical_internal_url, clean_text

_LINK_CACHE_TTL = 86400  # 24 hours


_classify_llm = LLMClient(purpose="classify_links", max_retries=2, default_timeout=60)

_PAGE_KIND_KEYS = ("about", "products", "contact", "team", "leadership", "services", "pricing")
_PAGE_KIND_WITH_HOME = ("home",) + _PAGE_KIND_KEYS
_PAGE_KIND_DESCRIPTIONS: dict[str, str] = {
    "about": "company overview/about-us/who-we-are page (best source for canonical company name, founded year, HQ)",
    "products": "products/services/solutions/catalog/linecard page",
    "contact": "contact/get-in-touch page (phone, email, address)",
    "team": "general team/people/staff page",
    "leadership": "executive team/leadership/management/board/C-suite page",
    "services": "services/capabilities/what-we-do page",
    "pricing": "pricing/plans/packages page",
}


def _build_default_classifier_prompt(page_kinds: list[str]) -> str:
    lines = ["Find the best URL for each of these page types:"]
    for kind in page_kinds:
        description = _PAGE_KIND_DESCRIPTIONS.get(kind)
        if description:
            lines.append(f"- {kind}: {description}")
    lines.append("Ignore auth, legal, policy, cart, search, testimonial pages.")
    return "\n".join(lines)


def classify_links_with_llm(
    *,
    domain: str,
    candidates: list[str],
    model: str,
    classifier_prompt_text: str | None = None,
    requested_page_kinds: list[str] | None = None,
) -> dict[str, str]:
    """Ask an LLM to pick the best URL for each page kind from *candidates*.

    Returns a dict with keys matching _PAGE_KIND_KEYS.
    Missing or unmatched kinds are set to "".
    Results are cached in Redis for 24h — same domain + candidate set skips the LLM.
    """
    if not candidates:
        return {}

    links_block = "\n".join(f"- {url}" for url in candidates[:200])
    requested = [
        kind
        for kind in (requested_page_kinds or list(_PAGE_KIND_KEYS))
        if kind in _PAGE_KIND_KEYS
    ]
    if not requested:
        requested = list(_PAGE_KIND_KEYS)
    classifier_prompt = (classifier_prompt_text or "").strip() or _build_default_classifier_prompt(requested)

    # Check Redis cache — key is based on domain + sorted candidate fingerprint
    redis = get_redis()
    cache_key = ""
    if redis:
        try:
            fingerprint = hashlib.sha256(
                (
                    domain
                    + "\n"
                    + ",".join(requested)
                    + "\n"
                    + classifier_prompt
                    + "\n"
                    + "\n".join(sorted(candidates[:200]))
                ).encode()
            ).hexdigest()[:16]
            cache_key = f"link_classify:{fingerprint}"
            cached = redis.get(cache_key)
            if cached:
                return json.loads(cached.decode("utf-8"))
        except Exception:  # noqa: BLE001
            pass
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
                    f"{classifier_prompt}\n\n"
                    f"Links:\n{links_block}\n\n"
                    "Return JSON with these keys only: "
                    + json.dumps({k: "" for k in requested})
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    if error:
        return {}
    try:
        parsed = json.loads(content) if content else {}
        result = {k: "" for k in _PAGE_KIND_KEYS}
        for key in requested:
            result[key] = str(parsed.get(key, "") or "").strip()
    except Exception:  # noqa: BLE001
        return {}

    if redis and cache_key:
        try:
            redis.setex(cache_key, _LINK_CACHE_TTL, json.dumps(result))
        except Exception:  # noqa: BLE001
            pass

    return result


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
    classifier_prompt_text: str | None = None,
    requested_page_kinds: list[str] | None = None,
) -> dict[str, str]:
    """Return a mapping of page_kind → URL for pages worth scraping.

    Always includes "home".  Attempts to discover about, products, contact,
    team, and pricing by combining sitemap URLs and home-page link extraction,
    then asking an LLM to pick the best match for each kind.
    """
    from app.services.fetch_service import discover_internal_links

    home = canonical_internal_url(start_url, domain)
    if not home:
        return {"home": ""}

    candidates: list[str] = []
    if include_sitemap:
        candidates.extend(await fetch_sitemap_urls(domain))

    home_fetch = await fetch_with_fallback(home, use_js=use_js_fallback)
    if home_fetch.final_url:
        home = canonical_internal_url(home_fetch.final_url, domain) or home
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

    # classify_links_with_llm uses urllib (blocking I/O + time.sleep backoff).
    # Run it in a thread so it doesn't freeze the asyncio event loop and
    # prevent Playwright's internal timers from firing.
    kind_urls = await asyncio.to_thread(
        classify_links_with_llm,
        domain=domain,
        candidates=deduped,
        model=classify_model,
        classifier_prompt_text=classifier_prompt_text,
        requested_page_kinds=requested_page_kinds,
    )

    result: dict[str, str] = {"home": home}
    for kind in ("about", "products", "contact", "team", "leadership", "services", "pricing"):
        raw_url = kind_urls.get(kind, "")
        canonical_kind = canonical_internal_url(raw_url, domain) if raw_url else ""
        if not canonical_kind and kind in ("about", "products"):
            canonical_kind = canonical_internal_url(f"https://{domain}/{kind}", domain) or ""
        result[kind] = canonical_kind

    return result


def apply_page_selection_rules(
    *,
    targets: dict[str, str],
    rules: dict | None,
) -> dict[str, str]:
    """Apply optional page-kind allowlist and fallback rules to discovered targets."""
    if not rules:
        return targets

    requested_kinds = [str(k).strip().lower() for k in (rules.get("page_kinds") or []) if str(k).strip()]
    requested_kinds = [k for k in requested_kinds if k in _PAGE_KIND_WITH_HOME]
    if not requested_kinds:
        return targets

    filtered: dict[str, str] = {kind: targets.get(kind, "") for kind in requested_kinds}
    if "home" not in filtered:
        filtered["home"] = targets.get("home", "")

    if not bool(rules.get("fallback_enabled", True)):
        return filtered

    fallback_limit = int(rules.get("fallback_limit", 1) or 0)
    if fallback_limit <= 0:
        return filtered

    priority_raw = rules.get("fallback_priority") or []
    priority = [str(k).strip().lower() for k in priority_raw if str(k).strip()]
    priority = [k for k in priority if k in _PAGE_KIND_WITH_HOME]
    if not priority:
        priority = list(_PAGE_KIND_WITH_HOME)

    added = 0
    for kind in priority:
        if kind in filtered:
            continue
        value = targets.get(kind, "")
        if not value:
            continue
        filtered[kind] = value
        added += 1
        if added >= fallback_limit:
            break

    return filtered
