"""
Scrapling fetcher exploration script.

Run with:  uv run python scripts/test_scrapling.py

Tests all three fetcher tiers against sites that are known to have
varying levels of bot protection.
"""
from __future__ import annotations

import asyncio
import time

from scrapling import AsyncFetcher, DynamicFetcher, StealthyFetcher

# ── Sites to test ────────────────────────────────────────────────────────────
PLAIN_SITES = [
    "https://example.com",             # trivial, always works
    "https://statesupply.com",         # electrical distributor, may have JS
]

PROTECTED_SITES = [
    "https://andantex.com",            # behind Cloudflare
    "https://northcoastelectric.com",  # behind Cloudflare
    "https://richardselectric.com",
    "https://pepconet.com",
]


def _text_preview(selector, chars: int = 120) -> str:
    try:
        text = selector.get_all_text(separator=" ").strip()
        return text[:chars].replace("\n", " ")
    except Exception:
        return "(could not extract text)"


# ── Tier 1: AsyncFetcher (static HTTP, curl_cffi) ────────────────────────────
async def test_static(url: str) -> None:
    print(f"\n{'─'*60}")
    print(f"STATIC  {url}")
    t0 = time.perf_counter()
    try:
        resp = await AsyncFetcher.get(
            url,
            follow_redirects=True,
            timeout=12,
            stealthy_headers=True,   # realistic browser headers
            verify=False,
        )
        elapsed = time.perf_counter() - t0
        text = resp.get_all_text(separator=" ").strip()
        print(f"  status : {getattr(resp, 'status', '?')}")
        print(f"  chars  : {len(text)}")
        print(f"  time   : {elapsed:.1f}s")
        print(f"  preview: {_text_preview(resp)}")
    except Exception as exc:
        print(f"  ERROR  : {exc}")


# ── Tier 2: DynamicFetcher (Playwright Chromium) ─────────────────────────────
async def test_dynamic(url: str) -> None:
    print(f"\n{'─'*60}")
    print(f"DYNAMIC {url}")
    t0 = time.perf_counter()
    try:
        resp = await DynamicFetcher.async_fetch(
            url,
            headless=True,
            timeout=28_000,
            wait=3_000,
            network_idle=True,
            load_dom=True,
            disable_resources=False,
        )
        elapsed = time.perf_counter() - t0
        text = resp.get_all_text(separator=" ").strip()
        print(f"  status : {getattr(resp, 'status', '?')}")
        print(f"  chars  : {len(text)}")
        print(f"  time   : {elapsed:.1f}s")
        print(f"  preview: {_text_preview(resp)}")
    except Exception as exc:
        print(f"  ERROR  : {exc}")


# ── Tier 3: StealthyFetcher (patchright + Cloudflare solver) ─────────────────
async def test_stealth(url: str) -> None:
    print(f"\n{'─'*60}")
    print(f"STEALTH {url}")
    t0 = time.perf_counter()
    try:
        resp = await StealthyFetcher.async_fetch(
            url,
            headless=True,
            timeout=60_000,
            network_idle=True,
            solve_cloudflare=True,   # auto-solve Turnstile / JS / interstitial challenges
            block_webrtc=True,       # prevent IP leak through WebRTC
            hide_canvas=True,        # randomise canvas fingerprint
        )
        elapsed = time.perf_counter() - t0
        text = resp.get_all_text(separator=" ").strip()
        print(f"  status : {getattr(resp, 'status', '?')}")
        print(f"  chars  : {len(text)}")
        print(f"  time   : {elapsed:.1f}s")
        print(f"  preview: {_text_preview(resp)}")
    except Exception as exc:
        print(f"  ERROR  : {exc}")


# ── page_action example: scroll + wait for lazy content ─────────────────────
async def test_page_action(url: str) -> None:
    """
    page_action lets you run arbitrary Playwright automation before the
    page content is captured — useful for infinite scroll, clicking 'Accept'
    on cookie banners, filling in forms, etc.
    """
    print(f"\n{'─'*60}")
    print(f"PAGE_ACTION {url}")

    async def scroll_to_bottom(page):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)

    t0 = time.perf_counter()
    try:
        resp = await DynamicFetcher.async_fetch(
            url,
            headless=True,
            timeout=28_000,
            network_idle=True,
            page_action=scroll_to_bottom,
        )
        elapsed = time.perf_counter() - t0
        text = resp.get_all_text(separator=" ").strip()
        print(f"  chars  : {len(text)}")
        print(f"  time   : {elapsed:.1f}s")
        print(f"  preview: {_text_preview(resp)}")
    except Exception as exc:
        print(f"  ERROR  : {exc}")


# ── CSS selector demo ────────────────────────────────────────────────────────
async def test_selectors(url: str) -> None:
    """Show how to extract structured data with Scrapling's CSS selector API."""
    print(f"\n{'─'*60}")
    print(f"SELECTORS {url}")
    try:
        resp = await AsyncFetcher.get(url, follow_redirects=True, stealthy_headers=True, verify=False)
        title   = resp.css("title::text").get(default="(no title)")
        desc    = resp.css("meta[name='description']::attr(content)").get(default="(no desc)")
        h1s     = resp.css("h1::text").getall()
        links   = resp.css("a::attr(href)").getall()
        print(f"  title  : {title[:80]}")
        print(f"  desc   : {desc[:120]}")
        print(f"  h1s    : {h1s[:3]}")
        print(f"  links  : {len(links)} found, first 3: {links[:3]}")
    except Exception as exc:
        print(f"  ERROR  : {exc}")


async def main() -> None:
    print("=" * 60)
    print("TIER 1 — Static (AsyncFetcher)")
    print("=" * 60)
    for url in PLAIN_SITES:
        await test_static(url)

    print("\n\n" + "=" * 60)
    print("TIER 2 — Dynamic (DynamicFetcher / Playwright)")
    print("=" * 60)
    for url in PROTECTED_SITES[:2]:   # just 2 to keep runtime reasonable
        await test_dynamic(url)

    print("\n\n" + "=" * 60)
    print("TIER 3 — Stealth (StealthyFetcher / patchright + Cloudflare solver)")
    print("=" * 60)
    for url in PROTECTED_SITES[:2]:
        await test_stealth(url)

    print("\n\n" + "=" * 60)
    print("EXTRAS — page_action + CSS selectors")
    print("=" * 60)
    await test_page_action("https://example.com")
    await test_selectors("https://example.com")

    print("\n\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
