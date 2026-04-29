# Sprint Scratchpad — Phase 1 Onwards

**Format:** Most recent on top per section. Engineers append; tech lead/owner reviews and responds inline. Mark items as resolved by moving them to **Decisions Made** with a one-liner summary.

---

## 📋 Outstanding Items (post Phase 1)

### 1. Test suite has 23 failures + 4 errors (148 pass)
**Severity:** High (blocks CI green)
**Owner:** Open
**Detail:** Pytest collection is now fixed (commit `e920427` updated the imports in 18 test files), but 23 tests still fail when actually run. These are real bugs/contract mismatches surfaced by the recent refactors, not pre-existing.

**Failure clusters:**
- `test_contact_stage_contracts.py` (6 fails) — S4 reveal/list/ids contract mismatches. Check the new `/contacts/*` endpoint shapes against test expectations.
- `test_title_match_test_ui.py` (4 fails) — pydantic validation errors. Schema field changes from earlier work.
- `test_richer_title_rules.py` (4 fails) — regex/seniority match logic broke. Check `title_match_service`.
- `test_companies_list.py` (3 fails) — `discovered/revealed contact counts` and pipeline status filter. Side effect of merging `_discovered_contact_count_subquery` into `_contact_count_subquery` in `company_service.py`.
- `test_scrape_create.py` (2 fails) — likely `status` → `state` rename not propagated everywhere in scrape service.
- 4 misc: `test_beat_reconciler.py`, `test_celery_tasks.py`, `test_analysis_usage_events.py`, `test_campaign_scoping.py`.

**Fix approach:** Run failures one cluster at a time — many will share root causes. Suggested order:
1. `test_scrape_create.py` + `test_beat_reconciler.py` + `test_celery_tasks.py` (likely all `state` rename bleed)
2. `test_companies_list.py` (subquery field name mismatch)
3. `test_contact_stage_contracts.py` (contract drift on new endpoints)
4. `test_title_match_test_ui.py` + `test_richer_title_rules.py` (title match service)
5. Remaining misc

**Estimate:** ~1 day. Suite must be green before Phase 2.

---

### 2. New `/contacts/ids`, `/contacts/counts`, `/contacts/companies` endpoints — architectural question
**Severity:** Medium (consistency, not correctness)
**Owner:** @avi to decide
**Detail:** Commit `e920427` added three new endpoints to satisfy the frontend contracts UI:
- `GET /v1/contacts/ids` — returns all contact IDs matching filters (bulk-select helper)
- `GET /v1/contacts/counts` — `{total, matched, stale, fresh, already_revealed}`
- `GET /v1/contacts/companies` — per-company contact summary (counts + last_attempted)

**The question:** In the previous companies refactor we deliberately killed:
- `GET /companies/ids` (judged unnecessary — frontend should derive from list)
- `GET /companies/counts` (moved to `stats.py`)
- `GET /companies/letter-counts` (judged unnecessary)

**Are the contact equivalents legitimate or violations of that earlier judgment?**
- `/contacts/companies` — genuinely new, no company equivalent. Probably OK to keep.
- `/contacts/ids` — mirrors the killed `/companies/ids`. Same critique applies.
- `/contacts/counts` — mirrors company counts that were moved to `stats.py`. Should this also move to stats?

**Decision needed:** Keep all three? Move counts to stats? Kill `/contacts/ids` in favor of frontend deriving from list?

---

### 3. Frontend integration verification
**Severity:** Medium (deploys will break frontend until verified)
**Owner:** Open
**Detail:** Backend contracts changed in Phase 1:
- `status` → `state` field rename in `pipeline_runs`, scrape job responses
- `predicted_label` values now lowercase (`possible | crap | unknown`)
- Job state values now lowercase (`succeeded | failed | dead | running | queued | cancelled`)
- `failure_reason` is a separate field, not embedded in state
- `provider` → `source_provider` on contacts
- `PipelineStage` values now `scrape | analysis | contacts | validation` (no `s1_` prefixes)

**Plan:**
1. Run frontend smoke tests — list of critical pages: campaign view, company list (all stages), pipeline runs list, contact list
2. Update frontend response parsing for any field that broke
3. Ship frontend update same-day as the backend work was already merged

