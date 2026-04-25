# Procrastinate Migration Design
**Date:** 2026-04-26  
**Status:** Approved for planning

---

## Objective

Replace Celery + Redis with Procrastinate on Postgres. Remove the custom job-tracking infrastructure that was built to compensate for what Celery doesn't provide. The result should be a codebase where each stage of the pipeline is obvious, each service does one thing, and the infrastructure is auditable directly in SQL.

---

## Core Principle: Delete, Don't Replace

The current codebase has ~8,800 lines across services and tasks. A large portion implements things Procrastinate gives for free: job state tracking, retry logic, idempotency, CAS locking, queue dispatch, and event history. The migration is not a rewrite — it is a deletion with a thin replacement layer on top.

---

## Deployment

**Current:** 10+ containers (api, redis, beat, 8 workers)  
**Target:** 4 containers

```
postgres          ← existing; Procrastinate adds its own tables here
api               ← FastAPI, largely unchanged
worker-scrape     ← Procrastinate worker, queue=scrape, concurrency=6-8
worker-pipeline   ← Procrastinate worker, 4 queues, per-queue concurrency
```

**worker-pipeline queue concurrency:**
| Queue     | Concurrency | Constraint            |
|-----------|-------------|-----------------------|
| analysis  | 3–4         | AI API rate limits    |
| contacts  | 3–4         | Snov / Apollo limits  |
| reveal    | 2–3         | Snov / Apollo limits  |
| verify    | 1–2         | ZeroBounce            |

**Memory budget (12GB VPS):**
- worker-scrape: 6–8 Playwright × ~200MB = ~1.5GB
- worker-pipeline: async I/O, ~300MB
- postgres: ~1.5GB
- api: ~200MB
- OS + headroom: ~2GB
- **Total: ~6GB / 12GB**

**Browserless eliminated.** worker-scrape runs local Playwright with Chromium.  
**Redis eliminated.** No broker container, no idle connection issues.

---

## Pipeline Flow

Each company progresses independently. Completing one stage enqueues the next automatically. Two stages require a user action before proceeding.

```
Upload CSV
  └─► scrape_website(company_id)           [queue: scrape, retry: exponential, max 5]
        └─► run_analysis(company_id)        [queue: analysis, retry: exponential, max 3]
              └─► if qualified:
                    fetch_contacts(company_id)  [queue: contacts, retry: exponential, max 3]
                          │
                    ┌─────┘
                    │  USER ACTION: apply title rules → trigger reveal
                    ▼
              reveal_email(contact_id)      [queue: reveal, retry: exponential, max 3]
                    └─► verify_email(contact_id)  [queue: verify, retry: exponential, max 3]
                              └─► campaign ready / exportable
```

**User gates:**
- After contact fetch: user defines title rules, then triggers bulk reveal enqueue
- Disqualified companies stop at analysis — no contact work done

---

## Task Definitions

Five tasks. Each does one thing and enqueues the next on success.

```python
# worker/tasks/scrape.py
@app.task(queue="scrape", retry=ExponentialRetry(max_attempts=5))
async def scrape_website(*, company_id: UUID) -> None:
    result = await ScrapeService().run(company_id)
    await run_analysis.defer_async(company_id=company_id)

# worker/tasks/analysis.py
@app.task(queue="analysis", retry=ExponentialRetry(max_attempts=3))
async def run_analysis(*, company_id: UUID) -> None:
    qualified = await AnalysisService().run(company_id)
    if qualified:
        await fetch_contacts.defer_async(company_id=company_id)

# worker/tasks/contacts.py
@app.task(queue="contacts", retry=ExponentialRetry(max_attempts=3))
async def fetch_contacts(*, company_id: UUID) -> None:
    await ContactService().run(company_id)
    # stops here — reveal is user-triggered

# worker/tasks/reveal.py
@app.task(queue="reveal", retry=ExponentialRetry(max_attempts=3))
async def reveal_email(*, contact_id: UUID) -> None:
    await RevealService().run(contact_id)
    await verify_email.defer_async(contact_id=contact_id)

# worker/tasks/verify.py
@app.task(queue="verify", retry=ExponentialRetry(max_attempts=3))
async def verify_email(*, contact_id: UUID) -> None:
    await VerifyService().run(contact_id)
```

Retry strategy and history live in `procrastinate_jobs`. No custom job tables needed.

---

## Data Model

### What is deleted

These tables and their enums exist solely to track job state that Procrastinate now owns:

| Deleted Table                  | Replaced By                      |
|-------------------------------|----------------------------------|
| `crawl_jobs`                  | `procrastinate_jobs` (scrape queue) |
| `analysis_jobs`               | `procrastinate_jobs` (analysis queue) |
| `contact_fetch_batches`       | deleted — no batch concept needed |
| `contact_fetch_jobs`          | `procrastinate_jobs` (contacts queue) |
| `contact_fetch_runtime_control` | deleted                         |
| `contact_provider_attempts`   | `procrastinate_jobs` (per-provider tasks if needed) |
| `contact_reveal_batches`      | deleted                          |
| `contact_reveal_jobs`         | `procrastinate_jobs` (reveal queue) |
| `contact_reveal_attempts`     | deleted                          |
| `contact_verify_jobs`         | `procrastinate_jobs` (verify queue) |
| `job_events`                  | `procrastinate_events`           |
| `pipeline_runs`               | deleted — company.pipeline_stage is the source of truth |
| `pipeline_run_events`         | deleted                          |

### Enums deleted (13 → 2)

