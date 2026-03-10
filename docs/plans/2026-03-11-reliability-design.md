# Reliability Design: Transactional Outbox + Redis Streams + CAS Locks

**Date:** 2026-03-11
**Status:** Approved

---

## Motivation

The existing system has three failure gaps:

1. **Creation → enqueue gap** — job row is written but `queue_service.enqueue()` fails (Redis down); job is created but never processed.
2. **Mid-task crash gap** — worker dies after claiming a job but before completing it; job is stuck in `running_*`/`RUNNING` state until manual intervention.
3. **Duplicate delivery gap** — two workers pop the same task from the queue; both write results, producing duplicate output.

This design closes all three gaps with three complementary mechanisms.

---

## Architecture Overview

```
[API handler]
    │ creates job + outbox row (one DB transaction)
    ▼
[job_outbox table]  ←── persistent, survives Redis downtime
    │ polled by OutboxDispatcher (background thread, SELECT FOR UPDATE SKIP LOCKED)
    ▼
[Redis Stream: jobs:stream]  ←── consumer group "workers", at-least-once delivery
    │ XREADGROUP / XACK
    ▼
[Worker process]
    │ CAS-claim job (UPDATE ... WHERE lock_token IS NULL OR expired)
    ▼
[DB write]  ←── guarded by lock_token re-verify before every commit
```

### Recovery Layers

| Layer | Recovers From |
|---|---|
| Outbox dispatcher | Redis down at job creation — row stays pending until Redis recovers |
| Stream PEL reaper | Worker crash mid-task — un-ACKed message reclaimed after idle threshold |
| CAS lock expiry | Duplicate delivery — second worker's CAS fails because first worker's lock is live |
| Startup recovery | Worker restart — `_recover_stuck_jobs` clears locks before spawning children |

> **Note:** CAS locks (Phase 2) and startup lock clearing are already implemented. This design adds the outbox and stream layers.

---

## Section 1: Three Guarantees

1. **At-least-once delivery** — every created job eventually reaches a worker, even if Redis is down at creation time.
2. **At-most-once DB write per job** — CAS lock ensures only one worker claims a job at a time; lock re-verify before every result write prevents stale writes.
3. **Crash recovery without manual intervention** — PEL reaper redelivers un-ACKed messages; startup recovery clears stale locks.

---

## Section 2: Data Model — `job_outbox` Table

```sql
CREATE TABLE job_outbox (
    id              UUID PRIMARY KEY,           -- app-side UUID (avoid pgcrypto dependency)
    job_id          UUID NOT NULL,
    task_type       TEXT NOT NULL,
    payload_json    JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ,                -- NULL = pending
    stream_id       TEXT,                       -- Redis stream entry ID, for audit
    publish_attempts INT NOT NULL DEFAULT 0     -- for debugging / alerting
);

-- Dispatcher query index: fast scan over pending rows ordered by age
CREATE INDEX ix_job_outbox_pending ON job_outbox (created_at)
    WHERE published_at IS NULL;

-- Idempotency: one pending entry per (job_id, task_type)
-- NOTE: use op.create_index(..., unique=True, postgresql_where=...) in Alembic.
-- op.create_unique_constraint does NOT support postgresql_where.
CREATE UNIQUE INDEX uq_job_outbox_pending
    ON job_outbox (job_id, task_type)
    WHERE published_at IS NULL;
```

**Job creation flow (single DB transaction):**
1. `INSERT INTO scrapejob / analysis_jobs ...`
2. `INSERT INTO job_outbox (id, job_id, task_type, payload_json) VALUES (...)`  — app generates UUID to avoid `gen_random_uuid()` / `pgcrypto` dependency.

The unique partial index prevents duplicate outbox rows if the API endpoint is retried before the dispatcher runs.

**Retention cleanup:** The outbox dispatcher only marks rows `published_at = now()`; it never deletes. The slot-0 `_maybe_cleanup` periodic job should also call `OutboxService.delete_published(ttl_days=7)` to prune old rows and keep the table bounded.

---

## Section 3: `QueueService` — Redis Streams

Replace the existing Redis list (`LPUSH` / `BRPOP`) with a Redis Stream + consumer group.

### Key constants

| Setting | Value |
|---|---|
| Stream key | `jobs:stream` |
| Consumer group | `workers` |
| Consumer name | `worker-{slot}` (stable, slot = 0..N-1; not PID) |

### Operations

**Produce (OutboxDispatcher → stream):**
```
XADD jobs:stream * task_type <t> payload_json <json>
```
No `MAXLEN` trimming — trimming can orphan PEL references for un-ACKed entries.

**Consume (Worker main loop):**
```
XREADGROUP GROUP workers CONSUMER worker-{slot}
    COUNT 1 BLOCK 5000
    STREAMS jobs:stream >
```
`>` delivers only new (undelivered) messages. Each message stays in the PEL until ACKed.

**ACK (after clean handler exit):**
```
XACK jobs:stream workers <message_id>
```
ACK is called only when the task handler returns a success signal. `_handle_task` must return `True` on success (including graceful terminal failure) and `False` on unhandled exception. The main worker loop ACKs only on `True`. Unhandled exceptions leave the message in PEL for redelivery.

> **Critical:** `_handle_task` currently swallows all exceptions with a bare `except`. It must be changed to return `bool` — `True` on clean exit, `False` (after logging) on exception — so the caller can decide whether to ACK.

**Group creation (at startup, idempotent):**
```
XGROUP CREATE jobs:stream workers 0 MKSTREAM
```
Start ID `0` consumes any backlog. Use `$` only when starting fresh with no existing messages.

