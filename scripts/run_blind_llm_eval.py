#!/usr/bin/env python3
"""Blind crawl + LLM prediction + evaluation pipeline for the 300-site set."""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import logging
import os
import re
import socket
import ssl
import textwrap
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

import pandas as pd
from scrapling import AsyncFetcher, DynamicFetcher, Selector


USER_AGENT = "ProspectShortlistingBot/0.2 (+https://example.com)"
US_ALLOWED_SUFFIXES = (
    ".com",
    ".net",
    ".org",
    ".us",
    ".edu",
    ".gov",
    ".mil",
)
SKIP_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".zip",
    ".rar",
    ".7z",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".mp4",
    ".mp3",
    ".avi",
    ".mov",
}


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    selector: Selector | None
    fetch_mode: str
    error: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Blind evaluation pipeline: crawl -> LLM classify -> evaluate."
    )
    parser.add_argument(
        "--mode",
        choices=["crawl", "classify", "evaluate", "abtest", "all"],
        default="all",
        help="Pipeline stage(s) to run.",
    )
    parser.add_argument(
        "--input-sample",
        type=Path,
        default=Path("data/website_sample_300.csv"),
        help="Input website sample CSV.",
    )
    parser.add_argument(
        "--max-sites",
        type=int,
        default=300,
        help="Max number of sites from sample to process.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Print progress every N completed domains.",
    )

    # Crawl settings
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrent domain crawls.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Static fetch timeout seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Fetch retries per URL.")
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Enable TLS cert verification for static fetches (disabled by default).",
    )
    parser.add_argument(
        "--js-fallback",
        action="store_true",
        help="Use DynamicFetcher fallback on failed/thin static responses.",
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
        help="Dynamic fetch wait in milliseconds after load.",
    )
    parser.add_argument(
        "--js-min-text-len",
        type=int,
        default=250,
        help="If static text shorter than this, trigger dynamic fallback.",
    )
    parser.add_argument(
        "--js-network-idle",
        action="store_true",
        help="Wait for network idle during dynamic fetch.",
    )
    parser.add_argument(
        "--js-disable-resources",
        action="store_true",
        help="Disable extra resources in dynamic fetch.",
    )
    parser.add_argument(
        "--max-pages-per-domain",
        type=int,
        default=60,
        help="Cap pages per domain crawl.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Max crawl depth from start URL.",
    )
    parser.add_argument(
        "--include-sitemap",
        action="store_true",
        help="Seed crawl queue from sitemap.xml URLs when available.",
    )
    parser.add_argument(
        "--no-dns-precheck",
        action="store_true",
        help="Disable DNS precheck before crawling a domain.",
    )
    parser.add_argument(
        "--domain-crawl-jsonl",
        type=Path,
        default=Path("data/domain_crawl_300.jsonl"),
        help="Domain-level crawl records JSONL.",
    )
    parser.add_argument(
        "--domain-pages-jsonl",
        type=Path,
        default=Path("data/domain_pages_300.jsonl"),
        help="Page-level crawl records JSONL.",
    )
    parser.add_argument(
        "--crawl-summary-csv",
        type=Path,
        default=Path("data/domain_crawl_300_summary.csv"),
        help="Crawl summary CSV.",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("data/domain_profiles"),
        help="Directory for per-domain markdown profiles.",
    )

    # LLM settings
    parser.add_argument(
        "--openrouter-api-key-env",
        default="OPENROUTER_API_KEY",
        help="Environment variable name for OpenRouter API key.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Optional env file to load API keys from if environment variable is missing.",
    )
    parser.add_argument(
        "--llm-model",
        default="arcee-ai/trinity-large-preview:free",
        help="OpenRouter model id.",
    )
    parser.add_argument(
        "--prompt-variant",
        default="baseline_multiclass_v1",
        choices=["baseline_multiclass_v1", "binary_precision_v1"],
        help="Prompt variant used in classify mode.",
    )
    parser.add_argument(
        "--ab-variants",
        default="baseline_multiclass_v1,binary_precision_v1",
        help="Comma-separated prompt variants for abtest mode.",
    )
    parser.add_argument(
        "--llm-workers",
        type=int,
        default=4,
        help="Concurrent LLM requests.",
    )
    parser.add_argument(
        "--llm-max-pages",
        type=int,
        default=25,
        help="Max pages per domain included in prompt context.",
    )
    parser.add_argument(
        "--llm-max-chars-per-page",
        type=int,
        default=1400,
        help="Max chars per page in prompt context.",
    )
    parser.add_argument(
        "--llm-max-total-chars",
        type=int,
        default=28000,
        help="Max total chars per domain prompt context.",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=0.0,
        help="LLM temperature.",
    )
    parser.add_argument(
        "--predictions-jsonl",
        type=Path,
        default=Path("data/llm_predictions_300.jsonl"),
        help="LLM predictions JSONL output.",
    )
    parser.add_argument(
        "--predictions-csv",
        type=Path,
        default=Path("data/llm_predictions_300.csv"),
        help="LLM predictions CSV output.",
    )
    parser.add_argument(
        "--ab-out-dir",
        type=Path,
        default=Path("data/abtest"),
        help="Output directory for A/B prompt test artifacts.",
    )
    parser.add_argument(
        "--ab-summary-csv",
        type=Path,
        default=Path("data/abtest/ab_summary.csv"),
        help="A/B metrics summary CSV path.",
    )
    parser.add_argument(
        "--ab-summary-md",
        type=Path,
        default=Path("data/abtest/ab_summary.md"),
        help="A/B metrics summary markdown path.",
    )

    # Evaluation settings
    parser.add_argument(
        "--evaluation-md",
        type=Path,
        default=Path("data/llm_eval_300.md"),
        help="Evaluation markdown report path.",
    )
    return parser.parse_args()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_url_candidates(raw: str) -> list[str]:
    value = (raw or "").strip()
    if not value:
        return []
    chunks = re.split(r"[\s,;]+", value.replace("\n", " ").replace("\t", " "))
    candidates: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        token = chunk.strip()
        if not token:
            continue
        if token.lower() in {"http:/", "https:/", "http://", "https://"}:
            continue
        if "://" not in token:
            token = f"https://{token}"
        parsed = urlparse(token)
        if not parsed.netloc:
            continue
        if token in seen:
            continue
        seen.add(token)
        candidates.append(token)
    return candidates


