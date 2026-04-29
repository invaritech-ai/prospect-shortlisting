# Phase 1 — State Vocabulary Normalization

**Sprint:** 2 weeks starting 2026-04-30
**Audience:** Mid-to-senior engineers
**Format:** Goals + acceptance criteria (engineers own the mechanics)

---

## Goal

Bring DB and code into alignment with [State Vocabulary Spec](2026-04-29-state-vocabulary-spec.md). Eliminate the case mismatches, `status`/`state` naming inconsistencies, and embedded failure reasons that have accumulated over time. Leave the codebase ready for Phase 2 (Procrastinate introduction).

**Non-goals (out of scope for this phase):**
- Procrastinate work — Phase 3+
- Dropping legacy job tables — they get dropped when their consumers are migrated, in later phases
- New features or endpoints
- The `external_provider_attempts` consolidation — Phase 2

---

## Acceptance Criteria (Sprint Exit Bar)

The sprint is complete when ALL of the following are true:

1. **No uppercase enum values exist in any state/stage/label DB column.** Verified by SQL spot-checks per the State Vocabulary Spec.
2. **No code path uses `func.lower()` to handle case mismatches.** Grep returns zero hits in service code.
3. **`status` column does not exist on `scrapejob` or `pipeline_runs`** — renamed to `state`.
4. **`failure_reason` column exists** on `scrapejob`, `crawl_jobs`, `contact_fetch_jobs`, `contact_provider_attempts`, `contact_reveal_attempts`. Populated for all rows where `state IN (failed, dead)`.
5. **No `state` column contains a failure reason as its value.** `site_unavailable`, `step1_failed`, etc. live only in `failure_reason`.
6. **`PipelineStage` enum values are `scrape | analysis | contacts | validation`** — no `s1_`, `s2_` prefixes anywhere.
7. **`contacts.provider` renamed to `contacts.source_provider`. `contacts.verification_provider` column exists.**
8. **All 8 stuck `pipeline_runs` rows resolved** — moved to `state=dead`.
9. **The `runs` table is dropped.** Zero references in code.
10. **Frontend renders new vocabulary correctly.** No 500s, no display bugs reported during smoke testing.
11. **Backend test suite passes.** No `# TODO: lowercase migration` comments left behind.
12. **State Vocabulary Spec is the source of truth.** Any new enum value introduced this sprint exists in the spec first.

---

## Scope — Concrete Changes

### DB Migrations
Single Alembic migration handling all changes; engineers may split into multiple if more comfortable, but ordering must respect FK and column-rename constraints.

| Change | Tables affected |
|--------|-----------------|
| Lowercase existing UPPERCASE values | `crawl_jobs.state`, `analysis_jobs.state`, `classification_results.predicted_label` |
| Rename `status` → `state` | `scrapejob`, `pipeline_runs` |
| Rewrite `completed` → `succeeded` | `scrapejob.state`, `contact_fetch_batches.state`, anywhere else using `completed` |
| Add `failure_reason` column (nullable string) | `scrapejob`, `crawl_jobs`, `contact_fetch_jobs`, `contact_provider_attempts`, `contact_reveal_attempts` |
| Extract failure reasons from `scrapejob.state` | `state=site_unavailable` → `state=failed, failure_reason=site_unavailable`; `state=step1_failed` → `state=failed, failure_reason=step1_failed` |
| Resolve 8 stuck `pipeline_runs` | All `state=running` rows that are >24h old → `state=dead` (one-off data fix) |
| Rename `contacts.provider` → `contacts.source_provider` | `contacts` |
| Add `contacts.verification_provider` column (nullable string) | `contacts` |
| Drop `runs` table | After confirming via `grep -rn "from app.models.*Run\b"` and DB FK check that nothing uses it |
| Update `PipelineStage` enum values in DB if stored as text | `pipeline_runs`, `pipeline_run_events`, anywhere a stage is persisted |

### Code Changes
Engineers own the granular file list. The minimum required surface:

