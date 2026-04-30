# Procrastinate Queue Architecture + S1 Scraping

**Date:** 2026-04-30
**Status:** Approved — ready to implement
**Audience:** Implementing engineer

---

## Goal

Replace the deleted Celery workers with a proper Procrastinate queue architecture.
Five named queues, three worker processes, backpressure at enqueue time, priority
on every defer call, idempotent re-entry on every task.

After this plan is fully implemented, S1 Scraping (single-row and bulk) is fully
functional end-to-end. The other four queues exist as stubs, ready to be filled
in when those pipeline stages are rebuilt.

---

## Existing code to preserve (do not rewrite)

| File | What to keep |
|---|---|
| `app/services/scrape_service.py` | `ScrapeJobManager.create_job()` + `ScrapeJobManager.run_scrape()` — intact |
| `app/models/scrape.py` | `ScrapeJob`, `ScrapePage` — intact |
| `app/api/schemas/scrape.py` | `ScrapeJobCreate`, `ScrapeJobRead`, `ScrapeRules` — intact |
| `app/db/session.py` | `get_engine()` already exported; `PS_WORKER_PROCESS` env var already handled (NullPool) |
| `app/queue.py` | Procrastinate `App` singleton — extend `import_paths` only |

---

## Queue → Worker mapping

| Queue | Worker service | `--concurrency` | Rate-limited by |
|---|---|---|---|
| `scrape` | `worker-scrape` | 4 | Browserless concurrent sessions |
| `ai_decision` | `worker-ai` | 2 | OpenRouter RPM per model |
| `contact_fetch` | `worker-provider` | 2 | Apollo / Snov req/min |
| `email_reveal` | `worker-provider` | 2 | Snov reveal credits/min |
| `validation` | `worker-provider` | 1 | ZeroBounce req/sec |

`worker-provider` listens to 3 queues with `--concurrency 5` total (2+2+1).

---

## Priority constants

Define once in `app/jobs/_priority.py` (new, 5 lines):

```python
USER_ACTION = 100    # single-row button click
BULK_USER   = 75     # user selected multiple rows
BULK_PIPELINE = 50   # background campaign pipeline run
```

Import from there in every job file.

---

## Backpressure

### New file: `app/services/queue_guard.py`

```python
"""Backpressure: cap bulk enqueue to avoid flooding queues."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

MAX_QUEUE_DEPTHS: dict[str, int] = {
    "scrape": 300,
    "ai_decision": 200,
    "contact_fetch": 150,
    "email_reveal": 150,
    "validation": 100,
}


def current_depth(engine: Engine, queue: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM procrastinate_jobs "
                "WHERE queue = :q AND status IN ('todo', 'doing')"
            ),
            {"q": queue},
        ).one()
    return int(row[0])


def available_slots(engine: Engine, queue: str, requested: int) -> int:
    """Return how many of `requested` can actually be enqueued right now."""
    depth = current_depth(engine, queue)
    headroom = max(0, MAX_QUEUE_DEPTHS[queue] - depth)
    return min(requested, headroom)
```

Every bulk endpoint calls `available_slots()` before looping over company IDs.
It returns the capped count — never raises. The endpoint response always includes
`queued_count`, `skipped_count`, and `queue_depth` so the frontend can show
"500 queued, 1 200 skipped — queue full."

---

## Files to create / modify

### 1. `app/jobs/_priority.py` _(new)_

```python
USER_ACTION   = 100
BULK_USER     = 75
BULK_PIPELINE = 50
```

### 2. `app/jobs/scrape.py` _(new — first real task)_

```python
"""Procrastinate task: run a single ScrapeJob."""
from __future__ import annotations

import logging
from uuid import UUID

from procrastinate import RetryStrategy

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401 (re-exported for callers)
from app.models import ScrapeJob
from app.queue import app
from app.services.scrape_service import ScrapeJobManager
from sqlmodel import Session

logger = logging.getLogger(__name__)

_manager = ScrapeJobManager()


@app.task(
    name="scrape_website",
    queue="scrape",
    retry=RetryStrategy(max_attempts=2, wait=60),
)
async def scrape_website(job_id: str, scrape_rules: dict | None = None) -> None:
    engine = get_engine()
    # Idempotency: skip if already terminal
    with Session(engine) as session:
        job = session.get(ScrapeJob, UUID(job_id))
    if job is None or job.terminal_state:
        logger.info("scrape_website skipped: job %s already terminal", job_id)
        return
    await _manager.run_scrape(engine=engine, job_id=UUID(job_id), scrape_rules=scrape_rules)
```

