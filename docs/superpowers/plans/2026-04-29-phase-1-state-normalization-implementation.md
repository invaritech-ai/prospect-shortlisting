# Phase 1 State Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align database and backend code with `2026-04-29-state-vocabulary-spec.md`.

**Architecture:** Keep the migration boring and explicit: rename columns, rewrite values, add `failure_reason` columns, and update ORM/service code to use the new names directly. Do not add compatibility shims or old-value translation helpers. Drop `runs` only after replacing current code references with `pipeline_runs` or deleting dead routes.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, Alembic, Postgres, pytest, ruff.

---

## File Map

- Create: `alembic/versions/<new>_phase_1_state_normalization.py` — one data/schema migration for canonical vocabulary.
- Modify: `app/models/pipeline.py` — enum values, renamed columns, new columns, drop `Run`.
- Modify: `app/models/__init__.py`, `app/db/session.py`, `alembic/env.py` — remove `Run` imports after dropping `runs`.
- Modify: `app/models/scrape.py` — rename `ScrapeJob.status` to `state`, add `failure_reason`.
- Modify: `app/services/*.py`, `app/tasks/*.py`, `app/api/routes/*.py` — replace old state names and column references.
- Modify: `app/api/schemas/*.py` — response fields use `state`, lowercase labels, `source_provider`.
- Delete or rewrite: `app/api/routes/runs.py`, `app/api/schemas/run.py` — `runs` table is removed by Phase 1.
- Test: `tests/test_state_vocabulary.py` — DB/model contract tests.
- Test: existing focused tests for scrape creation, pipeline runs, contacts, settings.

## Task 1: State Vocabulary Contract Tests

**Files:**
- Create: `tests/test_state_vocabulary.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run test to verify RED**

Run: `uv run pytest tests/test_state_vocabulary.py -q`

Expected: FAIL because `ScrapeJob.status`, `PipelineRun.status`, `Contact.provider`, uppercase enums, and missing `failure_reason` still exist.

## Task 2: Alembic Migration

**Files:**
- Create: `alembic/versions/<new>_phase_1_state_normalization.py`

- [ ] **Step 1: Write migration**

Migration must do these operations explicitly:

```text
scrapejob.status -> scrapejob.state
pipeline_runs.status -> pipeline_runs.state
contacts.provider -> contacts.source_provider
contacts.verification_provider added nullable
failure_reason added nullable to scrapejob, crawl_jobs, contact_fetch_jobs, contact_provider_attempts, contact_reveal_attempts
classification_results.predicted_label values POSSIBLE/CRAP/UNKNOWN -> possible/crap/unknown
crawl_jobs.state and analysis_jobs.state values SUCCEEDED/FAILED/DEAD/etc. -> lowercase
scrapejob completed -> succeeded
scrapejob site_unavailable -> state failed + failure_reason site_unavailable
scrapejob step1_failed -> state failed + failure_reason step1_failed
contact_fetch_batches completed -> succeeded
pipeline_runs running older rows -> dead
pipeline stage values s1_scrape/s2_analysis/s3_contacts/s4_validation -> scrape/analysis/contacts/validation
drop runs after dropping analysis_jobs.run_id FK/column and route references
```

- [ ] **Step 2: Verify migration against a disposable DB**

Run: `uv run alembic upgrade head`

Expected: migration applies cleanly.

## Task 3: Models and Schemas

**Files:**
- Modify: `app/models/pipeline.py`
- Modify: `app/models/scrape.py`
- Modify: `app/models/__init__.py`
- Modify: `app/db/session.py`
- Modify: `alembic/env.py`
- Modify: `app/api/schemas/pipeline_run.py`
- Modify: `app/api/schemas/contacts.py`

- [ ] **Step 1: Update model field names**

Use direct names:

```text
PipelineRun.state
ScrapeJob.state
Contact.source_provider
Contact.verification_provider
*.failure_reason
```

- [ ] **Step 2: Update enum values**

Use only values in `2026-04-29-state-vocabulary-spec.md`.

- [ ] **Step 3: Remove `Run` model exports**

Delete `Run` and `RunStatus` from imports/exports after route/service references are removed.

## Task 4: Service and Route Updates

**Files:**
- Modify: `app/services/analysis_service.py`
- Modify: `app/services/company_service.py`
- Modify: `app/services/contact_*service.py`
- Modify: `app/services/pipeline_run_orchestrator.py`
- Modify: `app/services/scrape_service.py`
- Modify: `app/tasks/*.py`
- Modify: `app/api/routes/*.py`

- [ ] **Step 1: Replace renamed columns**

Search and replace intentionally, then review every match:

```text
ScrapeJob.status -> ScrapeJob.state
PipelineRun.status -> PipelineRun.state
Contact.provider -> Contact.source_provider
```

- [ ] **Step 2: Replace old values**

Use:

```text
completed -> succeeded
s1_scrape -> scrape
s2_analysis -> analysis
s3_contacts -> contacts
s4_validation -> validation
POSSIBLE/CRAP/UNKNOWN -> possible/crap/unknown
```

- [ ] **Step 3: Remove `func.lower()` case shims**

Run: `rg -n "func\\.lower\\(" app`

Expected: no case-shim use for state/stage/label comparisons. `func.lower()` may remain for user search text.

## Task 5: Drop Runs Surface

**Files:**
- Delete: `app/api/routes/runs.py`
- Delete: `app/api/schemas/run.py`
- Modify: route registration file if present.
- Modify: prompt routes that count `Run` rows.
- Modify: tests that construct `Run`.

- [ ] **Step 1: Remove route and schema**

Delete the legacy `runs` API surface. Replace prompt usage counts with zero or with pipeline-run-based usage only if the relation is direct and obvious.

- [ ] **Step 2: Remove analysis dependency on `Run`**

Analysis jobs should get prompt/model context from fields already on `AnalysisJob`, `PipelineRun`, or snapshots. If the value is unavailable, fail plainly instead of recreating `runs`.

## Task 6: Verification

**Files:**
- Test files touched by the implementation.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_state_vocabulary.py -q
uv run pytest tests/test_settings_api.py tests/test_contact_verify.py tests/test_pipeline_runs.py -q
```

- [ ] **Step 2: Run lint**

Run:

```bash
uv run ruff check app tests
```

- [ ] **Step 3: Run migration verification SQL**

Against the target DB:

```sql
select distinct state from scrapejob;
select distinct state from pipeline_runs;
select distinct state from analysis_jobs;
select distinct predicted_label from classification_results;
select distinct pipeline_stage from contacts;
select distinct source_provider from contacts;
```

Expected: all values are lowercase canonical values from the spec.

## Self-Review

- Spec coverage: every Phase 1 acceptance criterion maps to a task above.
- Simplicity check: no compatibility layers, no adapter functions, no parallel old/new fields beyond the migration boundary.
- Known risk: dropping `runs` is the largest blast radius. If it blocks a clean implementation, stop and report the exact remaining consumers instead of half-dropping it.
