#!/usr/bin/env python3
"""Export title-matched contacts (people) to CSV.

Despite the filename, this script does not read ``title_match_rules``; it runs the
same SQL as the title-matched contacts query (``contacts.title_match = TRUE``).

Usage::

  uv run python scripts/get_title_match_rules.py -o title_matched.csv
  uv run python scripts/get_title_match_rules.py -o out.csv --campaign-id <uuid>

Requires ``PS_DATABASE_URL`` in the environment (e.g. from ``.env``).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("PS_DATABASE_URL")

SessionLocal = sessionmaker(
    bind=None,  # set in main after engine exists
    class_=Session,
    autoflush=False,
    autocommit=False,
)


def _build_sql(*, campaign_id: UUID | None) -> tuple[str, dict[str, object]]:
    base = """
SELECT
  c.id,
  c.company_id,
  co.domain,
  c.source_provider,
  c.provider_person_id,
  c.first_name,
  c.last_name,
  c.title,
  c.title_match,
  c.email,
  c.pipeline_stage,
  c.created_at,
  c.updated_at
FROM contacts AS c
JOIN companies AS co ON co.id = c.company_id
"""
    if campaign_id is not None:
        base += """
JOIN uploads AS u ON u.id = co.upload_id
"""
    base += """
WHERE c.title_match = TRUE
  AND c.is_active = TRUE
"""
    params: dict[str, object] = {}
    if campaign_id is not None:
        base += "  AND u.campaign_id = CAST(:campaign_id AS uuid)\n"
        params["campaign_id"] = str(campaign_id)
    return base, params


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export title-matched contacts to CSV.")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("title_matched_contacts.csv"),
        help="Output CSV path (default: title_matched_contacts.csv)",
    )
    p.add_argument(
        "--campaign-id",
        type=UUID,
        default=None,
        help="If set, only contacts whose company belongs to this campaign.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not DATABASE_URL:
        print("error: PS_DATABASE_URL is not set", file=sys.stderr)
        return 1

    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal.configure(bind=engine)

    sql, params = _build_sql(campaign_id=args.campaign_id)

    with SessionLocal() as session:
        result = session.execute(text(sql), params)
        rows = result.mappings().all()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        # Still write a header row so tools don't choke on empty files.
        fieldnames = [
            "id",
            "company_id",
            "domain",
            "source_provider",
            "provider_person_id",
            "first_name",
            "last_name",
            "title",
            "title_match",
            "email",
            "pipeline_stage",
            "created_at",
            "updated_at",
        ]
        with args.output.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
        print(f"wrote 0 rows -> {args.output.resolve()}")
        return 0

    fieldnames = list(rows[0].keys())
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            row = {k: r[k] for k in fieldnames}
            # Normalize UUIDs and datetimes for CSV
            for key, val in list(row.items()):
                if val is not None and hasattr(val, "isoformat"):
                    row[key] = val.isoformat()
                elif val is not None and not isinstance(val, (str, int, float, bool)):
                    row[key] = str(val)
            w.writerow(row)

    print(f"wrote {len(rows)} rows -> {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
