"""add scrape_prompts table

Revision ID: a9b8c7d6e5f4
Revises: f9a8b7c6d5e4
Create Date: 2026-04-20
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import UUID

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "f9a8b7c6d5e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrape_prompts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_system_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("intent_text", sa.Text(), nullable=True),
        sa.Column("compiled_prompt_text", sa.Text(), nullable=False),
        sa.Column("scrape_rules_structured", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_prompts_id", "scrape_prompts", ["id"])
    op.create_index("ix_scrape_prompts_name", "scrape_prompts", ["name"])
    op.create_index("ix_scrape_prompts_enabled", "scrape_prompts", ["enabled"])
    op.create_index("ix_scrape_prompts_is_system_default", "scrape_prompts", ["is_system_default"])
    op.create_index("ix_scrape_prompts_is_active", "scrape_prompts", ["is_active"])
    op.create_index(
        "uq_scrape_prompts_single_active",
        "scrape_prompts",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index("ix_scrape_prompts_created_at", "scrape_prompts", ["created_at"])
    op.create_index("ix_scrape_prompts_updated_at", "scrape_prompts", ["updated_at"])

    page_kinds = [
        "about",
        "products",
        "contact",
        "team",
        "leadership",
        "services",
        "pricing",
    ]
    compiled_prompt_text = "\n".join(
        [
            "Find the best URL for each of these page types:",
            "- about",
            "- products",
            "- contact",
            "- team",
            "- leadership",
            "- services",
            "- pricing",
        ]
    )
    now = datetime.now(timezone.utc)
    seed_table = sa.table(
        "scrape_prompts",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String(length=255)),
        sa.column("enabled", sa.Boolean()),
        sa.column("is_system_default", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("intent_text", sa.Text()),
        sa.column("compiled_prompt_text", sa.Text()),
        sa.column("scrape_rules_structured", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        seed_table,
        [
            {
                "id": UUID("2fd92939-4e13-4f59-8d37-8996fc5f4f36"),
                "name": "Default S1 Scrape Prompt",
                "enabled": True,
                "is_system_default": True,
                "is_active": True,
                "intent_text": (
                    "Find the best URL for each of these page types: "
                    "about, products, contact, team, leadership, services, pricing."
                ),
                "compiled_prompt_text": compiled_prompt_text,
                "scrape_rules_structured": {
                    "page_kinds": page_kinds,
                    "classifier_prompt_text": compiled_prompt_text,
                },
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_scrape_prompts_single_active", table_name="scrape_prompts")
    op.drop_index("ix_scrape_prompts_updated_at", table_name="scrape_prompts")
    op.drop_index("ix_scrape_prompts_created_at", table_name="scrape_prompts")
    op.drop_index("ix_scrape_prompts_is_active", table_name="scrape_prompts")
    op.drop_index("ix_scrape_prompts_is_system_default", table_name="scrape_prompts")
    op.drop_index("ix_scrape_prompts_enabled", table_name="scrape_prompts")
    op.drop_index("ix_scrape_prompts_name", table_name="scrape_prompts")
    op.drop_index("ix_scrape_prompts_id", table_name="scrape_prompts")
    op.drop_table("scrape_prompts")
