"""add campaign scope to title_match_rules

Revision ID: 4f6a7b8c9d0e
Revises: e0f2a8c9d7b1
Create Date: 2026-05-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "4f6a7b8c9d0e"
down_revision = "e0f2a8c9d7b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {column["name"] for column in inspector.get_columns("title_match_rules")}
    if "campaign_id" not in columns:
        op.add_column("title_match_rules", sa.Column("campaign_id", sa.Uuid(), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("title_match_rules")}
    if "ix_title_match_rules_campaign_id" not in indexes:
        op.create_index(
            "ix_title_match_rules_campaign_id",
            "title_match_rules",
            ["campaign_id"],
            unique=False,
        )

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("title_match_rules")}
    if "fk_title_match_rules_campaign_id_campaigns" not in foreign_keys:
        op.create_foreign_key(
            "fk_title_match_rules_campaign_id_campaigns",
            "title_match_rules",
            "campaigns",
            ["campaign_id"],
            ["id"],
        )

    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("title_match_rules")}
    if "uq_title_match_rules_campaign_rule" not in unique_constraints:
        op.create_unique_constraint(
            "uq_title_match_rules_campaign_rule",
            "title_match_rules",
            ["campaign_id", "rule_type", "match_type", "keywords"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("title_match_rules")}
    if "uq_title_match_rules_campaign_rule" in unique_constraints:
        op.drop_constraint("uq_title_match_rules_campaign_rule", "title_match_rules", type_="unique")

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("title_match_rules")}
    if "fk_title_match_rules_campaign_id_campaigns" in foreign_keys:
        op.drop_constraint("fk_title_match_rules_campaign_id_campaigns", "title_match_rules", type_="foreignkey")

    indexes = {index["name"] for index in inspector.get_indexes("title_match_rules")}
    if "ix_title_match_rules_campaign_id" in indexes:
        op.drop_index("ix_title_match_rules_campaign_id", table_name="title_match_rules")

    columns = {column["name"] for column in inspector.get_columns("title_match_rules")}
    if "campaign_id" in columns:
        op.drop_column("title_match_rules", "campaign_id")
