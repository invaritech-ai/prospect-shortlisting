# Celery → Procrastinate Cutover

**Date:** 2026-04-29
**Status:** Approved — clean break, no parallel systems
**Audience:** Mid-to-senior engineers

---

## Goal

Strip Celery, Redis, and all task-orchestration code completely. Install Procrastinate as the only execution layer. After this cutover, only campaign management and file upload pages will work end-to-end. Every async pipeline button (scrape, analyze, fetch contacts, reveal, verify, export) is intentionally broken — they will be rebuilt page-by-page in the next sprint phase, starting with S1 Scraping.

**Philosophy:** delete aggressively. No dead shells. We rewrite from scratch when each page comes back.

---

## Acceptance Criteria

1. **Zero Celery references** in `app/`, `tests/`, `scripts/`. Verified by `grep -rn "celery\|billiard\|kombu\|vine" app/ tests/ scripts/` returning no hits.
2. **Zero Redis references** in app code (other than docker-compose if cache layer survives — it doesn't here). Verified by `grep -rn "redis" app/` returning no hits.
3. **`pyproject.toml`** has no `celery`, `redis`, `billiard`, `kombu`, `vine`, `testcontainers[redis]`. Adds `procrastinate`.
4. **`docker-compose.yml`** has 3 services: `postgres`, `api`, `worker` (Procrastinate). No `redis`, no `worker-scrape-*`, no `worker-contact-*`, no `beat`.
5. **`docker compose up`** starts cleanly. API responds at `/v1/health/live`.
6. **`uv run pytest tests/test_state_enum_contracts.py`** passes (smoke test that imports still work).
7. **Procrastinate hello-world task executes successfully.** A trivial `@app.task async def ping() -> None: ...` deferred from a test endpoint runs in the worker, completes successfully, queryable via `SELECT status FROM procrastinate_jobs`.
8. **Campaigns CRUD works** — list, create, edit, delete via the existing endpoints. Manual smoke test in browser.
9. **Uploads CRUD works** — list, create, link to campaign, unlink. Manual smoke test in browser.

---

## Files to DELETE entirely

### Code
```
app/celery_app.py
app/services/redis_client.py
app/services/pipeline_run_orchestrator.py
app/services/contact_queue_service.py
app/services/contact_reveal_queue_service.py
app/services/contact_reveal_service.py
app/services/contact_service.py
app/services/contact_runtime_service.py        (if exists, used by Celery orchestration)
app/tasks/                                     (entire directory: scrape.py, analysis.py, contacts.py, beat.py, company.py, __init__.py)
app/api/routes/queue_admin.py
app/api/routes/queue_history.py
app/api/routes/scrape_actions.py
app/api/routes/scrape_jobs.py
app/api/routes/pipeline_runs.py                (rewrite later when frontend needs it; delete now)
```

### Tests
```
tests/test_celery_tasks.py
tests/test_idempotency.py                      (Celery delivery semantics)
tests/test_recovery.py                         (Celery worker recovery)
tests/test_beat_reconciler.py                  (Celery Beat)
tests/test_contact_admin.py                    (queue admin endpoints)
tests/test_contact_apollo.py                   (Celery contact fetch)
tests/test_contact_identity.py                 (Celery contact pipeline)
tests/test_contact_reveal.py                   (Celery reveal)
tests/test_contact_verify.py                   (Celery verify)
tests/test_contact_rules.py                    (depends on title rules — keep if test passes without Celery; delete if it imports task code)
tests/test_contact_stage_contracts.py          (depends on the deleted /contacts/ids etc. endpoints)
```
Re-evaluate `test_contact_rules.py` and `test_title_match_test_ui.py` — keep them if they test pure title-matching logic; delete if they exercise task execution.

### Schemas tied to deleted endpoints
```
app/api/schemas/scrape.py                      (review — used by deleted scrape routes)
app/api/schemas/scrape_prompt.py               (review — only delete if unused after route deletes)
app/api/schemas/pipeline_run.py                (only delete after pipeline_runs route is gone)
```

---

## Files to STRIP (delete imports/calls but keep file)

### `app/api/routes/companies.py`
Delete the entire `delete_companies` endpoint (depends on `app.tasks.company.cascade_delete_companies`). Frontend's "Delete companies" button breaks intentionally — rebuilt later.

### `app/api/routes/contacts.py`
Delete these endpoints (all depend on Celery):
- `POST /v1/contacts/fetch`
- `POST /v1/contacts/rematch` (keep if it's purely synchronous SQL — verify by reading the function body)
- `POST /v1/contacts/reveal`
- `POST /v1/contacts/verify`
- `GET /v1/contacts/export.csv` (keep if pure SQL read)
- `GET /v1/contacts/ids`, `/v1/contacts/counts`, `/v1/contacts/companies` (per earlier decision — these were re-added incorrectly, delete now)

Keep:
- `GET /v1/contacts` (read)
- `GET /v1/title-match-rules*` (CRUD — pure DB)

Delete corresponding schemas in `app/api/schemas/contacts.py`.

### `app/core/config.py`
Delete `redis_url`, `REDIS_URL` env vars, any Celery-specific config (broker_url, etc.).

### `app/db/session.py`
Verify no Celery imports. Should not contain any.

### `app/main.py`
Remove router imports for deleted route files. Verify the app starts after.

---

## Procrastinate Installation

### 1. Add dependency
```toml
# pyproject.toml
"procrastinate[psycopg2]>=2.10.0,<3.0",   # use psycopg2 to match existing SQLAlchemy stack
```
Run `uv lock && uv sync`.

Remove these from `pyproject.toml`:
```
"celery[redis]>=5.3.0,<5.5",
"redis>=7.2.1",
"testcontainers[postgres,redis]>=4.8.0",   # change to "testcontainers[postgres]"
```

### 2. Create the Procrastinate app
File: `app/queue.py` (single file, ~25 lines)

```python
from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.core.config import settings


_connector = PsycopgConnector(
    kwargs={
        "conninfo": settings.database_url,
    },
)

app = App(connector=_connector)
app.import_paths = ["app.jobs"]
```

### 3. Create the jobs package
File: `app/jobs/__init__.py` (empty for now — tasks added per-page in next phase)

File: `app/jobs/health.py` — ONE smoke-test task only:
```python
from __future__ import annotations

import logging

from app.queue import app

logger = logging.getLogger(__name__)


@app.task(name="ping")
async def ping() -> None:
    logger.info("procrastinate ping ok")
```

### 4. Run Procrastinate's schema migration
Procrastinate ships SQL to create its own tables. Run it as a one-shot:
```bash
uv run procrastinate schema --apply
```
This creates `procrastinate_jobs`, `procrastinate_periodic_defers`, `procrastinate_events`, etc.

(Alembic does NOT manage these — Procrastinate owns its schema.)

### 5. Add a smoke endpoint
File: `app/api/routes/health.py` (or extend existing `main.py` health routes)
```python
@router.post("/v1/health/ping-job", status_code=202)
async def queue_ping_job() -> dict[str, str]:
    from app.jobs.health import ping
    await ping.defer_async()
    return {"status": "queued"}
```

### 6. Update `docker-compose.yml`
Replace all `worker-*` services and the `beat` service with one:
```yaml
worker:
  build: .
  depends_on:
    postgres:
      condition: service_healthy
  environment:
    - DATABASE_URL=${DATABASE_URL}
  command: ["uv", "run", "procrastinate", "worker"]
  restart: unless-stopped
```
Delete the `redis` service entirely.

---

## Execution Order

Dispatch a single subagent to execute the sweep. Order matters:

1. **Delete the files in the DELETE list** — fast, mechanical
2. **Strip the files in the STRIP list** — remove imports, delete the listed endpoints
3. **Verify app boots** — `uv run python -c "from app.main import create_app; create_app()"` should succeed (will fail until step 1 + 2 are clean)
4. **Update `pyproject.toml` + `uv sync`**
5. **Add `app/queue.py` + `app/jobs/__init__.py` + `app/jobs/health.py`**
6. **Run `procrastinate schema --apply`** against the dev DB
7. **Add the `/v1/health/ping-job` endpoint**
8. **Rewrite `docker-compose.yml`** — drop celery/redis services, add `worker`
9. **Run smoke tests:**
   - `uv run pytest tests/test_state_enum_contracts.py -q` → pass
   - `uv run python -c "from app.main import create_app; create_app(); print('OK')"` → OK
   - `docker compose up` → all 3 services healthy
   - `curl -X POST http://localhost:8000/v1/health/ping-job` → 202
   - `psql -c "SELECT status FROM procrastinate_jobs ORDER BY id DESC LIMIT 5"` → ping job present, eventually `succeeded`
10. **Commit**

---

## Risks / Notes

- **Frontend will fail loudly** on every pipeline-trigger button. This is intentional. The S1 Scraping page rebuild is the next sprint task.
- **The `procrastinate schema --apply` step is idempotent** — safe to run once per environment. Production deploy will need this run once before workers start.
- **`testcontainers[redis]` removal** will affect any test fixture spinning up Redis. Those tests are in the DELETE list anyway.
- **`procrastinate[psycopg2]` vs `[psycopg]`**: SQLAlchemy uses psycopg2 in this project. Use the matching extra. If the project moves to psycopg3 later, swap.
- **No alembic migration for Procrastinate's tables** — Procrastinate manages its own schema lifecycle. Document this in deployment runbook.

---

## What Still Works After Cutover

- All read-only endpoints (campaigns list, uploads list, companies list, contacts list, title-match-rules CRUD, settings, stats — though stats has pre-existing bugs unrelated to this work)
- All entity CRUD that doesn't trigger async work (campaigns, uploads, title-match-rules)
- Frontend pages: campaigns, uploads (S0 view)

## What's Intentionally Broken

- All S1–S4 pipeline trigger buttons in the frontend
- Contact fetch/reveal/verify
- Scrape actions
- Delete companies (cascade was a Celery task)
- Pipeline runs view
- Queue admin/history pages

These get rebuilt one stage at a time, starting with S1 Scraping in the next sprint phase.
