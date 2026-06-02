#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import engine
from app.services.email_fetch_repair import (
    EmailFetchStatusRepairError,
    EmailFetchStatusRepairSummary,
    repair_email_fetch_status,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill uploaded_domains.fetch_status for legacy S3 contact rows.",
    )
    parser.add_argument("--campaign-id", required=True, type=UUID, help="Campaign UUID to repair.")
    parser.add_argument("--apply", action="store_true", help="Apply the repair. Defaults to dry-run.")
    return parser.parse_args()


def _print_summary(summary: EmailFetchStatusRepairSummary) -> None:
    mode = "apply" if summary.applied else "dry-run"
    print(f"email_fetch_status_repair mode={mode} campaign_id={summary.campaign_id}")
    print(f"scanned_domains={summary.scanned_domains}")
    print(f"domains_repaired={summary.domains_repaired}")
    print(f"contacts_visible={summary.contacts_visible}")
    print(f"emails_visible={summary.emails_visible}")
    print(f"possible_domains_repaired={summary.possible_domains_repaired}")
    print(f"possible_domains_still_pending={summary.possible_domains_still_pending}")
    print(f"failed_domains_with_contacts={summary.failed_domains_with_contacts}")
    print(f"succeeded_domains_without_contacts={summary.succeeded_domains_without_contacts}")
    if not summary.applied:
        print("No rows were changed. Re-run with --apply to update fetch_status.")


def main() -> int:
    args = _parse_args()
    try:
        with Session(engine) as session:
            summary = repair_email_fetch_status(
                session=session,
                campaign_id=args.campaign_id,
                apply=args.apply,
            )
    except EmailFetchStatusRepairError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
