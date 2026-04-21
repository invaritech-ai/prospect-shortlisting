#!/usr/bin/env python3
"""Live benchmark: static + impersonate fetch tiers against a handful of URLs.

Usage (from repo root):
  uv run python scripts/benchmark_fetch_domains.py
  uv run python scripts/benchmark_fetch_domains.py --urls 'https://a.com/,https://b.com/'
  PS_SCRAPE_LIVE_BENCHMARK=1 uv run pytest tests/test_fetch_live_domains.py -q

Does not run stealth/browser by default (fast, low cost). Use --with-stealth to
exercise the stealth tier (slow; may need Browserless or local Playwright).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/benchmark_fetch_domains.py` without PYTHONPATH=.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import argparse
import asyncio
import json
import sys
import time
from urllib.parse import urlparse

from app.core.config import settings
from app.services.fetch_service import (
    FetchErrorCode,
    _impersonate_fetch,
    _static_fetch,
    stealth_fetch_many,
)

# Curated for pipeline regression checks: mix of HTTP/HTTPS, small business sites,
# and a stable control (example.com).
DEFAULT_BENCHMARK_URLS: tuple[str, ...] = (
    "http://2t.com/",
    "https://2t.com/company/about-us.html",
    "http://21stcenturybearings.com/",
    "https://21stcenturybearings.com/about-us/",
    "https://example.com/",
    "https://www.wikipedia.org/wiki/Main_Page",
)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


async def _one_url(
    url: str,
    *,
    with_stealth: bool,
) -> dict[str, object]:
    dom = _domain(url)
    out: dict[str, object] = {"url": url, "domain": dom}

    t0 = time.perf_counter()
    static = await _static_fetch(url, timeout_sec=settings.scrape_static_timeout_sec)
    out["static_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["static_ok"] = static.selector is not None
    out["static_code"] = static.status_code
    out["static_error"] = static.error_code or FetchErrorCode.OK

    t1 = time.perf_counter()
    imp = await _impersonate_fetch(
        url, domain=dom, timeout_sec=settings.scrape_impersonate_timeout_sec
    )
    out["impersonate_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    out["impersonate_ok"] = imp.selector is not None
    out["impersonate_code"] = imp.status_code
    out["impersonate_error"] = imp.error_code or FetchErrorCode.OK

    if with_stealth:
        t2 = time.perf_counter()
        stealth_batch = await stealth_fetch_many([url], delay_range=(0, 0), per_page_timeout_sec=120.0)
        st = stealth_batch[0] if stealth_batch else None
        out["stealth_ms"] = round((time.perf_counter() - t2) * 1000, 1)
        out["stealth_ok"] = bool(st and st.selector is not None)
        out["stealth_code"] = getattr(st, "status_code", 0) if st else 0
        out["stealth_error"] = (st.error_code if st else "missing") or FetchErrorCode.OK

    return out


async def _run(urls: list[str], *, with_stealth: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for url in urls:
        u = url.strip()
        if not u:
            continue
        rows.append(await _one_url(u, with_stealth=with_stealth))
    return rows


def _print_table(rows: list[dict[str, object]], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    headers = (
        "url",
        "static_ok",
        "static_err",
        "imp_ok",
        "imp_err",
        "static_ms",
        "imp_ms",
    )
    if rows and "stealth_ok" in rows[0]:
        headers += ("st_ok", "st_err", "st_ms")
    print("\t".join(headers))
    for r in rows:
        line = [
            str(r.get("url", ""))[:60],
            str(r.get("static_ok")),
            str(r.get("static_error", ""))[:16],
            str(r.get("impersonate_ok")),
            str(r.get("impersonate_error", ""))[:16],
            str(r.get("static_ms")),
            str(r.get("impersonate_ms")),
        ]
        if "stealth_ok" in r:
            line += [
                str(r.get("stealth_ok")),
                str(r.get("stealth_error", ""))[:16],
                str(r.get("stealth_ms")),
            ]
        print("\t".join(line))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark static + impersonate fetch on test URLs.")
    parser.add_argument(
        "--urls",
        default="",
        help="Comma-separated URLs (default: built-in regression set).",
    )
    parser.add_argument(
        "--with-stealth",
        action="store_true",
        help="Also run stealth_fetch_many per URL (slow; optional).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON instead of a TSV table.",
    )
    args = parser.parse_args(argv)

    if args.urls.strip():
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    else:
        urls = list(DEFAULT_BENCHMARK_URLS)

    rows = asyncio.run(_run(urls, with_stealth=args.with_stealth))
    _print_table(rows, as_json=args.as_json)

    any_fail = any(
        not bool(r.get("static_ok")) and not bool(r.get("impersonate_ok"))
        for r in rows
    )
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
