# FastAPI Backend HTTP API Inventory
**Generated:** 2026-04-28  
**Scope:** `/v1/` prefix, 16 routers, ~55 endpoints, 6,582 LOC in routes

## Summary

- **Total Routers:** 16 (contacts, companies, discovered_contacts, campaigns, uploads, runs, analysis, stats, queue_admin, queue_history, pipeline_runs, prompts, scrape_prompts, scrape_jobs, scrape_actions, settings)
- **Total Endpoints:** ~55 public HTTP endpoints
- **Total Lines:** 6,582 LOC in route files (excluding schemas)
- **Key Observations:**
  - Fat routers: **contacts.py** (1,169 LOC), **companies.py** (955 LOC), **stats.py** (817 LOC), **discovered_contacts.py** (554 LOC), **queue_admin.py** (525 LOC)
  - Heavy SQL & filtering logic embedded directly in endpoints (no separate service layer for query building)
  - Idempotency handling in 2+ endpoints (contacts/verify, fetch-contacts-selected, discovered-contacts/reveal-emails)
  - Admin endpoints in queue_admin with no apparent access controls (drain, reset, recompute ops)
  - Schema duplication: multiple "ContactRead" variants + overlapping contact models across contacts & discovered_contacts

---

## Per-Router Details

### 1. **contacts.py** (1,169 LOC)
**Prefix:** `/v1`  
**Domain:** Contact fetching, verification, listing, title-matching rules

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/companies/{company_id}/fetch-contacts` | Enqueue contact fetch for single company | `campaign_id` (Query) | `ContactFetchResult` | `fetchContactsForCompany` |
| POST | `/runs/{run_id}/fetch-contacts` | Enqueue contact fetch for run's qualified companies | `campaign_id` (Query) | `ContactFetchResult` | `fetchContactsForRun` |
| POST | `/companies/fetch-contacts-selected` | Bulk fetch for selected company IDs (idempotent) | `BulkContactFetchRequest` | `ContactFetchResult` | `fetchContactsSelected` |
| GET | `/companies/{company_id}/contacts` | List contacts for a company | 7 query params (pagination, filters) | `ContactListResponse` | `listCompanyContacts` |
| GET | `/contacts/companies` | List companies grouped by contacts (complex aggregation) | 8 query params + `upload_id` | `ContactCompanyListResponse` | `listContactCompanies` |
| GET | `/contacts` | List all contacts with sorting/pagination (main contacts UI) | 9 query params, supports `sort_by`, `letters`, `count_by_letters` | `ContactListResponse` | `listContacts` |
| GET | `/contacts/counts` | Get contact stage counts (fetched/verified/campaign_ready/eligible) | `campaign_id`, `upload_id` | `ContactCountsResponse` | `getContactCounts` |
| GET | `/contacts/export.csv` | Export contacts to CSV | Same filters as list | CSV Response | `getContactsExportUrl` |
| POST | `/contacts/verify` | Queue ZeroBounce verification (idempotent) | `ContactVerifyRequest` | `ContactVerifyResult` | `verifyContacts` |
| GET | `/title-match-rules` | List title matching rules for campaign | `campaign_id` | `list[TitleMatchRuleRead]` | `listTitleMatchRules` |
| POST | `/title-match-rules` | Create title matching rule | `TitleMatchRuleCreate` | `TitleMatchRuleRead` | `createTitleMatchRule` |
| DELETE | `/title-match-rules/{rule_id}` | Delete title rule | `campaign_id` (Query) | 204 No Content | ✓ |
| POST | `/title-match-rules/rematch` | Re-evaluate title matches on discovered contacts | `campaign_id` (Query) | `RematchResult` | ✓ |
| POST | `/title-match-rules/seed` | Auto-seed rules from labeling data | `campaign_id` (Query) | `TitleRuleSeedResult` | ✓ |
| POST | `/title-match-rules/test` | Test title match rule against a title string | `TitleTestRequest` | `TitleTestResult` | `testTitleMatch` |
| GET | `/title-match-rules/stats` | Get rule coverage stats | `campaign_id` (Query) | `TitleRuleStatsResponse` | `getTitleRuleStats` |

**Smells & Notes:**
- **Line 165-216:** `_apply_contact_filters()` — massive helper doing 11+ filter conditions, N+1 risk on `company_ids` join
- **Line 219-247:** `_select_verification_contact_ids()` — complex subquery building, no schema-level validation
- **Line 515-662:** `list_contacts_by_company()` — 148 LOC, large SQL aggregation with 13 case expressions, subquery for `latest_contact_attempt`
- **Line 696-872:** `list_all_contacts()` — 176 LOC, supports letter-based alphabetization with per-letter counts, batch-fetches DiscoveredContact data inline (potential N+1 if many contacts)
- **Line 116-154:** `_contact_emails_map()` — joins ProspectContactEmail table, deduplication logic embedded here; could be service method
- **Idempotency:** Lines 368-446 (fetch-contacts-selected), 996-1069 (verify-contacts) — boilerplate repeated in both
- **No access control visible:** endpoints assume campaign/upload ownership validated upstream

---

### 2. **companies.py** (955 LOC)
**Prefix:** `/v1`  
**Domain:** Company listing, filtering, feedback, deletion, export

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| PUT | `/companies/{company_id}/feedback` | Upsert company classification feedback | `FeedbackUpsert` | `FeedbackRead` | `upsertCompanyFeedback` |
| GET | `/companies` | List companies with complex pipeline status + decision filters | 13 query params (decision, scrape, stage, sort filters) | `CompanyList` | `listCompanies` |
| GET | `/companies/ids` | Get IDs only (optimized for bulk operations) | Same as above | `CompanyIdsResult` | `listCompanyIds` |
| GET | `/companies/letter-counts` | Count companies by domain first letter | 5 query params | `LetterCounts` | `getLetterCounts` |
| GET | `/companies/counts` | Count by decision/stage | 2 query params | `CompanyCounts` | `getCompanyCounts` |
| GET | `/companies/export.csv` | Export companies to CSV | Same filters as list | CSV Response | `getCompaniesExportUrl` |
| POST | `/companies/delete` | Bulk delete companies (idempotent via route, not marked) | `CompanyDeleteRequest` | `CompanyDeleteResult` | `deleteCompanies` |

**Smells & Notes:**
- **Line 50-141:** 5 massive subquery helpers (`_latest_classification_subquery()`, `_latest_scrape_subquery()`, etc.) — each builds distinct() query with join, potential performance hot spot
- **Line 143-300+:** `list_companies()` — 228+ LOC, 8 joins, complex `case()` expressions for decision filter logic, full-text search on domain
- **Line 332-401:** `put_feedback()` — creates/updates feedback, triggers `recompute_company_stages()` (service call)
- **Decision filter logic:** Lines 169-230 — if-else tree for decision_filter ("all" | "unlabeled" | "possible" | "unknown" | "crap" | "labeled") modifies WHERE clauses
- **Stage filter:** Lines 231-270 — separate validation for stage_filter ("all", "contact_ready", "classification_ready", etc.)
- **N+1 risk:** Large company list may trigger hidden joins per company without prefetch; depends on SQLAlchemy lazy loading config
- **No bulk idempotency key tracking:** `/companies/delete` is POST but no X-Idempotency-Key header handling

---

### 3. **discovered_contacts.py** (554 LOC)
**Prefix:** `/v1`  
**Domain:** Contact discovery from scrape, reveal emails, bulk listing

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| GET | `/discovered-contacts` | List discovered contacts (from scrape) with sort/filter | 9 query params (provider, title_match, stale_email_only, sort_by) | `DiscoveredContactListResponse` | `listDiscoveredContacts` |
| GET | `/companies/{company_id}/discovered-contacts` | Discovered contacts for single company | 6 query params | `DiscoveredContactListResponse` | `listCompanyDiscoveredContacts` |
| GET | `/discovered-contacts/ids` | Get IDs only | Similar filters | `DiscoveredContactIdsResult` | `listDiscoveredContactIds` |
| GET | `/discovered-contacts/counts` | Counts by provider/title_match | `campaign_id` | `DiscoveredContactCountsResponse` | `getDiscoveredContactCounts` |
| GET | `/discovered-contacts/companies` | Discovered companies grouped by contact stats (like contacts/companies) | 5 query params | `ContactCompanyListResponse` | `listDiscoveredCompanies` |
| POST | `/discovered-contacts/reveal-emails` | Reveal/fetch emails from provider (idempotent) | `ContactRevealRequest` | `ContactRevealResult` | `revealDiscoveredContactEmails` |

**Smells & Notes:**
- **Line 226-328:** `list_discovered_contacts()` — 102 LOC, large aggregation subquery + sorting logic similar to contacts.py
- **Line 334-402:** `list_discovered_contacts_by_company()` — 68 LOC, similar aggregation pattern
- **Line 408-500:** `list_discovered_companies()` — 92 LOC, major aggregation with 11+ case expressions, subquery for `latest_discovery_attempt`, HAVING clause for match_gap_filter
- **Line 502-554:** `reveal_discovered_contact_emails()` — idempotency logic (Lines 513-545), calls `ContactRevealQueueService().enqueue_reveals()`, queueing pattern
- **Code duplication:** Aggregation patterns heavily duplicated from contacts.py (letter counts, filter validation, sort expressions)
- **Freshness cutoff:** Line 64 — `_freshness_cutoff()` uses config setting `contact_discovery_freshness_days` to define "stale"

---

### 4. **stats.py** (817 LOC)
**Prefix:** `/v1`  
**Domain:** Pipeline statistics, job counts, ETA, cost tracking

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| GET | `/stats` | Pipeline stage stats (counts, ETA, throughput) | `campaign_id`, `upload_id` | `StatsResponse` | `getStats` |
| GET | `/stats/costs` | Cost breakdown by company and stage | 5 query params (window_days, limit, offset) | `CostStatsResponse` | `getCostStats` |

**Smells & Notes:**
- **Line 90-700+:** `get_stats()` — ~300+ LOC, computes for each stage (scrape, analysis, contact_fetch, contact_reveal, validation):
  - Job counts (completed, failed, site_unavailable, running, queued, stuck)
  - Average job duration from recent sample (100 jobs)
  - Throughput from 60-min window
  - ETA calculation (queued_count * avg_sec / throughput)
  - All inline SQL with multiple subqueries, no service layer
- **Line 25:** `SCRAPE_RUNNING_STUCK_MINUTES = 35` — hard-coded stuck threshold
- **Line 29-30:** `_SAMPLE_SIZE = 100`, `_THROUGHPUT_WINDOW_MINUTES = 60` — query window params hard-coded
- **Cost stats:** Line 700+ — separate endpoint for cost aggregation, also inline SQL
- **No caching:** Re-queries all job tables on each call; could be slow during large runs

---

### 5. **queue_admin.py** (525 LOC)
**Prefix:** `/v1`  
**Domain:** Job queue management, stuck job recovery, pipeline recomputation (admin-only conceptually)

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/queue/drain` | Drain all queued jobs | — | `DrainQueueResult` | `drainQueue` |
| POST | `/jobs/reset-stuck` | Reset stuck analysis & contact-fetch jobs to queued | — | `ResetStuckResult` | `resetStuckJobs` |
| POST | `/jobs/mark-non-completed-failed` | Mark non-terminal jobs as failed (recovery op) | — | `MarkFailedResult` | ❌ unused |
| POST | `/analysis-jobs/reset-stuck` | Reset only stuck analysis jobs | — | `ResetStuckAnalysisResult` | `resetStuckAnalysisJobs` |
| POST | `/contact-fetch-jobs/reset-stuck` | Reset only stuck contact-fetch jobs | — | `ResetStuckAnalysisResult` | `resetStuckContactFetchJobs` |
| POST | `/jobs/mark-empty-completed-failed` | Mark completed jobs with 0 results as failed | — | `MarkEmptyCompletedResult` | ❌ unused |
| POST | `/runs/refresh-status` | Refresh terminal states of all runs | — | `RefreshRunStatusResult` | ❌ unused |
| POST | `/pipeline/recompute-stages` | Recompute company pipeline stages | — | `RecomputePipelineStagesResult` | ❌ unused |
| GET | `/contacts/admin/runtime-control` | Get contact queue runtime config (concurrency, backoff) | — | `ContactRuntimeControlRead` | ❌ unused |
| PATCH | `/contacts/admin/runtime-control` | Update contact queue runtime config | `ContactRuntimeControlUpdate` | `ContactRuntimeControlRead` | ❌ unused |
| GET | `/contacts/admin/backlog` | Detailed backlog summary (by state, provider, reason) | — | `ContactBacklogSummary` | ❌ unused |
| POST | `/contacts/admin/retry-failed` | Retry failed contact fetch companies | `ContactRetryRequest` | `ContactRetryResult` | ❌ unused |
| POST | `/contacts/admin/replay-deferred` | Replay deferred contact attempts | — | `ContactReplayResult` | ❌ unused |

