# Refactoring Strategy: Lean & Maintainable Codebase

**Date:** 2026-03-20
**Status:** Approved — implement before Phase 2 where marked P0/P1

---

## Goals

1. Break up two god-class service files (711 and 622 lines) into focused modules
2. Split two oversized route files into logical groups
3. Centralise scattered config values into `Settings`
4. Add a thin repository/query layer so routes stop executing raw ORM queries
5. Add request-level logging middleware (one place, not sprinkled across routes)

---

## Current Pain Points (from three-agent audit)

| File | Lines | Problem |
|------|-------|---------|
| `app/services/scrape_service.py` | ~711 | DNS, HTTP fetching, link classification, markdown, scrape orchestration, job lifecycle — 6 responsibilities |
| `app/services/analysis_service.py` | ~622 | Run creation, context assembly, LLM calls, result writing, run status refresh — 5 responsibilities |
| `app/api/routes/uploads.py` | ~703 | Upload parsing, company creation, filter validation, scrape enqueueing, result export — 5 responsibilities |
| `app/api/routes/stats.py` | ~410 | Stats read, drain queue, reset stuck, mark failed, refresh run status — 5 unrelated endpoints |

---

## Priority 1 — Service File Splits (do before Phase 2)

### 1a. `scrape_service.py` → 4 files

```
app/services/
  fetch_service.py        # AsyncFetcher, DynamicFetcher wrappers, fetch_with_fallback(), resolve_domain()
  link_service.py         # classify_links_with_llm(), discover_focus_targets(), sitemap parsing
  markdown_service.py     # (already exists) to_markdown(), _assemble_rule_based()
  scrape_service.py       # ScrapeService: job lifecycle only (claim, update_progress, complete, fail)
```

**Rule of thumb:** if a function doesn't touch `ScrapeJob` state, it doesn't belong in `scrape_service.py`.

### 1b. `analysis_service.py` → 3 files

```
app/services/
  run_service.py          # create_runs(), _refresh_run_status(), Run lifecycle
  context_service.py      # _bulk_latest_completed_scrape_jobs(), _bulk_ensure_crawl_adapters(),
                          # _analysis_pages_for_job(), _build_context_for_job()
  analysis_service.py     # AnalysisService: LLM calls + result writing only
                          # run_analysis_job(), _call_general_llm(), _call_classify_llm()
```

**Migration note:** `app/tasks/analysis.py` imports `AnalysisService` — update import after split.

---

## Priority 2 — Route File Splits (do before Phase 2)

### 2a. `uploads.py` → 3 files

```
app/api/routes/
  uploads.py              # POST /v1/uploads, GET /v1/uploads/{id} — upload + company creation
  companies.py            # GET /v1/uploads/{id}/companies (paginated, filtered) + export
  scrape_actions.py       # POST /v1/uploads/{id}/scrape + helper _enqueue_scrapes_for_companies()
```

### 2b. `stats.py` → 2 files

```
app/api/routes/
  stats.py                # GET /v1/stats — read-only, polled frequently by frontend
  queue_admin.py          # POST /v1/queue/drain, /jobs/reset-stuck, /jobs/mark-*, /runs/refresh-status
                          # These are operator actions, not stats — separate them
```

---

## Priority 3 — Config Centralisation (do before Phase 2)

All hardcoded thresholds should move to `app/core/config.py` (`Settings`):

| Current location | Value | New setting name |
|-----------------|-------|-----------------|
| `stats.py:17` | `35` minutes | `SCRAPE_STUCK_MINUTES` |
| `beat.py` | `35` / `20` minutes | `SCRAPE_STUCK_MINUTES` / `ANALYSIS_STUCK_MINUTES` |
| `scrape_service.py` | `MAX_CHARS_PER_PAGE`, `MAX_PAGES` | same |
| `scrape_service.py` | `SKIP_HINTS` frozenset | keep local (not a tunable) |
| `analysis_service.py` | `_LLM_MIN_INTERVAL_SEC = 0.5` | `LLM_MIN_INTERVAL_SEC` |
| `analysis_service.py` | `MAX_CONTEXT_CHARS` | `ANALYSIS_MAX_CONTEXT_CHARS` |

Both `stats.py` and `beat.py` use the same stuck-job threshold — they must stay in sync. Moving to `Settings` makes `SCRAPE_STUCK_MINUTES=35` the single source of truth.

---

## Priority 4 — Repository / Query Layer (defer to after Phase 2)

Routes currently execute raw ORM queries directly (e.g. `session.exec(select(Company).where(...))`). This makes unit testing routes impossible without a real DB and buries query logic inside HTTP handlers.

**Proposed thin DAO layer:**

```
app/db/
  queries/
    company_queries.py    # get_companies_paginated(), count_companies(), bulk_insert_companies()
    scrape_queries.py     # get_active_scrape_urls(), get_stuck_scrape_jobs()
    analysis_queries.py   # get_stuck_analysis_jobs(), get_run_progress()
```

**Rule:** DAOs return model instances or plain dicts. No HTTP concerns (no HTTPException, no Request). Routes call DAOs, not `session.exec(select(...))` directly.

**Why defer:** This is a clean-up pass, not a bug fix. Adding Phase 2 models first, then extracting queries, avoids doing the extract twice.

---

## Priority 5 — Request Logging Middleware (defer to after Phase 2)

Add a single FastAPI middleware that logs `method`, `path`, `status_code`, and `duration_ms` for every request. Currently this is sprinkled inconsistently across individual route handlers.

```python
# app/middleware/logging.py
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    log_event(logger, "http_request",
              method=request.method,
              path=request.url.path,
              status=response.status_code,
              ms=round((time.perf_counter() - t0) * 1000, 1))
    return response
```

---

## What NOT to do

- **No repository base classes / generics** — three concrete DAO modules are simpler than an abstract `BaseRepository[T]`
- **No service interfaces / ABC** — the app has no DI container; adding abstract base classes adds noise without benefit
- **No feature flags or backwards-compat shims** — just rename and update imports
- **Don't split tasks** — `app/tasks/scrape.py`, `analysis.py`, `beat.py` are already lean (< 100 lines each)
- **Don't add docstrings everywhere** — only where logic isn't obvious from names

---

## Suggested Order of Changes

```
Phase 0 (now):
  [P0] Split scrape_service.py → fetch_service, link_service, markdown_service, scrape_service
  [P0] Split analysis_service.py → run_service, context_service, analysis_service
  [P0] Split uploads.py → uploads, companies, scrape_actions
  [P0] Split stats.py → stats, queue_admin
  [P0] Centralise stuck-job thresholds (stats.py + beat.py) into Settings

Phase 1 (after Phase 2 contact pipeline is implemented):
  [P1] Add app/db/queries/ DAO layer
  [P1] Request logging middleware
```

---

## File Size Targets (after refactoring)

| File | Current | Target |
|------|---------|--------|
| `scrape_service.py` | 711 | < 200 |
| `analysis_service.py` | 622 | < 200 |
| `uploads.py` | 703 | < 200 |
| `stats.py` | 410 | < 150 |
| Each new file | — | < 250 |