def is_reasonable_host(netloc: str) -> bool:
    host = (netloc or "").strip().lower()
    if not host:
        return False
    host = host.split("@")[-1]
    host = host.split(":")[0]
    if not host:
        return False
    if any(ch in host for ch in (",", "/", " ")):
        return False
    if host.startswith(".") or host.endswith("."):
        return False
    if "." not in host:
        return False
    return True


def normalize_url(raw: str) -> str:
    candidates = split_url_candidates(raw)
    if not candidates:
        return ""
    for value in candidates:
        parsed = urlparse(value)
        if not parsed.netloc:
            continue
        if not is_reasonable_host(parsed.netloc):
            continue
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path or "/"
        normalized = parsed._replace(
            scheme=(parsed.scheme or "https").lower(),
            netloc=netloc,
            path=path,
            params="",
            query=parsed.query,
            fragment="",
        )
        return urlunparse(normalized)
    return ""


def domain_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_us_target_domain(domain: str) -> bool:
    d = (domain or "").strip().lower()
    if not d:
        return False
    if d.endswith(US_ALLOWED_SUFFIXES):
        return True
    last = d.rsplit(".", 1)[-1] if "." in d else ""
    if len(last) == 2 and last != "us":
        return False
    return False


def canonical_internal_url(url: str, domain: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != domain:
        return ""

    path = parsed.path or "/"
    lowered = path.lower()
    if any(lowered.endswith(ext) for ext in SKIP_EXTENSIONS):
        return ""

    canonical = parsed._replace(
        scheme=(parsed.scheme or "https").lower(),
        netloc=host,
        path=path.rstrip("/") or "/",
        params="",
        query="",
        fragment="",
    )
    return urlunparse(canonical)


def header_value(headers: Any, key: str) -> str:
    if isinstance(headers, dict):
        target = key.lower()
        for k, v in headers.items():
            if str(k).lower() == target:
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


def should_skip_link(href: str) -> bool:
    h = href.lower()
    return (
        not h
        or h.startswith("#")
        or h.startswith("mailto:")
        or h.startswith("tel:")
        or h.startswith("javascript:")
    )


def is_host_resolution_error(message: str) -> bool:
    m = (message or "").lower()
    return (
        "could not resolve host" in m
        or "name_not_resolved" in m
        or "bad hostname" in m
        or "url rejected: bad hostname" in m
    )


async def resolve_domain(domain: str, timeout_sec: float = 3.0) -> bool:
    if not domain:
        return False
    targets = [domain]
    if not domain.startswith("www."):
        targets.append(f"www.{domain}")
    for target in targets:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(socket.getaddrinfo, target, 443),
                timeout=timeout_sec,
            )
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def discover_internal_links(selector: Selector, base_url: str, domain: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for href_value in selector.css("a::attr(href)").getall():
        href = str(href_value).strip()
        if should_skip_link(href):
            continue
        absolute = urljoin(base_url, href)
        canonical = canonical_internal_url(absolute, domain)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        links.append(canonical)
    return links


def extract_page_kind(url: str) -> str:
    lowered = url.lower()
    if any(token in lowered for token in ("about", "company", "who-we-are", "our-story")):
        return "about"
    if any(token in lowered for token in ("product", "catalog", "linecard", "brands", "shop")):
        return "products"
    if any(token in lowered for token in ("contact", "support")):
        return "contact"
    return "home" if lowered.endswith("/") else "other"


def selector_to_page(selector: Selector, source_url: str, depth: int, fetch_mode: str) -> dict[str, Any]:
    title = clean_text(str(selector.css("title::text").get(default="")))[:300]
    description = clean_text(str(selector.css("meta[name='description']::attr(content)").get(default="")))[:800]
    text = clean_text(str(selector.get_all_text(separator=" ")))
    return {
        "url": str(selector.url or source_url),
        "source_url": source_url,
        "depth": depth,
        "page_kind": extract_page_kind(str(selector.url or source_url)),
        "status_code": int(getattr(selector, "status", 0) or 0),
        "fetch_mode": fetch_mode,
        "title": title,
        "description": description,
        "text_len": len(text),
        "text_excerpt": text[:9000],
        "has_search_box": int(len(selector.css("input[type='search']")) > 0),
    }


async def fetch_with_fallback(
    url: str,
    domain: str,
    args: argparse.Namespace,
    use_js: bool | None = None,
) -> FetchResult:
    if use_js is None:
        use_js = bool(args.js_fallback)

    attempts = [url]
    parsed = urlparse(url)
    if parsed.scheme == "https":
        attempts.append(url.replace("https://", "http://", 1))
    elif parsed.scheme == "http":
        attempts.append(url.replace("http://", "https://", 1))

    last_error = "unknown_error"
    for attempt in attempts:
        static_response: Selector | None = None
        static_error = ""
        try:
            static_response = await AsyncFetcher.get(
                attempt,
                follow_redirects=True,
                timeout=args.timeout,
                retries=args.retries,
                verify=args.verify_ssl,
                headers={"user-agent": USER_AGENT},
            )
            if is_html_selector_response(static_response):
                static_text = clean_text(str(static_response.get_all_text(separator=" ")))
                if not args.js_fallback or len(static_text) >= args.js_min_text_len:
                    return FetchResult(
                        final_url=str(static_response.url),
                        status_code=int(getattr(static_response, "status", 0) or 0),
                        selector=static_response,
                        fetch_mode="static",
                        error="",
                    )
                static_error = "thin_static"
            else:
                static_error = "non_html"
        except Exception as exc:  # noqa: BLE001
            static_error = str(exc)

        if is_host_resolution_error(static_error):
            last_error = static_error
            continue

        if use_js:
            try:
                dynamic_response = await DynamicFetcher.async_fetch(
                    attempt,
                    headless=True,
                    timeout=args.js_timeout_ms,
                    wait=args.js_wait_ms,
                    network_idle=args.js_network_idle,
                    disable_resources=args.js_disable_resources,
                    load_dom=True,
                    retries=args.retries,
                    retry_delay=1,
                    extra_headers={"user-agent": USER_AGENT},
                )
                if is_html_selector_response(dynamic_response):
                    return FetchResult(
                        final_url=str(dynamic_response.url),
                        status_code=int(getattr(dynamic_response, "status", 0) or 0),
                        selector=dynamic_response,
                        fetch_mode="dynamic",
                        error="",
                    )
                if static_response is not None and static_error != "non_html":
                    return FetchResult(
                        final_url=str(static_response.url),
                        status_code=int(getattr(static_response, "status", 0) or 0),
                        selector=static_response,
                        fetch_mode="static",
                        error=static_error,
                    )
                last_error = "non_html"
            except Exception as exc:  # noqa: BLE001
                if static_response is not None and static_error != "non_html":
                    return FetchResult(
                        final_url=str(static_response.url),
                        status_code=int(getattr(static_response, "status", 0) or 0),
                        selector=static_response,
                        fetch_mode="static",
                        error=static_error,
                    )
                last_error = str(exc) or static_error or "unknown_error"
        else:
            if static_response is not None and static_error != "non_html":
                return FetchResult(
                    final_url=str(static_response.url),
                    status_code=int(getattr(static_response, "status", 0) or 0),
                    selector=static_response,
                    fetch_mode="static",
                    error="",
                )
            last_error = static_error or "unknown_error"

    return FetchResult(final_url=url, status_code=0, selector=None, fetch_mode="none", error=last_error)


async def fetch_sitemap_urls(start_url: str, domain: str, args: argparse.Namespace) -> list[str]:
    sitemap_url = f"{urlparse(start_url).scheme}://{domain}/sitemap.xml"
    # Sitemap probing should stay lightweight; avoid dynamic browser fallback here.
    result = await fetch_with_fallback(sitemap_url, domain, args, use_js=False)
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
    found: list[str] = []
    for u in urls:
        canonical = canonical_internal_url(clean_text(u), domain)
        if canonical:
            found.append(canonical)
    return found[: args.max_pages_per_domain]


async def crawl_domain(row: dict[str, Any], args: argparse.Namespace, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    async with semaphore:
        domain = str(row.get("domain", "")).strip()
        start_url = normalize_url(str(row.get("normalized_url", "")).strip())
        status_label = str(row.get("Organization - Company Status", "")).strip()

        record: dict[str, Any] = {
            "domain": domain,
            "start_url": start_url,
            "status_label": status_label,
            "status_bucket": str(row.get("status_bucket", "")).strip(),
            "organization_name": str(row.get("Organization - Name", "")).strip(),
            "source_row": row.get("source_row", ""),
            "crawl_started_utc": datetime.now(timezone.utc).isoformat(),
            "pages": [],
            "errors": [],
        }
        if not domain or not start_url:
            record["errors"].append("missing_domain_or_start_url")
            record["crawl_finished_utc"] = datetime.now(timezone.utc).isoformat()
            return record

        if not args.no_dns_precheck:
            resolvable = await resolve_domain(domain)
            if not resolvable:
                record["errors"].append(f"{domain} :: dns_not_resolved")
                record["crawl_finished_utc"] = datetime.now(timezone.utc).isoformat()
                return record

        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        seen_urls: set[str] = set()
        seen_errors: set[str] = set()

        if args.include_sitemap:
            sitemap_urls = await fetch_sitemap_urls(start_url, domain, args)
            for su in sitemap_urls:
                queue.append((su, 1))

        while queue and len(record["pages"]) < args.max_pages_per_domain:
            url, depth = queue.popleft()
            canonical_url = canonical_internal_url(url, domain)
            if not canonical_url:
                continue
            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)

            fetch = await fetch_with_fallback(canonical_url, domain, args)
            if fetch.selector is None:
                error_msg = f"{canonical_url} :: {fetch.error}"
                if error_msg not in seen_errors and len(record["errors"]) < 60:
                    seen_errors.add(error_msg)
                    record["errors"].append(error_msg)
                continue

            page = selector_to_page(fetch.selector, canonical_url, depth, fetch.fetch_mode)
            record["pages"].append(page)

            if depth < args.max_depth:
                links = discover_internal_links(fetch.selector, page["url"], domain)
                for link in links:
                    if link not in seen_urls:
                        queue.append((link, depth + 1))

        record["crawl_finished_utc"] = datetime.now(timezone.utc).isoformat()
        return record


def write_domain_markdown(record: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    domain = record["domain"] or "unknown-domain"
    target = out_dir / f"{domain}.md"

    lines: list[str] = []
    lines.append(f"# Domain Profile: {domain}")
    lines.append(f"- domain: {domain}")
    lines.append(f"- organization_name: {record.get('organization_name', '')}")
    lines.append(f"- source_status_label: {record.get('status_label', '')}")
    lines.append(f"- source_status_bucket: {record.get('status_bucket', '')}")
    lines.append(f"- start_url: {record.get('start_url', '')}")
    lines.append(f"- crawl_started_utc: {record.get('crawl_started_utc', '')}")
    lines.append(f"- crawl_finished_utc: {record.get('crawl_finished_utc', '')}")
    lines.append(f"- pages_crawled: {len(record.get('pages', []))}")
    lines.append(f"- errors: {len(record.get('errors', []))}")
    lines.append("")
    lines.append("## Run Log")

    for page in record.get("pages", []):
        lines.append("")
        lines.append("=== PAGE START ===")
        lines.append(f"- url: {page.get('url', '')}")
        lines.append(f"- page_kind: {page.get('page_kind', '')}")
        lines.append(f"- depth: {page.get('depth', '')}")
        lines.append(f"- fetch_mode: {page.get('fetch_mode', '')}")
        lines.append(f"- status_code: {page.get('status_code', '')}")
        lines.append(f"- text_len: {page.get('text_len', '')}")
        lines.append(f"- has_search_box: {page.get('has_search_box', '')}")
        lines.append(f"- title: {page.get('title', '')}")
        lines.append(f"- description: {page.get('description', '')}")
        lines.append("")
        lines.append("```text")
        lines.append(page.get("text_excerpt", "")[:12000])
        lines.append("```")

    if record.get("errors"):
        lines.append("")
        lines.append("## Crawl Errors")
        for error in record["errors"][:200]:
            lines.append(f"- {error}")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def write_crawl_outputs(records: list[dict[str, Any]], args: argparse.Namespace) -> None:
    args.domain_crawl_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.domain_pages_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.crawl_summary_csv.parent.mkdir(parents=True, exist_ok=True)

    with args.domain_crawl_jsonl.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    with args.domain_pages_jsonl.open("w", encoding="utf-8") as handle:
        for record in records:
            for page in record.get("pages", []):
                row = {
                    "domain": record.get("domain", ""),
                    "organization_name": record.get("organization_name", ""),
                    "status_label": record.get("status_label", ""),
                    "status_bucket": record.get("status_bucket", ""),
                    **page,
                }
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    summary_rows: list[dict[str, Any]] = []
    for record in records:
        pages = record.get("pages", [])
        summary_rows.append(
            {
                "domain": record.get("domain", ""),
                "organization_name": record.get("organization_name", ""),
                "status_label": record.get("status_label", ""),
                "status_bucket": record.get("status_bucket", ""),
                "start_url": record.get("start_url", ""),
                "pages_crawled": len(pages),
                "dynamic_pages": int(sum(1 for p in pages if p.get("fetch_mode") == "dynamic")),
                "errors_count": len(record.get("errors", [])),
                "has_about_page": int(any(p.get("page_kind") == "about" for p in pages)),
                "has_products_page": int(any(p.get("page_kind") == "products" for p in pages)),
                "max_depth_observed": max([int(p.get("depth", 0)) for p in pages], default=0),
            }
        )
    pd.DataFrame(summary_rows).sort_values("domain").to_csv(args.crawl_summary_csv, index=False)

    for record in records:
        write_domain_markdown(record, args.profiles_dir)

    print(f"WROTE_DOMAIN_CRAWL: {args.domain_crawl_jsonl} rows={len(records)}")
    print(f"WROTE_PAGE_ROWS: {args.domain_pages_jsonl}")
    print(f"WROTE_CRAWL_SUMMARY: {args.crawl_summary_csv}")
    print(f"WROTE_PROFILES_DIR: {args.profiles_dir}")


async def run_crawl(args: argparse.Namespace) -> None:
    frame = pd.read_csv(args.input_sample).copy()
    if "domain" not in frame.columns:
        if "normalized_url" in frame.columns:
            frame["domain"] = frame["normalized_url"].astype("string").fillna("").map(domain_from_url)
        elif "Organization - Website" in frame.columns:
            frame["domain"] = (
                frame["Organization - Website"].astype("string").fillna("").map(normalize_url).map(domain_from_url)
            )
        else:
            frame["domain"] = ""
    before = len(frame)
    frame = frame[frame["domain"].astype("string").fillna("").map(is_us_target_domain)].copy()
    if args.max_sites > 0:
        frame = frame.head(args.max_sites).copy()
    print(f"[crawl] US-only filter kept {len(frame)}/{before} rows", flush=True)
    rows = frame.to_dict(orient="records")
    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = [crawl_domain(row=row, args=args, semaphore=semaphore) for row in rows]
    total = len(tasks)

    records: list[dict[str, Any]] = []
    for idx, coro in enumerate(asyncio.as_completed(tasks), start=1):
        rec = await coro
        records.append(rec)
        if args.progress_every > 0 and (idx % args.progress_every == 0 or idx == total):
            print(
                f"[crawl] {idx}/{total} done | domain={rec.get('domain','')} "
                f"pages={len(rec.get('pages', []))} errors={len(rec.get('errors', []))}",
                flush=True,
            )

    write_crawl_outputs(records, args)

    total_pages = sum(len(r.get("pages", [])) for r in records)
    with_pages = sum(1 for r in records if len(r.get("pages", [])) > 0)
    print(f"SITES_WITH_PAGES: {with_pages}/{len(records)}")
    print(f"TOTAL_PAGES: {total_pages}")


def build_domain_prompt_context(record: dict[str, Any], args: argparse.Namespace) -> str:
    pages = sorted(record.get("pages", []), key=lambda p: (int(p.get("depth", 99)), p.get("url", "")))
    pages = pages[: args.llm_max_pages]

    parts: list[str] = []
    total_chars = 0
    for page in pages:
        excerpt = str(page.get("text_excerpt", ""))[: args.llm_max_chars_per_page]
        block = (
            "=== PAGE START ===\n"
            f"url: {page.get('url', '')}\n"
            f"page_kind: {page.get('page_kind', '')}\n"
            f"title: {page.get('title', '')}\n"
            f"description: {page.get('description', '')}\n"
            f"text:\n{excerpt}\n"
        )
        if total_chars + len(block) > args.llm_max_total_chars:
            break
        parts.append(block)
        total_chars += len(block)

    return "\n".join(parts)


def load_env_vars_from_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            loaded[key] = value
    return loaded


def get_openrouter_api_key(args: argparse.Namespace) -> str:
    env_key = args.openrouter_api_key_env
    key = os.getenv(env_key, "").strip()
    if key:
        return key
    loaded = load_env_vars_from_file(args.env_file)
    key = loaded.get(env_key, "").strip()
    if key:
        os.environ[env_key] = key
    return key


def build_prompt_messages(
    variant: str,
    record: dict[str, Any],
    context: str,
) -> list[dict[str, str]]:
    domain = record.get("domain", "")
    org = record.get("organization_name", "")

    if variant == "binary_precision_v1":
        system_prompt = textwrap.dedent(
            """
            You are a strict B2B prospect scoring analyst.
            Goal: maximize precision for Possible class.
            Use only provided website evidence.
            If evidence is weak/conflicting, prefer Crap or Unknown (not Possible).
            Return JSON only.
            """
        ).strip()
        user_prompt = textwrap.dedent(
            f"""
            Domain: {domain}
            Organization: {org}

            Task:
            1) Decide predicted_label in ["Possible","Crap","Unknown"].
            2) Provide priority_score 0-100.
            3) Provide confidence 0-1.
            4) Extract signals object:
               - distributor_terms (bool)
               - manufacturer_terms (bool)
               - reseller_terms (bool)
               - catalog_linecard (bool)
               - inventory_stock (bool)
               - quote_rfq (bool)
               - search_filter (bool)
               - ecommerce_cart (bool)
               - authorized_franchised (bool)
               - service_only (bool)
            5) Extract other_fields object:
               - business_model (string)
               - target_role (string)
               - products_evidence (string)
               - commerce_capability (string)
            6) Evidence list: 3-8 short quotes, each with URL hint.

            Precision rubric for Possible:
            - Require at least 2 strong positive signals from:
              [distributor_terms, manufacturer_terms, catalog_linecard, inventory_stock, search_filter, authorized_franchised]
            - And no dominant negative posture (service-only with no catalog/product evidence).
            - If these conditions are not met, choose Crap or Unknown.

            Output JSON schema:
            {{
              "predicted_label": "Possible|Crap|Unknown",
              "priority_score": 0,
              "confidence": 0.0,
              "signals": {{ ... }},
              "other_fields": {{ ... }},
              "evidence": ["..."]
            }}

            Website content:
            {context}
            """
        ).strip()
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # baseline_multiclass_v1
    system_prompt = (
        "You are a strict B2B prospect classifier. "
        "Infer company type and sales potential from website pages only. "
        "Do not assume hidden data. "
        "Return JSON only."
    )
    user_prompt = textwrap.dedent(
        f"""
        Domain: {domain}
        Organization: {org}

        Determine:
        1) predicted_label: one of ["Possible","Crap","Well-served","Unqualified","Unknown"]
        2) priority_score: integer 0-100
        3) confidence: float 0-1
        4) signals: object with keys:
           - distributor_terms (bool)
           - manufacturer_terms (bool)
           - reseller_terms (bool)
           - catalog_linecard (bool)
           - inventory_stock (bool)
           - quote_rfq (bool)
           - search_filter (bool)
           - ecommerce_cart (bool)
           - authorized_franchised (bool)
           - service_only (bool)
        5) other_fields: object with inferred fields:
           - business_model (string)
           - target_role (string)
           - products_evidence (string)
           - commerce_capability (string)
        6) evidence: list of 3-8 short quoted snippets with URL hints.

        Output schema:
        {{
          "predicted_label": "...",
          "priority_score": 0,
          "confidence": 0.0,
          "signals": {{ ... }},
          "other_fields": {{ ... }},
          "evidence": ["..."]
        }}

        Website content:
        {context}
        """
    ).strip()
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def normalize_predicted_label(raw: str, variant: str) -> str:
    label = (raw or "").strip()
    if not label:
        return "Unknown"
    normalized = label.lower()
    if variant == "binary_precision_v1":
        if normalized == "possible":
            return "Possible"
        if normalized in {"crap", "not possible", "not_possible", "not-possible", "negative"}:
            return "Crap"
        return "Unknown"
    return label


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        return json.loads(snippet)
    raise ValueError("No valid JSON object found in LLM response")


def call_openrouter(model: str, api_key: str, messages: list[dict[str, str]], temperature: float) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url="https://openrouter.ai/api/v1/chat/completions",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://local.prospect-shortlisting",
            "X-Title": "prospect-shortlisting",
        },
    )
    context = ssl.create_default_context()
    with urlopen(request, context=context, timeout=120) as response:  # noqa: S310
        raw = response.read().decode("utf-8", errors="ignore")
    decoded = json.loads(raw)
    content = decoded["choices"][0]["message"]["content"]
    return extract_json_object(content)


