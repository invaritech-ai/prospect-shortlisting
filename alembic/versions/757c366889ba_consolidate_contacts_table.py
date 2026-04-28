"""consolidate_contacts_table

Revision ID: 757c366889ba
Revises: e9f0a1b2c3d4
Create Date: 2026-04-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "757c366889ba"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename table
    op.rename_table("discovered_contacts", "contacts")

    # 2. Rename unique constraint
    op.drop_constraint("uq_discovered_contacts_provider_key", "contacts", type_="unique")
    op.create_unique_constraint(
        "uq_contacts_provider_key",
        "contacts",
        ["company_id", "provider", "provider_person_id"],
    )

    # 3. Rename indexes
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_id RENAME TO ix_contacts_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_company_id RENAME TO ix_contacts_company_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_contact_fetch_job_id RENAME TO ix_contacts_contact_fetch_job_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_provider RENAME TO ix_contacts_provider")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_provider_person_id RENAME TO ix_contacts_provider_person_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_title_match RENAME TO ix_contacts_title_match")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_provider_has_email RENAME TO ix_contacts_provider_has_email")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_is_active RENAME TO ix_contacts_is_active")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_backfilled RENAME TO ix_contacts_backfilled")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_discovered_at RENAME TO ix_contacts_discovered_at")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_last_seen_at RENAME TO ix_contacts_last_seen_at")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_created_at RENAME TO ix_contacts_created_at")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_updated_at RENAME TO ix_contacts_updated_at")

    # 4. Add new columns
    op.add_column("contacts", sa.Column("email", sa.String(512), nullable=True))
    op.add_column("contacts", sa.Column("email_provider", sa.String(32), nullable=True))
    op.add_column("contacts", sa.Column("email_confidence", sa.Float(), nullable=True))
    op.add_column("contacts", sa.Column("provider_email_status", sa.String(32), nullable=True))
    op.add_column("contacts", sa.Column("reveal_raw_json", sa.JSON(), nullable=True))
    op.add_column("contacts", sa.Column("verification_status", sa.String(32), nullable=False, server_default="unverified"))
    op.add_column("contacts", sa.Column("zerobounce_raw", sa.JSON(), nullable=True))
    op.add_column("contacts", sa.Column("pipeline_stage", sa.String(32), nullable=False, server_default="fetched"))

    # 5. Create indexes on new columns
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_verification_status", "contacts", ["verification_status"])
    op.create_index("ix_contacts_pipeline_stage", "contacts", ["pipeline_stage"])

    # 6. Drop prospect_contact_emails first (FK → prospect_contacts)
    op.drop_table("prospect_contact_emails")

    # 7. Drop prospect_contacts
    op.drop_table("prospect_contacts")


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported — data loss would occur.")