**Smells & Notes:**
- **⚠️ Security:** No visible authentication/authorization checks on these endpoints; code assumes upstream auth middleware
- **Unused endpoints:** Lines 144-228 (`mark_non_completed_failed`, `mark_empty_completed_failed`), lines 245-297 (refresh_run_statuses), and most admin contact endpoints (Lines 332-525) appear never called from frontend
- **Line 93-116:** `drain_queue()` — marks all QUEUED jobs as RUNNING with fixed throughput limits; dangerous if called by accident
- **Line 118-142:** `reset_stuck_jobs()` — resets jobs stuck > 35 min back to QUEUED; no dry-run or confirmation
- **Line 303-328:** Contact runtime control — read/update concurrency & backoff settings; PATCH endpoint allows runtime behavior changes
- **Embedded state machine logic:** Job state transitions (QUEUED → RUNNING, FAILED → QUEUED, etc.) hard-coded in each endpoint, no centralized state machine

---

### 6. **pipeline_runs.py** (444 LOC)
**Prefix:** `/v1`  
**Domain:** Pipeline run lifecycle, progress tracking, cost summaries

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/pipeline-runs/start` | Enqueue all qualified companies in campaign for analysis | `PipelineRunStartRequest` | `PipelineRunStartResponse` | `startPipelineRun` |
| GET | `/pipeline-runs/{run_id}/progress` | Poll run progress (job counts by stage/state) | — | `PipelineRunProgressRead` | `getPipelineRunProgress` |
| GET | `/pipeline-runs/{run_id}/costs` | Get cost breakdown for run | — | `PipelineCostSummaryRead` | `getPipelineRunCosts` |
| GET | `/campaigns/{campaign_id}/costs` | Get cost breakdown for entire campaign | — | `PipelineCostSummaryRead` | `getCampaignCosts` |
| GET | `/costs/reconciliation-summary` | Unused; reconciliation stats | — | JSON | ❌ unused |

**Smells & Notes:**
- **Line 100-290:** `start_run()` — ~190 LOC, complex business logic:
  - Fetches Run record, queries for qualified companies
  - Creates AnalysisJob per company (bulk insert)
  - Enqueues via Celery, handles idempotency with X-Idempotency-Key
  - Calls `recompute_company_stages()` after enqueue
- **Line 292-380+:** `get_run_progress()` — ~88 LOC, builds progress summary from job counts in AnalysisJob/ContactFetchJob/ContactVerifyJob
- **Cost queries:** Lines 382+ — separate cost calculations by run_id vs campaign_id, similar logic duplicated

---

### 7. **settings.py** (493 LOC)
**Prefix:** `/v1`  
**Domain:** Integration provider config (ScrapeFlow, ZeroBounce, Snov, LinkedIn)

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| GET | `/integrations` | List integration status & encryption keys | — | `IntegrationsStatusResponse` | `getIntegrationSettings` |
| PUT | `/integrations/{provider}` | Update provider config (API keys, enabled flag) | `IntegrationProviderUpdateRequest` | `IntegrationProviderStatus` | `updateIntegrationProvider` |
| GET | `/integrations/health` | Health check each provider (API call to verify auth) | — | `list[IntegrationHealthItem]` | `getIntegrationsHealth` |
| POST | `/integrations/{provider}/test` | Test provider connectivity | — | `IntegrationTestResponse` | `testIntegrationProvider` |

**Smells & Notes:**
- **Line 80-200+:** `get_integrations()` — reads from DB, returns public keys; ⚠️ depends on `settings.settings_encryption_key` for decryption
- **Line 207-280+:** `update_integrations()` — validates provider, encrypts secrets, writes to DB, calls `recompute_company_stages()` if ScrapeFlow config changes
- **Health checks:** Line 301+ — iterates providers and calls health API; could timeout if provider is slow
- **Encryption dependency:** All secret handling requires non-empty `PS_SETTINGS_ENCRYPTION_KEY` env var; main.py warns if missing (line 47-51)

---

### 8. **campaigns.py** (192 LOC)
**Prefix:** `/v1`  
**Domain:** Campaign CRUD and upload assignment

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/campaigns` | Create campaign | `CampaignCreate` | `CampaignRead` | `createCampaign` |
| GET | `/campaigns` | List campaigns | `limit`, `offset` | `CampaignList` | `listCampaigns` |
| PATCH | `/campaigns/{campaign_id}` | Update campaign metadata | `CampaignUpdate` | `CampaignRead` | `updateCampaign` |
| DELETE | `/campaigns/{campaign_id}` | Delete campaign (cascade?) | — | 204 No Content | `deleteCampaign` |
| POST | `/campaigns/{campaign_id}/assign-uploads` | Assign uploads to campaign | `{upload_ids: []}` | `CampaignRead` | `assignUploadsToCampaign` |