All of these collapse:
- `CrawlJobState`, `AnalysisJobState`, `ContactFetchJobState`, `ContactFetchBatchState`, `ContactProviderAttemptState`, `ContactVerifyJobState`, `PipelineRunStatus`, `PipelineStage`, `RunStatus`, `JobType`

**What remains:**

```python
class CompanyStage(StrEnum):
    UPLOADED      = "uploaded"
    SCRAPING      = "scraping"
    SCRAPE_FAILED = "scrape_failed"
    SCRAPED       = "scraped"
    ANALYZING     = "analyzing"
    QUALIFIED     = "qualified"
    DISQUALIFIED  = "disqualified"
    CONTACTS_FETCHING = "contacts_fetching"
    CONTACTS_READY    = "contacts_ready"

class ContactStage(StrEnum):
    FETCHED       = "fetched"
    REVEALING     = "revealing"
    REVEALED      = "revealed"
    REVEAL_FAILED = "reveal_failed"
    VERIFYING     = "verifying"
    VERIFIED      = "verified"
    CAMPAIGN_READY = "campaign_ready"
```

### What is kept (unchanged)

`Campaign`, `Upload`, `Company`, `CrawlArtifact`, `Prompt`, `ScrapePrompt`, `ClassificationResult`, `CompanyFeedback`, `DiscoveredContact`, `ProspectContact`, `ProspectContactEmail`, `TitleMatchRule`, `AiUsageEvent`

---

## Service Layer

### What is deleted

| Deleted File                          | Reason                                      |
|--------------------------------------|---------------------------------------------|
| `celery_app.py`                      | replaced by `procrastinate_app.py`          |
| `tasks/beat.py`                      | periodic tasks move to Procrastinate cron   |
| `services/contact_queue_service.py`  | dispatch is now `task.defer()`              |
| `services/contact_reveal_queue_service.py` | same                                  |
| `services/contact_runtime_service.py` | CAS locking no longer needed               |
| `services/idempotency_service.py`    | Procrastinate handles idempotency natively  |
| `services/redis_client.py`           | Redis removed                               |
| `services/pipeline_run_orchestrator.py` | pipeline runs deleted                    |
| `services/pipeline_service.py`       | superseded by direct stage transitions      |
| `services/run_service.py`            | superseded                                  |

### What is simplified

Each service becomes a single-responsibility async function:

| Service                   | Current lines | Expected after |
|---------------------------|---------------|----------------|
| `contact_service.py`      | 898           | ~200           |
| `contact_reveal_service.py` | 946         | ~200           |
| `contact_verify_service.py` | 241         | ~150           |
| `fetch_service.py`        | 958           | ~400 (core scraping logic stays) |
| `analysis_service.py`     | 426           | ~250           |

### What is unchanged

`snov_client.py`, `apollo_client.py`, `zerobounce_client.py`, `llm_client.py`, `scrape_service.py` (core logic), `markdown_service.py`, `link_service.py`, `url_utils.py`, `title_match_service.py`, `secret_store.py`, `credentials_resolver.py`, `domain_policy.py`, `scrape_prompt_compiler.py`

Provider clients and scraping logic are untouched.

---

## Scraping: Session & Retry Behaviour

- Each `scrape_website` task creates one Playwright browser session
- All pages for that domain (homepage, about, services, etc.) are fetched within that session
- Human-like behaviour (random delays, realistic headers, no automation fingerprints) is implemented inside `ScrapeService`
- On retry, a fresh session is used — a new fingerprint can help bypass blocks
- `ExponentialRetry(max_attempts=5)` gives: retry at ~1m, ~2m, ~4m, ~8m, ~16m

---

## Reconciliation

Two periodic tasks via Procrastinate's built-in cron:

```python
@app.periodic(cron="*/10 * * * *")
async def reconcile_stuck_jobs() -> None:
    # find companies stuck in *ing states > 35 min, reset to previous stage

@app.periodic(cron="*/15 * * * *")
async def reconcile_openrouter_costs() -> None:
    # existing logic, unchanged
```

No Beat container. Periodic tasks run inside `worker-pipeline`.

---

## Error Visibility

Because Procrastinate uses Postgres, failed jobs are directly queryable:

```sql
-- All failed scrape jobs in a campaign
SELECT pj.* FROM procrastinate_jobs pj
JOIN companies c ON (pj.args->>'company_id')::uuid = c.id
WHERE pj.queue_name = 'scrape'
  AND pj.status = 'failed'
  AND c.upload_id IN (SELECT id FROM uploads WHERE campaign_id = '...');
```

No Redis inspection. No separate monitoring infra. Admin UI can surface this via existing API patterns.

---

## Migration Path

This is a green-field rewrite of the infrastructure layer, not the business logic. The sequence:

1. Add Procrastinate dependency, initialise schema migration
2. Write `procrastinate_app.py` (replaces `celery_app.py`)
3. Write 5 tasks (thin wrappers over existing service logic)
4. Simplify services — strip out CAS locking, dispatch, manual retry
5. Collapse DB models — delete job tables, write Alembic migration
6. Remove Celery, Beat, Redis from `docker-compose.yml`
7. Update API routes that expose job state (point at `procrastinate_jobs`)
8. Update `worker-scrape` Dockerfile to install Playwright + Chromium
9. Test end-to-end on a small campaign before removing old tables

**Estimated effort:** 3–4 days of focused work.  
**Risk:** Low. All provider clients, scraping logic, and AI logic are untouched. The only changes are the wiring between them.