def classify_record(
    record: dict[str, Any],
    args: argparse.Namespace,
    api_key: str,
    prompt_variant: str,
) -> dict[str, Any]:
    context = build_domain_prompt_context(record, args)
    if not context.strip():
        return {
            "domain": record.get("domain", ""),
            "organization_name": record.get("organization_name", ""),
            "true_status_label": record.get("status_label", ""),
            "prompt_variant": prompt_variant,
            "predicted_label": "Unknown",
            "priority_score": 0,
            "confidence": 0.0,
            "signals_json": "{}",
            "other_fields_json": "{}",
            "evidence_json": "[]",
            "llm_error": "empty_context",
        }
    messages = build_prompt_messages(
        variant=prompt_variant,
        record=record,
        context=context,
    )

    retries = 3
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            response = call_openrouter(
                model=args.llm_model,
                api_key=api_key,
                messages=messages,
                temperature=args.llm_temperature,
            )
            return {
                "domain": record.get("domain", ""),
                "organization_name": record.get("organization_name", ""),
                "true_status_label": record.get("status_label", ""),
                "prompt_variant": prompt_variant,
                "predicted_label": normalize_predicted_label(
                    str(response.get("predicted_label", "Unknown")),
                    prompt_variant,
                ),
                "priority_score": int(response.get("priority_score", 0) or 0),
                "confidence": float(response.get("confidence", 0.0) or 0.0),
                "signals_json": json.dumps(response.get("signals", {}), ensure_ascii=True),
                "other_fields_json": json.dumps(response.get("other_fields", {}), ensure_ascii=True),
                "evidence_json": json.dumps(response.get("evidence", []), ensure_ascii=True),
                "llm_error": "",
            }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < retries:
                time.sleep(1.5 * attempt)

    return {
        "domain": record.get("domain", ""),
        "organization_name": record.get("organization_name", ""),
        "true_status_label": record.get("status_label", ""),
        "prompt_variant": prompt_variant,
        "predicted_label": "Unknown",
        "priority_score": 0,
        "confidence": 0.0,
        "signals_json": "{}",
        "other_fields_json": "{}",
        "evidence_json": "[]",
        "llm_error": last_error or "unknown_llm_error",
    }


