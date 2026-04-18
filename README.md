Architecture and data pipeline overview: [docs/repository-mental-model.md](docs/repository-mental-model.md).
Pre-merge guardrails for pipeline changes: [docs/pipeline-consistency-checklist.md](docs/pipeline-consistency-checklist.md).

## Run with Docker (API + Worker)

This setup runs two app processes:

- `api`: FastAPI service
- `worker`: Redis queue consumer for async scrape jobs

Redis is **external** (not part of `docker-compose.yml`).

### 1) Set environment

Copy `.env.example` to `.env` and set at least:

- `PS_DATABASE_URL`
- `PS_REDIS_URL` (non-TLS `redis://...`)
- `PS_OPENROUTER_API_KEY`

### 2) Start services

```bash
docker compose up --build -d
```

### 3) Check API health

```bash
curl -sS http://127.0.0.1:8000/v1/health/live
```

### 4) Queue scrape jobs (async)

Jobs are automatically enqueued when created via `POST /v1/scrape-jobs`. To retry a failed/terminal job:

```bash
curl -sS -X POST "$BASE/v1/scrape-jobs/$JOB_ID/enqueue" | jq
```

## New Pipeline Contracts (Campaign Stage-Resume)

Recent backend/frontend contracts now support campaign-like controls using existing `upload_id` scope plus idempotent retrigger controls.

- `GET /v1/contacts/companies` supports `match_gap_filter`:
  - `all`
  - `contacts_no_match`
  - `matched_no_email`
  - `ready_candidates`
- Retrigger endpoints support `X-Idempotency-Key`:
  - `POST /v1/companies/scrape-selected`
  - `POST /v1/companies/scrape-all`
  - `POST /v1/scrape-jobs/{job_id}/enqueue`
  - `POST /v1/companies/fetch-contacts-selected`
  - `POST /v1/contacts/verify`
- Scrape rules can be provided on selected scraping requests to limit page kinds and fallback behavior.
- `GET /v1/stats` now returns queue blocks for `contact_fetch` and `validation`, plus optional `costs`.
- `GET /v1/stats/costs` is available as a paginated cost-contract scaffold (currently returns null stage values until provider/model cost ingestion is wired).
- Selected company/contact/stats list endpoints now support optional `upload_id` for campaign-like scoping.

## How to Test These Changes

From repo root:

```bash
uv run pytest tests/test_idempotency_service.py tests/test_scrape_page_rules.py tests/test_bulk_contact_fetch.py tests/test_contact_company_gap_filters.py
```

Frontend API contract tests:

```bash
node --test "apps/web/tests/*.test.ts"
```

Frontend build/type check:

```bash
npm --prefix "/Users/avi/Documents/Projects/AI/Prospect_shortlisting/apps/web" run build
```

Backend regression suite (excluding exploratory scripts under `scripts/`):

```bash
uv run pytest -q tests
```