Note: `run_scrape()` takes `engine` not `session` — it manages its own sessions
internally for the CAS (claim-and-set) lock operations. Do not change this.

### 3. `app/jobs/ai_decision.py` _(new — stub only)_

```python
"""Procrastinate task stub: AI classification. Body implemented in S2 phase."""
from __future__ import annotations
import logging
from app.queue import app

logger = logging.getLogger(__name__)

@app.task(name="run_ai_decision", queue="ai_decision")
async def run_ai_decision(analysis_job_id: str) -> None:
    logger.warning("run_ai_decision: not yet implemented (job %s)", analysis_job_id)
```

### 4. `app/jobs/contact_fetch.py` _(new — stub)_

```python
from __future__ import annotations
import logging
from app.queue import app

logger = logging.getLogger(__name__)

@app.task(name="fetch_contacts", queue="contact_fetch")
async def fetch_contacts(company_id: str, campaign_id: str) -> None:
    logger.warning("fetch_contacts: not yet implemented")
```

### 5. `app/jobs/email_reveal.py` _(new — stub)_

```python
from __future__ import annotations
import logging
from app.queue import app

logger = logging.getLogger(__name__)

@app.task(name="reveal_email", queue="email_reveal")
async def reveal_email(contact_id: str) -> None:
    logger.warning("reveal_email: not yet implemented")
```

### 6. `app/jobs/validation.py` _(new — stub)_

```python
from __future__ import annotations
import logging
from app.queue import app

logger = logging.getLogger(__name__)

@app.task(name="validate_email", queue="validation")
async def validate_email(contact_id: str) -> None:
    logger.warning("validate_email: not yet implemented")
```

### 7. `app/queue.py` _(update import_paths)_

```python
app = App(
    connector=_connector,
    import_paths=[
        "app.jobs.health",
        "app.jobs.scrape",
        "app.jobs.ai_decision",
        "app.jobs.contact_fetch",
        "app.jobs.email_reveal",
        "app.jobs.validation",
    ],
)
```

### 8. `app/api/routes/scrape_jobs.py` _(new — 3 endpoints)_

```python
"""ScrapeJob REST endpoints: create, get, pages-content."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.api.schemas.scrape import ScrapeJobCreate, ScrapeJobRead, ScrapePageContentRead
from app.db.session import get_engine, get_session
from app.jobs._priority import USER_ACTION
from app.jobs.scrape import scrape_website
from app.models import ScrapeJob, ScrapePage
from app.services.scrape_service import (
    CircuitBreakerOpenError,
    ScrapeJobAlreadyRunningError,
    ScrapeJobManager,
)

router = APIRouter(prefix="/v1", tags=["scrape-jobs"])
_manager = ScrapeJobManager()

_DEFAULT_GENERAL_MODEL = "openai/gpt-4.1-nano"
_DEFAULT_CLASSIFY_MODEL = "inception/mercury-2"


@router.post("/scrape-jobs", response_model=ScrapeJobRead, status_code=201)
async def create_scrape_job(
    payload: ScrapeJobCreate,
    session: Session = Depends(get_session),
) -> ScrapeJobRead:
    try:
        job = _manager.create_job(
            session=session,
            website_url=payload.website_url,
            js_fallback=payload.js_fallback,
            include_sitemap=payload.include_sitemap,
            general_model=payload.general_model or _DEFAULT_GENERAL_MODEL,
            classify_model=payload.classify_model or _DEFAULT_CLASSIFY_MODEL,
        )
        session.commit()
    except ScrapeJobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CircuitBreakerOpenError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    await scrape_website.defer_async(
        job_id=str(job.id),
        scrape_rules=payload.scrape_rules.model_dump() if payload.scrape_rules else None,
        priority=USER_ACTION,
    )
    return ScrapeJobRead.model_validate(job, from_attributes=True)


@router.get("/scrape-jobs/{job_id}", response_model=ScrapeJobRead)
def get_scrape_job(
    job_id: UUID,
    session: Session = Depends(get_session),
) -> ScrapeJobRead:
    job = session.get(ScrapeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ScrapeJob not found.")
    return ScrapeJobRead.model_validate(job, from_attributes=True)


@router.get("/scrape-jobs/{job_id}/pages-content", response_model=list[ScrapePageContentRead])
def list_scrape_job_pages(
    job_id: UUID,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> list[ScrapePageContentRead]:
    if session.get(ScrapeJob, job_id) is None:
        raise HTTPException(status_code=404, detail="ScrapeJob not found.")
    pages = list(
        session.exec(
            select(ScrapePage)
            .where(col(ScrapePage.job_id) == job_id)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return [ScrapePageContentRead.model_validate(p, from_attributes=True) for p in pages]
```

