# Manual S2 AI Decision Design

Date: 2026-05-01

## Goal

Restore S2 as a manual stage that lets an operator:

- select companies that already have scraped info
- choose a saved matching prompt
- create AI decision jobs for those companies
- observe run-level progress from the frontend

This design does not add automatic S1 -> S2 progression. It only restores the manual S2 operator flow.

## Scope

Manual S2 needs three operator capabilities:

1. Select matching criteria
2. CRUD prompts for matching
3. Trigger AI decision with the selected prompt

For this phase, "matching criteria" means:

- the operator's current company selection in S2
- one eligibility gate: company must have scraped info
- the selected saved prompt

No second structured filter system is required.

## Current Shape

The codebase already contains most of the S2 building blocks:

- The frontend S2 view already supports row selection, per-row classify, and prompt selection.
- Prompt CRUD already exists in `app/api/routes/prompts.py`.
- `apps/web/src/hooks/usePromptManagement.ts` and `apps/web/src/components/panels/PromptLibraryPanel.tsx` already support create, update, enable/disable, clone, and delete.
- `AnalysisService.run_analysis_job()` already performs the actual classification work.
- `app/jobs/ai_decision.py` exists, but it is still a stub.
- `apps/web/src/lib/api.ts` already posts to `/v1/pipeline-runs/start`, but the backend route is missing.

The result is that the UI and prompt library largely exist, but the manual S2 dispatch path is incomplete.

## Eligibility Rule

S2 must only accept companies with scraped info.

The backend should be authoritative here. The current best existing rule is already encoded by `latest_usable_scrape()` in `app/services/pipeline_service.py`:

- the company must have a latest `ScrapeJob`
- that scrape job must have `state == "succeeded"`
- that scrape job must have `markdown_pages_count > 0`

The frontend may use existing company list fields to guide button states, but the backend must re-check eligibility before creating any `AnalysisJob`.

## Recommended Approach

Use the existing frontend and prompt CRUD as-is, and add a thin backend orchestration layer for manual S2.

The restored flow should be:

1. Operator enters S2 and filters/selects companies.
2. Operator chooses a saved prompt from the existing prompt library drawer.
3. Frontend sends `POST /v1/pipeline-runs/start` with `campaign_id`, `company_ids`, and `analysis_prompt_snapshot`.
4. Backend validates:
   - campaign scope
   - prompt exists and is enabled
   - each company belongs to the campaign
   - each company has scraped info
5. Backend creates one `PipelineRun`.
6. Backend creates one `AnalysisJob` per eligible company.
7. Backend defers one `run_ai_decision` Procrastinate task per created `AnalysisJob`.
8. Worker executes `AnalysisService.run_analysis_job()`.
9. Frontend polls run progress and per-job detail endpoints that already fit the current UI shape.

This is the smallest change that makes S2 real again without redesigning prompt management or coupling S2 to automatic pipeline orchestration.

## Backend Design

### Route layer

Add a dedicated route module for pipeline runs.

Endpoints:

- `POST /v1/pipeline-runs/start`
- `GET /v1/pipeline-runs/{pipeline_run_id}/progress`

`POST /start` should support manual S2 only for now. It does not need to enqueue scrape, contact, or validation work.

### Orchestration

The route should create:

- one `PipelineRun`
- one `AnalysisJob` per eligible company

`AnalysisJob` requires `crawl_artifact_id`, so orchestration must also ensure the crawl adapter bridge exists for scraped companies. The repo already has `bulk_ensure_crawl_adapters()` in `app/services/context_service.py` for this exact purpose.

The orchestration flow should be:

1. Load campaign-scoped companies for submitted IDs.
2. Resolve the selected prompt from `analysis_prompt_snapshot.prompt_id`.
3. Build a scrape map for those companies from latest usable scrape jobs.
4. Split companies into:
   - eligible: has usable scrape
   - skipped: missing usable scrape
5. Call `bulk_ensure_crawl_adapters()` for eligible companies.
6. Create `AnalysisJob` rows using:
   - `upload_id`
   - `company_id`
   - `crawl_artifact_id`
   - `prompt_id`
   - `general_model = settings.general_model`
   - `classify_model = settings.classify_model`
   - `prompt_hash = sha256(prompt.prompt_text).hexdigest()[:32]`
   - `pipeline_run_id = run.id`
7. Commit.
8. Defer one `run_ai_decision` task per created job.
9. Update `PipelineRun` counts.

If deferring fails for some jobs, the run should record those failures instead of pretending everything queued successfully.

### Worker

Replace the S2 task stub with a thin worker wrapper:

- parse `analysis_job_id`
- load engine
- call `AnalysisService.run_analysis_job(engine=..., analysis_job_id=...)`

The worker should not duplicate analysis logic that already exists in `AnalysisService`.

### Progress

`GET /v1/pipeline-runs/{id}/progress` should aggregate `AnalysisJob` states for the run and return:

- queued
- running
- succeeded
- failed
- total

Run state should be computed from the run and job counters:

- `queued` or `running` jobs -> run is `running`
- all jobs terminal and no failures -> run is `succeeded`
- all jobs terminal and at least one failed/dead -> run is `failed`

This is enough for the current S2 header progress bar.

## Frontend Design

Keep the current S2 interaction model.

### Matching criteria

Do not add a new filter-builder UI.

For this phase, matching criteria remains:

- whatever the operator selected in S2
- only companies that already have scraped info
- the selected prompt

### Prompt CRUD

Reuse the current prompt library flow:

- `listPrompts()`
- `createPrompt()`
- `updatePrompt()`
- `deletePrompt()`
- enabled/disabled state

No schema changes are required for prompts in this phase.

### Trigger flow

Keep `createRuns()` as the frontend entry point, but make it return real queued/skipped counts from the backend instead of placeholders.

The UI should:

- prevent analysis when no enabled prompt is selected
- surface how many companies were queued vs skipped
- continue supporting both bulk and per-row S2 actions

## Error Handling

Expected operator-facing failures:

- prompt missing or disabled
- no campaign selected
- submitted company IDs outside campaign scope
- selected companies have no scraped info
- task defer failure for a subset of jobs

Backend responses should keep the run truthful:

- `requested_count`: submitted companies
- `queued_count`: jobs actually deferred
- `skipped_count`: ineligible companies
- `failed_count`: records created but task defer failed, or other per-company enqueue failures

The system should not silently treat skipped companies as queued work.

## Testing

Add focused backend coverage for:

- prompt selection and enabled validation
- campaign/company scope validation
- eligibility gate for scraped info
- adapter creation via `bulk_ensure_crawl_adapters()`
- `PipelineRun` and `AnalysisJob` creation counts
- Procrastinate defer calls
- run progress aggregation
- worker task invoking `AnalysisService.run_analysis_job()`

Frontend tests only need contract updates where the API response shape changes.

## Non-goals

This design intentionally does not include:

- automatic S1 -> S2 enqueue
- prompt schema redesign
- a second structured filter system
- S2-specific UI redesign
- contact pipeline changes beyond preserving existing `AnalysisService` behavior

## Result

After this work:

- S2 prompt CRUD remains intact
- the operator can select a prompt and run manual S2
- only companies with scraped info are eligible
- manual S2 work is queued through Procrastinate
- the frontend can show real progress for each analysis run
