"""backfill discovered_contacts from prospect_contacts

Revision ID: 9c2d3e4f5a6b
Revises: 8b1c2d3e4f5a
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c2d3e4f5a6b"
down_revision: Union[str, Sequence[str], None] = "8b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill discovered_contacts rows from existing prospect_contacts rows.

    Strategy:
    - Normalise the ``source`` column to 'snov' or 'apollo'; skip all others.
    - Derive ``provider_person_id`` in priority order:
        1. id / user_id / search_emails_start from snov_prospect_raw (snov);
           id from apollo_prospect_raw (apollo)
        2. linkedin_url when non-empty
        3. lower(first_name) || '|' || lower(last_name) || '|' || lower(coalesce(title,''))
    - Skip rows whose derived provider_person_id is empty after all attempts.
    - Skip rows where a matching (company_id, provider, provider_person_id) tuple
      already exists in discovered_contacts (idempotent ON CONFLICT DO NOTHING).
    - Set is_active = true, backfilled = true.
    - Downgrade is a no-op; data migrations are not reversed.
    """

    # Step 1: Build temporary staging table with derived fields
    op.execute("""
        CREATE TEMPORARY TABLE _dc_backfill AS
        SELECT
            gen_random_uuid()                              AS id,
            pc.company_id                                  AS company_id,
            pc.contact_fetch_job_id                        AS contact_fetch_job_id,

            lower(trim(pc.source))                         AS provider,

            CASE
                WHEN lower(trim(pc.source)) = 'snov'
                     AND pc.snov_prospect_raw IS NOT NULL
                     AND (
                             pc.snov_prospect_raw->>'id'                  IS NOT NULL
                          OR pc.snov_prospect_raw->>'user_id'             IS NOT NULL
                          OR pc.snov_prospect_raw->>'search_emails_start' IS NOT NULL
                     )
                THEN coalesce(
                         pc.snov_prospect_raw->>'id',
                         pc.snov_prospect_raw->>'user_id',
                         pc.snov_prospect_raw->>'search_emails_start'
                     )

                WHEN lower(trim(pc.source)) = 'apollo'
                     AND pc.apollo_prospect_raw IS NOT NULL
                     AND pc.apollo_prospect_raw->>'id' IS NOT NULL
                THEN pc.apollo_prospect_raw->>'id'

                WHEN pc.linkedin_url IS NOT NULL
                     AND trim(pc.linkedin_url) <> ''
                THEN trim(pc.linkedin_url)

                ELSE lower(trim(pc.first_name))
                     || '|'
                     || lower(trim(pc.last_name))
                     || '|'
                     || lower(trim(coalesce(pc.title, '')))
            END                                            AS provider_person_id,

            pc.first_name                                  AS first_name,
            pc.last_name                                   AS last_name,
            pc.title                                       AS title,
            pc.title_match                                 AS title_match,
            pc.linkedin_url                                AS linkedin_url,

            CASE
                WHEN lower(trim(pc.source)) = 'apollo' THEN pc.apollo_prospect_raw
                ELSE pc.snov_prospect_raw
            END                                            AS raw_payload_json,

            NULL::text                                     AS source_url,
            NULL::boolean                                  AS provider_has_email,
            NULL::json                                     AS provider_metadata_json,

            pc.created_at                                  AS discovered_at,
            pc.created_at                                  AS last_seen_at,
            now()                                          AS created_at,
            now()                                          AS updated_at

        FROM prospect_contacts pc
        WHERE lower(trim(pc.source)) IN ('snov', 'apollo')
    """)

    # Step 2: Remove rows where provider_person_id is empty or degenerate
    op.execute("""
        DELETE FROM _dc_backfill
        WHERE provider_person_id IS NULL
           OR trim(provider_person_id) = ''
           OR provider_person_id = '||'
    """)

    # Step 3: Insert into discovered_contacts, skipping existing tuples
    op.execute("""
        INSERT INTO discovered_contacts (
            id,
            company_id,
            contact_fetch_job_id,
            provider,
            provider_person_id,
            first_name,
            last_name,
            title,
            title_match,
            linkedin_url,
            source_url,
            provider_has_email,
            provider_metadata_json,
            raw_payload_json,
            is_active,
            backfilled,
            discovered_at,
            last_seen_at,
            created_at,
            updated_at
        )
        SELECT
            id,
            company_id,
            contact_fetch_job_id,
            provider,
            provider_person_id,
            first_name,
            last_name,
            title,
            title_match,
            linkedin_url,
            source_url,
            provider_has_email,
            provider_metadata_json,
            raw_payload_json,
            true  AS is_active,
            true  AS backfilled,
            discovered_at,
            last_seen_at,
            created_at,
            updated_at
        FROM _dc_backfill
        ON CONFLICT (company_id, provider, provider_person_id)
        DO NOTHING
    """)

    # Step 4: Clean up staging table
    op.execute("DROP TABLE IF EXISTS _dc_backfill")

def downgrade() -> None:
    """Data migrations are not reversed."""
    pass