def load_domain_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def run_classification_variant(
    args: argparse.Namespace,
    prompt_variant: str,
    predictions_jsonl: Path,
    predictions_csv: Path,
) -> pd.DataFrame:
    api_key = get_openrouter_api_key(args)
    if not api_key:
        raise RuntimeError(
            f"Missing API key. Set {args.openrouter_api_key_env} or provide it in {args.env_file}."
        )

    records = load_domain_records(args.domain_crawl_jsonl)[: args.max_sites]
    predictions: list[dict[str, Any]] = []
    total = len(records)

    predictions_jsonl.parent.mkdir(parents=True, exist_ok=True)
    predictions_csv.parent.mkdir(parents=True, exist_ok=True)
    with predictions_jsonl.open("w", encoding="utf-8") as stream_out:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.llm_workers) as executor:
            futures = [
                executor.submit(classify_record, record, args, api_key, prompt_variant)
                for record in records
            ]
            for idx, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                pred = future.result()
                predictions.append(pred)
                stream_out.write(json.dumps(pred, ensure_ascii=True) + "\n")
                stream_out.flush()
                if args.progress_every > 0 and (idx % args.progress_every == 0 or idx == total):
                    err_text = str(pred.get("llm_error", "")).strip()
                    err_flag = "yes" if err_text else "no"
                    err_hint = f" reason={err_text[:120]}" if err_text else ""
                    print(
                        f"[classify:{prompt_variant}] {idx}/{total} done | "
                        f"domain={pred.get('domain','')} llm_error={err_flag}{err_hint}",
                        flush=True,
                    )

    pred_df = pd.DataFrame(predictions).sort_values("domain")
    pred_df.to_csv(predictions_csv, index=False)

    print(f"WROTE_PREDICTIONS_JSONL: {predictions_jsonl} rows={len(predictions)}")
    print(f"WROTE_PREDICTIONS_CSV: {predictions_csv}")
    print(
        f"LLM_ERRORS ({prompt_variant}): "
        f"{int((pred_df['llm_error'].astype('string') != '').sum())}"
    )
    return pred_df


