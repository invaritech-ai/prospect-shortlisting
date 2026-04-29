from __future__ import annotations

from sqlalchemy import inspect

from app.models import Contact, PipelineRun, ScrapeJob
from app.models.pipeline import (
    AnalysisJobState,
    ContactFetchBatchState,
    ContactFetchJobState,
    ContactProviderAttemptState,
    ContactVerifyJobState,
    PipelineRunStatus,
    PipelineStage,
    PredictedLabel,
)


def test_canonical_enum_values_are_lowercase() -> None:
    enums = [
        AnalysisJobState,
        ContactFetchBatchState,
        ContactFetchJobState,
        ContactProviderAttemptState,
        ContactVerifyJobState,
        PipelineRunStatus,
        PipelineStage,
        PredictedLabel,
    ]

    for enum_cls in enums:
        for item in enum_cls:
            assert item.value == item.value.lower()
            assert "-" not in item.value


def test_pipeline_stage_values_have_no_order_prefixes() -> None:
    assert {item.value for item in PipelineStage} == {
        "scrape",
        "analysis",
        "contacts",
        "validation",
    }


def test_contact_columns_use_canonical_provider_names() -> None:
    assert hasattr(Contact, "source_provider")
    assert not hasattr(Contact, "provider")
    assert hasattr(Contact, "verification_provider")


def test_scrape_and_pipeline_run_use_state_not_status() -> None:
    assert hasattr(ScrapeJob, "state")
    assert not hasattr(ScrapeJob, "status")
    assert hasattr(PipelineRun, "state")
    assert not hasattr(PipelineRun, "status")


def test_failure_reason_columns_exist(sqlite_engine) -> None:
    inspector = inspect(sqlite_engine)
    expected = {
        "scrapejob": "failure_reason",
        "crawl_jobs": "failure_reason",
        "contact_fetch_jobs": "failure_reason",
        "contact_provider_attempts": "failure_reason",
        "contact_reveal_attempts": "failure_reason",
    }

    for table, column_name in expected.items():
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert column_name in columns
