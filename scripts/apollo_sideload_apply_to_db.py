#!/usr/bin/env python3
"""Apply Apollo sideload enrichment CSV to ``contacts`` (PostgreSQL).

Reads ``enriched_contacts.csv`` produced by ``apollo_fetch_sideload.py`` and
updates existing rows by ``id``:

- ``email`` ← ``apollo_email``
- ``email_provider`` ← ``apollo``
- ``email_confidence`` ← derived from Apollo ``email_status`` in ``apollo_raw``
- ``provider_email_status`` ← Apollo ``email_status``
- ``reveal_raw_json`` ← parsed ``apollo_raw``
- ``pipeline_stage`` ← ``email_revealed``
- ``provider_has_email`` ← ``true``
- ``updated_at`` ← now (UTC)

Requires ``PS_DATABASE_URL``. Default: skip rows where DB ``contacts.email``
is already set unless ``--force``.

Usage::

  uv run python scripts/apollo_sideload_apply_to_db.py \\
    --csv apollo_enrichment_out/enriched_contacts.csv --dry-run

  uv run python scripts/apollo_sideload_apply_to_db.py \\
    --csv apollo_enrichment_out/enriched_contacts.csv
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_apollo_raw(value: object) -> dict | None:
    """CSV may store Python repr of dict; normalize to a dict for JSON storage."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dict):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        out = ast.literal_eval(s)
        return out if isinstance(out, dict) else None
    except (SyntaxError, ValueError, TypeError):
        try:
            out = json.loads(s)
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            return None


def apollo_email_confidence(email_status: str | None) -> float | None:
    """Map Apollo person ``email_status`` to 0.0–1.0 (mirrors reveal heuristics)."""
    if not email_status or not str(email_status).strip():
        return 1.0
    s = str(email_status).strip().lower()
    if s in ("verified", "valid"):
        return 1.0
    if s in ("unverified", "unknown", "guessed", "extrapolated"):
        return 0.5
    if s in ("invalid", "unavailable", "bounced"):
        return 0.0
    return 0.5


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Apply apollo_enrichment_out/enriched_contacts.csv to contacts table.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("apollo_enrichment_out/enriched_contacts.csv"),
        help="Path to enriched_contacts.csv",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("PS_DATABASE_URL", ""),
        help="Override database URL (default: PS_DATABASE_URL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts and sample; no DB writes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update even when contacts.email is already set.",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("error: set PS_DATABASE_URL or pass --database-url", file=sys.stderr)
        return 1

    if not args.csv.is_file():
        print(f"error: file not found: {args.csv}", file=sys.stderr)
        return 1

    df = pd.read_csv(args.csv)
    required = {"id", "apollo_email"}
    missing = required - set(str(c).strip() for c in df.columns)
    if missing:
        print(f"error: CSV missing columns: {sorted(missing)}", file=sys.stderr)
        return 1

    df = df.copy()
    df["apollo_email"] = df["apollo_email"].apply(
        lambda x: str(x).strip() if x is not None and not (isinstance(x, float) and pd.isna(x)) else ""
    )
    df = df[df["apollo_email"] != ""]

    if df.empty:
        print("No rows with non-empty apollo_email; nothing to do.")
        return 0

    engine = create_engine(args.database_url, echo=False)

    updated = 0
    rows_without_parsed_raw = 0
    skipped_has_email = 0
    skipped_not_found = 0

    update_sql = text("""
        UPDATE contacts
        SET
            email = :email,
            email_provider = 'apollo',
            email_confidence = :email_confidence,
            provider_email_status = :provider_email_status,
            reveal_raw_json = CAST(:reveal_raw_json AS json),
            pipeline_stage = 'email_revealed',
            provider_has_email = true,
            updated_at = :updated_at
        WHERE id = CAST(:id AS uuid)
          AND (:force OR email IS NULL)
    """)

    select_email_sql = text(
        "SELECT email FROM contacts WHERE id = CAST(:id AS uuid)"
    )

    sample_n = min(3, len(df))

    if args.dry_run:
        print(f"Would process {len(df)} rows with apollo_email (dry-run).")
        for i, row in df.head(sample_n).iterrows():
            raw = parse_apollo_raw(row.get("apollo_raw"))
            status = (raw or {}).get("email_status")
            print(
                f"  sample {row['id']}: email={row['apollo_email']!r} "
                f"status={status!r}"
            )
        return 0

    with engine.begin() as conn:
        for _, row in df.iterrows():
            cid = str(row["id"]).strip()
            email = row["apollo_email"]
            raw = parse_apollo_raw(row.get("apollo_raw"))
            status_val = None
            if raw:
                status_val = raw.get("email_status")
                if status_val is not None:
                    status_val = str(status_val)[:32]

            conf = apollo_email_confidence(str(status_val) if status_val else None)

            # Pre-check: row exists and email skip
            ex = conn.execute(
                select_email_sql, {"id": cid}
            ).first()
            if ex is None:
                skipped_not_found += 1
                continue
            (existing_email,) = ex
            if existing_email and str(existing_email).strip() and not args.force:
                skipped_has_email += 1
                continue

            payload_json = json.dumps(raw) if raw else "{}"
            if not raw:
                rows_without_parsed_raw += 1

            result = conn.execute(
                update_sql,
                {
                    "id": cid,
                    "email": email,
                    "email_confidence": conf,
                    "provider_email_status": status_val,
                    "reveal_raw_json": payload_json,
                    "updated_at": _utcnow(),
                    "force": args.force,
                },
            )
            if result.rowcount:
                updated += 1

    print(
        f"updated={updated}  skipped_already_have_email={skipped_has_email}  "
        f"skipped_not_found={skipped_not_found}  "
        f"rows_without_parsed_apollo_raw={rows_without_parsed_raw}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
