# Schema Simplification Design

**Date:** 2026-05-16  
**Branch:** `refactor/schema-simplification`  
**Status:** Approved

---

## Mental model

```
Settings define behavior
Batches represent operator actions
Procrastinate owns job execution (never duplicate in DB)
Results store final usable output
Events/logs are optional observability, not product state
```

---

## Target schema — 14 tables

### Settings
| Table | Purpose |
|---|---|
| `integration_secrets` | Encrypted API credentials — unchanged |

### Campaign / Upload / Domain layer
| Table | Purpose |
|---|---|
| `campaigns` | id, name, description, created_at |
| `uploads` | id, campaign_id, filename, checksum, row_count, created_at |
| `uploaded_domains` | Foundation table — see below |

```
uploaded_domains
- id
- campaign_id
- upload_id (nullable — domain belongs to campaign directly post-dedupe)
- raw_url
- normalized_url
- domain
- dedupe_key
- scrape_status      (null / queued / running / succeeded / failed)
- decision_status    (null / queued / running / succeeded / failed)
- fetch_status       (null / queued / running / succeeded / failed)
- verify_status      (null / queued / running / succeeded / failed)
- created_at
```

Status columns are updated as each stage completes. They represent the current state for the domain, not per-batch history (that lives in result tables).

### S1 — Scraping
| Table | Purpose |
|---|---|
| `scrape_settings` | id, campaign_id (nullable), name, instruction_text, structured_rules_json, settings_hash, is_active, created_at |
| `scrape_batches` | id, campaign_id, scrape_settings_id, settings_snapshot_json, settings_hash, state, selected_domain_count, queued_count, success_count, failed_count, created_at, finished_at |
| `scrape_results` | id, campaign_id, domain_id, scrape_batch_id, state, pages_attempted_count, pages_success_count, markdown_pages_count, scraped_pages_json, error_code, created_at, updated_at |

### S2 — Classification
| Table | Purpose |
|---|---|
| `decision_settings` | id, campaign_id (nullable), name, instruction_text, model, settings_hash, is_active, created_at |
| `classification_batches` | id, campaign_id, decision_settings_id, settings_snapshot_json, settings_hash, state, selected_domain_count, queued_count, success_count, failed_count, created_at, finished_at |
| `classification_results` | id, campaign_id, domain_id, scrape_result_id, classification_batch_id, state, predicted_label, confidence, reasoning_json, evidence_json, input_hash, settings_hash, manual_label (nullable), manual_thumbs (nullable), manual_comment (nullable), manually_reviewed_at (nullable), created_at |

AI result and manual feedback stored in separate columns — AI result is never overwritten.

### S3 — Email fetch
| Table | Purpose |
|---|---|
| `role_fetch_criteria` | id, campaign_id, name, include_rules_json, exclude_rules_json, criteria_hash, is_active, created_at. Append-only — create new row when criteria changes. |
| `email_fetch_batches` | id, campaign_id, role_fetch_criteria_id, criteria_snapshot_json, criteria_hash, provider_order_json, state, selected_domain_count, queued_count, success_count, failed_count, created_at, finished_at |
| `contacts` | Per-person rows — see below |

Per-domain fetch status lives in `uploaded_domains.fetch_status`. Contacts are the output.

```
contacts
- id
- campaign_id
- domain_id
- email_fetch_batch_id
- criteria_hash
- first_name
- last_name
- title
- linkedin_url
- title_match (bool)
- apollo_person_id (nullable)
- snov_person_id (nullable)
- apollo_email (nullable)
- snov_email (nullable)
- selected_email (nullable)          ← what S4 verifies
- selected_email_provider (nullable)
- provider_evidence_json
- verification_batch_id (nullable)   ← which batch verified this
- verified_email_snapshot (nullable) ← email at enqueue time
- verification_status (nullable)     ← valid / invalid / catch_all / etc.
- verification_sub_status (nullable)
- verification_raw_json (nullable)
- verification_applied (bool)        ← result written back?
- verified_at (nullable)
- created_at
- updated_at
```

### S4 — Verification
| Table | Purpose |
|---|---|
| `verification_batches` | id, campaign_id, state, selected_count, queued_count, verified_count, valid_count, invalid_count, skipped_count, created_at, finished_at |

No separate `email_verifications` table. Verification result folds into `contacts`.

