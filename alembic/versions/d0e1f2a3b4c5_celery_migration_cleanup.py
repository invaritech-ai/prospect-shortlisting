"""Celery migration cleanup: drop job_outbox, remove OCR/step columns

Revision ID: d0e1f2a3b4c5
Revises: c4d5e6f7a8b9
Create Date: 2026-03-19 00:00:00.000000

Changes:
- Drop job_outbox table (outbox pattern replaced by direct Celery task.delay())
- Drop ocr_model column from runs (OCR pipeline removed)
- Drop OCR/step1/step2 columns from scrapejob
- Drop OCR/screenshot columns from scrapepage
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_column_if_exists(table: str, column: str) -> None:
    """Drop a column only if it exists (handles re-entrant migrations)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column in cols:
        op.drop_column(table, column)


def _add_column_if_missing(table: str, column: str, col_def: sa.Column) -> None:  # type: ignore[type-arg]
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column not in cols:
        op.add_column(table, col_def)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Drop the job_outbox table
    # ------------------------------------------------------------------
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "job_outbox" in inspector.get_table_names():
        op.drop_table("job_outbox")

    # ------------------------------------------------------------------
    # 2. runs: drop ocr_model column
    # ------------------------------------------------------------------
    _drop_column_if_exists("runs", "ocr_model")

    # ------------------------------------------------------------------
    # 3. scrapejob: drop removed columns
    #    (stage1_status, stage2_status, ocr_model, enable_ocr,
    #     max_images_per_page, ocr_images_processed_count,
    #     step1_started_at, step1_finished_at,
    #     step2_started_at, step2_finished_at,
    #     max_pages, max_depth)
    # ------------------------------------------------------------------
    if "scrapejob" in inspector.get_table_names():
        for col in [
            "stage1_status",
            "stage2_status",
            "ocr_model",
            "enable_ocr",
            "max_images_per_page",
            "ocr_images_processed_count",
            "step1_started_at",
            "step1_finished_at",
            "step2_started_at",
            "step2_finished_at",
            "max_pages",
            "max_depth",
        ]:
            _drop_column_if_exists("scrapejob", col)

        # Ensure started_at and finished_at exist (may already be present)
        _add_column_if_missing(
            "scrapejob",
            "started_at",
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            "scrapejob",
            "finished_at",
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ------------------------------------------------------------------
    # 4. scrapepage: drop removed columns
    #    (html_snapshot, image_urls_json, ocr_text)
    # ------------------------------------------------------------------
    if "scrapepage" in inspector.get_table_names():
        for col in ["html_snapshot", "image_urls_json", "ocr_text"]:
            _drop_column_if_exists("scrapepage", col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Restore ocr_model on runs
    _add_column_if_missing(
        "runs",
        "ocr_model",
        sa.Column("ocr_model", sa.String(length=128), nullable=True),
    )

    # Restore scrapejob columns
    if "scrapejob" in inspector.get_table_names():
        for col_name, col_def in [
            ("stage1_status", sa.Column("stage1_status", sa.String(length=64), nullable=True)),
            ("stage2_status", sa.Column("stage2_status", sa.String(length=64), nullable=True)),
            ("ocr_model", sa.Column("ocr_model", sa.String(length=128), nullable=True)),
            ("enable_ocr", sa.Column("enable_ocr", sa.Boolean(), nullable=True)),
            ("max_images_per_page", sa.Column("max_images_per_page", sa.Integer(), nullable=True)),
            ("ocr_images_processed_count", sa.Column("ocr_images_processed_count", sa.Integer(), nullable=True)),
            ("step1_started_at", sa.Column("step1_started_at", sa.DateTime(timezone=True), nullable=True)),
            ("step1_finished_at", sa.Column("step1_finished_at", sa.DateTime(timezone=True), nullable=True)),
            ("step2_started_at", sa.Column("step2_started_at", sa.DateTime(timezone=True), nullable=True)),
            ("step2_finished_at", sa.Column("step2_finished_at", sa.DateTime(timezone=True), nullable=True)),
            ("max_pages", sa.Column("max_pages", sa.Integer(), nullable=True)),
            ("max_depth", sa.Column("max_depth", sa.Integer(), nullable=True)),
        ]:
            _add_column_if_missing("scrapejob", col_name, col_def)

    # Restore scrapepage columns
    if "scrapepage" in inspector.get_table_names():
        for col_name, col_def in [
            ("html_snapshot", sa.Column("html_snapshot", sa.Text(), nullable=True)),
            ("image_urls_json", sa.Column("image_urls_json", sa.Text(), nullable=True)),
            ("ocr_text", sa.Column("ocr_text", sa.Text(), nullable=True)),
        ]:
            _add_column_if_missing("scrapepage", col_name, col_def)
