# Sprint Scratchpad — Phase 1 Onwards

**Format:** Most recent on top per section. Engineers append; tech lead/owner reviews and responds inline. Mark items as resolved by moving them to **Decisions Made** with a one-liner summary.

---

## 📋 Outstanding Items (post Phase 1)

### 1. Broken tests — pre-existing from `DiscoveredContact → Contact` rename
**Severity:** High (blocks CI green)
**Owner:** Open
**Detail:** Full test suite is red. 13 test files still import `ProspectContact` which was deleted in the model consolidation refactor (commit `e0c6fbe`). State vocab work surfaced this; it's not caused by the state vocab work itself.

**Files needing updates:**
- `tests/test_campaign_scoping.py`
- `tests/test_companies_list.py`
- `tests/test_contact_admin.py`
- `tests/test_contact_apollo.py`
- `tests/test_contact_identity.py`
- `tests/test_contact_reveal.py`
- `tests/test_contact_rules.py`
- `tests/test_contact_stage_contracts.py`
- `tests/test_contact_verify.py`
- `tests/test_contacts.py`
- `tests/test_pipeline_runs.py`
- `tests/test_title_match_test_ui.py`
- `scripts/test_scrape.py`

**Fix:** Replace `ProspectContact` with `Contact` (the new unified model). Most usages are `from app.models import ProspectContact` → `from app.models import Contact` plus call site updates. Some assertions about `ProspectContactEmail` need to be removed (table dropped).

**Estimate:** ~1 day mechanical. Not blocking Phase 2 design work but suite must be green before any further DB or model changes.

---

### 2. Frontend integration verification
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