**Snapshot safety:** when ZeroBounce responds, compare `contact.selected_email` with `contact.verified_email_snapshot`. If they match → apply result, set `verification_applied=true`. If the email changed since enqueue → set `verification_applied=false`, skip. This makes S4 safe when S3 runs concurrently.

---

## Table mapping (old → new)

| Old table(s) | New table | Notes |
|---|---|---|
| `companies` | `uploaded_domains` | Add direct `campaign_id`; add four status columns |
| `scrape_prompts` | `scrape_settings` | Field rename + `settings_hash` |
| `scrape_runs` | `scrape_batches` | Rename + settings FK/snapshot |
| `crawl_artifacts` + `scrapepage` | `scrape_results` | Consolidated; pages → `scraped_pages_json` |
| `prompts` | `decision_settings` | Field rename + `settings_hash`, `model` |
| `classification_results` + `company_feedback` | `classification_results` | Manual fields added; AI result preserved |
| `title_match_rules` | `role_fetch_criteria` | One row per campaign; rules → include/exclude JSON |
| `contact_fetch_batches` | `email_fetch_batches` | Rename + criteria FK/snapshot |
| `contacts` | `contacts` | Merge Apollo+Snov rows; add `selected_email`; fold in verification fields |
| `contact_verify_jobs` | `verification_batches` | Refactored as operator action table |

**Dropped entirely (no migration):**  
`crawl_jobs`, `analysis_jobs`, `contact_fetch_jobs`, `contact_provider_attempts`,  
`contact_reveal_batches`, `contact_fetch_runtime_controls`, `job_events`,  
`pipeline_runs`, `pipeline_run_events`, `ai_usage_events`, `scrapejob`, `scrape_run_items`

---

## Contact merge logic

When migrating existing contacts, deduplicate within the same domain by this priority:

1. Same normalized `selected_email` + domain
2. Same `linkedin_url` + domain
3. Same `provider_person_id` (Apollo or Snov)
4. Same `first_name` + `last_name` (normalized) + domain — last resort only

On merge: Apollo fields → `apollo_*` columns, Snov fields → `snov_*` columns.  
`selected_email` = whichever provider has a non-null email (Apollo preferred).

---

## Migration execution

**Two databases:** `TEMP_DB_URL` (staging) and `PROD_DB_URL` (production).

**One script** (`scripts/migrate_schema.py`) with two explicit modes:

### Mode 1 — `--setup-temp` (run now)

```
Phase 1 — Build new schema in TEMP_DB
  Create all 14 tables via Alembic 0001_initial_schema

Phase 2 — Transform and load into TEMP_DB
  - uploaded_domains  ← companies (campaign_id from upload.campaign_id; add status columns)
  - scrape_settings   ← scrape_prompts
  - scrape_batches    ← scrape_runs
  - scrape_results    ← crawl_artifacts + scrapepage (consolidated)
  - decision_settings ← prompts
  - classification_results ← classification_results + company_feedback
  - role_fetch_criteria    ← title_match_rules (group per campaign → JSON)
  - email_fetch_batches    ← contact_fetch_batches
  - contacts               ← contacts (merge by priority; fold in verification fields)
  - verification_batches   ← contact_verify_jobs
  [PAUSE — print row counts per table, ask "continue?"]

Phase 3 — Verify TEMP_DB
  FK integrity checks
  Row count checks vs PROD
  Spot-check: 5 random contacts, 5 random domains
  [PAUSE — print verification report, confirm before exiting]
```

App is then pointed at TEMP_DB for testing. Nothing touches prod.

### Mode 2 — `--apply-prod` (run later, only when satisfied)

```
Phase 4 — Apply to PROD
  Drop all old tables in PROD_DB
  Create new schema (Alembic 0001)
  Bulk copy all data from TEMP_DB → PROD_DB
  Stamp Alembic version

Phase 5 — Verify PROD
  Row counts match TEMP_DB
  Print final summary
```

`--apply-prod` is an explicit flag. It cannot run accidentally.

---

## Alembic

All existing migration files deleted.  
New `alembic/versions/0001_initial_schema.py` = full new schema as `upgrade()`, empty `downgrade()`.  
`alembic_version` stamped after each mode completes.

---

## Invariants (enforced going forward)

- Never create both a batch table and a job table for the same stage — Procrastinate owns execution
- Settings/criteria rows are append-only; create a new row when they change, never mutate
- Every result table has a `batch_id` FK so counts stay explainable
- `selected_email` is the single field S4 verifies; provider columns are evidence only
- `uploaded_domains` status columns always reflect the latest completed stage outcome
