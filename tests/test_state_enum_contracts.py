from __future__ import annotations

from sqlalchemy import Enum as SAEnum

from app.api.routes.stats import PipelineStageStats
from app.api.schemas.pipeline_run import PipelineStageProgressRead
from app.models.pipeline import (
    AnalysisJob,
    AnalysisJobState,
    ClassificationResult,
    ContactFetchJob,
    ContactFetchJobState,
    ContactRevealJob,
    CrawlJob,
    CrawlJobState,
    JobEvent,
    JobType,
    PredictedLabel,
    Run,
    RunStatus,
)


def _enum_values(enum_cls: type) -> list[str]:
    return [member.value for member in enum_cls]


def test_native_db_enum_columns_bind_python_values() -> None:
    expected = {
        (CrawlJob, "state"): _enum_values(CrawlJobState),
        (Run, "status"): _enum_values(RunStatus),
        (AnalysisJob, "state"): _enum_values(AnalysisJobState),
        (ClassificationResult, "predicted_label"): _enum_values(PredictedLabel),
        (JobEvent, "job_type"): _enum_values(JobType),
        (ContactFetchJob, "state"): _enum_values(ContactFetchJobState),
        (ContactRevealJob, "state"): _enum_values(ContactFetchJobState),
    }

    for (model, column_name), values in expected.items():
        column_type = model.__table__.c[column_name].type
        assert isinstance(column_type, SAEnum)
        assert column_type.enums == values


def test_pipeline_progress_api_uses_succeeded_not_completed() -> None:
    assert "succeeded" in PipelineStageProgressRead.model_fields
    assert "completed" not in PipelineStageProgressRead.model_fields
    assert "succeeded" in PipelineStageStats.model_fields
    assert "completed" not in PipelineStageStats.model_fields
