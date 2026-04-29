# Architecture Overview — Backend Simplification

**Date:** 2026-04-29
**Status:** Approved direction, phased execution

## The Principle

> **Postgres owns state. Procrastinate owns execution. App tables own business facts.**

Every line of new code and every new table must answer one question: which of these three responsibilities does it serve? If the answer is unclear, the design is wrong.

## The Problem

The codebase has accumulated a separate "job bookkeeping" table for nearly every async operation:

```
contact_fetch_jobs, contact_fetch_batches, contact_provider_attempts,
contact_reveal_jobs, contact_reveal_batches, contact_reveal_attempts,
contact_verify_jobs, analysis_jobs, crawl_jobs, runs, pipeline_runs, ...
```

These exist because Celery + Redis don't give us durable, queryable job state in Postgres. Each table has its own state column, its own retry logic, its own dead-letter handling — all reinventing the same wheel with subtle inconsistencies (uppercase vs lowercase enum values, `completed` vs `succeeded`, status fields holding error reasons).

The result: 28 tables, ~50% of which are operational not durable; case-inconsistent enums papered over with `func.lower()`; a frontend that has no single answer to "what's running right now?"

## The End State

**~13 business-fact tables** holding what survives a worker restart:

```
campaigns, uploads, companies, company_feedback,
crawl_artifacts, classification_results, contacts,
title_match_rules, integration_secrets, ai_usage_events,
pipeline_runs, pipeline_run_events,
external_provider_attempts          ← new, generic, replaces 5+ tables
prompts, scrape_prompts             ← consolidate later
```

**Procrastinate's internal tables** for execution state (queued, running, retrying, dead, locked). Queryable directly via SQL.

**Everything else is dropped or archived.**

## Migration Philosophy

1. **Clean break, no compatibility shims.** Old endpoints get deleted. Old tables get dropped. The frontend updates to the new contracts in the same sprint. We are not maintaining two parallel systems.
2. **Migrate one stage at a time.** Verification → reveal → fetch → analysis → scrape. Each phase is a separate PR with its own acceptance tests.
3. **Drop legacy tables when their replacement is in place.** No read-compatibility period — if the frontend or any service still reads an old table, that's a bug to fix, not a reason to keep the table.
4. **No new app table to track async work.** Create app tables only for business facts you need after the worker finishes.

## Sequencing

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Canonical state vocabulary — lowercase, normalized, separate failure_reason from state | This sprint (2 weeks) |
| 2 | `external_provider_attempts` table design | After Phase 1 |
| 3 | Procrastinate alongside Celery — pilot with `verify_contact_email` | After Phase 2 |
| 4 | Migrate contact fetch + reveal → Procrastinate | After Phase 3 stable |
| 5 | Migrate analysis + scrape → Procrastinate | Last, most critical |

Phases 2–5 execution plans are deliberately not written yet. Phase 1 will surface decisions that reshape them.

## Decision Rules for Engineers

When in doubt during execution:

- **Adding a new state value?** Update the State Vocabulary Spec first, then code.
- **Tempted to create a job/batch/attempt table?** Don't. Use Procrastinate (Phase 3+) or `external_provider_attempts` (Phase 2+).
- **Status column holding an error reason?** Wrong. Add a separate `failure_reason` column.
- **Frontend asking "what's running?"** Answer from Procrastinate after Phase 3, from current job tables before.
- **Frontend asking "how many companies are contact_ready?"** Answer from `companies.pipeline_stage` — always.

## What Success Looks Like at End of Sprint (Phase 1 Complete)

- All state/stage/label values are lowercase across DB and code
- `succeeded` everywhere, never `completed`
- `state` for jobs, `pipeline_stage` for entities, `verdict` or `label` for classifications
- `failure_reason` is its own column, never embedded in state
- No code path uses `func.lower()` to handle case mismatches between DB and Python
- Existing data migrated cleanly; no orphaned old values
- Frontend integrations still functional (acceptance test suite green)
