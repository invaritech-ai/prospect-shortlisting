#!/usr/bin/env python3
"""Scrape selected company websites and extract structured prospecting signals."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
from scrapling import AsyncFetcher, DynamicFetcher, Selector


USER_AGENT = (
    "Mozilla/5.0 (compatible; ProspectShortlistingBot/0.1; +https://example.com/bot)"
)

ROLE_TERMS = {
    "distributor": [
        "distributor",
        "authorized distributor",
        "stocking distributor",
        "channel partner",
        "line card",
    ],
    "manufacturer": [
        "manufacturer",
        "manufacturing",
        "oem",
        "factory",
        "design and manufacture",
    ],
    "reseller": [
        "reseller",
        "value-added reseller",
        "var",
        "dealer",
        "authorized reseller",
    ],
    "services": [
        "services",
        "consulting",
        "integration",
        "repair",
        "maintenance",
    ],
}

QUALITY_TERMS = {
    "rfq": ["rfq", "request a quote", "quote request"],
    "ecommerce": ["add to cart", "checkout", "buy now", "shop now"],
    "search": ["search", "parametric", "filter", "faceted"],
    "catalog": ["catalog", "products", "product categories", "brands"],
    "authorization": ["authorized", "franchised", "certified partner"],
}

ABOUT_HINTS = ("about", "company", "who-we-are", "our-story")
PRODUCT_HINTS = ("products", "catalog", "linecard", "brands", "shop")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape website sample and extract signals.")
    parser.add_argument(
        "--input-sample",
        type=Path,
        default=Path("data/website_sample_250.csv"),
        help="CSV produced by scripts/select_websites.py",
    )
    parser.add_argument(
        "--output-features",
        type=Path,
        default=Path("data/scraped_signals.csv"),
        help="Output CSV with one row per company/domain.",
    )
    parser.add_argument(
        "--output-pages",
        type=Path,
        default=Path("data/scraped_pages.jsonl"),
        help="Output JSONL with page-level captures.",
    )
    parser.add_argument("--max-sites", type=int, default=250, help="Maximum sites to scrape.")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=12,
        help="Number of concurrent site workers.",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds.")
    parser.add_argument(
        "--max-links-per-kind",
        type=int,
        default=2,
        help="Candidate links to try for about/products kinds.",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Verify SSL certificates for requests (disabled by default).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Scrapling retry attempts per URL.",
    )
    parser.add_argument(
        "--js-fallback",
        action="store_true",
        help="Use Scrapling DynamicFetcher as fallback for failed/thin static pages.",
    )
    parser.add_argument(
        "--js-timeout-ms",
        type=int,
        default=25000,
        help="Dynamic fetch timeout in milliseconds.",
    )
    parser.add_argument(
        "--js-wait-ms",
        type=int,
        default=400,
        help="Extra wait in milliseconds before closing dynamic page.",
    )
    parser.add_argument(
        "--js-min-text-len",
        type=int,
        default=250,
        help="If static page text length is below this, dynamic fallback is attempted.",
    )
    parser.add_argument(
        "--js-network-idle",
        action="store_true",
        help="Wait for network idle in dynamic fetch.",
    )
    parser.add_argument(
        "--js-disable-resources",
        action="store_true",
        help="Disable unnecessary resource loading in dynamic fetch.",
    )
    return parser.parse_args()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def same_domain(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()


def find_candidate_links(base_url: str, selector: Selector) -> dict[str, list[str]]:
    found = {"about": [], "products": []}
    seen: set[str] = set()

    for href_value in selector.css("a::attr(href)").getall():
        href = str(href_value).strip()
        if not href or href.startswith("#") or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        abs_url = urljoin(base_url, href)
        if not same_domain(base_url, abs_url):
            continue
        lowered = abs_url.lower()
        if lowered in seen:
            continue
        seen.add(lowered)

        if any(token in lowered for token in ABOUT_HINTS):
            found["about"].append(abs_url)
        if any(token in lowered for token in PRODUCT_HINTS):
            found["products"].append(abs_url)

    return found


def header_value(headers: Any, key: str) -> str:
    key_lower = key.lower()
    if isinstance(headers, dict):
        for k, v in headers.items():
            if str(k).lower() == key_lower:
                return str(v)
    return ""


def is_html_selector_response(response: Selector) -> bool:
    ctype = header_value(getattr(response, "headers", {}), "content-type").lower()
    if "text/html" in ctype or "application/xhtml+xml" in ctype:
        return True
    if "application/json" in ctype or "text/plain" in ctype:
        return False
    # Some sites/fetchers omit content-type; fall back to parsed DOM/text.
    if len(response.css("html")) > 0:
        return True
    extracted = clean_text(str(response.get_all_text(separator=" ")))
    return len(extracted) > 40


def extract_page_info(response: Selector, page_kind: str) -> dict[str, Any]:
    title = clean_text(str(response.css("title::text").get(default="")))
    description = clean_text(str(response.css("meta[name='description']::attr(content)").get(default="")))
    text = clean_text(str(response.get_all_text(separator=" ")))
    return {
        "page_kind": page_kind,
        "url": str(response.url),
        "status_code": int(getattr(response, "status", 0) or 0),
        "title": title[:300],
        "description": description[:600],
        "text_excerpt": text[:3000],
        "text_len": len(text),
        "has_search_box": int(len(response.css("input[type='search']")) > 0),
    }


def count_term_hits(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


async def fetch_with_fallback(
    url: str,
    timeout: float,
    verify_ssl: bool,
    retries: int,
    js_fallback: bool,
    js_timeout_ms: int,
    js_wait_ms: int,
    js_min_text_len: int,
    js_network_idle: bool,
    js_disable_resources: bool,
) -> tuple[str, int, Selector | None, str, str]:
    attempts = [url]
    parsed = urlparse(url)
    if parsed.scheme == "https":
        attempts.append(url.replace("https://", "http://", 1))
    elif parsed.scheme == "http":
        attempts.append(url.replace("http://", "https://", 1))

    last_error = ""
    for attempt in attempts:
        static_response: Selector | None = None
        static_error = ""
        try:
            static_response = await AsyncFetcher.get(
                attempt,
                follow_redirects=True,
                timeout=timeout,
                retries=retries,
                verify=verify_ssl,
                headers={"user-agent": USER_AGENT},
            )
            if not is_html_selector_response(static_response):
                static_error = "non_html"
            else:
                static_text = clean_text(str(static_response.get_all_text(separator=" ")))
                should_use_js = js_fallback and len(static_text) < js_min_text_len
                if not should_use_js:
                    return (
                        str(static_response.url),
                        int(getattr(static_response, "status", 0) or 0),
                        static_response,
                        "",
                        "static",
                    )
        except Exception as exc:  # noqa: BLE001
            static_error = str(exc)

        if js_fallback:
            try:
                dynamic_response = await DynamicFetcher.async_fetch(
                    attempt,
                    headless=True,
                    timeout=js_timeout_ms,
                    wait=js_wait_ms,
                    network_idle=js_network_idle,
                    disable_resources=js_disable_resources,
                    load_dom=True,
                    retries=retries,
                    retry_delay=1,
                    extra_headers={"user-agent": USER_AGENT},
                )
                if is_html_selector_response(dynamic_response):
                    return (
                        str(dynamic_response.url),
                        int(getattr(dynamic_response, "status", 0) or 0),
                        dynamic_response,
                        "",
                        "dynamic",
                    )
                if static_response is not None and static_error != "non_html":
                    return (
                        str(static_response.url),
                        int(getattr(static_response, "status", 0) or 0),
                        static_response,
                        static_error,
                        "static",
                    )
                last_error = "non_html"
            except Exception as exc:  # noqa: BLE001
                dynamic_error = str(exc)
                if static_response is not None and static_error != "non_html":
                    return (
                        str(static_response.url),
                        int(getattr(static_response, "status", 0) or 0),
                        static_response,
                        static_error,
                        "static",
                    )
                last_error = dynamic_error or static_error or "unknown_error"
        else:
            if static_response is not None and static_error != "non_html":
                return (
                    str(static_response.url),
                    int(getattr(static_response, "status", 0) or 0),
                    static_response,
                    "",
                    "static",
                )
            last_error = static_error or "unknown_error"

    return url, 0, None, last_error or "unknown_error", "none"


async def process_site(
    row: dict[str, Any],
    semaphore: asyncio.Semaphore,
    max_links_per_kind: int,
    timeout: float,
    verify_ssl: bool,
    retries: int,
    js_fallback: bool,
    js_timeout_ms: int,
    js_wait_ms: int,
    js_min_text_len: int,
    js_network_idle: bool,
    js_disable_resources: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    async with semaphore:
        base_url = str(row.get("normalized_url", "")).strip()
        domain = str(row.get("domain", "")).strip()
        raw_pages: list[dict[str, Any]] = []

        feature_row: dict[str, Any] = {
            "domain": domain,
            "normalized_url": base_url,
            "organization_name": row.get("Organization - Name", ""),
            "status_label": row.get("Organization - Company Status", ""),
            "type_label": row.get("Organization - TYPE", ""),
            "human_labels": row.get("Organization - Labels", ""),
            "source_row": row.get("source_row", ""),
            "home_status_code": 0,
            "home_fetch_error": "",
            "home_fetch_mode": "none",
            "fetched_pages": 0,
            "has_about_page": 0,
            "has_products_page": 0,
            "combined_text_len": 0,
            "dynamic_pages": 0,
        }

        if not base_url:
            feature_row["home_fetch_error"] = "missing_url"
            return feature_row, []

        final_url, status_code, home_response, error, fetch_mode = await fetch_with_fallback(
            base_url,
            timeout=timeout,
            verify_ssl=verify_ssl,
            retries=retries,
            js_fallback=js_fallback,
            js_timeout_ms=js_timeout_ms,
            js_wait_ms=js_wait_ms,
            js_min_text_len=js_min_text_len,
            js_network_idle=js_network_idle,
            js_disable_resources=js_disable_resources,
        )
        feature_row["home_status_code"] = status_code
        feature_row["home_fetch_error"] = error
        feature_row["home_fetch_mode"] = fetch_mode

        combined_chunks: list[str] = []
        if home_response is not None:
            page = extract_page_info(home_response, "home")
            page["fetch_mode"] = fetch_mode
            raw_pages.append(page)
            combined_chunks.append(page["text_excerpt"])
            links = find_candidate_links(final_url, home_response)
        else:
            links = {"about": [], "products": []}

        for kind in ("about", "products"):
            for candidate_url in links[kind][:max_links_per_kind]:
                _, _, page_response, _, page_fetch_mode = await fetch_with_fallback(
                    candidate_url,
                    timeout=timeout,
                    verify_ssl=verify_ssl,
                    retries=retries,
                    js_fallback=js_fallback,
                    js_timeout_ms=js_timeout_ms,
                    js_wait_ms=js_wait_ms,
                    js_min_text_len=js_min_text_len,
                    js_network_idle=js_network_idle,
                    js_disable_resources=js_disable_resources,
                )
                if page_response is None:
                    continue
                page = extract_page_info(page_response, kind)
                page["fetch_mode"] = page_fetch_mode
                raw_pages.append(page)
                combined_chunks.append(page["text_excerpt"])
                if kind == "about":
                    feature_row["has_about_page"] = 1
                if kind == "products":
                    feature_row["has_products_page"] = 1
                break

        full_text = clean_text(" ".join(combined_chunks)).lower()
        feature_row["fetched_pages"] = len(raw_pages)
        feature_row["combined_text_len"] = len(full_text)
        feature_row["has_search_box_any_page"] = int(any(p["has_search_box"] for p in raw_pages))
        feature_row["dynamic_pages"] = int(sum(1 for p in raw_pages if p.get("fetch_mode") == "dynamic"))

        for role, terms in ROLE_TERMS.items():
            feature_row[f"signal_{role}_hits"] = count_term_hits(full_text, terms)
        for quality, terms in QUALITY_TERMS.items():
            feature_row[f"signal_{quality}_hits"] = count_term_hits(full_text, terms)

        page_records: list[dict[str, Any]] = []
        for page in raw_pages:
            page_record = {
                "domain": domain,
                "normalized_url": base_url,
                "organization_name": row.get("Organization - Name", ""),
                "status_label": row.get("Organization - Company Status", ""),
                "type_label": row.get("Organization - TYPE", ""),
                **page,
            }
            page_record["fetch_error"] = ""
            page_records.append(page_record)

        return feature_row, page_records


async def run_scrape(args: argparse.Namespace) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frame = pd.read_csv(args.input_sample)
    frame = frame.head(args.max_sites).copy()
    rows = frame.to_dict(orient="records")

    semaphore = asyncio.Semaphore(args.concurrency)

    features: list[dict[str, Any]] = []
    page_records: list[dict[str, Any]] = []
    tasks = [
        process_site(
            row=row,
            semaphore=semaphore,
            max_links_per_kind=args.max_links_per_kind,
            timeout=args.timeout,
            verify_ssl=args.verify_ssl,
            retries=args.retries,
            js_fallback=args.js_fallback,
            js_timeout_ms=args.js_timeout_ms,
            js_wait_ms=args.js_wait_ms,
            js_min_text_len=args.js_min_text_len,
            js_network_idle=args.js_network_idle,
            js_disable_resources=args.js_disable_resources,
        )
        for row in rows
    ]
    for coro in asyncio.as_completed(tasks):
        feat, pages = await coro
        features.append(feat)
        page_records.extend(pages)

    return pd.DataFrame(features), page_records


def write_outputs(
    feature_df: pd.DataFrame,
    page_records: list[dict[str, Any]],
    output_features: Path,
    output_pages: Path,
) -> None:
    output_features.parent.mkdir(parents=True, exist_ok=True)
    output_pages.parent.mkdir(parents=True, exist_ok=True)
    feature_df.sort_values("domain").to_csv(output_features, index=False)

    with output_pages.open("w", encoding="utf-8") as handle:
        for record in page_records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    print(f"WROTE_FEATURES: {output_features} rows={len(feature_df)}")
    print(f"WROTE_PAGES: {output_pages} rows={len(page_records)}")
    if not feature_df.empty:
        ok = int((feature_df["fetched_pages"] > 0).sum())
        print(f"SITES_WITH_ANY_PAGE: {ok}")
        print(f"SITES_WITHOUT_PAGES: {len(feature_df) - ok}")


def main() -> None:
    args = parse_args()
    logging.getLogger("scrapling").setLevel(logging.ERROR)
    feature_df, page_records = asyncio.run(run_scrape(args))
    write_outputs(feature_df, page_records, args.output_features, args.output_pages)


if __name__ == "__main__":
    main()