**Note:** `ScrapePageContentRead` must exist in `app/api/schemas/scrape.py`. If it doesn't,
add it:

```python
class ScrapePageContentRead(BaseModel):
    id: int
    job_id: UUID
    url: str
    canonical_url: str
    page_kind: str
    fetch_mode: str
    status_code: int
    title: str
    description: str
    markdown_content: str
    fetch_error_code: str
    created_at: datetime
```

### 9. `app/api/routes/companies.py` _(add 2 endpoints)_

Add these two endpoints. Import `queue_guard`, `scrape_website`, `ScrapeJobManager`,
`ScrapeJob`, `ScrapeJobAlreadyRunningError`, `CircuitBreakerOpenError` at the top.

```python
from app.api.schemas.upload import CompanyScrapeResult
from app.db.session import get_engine
from app.jobs._priority import BULK_USER
from app.jobs.scrape import scrape_website
from app.models import ScrapeJob
from app.services.queue_guard import available_slots, current_depth
from app.services.scrape_service import (
    CircuitBreakerOpenError,
    ScrapeJobAlreadyRunningError,
    ScrapeJobManager,
)

_scrape_manager = ScrapeJobManager()
_DEFAULT_GENERAL_MODEL = "openai/gpt-4.1-nano"
_DEFAULT_CLASSIFY_MODEL = "inception/mercury-2"


@router.post("/companies/scrape-selected", response_model=CompanyScrapeResult)
async def scrape_selected_companies(
    payload: CompanyScrapeRequest,
    session: Session = Depends(get_session),
) -> CompanyScrapeResult:
    validate_campaign_upload_scope(
        session=session,
        campaign_id=payload.campaign_id,
        upload_id=payload.upload_id,
    )
    engine = get_engine()
    company_ids = payload.company_ids

    can_enqueue = available_slots(engine, "scrape", len(company_ids))
    to_enqueue = company_ids[:can_enqueue]
    skipped_capacity = company_ids[can_enqueue:]

    queued_job_ids: list[UUID] = []
    failed_company_ids: list[UUID] = list(skipped_capacity)  # capacity-skipped count as failed

    for company_id in to_enqueue:
        company = session.get(Company, company_id)
        if company is None:
            failed_company_ids.append(company_id)
            continue
        try:
            job = _scrape_manager.create_job(
                session=session,
                website_url=company.normalized_url,
                js_fallback=True,
                include_sitemap=True,
                general_model=_DEFAULT_GENERAL_MODEL,
                classify_model=_DEFAULT_CLASSIFY_MODEL,
            )
            session.commit()
            await scrape_website.defer_async(
                job_id=str(job.id),
                scrape_rules=payload.scrape_rules.model_dump() if payload.scrape_rules else None,
                priority=BULK_USER,
            )
            queued_job_ids.append(job.id)
        except (ScrapeJobAlreadyRunningError, CircuitBreakerOpenError, ValueError):
            session.rollback()
            failed_company_ids.append(company_id)

    return CompanyScrapeResult(
        requested_count=len(company_ids),
        queued_count=len(queued_job_ids),
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids,
    )


@router.post("/companies/scrape-all", response_model=CompanyScrapeResult)
async def scrape_all_companies(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> CompanyScrapeResult:
    """Queue scrape jobs for every company in the campaign with no active scrape."""
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=None)
    engine = get_engine()

    # Companies with no active (non-terminal) scrape job
    active_subq = (
        select(col(ScrapeJob.domain))
        .where(col(ScrapeJob.terminal_state).is_(False))
        .scalar_subquery()
    )
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == campaign_id,
                col(Company.domain).not_in(active_subq),
            )
        ).all()
    )

    can_enqueue = available_slots(engine, "scrape", len(companies))
    to_enqueue = companies[:can_enqueue]

    queued_job_ids: list[UUID] = []
    failed_company_ids: list[UUID] = []

    for company in to_enqueue:
        try:
            job = _scrape_manager.create_job(
                session=session,
                website_url=company.normalized_url,
                js_fallback=True,
                include_sitemap=True,
                general_model=_DEFAULT_GENERAL_MODEL,
                classify_model=_DEFAULT_CLASSIFY_MODEL,
            )
            session.commit()
            await scrape_website.defer_async(
                job_id=str(job.id),
                priority=BULK_PIPELINE,
            )
            queued_job_ids.append(job.id)
        except (ScrapeJobAlreadyRunningError, CircuitBreakerOpenError, ValueError):
            session.rollback()
            failed_company_ids.append(company.id)

    skipped = len(companies) - can_enqueue
    return CompanyScrapeResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids + [c.id for c in companies[can_enqueue:]],
    )
```

