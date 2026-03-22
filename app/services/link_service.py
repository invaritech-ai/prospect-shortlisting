"""Link classification and page discovery: sitemap parsing, LLM link picking."""
from __future__ import annotations

import asyncio
import json
import re

from app.services.fetch_service import fetch_with_fallback, should_skip_url
from app.services.llm_client import LLMClient
from app.services.url_utils import canonical_internal_url, clean_text


_classify_llm = LLMClient(purpose="classify_links", max_retries=2, default_timeout=60)

_PAGE_KIND_KEYS = ("about", "products", "contact", "team", "leadership", "services", "pricing")


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
                    "- pricing: pricing/plans/packages page\n"
                    "Ignore auth, legal, policy, cart, search, testimonial pages.\n\n"
                    f"Links:\n{links_block}\n\n"
                    'Return JSON: {"about":"","products":"","contact":"","team":"","leadership":"","services":"","pricing":""}'
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
    from app.services.fetch_service import discover_internal_links

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

    # classify_links_with_llm uses urllib (blocking I/O + time.sleep backoff).
    # Run it in a thread so it doesn't freeze the asyncio event loop and
    # prevent Playwright's internal timers from firing.
    kind_urls = await asyncio.to_thread(
        classify_links_with_llm, domain=domain, candidates=deduped, model=classify_model
    )

    result: dict[str, str] = {"home": home}
    for kind in ("about", "products", "contact", "team", "leadership", "services", "pricing"):
        raw_url = kind_urls.get(kind, "")
        canonical_kind = canonical_internal_url(raw_url, domain) if raw_url else ""
        if not canonical_kind and kind in ("about", "products"):
            canonical_kind = canonical_internal_url(f"https://{domain}/{kind}", domain) or ""
        result[kind] = canonical_kind

    return result