**Smells & Notes:**
- Straightforward CRUD, minimal business logic
- No visible cascade delete handling; deleting campaign may orphan uploads/companies
- Assign-uploads is POST but non-idempotent (could double-assign)

---

### 9. **uploads.py** (151 LOC)
**Prefix:** `/v1`  
**Domain:** CSV file uploads, company list imports

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/uploads` | Upload CSV file | `file` (FormData), `campaign_id` (optional) | `UploadCreateResult` | `uploadFile`, `uploadFileToCampaign` |
| GET | `/uploads` | List uploads | `limit`, `offset` | `UploadList` | `listUploads` |
| GET | `/uploads/{upload_id}` | Get upload metadata | — | `UploadDetail` | `getUpload` |
| GET | `/uploads/{upload_id}/companies` | List companies from upload | `limit`, `offset` | `UploadCompanyList` | `getUploadCompanies` |

**Smells & Notes:**
- Simple file handling, delegates parsing to service
- No virus scanning or file-size limits visible

---

### 10. **scrape_actions.py** (296 LOC)
**Prefix:** `/v1`  
**Domain:** Trigger web scraping for companies

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/companies/scrape-selected` | Enqueue scrape for selected companies (idempotent) | `CompanyScrapeRequest` | `CompanyScrapeResult` | `scrapeSelectedCompanies` |
| POST | `/companies/scrape-all` | Enqueue scrape for all unscraped in campaign (idempotent) | `{upload_id?, scrape_rules?}` | `CompanyScrapeResult` | `scrapeAllCompanies` |

