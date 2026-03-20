"""add indexes on updated_at and lock_expires_at for stuck-job queries

Revision ID: a1b2c3d4e5f7
Revises: f7e8d9c0b1a2
Create Date: 2026-03-20 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f7e8d9c0b1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ScrapeJob.updated_at — used in beat reconciler stuck-job query
    op.create_index("ix_scrapejob_updated_at", "scrapejob", ["updated_at"])

    # AnalysisJob.updated_at — used in beat reconciler stuck-job query
    op.create_index("ix_analysis_jobs_updated_at", "analysis_jobs", ["updated_at"])

    # AnalysisJob.lock_expires_at — used in stats stuck-count query
    op.create_index("ix_analysis_jobs_lock_expires_at", "analysis_jobs", ["lock_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_lock_expires_at", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_updated_at", table_name="analysis_jobs")
    op.drop_index("ix_scrapejob_updated_at", table_name="scrapejob")
