# S4 Email Verification Design

**Date:** 2026-06-04

## Goal

S4 is the operator-controlled Email Verification stage. It verifies fetched contact emails through ZeroBounce after S3 has populated `contacts.selected_email`.

This replaces the old S4 reveal and S5 validation product model. Old reveal/S5 semantics do not need compatibility preservation.

## Scope

S4 shows only rows from `contacts` where `selected_email` is present. The normal UI is a contact/email table, not a company table and not a provider evidence ledger.

Each row represents one selected contact email and shows:

- contact name
- title
- company/domain
- selected email
- verification status and substatus
- last verification or update time
- row action

Apollo and Snov remain hidden from S4. ZeroBounce can be named where it affects operator understanding, such as preview, credits, and global integration settings.

## Filters And Search

S4 follows the S1/S2/S3 table conventions:

- real backend data only
- shared campaign stage-count API for sidebar/top/header counts
- pagination
- search
- filters
- select matching
- preview-confirm before spending credits
- explicit status counts and refresh behavior

A-Z chips are company/domain A-Z, not contact-name A-Z. The UI should label this clearly as `Company A-Z`.

Search should match contact name, title, email, and domain.

Filter chips:

- `All`
- `Pending`
- `Checking`
- `Stale`
- `Valid`
- `Undeliverable`
- `Catch-all`
- `Unknown`
- `Failed`

## Status Semantics

`Failed` means a technical or provider failure only:

- ZeroBounce API error
- network timeout
- malformed provider response
- credential/auth/credits failure

Real ZeroBounce verdicts are results, not failures.

UI bucket mapping:

- ZeroBounce `valid` -> `Valid`
- ZeroBounce `invalid`, `do_not_mail`, `spamtrap`, `abuse` -> `Undeliverable`
- ZeroBounce `catch-all` or `catch_all` -> `Catch-all`
- ZeroBounce `unknown` -> `Unknown`
- technical/provider error -> `Failed`

Only fresh `valid` is campaign-ready. `Undeliverable`, `Catch-all`, and `Unknown` remain stored results but are not campaign-ready in v1. There is no manual override for non-valid statuses in v1.

## Eligibility And Actions

The operator can:

- validate one email inline
- select rows and validate the eligible subset
- validate all currently matching unvalidated/stale/failed emails

Every paid validation action goes through preview-confirm, including a single inline row action.

`Validate matching` uses the current filtered/searched set, not the whole campaign unless the whole campaign is currently visible by filters. Copy should make that explicit, for example:

- `Validate 183 matching pending`
- `Validate first 200 of 1,243 matching`

The maximum confirmed batch size is 200 emails.

Selection remains enabled for every row. If a mixed selection contains rows that do not need validation, preview shows both actionable and skipped counts. If no selected rows are actionable, the UI shows a toast explaining that fresh results can be revalidated after 30 days.

Actionable rows:

- `Pending`
- `Stale`
- technical `Failed`

Fresh `Valid`, `Undeliverable`, `Catch-all`, and `Unknown` are filterable and selectable but not actionable until stale.

Never-checked and technical-failed rows use the action label `Validate`. Stale rows use `Revalidate`.

## Staleness And Cache

ZeroBounce results are fresh for 30 days. After 30 days, a verified row is `Stale` and is treated as needing validation.

S4 should add a small reusable email verification cache table keyed by normalized email and provider. It stores:

- normalized email
- provider, currently `zerobounce`
- status
- substatus
- raw result JSON
- validated timestamp

The cache is used across campaigns. Preview shows estimated paid validations and cached result counts. It does not need to show live ZeroBounce credit balance in v1.

Preview can run without ZeroBounce credentials because it only calculates selected, eligible, cached, and paid counts. Confirm requires valid ZeroBounce credentials only when paid validations are needed. If all rows are cache hits, confirmation can succeed without provider credentials.

## Batches And Snapshot Safety

Every confirmed validation action creates a `VerificationBatch`, even if all selected rows are cache hits.

Confirmation immediately marks eligible contacts as checking by setting:

- `verification_batch_id`
- `verified_email_snapshot`
- `verification_applied = false`

The worker verifies the exact enqueue-time email snapshot. Result writeback applies only when the contact still has that same `selected_email`. If S3 changes the selected email during a verification batch, the old snapshot result is not applied and the item is counted as skipped/stale.

This keeps S4 from mutating S3 contact discovery semantics.

## Backend API

Use a new S4 namespace instead of old `/contacts/verify` compatibility routes.

Recommended endpoints:

- `GET /v1/email-verification/contacts`
- `GET /v1/email-verification/contact-ids`
- `GET /v1/email-verification/letter-counts`
- `POST /v1/email-verification/preview`
- `POST /v1/email-verification/batches`
- `GET /v1/email-verification/batches/{id}`
- `GET /v1/email-verification/batches/active?campaign_id=...`

The active batch endpoint should ignore orphan queued/running batch rows unless selected contacts are actually still checking for that batch.

## Worker And Live Updates

S4 uses a separate Procrastinate queue named `validation`, with concurrency 1 by default.

Local worker:

```bash
./scripts/run_worker.sh validation
```

Deployment should include a first-class `worker-validation` service in `docker-compose.yml`.

The worker uses ZeroBounce `validatebatch` once per paid miss set after cache reuse.

Add a notification trigger on `verification_batches` and emit campaign SSE events with `stage: "s4"` so S4 can refresh like S3.

## Counts

Shared S4 badge count:

```text
pending + stale + failed technical + checking
```

Fresh `Valid`, `Undeliverable`, `Catch-all`, and `Unknown` are not included in the badge because they are real outcomes and are not actionable until stale.

Campaign-ready should be derived cheaply from `contacts`, not stored as an old pipeline stage. A contact is campaign-ready when:

- `selected_email IS NOT NULL`
- `verification_applied = true`
- `verification_status = 'valid'`
- `verified_email_snapshot = selected_email`
- `verified_at >= now - 30 days`

The cache table is for reuse and write-time decisions. Normal S4 list and count reads should mostly use `contacts`.

## Non-Goals

- No manual override for non-valid statuses.
- No force-revalidate action for fresh results.
- No provider evidence display in normal S4 UI.
- No live ZeroBounce credit balance in S4 preview.
- No compatibility work for obsolete reveal/S5 product semantics.
