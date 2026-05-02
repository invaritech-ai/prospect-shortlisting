#!/usr/bin/env python3
"""One row per domain: keep the most senior title-matched contact.

Reads a CSV with columns like those from ``get_title_match_rules.py`` (must include
``domain``, ``title``, ``source_provider``). Writes a CSV with the same columns,
deduped so each ``domain`` appears once.

Seniority is heuristic: C-suite / founder / owner / GM → VP → director / head →
manager → senior IC → unknown. See ``seniority_score`` below.

Tie-breaks (same domain, same score): prefer Apollo over Snov, then longer title
string, then lexicographic ``id`` for stability.

Usage::

  uv run python scripts/clean_up_for_apollo.py -i out.csv -o apollo_one_per_domain.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.title_match_service import normalize_title


def seniority_score(title: str | float | None) -> int:
    """Higher = more senior. Uses the same normalization as title matching."""
    if title is None or (isinstance(title, float) and pd.isna(title)):
        t = ""
    else:
        t = normalize_title(str(title))
    if not t.strip():
        return 0

    # VP / EVP / SVP before generic "president"
    if re.search(r"\b(svp|evp|avp|vice president)\b", t) or re.search(
        r"(?<![a-z])vp(?![a-z])", t
    ):
        return 80

    # C-suite, founder, owner, president (not vice president), GM
    if re.search(
        r"\b(chief|founder|owner|president|general manager)\b",
        t,
    ) and "vice president" not in t:
        return 100
    if re.search(
        r"\b(ceo|cto|cmo|cfo|coo|cdo|cio|cro|cpo|cbo|chro)\b",
        t,
    ):
        return 100

    if "chief" in t:
        return 100

    if re.search(r"\b(director|head of)\b", t):
        return 60

    if re.search(r"\bmanager\b", t):
        return 40

    if re.search(r"\b(senior|lead|principal|staff)\b", t):
        return 20

    # Title matched your rules but no known seniority token — rank above empty
    return 10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dedupe CSV to one contact per domain (most senior).")
    p.add_argument("-i", "--input", type=Path, required=True, help="Input CSV path.")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV (default: <input_stem>_one_per_domain.csv)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1

    out = args.output
    if out is None:
        out = args.input.with_name(f"{args.input.stem}_one_per_domain{args.input.suffix}")

    df = pd.read_csv(args.input)
    required = {"domain", "title", "source_provider"}
    missing = required - set(df.columns)
    if missing:
        print(f"error: CSV missing columns: {sorted(missing)}", file=sys.stderr)
        return 1

    df = df.copy()
    df["_score"] = df["title"].map(seniority_score)
    df["_prov"] = df["source_provider"].map(lambda x: 1 if str(x).lower() == "apollo" else 0)
    df["_tlen"] = df["title"].fillna("").astype(str).str.len()
    if "id" in df.columns:
        df["_tie"] = df["id"].astype(str)
    elif "provider_person_id" in df.columns:
        df["_tie"] = df["provider_person_id"].astype(str)
    else:
        df["_tie"] = pd.RangeIndex(len(df)).astype(str)

    df = df.sort_values(
        ["domain", "_score", "_prov", "_tlen", "_tie"],
        ascending=[True, False, False, False, True],
        kind="mergesort",
    )
    df = df.drop_duplicates(subset=["domain"], keep="first")
    df = df.drop(columns=["_score", "_prov", "_tlen", "_tie"])

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} rows (one per domain) -> {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