**Note:** `CompanyScrapeRequest` and `CompanyScrapeResult` already exist in
`app/api/schemas/upload.py`. Import them; do not redefine.

### 10. `app/main.py` _(register new router)_

```python
from app.api.routes.scrape_jobs import router as scrape_jobs_router
app.include_router(scrape_jobs_router)
```

### 11. `docker-compose.yml` _(replace single `worker` with 3)_

Remove the existing `worker` service. Add:

```yaml
  worker-scrape:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    environment:
      PS_WORKER_PROCESS: "1"
    depends_on:
      api:
        condition: service_healthy
    command:
      - "uv"
      - "run"
      - "procrastinate"
      - "--app=app.queue.app"
      - "worker"
      - "--queue"
      - "scrape"
      - "--concurrency"
      - "4"
    restart: unless-stopped

  worker-ai:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    environment:
      PS_WORKER_PROCESS: "1"
    depends_on:
      api:
        condition: service_healthy
    command:
      - "uv"
      - "run"
      - "procrastinate"
      - "--app=app.queue.app"
      - "worker"
      - "--queue"
      - "ai_decision"
      - "--concurrency"
      - "2"
    restart: unless-stopped

  worker-provider:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    environment:
      PS_WORKER_PROCESS: "1"
    depends_on:
      api:
        condition: service_healthy
    command:
      - "uv"
      - "run"
      - "procrastinate"
      - "--app=app.queue.app"
      - "worker"
      - "--queue"
      - "contact_fetch"
      - "--queue"
      - "email_reveal"
      - "--queue"
      - "validation"
      - "--concurrency"
      - "5"
    restart: unless-stopped
```

`PS_WORKER_PROCESS=1` activates NullPool in `session.py` — required for all worker
containers.

---

## Execution order

1. Create `app/jobs/_priority.py`
2. Create `app/services/queue_guard.py`
3. Create `app/jobs/scrape.py` (full implementation)
4. Create `app/jobs/ai_decision.py`, `contact_fetch.py`, `email_reveal.py`, `validation.py` (stubs)
5. Update `app/queue.py` — extend `import_paths`
6. Add `ScrapePageContentRead` to `app/api/schemas/scrape.py` if missing
7. Create `app/api/routes/scrape_jobs.py`
8. Extend `app/api/routes/companies.py` with the two new endpoints
9. Register `scrape_jobs_router` in `app/main.py`
10. Rewrite `docker-compose.yml` worker section

**Verification after each step:**

After step 5:
```bash
uv run python -c "from app.queue import app; print(app.import_paths)"
```

After step 9:
```bash
uv run python -c "from app.main import create_app; create_app(); print('OK')"
uv run pytest tests/test_state_enum_contracts.py -q
```

After step 10:
```bash
docker compose up -d
docker compose ps   # all 5 services healthy
curl -s http://localhost:8000/v1/health/live
```

End-to-end smoke test:
```bash
# Create a single scrape job
curl -s -X POST http://localhost:8000/v1/scrape-jobs \
  -H "Content-Type: application/json" \
  -d '{"website_url": "https://example.com"}' | jq .

# Wait 5s, then check status
JOB_ID=<id from above>
curl -s http://localhost:8000/v1/scrape-jobs/$JOB_ID | jq '.state, .terminal_state'

# Check procrastinate_jobs table
psql $DATABASE_URL -c \
  "SELECT task_name, queue, status FROM procrastinate_jobs ORDER BY id DESC LIMIT 5"
```

---

## Acceptance criteria

1. `POST /v1/scrape-jobs` returns `state=created` in < 200 ms
2. `worker-scrape` picks up the job; `GET /v1/scrape-jobs/{id}` shows `state=running` within 5 s
3. Job reaches `terminal_state=true` with `state=succeeded` or `state=failed` (not stuck)
4. `POST /v1/companies/scrape-selected` with 5 company IDs returns `queued_count=5`
5. `POST /v1/companies/scrape-all` with queue already at depth 300 returns `queued_count=0, skipped_count=N`
6. `docker compose ps` shows 5 services all healthy
7. `uv run pytest tests/test_scrape_create.py -q` passes (pre-existing test)
8. `uv run ruff check app/` clean

---

## What stays intentionally broken

- S1 "Reset stuck" / "Drain queue" buttons — these called Redis endpoints; map to
  Procrastinate DB queries in a later pass
- Operations tab scrape timeline — needs `procrastinate_events` query; deferred to
  the Operations rebuild sprint
- S2, S3, S4, S5 pipeline stages — job stubs exist but bodies are empty;
  implemented stage by stage in subsequent sprints