- `app/models/pipeline.py` — update enum classes (`CrawlJobState`, `AnalysisJobState`, `PredictedLabel`, `PipelineStage`, `RunStatus`/`PipelineRunStatus`, etc.)
- All services that construct or filter on these values (`*_service.py`, `*_query_service.py`)
- API schemas in `app/api/schemas/` — verify response models match new vocabulary
- API routes — remove `func.lower()` shims
- Tests — update fixtures, expected response payloads
- `app/tasks/` — task code that writes job state
- Delete `runs.py` route and any orphaned schemas after `runs` table is dropped

### Frontend Changes
Frontend engineer pairs with backend on PR review and ships frontend updates same-day as backend merges.

| Backend change | Frontend update |
|----------------|-----------------|
| `predicted_label`: `POSSIBLE` → `possible` | UI label maps must accept lowercase; remove uppercase handling |
| `state`: `SUCCEEDED` → `succeeded`, `completed` → `succeeded` | Status badges, filter dropdowns, progress bars |
| `status` → `state` field rename on pipeline_runs | All response parsing |
| `s1_scrape` → `scrape` etc. | Stage labels in pipeline run views |
| `provider` → `source_provider` | Contact list columns |
| `failure_reason` separate from state | Error display logic — show reason as separate badge |

---

## PR Sequencing

Five PRs landing roughly one every 2 working days. Each PR independently mergeable, frontend updates merge same-day or next-day.

| # | PR title | Scope | Day target |
|---|----------|-------|------------|
| 1 | Lowercase state values + remove case shims | UPPERCASE → lowercase migration; enum class updates; remove `func.lower()` calls | Day 2 |
| 2 | Rename status → state, succeeded over completed | `scrapejob` and `pipeline_runs` column rename; `completed` → `succeeded` everywhere | Day 4 |
| 3 | Extract failure_reason from state | New columns + data migration on scrapejob; service code writes failure_reason | Day 6 |
| 4 | Provider field renames + new column | `contacts.provider` → `source_provider`; add `verification_provider`; PipelineStage prefix removal | Day 8 |
| 5 | Cleanup — drop runs, fix stuck pipeline_runs, frontend polish | Drop `runs` table; one-off pipeline_runs fix; frontend smoke test pass | Day 10 |

Days 11–14 are buffer for surfaced issues, frontend polish, and prep for Phase 2 plan writing.

---

## Risk Register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Migration runs on prod and breaks running scrape tasks | Medium | Migration must be deployable while workers are paused; Phase 1 ops checklist includes `docker compose stop celery-*-worker` before migrate |
| Hidden code path still emits `completed` or uppercase values | High | Pre-merge test: insert 100 jobs through each pipeline, assert all states match spec |
| Frontend not ready for backend deploy | Medium | Frontend engineer reviews each backend PR; same-day deploy windows |
| `runs` table has hidden consumers | Low | Pre-drop check: enable Postgres `log_statement = 'all'` on staging for 24h, grep for `runs` table reads |
| 8 stuck `pipeline_runs` aren't actually safe to mark dead | Low | Manual review by tech lead before the bulk update; if any are <24h old they may still be alive |

---

## Rollback Plan

Each PR's Alembic migration must include a working `downgrade()`. Data migrations (e.g., the `state` value rewrites) must be reversible — if necessary, store a one-off backup table during migration and restore in downgrade.

If a deployed PR causes a P1 incident:
1. Revert the deployment to previous Docker image
2. Run `alembic downgrade -1`
3. Frontend reverts in lockstep

The `runs` table drop is the only irreversible step. Verified safe by zero-references audit before drop.

---

## Scratchpad

All open questions, blockers, and decisions during execution → [`2026-04-29-sprint-scratchpad.md`](2026-04-29-sprint-scratchpad.md).

---

## Phase 2 Preview (informational only — not in scope this sprint)

Once Phase 1 ships, the team is unblocked for:
- Designing the `external_provider_attempts` table that consolidates `contact_provider_attempts` + `contact_reveal_attempts`
- Introducing Procrastinate alongside Celery, piloting with `verify_contact_email`

Phase 2 execution plan will be written week 2 of this sprint based on what Phase 1 surfaces.
