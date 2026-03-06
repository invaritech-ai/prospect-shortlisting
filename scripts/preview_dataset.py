#!/usr/bin/env python3
"""Preview tabular datasets with pandas."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".jsonl", ".parquet"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a dataset into a DataFrame and preview it.")
    parser.add_argument("path", type=Path, help="Path to dataset file.")
    parser.add_argument(
        "--sheet",
        default=None,
        help="Sheet name/index for Excel files (defaults to first sheet).",
    )
    parser.add_argument("--rows", type=int, default=10, help="Number of rows to preview.")
    return parser.parse_args()


def load_dataframe(path: Path, sheet: str | None) -> tuple[pd.DataFrame, list[str] | None]:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {ext}")

    if ext in {".xlsx", ".xls"}:
        workbook = pd.ExcelFile(path)
        sheet_names = workbook.sheet_names
        selected_sheet = sheet if sheet is not None else sheet_names[0]
        frame = pd.read_excel(path, sheet_name=selected_sheet)
        return frame, sheet_names

    if ext == ".csv":
        return pd.read_csv(path), None
    if ext == ".tsv":
        return pd.read_csv(path, sep="\t"), None
    if ext == ".json":
        return pd.read_json(path), None
    if ext == ".jsonl":
        return pd.read_json(path, lines=True), None
    if ext == ".parquet":
        return pd.read_parquet(path), None

    raise ValueError(f"Unhandled file extension: {ext}")


def main() -> None:
    args = parse_args()
    path = args.path
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    frame, sheet_names = load_dataframe(path, args.sheet)

    print(f"FILE: {path}")
    print(f"SHAPE: {frame.shape[0]} rows x {frame.shape[1]} columns")
    if sheet_names is not None:
        print(f"SHEETS: {sheet_names}")

    print("\nCOLUMNS:")
    for column in frame.columns:
        null_count = int(frame[column].isna().sum())
        dtype = str(frame[column].dtype)
        print(f"- {column} | dtype={dtype} | nulls={null_count}")

    print(f"\nPREVIEW (first {args.rows} rows):")
    print(frame.head(args.rows).to_string(index=False))


if __name__ == "__main__":
    main()
