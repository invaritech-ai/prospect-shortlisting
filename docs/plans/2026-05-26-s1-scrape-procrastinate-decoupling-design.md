# S1 Scrape Procrastinate Decoupling Design

## Decision

Use the recommended model:

- `scrape_results` is the only app-owned data/work/result table for S1 scrape execution.
- `procrastinate_jobs` is the queue transport and execution lifecycle table.
- `scrape_batches` groups one user action, snapshots settings, and provides batch identity. Its counters/state are derived or cached, not authoritative.
- `uploaded_domains.scrape_status` remains a denormalized list/filter cache, not a source of truth.
- No new tables.

## Why The Current Implementation Is Not Clean

The current implementation has multiple overlapping state machines:

- Procrastinate has `todo`, `doing`, `succeeded`, `failed`, `cancelled`, `aborting`, `aborted`.
- `scrape_results` has app states such as `queued`, `dispatched`, `running`, `succeeded`, `failed`.
- `scrape_batches` has `queued`, `dispatching`, `running`, `completed`, `failed`, plus denormalized counters.
- `uploaded_domains.scrape_status` duplicates latest domain state.
- The frontend mixes batch counters, domain status, active-batch polling, and list polling.

This made queue lifecycle and product scrape outcome drift apart. The observed stale `1 running` happened because Procrastinate had already finished a task, but `scrape_results` and `scrape_batches` still had non-terminal app state.

## Procrastinate Semantics

Procrastinate owns task execution lifecycle only.

Relevant `procrastinate_jobs.status` values in Procrastinate 2.15.1:

- `todo`: job is queued.
- `doing`: worker is executing the job.
- `succeeded`: task function returned normally.
- `failed`: task function raised and retry policy is exhausted or failure is terminal.
- `cancelled`, `aborting`, `aborted`: cancellation/abort states.

Important distinction:

- `procrastinate_jobs.status = succeeded` means the task reached its terminal handling path.
- `scrape_results.state = succeeded` means usable markdown was produced.
- `scrape_results.state = failed` means the scrape reached terminal business failure.

A worker dying mid-task is a queue/infra failure. Procrastinate should recover/retry it. The app row may still say `running`; the next worker must safely reprocess the same `result_id`.

## Target State Model

`ScrapeResult.state` should use only product/work states:

- `queued`: app created the work item and a queue job should exist or soon exist.
- `running`: a worker started processing the result.
- `succeeded`: markdown payload was written.
- `failed`: terminal business failure was written.

Remove S1 dependency on these app states:

- `dispatched`
- `dispatching`
- `retrying`

Queue transport states belong to Procrastinate, not `scrape_results`.

## Target Flow

### Create Job

`POST /v1/scrape-jobs`:

1. Check Procrastinate schema readiness.
2. Reject if there is an active S1 batch for the campaign.
3. Resolve explicit domain IDs and/or filters.
4. Load/snapshot scrape settings.
5. Create `scrape_batches` row.
6. Create one `scrape_results` row per domain with `state = queued`.
7. Set `uploaded_domains.scrape_status = queued` as a denormalized UI cache.
8. Directly enqueue one Procrastinate `scrape_domain(result_id)` job per result.
9. Return batch projection.

No S1 dispatcher job. No `dispatched` state.

### Worker

`procrastinate scrape_domain(result_id)`:

1. Load `scrape_results` row.
2. If `state = succeeded`, return normally.
3. If `state = failed` and `retryable = false`, return normally.
4. If `state in ('queued', 'running')`, claim/process the row.
5. Mark `state = running`, update timestamp.
6. Perform DNS, discovery, fetch, markdown conversion.
7. If markdown exists, write `scraped_pages_json`, counts, final URL, mark `state = succeeded`, update `uploaded_domains.scrape_status = succeeded`, return normally.
8. If business-terminal failure occurs, write error fields, failure class, retryable flag, mark `state = failed`, update `uploaded_domains.scrape_status = failed`, return normally.
9. If unexpected infra/process error occurs, raise so Procrastinate owns retry/recovery.

