#!/usr/bin/env python3
"""Print focused samples from a tabular dataset for rapid label discovery."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_COLUMNS = [
    "Organization - Name",
    "Organization - Website",
    "Organization - Company Status",
    "Organization - TYPE",
    "Organization - Labels",
    "Organization - company-wide note",
    "Organization - People",
    "Organization - LinkedIn profile",
    "Organization - Company LI",
]

LABEL_SIGNAL_COLUMNS = [
    "Organization - Company Status",
    "Organization - TYPE",
    "Organization - Labels",
    "Organization - company-wide note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show useful dataset samples.")
    parser.add_argument("path", type=Path, help="Path to .xlsx/.csv dataset.")
    parser.add_argument("--rows", type=int, default=12, help="Rows per sample block.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling.")
    parser.add_argument(
        "--sheet",
        default=None,
        help="Excel sheet name/index (defaults to first sheet).",
    )
    parser.add_argument(
        "--per-value",
        type=int,
        default=3,
        help="Rows to show for each top value in status/type/labels.",
    )
    parser.add_argument(
        "--top-values",
        type=int,
        default=6,
        help="How many frequent values to include per field.",
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
    raise ValueError(f"Unsupported extension for this script: {ext}")


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [col for col in columns if col in df.columns]


def non_empty_mask(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip().ne("")


def print_block(title: str, frame: pd.DataFrame, rows: int) -> None:
    print(f"\n=== {title} ({len(frame)} candidate rows) ===")
    if frame.empty:
        print("No rows found.")
        return
    take = min(rows, len(frame))
    print(frame.head(take).to_string(index=False))


def print_value_examples(
    df: pd.DataFrame,
    column: str,
    rows_per_value: int,
    top_values: int,
    display_columns: list[str],
) -> None:
    if column not in df.columns:
        return
    cleaned = df[column].astype("string").fillna("").str.strip()
    counts = cleaned[cleaned.ne("")].value_counts().head(top_values)
    print(f"\n=== EXAMPLES BY {column} ===")
    if counts.empty:
        print("No non-empty values found.")
        return
    for value, count in counts.items():
        subset = df[cleaned.eq(value)][display_columns].head(rows_per_value)
        print(f"\n[{value}] count={count}")
        print(subset.to_string(index=False))


def main() -> None:
    args = parse_args()
    df = load_dataframe(args.path, args.sheet)
    cols = ensure_columns(df, DEFAULT_COLUMNS)
    dfv = df[cols].copy()

    print(f"FILE: {args.path}")
    print(f"SHAPE: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"DISPLAY COLUMNS: {cols}")

    random_rows = dfv.sample(n=min(args.rows, len(dfv)), random_state=args.seed)
    print_block("RANDOM SAMPLE", random_rows, args.rows)

    signal_cols = ensure_columns(dfv, LABEL_SIGNAL_COLUMNS)
    if signal_cols:
        signal_mask = False
        for col in signal_cols:
            signal_mask = signal_mask | non_empty_mask(dfv[col])
        signal_rows = dfv[signal_mask]
        print_block("ROWS WITH ANY LABEL SIGNAL", signal_rows, args.rows)

    website_col = "Organization - Website"
    li_col = "Organization - Company LI"
    if website_col in dfv.columns and li_col in dfv.columns:
        website_and_li = dfv[non_empty_mask(dfv[website_col]) & non_empty_mask(dfv[li_col])]
        print_block("ROWS WITH WEBSITE + COMPANY LI", website_and_li, args.rows)

    print_value_examples(
        df=dfv,
        column="Organization - Company Status",
        rows_per_value=args.per_value,
        top_values=args.top_values,
        display_columns=cols,
    )
    print_value_examples(
        df=dfv,
        column="Organization - TYPE",
        rows_per_value=args.per_value,
        top_values=args.top_values,
        display_columns=cols,
    )
    print_value_examples(
        df=dfv,
        column="Organization - Labels",
        rows_per_value=args.per_value,
        top_values=args.top_values,
        display_columns=cols,
    )


if __name__ == "__main__":
    main()
