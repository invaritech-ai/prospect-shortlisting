"""add_pipeline_stages_and_contact_verify_jobs

Revision ID: c9d8e7f6a5b4
Revises: b5c6d7e8f9a0
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = "7f8e9d0c1b2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("pipeline_stage", sa.String(length=32), nullable=True))
    op.execute("UPDATE companies SET pipeline_stage = 'uploaded'")
    op.execute(
        """
        UPDATE companies c
        SET pipeline_stage = 'scraped'
        WHERE EXISTS (
            SELECT 1
            FROM scrapejob sj
            WHERE sj.normalized_url = c.normalized_url
              AND sj.status = 'completed'
              AND sj.markdown_pages_count > 0
        )
        """
    )
    op.execute(
        """
        WITH latest_labels AS (
            SELECT
                c.id AS company_id,
                LOWER(
                    COALESCE(
                        cf.manual_label,
                        (
                            SELECT CAST(cr.predicted_label AS TEXT)
                            FROM analysis_jobs aj
                            JOIN classification_results cr ON cr.analysis_job_id = aj.id
                            WHERE aj.company_id = c.id
                              AND COALESCE(cr.is_stale, FALSE) = FALSE
                            ORDER BY cr.created_at DESC
                            LIMIT 1
                        )
                    )
                ) AS effective_label
            FROM companies c
            LEFT JOIN company_feedback cf ON cf.company_id = c.id
        )
        UPDATE companies c
        SET pipeline_stage = CASE
            WHEN ll.effective_label = 'possible' THEN 'contact_ready'
            WHEN ll.effective_label IS NOT NULL THEN 'classified'
            ELSE c.pipeline_stage
        END
        FROM latest_labels ll
        WHERE c.id = ll.company_id
          AND c.pipeline_stage IN ('scraped', 'classified', 'contact_ready')
        """
    )
    op.alter_column("companies", "pipeline_stage", nullable=False)
    op.create_index(op.f("ix_companies_pipeline_stage"), "companies", ["pipeline_stage"], unique=False)

    op.add_column("prospect_contacts", sa.Column("pipeline_stage", sa.String(length=32), nullable=True))
    op.add_column("prospect_contacts", sa.Column("provider_email_status", sa.String(length=32), nullable=True))
    op.add_column(
        "prospect_contacts",
        sa.Column("verification_status", sa.String(length=32), nullable=True),
    )
    op.execute("UPDATE prospect_contacts SET provider_email_status = LOWER(email_status)")
    op.execute(
        """
        UPDATE prospect_contacts
        SET verification_status = CASE
            WHEN zerobounce_raw IS NULL THEN 'unverified'
            WHEN LOWER(email_status) IN ('catch-all', 'catch_all') THEN 'catch_all'
            WHEN LOWER(email_status) IN ('not_valid', 'not valid') THEN 'invalid'
            WHEN email_status IS NULL OR TRIM(email_status) = '' THEN 'unknown'
            ELSE LOWER(email_status)
        END
        """
    )
    op.execute(
        """
        UPDATE prospect_contacts
        SET pipeline_stage = CASE
            WHEN title_match = TRUE
             AND email IS NOT NULL
             AND verification_status = 'valid' THEN 'campaign_ready'
            WHEN verification_status <> 'unverified' THEN 'verified'
            ELSE 'fetched'
        END
        """
    )
    op.alter_column("prospect_contacts", "pipeline_stage", nullable=False)
    op.alter_column("prospect_contacts", "verification_status", nullable=False)
    op.create_index(op.f("ix_prospect_contacts_pipeline_stage"), "prospect_contacts", ["pipeline_stage"], unique=False)
    op.create_index(op.f("ix_prospect_contacts_provider_email_status"), "prospect_contacts", ["provider_email_status"], unique=False)
    op.create_index(op.f("ix_prospect_contacts_verification_status"), "prospect_contacts", ["verification_status"], unique=False)
    op.drop_index(op.f("ix_prospect_contacts_email_status"), table_name="prospect_contacts")
    op.drop_column("prospect_contacts", "email_status")

    op.create_table(
        "contact_verify_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("terminal_state", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.String(length=4000), nullable=True),
        sa.Column("lock_token", sa.String(length=64), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(), nullable=True),
        sa.Column("filter_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("contact_ids_json", sa.JSON(), nullable=True),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("verified_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contact_verify_jobs_id"), "contact_verify_jobs", ["id"], unique=False)
    op.create_index(op.f("ix_contact_verify_jobs_state"), "contact_verify_jobs", ["state"], unique=False)
    op.create_index(op.f("ix_contact_verify_jobs_lock_expires_at"), "contact_verify_jobs", ["lock_expires_at"], unique=False)
    op.create_index(op.f("ix_contact_verify_jobs_created_at"), "contact_verify_jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_contact_verify_jobs_updated_at"), "contact_verify_jobs", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_contact_verify_jobs_updated_at"), table_name="contact_verify_jobs")
    op.drop_index(op.f("ix_contact_verify_jobs_created_at"), table_name="contact_verify_jobs")
    op.drop_index(op.f("ix_contact_verify_jobs_lock_expires_at"), table_name="contact_verify_jobs")
    op.drop_index(op.f("ix_contact_verify_jobs_state"), table_name="contact_verify_jobs")
    op.drop_index(op.f("ix_contact_verify_jobs_id"), table_name="contact_verify_jobs")
    op.drop_table("contact_verify_jobs")

    op.add_column("prospect_contacts", sa.Column("email_status", sa.String(length=32), nullable=True))
    op.execute(
        """
        UPDATE prospect_contacts
        SET email_status = COALESCE(provider_email_status, verification_status, 'unverified')
        """
    )
    op.alter_column("prospect_contacts", "email_status", nullable=False)
    op.create_index(op.f("ix_prospect_contacts_email_status"), "prospect_contacts", ["email_status"], unique=False)
    op.drop_index(op.f("ix_prospect_contacts_verification_status"), table_name="prospect_contacts")
    op.drop_index(op.f("ix_prospect_contacts_provider_email_status"), table_name="prospect_contacts")
    op.drop_index(op.f("ix_prospect_contacts_pipeline_stage"), table_name="prospect_contacts")
    op.drop_column("prospect_contacts", "verification_status")
    op.drop_column("prospect_contacts", "provider_email_status")
    op.drop_column("prospect_contacts", "pipeline_stage")

    op.drop_index(op.f("ix_companies_pipeline_stage"), table_name="companies")
    op.drop_column("companies", "pipeline_stage")