**Stream retention:** No active `MAXLEN` trimming — trimming can orphan PEL references. If storage becomes a concern later, use `XTRIM MINID <id>` where `<id>` is the lowest stream entry ID still referenced in the PEL (confirm with `XPENDING`).

**List → stream migration (one-time, at startup):**
Runs in the `WorkerSupervisor` process before any children are spawned, or in `main()` for single-worker mode. Guard with a Redis `SETNX` lock (`jobs:list_migration_done`) so it runs exactly once across restarts. Reads all entries from the old `jobs:queue` list, XADDs them to the stream, then deletes the list key.

---

## Section 4: Outbox Dispatcher (`OutboxDispatcher`)

Runs as a `threading.Thread` in the slot-0 worker process. Loop interval: 1 second.

```
LOOP every 1s:
  # Step A: read pending rows (FOR UPDATE SKIP LOCKED — no other dispatcher can touch these)
  BEGIN TRANSACTION (read)
    SELECT id, task_type, payload_json
    FROM job_outbox
    WHERE published_at IS NULL
    ORDER BY created_at
    LIMIT 100
    FOR UPDATE SKIP LOCKED
  COMMIT (releases row locks)

  # Step B: for each row, enqueue then mark published
  FOR each row:
    stream_id = XADD jobs:stream * task_type <t> payload_json <json>   ← enqueue FIRST
    if XADD succeeds:
      UPDATE job_outbox
        SET published_at = now(), stream_id = <stream_id>,
            publish_attempts = publish_attempts + 1
        WHERE id = row.id
      COMMIT
    else:
      increment publish_attempts only, leave published_at NULL, COMMIT
      (row retries next loop)
```

**Ordering matters:** XADD before marking published.
- XADD succeeds, DB update fails → stream message exists, outbox retries → duplicate stream entry → CAS deduplicates at job level. Safe.
- XADD fails → row stays pending, retries next loop. Safe.

**`stream_id` and `publish_attempts` are updated only when XADD succeeds.** If XADD fails, only `publish_attempts` is incremented (for alerting).

**Do not hold the DB transaction open during Redis I/O.** The FOR UPDATE lock is released at the end of Step A. Step B opens a separate per-row transaction. This keeps lock hold time short and avoids DB connection exhaustion.

---

## Section 5: PEL Reaper (`WatchdogThread`)

Runs as a `threading.Thread` in the slot-0 worker process. Interval: every 5 minutes.

```
XAUTOCLAIM jobs:stream workers reaper <idle_ms> 0-0 COUNT 200
→ for each reclaimed entry:
    stream_id_new = XADD jobs:stream * task_type <t> payload_json <json>  ← re-add FIRST
    XACK jobs:stream workers <original_message_id>                         ← ack after
```

**Safety rules:**
- **XADD before XACK** — if XADD fails after XACK, the task is lost permanently.
- **Idle threshold > max task duration** — e.g., if scrape step1 can take 25 minutes, set idle threshold to 30+ minutes to avoid premature redelivery.
- Use `XAUTOCLAIM` (Redis 6.2+) rather than `XPENDING` + `XCLAIM`; it's atomic and simpler.

Re-adding as a new stream message (rather than processing inline in the reaper) keeps task handling in one place: the worker's main `XREADGROUP` loop.

---

## Section 6: Tests (`tests/`)

**Setup:** `pytest` + `testcontainers-python` (real Postgres + Redis containers, one per session).

| Test | What it proves |
|---|---|
| `test_cas_duplicate_claim` | Two threads claim same job simultaneously; only one wins, both complete without double write |
| `test_cas_lock_expiry_reclaim` | Job's lock is manually backdated; new worker claims it successfully |
| `test_outbox_drain_redis_down` | Job created while Redis container is stopped; outbox row written; dispatcher drains when Redis restarts |
| `test_pel_reaper_reclaims` | Message un-ACKed (simulated crash); reaper reclaims and redelivers; job completes |
| `test_fail_job_clears_lock_on_queued` | Transient failure → job back to QUEUED with `lock_token=NULL` |
| `test_reset_stuck_clears_locks` | `POST /v1/jobs/reset-stuck` clears `lock_token` and `lock_expires_at` |
| `test_duplicate_delivery_idempotent` | Same analysis job delivered twice; only one `ClassificationResult` row persists |
| `test_list_to_stream_migration` (optional) | Old list entries migrated to stream at startup without duplication |

All tests use real containers — no mocks for Postgres or Redis.
`test_outbox_drain_redis_down` stops the Redis container with `container.stop()`, creates a job, then restarts with `container.start()` and asserts the outbox row drains.

---

## Already Implemented (Phase 2)

The following are **already in the codebase** and do not need to be re-implemented:

- `lock_token` / `lock_expires_at` columns on both `ScrapeJob` and `AnalysisJob`
- Alembic migration `b3c4d5e6f7a8_add_job_lock_columns.py`
- CAS claim in `ScrapeService.run_step1`, `run_step2`
- CAS claim in `AnalysisService.run_analysis_job`
- Lock re-verify before every result write in both services
- `_fail_job` clears lock when setting back to QUEUED
- `_recover_stuck_jobs` clears `lock_token` / `lock_expires_at` on startup
- `/v1/jobs/reset-stuck` and `/v1/analysis-jobs/reset-stuck` clear locks

---

## Implementation Order

1. `job_outbox` table + Alembic migration
2. `OutboxService` (write to outbox, drain loop)
3. Rewrite `QueueService` → Redis Streams
4. `OutboxDispatcher` thread (slot-0 worker)
5. `WatchdogThread` / PEL reaper (slot-0 worker)
6. Update job creation endpoints (scrape + analysis) → write to outbox
7. Docker Compose Redis service
8. Startup list → stream migration
9. Test suite (`tests/`)
