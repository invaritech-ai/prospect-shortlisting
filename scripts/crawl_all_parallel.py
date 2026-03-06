#!/usr/bin/env python3
"""Build full website sample and run parallel crawl workers."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


STATUS_COL = "Organization - Company Status"
WEBSITE_COL = "Organization - Website"
NAME_COL = "Organization - Name"
TYPE_COL = "Organization - TYPE"
LABELS_COL = "Organization - Labels"
NOTE_COL = "Organization - company-wide note"
PEOPLE_COL = "Organization - People"
LINKEDIN_COL = "Organization - Company LI"
REQUIRED_COLUMNS = [
    STATUS_COL,
    WEBSITE_COL,
    NAME_COL,
    TYPE_COL,
    LABELS_COL,
    NOTE_COL,
    PEOPLE_COL,
    LINKEDIN_COL,
]
US_ALLOWED_SUFFIXES = (
    ".com",
    ".net",
    ".org",
    ".us",
    ".edu",
    ".gov",
    ".mil",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel crawler launcher for all websites in source list.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/organizations-16279854-126.xlsx"),
        help="Source .xlsx/.csv with organization list.",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Excel sheet name/index (default: first sheet).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel crawl workers (processes).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/full_crawl_parallel"),
        help="Output directory for shards and crawl artifacts.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only build sample + shard CSVs, do not launch crawlers.",
    )
    parser.add_argument(
        "--source-cache-csv",
        type=Path,
        default=None,
        help="Optional cache CSV path for source rows (speeds reruns).",
    )

    # Pass-through crawl settings.
    parser.add_argument("--concurrency", type=int, default=6, help="Per-worker crawl concurrency.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per request.")
    parser.add_argument("--max-pages-per-domain", type=int, default=40, help="Max pages per domain.")
    parser.add_argument("--max-depth", type=int, default=2, help="Max link depth.")
    parser.add_argument("--js-fallback", action="store_true", help="Enable JS fallback.")
    parser.add_argument("--js-min-text-len", type=int, default=250, help="Trigger JS fallback below this text len.")
    parser.add_argument("--js-wait-ms", type=int, default=300, help="JS wait milliseconds.")
    parser.add_argument("--include-sitemap", action="store_true", help="Seed with sitemap links.")
    parser.add_argument("--progress-every", type=int, default=25, help="Progress print interval.")
    parser.add_argument("--no-dns-precheck", action="store_true", help="Disable DNS precheck.")
    return parser.parse_args()


def load_dataframe(path: Path, sheet: str | None, cache_csv: Path | None) -> pd.DataFrame:
    if cache_csv is not None and cache_csv.exists():
        print(f"[source] loading cache: {cache_csv}")
        return pd.read_csv(cache_csv)

    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        print(f"[source] reading Excel (first run can be slow): {path}")
        workbook = pd.ExcelFile(path)
        selected = sheet if sheet is not None else workbook.sheet_names[0]
        df = pd.read_excel(path, sheet_name=selected, usecols=lambda c: c in REQUIRED_COLUMNS)
    elif ext == ".csv":
        df = pd.read_csv(path, usecols=lambda c: c in REQUIRED_COLUMNS)
    else:
        raise ValueError(f"Unsupported source extension: {ext}")

    if cache_csv is not None:
        cache_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_csv, index=False)
        print(f"[source] wrote cache: {cache_csv}")
    return df


def split_url_candidates(raw: object) -> list[str]:
    if pd.isna(raw):
        return []
    value = str(raw).strip()
    if not value:
        return []
    chunks = [c.strip() for c in value.replace("\n", " ").split(",")]
    out: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        for token in chunk.split():
            t = token.strip()
            if not t:
                continue
            if "://" not in t:
                t = f"https://{t}"
            out.append(t)
    return out


def is_reasonable_host(netloc: str) -> bool:
    host = (netloc or "").strip().lower()
    if not host:
        return False
    host = host.split("@")[-1].split(":")[0]
    if not host:
        return False
    if any(ch in host for ch in (",", "/", " ")):
        return False
    if "." not in host:
        return False
    return True


def normalize_url(raw: object) -> str:
    for candidate in split_url_candidates(raw):
        parsed = urlparse(candidate)
        if not parsed.netloc or not is_reasonable_host(parsed.netloc):
            continue
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        scheme = (parsed.scheme or "https").lower()
        path = parsed.path or "/"
        return f"{scheme}://{netloc}{path.rstrip('/') or '/'}"
    return ""


def domain_from_url(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url).netloc.lower()
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


def bucket_status(value: object) -> str:
    if pd.isna(value):
        return "unlabeled"
    status = str(value).strip()
    if not status:
        return "unlabeled"
    low = status.lower()
    if low == "possible":
        return "possible"
    if low == "crap":
        return "crap"
    if low == "well-served":
        return "well_served"
    if low == "unqualified":
        return "unqualified"
    return "other_labeled"


def build_all_sample(source: pd.DataFrame, output_csv: Path) -> pd.DataFrame:
    df = source.copy()
    df["normalized_url"] = df[WEBSITE_COL].map(normalize_url)
    df = df[df["normalized_url"].ne("")].copy()
    df["domain"] = df["normalized_url"].map(domain_from_url)
    df = df[df["domain"].map(is_us_target_domain)].copy()
    df = df[df["domain"].ne("")].copy()
    df["status_bucket"] = df[STATUS_COL].map(bucket_status)
    df["source_row"] = df.index

    # Keep richest row per domain.
    richness = (
        df[TYPE_COL].astype("string").fillna("").str.strip().ne("").astype(int)
        + df[LABELS_COL].astype("string").fillna("").str.strip().ne("").astype(int)
        + df[NOTE_COL].astype("string").fillna("").str.strip().ne("").astype(int)
        + df[STATUS_COL].astype("string").fillna("").str.strip().ne("").astype(int)
    )
    df["richness"] = richness
    df = df.sort_values(["domain", "richness"], ascending=[True, False]).drop_duplicates("domain", keep="first")

    cols = [
        "source_row",
        NAME_COL,
        WEBSITE_COL,
        "normalized_url",
        "domain",
        STATUS_COL,
        TYPE_COL,
        LABELS_COL,
        NOTE_COL,
        PEOPLE_COL,
        LINKEDIN_COL,
        "status_bucket",
    ]
    out = df[cols].sort_values("domain").reset_index(drop=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False)
    return out


def split_shards(df: pd.DataFrame, workers: int, shard_dir: Path) -> list[Path]:
    shard_dir.mkdir(parents=True, exist_ok=True)
    rows = len(df)
    if rows == 0:
        return []
    per = math.ceil(rows / max(workers, 1))
    paths: list[Path] = []
    for i in range(workers):
        start = i * per
        end = min(rows, (i + 1) * per)
        if start >= end:
            break
        shard = df.iloc[start:end].copy()
        path = shard_dir / f"shard_{i:02d}.csv"
        shard.to_csv(path, index=False)
        paths.append(path)
    return paths


def launch_workers(args: argparse.Namespace, shard_paths: list[Path]) -> int:
    processes: list[tuple[int, subprocess.Popen[str]]] = []
    for idx, shard in enumerate(shard_paths):
        out_prefix = args.out_dir / "workers" / f"worker_{idx:02d}"
        out_prefix.mkdir(parents=True, exist_ok=True)

        cmd = [
            "uv",
            "run",
            "python",
            "scripts/run_blind_llm_eval.py",
            "--mode",
            "crawl",
            "--input-sample",
            str(shard),
            "--max-sites",
            "999999",
            "--concurrency",
            str(args.concurrency),
            "--timeout",
            str(args.timeout),
            "--retries",
            str(args.retries),
            "--max-pages-per-domain",
            str(args.max_pages_per_domain),
            "--max-depth",
            str(args.max_depth),
            "--js-min-text-len",
            str(args.js_min_text_len),
            "--js-wait-ms",
            str(args.js_wait_ms),
            "--progress-every",
            str(args.progress_every),
            "--domain-crawl-jsonl",
            str(out_prefix / "domain_crawl.jsonl"),
            "--domain-pages-jsonl",
            str(out_prefix / "domain_pages.jsonl"),
            "--crawl-summary-csv",
            str(out_prefix / "crawl_summary.csv"),
            "--profiles-dir",
            str(out_prefix / "profiles"),
        ]
        if args.js_fallback:
            cmd.append("--js-fallback")
        if args.include_sitemap:
            cmd.append("--include-sitemap")
        if args.no_dns_precheck:
            cmd.append("--no-dns-precheck")

        print(f"[launch] worker={idx} shard={shard} -> {out_prefix}", flush=True)
        proc = subprocess.Popen(cmd)  # noqa: S603
        processes.append((idx, proc))

    rc = 0
    for idx, proc in processes:
        code = proc.wait()
        print(f"[done] worker={idx} exit_code={code}", flush=True)
        if code != 0:
            rc = code
    return rc


def merge_worker_outputs(out_dir: Path, merged_dir: Path) -> None:
    merged_dir.mkdir(parents=True, exist_ok=True)
    worker_dirs = sorted((out_dir / "workers").glob("worker_*"))

    merged_crawl = merged_dir / "domain_crawl_merged.jsonl"
    merged_pages = merged_dir / "domain_pages_merged.jsonl"
    merged_summary = merged_dir / "crawl_summary_merged.csv"

    with merged_crawl.open("w", encoding="utf-8") as hc, merged_pages.open("w", encoding="utf-8") as hp:
        summaries = []
        for wd in worker_dirs:
            c = wd / "domain_crawl.jsonl"
            p = wd / "domain_pages.jsonl"
            s = wd / "crawl_summary.csv"
            if c.exists():
                hc.write(c.read_text(encoding="utf-8"))
            if p.exists():
                hp.write(p.read_text(encoding="utf-8"))
            if s.exists():
                summaries.append(pd.read_csv(s))
        if summaries:
            pd.concat(summaries, ignore_index=True).to_csv(merged_summary, index=False)

    print(f"[merge] {merged_crawl}")
    print(f"[merge] {merged_pages}")
    print(f"[merge] {merged_summary}")


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cache_csv = args.source_cache_csv or (args.out_dir / "source_cache.csv")

    source_df = load_dataframe(args.source, args.sheet, cache_csv)
    all_sample_csv = args.out_dir / "website_sample_all.csv"
    all_df = build_all_sample(source_df, all_sample_csv)
    print(f"[sample] wrote={all_sample_csv} rows={len(all_df)} (US-only)")

    shard_dir = args.out_dir / "shards"
    shard_paths = split_shards(all_df, args.workers, shard_dir)
    print(f"[shards] count={len(shard_paths)} dir={shard_dir}")
    for i, path in enumerate(shard_paths):
        count = len(pd.read_csv(path))
        print(f"[shard] {i:02d} rows={count} file={path}")

    if args.prepare_only:
        return

    rc = launch_workers(args, shard_paths)
    merge_worker_outputs(args.out_dir, args.out_dir / "merged")
    if rc != 0:
        sys.exit(rc)


if __name__ == "__main__":
    main()
