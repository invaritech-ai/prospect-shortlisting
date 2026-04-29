# Phase 1.5 Hard Delete Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the legacy `runs` lifecycle so `pipeline_runs` and `analysis_jobs` become the analysis source of truth.

**Architecture:** Delete the public `/v1/runs` API and the `Run` model/table. Move the analysis prompt/model inputs that were previously read through `Run` onto each `AnalysisJob`, keeping execution simple and local to the job row. Preserve `pipeline_run_id` as the orchestration link.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, Alembic, PostgreSQL. Do not run SQLite-backed tests.

---

## File Map

- Delete: `app/api/routes/runs.py`
- Delete: `app/api/schemas/run.py`
- Delete: `app/services/run_service.py`
- Modify: `app/main.py`
  Remove `runs_router` import and registration.
- Modify: `app/api/schemas/__init__.py`
  Remove legacy run schema exports.
- Modify: `app/models/pipeline.py`
  Remove `RunStatus` and `Run`; change `AnalysisJob` from `run_id` to direct `prompt_id`, `general_model`, `classify_model`.
- Modify: `app/models/__init__.py`
  Stop exporting `Run`.
- Modify: `app/db/session.py`
  Stop importing `Run`.
- Modify: `alembic/env.py`
  Stop importing `Run`.
- Modify: `app/api/routes/pipeline_runs.py`
  Create `AnalysisJob` rows directly instead of using `RunService`.
- Modify: `app/api/routes/analysis.py`
  Replace legacy `/runs/{run_id}/jobs` with `/pipeline-runs/{pipeline_run_id}/analysis-jobs`; load prompt/model details from `AnalysisJob`.
- Modify: `app/api/routes/prompts.py`
  Count prompt usage through `AnalysisJob.prompt_id`.
- Modify: `app/api/routes/queue_admin.py`
  Remove `/runs/refresh-status`.
- Modify: `app/services/analysis_service.py`
  Load prompt/model data directly from `AnalysisJob`.
- Create: `alembic/versions/3c4d5e6f7081_drop_legacy_runs.py`
  Backfill `analysis_jobs.prompt_id/general_model/classify_model` from `runs`, drop `analysis_jobs.run_id`, drop `runs`, drop `runstatus`.
- Test: `tests/test_state_enum_contracts.py`
  Remove `Run` enum binding expectations.
- Optional cleanup in SQLite-only tests may be made for import health, but do not run them.

## Tasks

### Task 1: Remove Public Runs API

- [ ] Delete `app/api/routes/runs.py` and `app/api/schemas/run.py`.
- [ ] Remove `runs_router` import and `app.include_router(runs_router)` from `app/main.py`.
- [ ] Remove run schema exports from `app/api/schemas/__init__.py`.

### Task 2: Move Analysis Job Inputs Onto AnalysisJob

- [ ] In `app/models/pipeline.py`, remove `RunStatus` and `Run`.
- [ ] Change `AnalysisJob.__table_args__` to a pipeline-run/company uniqueness constraint.
- [ ] Replace `run_id` with:

```python
prompt_id: UUID = Field(foreign_key="prompts.id", index=True)
general_model: str = Field(max_length=128)
classify_model: str = Field(max_length=128)
```

- [ ] Update model exports/import registries.

### Task 3: Rebuild Analysis Queue Creation

- [ ] Replace `RunService.create_runs` usage in `app/api/routes/pipeline_runs.py` with direct `AnalysisJob` creation.
- [ ] Keep the existing behavior: only create analysis jobs for companies with completed scrape artifacts.
- [ ] Store `prompt_id`, `general_model`, and `classify_model` on each `AnalysisJob`.
- [ ] Enqueue `run_analysis_job.delay(str(job.id))` after commit.

### Task 4: Rebuild Analysis Execution Reads

- [ ] In `app/services/analysis_service.py`, load `Prompt` via `analysis_job.prompt_id`.
- [ ] Use `analysis_job.classify_model` for the LLM call.
- [ ] Remove `RunService.refresh_run_status` calls.
- [ ] Keep `pipeline_run_id` usage for AI usage events and S3 orchestration.

### Task 5: Rebuild Read APIs On PipelineRun

- [ ] In `app/api/routes/analysis.py`, replace `/runs/{run_id}/jobs` with `/pipeline-runs/{pipeline_run_id}/analysis-jobs`.
- [ ] Return `pipeline_run_id` instead of `run_id` in analysis schemas.
- [ ] In prompt routes, use `AnalysisJob.prompt_id` for `run_count` until the response field is renamed later.

### Task 6: Drop Legacy DB Objects

- [ ] Add Alembic migration `3c4d5e6f7081_drop_legacy_runs.py`.
- [ ] Backfill new `analysis_jobs` columns from `runs`.
- [ ] Drop `analysis_jobs.run_id`.
- [ ] Drop `runs`.
- [ ] Drop PostgreSQL enum type `runstatus`.
- [ ] Apply to live DB after code compiles.

### Task 7: Non-SQLite Verification

- [ ] Run focused ruff.
- [ ] Run import/compile checks.
- [ ] Query live Postgres for absence of `runs` and `runstatus`.
- [ ] Do not run SQLite-backed tests.

## Acceptance Criteria

- `rg "\bRun\b|RunStatus|runs_router|app.api.schemas.run|app.services.run_service" app alembic tests/test_state_enum_contracts.py` has no active backend dependency.
- FastAPI app imports without the legacy runs router.
- `analysis_jobs` has `prompt_id`, `general_model`, `classify_model`, and no `run_id`.
- Live DB has no `runs` table and no `runstatus` enum.
- No SQLite tests were run.
