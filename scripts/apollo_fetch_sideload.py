#!/usr/bin/env python3
"""Side-load Apollo bulk_match enrichment and save raw + enriched CSV locally.

Smoke mode (one API batch, minimal credits)::

  uv run python scripts/apollo_fetch_sideload.py --input apollo_one_per_domain.csv --smoke

Or explicitly::

  uv run python scripts/apollo_fetch_sideload.py -i data.csv --limit 10 --max-batches 1

Input CSV must include: id, first_name, last_name, domain. Optional: title.
Rows with a non-empty ``email`` are skipped (already sideloaded / revealed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv


APOLLO_BULK_MATCH_URL = "https://api.apollo.io/api/v1/people/bulk_match"
BATCH_SIZE = 10

# Columns this script reads from the input CSV (apollo export / one-per-domain CSV).
REQUIRED_INPUT_COLUMNS = frozenset({"id", "first_name", "last_name", "domain"})


def chunks(items: list[dict[str, Any]], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def load_done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    done = set()
    with path.open("r") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                done.add(str(row["contact_id"]))
    return done


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def validate_input_columns(columns: pd.Index) -> None:
    present = {str(c).strip() for c in columns}
    missing = REQUIRED_INPUT_COLUMNS - present
    if missing:
        print(
            "error: input CSV is missing required columns: "
            f"{sorted(missing)}. Found: {list(columns)}",
            file=sys.stderr,
        )
        raise SystemExit(2)


def extract_email(person: dict[str, Any] | None) -> str | None:
    if not person:
        return None

    return (
        person.get("email")
        or person.get("sanitized_email")
        or person.get("primary_email")
    )


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Apollo bulk_match sideload: raw JSONL + enriched CSV.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", default=Path("apollo_enrichment_out"), type=Path)
    parser.add_argument(
        "--limit",
        default=2000,
        type=int,
        help="Max contacts to consider after filters (default 2000).",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N bulk_match calls (e.g. 1 for a single batch smoke test).",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=f"Same as --limit {BATCH_SIZE} --max-batches 1 (one batch, ~{BATCH_SIZE} rows max).",
    )
    parser.add_argument("--sleep", default=1.0, type=float)
    args = parser.parse_args()

    if args.smoke:
        args.limit = BATCH_SIZE
        args.max_batches = 1

    api_key = os.getenv("PS_APOLLO_API_KEY")
    if not api_key:
        raise RuntimeError("Missing PS_APOLLO_API_KEY in .env")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    completed_path = args.out_dir / "completed.jsonl"
    failed_path = args.out_dir / "failed.jsonl"
    raw_path = args.out_dir / "raw_responses.jsonl"
    enriched_csv_path = args.out_dir / "enriched_contacts.csv"

    df = pd.read_csv(args.input)
    validate_input_columns(df.columns)

    # Only enrich rows that still need an email (empty / NaN in export).
    if "email" not in df.columns:
        print(
            'warning: no "email" column; processing all rows (add email column to skip filled rows)',
            file=sys.stderr,
        )
    else:
        df = df[df["email"].isna()]
    df = df[df["first_name"].notna()]
    df = df[df["last_name"].notna()]
    df = df[df["domain"].notna()]
    df = df.head(args.limit)

    contacts = df.to_dict("records")
    done_ids = load_done_ids(completed_path)

    contacts = [c for c in contacts if str(c["id"]) not in done_ids]

    n_batches = (len(contacts) + BATCH_SIZE - 1) // BATCH_SIZE if contacts else 0
    planned_batches = n_batches
    if args.max_batches is not None:
        planned_batches = min(n_batches, args.max_batches)

    print(
        f"contacts_to_fetch={len(contacts)}  batch_size={BATCH_SIZE}  "
        f"batches_total={n_batches}  batches_this_run={planned_batches}"
        + (f"  (--max-batches {args.max_batches})" if args.max_batches else ""),
        file=sys.stderr,
    )

    enriched_rows = []
    batches_done = 0

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    for batch in chunks(contacts, BATCH_SIZE):
        details = []

        for c in batch:
            details.append(
                {
                    "first_name": str(c["first_name"]),
                    "last_name": str(c["last_name"]),
                    "domain": str(c["domain"]),
                    "title": str(c["title"]) if pd.notna(c.get("title")) else None,
                }
            )

        payload = {
            "details": details,
        }

        try:
            resp = requests.post(
                APOLLO_BULK_MATCH_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )

            response_json = resp.json()

            append_jsonl(
                raw_path,
                {
                    "status_code": resp.status_code,
                    "request_contacts": [str(c["id"]) for c in batch],
                    "payload": payload,
                    "response": response_json,
                },
            )

            if resp.status_code >= 400:
                for c in batch:
                    append_jsonl(
                        failed_path,
                        {
                            "contact_id": str(c["id"]),
                            "reason": "http_error",
                            "status_code": resp.status_code,
                            "response": response_json,
                        },
                    )
                continue

            people = (
                response_json.get("people")
                or response_json.get("matches")
                or response_json.get("details")
                or []
            )

            for c, person in zip(batch, people):
                email = extract_email(person)

                row = {
                    **c,
                    "apollo_email": email,
                    "apollo_raw": person,
                }

                enriched_rows.append(row)

                append_jsonl(
                    completed_path,
                    {
                        "contact_id": str(c["id"]),
                        "email": email,
                        "success": bool(email),
                    },
                )

                print(
                    f"{c['id']} | {c['first_name']} {c['last_name']} | {c['domain']} | {email}"
                )

        except Exception as e:
            for c in batch:
                append_jsonl(
                    failed_path,
                    {
                        "contact_id": str(c["id"]),
                        "reason": "exception",
                        "error": str(e),
                    },
                )

        batches_done += 1
        if args.max_batches is not None and batches_done >= args.max_batches:
            print(
                f"Stopping after {batches_done} batch(es) (--max-batches).",
                file=sys.stderr,
            )
            break

        time.sleep(args.sleep)

    if enriched_rows:
        out_df = pd.DataFrame(enriched_rows)
        if enriched_csv_path.exists():
            prev = pd.read_csv(enriched_csv_path)
            out_df = pd.concat([prev, out_df], ignore_index=True)
            out_df["id"] = out_df["id"].astype(str)
            out_df = out_df.drop_duplicates(subset=["id"], keep="last")
        out_df.to_csv(enriched_csv_path, index=False)
        print(f"wrote {len(out_df)} enriched rows -> {enriched_csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