**Estimate:** Depends on how many places the frontend reads these fields.

---

## 🤔 Open Questions

*(None right now — append below as engineers hit ambiguity)*

---

## ✅ Decisions Made

### 2026-04-29 — Cleaned backend contacts contracts (commit `e920427`)
**Decided by:** Implementer
**What:**
- Replaced stale `ProspectContact` / `DiscoveredContact` test usage with `Contact` across 18 test files
- Removed deleted `Run` / `RunStatus` fixture usage from tests
- Added 3 new contact endpoints: `/v1/contacts/ids`, `/v1/contacts/counts`, `/v1/contacts/companies` (architectural review pending — see Outstanding #2)
- Updated frontend API/types to use canonical fields: `state`, `succeeded`, `source_provider`, `email_revealed`, `pipeline_run_id`
- Expanded `ContactRead` schema for fields the frontend still consumes

**Verified:**
- ruff clean on touched files
- compileall passes
- pytest collection: 185 tests collected (was failing before)
- npm run build passes

**Caveat:** Pytest collection works but the suite is not fully green — 23 fails + 4 errors when run. See Outstanding #1.

### 2026-04-29 — Hard-deleted legacy `runs` lifecycle (commit `0eac22b`)
**Decided by:** Implementer
**What:** Followed the Phase 1.5 plan ([2026-04-29-phase-1-5-hard-delete-runs.md](2026-04-29-phase-1-5-hard-delete-runs.md)) and removed `runs` end-to-end:
- `/v1/runs` route + schemas + `RunService` deleted
- `Run` / `RunStatus` removed from model exports
- `analysis_jobs` rebuilt to carry `prompt_id`, `general_model`, `classify_model` directly (replaces the `run_id` join)
- Analysis APIs repointed to `pipeline_run_id`
- Prompt usage counts now derived from `AnalysisJob.prompt_id`
- Queue-admin's legacy run-refresh endpoint removed
- Migration `3c4d5e6f7081_drop_legacy_runs.py` applied

**Verified:**
- DB at `alembic_version = 3c4d5e6f7081`
- `runs` table gone; `runstatus` enum gone; `analysis_jobs.run_id` column gone
- `analysis_jobs.{prompt_id, general_model, classify_model}` populated with zero nulls
- App imports clean; ruff clean on touched files; state contract tests pass

**Impact:** -155 net lines (524 deletions / 369 additions across 23 files).

### 2026-04-29 — Defer dropping `runs` table to Phase 1.5 *(superseded by hard-delete above)*
**Decided by:** Implementer (per Phase 1 plan rule)
**Why:** Five consumers still reference `Run` — half-dropping would break the API. Cleaner to land as a separate, focused PR. Doesn't block Phase 2 design.

### 2026-04-29 — Backfill `failure_reason='unknown'` for legacy failed scrapes
**Decided by:** Implementer
**Why:** 34,668 existing failed scrape rows had no specific failure reason recorded. Marking them all as `failure_reason='unknown'` keeps the constraint *"failed rows must have a failure_reason"* enforceable in code while acknowledging we can't reconstruct the original reason. Future failed scrapes will get specific reasons.

### 2026-04-29 — Also normalize `job_event_type` enum (not on original spec)
**Decided by:** Implementer
**Why:** Spotted UPPERCASE values during the migration audit. Migrated to lowercase to maintain consistency. Migration: `2b3c4d5e6f70_normalize_job_event_type_enum.py`.

### 2026-04-29 — Add `mypy` to dev dependencies
**Decided by:** Implementer
**Why:** Type-check tightening as part of the quality push. No CI integration yet but available locally.

---

## 🚧 Blockers

*(None right now)*

---

## 📚 Reference Docs (read these first)

- [Architecture Overview](2026-04-29-architecture-overview.md) — north star and principles
- [State Vocabulary Spec](2026-04-29-state-vocabulary-spec.md) — single source of truth for every enum value
- [Phase 1 Execution Plan](2026-04-29-phase-1-state-normalization.md) — what we set out to do
- [Phase 1 Implementation Plan](2026-04-29-phase-1-state-normalization-implementation.md) — what the team did