def run_classification(args: argparse.Namespace) -> None:
    run_classification_variant(
        args=args,
        prompt_variant=args.prompt_variant,
        predictions_jsonl=args.predictions_jsonl,
        predictions_csv=args.predictions_csv,
    )


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate_predictions_frame(df: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame, pd.DataFrame]:
    status = df["true_status_label"].astype("string").fillna("")
    pred = df["predicted_label"].astype("string").fillna("Unknown")

    valid = status.ne("")
    valid_df = df[valid].copy()
    valid_status = status[valid]
    valid_pred = pred[valid]

    exact_accuracy = safe_div(float((valid_status == valid_pred).sum()), float(len(valid_df)))

    true_possible = valid_status.eq("Possible")
    pred_possible = valid_pred.eq("Possible")

    tp = int((true_possible & pred_possible).sum())
    fp = int((~true_possible & pred_possible).sum())
    fn = int((true_possible & ~pred_possible).sum())
    tn = int((~true_possible & ~pred_possible).sum())

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)

    confusion = pd.crosstab(valid_status, valid_pred)
    high_conf = valid_df[valid_df["confidence"].fillna(0) >= 0.75]
    high_conf_acc = safe_div(
        float((high_conf["true_status_label"] == high_conf["predicted_label"]).sum()),
        float(len(high_conf)),
    )

    metrics = {
        "evaluated_rows": float(len(valid_df)),
        "exact_accuracy": float(exact_accuracy),
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
        "tn": float(tn),
        "possible_precision": float(precision),
        "possible_recall": float(recall),
        "possible_f1": float(f1),
        "rows_confidence_ge_0_75": float(len(high_conf)),
        "exact_accuracy_confidence_ge_0_75": float(high_conf_acc),
        "llm_errors": float(
            int((df["llm_error"].astype("string").fillna("").str.strip().ne("")).sum())
            if "llm_error" in df.columns
            else 0
        ),
    }
    return metrics, confusion, valid_df


