"""drop legacy runs

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "3c4d5e6f7081"
down_revision = "2b3c4d5e6f70"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_foreign_keys(table_name) + inspector.get_unique_constraints(table_name)
    return any(constraint.get("name") == constraint_name for constraint in constraints)


def _has_index(table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    if not _has_column("analysis_jobs", "prompt_id"):
        op.add_column("analysis_jobs", sa.Column("prompt_id", sa.Uuid(), nullable=True))
        op.create_index(op.f("ix_analysis_jobs_prompt_id"), "analysis_jobs", ["prompt_id"], unique=False)
    if not _has_column("analysis_jobs", "general_model"):
        op.add_column("analysis_jobs", sa.Column("general_model", sa.String(length=128), nullable=True))
    if not _has_column("analysis_jobs", "classify_model"):
        op.add_column("analysis_jobs", sa.Column("classify_model", sa.String(length=128), nullable=True))

    if _has_table("runs") and _has_column("analysis_jobs", "run_id"):
        op.execute(
            """
            UPDATE analysis_jobs AS aj
            SET prompt_id = r.prompt_id,
                general_model = r.general_model,
                classify_model = r.classify_model
            FROM runs AS r
            WHERE aj.run_id = r.id
              AND aj.prompt_id IS NULL
            """
        )

    op.alter_column("analysis_jobs", "prompt_id", nullable=False)
    op.alter_column("analysis_jobs", "general_model", nullable=False)
    op.alter_column("analysis_jobs", "classify_model", nullable=False)
    if not _has_constraint("analysis_jobs", "fk_analysis_jobs_prompt_id_prompts"):
        op.create_foreign_key(
            "fk_analysis_jobs_prompt_id_prompts",
            "analysis_jobs",
            "prompts",
            ["prompt_id"],
            ["id"],
        )

    if _has_constraint("analysis_jobs", "uq_analysis_jobs_run_company"):
        op.drop_constraint("uq_analysis_jobs_run_company", "analysis_jobs", type_="unique")
    if not _has_constraint("analysis_jobs", "uq_analysis_jobs_pipeline_run_company"):
        op.create_unique_constraint(
            "uq_analysis_jobs_pipeline_run_company",
            "analysis_jobs",
            ["pipeline_run_id", "company_id"],
        )

    if _has_column("analysis_jobs", "run_id"):
        if _has_index("analysis_jobs", "ix_analysis_jobs_run_id"):
            op.drop_index("ix_analysis_jobs_run_id", table_name="analysis_jobs")
        if _has_constraint("analysis_jobs", "analysis_jobs_run_id_fkey"):
            op.drop_constraint("analysis_jobs_run_id_fkey", "analysis_jobs", type_="foreignkey")
        op.drop_column("analysis_jobs", "run_id")

    if _has_table("runs"):
        op.drop_table("runs")
    op.execute("DROP TYPE IF EXISTS runstatus")


def downgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_id", sa.Uuid(), nullable=False),
        sa.Column("general_model", sa.String(length=128), nullable=False),
        sa.Column("classify_model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_jobs", sa.Integer(), nullable=False),
        sa.Column("completed_jobs", sa.Integer(), nullable=False),
        sa.Column("failed_jobs", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"]),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("analysis_jobs", sa.Column("run_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_analysis_jobs_run_id"), "analysis_jobs", ["run_id"], unique=False)
    op.create_foreign_key("analysis_jobs_run_id_fkey", "analysis_jobs", "runs", ["run_id"], ["id"])

    if _has_constraint("analysis_jobs", "uq_analysis_jobs_pipeline_run_company"):
        op.drop_constraint("uq_analysis_jobs_pipeline_run_company", "analysis_jobs", type_="unique")
    if _has_constraint("analysis_jobs", "fk_analysis_jobs_prompt_id_prompts"):
        op.drop_constraint("fk_analysis_jobs_prompt_id_prompts", "analysis_jobs", type_="foreignkey")
    if _has_index("analysis_jobs", "ix_analysis_jobs_prompt_id"):
        op.drop_index("ix_analysis_jobs_prompt_id", table_name="analysis_jobs")
    op.drop_column("analysis_jobs", "classify_model")
    op.drop_column("analysis_jobs", "general_model")
    op.drop_column("analysis_jobs", "prompt_id")
