"""pipeline_perf_indexes

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-01 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "e4f5a6b7c8d9"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_classification_results_campaign_effective_label
        ON classification_results (campaign_id, lower(coalesce(manual_label, predicted_label)));
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_classification_results_campaign_domain_created
        ON classification_results (campaign_id, domain_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scrape_results_campaign_domain_updated
        ON scrape_results (campaign_id, domain_id, updated_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_uploaded_domains_campaign_scrape_domain
        ON uploaded_domains (campaign_id, scrape_status, domain);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scrape_batches_campaign_state_created
        ON scrape_batches (campaign_id, state, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_classification_batches_campaign_state_created
        ON classification_batches (campaign_id, state, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_email_fetch_batches_campaign_state_created
        ON email_fetch_batches (campaign_id, state, created_at DESC);
        """
    )
    op.execute("ANALYZE uploaded_domains;")
    op.execute("ANALYZE classification_results;")
    op.execute("ANALYZE scrape_results;")
    op.execute("ANALYZE scrape_batches;")
    op.execute("ANALYZE classification_batches;")
    op.execute("ANALYZE email_fetch_batches;")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_fetch_batches_campaign_state_created;")
    op.execute("DROP INDEX IF EXISTS ix_classification_batches_campaign_state_created;")
    op.execute("DROP INDEX IF EXISTS ix_scrape_batches_campaign_state_created;")
    op.execute("DROP INDEX IF EXISTS ix_uploaded_domains_campaign_scrape_domain;")
    op.execute("DROP INDEX IF EXISTS ix_scrape_results_campaign_domain_updated;")
    op.execute("DROP INDEX IF EXISTS ix_classification_results_campaign_domain_created;")
    op.execute("DROP INDEX IF EXISTS ix_classification_results_campaign_effective_label;")