def write_evaluation_report(
    args: argparse.Namespace,
    predictions_file: Path,
    metrics: dict[str, float],
    confusion: pd.DataFrame,
    valid_df: pd.DataFrame,
    output_md: Path,
    title: str = "Blind LLM Evaluation",
) -> None:
    exact_accuracy = metrics["exact_accuracy"]
    tp = int(metrics["tp"])
    fp = int(metrics["fp"])
    fn = int(metrics["fn"])
    tn = int(metrics["tn"])
    precision = metrics["possible_precision"]
    recall = metrics["possible_recall"]
    f1 = metrics["possible_f1"]
    high_conf_rows = int(metrics["rows_confidence_ge_0_75"])
    high_conf_acc = metrics["exact_accuracy_confidence_ge_0_75"]

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- predictions_file: {predictions_file}")
    lines.append(f"- evaluated_rows: {int(metrics['evaluated_rows'])}")
    lines.append(f"- llm_errors: {int(metrics['llm_errors'])}")
    lines.append("")
    lines.append("## Exact Label Metrics")
    lines.append(f"- exact_accuracy: {exact_accuracy:.3f}")
    lines.append("")
    lines.append("## Binary Possible-vs-Other")
    lines.append(f"- tp: {tp}")
    lines.append(f"- fp: {fp}")
    lines.append(f"- fn: {fn}")
    lines.append(f"- tn: {tn}")
    lines.append(f"- precision: {precision:.3f}")
    lines.append(f"- recall: {recall:.3f}")
    lines.append(f"- f1: {f1:.3f}")
    lines.append("")
    lines.append("## Confidence Slice")
    lines.append(f"- rows_confidence_ge_0_75: {high_conf_rows}")
    lines.append(f"- exact_accuracy_confidence_ge_0_75: {high_conf_acc:.3f}")
    lines.append("")
    lines.append("## Confusion Matrix")
    lines.append("```text")
    lines.append(confusion.to_string())
    lines.append("```")
    lines.append("")

    top_errors = valid_df[valid_df["true_status_label"] != valid_df["predicted_label"]][
        ["domain", "true_status_label", "predicted_label", "priority_score", "confidence", "llm_error"]
    ].head(50)
    if not top_errors.empty:
        lines.append("## Sample Misclassifications")
        lines.append("```text")
        lines.append(top_errors.to_string(index=False))
        lines.append("```")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE_EVALUATION: {output_md}")


