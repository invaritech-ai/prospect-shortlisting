#!/usr/bin/env python3
"""Benchmark classify_links_with_llm across multiple models.

For each domain:
  1. Fetch home page once to collect candidate links (shared across all models)
  2. Call classify_links_with_llm() with each model in parallel
  3. Print a comparison table: which URL did each model select per page kind?
  4. Score each model: how many non-empty, non-guessed URLs it found

Usage:
    uv run python scripts/benchmark_classify.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.services.scrape_service import (
    classify_links_with_llm,
    discover_internal_links,
    fetch_sitemap_urls,
    fetch_with_fallback,
)
from app.services.url_utils import canonical_internal_url, domain_from_url, normalize_url

DOMAINS = [
    "https://baldwinsupply.com",
    "https://aai-inc.com",
    "https://afcind.com",
    "https://automationdirect.com",
    "https://spi-connects.com",
    "https://glenair.com",
    "https://wesco.com",
    "https://megagroupcomponents.com",
]

MODELS = [
    "xiaomi/mimo-v2-omni",
    "minimax/minimax-m2.7",
    "openai/gpt-5.4-nano",
    "mistralai/mistral-small-2603",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "qwen/qwen3.5-9b",
    "inception/mercury-2",
    "google/gemini-3.1-flash-lite-preview",
]

PAGE_KINDS = ["about", "products", "contact", "team", "leadership", "pricing"]

# Baseline "known good" URLs from the previous static run with inception/mercury-2.
# Used to flag when a model picks something clearly wrong (404, login, duplicate home).
KNOWN_GOOD: dict[str, dict[str, str]] = {
    "afcind.com":         {"leadership": "/about/leadership-team", "contact": "/contact-us"},
    "wesco.com":          {"leadership": "/us/en/our-company/leadership.html", "contact": "/us/en/contact.html"},
    "automationdirect.com": {"about": "/support/about-adc", "contact": "/adc/contactus/contactus"},
    "spi-connects.com":   {"contact": "/contact"},
    "glenair.com":        {"contact": "/contact", "about": "/about"},
}


class CandidateSet(NamedTuple):
    domain: str
    home_url: str
    candidates: list[str]
    fetch_ms: float


async def collect_candidates(url: str) -> CandidateSet:
    normalized = normalize_url(url) or url
    domain = domain_from_url(normalized) or normalized
    t0 = time.perf_counter()

    # Fetch home page for internal links
    home_fetch = await fetch_with_fallback(normalized, use_js=False)
    candidates: list[str] = []
    if home_fetch.selector is not None:
        candidates.extend(
            discover_internal_links(home_fetch.selector, str(home_fetch.selector.url or normalized), domain)
        )

    fetch_ms = (time.perf_counter() - t0) * 1000

    # Deduplicate
    seen: set[str] = {canonical_internal_url(normalized, domain) or normalized}
    deduped: list[str] = []
    for c in candidates:
        canon = canonical_internal_url(c, domain)
        if canon and canon not in seen:
            seen.add(canon)
            deduped.append(canon)

    return CandidateSet(domain=domain, home_url=normalized, candidates=deduped, fetch_ms=fetch_ms)


def run_model(model: str, cs: CandidateSet) -> tuple[str, dict[str, str], float]:
    """Synchronous wrapper for one model × one domain call."""
    t0 = time.perf_counter()
    result = classify_links_with_llm(domain=cs.domain, candidates=cs.candidates, model=model)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return model, result, elapsed_ms


def short_path(url: str, domain: str) -> str:
    """Strip scheme+domain for compact display."""
    if not url:
        return ""
    for prefix in (f"https://www.{domain}", f"http://www.{domain}",
                   f"https://{domain}", f"http://{domain}"):
        if url.startswith(prefix):
            path = url[len(prefix):]
            return path or "/"
    return url[:50]


def score(results: dict[str, str]) -> int:
    """Count non-empty kind results."""
    return sum(1 for v in results.values() if v)


def main() -> None:
    print(f"Collecting candidate links from {len(DOMAINS)} domains...")
    print("(home page fetch only — no sitemap, no JS)\n")

    # Step 1: fetch all home pages concurrently
    candidate_sets: list[CandidateSet] = asyncio.run(_collect_all())

    for cs in candidate_sets:
        print(f"  {cs.domain:<35} {len(cs.candidates):>3} candidates  ({cs.fetch_ms:.0f}ms)")
    print()

    # Step 2: run all model×domain combinations in a thread pool
    # (classify_links_with_llm is synchronous — uses urllib)
    tasks: list[tuple[str, CandidateSet]] = [
        (model, cs) for cs in candidate_sets for model in MODELS
    ]

    print(f"Running {len(tasks)} classification calls ({len(MODELS)} models × {len(DOMAINS)} domains)...\n")

    # results[domain][model] = (kind_urls, elapsed_ms)
    results: dict[str, dict[str, tuple[dict[str, str], float]]] = {
        cs.domain: {} for cs in candidate_sets
    }

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(run_model, model, cs): (model, cs) for model, cs in tasks}
        done = 0
        for future in as_completed(futures):
            model, cs = futures[future]
            try:
                _, kind_urls, elapsed_ms = future.result()
                results[cs.domain][model] = (kind_urls, elapsed_ms)
            except Exception as exc:
                results[cs.domain][model] = ({}, 0.0)
                print(f"  ERROR {model} / {cs.domain}: {exc}")
            done += 1
            if done % 8 == 0:
                print(f"  {done}/{len(tasks)} done...")

    print()

    # Step 3: print per-domain tables
    model_short = [m.split("/")[-1][:22] for m in MODELS]
    col_w = 23

    for cs in candidate_sets:
        domain = cs.domain
        print("=" * 80)
        print(f"  {domain}  ({len(cs.candidates)} candidates)")
        print("=" * 80)

        # Header row
        header = f"  {'kind':<12}"
        for ms in model_short:
            header += f"  {ms:<{col_w}}"
        print(header)
        print("  " + "-" * (12 + (col_w + 2) * len(MODELS)))

        for kind in PAGE_KINDS:
            row = f"  {kind:<12}"
            for model in MODELS:
                kind_urls, _ = results[domain].get(model, ({}, 0.0))
                url = kind_urls.get(kind, "")
                path = short_path(url, domain) if url else "(none)"
                # Flag if it looks like a known-good match or clearly wrong
                good_path = KNOWN_GOOD.get(domain, {}).get(kind, "")
                if good_path and url and good_path in url:
                    marker = "✓"
                elif url and any(bad in url.lower() for bad in ("/login", "/signin", "/404")):
                    marker = "✗"
                else:
                    marker = " "
                cell = f"{marker}{path}"[:col_w]
                row += f"  {cell:<{col_w}}"
            print(row)

        # Timing row
        timing_row = f"  {'latency(ms)':<12}"
        for model in MODELS:
            _, elapsed_ms = results[domain].get(model, ({}, 0.0))
            cell = f"{elapsed_ms:.0f}ms"
            timing_row += f"  {cell:<{col_w}}"
        print("  " + "-" * (12 + (col_w + 2) * len(MODELS)))
        print(timing_row)

        # Score row
        score_row = f"  {'score':<12}"
        for model in MODELS:
            kind_urls, _ = results[domain].get(model, ({}, 0.0))
            s = score(kind_urls)
            score_row += f"  {s}/{len(PAGE_KINDS)}{' ' * (col_w - 3)}"
        print(score_row)
        print()

    # Step 4: aggregate score table
    print("=" * 80)
    print("  AGGREGATE SCORES  (sum of kinds found across all domains)")
    print("=" * 80)
    print(f"  {'model':<40} {'total':>7}  {'avg/domain':>10}  {'avg latency':>12}")
    print("  " + "-" * 75)

    model_totals: list[tuple[str, int, float]] = []
    for model in MODELS:
        total_score = 0
        total_latency = 0.0
        count = 0
        for cs in candidate_sets:
            kind_urls, elapsed_ms = results[cs.domain].get(model, ({}, 0.0))
            total_score += score(kind_urls)
            total_latency += elapsed_ms
            count += 1
        avg_score = total_score / max(count, 1)
        avg_latency = total_latency / max(count, 1)
        model_totals.append((model, total_score, avg_latency))
        max_possible = len(PAGE_KINDS) * len(DOMAINS)
        print(f"  {model:<40} {total_score:>4}/{max_possible}  {avg_score:>10.1f}  {avg_latency:>10.0f}ms")

    print()
    best = max(model_totals, key=lambda x: x[1])
    fastest = min(model_totals, key=lambda x: x[2])
    print(f"  Best coverage:  {best[0]}  ({best[1]} kinds found)")
    print(f"  Fastest:        {fastest[0]}  ({fastest[2]:.0f}ms avg)")


async def _collect_all() -> list[CandidateSet]:
    return await asyncio.gather(*[collect_candidates(url) for url in DOMAINS])


if __name__ == "__main__":
    main()