**Smells & Notes:**
- Both endpoints use `X-Idempotency-Key` header for safety (lines 120-170, 204-280)
- `CompanyScrapeRequest` accepts optional `scrape_rules` (JSON schema for page selectors)
- Calls `ScrapeQueueService().enqueue_scrapes()` to batch enqueue ScrapeJob records
- No progress polling visible; relies on stats.py for pipeline status

---

### 11. **scrape_jobs.py** (242 LOC)
**Prefix:** `/v1`  
**Domain:** Scrape job CRUD and result retrieval

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/scrape-jobs` | Create scrape job manually | `ScrapeJobCreate` | `ScrapeJobRead` | `createScrapeJob` |
| GET | `/scrape-jobs` | List scrape jobs | `limit`, `offset`, `status_filter`, `search` | `list[ScrapeJobRead]` | `listScrapeJobs` |
| GET | `/scrape-jobs/{job_id}` | Get scrape job detail | — | `ScrapeJobRead` | `getScrapeJob` |
| GET | `/scrape-jobs/{job_id}/pages` | List scraped pages for job | — | `list[ScrapePageRead]` | ❌ unused |
| GET | `/scrape-jobs/{job_id}/pages-content` | Get page content (HTML/text) | `limit`, `offset` | `list[ScrapePageContentRead]` | `listScrapeJobPageContents` |
| POST | `/scrape-jobs/{job_id}/enqueue` | Manually enqueue a job | — | `ScrapeJobRead` | ❌ unused |

**Smells & Notes:**
- **Line 50-180:** Heavy filtering logic for status_filter ("all", "active", "completed", "failed", "stuck") with dynamic WHERE
- **Line 182-225:** `list_scrape_jobs()` — supports full-text search on URL; implements pagination with limit/offset
- **Unused endpoints:** `/pages`, `/enqueue` never called from frontend

---

### 12. **runs.py** (147 LOC)
**Prefix:** `/v1`  
**Domain:** Analysis run CRUD

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| POST | `/runs` | Create analysis run (legacy? pipeline_runs/start is primary) | `RunCreateRequest` | `RunCreateResult` | `createRuns` |
| GET | `/runs` | List runs | `campaign_id` (optional), `limit`, `offset` | `list[RunRead]` | `listRuns` |
| GET | `/runs/{run_id}` | Get run detail | — | `RunRead` | ❌ unused |

**Smells & Notes:**
- `/runs/{run_id}` endpoint never called; frontend uses `/runs` list + `pipeline-runs/{run_id}/progress` instead
- Minimal; likely legacy in favor of pipeline_runs.py

---

### 13. **analysis.py** (125 LOC)
**Prefix:** `/v1`  
**Domain:** Analysis job and run detail (minimal)

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| GET | `/runs/{run_id}/jobs` | List analysis jobs for a run | `limit`, `offset` | `list[AnalysisRunJobRead]` | `listRunJobs` |
| GET | `/analysis-jobs/{analysis_job_id}` | Get analysis job detail (classification, document scraped, etc.) | — | `AnalysisJobDetailRead` | `getAnalysisJobDetail` |

**Smells & Notes:**
- Minimal; mostly read-only detail pages

---

### 14. **prompts.py** (92 LOC)
**Prefix:** `/v1`  
**Domain:** Analysis prompts (for LLM classification)

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| GET | `/prompts` | List prompts | `enabled_only` | `list[PromptRead]` | `listPrompts` |
| POST | `/prompts` | Create prompt | `PromptCreate` | `PromptRead` | `createPrompt` |
| PATCH | `/prompts/{prompt_id}` | Update prompt | `PromptUpdate` | `PromptRead` | `updatePrompt` |
| DELETE | `/prompts/{prompt_id}` | Delete prompt | — | 204 No Content | `deletePrompt` |

**Smells & Notes:**
- Straight CRUD for LLM prompts

---

### 15. **scrape_prompts.py** (181 LOC)
**Prefix:** `/v1`  
**Domain:** Web scrape extraction prompts (LLM-based)

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| GET | `/scrape-prompts` | List scrape extraction prompts | `enabled_only` | `list[ScrapePromptRead]` | `listScrapePrompts` |
| POST | `/scrape-prompts` | Create scrape prompt | `ScrapePromptCreate` | `ScrapePromptRead` | `createScrapePrompt` |
| PATCH | `/scrape-prompts/{prompt_id}` | Update scrape prompt | `ScrapePromptUpdate` | `ScrapePromptRead` | `updateScrapePrompt` |
| DELETE | `/scrape-prompts/{prompt_id}` | Delete scrape prompt | — | 204 No Content | `deleteScrapePrompt` |
| POST | `/scrape-prompts/{prompt_id}/activate` | Activate a prompt (single active?) | — | `ScrapePromptRead` | `activateScrapePrompt` |

**Smells & Notes:**
- Similar to prompts.py but for scrape extraction
- `/activate` endpoint implies only one active at a time; no validation visible

---

### 16. **queue_history.py** (198 LOC)
**Prefix:** `/v1`  
**Domain:** Job event history and audit log

| METHOD | PATH | Purpose | Request | Response | Frontend Caller(s) |
|--------|------|---------|---------|----------|-------------------|
| GET | `/queue-history` | List job events (state transitions, errors) | `campaign_id`, `stage`, `view`, `limit`, `offset` | `QueueHistoryResponse` | `getQueueHistory` |

**Smells & Notes:**
- Single endpoint; logs job state changes, errors, retries
- Supports filtering by stage (scrape, analysis, contact_fetch, etc.) and view type

---

## Cross-Cutting Observations

### 1. **Duplication of Aggregation Patterns**
Multiple routers implement similar SQL aggregation patterns:
- **contacts.py:515-662** — `list_contacts_by_company()` (companies grouped by contact stats)
- **discovered_contacts.py:408-500** — `list_discovered_companies()` (nearly identical pattern)
- Both compute: title_matched_count, email_count, fetched_count, verified_count, campaign_ready_count, eligible_verify_count

These should be extracted to a shared service or single endpoint variant.

### 2. **Filtering Logic Scattered Across Routes**
- **contacts.py:165-216** — `_apply_contact_filters()` helper with 11+ conditions
- **companies.py:169-300+** — decision_filter, scrape_filter, stage_filter tree
- **discovered_contacts.py:** Similar filter validation repeated
- **scrape_jobs.py:** Separate status_filter logic

**Recommendation:** Extract filter builders to a shared query-service layer.

### 3. **Idempotency Handling (Partial & Inconsistent)**
- **Implemented in:**
  - `fetch_contacts_selected()` — X-Idempotency-Key (contacts.py:368)
  - `verify_contacts()` — X-Idempotency-Key (contacts.py:996)
  - `reveal_discovered_contact_emails()` — X-Idempotency-Key (discovered_contacts.py:502)
  - `start_run()` — X-Idempotency-Key (pipeline_runs.py:100)
  - `scrape_selected()`, `scrape_all()` — X-Idempotency-Key (scrape_actions.py)
- **Missing in:**
  - `/companies/delete` — POST but no idempotency key
  - `/campaigns/{id}/assign-uploads` — non-idempotent assign
  - All CRUD endpoints (campaigns, prompts, etc.)

**Smell:** Boilerplate idempotency code in every endpoint; no middleware to centralize.

### 4. **Admin Endpoints Without Visible Auth/Authz**
- **queue_admin.py:** All 13 endpoints are dangerous operations (drain, reset, recompute) but no `@require_admin` decorator visible
- **settings.py:** Encryption key updates allowed without role check visible
- **Assumption:** Auth middleware upstream blocks non-admin users, but no local validation

### 5. **Schema Duplication & Overlap**
Multiple overlapping contact models:
- `ProspectContactRead` (prospects after verification)
- `DiscoveredContactRead` (from scrape)
- `ContactCompanySummary` (aggregate stats)
- Multiple `ContactFetchResult`, `ContactVerifyResult` variants

No single canonical "Contact" schema; callers must manage 3+ variants per operation.

### 6. **N+1 Query Risks**
- **contacts.py:791-814** — Batch-fetches DiscoveredContact data post-query to fill `last_seen_at`, `provider_has_email`; inline loop with dict lookup (works but could use JOIN)
- **companies.py:50-141** — 5 subqueries with DISTINCT; SQLAlchemy may lazy-load relationship data if not explicitly prefetched
- **Large list endpoints:** No visible `.options(joinedload(...))` or explicit select conditions

### 7. **Business Logic in Endpoints (No Service Layer)**
- **Pipeline stage recomputation:** Called directly from companies.py PUT feedback (line 340+) and settings.py PUT integration (line 280+); could be slow
- **Contact queue enqueue:** `ContactQueueService().enqueue_fetches()` (contacts.py:250) — is a service but complex logic mixed with idempotency + query validation
- **Email reveal queue:** `ContactRevealQueueService().enqueue_reveals()` (discovered_contacts.py:502) — similar pattern

**No abstraction for:**
- Job state machine (transitions, validation)
- Bulk filter application (reused in contacts + companies + discovered)
- Pagination normalization (limit/offset validation in every endpoint)

### 8. **Likely-Dead Endpoints**
Never called from frontend (api.ts) or admin:
- `/jobs/mark-non-completed-failed` (queue_admin.py:144)
- `/jobs/mark-empty-completed-failed` (queue_admin.py:226)
- `/runs/refresh-status` (queue_admin.py:245)
- `/contacts/admin/runtime-control` GET/PATCH (queue_admin.py:303, 309)
- `/contacts/admin/backlog` (queue_admin.py:332)
- `/contacts/admin/retry-failed` (queue_admin.py:405)
- `/contacts/admin/replay-deferred` (queue_admin.py:472)
- `/scrape-jobs/{id}/pages` (scrape_jobs.py)
- `/scrape-jobs/{id}/enqueue` (scrape_jobs.py)
- `/runs/{run_id}` GET (runs.py)
- `/costs/reconciliation-summary` (pipeline_runs.py)

**Impact:** ~10-15% of endpoints unused; candidates for removal or consolidation.

### 9. **Inconsistent Pagination**
- Most use `limit` (default 50, max 500) + `offset`
- Some use `limit` (default 25, max 200)
- `/uploads`: default 20
- No cursor-based pagination; potential performance issue on large datasets with high offset

### 10. **Error Handling & Status Codes**
- 404 for missing resources (consistent)
- 422 for validation errors (consistent)
- 201 for resource creation (mostly used, not all)
- 204 for DELETE (used)
- 503 for queue unavailable (used in contacts/verify)
- 409 for idempotency conflict (used in some endpoints)

**Missing:** 400 for bad request (uses 422), no 429 rate-limit responses visible

### 11. **Fat Endpoints (>80 LOC)**
| File | Function | LOC | Complexity |
|------|----------|-----|-----------|
| contacts.py | list_contacts_by_company | 148 | Massive SQL aggregation + match_gap filter logic |
| contacts.py | list_all_contacts | 176 | Letter counts, sorting, DiscoveredContact batch lookup |
| companies.py | list_companies | 228+ | Multiple joins, decision/scrape/stage filter tree, sort handling |
| discovered_contacts.py | list_discovered_companies | 92 | Aggregation + HAVING clauses + match_gap filter |
| pipeline_runs.py | start_run | 190 | Job creation loop, idempotency, stage recomputation |
| stats.py | get_stats | 300+ | Per-stage job counting, ETA calculation, throughput sampling |

**Candidates for extraction:** Sorting logic, filter builders, aggregation queries → service layer.

### 12. **Hard-Coded Constants**
- `stats.py:25` — `SCRAPE_RUNNING_STUCK_MINUTES = 35` (matches Beat reconciler)
- `stats.py:29-30` — `_SAMPLE_SIZE = 100`, `_THROUGHPUT_WINDOW_MINUTES = 60`
- `contacts.py:73-74` — `_ALLOWED_CONTACT_STAGE_FILTERS`, `_ALLOWED_MATCH_GAP_FILTERS` (sets of strings)
- `companies.py:143-300` — Decision/stage filter logic duplicated as if-else trees

**Recommendation:** Move to Pydantic config, ENV vars, or database.

### 13. **Missing Validation**
- No request body size limits visible
- No explicit rate-limiting headers (X-RateLimit-*)
- Filter parameters not always validated at schema level (string validation then .lower() in handler)
- Campaign/upload scope validation scattered (some endpoints check, some assume upstream)

### 14. **Feature Overlap: Two Ways to List Contacts**
- `GET /contacts` — global contact list with 9 filters
- `GET /companies/{id}/contacts` — company-scoped subset with 4 filters
- Frontend uses both in different views

Could unify with optional `company_id` parameter.

---

## Recommendations for Review

**Before refactoring, decide:**

1. **Keep admin endpoints?** (queue_admin.py) — Are they actively used in ops? Safe to remove if not.
2. **Consolidate contact/discovered contact routes?** — Two parallel APIs (contacts.py vs discovered_contacts.py) doing similar things.
3. **Centralize filter + sort logic?** — Extract to middleware or shared service to reduce duplication.
4. **Idempotency as middleware?** — Consider wrapping all mutating endpoints with automatic idempotency key handling.
5. **Remove dead endpoints?** — Confirm no external integrations depend on them before deletion.
6. **Split stats.py?** — Separate route for cost vs pipeline stats; decouple from main router.
7. **Add query service layer?** — All the SQL logic in endpoints makes them hard to test and maintain.

