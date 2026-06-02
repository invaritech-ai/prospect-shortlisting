"""backfill_domain_fetch_updated_at

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-06-02 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        UPDATE uploaded_domains AS domains
        SET fetch_updated_at = attempts.latest_fetch_at
        FROM (
            SELECT
                selected.domain_id::uuid AS domain_id,
                max(coalesce(batches.finished_at, batches.created_at)) AS latest_fetch_at
            FROM email_fetch_batches AS batches
            CROSS JOIN LATERAL jsonb_array_elements_text(
                batches.selected_domain_ids_json::jsonb
            ) AS selected(domain_id)
            WHERE batches.selected_domain_ids_json IS NOT NULL
            GROUP BY selected.domain_id::uuid
        ) AS attempts
        WHERE domains.id = attempts.domain_id
          AND domains.fetch_updated_at IS NULL
          AND domains.fetch_status IS NOT NULL;
        """
    )


def downgrade() -> None:
    pass
