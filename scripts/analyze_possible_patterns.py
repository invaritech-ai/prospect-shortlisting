#!/usr/bin/env python3
"""Analyze common patterns among Possible-tagged websites."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "your",
    "you",
    "are",
    "our",
    "their",
    "has",
    "have",
    "will",
    "can",
    "about",
    "home",
    "contact",
    "services",
    "products",
    "product",
    "solutions",
    "company",
    "page",
    "more",
    "all",
    "new",
    "not",
    "was",
    "www",
    "com",
    "http",
    "https",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze common patterns in Possible-labeled sites.")
    parser.add_argument(
        "--signals",
        type=Path,
        default=Path("data/scraped_signals_300_js.csv"),
        help="Path to site-level signals CSV.",
    )
    parser.add_argument(
        "--pages",
        type=Path,
        default=Path("data/scraped_pages_300_js.jsonl"),
        help="Path to page-level JSONL.",
    )
    parser.add_argument(
        "--positive-label",
        default="Possible",
        help="Exact status label treated as positive.",
    )
    parser.add_argument(
        "--negative-label",
        default="Crap",
        help="Exact status label used for lift comparison.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="How many top terms/patterns to print.",
    )
    parser.add_argument(
        "--min-term-count",
        type=int,
        default=8,
        help="Minimum positive-term count to consider for lift.",
    )
    return parser.parse_args()


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())
    return [t for t in tokens if t not in STOPWORDS and not t.isdigit()]


def compute_term_counter(page_rows: list[dict]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in page_rows:
        excerpt = str(row.get("text_excerpt", ""))
        counter.update(tokenize(excerpt))
    return counter


def load_pages(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> None:
    args = parse_args()
    signals = pd.read_csv(args.signals)

    pos_mask = signals["status_label"].astype("string").eq(args.positive_label)
    neg_mask = signals["status_label"].astype("string").eq(args.negative_label)
    pos = signals[pos_mask].copy()
    neg = signals[neg_mask].copy()

    print(f"POSITIVE_LABEL: {args.positive_label} rows={len(pos)}")
    print(f"NEGATIVE_LABEL: {args.negative_label} rows={len(neg)}")

    if pos.empty:
        print("No positive rows found.")
        return

    print("\nSTRUCTURAL PATTERNS (positive cohort):")
    structural_cols = [
        "fetched_pages",
        "has_about_page",
        "has_products_page",
        "has_search_box_any_page",
        "dynamic_pages",
        "combined_text_len",
    ]
    for col in structural_cols:
        if col in pos.columns:
            print(f"- {col}: mean={pos[col].mean():.3f}")

    signal_cols = [c for c in pos.columns if c.startswith("signal_")]
    print("\nSIGNAL PREVALENCE IN POSITIVE COHORT:")
    for col in signal_cols:
        prevalence = float((pos[col] > 0).mean())
        avg_hits = float(pos[col].mean())
        print(f"- {col}: prevalence={format_pct(prevalence)} avg_hits={avg_hits:.3f}")

    if not neg.empty:
        print("\nTOP DIFFERENTIATORS VS NEGATIVE (by prevalence delta):")
        deltas: list[tuple[str, float, float, float]] = []
        for col in signal_cols + ["has_products_page", "has_about_page", "has_search_box_any_page"]:
            if col not in neg.columns:
                continue
            p = float((pos[col] > 0).mean()) if col.startswith("signal_") else float(pos[col].mean())
            n = float((neg[col] > 0).mean()) if col.startswith("signal_") else float(neg[col].mean())
            deltas.append((col, p, n, p - n))
        deltas.sort(key=lambda item: abs(item[3]), reverse=True)
        for col, p, n, d in deltas[: args.top_n]:
            print(f"- {col}: positive={format_pct(p)} negative={format_pct(n)} delta={d * 100:.1f}pp")

    pages = load_pages(args.pages)
    domain_to_status = {
        str(row["domain"]): str(row["status_label"])
        for row in signals[["domain", "status_label"]].to_dict(orient="records")
    }

    pos_pages = [r for r in pages if domain_to_status.get(str(r.get("domain", ""))) == args.positive_label]
    neg_pages = [r for r in pages if domain_to_status.get(str(r.get("domain", ""))) == args.negative_label]
    print(f"\nPAGE ROWS: positive={len(pos_pages)} negative={len(neg_pages)}")

    pos_terms = compute_term_counter(pos_pages)
    neg_terms = compute_term_counter(neg_pages)
    print("\nMOST COMMON TERMS IN POSITIVE PAGES:")
    for term, cnt in pos_terms.most_common(args.top_n):
        print(f"- {term}: {cnt}")

    if neg_pages:
        print("\nTERMS WITH HIGHEST LIFT VS NEGATIVE:")
        total_pos = sum(pos_terms.values()) or 1
        total_neg = sum(neg_terms.values()) or 1
        lifted: list[tuple[str, int, int, float]] = []
        for term, p_cnt in pos_terms.items():
            if p_cnt < args.min_term_count:
                continue
            n_cnt = neg_terms.get(term, 0)
            p_rate = p_cnt / total_pos
            n_rate = (n_cnt + 1) / (total_neg + 1)
            lift = p_rate / n_rate
            lifted.append((term, p_cnt, n_cnt, lift))
        lifted.sort(key=lambda row: row[3], reverse=True)
        for term, p_cnt, n_cnt, lift in lifted[: args.top_n]:
            print(f"- {term}: pos={p_cnt} neg={n_cnt} lift={lift:.2f}x")

    print("\nTOP POSITIVE DOMAINS BY SIGNAL DENSITY:")
    ranked = pos.copy()
    ranked["signal_density"] = ranked[signal_cols].sum(axis=1)
    cols = [
        "domain",
        "signal_density",
        "has_products_page",
        "has_about_page",
        "has_search_box_any_page",
        "combined_text_len",
    ]
    for row in ranked.sort_values("signal_density", ascending=False).head(args.top_n)[cols].to_dict(
        orient="records"
    ):
        print(
            "- {domain}: density={signal_density:.0f}, products={has_products_page}, about={has_about_page}, "
            "search={has_search_box_any_page}, text_len={combined_text_len:.0f}".format(**row)
        )


if __name__ == "__main__":
    main()