The worker must be idempotent. Reprocessing `running` is allowed because `running` can mean a prior worker died.

## Status Projection API

Add one frontend-facing projection endpoint:

`GET /v1/scrape-jobs/{batch_id}/status`

It returns one object used by the S1 header, progress banner, sidebar live dot, action lock, and ETA.

Fields:

- Batch metadata: `batch_id`, `campaign_id`, `created_at`, `finished_at`.
- Product counts from `scrape_results`: `selected`, `queued`, `running`, `succeeded`, `failed`, `terminal`.
- Queue counts from `procrastinate_jobs`: `todo`, `doing`, `queue_succeeded`, `queue_failed`, `cancelled`, `aborting`, `aborted`.
- Derived state: `queued`, `running`, `completed`, `failed`, or `inconsistent`.
- `eta_seconds` derived from terminal count and elapsed time.
- `inconsistency_reason` if queue and app state disagree.

Derived rules:

- `completed` when `terminal == selected`.
- `running` when any result is `queued/running` and Procrastinate has `todo/doing` jobs for those result IDs.
- `inconsistent` when `scrape_results` has non-terminal rows but no matching queue jobs are `todo/doing`.
- `failed` only for batch-level failure to create/enqueue, not for business failures inside individual scrape rows.

## Frontend Contract

Frontend should stop deriving S1 live state from multiple sources.

Use one batch-status object for:

- desktop top header
- mobile header live dot
- S1 stage header stats
- progress banner
- sidebar badge live dot
- scrape/retry button lock state

Domain table/list data continues to come from `GET /v1/companies`, but its `Updated` and error label are display details, not batch activity truth.

## Reconciliation

No automatic mutation from read APIs in this pass.

If status API detects:

- `scrape_results.state in ('queued', 'running')`
- and no matching Procrastinate job in `todo/doing`

then return:

```json
{
  "state": "inconsistent",
  "inconsistency_reason": "non_terminal_results_without_live_queue_jobs"
}
```

A later admin endpoint can repair this explicitly, but the normal path should avoid creating it.

## Migration / Compatibility

No new DB tables.

No schema migration is required for the first pass if we do not store Procrastinate job IDs. Queue projection can match jobs by `procrastinate_jobs.args->>'result_id'`.

Compatibility choices:

- Keep `POST /v1/scrape-batches` as a wrapper around the new create logic until frontend switches to `POST /v1/scrape-jobs`.
- Keep `GET /v1/scrape-batches/active` as a wrapper around the new status projection initially.
- Stop using `dispatch_scrape_batch` for S1. It can remain temporarily unused until cleanup.

## Testing Strategy

Backend:

- Job creation creates batch/results and enqueues one Procrastinate job per result.
- No dispatcher task is created.
- Worker returns normally for terminal `succeeded` rows.
- Worker returns normally for permanent `failed` rows.
- Worker reprocesses `running` rows to recover worker-death cases.
- Business failure writes `scrape_results.failed` and Procrastinate task succeeds.
- Infra exception raises and leaves row non-terminal for Procrastinate retry.
- Status endpoint reports completed when all results terminal.
- Status endpoint reports inconsistent when app rows are non-terminal but queue has no live jobs.

Frontend:

- S1 header, banner, sidebar, and button lock read from the same status object.
- No stale `1 running` when status endpoint reports completed.
- Buttons unlock when batch state is `completed` or `inconsistent` with explicit error display.
- Table rows continue to show latest per-domain scrape metadata.

## Open Constraints

- The existing working tree contains uncommitted code changes from the previous S1 count/race fix. Implementation must account for or intentionally supersede those changes.
- Procrastinate queue schema remains manually bootstrapped.
- The target DB is Postgres, not SQLite; SQLite tests are acceptable only for pure unit behavior and should not drive DB design.