def run_evaluation(args: argparse.Namespace) -> None:
    df = pd.read_csv(args.predictions_csv).copy()
    metrics, confusion, valid_df = evaluate_predictions_frame(df)
    write_evaluation_report(
        args=args,
        predictions_file=args.predictions_csv,
        metrics=metrics,
        confusion=confusion,
        valid_df=valid_df,
        output_md=args.evaluation_md,
        title="Blind LLM Evaluation",
    )


def run_abtest(args: argparse.Namespace) -> None:
    variants = [v.strip() for v in args.ab_variants.split(",") if v.strip()]
    if not variants:
        raise ValueError("No prompt variants specified for abtest mode.")

    summary_rows: list[dict[str, Any]] = []
    for variant in variants:
        jsonl_path = args.ab_out_dir / f"llm_predictions_{variant}.jsonl"
        csv_path = args.ab_out_dir / f"llm_predictions_{variant}.csv"
        eval_md_path = args.ab_out_dir / f"llm_eval_{variant}.md"

        print(f"\n[abtest] Running variant: {variant}")
        pred_df = run_classification_variant(
            args=args,
            prompt_variant=variant,
            predictions_jsonl=jsonl_path,
            predictions_csv=csv_path,
        )
        metrics, confusion, valid_df = evaluate_predictions_frame(pred_df)
        write_evaluation_report(
            args=args,
            predictions_file=csv_path,
            metrics=metrics,
            confusion=confusion,
            valid_df=valid_df,
            output_md=eval_md_path,
            title=f"Blind LLM Evaluation - {variant}",
        )
        summary_rows.append(
            {
                "variant": variant,
                "evaluated_rows": int(metrics["evaluated_rows"]),
                "llm_errors": int(metrics["llm_errors"]),
                "exact_accuracy": metrics["exact_accuracy"],
                "possible_precision": metrics["possible_precision"],
                "possible_recall": metrics["possible_recall"],
                "possible_f1": metrics["possible_f1"],
                "rows_confidence_ge_0_75": int(metrics["rows_confidence_ge_0_75"]),
                "exact_accuracy_confidence_ge_0_75": metrics["exact_accuracy_confidence_ge_0_75"],
                "predictions_csv": str(csv_path),
                "evaluation_md": str(eval_md_path),
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["possible_f1", "possible_precision", "exact_accuracy"], ascending=False
    )
    args.ab_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(args.ab_summary_csv, index=False)

    lines: list[str] = []
    lines.append("# Prompt A/B Summary")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- domain_crawl_file: {args.domain_crawl_jsonl}")
    lines.append("")
    lines.append("## Ranking (higher is better)")
    lines.append("```text")
    lines.append(
        summary_df[
            [
                "variant",
                "possible_precision",
                "possible_recall",
                "possible_f1",
                "exact_accuracy",
                "llm_errors",
                "evaluated_rows",
            ]
        ].to_string(index=False, float_format=lambda x: f"{x:.3f}")
    )
    lines.append("```")
    lines.append("")
    lines.append(f"- summary_csv: {args.ab_summary_csv}")

    args.ab_summary_md.parent.mkdir(parents=True, exist_ok=True)
    args.ab_summary_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE_AB_SUMMARY_CSV: {args.ab_summary_csv}")
    print(f"WROTE_AB_SUMMARY_MD: {args.ab_summary_md}")


def main() -> None:
    scrapling_logger = logging.getLogger("scrapling")
    scrapling_logger.setLevel(logging.CRITICAL)
    scrapling_logger.propagate = False
    args = parse_args()
    if args.mode in {"crawl", "all"}:
        asyncio.run(run_crawl(args))
    if args.mode in {"classify", "all"}:
        run_classification(args)
    if args.mode in {"evaluate", "all"}:
        run_evaluation(args)
    if args.mode == "abtest":
        run_abtest(args)


if __name__ == "__main__":
    main()
