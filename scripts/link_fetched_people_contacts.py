#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import engine
from app.services.fetched_people_repair import (
    FetchedPeopleLinkRepairSummary,
    FetchedPeopleRepairError,
    link_fetched_people_contacts,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Link fetched_people rows to matching existing contacts without changing contacts.",
    )
    parser.add_argument("--campaign-id", required=True, type=UUID, help="Campaign UUID to repair.")
    parser.add_argument("--apply", action="store_true", help="Apply the repair. Defaults to dry-run.")
    return parser.parse_args()


def _print_summary(summary: FetchedPeopleLinkRepairSummary) -> None:
    mode = "apply" if summary.applied else "dry-run"
    print(f"fetched_people_contact_link_repair mode={mode} campaign_id={summary.campaign_id}")
    print(f"scanned_fetched_people={summary.scanned_fetched_people}")
    print(f"linked={summary.linked}")
    print(f"ambiguous={summary.ambiguous}")
    print(f"unmatched={summary.unmatched}")
    if not summary.applied:
        print("No rows were changed. Re-run with --apply to link fetched_people.contact_id.")


def main() -> int:
    args = _parse_args()
    try:
        with Session(engine) as session:
            summary = link_fetched_people_contacts(
                session=session,
                campaign_id=args.campaign_id,
                apply=args.apply,
            )
    except FetchedPeopleRepairError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
