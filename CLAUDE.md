



# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

B2B prospect shortlisting tool. Spreadsheet of company URLs → scrape site → AI-classify → discover contacts → reveal emails → validate. FastAPI + SQLModel/Alembic on Postgres, React/Vite SPA, **Procrastinate** as the async queue (PostgreSQL LISTEN/NOTIFY — no Redis/Celery despite what `docs/repository-mental-model.md` says; that doc predates the migration off Celery and is partly stale).

## Common commands

Backend (Python 3.12, `uv`):

```bash
uv sync                                              # install
uv run alembic upgrade head                          # app schema
uv run python -m procrastinate --app=app.queue.app schema --apply   # queue tables (idempotent)
uv run uvicorn app.main:app --reload --port 8000    # API
./scripts/run_worker.sh scrape 2                     # worker (S1)
./scripts/run_worker.sh ai_decision 2                # worker (S2)
./scripts/run_worker.sh "contact_fetch,email_reveal,validation" 5   # workers (S3/S4/S5)
uv run pytest -q tests/                              # full test suite
uv run pytest tests/test_state_enum_contracts.py -q  # fast smoke
uv run pytest tests/path/to/test.py::test_name       # single test
uv run ruff check .                                  # lint (ruff is a pinned dep)
uv run mypy app                                      # type check
```

Tests require Postgres — set `PS_TEST_DATABASE_URL` (or `TEST_DATABASE_URL`) to a disposable DB. There is no SQLite fallback.

Frontend (`apps/web`, Node 22+; pnpm only):

```bash
cd apps/web && pnpm install
pnpm dev          # Vite on :5173, expects API at :8000
pnpm build        # tsc -b && vite build
pnpm lint
```

Docker stack: `docker compose up --build -d` (postgres, api, worker-scrape, worker-ai, worker-provider). API container runs `alembic upgrade head` and `procrastinate schema --apply` on startup.

## Architecture

### Pipeline stages (S1–S5)

Each company moves through five queues. One named queue per stage; one task module per stage in `app/jobs/`:

| Stage | Queue | Module | Purpose |
|---|---|---|---|
| S1 | `scrape` | `app/jobs/scrape.py` | Fetch site (static → curl_cffi → local Scrapling browser fallback) |
| S2 | `ai_decision` | `app/jobs/ai_decision.py` | OpenRouter LLM classification (`Possible`/`Crap`/`Unknown`) |
| S3 | `contact_fetch` | `app/jobs/contact_fetch.py` | Apollo/Snov contact discovery |
| S4 | `email_reveal` | `app/jobs/email_reveal.py` | Snov email reveal |
| S5 | `validation` | `app/jobs/validation.py` | ZeroBounce email validation |

`app/queue.py` defines the Procrastinate app and connector pool (separate from SQLAlchemy's pool). `PS_WORKER_PROCESS=1` (set by `run_worker.sh`) switches **SQLAlchemy** to `NullPool` so tasks don't fight over connections — never set this for the API process.

The scraper does **not** use `PS_BROWSERLESS_URL`; the browser fallback is local Scrapling/Patchright. Don't add Browserless calls to S1 without checking with the user.

### Layering

- `app/api/routes/` — thin HTTP layer (FastAPI routers under `/v1`).
- `app/api/schemas/` — Pydantic request/response models.
- `app/services/` — orchestration & business logic (this is where work happens; routes call services).
- `app/jobs/` — Procrastinate task definitions; jobs call services, not the other way around.
- `app/models/` — SQLModel tables split by domain: base helpers, core upload/campaign/domain tables, scrape tables, classification tables, contacts tables, settings/secrets.
- `app/db/`, `app/core/config.py` — DB session and `PS_*` env settings.

### Domain model (key tables)

`Upload` → `Company` → `CrawlJob`/`CrawlArtifact` → `AnalysisJob`/`ClassificationResult` → `ContactFetchJob` → `DiscoveredContact`/`ProspectContact`. `JobEvent` is the cross-cutting audit log. `AnalysisJob` and `ContactFetchJob` use `lock_token` + `lock_expires_at` for idempotent worker claims; `ClassificationResult.input_hash` is the cache key for skip-if-unchanged. Predicted labels enum: `Possible`, `Crap`, `Unknown`.

Campaign-scoped data flows: contacts are filtered by active status and freshness; many endpoints take a campaign id and apply that scoping in the service layer (see recent commits `f368646`, `e634dfa`).

### Frontend

`apps/web/src/App.tsx` is the orchestrator for stage views (S1–S4 panels), CampaignsView, DashboardView, uploads, settings, and auth. API client and types live in `apps/web/src/lib/api.ts` and `types.ts` — when changing a backend route, update both. Production deploy is **Dockerfile-based** (`apps/web/Dockerfile` → nginx); the `nixpacks.toml` is kept only for reference and must not be used (broke prod 2026-04-19 due to missing cache-header control). `index.html` is `no-store`; `/assets/*` is immutable.

### Environment

Required `PS_*` / API keys live in `.env` (see README "Key environment variables"): `DATABASE_URL`, `OPENROUTER_API_KEY`, `SNOV_CLIENT_ID`/`SNOV_CLIENT_SECRET`, `APOLLO_API_KEY`, `ZEROBOUNCE_API_KEY`. Settings are loaded via `app/core/config.py` (pydantic-settings).

## Working notes

- When adding a new pipeline state or job type, update the state enum, `JobEvent` writers, and `tests/test_state_enum_contracts.py` together — that test is the contract.
- New schema changes: SQLModel edit + new Alembic revision in `alembic/versions/`. Never edit existing revisions.
- `docs/repository-mental-model.md` references Celery/Redis/Beat — that's the old architecture. Trust `README.md` and `app/queue.py` / `app/jobs/` for the current Procrastinate model.
- Design specs and historical plans are in `docs/plans/` and `docs/superpowers/plans/`; the state vocabulary spec is the canonical reference for stage transitions.
