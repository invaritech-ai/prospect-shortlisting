#!/usr/bin/env python3
"""Scrape diagnostic script.

Usage:
    uv run python scripts/test_scrape.py https://example.com [https://other.com ...]

Options:
    --js            Enable JS/dynamic fetching (Playwright)
    --sitemap       Include sitemap.xml discovery
    --general-model MODEL   Model for markdown LLM fallback (default: from config)
    --classify-model MODEL  Model for URL classification (default: from config)
    --no-markdown   Skip markdown conversion (faster, just show raw text stats)

Output:
    Per-URL report with phase timings, discovered URLs, LLM page selections,
    per-page fetch mode / text length / markdown preview, and a summary.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Allow running from project root without installing the package.
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.markdown_service import MarkdownService
from app.services.scrape_service import (
    _PAGE_KINDS,
    discover_focus_targets,
    fetch_with_fallback,
    resolve_domain,
    should_skip_url,
)
from app.services.url_utils import canonical_internal_url, clean_text, domain_from_url, normalize_url


def _ms(t_start: float) -> str:
    return f"{(time.perf_counter() - t_start) * 1000:.0f}ms"


def _bar(n: int, total: int, width: int = 30) -> str:
    filled = int(width * n / max(total, 1))
    return "[" + "#" * filled + "-" * (width - filled) + f"] {n}/{total}"


DIVIDER = "=" * 72
SUBDIV = "-" * 50


async def scrape_url(
    url: str,
    *,
    use_js: bool,
    include_sitemap: bool,
    general_model: str,
    classify_model: str,
    do_markdown: bool,
) -> dict:
    print(f"\n{DIVIDER}")
    print(f"  URL: {url}")
    print(DIVIDER)

    normalized = normalize_url(url)
    if not normalized:
        print("  ERROR: Could not normalize URL")
        return {"url": url, "error": "bad_url"}

    domain = domain_from_url(normalized)
    if not domain:
        print("  ERROR: Could not derive domain")
        return {"url": url, "error": "bad_domain"}

    print(f"  Normalized: {normalized}")
    print(f"  Domain:     {domain}")

    result: dict = {"url": url, "normalized": normalized, "domain": domain}

    # ── Phase 1: DNS ──────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    dns_ok = await resolve_domain(domain)
    dns_ms = _ms(t0)
    status = "OK" if dns_ok else "FAILED"
    print(f"\n[DNS] {status} ({dns_ms})")
    result["dns_ok"] = dns_ok
    result["dns_ms"] = dns_ms

    if not dns_ok:
        print("  Cannot continue — domain does not resolve.")
        return result

    # ── Phase 2: Discovery ────────────────────────────────────────────────────
    print(f"\n[DISCOVERY] sitemap={include_sitemap}, js={use_js}, model={classify_model}")
    t1 = time.perf_counter()
    targets = await discover_focus_targets(
        start_url=normalized,
        domain=domain,
        include_sitemap=include_sitemap,
        use_js_fallback=use_js,
        classify_model=classify_model,
    )
    discover_ms = _ms(t1)
    print(f"  Completed in {discover_ms}")
    print(f"  Pages selected ({len([v for v in targets.values() if v])}/{len(targets)}):")
    for kind, selected_url in targets.items():
        marker = "  " if selected_url else "--"
        print(f"    {marker} {kind:12s}: {selected_url or '(none found)'}")

    result["discovery_ms"] = discover_ms
    result["targets"] = targets

    # ── Phase 3: Fetch + Markdown ─────────────────────────────────────────────
    markdown_svc = MarkdownService() if do_markdown else None

    pages = []
    total_text_chars = 0
    total_md_chars = 0

    print(f"\n[PAGES]")
    seen: set[str] = set()

    for kind, depth in _PAGE_KINDS:
        target_url = targets.get(kind, "")
        if not target_url or target_url in seen:
            if not target_url:
                print(f"\n  {kind:12s} — skipped (no URL discovered)")
            continue
        seen.add(target_url)

        print(f"\n  {kind.upper()} — {target_url}")
        print(f"  {'-' * 60}")

        t2 = time.perf_counter()
        fetch = await fetch_with_fallback(target_url, use_js=use_js)
        fetch_ms = _ms(t2)

        if fetch.selector is None:
            print(f"  Fetch:   FAILED ({fetch.error_code}) — {fetch.error_message[:120]}")
            print(f"  Time:    {fetch_ms}")
            pages.append({
                "kind": kind, "url": target_url,
                "success": False, "fetch_ms": fetch_ms,
                "error_code": fetch.error_code, "error_message": fetch.error_message,
            })
            continue

        page_url = str(fetch.selector.url or target_url)

        # Skip if redirect landed on a login/auth page.
        if should_skip_url(page_url):
            print(f"  Fetch:   SKIPPED — redirected to login/auth: {page_url}")
            pages.append({"kind": kind, "url": target_url, "success": False,
                          "fetch_ms": fetch_ms, "error_code": "login_redirect", "error_message": page_url})
            continue

        # Skip if redirect landed on a URL already scraped (e.g. /about → /).
        final_canonical = canonical_internal_url(page_url, domain) or page_url
        if final_canonical != target_url and final_canonical in seen:
            print(f"  Fetch:   SKIPPED — redirect duplicate of already-scraped page: {page_url}")
            pages.append({"kind": kind, "url": target_url, "success": False,
                          "fetch_ms": fetch_ms, "error_code": "redirect_duplicate", "error_message": page_url})
            continue
        seen.add(final_canonical)

        title = clean_text(str(fetch.selector.css("title::text").get(default="")))[:120]
        desc = clean_text(str(fetch.selector.css("meta[name='description']::attr(content)").get(default="")))[:200]
        raw_text = clean_text(str(fetch.selector.get_all_text(separator=" ")))
        text_len = len(raw_text)
        total_text_chars += text_len

        print(f"  Fetch:   OK ({fetch.fetch_mode}) — HTTP {fetch.status_code}")
        print(f"  Time:    {fetch_ms}")
        if page_url != target_url:
            print(f"  Final:   {page_url}")
        print(f"  Title:   {title or '(none)'}")
        if desc:
            print(f"  Desc:    {desc[:100]}")
        print(f"  Text:    {text_len:,} chars")

        page_info: dict = {
            "kind": kind, "url": page_url, "success": True,
            "fetch_mode": fetch.fetch_mode, "status_code": fetch.status_code,
            "fetch_ms": fetch_ms, "title": title, "text_len": text_len,
        }

        if do_markdown and markdown_svc:
            t3 = time.perf_counter()
            markdown, used_llm, llm_error = markdown_svc.to_markdown(
                url=page_url,
                title=title,
                page_text=raw_text[:40000],
                model=general_model,
            )
            md_ms = _ms(t3)
            md_len = len(markdown)
            total_md_chars += md_len

            llm_note = f" [LLM fallback{'⚠ error' if llm_error else ''}]" if used_llm else ""
            print(f"  Markdown:{md_len:,} chars{llm_note} ({md_ms})")

            # Print the first 600 chars as preview
            preview = markdown[:600].strip()
            if preview:
                print(f"\n  --- MARKDOWN PREVIEW ---")
                for line in preview.splitlines():
                    print(f"  {line}")
                if len(markdown) > 600:
                    print(f"  ... [{md_len - 600:,} more chars]")
                print(f"  --- END PREVIEW ---")

            page_info["md_len"] = md_len
            page_info["md_ms"] = md_ms
            page_info["used_llm"] = used_llm
        else:
            # Show raw text preview
            preview = raw_text[:500].strip()
            if preview:
                print(f"\n  --- TEXT PREVIEW ---")
                for line in preview.splitlines()[:15]:
                    print(f"  {line}")
                if text_len > 500:
                    print(f"  ... [{text_len - 500:,} more chars]")
                print(f"  --- END PREVIEW ---")

        pages.append(page_info)

    # ── Summary table ─────────────────────────────────────────────────────────
    all_kinds = [k for k, _ in _PAGE_KINDS]
    pages_by_kind = {p["kind"]: p for p in pages}

    print(f"\n{SUBDIV}")
    print(f"  SUMMARY for {domain}  (discovery: {discover_ms})")
    print(SUBDIV)

    col_kind  = 12
    col_stat  = 10
    col_fetch = 9
    col_text  = 9
    col_md    = 9
    header = (
        f"  {'page':<{col_kind}} {'status':<{col_stat}}"
        f" {'fetch':>{col_fetch}} {'text':>{col_text}}"
        + (f" {'markdown':>{col_md}}" if do_markdown else "")
    )
    sep = "  " + "-" * (col_kind + col_stat + col_fetch + col_text + col_md + 6)
    print(header)
    print(sep)

    for kind in all_kinds:
        p = pages_by_kind.get(kind)
        if p is None:
            row_stat  = "(not found)"
            row_fetch = "-"
            row_text  = "-"
            row_md    = "-"
        elif not p.get("success"):
            err = p.get("error_code", "fail")
            row_stat  = err[:col_stat]
            row_fetch = p.get("fetch_ms", "-")
            row_text  = "-"
            row_md    = "-"
        else:
            status = p.get("status_code", 0)
            row_stat  = f"HTTP {status}"
            row_fetch = p.get("fetch_ms", "-")
            row_text  = f"{p.get('text_len', 0):,}"
            row_md    = f"{p.get('md_len', 0):,}" if do_markdown else "-"

        print(
            f"  {kind:<{col_kind}} {row_stat:<{col_stat}}"
            f" {str(row_fetch):>{col_fetch}} {str(row_text):>{col_text}}"
            + (f" {str(row_md):>{col_md}}" if do_markdown else "")
        )

    print(sep)
    total_md_str = f" {total_md_chars:>{col_md},}" if do_markdown else ""
    print(
        f"  {'TOTAL':<{col_kind}} {'':<{col_stat}}"
        f" {'':{col_fetch}} {total_text_chars:>{col_text},}"
        + (f" {total_md_chars:>{col_md},}" if do_markdown else "")
    )

    result["pages"] = pages
    result["total_text_chars"] = total_text_chars
    result["total_md_chars"] = total_md_chars
    return result


async def main(args: argparse.Namespace) -> None:
    general_model = args.general_model or settings.general_model
    classify_model = args.classify_model or settings.classify_model

    print(f"General model:  {general_model}")
    print(f"Classify model: {classify_model}")
    print(f"JS fallback:    {args.js}")
    print(f"Sitemap:        {args.sitemap}")
    print(f"Markdown:       {not args.no_markdown}")

    t_total = time.perf_counter()
    results = []
    for url in args.urls:
        r = await scrape_url(
            url,
            use_js=args.js,
            include_sitemap=args.sitemap,
            general_model=general_model,
            classify_model=classify_model,
            do_markdown=not args.no_markdown,
        )
        results.append(r)

    total_elapsed = f"{(time.perf_counter() - t_total):.1f}s"
    print(f"\n{DIVIDER}")
    print(f"  ALL DONE — {len(args.urls)} URL(s) in {total_elapsed}")
    print(DIVIDER)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape diagnostic: run the scraping pipeline against real URLs and print verbose output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("urls", nargs="+", help="One or more URLs to scrape")
    parser.add_argument("--js", action="store_true", help="Enable JS/dynamic fetching")
    parser.add_argument("--sitemap", action="store_true", help="Include sitemap.xml discovery")
    parser.add_argument("--general-model", default="", help="Model for markdown conversion")
    parser.add_argument("--classify-model", default="", help="Model for URL classification")
    parser.add_argument("--no-markdown", action="store_true", help="Skip markdown conversion")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
