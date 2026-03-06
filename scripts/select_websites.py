#!/usr/bin/env python3
"""Select a stratified sample of company websites from the source spreadsheet."""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Build a website sample for scraping.")
    parser.add_argument("input_path", type=Path, help="Path to source .xlsx/.csv file.")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("data/website_sample_250.csv"),
        help="Where to write sampled rows.",
    )
    parser.add_argument("--target", type=int, default=250, help="Target number of websites.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--sheet",
        default=None,
        help="Excel sheet name/index (defaults to first sheet).",
    )
    return parser.parse_args()


def load_dataframe(path: Path, sheet: str | None) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        workbook = pd.ExcelFile(path)
        chosen_sheet = sheet if sheet is not None else workbook.sheet_names[0]
        return pd.read_excel(path, sheet_name=chosen_sheet)
    if ext == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file extension: {ext}")


def normalize_url(value: object) -> str:
    if pd.isna(value):
        return ""
    url = str(value).strip()
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    path = parsed.path.rstrip("/")
    return f"{scheme}://{netloc}{path}"


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


def bucket_status(value: object) -> str:
    if pd.isna(value):
        return "unlabeled"
    status = str(value).strip()
    if not status:
        return "unlabeled"
    status_lower = status.lower()
    if status_lower == "possible":
        return "possible"
    if status_lower == "crap":
        return "crap"
    if status_lower == "well-served":
        return "well_served"
    if status_lower == "unqualified":
        return "unqualified"
    return "other_labeled"


def desired_quota(target: int) -> dict[str, int]:
    return {
        "possible": int(target * 0.32),
        "crap": int(target * 0.32),
        "well_served": int(target * 0.08),
        "unqualified": int(target * 0.08),
        "other_labeled": int(target * 0.05),
        "unlabeled": target
        - (
            int(target * 0.32)
            + int(target * 0.32)
            + int(target * 0.08)
            + int(target * 0.08)
            + int(target * 0.05)
        ),
    }


def sample_bucket(
    frame: pd.DataFrame,
    count: int,
    seed: int,
    used_domains: set[str],
) -> pd.DataFrame:
    if count <= 0 or frame.empty:
        return frame.iloc[0:0]
    shuffled = frame.sample(frac=1.0, random_state=seed)
    rows = []
    for _, row in shuffled.iterrows():
        domain = row["domain"]
        if not domain or domain in used_domains:
            continue
        rows.append(row)
        used_domains.add(domain)
        if len(rows) >= count:
            break
    if not rows:
        return frame.iloc[0:0]
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    source = load_dataframe(args.input_path, args.sheet).copy()

    source["normalized_url"] = source[WEBSITE_COL].map(normalize_url)
    source = source[source["normalized_url"].ne("")].copy()
    source["domain"] = source["normalized_url"].map(domain_from_url)
    source = source[source["domain"].map(is_us_target_domain)].copy()
    source["status_bucket"] = source[STATUS_COL].map(bucket_status)
    source["source_row"] = source.index

    # Prefer rows with richer metadata when duplicate domains exist.
    metadata_score = (
        source[TYPE_COL].astype("string").fillna("").str.strip().ne("").astype(int)
        + source[LABELS_COL].astype("string").fillna("").str.strip().ne("").astype(int)
        + source[NOTE_COL].astype("string").fillna("").str.strip().ne("").astype(int)
        + source[STATUS_COL].astype("string").fillna("").str.strip().ne("").astype(int)
    )
    source["metadata_score"] = metadata_score
    source = (
        source.sort_values(["domain", "metadata_score"], ascending=[True, False])
        .drop_duplicates(subset=["domain"], keep="first")
        .copy()
    )

    quotas = desired_quota(args.target)
    selected_parts: list[pd.DataFrame] = []
    used_domains: set[str] = set()

    for idx, bucket in enumerate(
        ["possible", "crap", "well_served", "unqualified", "other_labeled", "unlabeled"]
    ):
        bucket_rows = source[source["status_bucket"].eq(bucket)]
        part = sample_bucket(bucket_rows, quotas[bucket], args.seed + idx, used_domains)
        selected_parts.append(part)

    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else source.iloc[0:0]

    if len(selected) < args.target:
        remaining = source[~source["domain"].isin(used_domains)]
        fill = sample_bucket(
            remaining,
            args.target - len(selected),
            args.seed + 99,
            used_domains,
        )
        selected = pd.concat([selected, fill], ignore_index=True)

    out_cols = [
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
    selected = selected[out_cols].sort_values("domain").reset_index(drop=True)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(args.output_path, index=False)

    print(f"WROTE: {args.output_path}")
    print(f"SELECTED_ROWS: {len(selected)}")
    print("TARGET: US-only domains")
    print("BUCKET_COUNTS:")
    counts = selected["status_bucket"].value_counts()
    for bucket, count in counts.items():
        print(f"- {bucket}: {int(count)}")


if __name__ == "__main__":
    main()
