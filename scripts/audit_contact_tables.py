from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import engine


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only audit comparing discovered_contacts and prospect_contacts.",
    )
    parser.add_argument("--campaign-id", type=UUID, default=None, help="Limit audit to one campaign UUID.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum company rows to print.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    campaign_filter = "and u.campaign_id = :campaign_id" if args.campaign_id else ""
    params = {"campaign_id": str(args.campaign_id), "limit": args.limit}

    integrity_queries = {
        "orphan_discovered_company": """
            select count(*)
            from discovered_contacts dc
            left join companies c on c.id = dc.company_id
            where c.id is null
        """,
        "orphan_prospect_company": """
            select count(*)
            from prospect_contacts pc
            left join companies c on c.id = pc.company_id
            where c.id is null
        """,
        "empty_discovered_provider_id": """
            select count(*)
            from discovered_contacts
            where provider_person_id is null or trim(provider_person_id) = ''
        """,
        "duplicate_discovered_provider_key": """
            select count(*)
            from (
                select company_id, provider, provider_person_id, count(*) as row_count
                from discovered_contacts
                group by company_id, provider, provider_person_id
                having count(*) > 1
            ) duplicates
        """,
        "duplicate_prospect_company_email": """
            select count(*)
            from (
                select company_id, lower(email), count(*) as row_count
                from prospect_contacts
                where email is not null and trim(email) <> ''
                group by company_id, lower(email)
                having count(*) > 1
            ) duplicates
        """,
        "prospect_email_missing_child_row": """
            select count(*)
            from prospect_contacts pc
            where pc.email is not null
              and trim(pc.email) <> ''
              and not exists (
                select 1
                from prospect_contact_emails e
                where e.contact_id = pc.id
                  and e.email_normalized = lower(pc.email)
              )
        """,
        "orphan_prospect_contact_email": """
            select count(*)
            from prospect_contact_emails e
            left join prospect_contacts pc on pc.id = e.contact_id
            where pc.id is null
        """,
    }

    comparison_query = f"""
        select
            u.campaign_id,
            c.domain,
            c.id as company_id,
            count(distinct dc.id) as discovered_count,
            count(distinct case when dc.title_match then dc.id end) as discovered_title_matched_count,
            count(distinct pc.id) as prospect_count,
            count(distinct case when pc.email is not null and trim(pc.email) <> '' then pc.id end) as prospect_with_email_count
        from companies c
        join uploads u on u.id = c.upload_id
        left join discovered_contacts dc on dc.company_id = c.id and dc.is_active = true
        left join prospect_contacts pc on pc.company_id = c.id
        where (
            exists (select 1 from discovered_contacts d where d.company_id = c.id)
            or exists (select 1 from prospect_contacts p where p.company_id = c.id)
        )
        {campaign_filter}
        group by u.campaign_id, c.domain, c.id
        order by discovered_count desc, prospect_count desc, c.domain asc
        limit :limit
    """

    with Session(engine) as session:
        print("Integrity checks")
        for name, query in integrity_queries.items():
            count = session.exec(text(query)).one()[0]
            print(f"{name}: {count}")

        print()
        print("Company comparison")
        print("campaign_id,domain,company_id,discovered,matched,prospects,prospects_with_email")
        for row in session.execute(text(comparison_query), params):
            print(",".join(str(value) for value in row))


if __name__ == "__main__":
    main()
