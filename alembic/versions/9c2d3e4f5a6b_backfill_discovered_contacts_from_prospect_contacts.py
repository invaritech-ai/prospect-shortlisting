"""Backfill discovered_contacts from prospect_contacts.

Revision ID: 9c2d3e4f5a6b
Revises: 8b1c2d3e4f5a
Create Date: 2026-04-24

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c2d3e4f5a6b"
down_revision: Union[str, Sequence[str], None] = "8b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reconcile discovered_contacts from historical prospect_contacts rows.

    Rules:
    - Snov native identity: ``id``, ``user_id``, or ``search_emails_start``.
    - Apollo native identity: ``id`` only.
    - No LinkedIn / name / title fallback identity.
    - Duplicate source rows collapse to one canonical discovered row per
      ``(company_id, provider, provider_person_id)`` key.
    - Matching discovered rows are updated/reactivated.
    - Active discovered rows in a backfilled provider scope but absent from the
      canonical source set are marked inactive, never deleted.
    """

    op.execute(
        """
        CREATE TEMPORARY TABLE _dc_backfill_source AS
        WITH source_rows AS (
            SELECT
                pc.id                                                   AS source_row_id,
                pc.company_id                                           AS company_id,
                pc.contact_fetch_job_id                                 AS contact_fetch_job_id,
                lower(trim(pc.source))                                  AS provider,
                CASE
                    WHEN lower(trim(pc.source)) = 'apollo' THEN nullif(trim(pc.apollo_prospect_raw->>'id'), '')
                    WHEN lower(trim(pc.source)) = 'snov' THEN coalesce(
                        nullif(trim(pc.snov_prospect_raw->>'id'), ''),
                        nullif(trim(pc.snov_prospect_raw->>'user_id'), ''),
                        nullif(trim(pc.snov_prospect_raw->>'search_emails_start'), '')
                    )
                    ELSE NULL
                END                                                     AS provider_person_id,
                pc.first_name                                           AS first_name,
                pc.last_name                                            AS last_name,
                pc.title                                                AS title,
                pc.title_match                                          AS title_match,
                NULLIF(trim(pc.linkedin_url), '')                       AS linkedin_url,
                CASE
                    WHEN lower(trim(pc.source)) = 'apollo' THEN coalesce(
                        nullif(trim(pc.apollo_prospect_raw->>'website_url'), ''),
                        nullif(trim(pc.apollo_prospect_raw->>'photo_url'), '')
                    )
                    WHEN lower(trim(pc.source)) = 'snov' THEN nullif(trim(pc.snov_prospect_raw->>'source_page'), '')
                    ELSE NULL
                END                                                     AS source_url,
                CASE
                    WHEN lower(trim(pc.source)) = 'apollo'
                         AND pc.apollo_prospect_raw IS NOT NULL
                         AND pc.apollo_prospect_raw->>'has_email' IS NOT NULL
                    THEN (pc.apollo_prospect_raw->>'has_email')::boolean
                    ELSE NULL
                END                                                     AS provider_has_email,
                CASE
                    WHEN lower(trim(pc.source)) = 'apollo' THEN NULLIF(
                        json_strip_nulls(
                            json_build_object(
                                'has_email',
                                CASE
                                    WHEN pc.apollo_prospect_raw->>'has_email' IS NULL THEN NULL
                                    ELSE (pc.apollo_prospect_raw->>'has_email')::boolean
                                END,
                                'organization_id',
                                nullif(trim(pc.apollo_prospect_raw->>'organization_id'), '')
                            )
                        )::text,
                        '{}'
                    )::json
                    ELSE NULL
                END                                                     AS provider_metadata_json,
                CASE
                    WHEN lower(trim(pc.source)) = 'apollo' THEN pc.apollo_prospect_raw
                    ELSE pc.snov_prospect_raw
                END                                                     AS raw_payload_json,
                pc.created_at                                           AS created_at,
                pc.updated_at                                           AS updated_at
            FROM prospect_contacts pc
            WHERE lower(trim(pc.source)) IN ('snov', 'apollo')
        ),
        native_rows AS (
            SELECT *
            FROM source_rows
            WHERE provider_person_id IS NOT NULL
              AND trim(provider_person_id) <> ''
        ),
        ranked_rows AS (
            SELECT
                native_rows.*,
                row_number() OVER (
                    PARTITION BY company_id, provider, provider_person_id
                    ORDER BY updated_at DESC, created_at DESC, source_row_id DESC
                ) AS rn,
                min(created_at) OVER (
                    PARTITION BY company_id, provider, provider_person_id
                ) AS discovered_at,
                max(updated_at) OVER (
                    PARTITION BY company_id, provider, provider_person_id
                ) AS last_seen_at
            FROM native_rows
        )
        SELECT
            source_row_id AS id,
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
            discovered_at,
            last_seen_at
        FROM ranked_rows
        WHERE rn = 1
        """
    )

    op.execute(
        """
        CREATE TEMPORARY TABLE _dc_backfill_scopes AS
        SELECT DISTINCT
            company_id,
            lower(trim(source)) AS provider
        FROM prospect_contacts
        WHERE lower(trim(source)) IN ('snov', 'apollo')
        """
    )

    op.execute(
        """
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
            COALESCE(first_name, ''),
            COALESCE(last_name, ''),
            title,
            COALESCE(title_match, false),
            linkedin_url,
            source_url,
            provider_has_email,
            provider_metadata_json,
            raw_payload_json,
            true,
            true,
            discovered_at,
            last_seen_at,
            now(),
            now()
        FROM _dc_backfill_source
        ON CONFLICT (company_id, provider, provider_person_id)
        DO UPDATE SET
            contact_fetch_job_id = EXCLUDED.contact_fetch_job_id,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            title = EXCLUDED.title,
            title_match = EXCLUDED.title_match,
            linkedin_url = EXCLUDED.linkedin_url,
            source_url = EXCLUDED.source_url,
            provider_has_email = EXCLUDED.provider_has_email,
            provider_metadata_json = EXCLUDED.provider_metadata_json,
            raw_payload_json = EXCLUDED.raw_payload_json,
            is_active = true,
            backfilled = true,
            discovered_at = EXCLUDED.discovered_at,
            last_seen_at = EXCLUDED.last_seen_at,
            updated_at = now()
        """
    )

    op.execute(
        """
        UPDATE discovered_contacts dc
        SET
            is_active = false,
            updated_at = now()
        WHERE dc.is_active = true
          AND EXISTS (
              SELECT 1
              FROM _dc_backfill_scopes scopes
              WHERE scopes.company_id = dc.company_id
                AND scopes.provider = dc.provider
          )
          AND NOT EXISTS (
              SELECT 1
              FROM _dc_backfill_source src
              WHERE src.company_id = dc.company_id
                AND src.provider = dc.provider
                AND src.provider_person_id = dc.provider_person_id
          )
        """
    )

    op.execute("DROP TABLE IF EXISTS _dc_backfill_source")
    op.execute("DROP TABLE IF EXISTS _dc_backfill_scopes")


def downgrade() -> None:
    """Data migrations are not reversed."""
    pass
