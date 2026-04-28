# Companies API Simplification

**Date:** 2026-04-29  
**Status:** Approved  
**Scope:** `app/api/routes/companies.py`, `app/services/company_service.py` (new), `app/api/routes/stats.py`

## Problem

`companies.py` is 955 LOC with business logic, cascade delete, filter pipeline, and dead endpoints all mixed into route handlers. Specific issues:

1. `getattr(x, "default", ...)` boilerplate repeated 12+ times — defensive cargo-cult code.
2. `POST /companies/delete` does deep cascade deletes across 9 tables inline in the handler. Missing `DiscoveredContact` and `ScrapeJob` — existing bug.
3. Filter pipeline (6 subqueries + 5 apply-functions) rebuilt identically in 3+ endpoints.
4. 3 endpoints are dead/unused: `/ids`, `/letter-counts`, `/export.csv`.
5. `/companies/counts` is dashboard aggregation mixed into a domain router.
6. `upload.valid_count` decremented in a Python loop instead of bulk SQL.

## Design

### Files

| File | Change |
|------|--------|
| `app/api/routes/companies.py` | Stripped to 3 endpoints. ~120 LOC target. |
| `app/services/company_service.py` | **New.** All query + delete logic. |
| `app/api/routes/stats.py` | Receives `GET /companies/counts` (straight move, no logic change). |

### Endpoints killed

- `GET /companies/ids`
- `GET /companies/letter-counts`
- `GET /companies/export.csv`

### Endpoints kept

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/companies` | Thin handler — delegates to `build_filtered_company_stmt` |
| `PUT` | `/companies/{company_id}/feedback` | Unchanged — synchronous recompute_company_stages is justified |
| `DELETE` | `/companies` | Body: `{company_ids, campaign_id}`. 202 response. Cascade via bg task. |

### `GET /companies` — stage coverage

One endpoint serves all pipeline stages via `stage_filter`:

| Stage | `stage_filter` value |
|-------|---------------------|
| S1 — Uploaded | `uploaded` |
| S2 — Scraped | `scraped` / `has_scrape` |
| S3 — Classified / Contact Ready | `classified` / `contact_ready` |

### `app/services/company_service.py`

```
CompanyFilters                     # dataclass: all validated + normalized filter/sort params
validate_company_filters(...)      # replaces getattr boilerplate + _validate_filters

build_filtered_company_stmt(       # assembles SELECT with all joins + filters, returns un-paginated statement
    session, campaign_id, filters, upload_id
) -> Select

# Subquery helpers (moved from companies.py)
_latest_classification_subquery()
_latest_scrape_subquery()
_latest_analysis_subquery()
_contact_count_subquery()
_discovered_contact_count_subquery()
_latest_contact_fetch_subquery()

# Filter-apply functions (moved from companies.py)
_apply_decision_filter(...)
_apply_scrape_filter(...)
_apply_stage_filter(...)
_apply_pipeline_status_filter(...)
_apply_search_filter(...)

cascade_delete_companies(          # full cascade — called by bg task only, NOT by route
    session, company_ids, campaign_id
) -> CompanyDeleteResult
```

`stats.py` imports `_latest_classification_subquery` and `_latest_scrape_subquery` from `company_service.py` — no duplication.

### `DELETE /companies` contract

**Request body:**
```json
{ "company_ids": ["uuid", ...], "campaign_id": "uuid" }
```

**Route (synchronous):**
1. Validate `company_ids` belong to `campaign_id` — 404 if campaign not found, filter out IDs not in campaign.
2. Enqueue bg task: `cascade_delete_companies(company_ids, campaign_id)`.
3. Return 202:
```json
{ "queued_count": 5, "queued_ids": ["uuid", ...] }
```

**Bg task (`cascade_delete_companies`)** — full cascade in order:
1. Collect `crawl_job_ids` and `analysis_job_ids` for company_ids
2. Delete `ClassificationResult` WHERE analysis_job_id IN (...)
3. Delete `JobEvent` (type=analysis) WHERE job_id IN (...)
4. Delete `AnalysisJob` WHERE company_id IN (...)
5. Delete `CrawlArtifact` WHERE crawl_job_id IN (...)
6. Delete `JobEvent` (type=crawl) WHERE job_id IN (...)
7. Delete `CrawlJob` WHERE company_id IN (...)
8. Delete `ScrapeJob` WHERE normalized_url IN (company normalized_urls) — **missing in current code, bug fix**
9. Delete `DiscoveredContact` WHERE company_id IN (...) — **missing in current code, bug fix**
10. Delete `ProspectContact` WHERE company_id IN (...)
11. Delete `ContactFetchJob` WHERE company_id IN (...)
12. Delete `CompanyFeedback` WHERE company_id IN (...)
13. Delete `Company` WHERE id IN (...)
14. Bulk UPDATE `Upload.valid_count` via single SQL — replaces Python loop

### `getattr` boilerplate removal

All `if not isinstance(x, type): x = getattr(x, "default", ...)` blocks deleted. FastAPI resolves Query defaults natively with proper type annotations.

## What does NOT change

- `PUT /companies/{company_id}/feedback` — logic identical, `recompute_company_stages` stays inline
- `GET /companies/counts` — straight move to `stats.py`, zero logic changes, same URL, same schema
- All filter constants and aliases — moved to service, not changed
