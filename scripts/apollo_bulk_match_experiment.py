#!/usr/bin/env python3
"""Minimal Apollo bulk_match probe — prints status + raw body (Apollo often explains 403 in JSON).

Uses the same URL shape as app.services.apollo_client.ApolloClient.reveal_email.

Examples:

  cd /path/to/Prospect_shortlisting
  uv run python scripts/apollo_bulk_match_experiment.py 587cf802f65125cad923a266

  # Same request without reveal flags (baseline — uses credits differently)
  uv run python scripts/apollo_bulk_match_experiment.py 587cf802f65125cad923a266 --no-reveal

API key: resolves via app.credentials_resolver (DB secret store first, then APOLLO_API_KEY env).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root on sys.path for `app.*` imports when run as scripts/foo.py
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx  # noqa: E402

from app.services.credentials_resolver import resolve as resolve_credential  # noqa: E402

_APOLLO_BASE = "https://api.apollo.io/api/v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Apollo POST /people/bulk_match")
    parser.add_argument(
        "person_id",
        help="Apollo person id (stored as Contact.provider_person_id)",
    )
    parser.add_argument(
        "--no-reveal",
        action="store_true",
        help="Omit reveal_personal_emails / reveal_phone_number query flags",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="HTTP timeout seconds",
    )
    args = parser.parse_args()

    api_key = resolve_credential("apollo", "api_key")
    if not api_key:
        print(
            "No Apollo API key: set APOLLO_API_KEY or configure Apollo in app integrations (DB).",
            file=sys.stderr,
        )
        return 2

    if args.no_reveal:
        url = f"{_APOLLO_BASE}/people/bulk_match"
        params = None
    else:
        url = f"{_APOLLO_BASE}/people/bulk_match"
        params = {
            "reveal_personal_emails": "true",
            "reveal_phone_number": "false",
        }

    payload = {"details": [{"id": args.person_id.strip()}]}
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Accept": "application/json",
        "X-Api-Key": api_key,
    }

    print(f"POST {url}")
    if params:
        print(f"query: {params}")
    print(f"payload: {json.dumps(payload)}\n")

    try:
        r = httpx.post(
            url,
            params=params,
            headers=headers,
            json=payload,
            timeout=args.timeout,
        )
    except httpx.HTTPError as exc:
        print(f"transport_error: {exc}", file=sys.stderr)
        return 1

    print(f"status: {r.status_code}")
    body = r.text
    print("body:")
    try:
        parsed = r.json()
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print(body)

    return 0 if r.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
