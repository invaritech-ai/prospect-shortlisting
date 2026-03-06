#!/usr/bin/env python3
"""Check whether Possible-associated signals leak into other classes."""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze signal overlap across classes.")
    parser.add_argument(
        "--signals",
        type=Path,
        default=Path("data/scraped_signals_300_js.csv"),
        help="Path to site-level signals CSV.",
    )
    parser.add_argument(
        "--positive-label",
        default="Possible",
        help="Exact label considered positive.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of rows to print for ranked sections.",
    )
    parser.add_argument(
        "--min-support",
        type=int,
        default=8,
        help="Minimum support for combo analysis.",
    )
    return parser.parse_args()


def bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col.startswith("signal_"):
        return df[col].fillna(0).astype(float) > 0
    return df[col].fillna(0).astype(float) > 0


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.signals)
    status = df["status_label"].astype("string")

    positive_mask = status.eq(args.positive_label)
    non_positive_mask = ~positive_mask

    print(f"TOTAL_ROWS: {len(df)}")
    print(f"POSITIVE_ROWS ({args.positive_label}): {int(positive_mask.sum())}")
    print(f"NON_POSITIVE_ROWS: {int(non_positive_mask.sum())}")
    print("\nCLASS_COUNTS:")
    print(status.value_counts(dropna=False).to_string())

    candidate_features = [c for c in df.columns if c.startswith("signal_")] + [
        "has_products_page",
        "has_about_page",
        "has_search_box_any_page",
    ]
    candidate_features = [c for c in candidate_features if c in df.columns]

    print("\nFEATURE LEAKAGE (single features):")
    rows: list[dict] = []
    for col in candidate_features:
        active = bool_col(df, col)
        pos_active = int((positive_mask & active).sum())
        non_pos_active = int((non_positive_mask & active).sum())
        total_active = int(active.sum())

        pos_rate = pos_active / max(int(positive_mask.sum()), 1)
        non_pos_rate = non_pos_active / max(int(non_positive_mask.sum()), 1)
        precision = pos_active / max(total_active, 1)

        rows.append(
            {
                "feature": col,
                "support_total": total_active,
                "pos_active": pos_active,
                "non_pos_active": non_pos_active,
                "pos_rate": pos_rate,
                "non_pos_rate": non_pos_rate,
                "precision_if_used_alone": precision,
            }
        )

    summary = pd.DataFrame(rows).sort_values(
        ["precision_if_used_alone", "support_total"], ascending=[False, False]
    )
    print(summary.head(args.top_n).to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    leaked = summary[summary["non_pos_active"] > 0]
    print(f"\nFEATURES WITH LEAKAGE INTO NON-POSITIVE: {len(leaked)}/{len(summary)}")
    if len(leaked) > 0:
        print("Most leaked by non-positive count:")
        print(
            leaked.sort_values("non_pos_active", ascending=False)
            .head(args.top_n)[["feature", "non_pos_active", "pos_active", "precision_if_used_alone"]]
            .to_string(index=False, float_format=lambda x: f"{x:.3f}")
        )

    # Show class-level prevalence for the strongest signals by precision/support.
    top_features = summary.head(min(8, len(summary)))["feature"].tolist()
    classes = sorted(status.dropna().unique().tolist())
    print("\nCLASS PREVALENCE FOR TOP FEATURES:")
    for feature in top_features:
        active = bool_col(df, feature)
        parts: list[str] = []
        for cls in classes:
            cls_mask = status.eq(cls)
            rate = float((active & cls_mask).sum()) / max(int(cls_mask.sum()), 1)
            parts.append(f"{cls}={rate * 100:.1f}%")
        print(f"- {feature}: " + " | ".join(parts))

    # Combo analysis to find less leaky signatures.
    combo_pool = [
        c
        for c in [
            "signal_distributor_hits",
            "signal_manufacturer_hits",
            "signal_catalog_hits",
            "signal_reseller_hits",
            "signal_search_hits",
            "signal_authorization_hits",
            "has_products_page",
            "has_about_page",
        ]
        if c in df.columns
    ]

    combo_rows: list[dict] = []
    for r in (2, 3):
        for combo in combinations(combo_pool, r):
            mask = pd.Series(True, index=df.index)
            for col in combo:
                mask = mask & bool_col(df, col)
            support = int(mask.sum())
            if support < args.min_support:
                continue
            pos_support = int((mask & positive_mask).sum())
            non_pos_support = int((mask & non_positive_mask).sum())
            precision = pos_support / max(support, 1)
            combo_rows.append(
                {
                    "combo": " + ".join(combo),
                    "support_total": support,
                    "pos_support": pos_support,
                    "non_pos_support": non_pos_support,
                    "precision": precision,
                }
            )

    print("\nTOP FEATURE COMBINATIONS (lower leakage):")
    if combo_rows:
        combo_df = pd.DataFrame(combo_rows).sort_values(
            ["precision", "support_total"], ascending=[False, False]
        )
        print(combo_df.head(args.top_n).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    else:
        print("No combos met support threshold.")


if __name__ == "__main__":
    main()
