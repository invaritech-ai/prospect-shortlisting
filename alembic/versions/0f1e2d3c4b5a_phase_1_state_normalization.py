"""phase 1 state normalization

Revision ID: 0f1e2d3c4b5a
Revises: 757c366889ba
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0f1e2d3c4b5a"
down_revision = "757c366889ba"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _rename_column_if_exists(table_name: str, old_name: str, new_name: str) -> None:
    if _has_column(table_name, old_name) and not _has_column(table_name, new_name):
        op.alter_column(table_name, old_name, new_column_name=new_name)


def _add_failure_reason(table_name: str) -> None:
    if not _has_column(table_name, "failure_reason"):
        op.add_column(table_name, sa.Column("failure_reason", sa.String(length=128), nullable=True))
        op.create_index(op.f(f"ix_{table_name}_failure_reason"), table_name, ["failure_reason"], unique=False)


def _rename_enum_value(enum_name: str, old: str, new: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"ALTER TYPE {enum_name} RENAME VALUE '{old}' TO '{new}'")


def upgrade() -> None:
    _rename_enum_value("predictedlabel", "POSSIBLE", "possible")
    _rename_enum_value("predictedlabel", "CRAP", "crap")
    _rename_enum_value("predictedlabel", "UNKNOWN", "unknown")
    for enum_name in ("crawljobstate", "analysisjobstate"):
        _rename_enum_value(enum_name, "QUEUED", "queued")
        _rename_enum_value(enum_name, "RUNNING", "running")
        _rename_enum_value(enum_name, "SUCCEEDED", "succeeded")
        _rename_enum_value(enum_name, "FAILED", "failed")
        _rename_enum_value(enum_name, "DEAD", "dead")
    _rename_enum_value("runstatus", "CREATED", "created")
    _rename_enum_value("runstatus", "RUNNING", "running")
    _rename_enum_value("runstatus", "COMPLETED", "succeeded")
    _rename_enum_value("runstatus", "FAILED", "failed")

    _rename_column_if_exists("scrapejob", "status", "state")
    _rename_column_if_exists("pipeline_runs", "status", "state")
    _rename_column_if_exists("contacts", "provider", "source_provider")

    if not _has_column("contacts", "verification_provider"):
        op.add_column("contacts", sa.Column("verification_provider", sa.String(length=32), nullable=True))
        op.create_index(op.f("ix_contacts_verification_provider"), "contacts", ["verification_provider"], unique=False)

    for table_name in (
        "scrapejob",
        "crawl_jobs",
        "contact_fetch_jobs",
        "contact_provider_attempts",
        "contact_reveal_attempts",
    ):
        _add_failure_reason(table_name)

    op.execute(
        """
        UPDATE scrapejob
        SET failure_reason = CASE
                WHEN state = 'site_unavailable' THEN 'site_unavailable'
                WHEN state = 'step1_failed' THEN 'step1_failed'
                ELSE failure_reason
            END,
            state = CASE
                WHEN state IN ('completed') THEN 'succeeded'
                WHEN state IN ('site_unavailable', 'step1_failed') THEN 'failed'
                ELSE state
            END
        """
    )
    op.execute("UPDATE contact_fetch_batches SET state = 'succeeded' WHERE state = 'completed'")
    op.execute("UPDATE contact_reveal_batches SET state = 'succeeded' WHERE state = 'completed'")
    op.execute("UPDATE pipeline_runs SET state = 'dead' WHERE state = 'running'")
    op.execute("UPDATE pipeline_run_events SET stage = 'scrape' WHERE stage = 's1_scrape'")
    op.execute("UPDATE pipeline_run_events SET stage = 'analysis' WHERE stage = 's2_analysis'")
    op.execute("UPDATE pipeline_run_events SET stage = 'contacts' WHERE stage = 's3_contacts'")
    op.execute("UPDATE pipeline_run_events SET stage = 'validation' WHERE stage = 's4_validation'")
    op.execute("UPDATE ai_usage_events SET stage = 'scrape' WHERE stage = 's1_scrape'")
    op.execute("UPDATE ai_usage_events SET stage = 'analysis' WHERE stage = 's2_analysis'")
    op.execute("UPDATE ai_usage_events SET stage = 'contacts' WHERE stage = 's3_contacts'")
    op.execute("UPDATE ai_usage_events SET stage = 'validation' WHERE stage = 's4_validation'")


def downgrade() -> None:
    op.execute("UPDATE ai_usage_events SET stage = 's1_scrape' WHERE stage = 'scrape'")
    op.execute("UPDATE ai_usage_events SET stage = 's2_analysis' WHERE stage = 'analysis'")
    op.execute("UPDATE ai_usage_events SET stage = 's3_contacts' WHERE stage = 'contacts'")
    op.execute("UPDATE ai_usage_events SET stage = 's4_validation' WHERE stage = 'validation'")
    op.execute("UPDATE pipeline_run_events SET stage = 's1_scrape' WHERE stage = 'scrape'")
    op.execute("UPDATE pipeline_run_events SET stage = 's2_analysis' WHERE stage = 'analysis'")
    op.execute("UPDATE pipeline_run_events SET stage = 's3_contacts' WHERE stage = 'contacts'")
    op.execute("UPDATE pipeline_run_events SET stage = 's4_validation' WHERE stage = 'validation'")
    op.execute("UPDATE contact_reveal_batches SET state = 'completed' WHERE state = 'succeeded'")
    op.execute("UPDATE contact_fetch_batches SET state = 'completed' WHERE state = 'succeeded'")
    op.execute(
        """
        UPDATE scrapejob
        SET state = CASE
                WHEN failure_reason = 'site_unavailable' THEN 'site_unavailable'
                WHEN failure_reason = 'step1_failed' THEN 'step1_failed'
                WHEN state = 'succeeded' THEN 'completed'
                ELSE state
            END
        """
    )

    for table_name in (
        "contact_reveal_attempts",
        "contact_provider_attempts",
        "contact_fetch_jobs",
        "crawl_jobs",
        "scrapejob",
    ):
        if _has_column(table_name, "failure_reason"):
            op.drop_index(op.f(f"ix_{table_name}_failure_reason"), table_name=table_name)
            op.drop_column(table_name, "failure_reason")

    if _has_column("contacts", "verification_provider"):
        op.drop_index(op.f("ix_contacts_verification_provider"), table_name="contacts")
        op.drop_column("contacts", "verification_provider")

    _rename_column_if_exists("contacts", "source_provider", "provider")
    _rename_column_if_exists("pipeline_runs", "state", "status")
    _rename_column_if_exists("scrapejob", "state", "status")

    _rename_enum_value("runstatus", "failed", "FAILED")
    _rename_enum_value("runstatus", "succeeded", "COMPLETED")
    _rename_enum_value("runstatus", "running", "RUNNING")
    _rename_enum_value("runstatus", "created", "CREATED")
    _rename_enum_value("analysisjobstate", "dead", "DEAD")
    _rename_enum_value("analysisjobstate", "failed", "FAILED")
    _rename_enum_value("analysisjobstate", "succeeded", "SUCCEEDED")
    _rename_enum_value("analysisjobstate", "running", "RUNNING")
    _rename_enum_value("analysisjobstate", "queued", "QUEUED")
    _rename_enum_value("crawljobstate", "dead", "DEAD")
    _rename_enum_value("crawljobstate", "failed", "FAILED")
    _rename_enum_value("crawljobstate", "succeeded", "SUCCEEDED")
    _rename_enum_value("crawljobstate", "running", "RUNNING")
    _rename_enum_value("crawljobstate", "queued", "QUEUED")
    _rename_enum_value("predictedlabel", "unknown", "UNKNOWN")
    _rename_enum_value("predictedlabel", "crap", "CRAP")
    _rename_enum_value("predictedlabel", "possible", "POSSIBLE")
