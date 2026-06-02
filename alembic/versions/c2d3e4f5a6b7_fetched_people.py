"""add fetched people ledger

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fetched_people",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("domain_id", sa.Uuid(), nullable=False),
        sa.Column("email_fetch_batch_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("criteria_hash", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_person_id", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("linkedin_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_summary_json", sa.JSON(), nullable=True),
        sa.Column("match_status", sa.String(length=64), nullable=False),
        sa.Column("match_reason", sa.String(length=512), nullable=False),
        sa.Column("email_lookup_attempted", sa.Boolean(), nullable=False),
        sa.Column("email_result", sa.String(length=512), nullable=True),
        sa.Column("email_status", sa.String(length=64), nullable=True),
        sa.Column("email_error_code", sa.String(length=128), nullable=False),
        sa.Column("email_raw_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["domain_id"], ["uploaded_domains.id"]),
        sa.ForeignKeyConstraint(["email_fetch_batch_id"], ["email_fetch_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fetched_people_campaign_id"), "fetched_people", ["campaign_id"], unique=False)
    op.create_index("ix_fetched_people_campaign_domain", "fetched_people", ["campaign_id", "domain_id"], unique=False)
    op.create_index("ix_fetched_people_batch_provider", "fetched_people", ["email_fetch_batch_id", "provider", "provider_person_id"], unique=False)
    op.create_index(op.f("ix_fetched_people_contact_id"), "fetched_people", ["contact_id"], unique=False)
    op.create_index(op.f("ix_fetched_people_created_at"), "fetched_people", ["created_at"], unique=False)
    op.create_index(op.f("ix_fetched_people_criteria_hash"), "fetched_people", ["criteria_hash"], unique=False)
    op.create_index(op.f("ix_fetched_people_domain_id"), "fetched_people", ["domain_id"], unique=False)
    op.create_index(op.f("ix_fetched_people_email_fetch_batch_id"), "fetched_people", ["email_fetch_batch_id"], unique=False)
    op.create_index(op.f("ix_fetched_people_email_lookup_attempted"), "fetched_people", ["email_lookup_attempted"], unique=False)
    op.create_index(op.f("ix_fetched_people_id"), "fetched_people", ["id"], unique=False)
    op.create_index(op.f("ix_fetched_people_match_status"), "fetched_people", ["match_status"], unique=False)
    op.create_index(op.f("ix_fetched_people_provider"), "fetched_people", ["provider"], unique=False)
    op.create_index(op.f("ix_fetched_people_provider_person_id"), "fetched_people", ["provider_person_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fetched_people_provider_person_id"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_provider"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_match_status"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_id"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_email_lookup_attempted"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_email_fetch_batch_id"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_domain_id"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_criteria_hash"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_created_at"), table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_contact_id"), table_name="fetched_people")
    op.drop_index("ix_fetched_people_batch_provider", table_name="fetched_people")
    op.drop_index("ix_fetched_people_campaign_domain", table_name="fetched_people")
    op.drop_index(op.f("ix_fetched_people_campaign_id"), table_name="fetched_people")
    op.drop_table("fetched_people")
