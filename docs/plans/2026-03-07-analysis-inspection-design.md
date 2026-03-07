# Analysis Inspection Design

## Summary

The next logical slice is operator-facing inspection for completed and in-flight analysis work. The classification pipeline already stores enough data to explain outcomes: `analysis_jobs`, `classification_results.reasoning_json`, and `classification_results.evidence_json`. What is missing is a coherent inspection surface that lets the operator move from run status to company-level evidence without leaving the main console.

The chosen design is run-centric:

- `Analysis Runs` remains the index.
- Clicking a run opens a right-side drilldown drawer.
- The drawer first shows run metadata and the company jobs in that run.
- Clicking a company job switches the drawer into evidence mode for that job.

This is preferred over a company-first design because runs are the execution unit. Prompt choice, failures, and progress all attach to runs, so inspection should anchor there.

## Goals

- Let the operator inspect all jobs within a run.
- Let the operator see why a company was classified the way it was.
- Reuse stored evidence and reasoning without adding new persistence.
- Preserve the current operator-console density and navigation patterns.

## Non-Goals

- Retry failed jobs.
- Edit evidence or reasoning.
- Show screenshots, OCR text, or raw scraped HTML in this slice.
- Add a separate standalone analysis screen.

## Backend Design

### New read endpoints

Add read-only analysis inspection endpoints:

- `GET /v1/runs/{run_id}/jobs`
- `GET /v1/analysis-jobs/{analysis_job_id}`

These should live in a dedicated route module, not inside `uploads.py`.

Recommended file:

- `app/api/routes/analysis.py`

### `GET /v1/runs/{run_id}/jobs`

Purpose: provide the run drilldown table.

Response item fields:

- `analysis_job_id`
- `run_id`
- `company_id`
- `domain`
- `state`
- `terminal_state`
- `last_error_code`
- `last_error_message`
- `predicted_label`
- `confidence`
- `created_at`
- `started_at`
- `finished_at`

Ordering:

- `companies.domain ASC` for operator scanning

Behavior:

- return jobs even when no `classification_result` exists yet
- in that case `predicted_label` and `confidence` stay null

### `GET /v1/analysis-jobs/{analysis_job_id}`

Purpose: provide the evidence view for one classified company job.

Response fields:

- job metadata:
  - `analysis_job_id`
  - `run_id`
  - `company_id`
  - `domain`
  - `state`
  - `terminal_state`
  - `last_error_code`
  - `last_error_message`
  - `created_at`
  - `started_at`
  - `finished_at`
- run metadata:
  - `prompt_name`
  - `run_status`
- classification fields:
  - `predicted_label`
  - `confidence`
  - `reasoning_json`
  - `evidence_json`

### Service boundary

Use a read service or dedicated query helpers that:

- join `analysis_jobs` -> `companies`
- left join `classification_results`
- join `runs` and `prompts` where needed

Keep route handlers thin and return explicit response schemas.

### Error handling

- `404` if run/job does not exist
- if job exists but no result exists yet, return the job with nullable classification fields
- do not synthesize fake evidence or placeholder labels

## Frontend Design

### Entry point

Inside `Analysis Runs`, each run row gets an `Inspect` action.

### Drawer model

Use one right-side drawer with two modes:

1. Run mode
2. Evidence mode

This avoids nested drawers and keeps mobile behavior simple.

### Run mode

Header:

- prompt name
- run status badge
- progress summary
- timestamps
- close action

Body:

- compact jobs table

Columns:

- `Domain`
- `Result`
- `State`
- `Confidence`
- `Inspect`

### Evidence mode

Header:

- back button
- domain
- predicted label badge
- confidence
- job state badge

Body sections:

1. `Evidence`
- render evidence list items as dense quote cards
- preserve URL hints

2. `Signals`
- render `reasoning_json.signals`
- boolean values should read as `Yes`/`No`, not raw JSON

3. `Other Fields`
- render `reasoning_json.other_fields` as labeled rows

4. `Raw Model Output`
- collapsed by default
- only for debugging

### Visual direction

Stay within the existing operator console language:

- same folder-tab navigation
- same compact table density
- same badge palette
- same right-side drawer pattern already used for markdown and prompt management

The evidence view should feel like an inspection console, not a document editor.

### Mobile behavior

- drawer becomes full width
- jobs table can scroll horizontally
- evidence sections stack vertically

## Data Flow

1. Operator opens `Analysis Runs`.
2. Operator clicks `Inspect` on a run.
3. Frontend fetches `GET /v1/runs/{run_id}/jobs`.
4. Operator clicks `Inspect` on a job row.
5. Frontend fetches `GET /v1/analysis-jobs/{analysis_job_id}`.
6. Drawer switches into evidence mode and renders evidence and reasoning.

## Testing

Backend:

- run jobs endpoint returns jobs with and without classification results
- job detail endpoint returns full evidence payload
- missing run/job returns `404`

Frontend:

- clicking run inspect opens drawer and loads job list
- clicking job inspect switches to evidence mode
- back returns to job list
- null result fields render sane empty states
- mobile drawer remains usable

## Recommendation

Implement this as the next slice before retries. It closes the operator loop by making classifications explainable and debuggable using data the system already stores.
