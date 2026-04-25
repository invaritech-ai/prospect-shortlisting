# Procrastinate Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Celery + Redis with Procrastinate on Postgres, deleting all custom job-tracking infrastructure in the process, leaving a 7-container deployment (postgres, api, scrape worker + 4 specialized pipeline workers for strict per-queue concurrency) with 5 simple async tasks.

**Architecture:** Each pipeline stage is a Procrastinate async task that updates `company.pipeline_stage` directly and enqueues the next task on success. Procrastinate's `procrastinate_jobs` table replaces 13 custom job-tracking tables. All CAS locking, idempotency, and retry logic are removed — Procrastinate handles them natively.

**Tech Stack:** Procrastinate ≥ 2.0 (psycopg v3 connector), psycopg[binary] v3 (already installed; powers both sync and async connectors), SQLModel/SQLAlchemy (sync for API, async for workers via `psycopg` driver), Playwright local (Chromium, no Browserless), Docker Compose.

**Design doc:** `docs/plans/2026-04-26-procrastinate-migration-design.md`

---

## Critical Pre-Condition: DB Copy Test

Before running any migration against the live database, take a `pg_dump` and run the Alembic migration (Task 3) against that copy first. Verify row counts match. Only then run against live.

---

## File Map

### Created
- `app/worker/__init__.py`
- `app/worker/app.py` — Procrastinate app singleton, connector config
- `app/worker/tasks/__init__.py`
- `app/worker/tasks/scrape.py` — `scrape_website` task
- `app/worker/tasks/analysis.py` — `run_analysis` task
- `app/worker/tasks/contacts.py` — `fetch_contacts` task
- `app/worker/tasks/reveal.py` — `reveal_email` task
- `app/worker/tasks/verify.py` — `verify_email` task
- `app/worker/tasks/periodic.py` — reconciliation periodic tasks
- `Dockerfile.worker-scrape` — Playwright + Chromium image
- `alembic/versions/XXXX_procrastinate_migration.py` — DB migration

### Heavily Modified
- `app/models/pipeline.py` — remove 15 job-tracking models, update 2 enums, add `label_source`
- `app/models/scrape.py` — remove `ScrapeJob`, update `ScrapePage` (drop FK to scrapejob, add `company_id`)
- `app/models/__init__.py` — remove deleted model exports
- `app/db/session.py` — remove deleted model imports, add async session
- `app/main.py` — replace `@app.on_event` with lifespan, integrate Procrastinate app
- `app/core/config.py` — remove `redis_url`, keep `database_url`
- `app/services/fetch_service.py` — remove ScrapeJob/lock logic, async rewrite (~400 lines)
- `app/services/analysis_service.py` — remove AnalysisJob/lock/CAS, async rewrite (~250 lines)
- `app/services/contact_service.py` — remove batch/attempt/CAS/dispatch, async rewrite (~200 lines)
- `app/services/contact_reveal_service.py` — same (~200 lines)
- `app/services/contact_verify_service.py` — remove ContactVerifyJob tracking, async rewrite (~150 lines)
- `app/api/routes/contacts.py` — remove idempotency, use `fetch_contacts.defer_async()`
- `app/api/routes/scrape_actions.py` — use `scrape_website.defer_async()`
- `app/api/routes/companies.py` — add manual label override + trigger fetch_contacts endpoint
- `app/api/routes/queue_admin.py` — rewrite: query `procrastinate_jobs` instead of custom tables
- `app/api/routes/queue_history.py` — rewrite: query `procrastinate_jobs`
- `docker-compose.yml` — 7 containers (postgres, api, worker-scrape, worker-analysis, worker-contacts, worker-reveal, worker-verify)

### Deleted
- `app/celery_app.py`
- `app/tasks/` (entire directory)
- `app/services/contact_queue_service.py`
- `app/services/contact_reveal_queue_service.py`
- `app/services/contact_runtime_service.py`
- `app/services/idempotency_service.py`
- `app/services/redis_client.py`
- `app/services/pipeline_run_orchestrator.py`
- `app/services/pipeline_service.py`
- `app/services/run_service.py`
- `app/api/routes/runs.py`
- `app/api/routes/pipeline_runs.py`
- `app/api/routes/scrape_jobs.py` (superseded by scrape_actions.py + upload auto-enqueue)

---

## Task 1: Procrastinate Dependency & App Bootstrap

**Files:**
- Modify: `pyproject.toml`
- Create: `app/worker/__init__.py`, `app/worker/app.py`
- Modify: `app/core/config.py`
- Modify: `app/db/session.py`
- Modify: `app/main.py`

- [ ] **Step 1: Add procrastinate, remove celery/redis from pyproject.toml**

In `pyproject.toml`, replace:
```toml
"celery[redis]>=5.3.0,<5.5",
"redis>=7.2.1",
```
with:
```toml
"procrastinate>=2.0.0",
```
`psycopg[binary]` is already present and is what Procrastinate's `PsycopgConnector` uses. Leave all other deps untouched.

In `[project.optional-dependencies]` test section, replace:
```toml
"testcontainers[postgres,redis]>=4.8.0",
```
with:
```toml
"testcontainers[postgres]>=4.8.0",
```

Also remove these unused test deps that depended on Redis tooling, if present.

- [ ] **Step 2: Install**

```bash
uv sync
```
Expected: resolves without errors.

- [ ] **Step 3: Create `app/worker/__init__.py`**

```python
```
(empty)

- [ ] **Step 4: Create `app/worker/app.py`**

```python
from __future__ import annotations

import procrastinate

from app.core.config import settings


def procrastinate_dsn() -> str:
    """Return a raw `postgresql://` DSN for Procrastinate (strips SQLAlchemy prefix)."""
    url = settings.database_url
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


# Async connector used by both workers and API dispatch routes (which become async).
# `conninfo` is set on the connector itself; `app.open_async()` then opens the pool.
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=procrastinate_dsn()),
    import_paths=["app.worker.tasks"],
)
```

Notes:
- One `App` instance is shared by FastAPI (for `defer_async`) and the workers (for execution). FastAPI dispatch routes that call `defer_async` must be `async def`.
- `import_paths=["app.worker.tasks"]` lets workers discover all task modules without explicit import in `app.py`.

- [ ] **Step 5: Remove `redis_url` from `app/core/config.py`**

Delete the line:
```python
redis_url: str = "redis://127.0.0.1:6379/0"
```

- [ ] **Step 6: Add async DB session to `app/db/session.py`**

At the bottom of the file, add:
```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def _async_url(database_url: str) -> str:
    """Convert a sync SQLAlchemy URL to an async psycopg-driver URL."""
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + database_url[len("postgresql+psycopg2://"):]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]
    return database_url


async_engine = create_async_engine(
    _async_url(settings.database_url),
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency-injection helper: yields an AsyncSession per request."""
    async with AsyncSession(async_engine) as session:
        yield session


@asynccontextmanager
async def async_session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager for use inside Procrastinate tasks (no DI framework)."""
    async with AsyncSession(async_engine) as session:
        yield session
```

Two helpers because FastAPI uses async-generator dependencies but tasks need a context manager. Both produce the same `AsyncSession`.

- [ ] **Step 7: Replace `@app.on_event("startup")` with lifespan in `app/main.py`**

Replace the full `create_app` function with:
```python
from contextlib import asynccontextmanager
from app.worker.app import app as procrastinate_app


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    configure_logging()
    init_db()
    if not (settings.settings_encryption_key or "").strip():
        logger.warning(
            "settings_encryption_key_missing: integration settings writes are "
            "disabled until PS_SETTINGS_ENCRYPTION_KEY is configured"
        )
    # Connector conninfo was set when the connector was constructed in worker/app.py.
    # open_async() opens the connection pool and starts background tasks.
    async with procrastinate_app.open_async():
        yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    origins = [v.strip() for v in settings.cors_allow_origins.split(",") if v.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/v1/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    app.include_router(analysis_router)
    app.include_router(campaigns_router)
    app.include_router(contacts_router)
    app.include_router(companies_router)
    app.include_router(discovered_contacts_router)
    app.include_router(prompts_router)
    app.include_router(queue_admin_router)
    app.include_router(queue_history_router)
    app.include_router(scrape_actions_router)
    app.include_router(scrape_prompts_router)
    app.include_router(settings_router)
    app.include_router(stats_router)
    app.include_router(uploads_router)
    return app


app = create_app()
```
Remove the imports and registrations for `runs_router`, `pipeline_runs_router`, `scrape_jobs_router` — those routes are deleted in Task 10.

- [ ] **Step 8: Add async_session test fixture**

Add the following to `tests/conftest.py` (next to existing sync `session` fixture):
```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel


@pytest_asyncio.fixture
async def async_session(test_database_url):
    """Async session for worker task tests. Uses the same testcontainer DB as sync tests."""
    from app.db.session import _async_url

    engine = create_async_engine(_async_url(test_database_url), echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()
```

If `test_database_url` is not already a fixture, replace with whatever fixture the existing sync `session` fixture uses to get a connection string. (Check `tests/conftest.py` for the pattern.)

- [ ] **Step 9: Initialise Procrastinate schema**

```bash
uv run procrastinate --app app.worker.app.app schema --apply
```
Expected: prints "Applying schema…" and exits 0. Three `procrastinate_*` tables now exist in the database.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml app/worker/ app/core/config.py app/db/session.py app/main.py tests/conftest.py
git commit -m "feat: add procrastinate, async DB session, remove redis/celery deps"
```

---

## Task 2: New Models & Enums

**Files:**
- Modify: `app/models/pipeline.py`
- Modify: `app/models/scrape.py`
- Modify: `app/models/__init__.py`
- Modify: `app/db/session.py`

- [ ] **Step 1: Rewrite enums in `app/models/pipeline.py`**

Replace all existing `StrEnum` definitions at the top of the file with only:
```python
class CompanyStage(StrEnum):
    UPLOADED          = "uploaded"
    SCRAPING          = "scraping"
    SCRAPE_FAILED     = "scrape_failed"
    SCRAPED           = "scraped"
    ANALYZING         = "analyzing"
    QUALIFIED         = "qualified"
    DISQUALIFIED      = "disqualified"
    UNKNOWN           = "unknown"
    CONTACTS_FETCHING = "contacts_fetching"
    CONTACTS_READY    = "contacts_ready"


class ContactStage(StrEnum):
    FETCHED        = "fetched"
    REVEALING      = "revealing"
    REVEALED       = "revealed"
    REVEAL_FAILED  = "reveal_failed"
    VERIFYING      = "verifying"
    VERIFIED       = "verified"
    CAMPAIGN_READY = "campaign_ready"


class PredictedLabel(StrEnum):
    POSSIBLE = "Possible"
    CRAP     = "Crap"
    UNKNOWN  = "Unknown"
```

Delete: `CrawlJobState`, `RunStatus`, `AnalysisJobState`, `JobType`, `ContactFetchJobState`, `ContactFetchBatchState`, `ContactProviderAttemptState`, `CompanyPipelineStage`, `ContactPipelineStage`, `ContactVerifyJobState`, `PipelineRunStatus`, `PipelineStage`.

- [ ] **Step 2: Update `Company` model in `app/models/pipeline.py`**

Replace the `pipeline_stage` field and add `label_source`:
```python
class Company(SQLModel, table=True):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("upload_id", "normalized_url", name="uq_companies_upload_normalized_url"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True)
    raw_url: str = Field(sa_column=Column(Text, nullable=False))
    normalized_url: str = Field(max_length=2048)
    domain: str = Field(max_length=255, index=True)
    pipeline_stage: CompanyStage = Field(
        default=CompanyStage.UPLOADED,
        sa_column=Column(Text, nullable=False, index=True),
    )
    label_source: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # ... rest of fields unchanged
```

- [ ] **Step 3: Update `CrawlArtifact` — drop FK to crawl_jobs**

Change `crawl_job_id` from a FK field to a plain nullable UUID (so existing data is preserved but the FK constraint is gone before we drop crawl_jobs):
```python
class CrawlArtifact(SQLModel, table=True):
    __tablename__ = "crawl_artifacts"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    crawl_job_id: UUID | None = Field(default=None, sa_column=Column(sa.UUID(as_uuid=True), nullable=True))
    # ... rest of fields unchanged (no `foreign_key=` on crawl_job_id)
```

- [ ] **Step 4: Delete job-tracking model classes from `app/models/pipeline.py`**

Remove the following class definitions entirely (keep their table names in mind for the Alembic migration):
- `CrawlJob` (`crawl_jobs`)
- `Run` (`runs`)
- `AnalysisJob` (`analysis_jobs`)
- `ClassificationResult` — **keep this one**
- `CompanyFeedback` — **keep**
- `JobEvent` (`job_events`)
- `PipelineRun` (`pipeline_runs`)
- `PipelineRunEvent` (`pipeline_run_events`)
- `ContactFetchRuntimeControl` (`contact_fetch_runtime_controls`)
- `ContactFetchBatch` (`contact_fetch_batches`)
- `ContactFetchJob` (`contact_fetch_jobs`)
- `ContactProviderAttempt` (`contact_provider_attempts`)
- `ContactRevealBatch` (`contact_reveal_batches`)
- `ContactRevealJob` (`contact_reveal_jobs`)
- `ContactRevealAttempt` (`contact_reveal_attempts`)
- `ContactVerifyJob` (`contact_verify_jobs`)

Keep: `Campaign`, `Upload`, `Company`, `CrawlArtifact`, `Prompt`, `ScrapePrompt`, `ClassificationResult`, `CompanyFeedback`, `AiUsageEvent`, `DiscoveredContact`, `ProspectContact`, `ProspectContactEmail`, `TitleMatchRule`.

- [ ] **Step 5: Update `ProspectContact` pipeline_stage field**

Find and update the `pipeline_stage` field type from `ContactPipelineStage` to `ContactStage`:
```python
pipeline_stage: ContactStage = Field(
    default=ContactStage.FETCHED,
    sa_column=Column(Text, nullable=False, index=True),
)
```

- [ ] **Step 6: Update `app/models/scrape.py` — remove ScrapeJob, update ScrapePage**

Delete the entire `ScrapeJob` class. Update `ScrapePage` to replace the FK on `job_id` with `company_id`:
```python
class ScrapePage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)

    url: str
    canonical_url: str
    depth: int = Field(default=0)
    page_kind: str = Field(default="other")
    fetch_mode: str = Field(default="none")
    status_code: int = Field(default=0)

    title: str = Field(default="")
    description: str = Field(default="")
    text_len: int = Field(default=0)
    raw_text: str = Field(default="")
    markdown_content: str = Field(default="")

    fetch_error_code: str = Field(default="")
    fetch_error_message: str = Field(default="")

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
```

- [ ] **Step 7: Update `app/models/__init__.py`**

Remove exports for all deleted models. The final `__init__.py` should only export:
```python
from app.models.pipeline import (
    AiUsageEvent,
    Campaign,
    ClassificationResult,
    Company,
    CompanyFeedback,
    CompanyStage,
    ContactStage,
    CrawlArtifact,
    DiscoveredContact,
    PredictedLabel,
    Prompt,
    ProspectContact,
    ProspectContactEmail,
    ScrapePrompt,
    TitleMatchRule,
    Upload,
)
from app.models.scrape import ScrapePage
from app.models.settings import IntegrationSecret
```

- [ ] **Step 8: Update `app/db/session.py` model imports**

Replace the massive import block at the top with the slimmed-down list matching the new `__init__.py`.

- [ ] **Step 9: Run tests to confirm model layer compiles**

```bash
uv run pytest tests/ -x --ignore=tests/test_contact_apollo.py --ignore=tests/test_contact_reveal.py --ignore=tests/test_contact_verify.py -q 2>&1 | head -40
```
Expected: import errors may still exist in route/service files (those are fixed later), but model-level tests should pass or skip.

- [ ] **Step 10: Commit**

```bash
git add app/models/ app/db/session.py
git commit -m "feat: collapse models — 15 job-tracking tables removed, 2 enums added"
```

---

## Task 3: Alembic DB Migration

**Files:**
- Create: `alembic/versions/XXXX_procrastinate_migration.py`

> ⚠️ **Run on a DB copy first.** `pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql` before touching live.

- [ ] **Step 1: Generate empty migration**

```bash
uv run alembic revision --autogenerate -m "procrastinate_migration"
```
Expected: creates `alembic/versions/XXXX_procrastinate_migration.py`. Autogenerate will detect the removed models. **Do not use the autogenerated content directly** — replace it entirely with the explicit migration below.

- [ ] **Step 2: Write the upgrade function**

Replace the generated `upgrade()` body with:
```python
def upgrade() -> None:
    # ── 1. Prepare companies table ────────────────────────────────────────

    # Add label_source column
    op.add_column("companies", sa.Column("label_source", sa.Text(), nullable=True))

    # Backfill: classified → qualified / disqualified / unknown
    # Join classification_results to determine correct label per company
    op.execute("""
        UPDATE companies c
        SET
            pipeline_stage = CASE cr.predicted_label
                WHEN 'Possible' THEN 'qualified'
                WHEN 'Crap'     THEN 'disqualified'
                ELSE                 'unknown'
            END,
            label_source = 'ai'
        FROM classification_results cr
        WHERE c.pipeline_stage = 'classified'
          AND cr.company_id = c.id
    """)

    # Any 'classified' with no classification_result (shouldn't exist, safety net)
    op.execute("""
        UPDATE companies
        SET pipeline_stage = 'unknown', label_source = 'ai'
        WHERE pipeline_stage = 'classified'
    """)

    # Rename contact_ready → contacts_ready
    op.execute("""
        UPDATE companies
        SET pipeline_stage = 'contacts_ready'
        WHERE pipeline_stage = 'contact_ready'
    """)

    # ── 2. Prepare crawl_artifacts — drop FK to crawl_jobs ────────────────
    # Find and drop the FK constraint name (may vary by DB):
    op.execute("""
        ALTER TABLE crawl_artifacts
        DROP CONSTRAINT IF EXISTS crawl_artifacts_crawl_job_id_fkey
    """)

    # ── 3. Prepare scrapepage — swap job_id FK for company_id ─────────────
    op.add_column("scrapepage", sa.Column("company_id", sa.UUID(as_uuid=True), nullable=True))
    op.execute("""
        UPDATE scrapepage sp
        SET company_id = sj.company_id
        FROM scrapejob sj
        WHERE sp.job_id = sj.id
          AND sj.company_id IS NOT NULL
    """)
    # Drop old FK constraint on job_id
    op.execute("""
        ALTER TABLE scrapepage
        DROP CONSTRAINT IF EXISTS scrapepage_job_id_fkey
    """)
    op.create_foreign_key(
        "fk_scrapepage_company_id", "scrapepage", "companies", ["company_id"], ["id"]
    )
    op.create_index("ix_scrapepage_company_id", "scrapepage", ["company_id"])

    # ── 4. Drop indexes that reference soon-to-be-dropped columns/tables ──
    op.execute("DROP INDEX IF EXISTS ix_scrapepage_job_id")

    # ── 5. Drop job-tracking tables (order: children before parents) ──────
    op.drop_table("contact_provider_attempts")
    op.drop_table("contact_fetch_jobs")
    op.drop_table("contact_fetch_batches")
    op.drop_table("contact_fetch_runtime_controls")
    op.drop_table("contact_reveal_attempts")
    op.drop_table("contact_reveal_jobs")
    op.drop_table("contact_reveal_batches")
    op.drop_table("contact_verify_jobs")
    op.drop_table("job_events")
    op.drop_table("analysis_jobs")
    op.drop_table("scrapepage")  # WAIT — see note below
    op.drop_table("scrapejob")
    op.drop_table("pipeline_run_events")
    op.drop_table("pipeline_runs")
    op.drop_table("runs")
    op.drop_table("crawl_jobs")
```

> ⚠️ **Important:** Do **not** drop `scrapepage` if it stores valuable scraped page content the project still needs. Verify by checking `app/services/fetch_service.py` and the artifact-loading code in `app/services/analysis_service.py` — does analysis read from `scrapepage` or only from `crawl_artifacts`?
>
> - If analysis reads only `crawl_artifacts`: `scrapepage` is intermediate cache, safe to drop.
> - If analysis reads `scrapepage` directly: keep the table, only swap the FK (already done in Step 3 above), and remove `op.drop_table("scrapepage")` from the list.
>
> Do this check **before generating the migration**. Default assumption in this plan: `scrapepage` is kept (since Task 2 Step 6 modifies its model), so **delete the line `op.drop_table("scrapepage")`** from the list above unless your check confirms it's pure cache.

> **Note on table names:** Verify all table names against `\dt` in psql before running. SQLModel default naming can produce slightly different names (e.g. `contact_fetch_runtime_control` vs `_controls`). The class definitions in `app/models/pipeline.py` use explicit `__tablename__`; cross-reference there.

- [ ] **Step 3: Write the downgrade function**

```python
def downgrade() -> None:
    raise NotImplementedError(
        "This migration is irreversible. Restore from pg_dump to roll back."
    )
```

- [ ] **Step 4: Test on DB copy**

```bash
# Dump live DB
pg_dump $DATABASE_URL > /tmp/prospect_backup_$(date +%Y%m%d_%H%M%S).sql

# Restore to a test DB
createdb prospect_test
psql prospect_test < /tmp/prospect_backup_*.sql

# Run migration against copy
DATABASE_URL=postgresql://user:pass@localhost/prospect_test uv run alembic upgrade head
```

Verify with:
```sql
-- Should return 0 (no more 'classified' rows)
SELECT COUNT(*) FROM companies WHERE pipeline_stage = 'classified';

-- Should return 0 (no more 'contact_ready' rows)
SELECT COUNT(*) FROM companies WHERE pipeline_stage = 'contact_ready';

-- Count should match pre-migration classified count
SELECT pipeline_stage, COUNT(*) FROM companies
WHERE pipeline_stage IN ('qualified', 'disqualified', 'unknown')
GROUP BY pipeline_stage;

-- All job tracking tables should be gone
SELECT tablename FROM pg_tables WHERE tablename IN
  ('crawl_jobs', 'analysis_jobs', 'contact_fetch_jobs', 'pipeline_runs', 'runs');
-- Expected: 0 rows
```

- [ ] **Step 5: Run against live DB once copy test passes**

```bash
uv run alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add alembic/
git commit -m "feat: migrate schema — backfill company stages, drop 15 job-tracking tables"
```

---

## Task 4: Scrape Task + Service

**Files:**
- Create: `app/worker/tasks/__init__.py`, `app/worker/tasks/scrape.py`
- Modify: `app/services/fetch_service.py` (remove ScrapeJob logic, keep scraping core)
- Modify: `app/services/scrape_service.py` (remove ScrapeJob creation, work with company_id)

- [ ] **Step 1: Create `app/worker/tasks/__init__.py`**

```python
```
(empty)

- [ ] **Step 2: Create `app/worker/tasks/scrape.py`**

```python
from __future__ import annotations

import logging
from uuid import UUID

import procrastinate

from app.core.logging import log_event
from app.db.session import async_session_scope
from app.models.pipeline import Company, CompanyStage
from app.worker.app import app

logger = logging.getLogger(__name__)


@app.task(
    queue="scrape",
    retry=procrastinate.ExponentialRetry(
        max_attempts=5, wait_minimum=60, wait_multiplier=2, wait_jitter=15,
    ),
)
async def scrape_website(*, company_id: str) -> None:
    from app.services.scrape_service import ScrapeService
    from app.worker.tasks.analysis import run_analysis  # local import to avoid cycle on worker boot

    cid = UUID(company_id)

    async with async_session_scope() as session:
        company = await session.get(Company, cid)
        if company is None:
            log_event(logger, "scrape_company_not_found", company_id=company_id)
            return
        company.pipeline_stage = CompanyStage.SCRAPING
        await session.commit()

    try:
        async with async_session_scope() as session:
            await ScrapeService().run(session=session, company_id=cid)
        await run_analysis.defer_async(company_id=company_id)
        log_event(logger, "scrape_done", company_id=company_id)
    except Exception:
        async with async_session_scope() as session:
            company = await session.get(Company, cid)
            if company is not None:
                company.pipeline_stage = CompanyStage.SCRAPE_FAILED
                await session.commit()
        raise
```

- [ ] **Step 3: Simplify `ScrapeService` signature**

In `app/services/scrape_service.py`, change the primary entry point from:
```python
async def run_scrape(self, *, engine: Any, job_id: str, scrape_rules: dict | None) -> None:
```
to:
```python
from sqlalchemy.ext.asyncio import AsyncSession

async def run(self, *, session: AsyncSession, company_id: UUID) -> None:
    """Scrape one company's website. Updates pipeline_stage to SCRAPED on success."""
```

Remove all `ScrapeJob` creation, lock acquisition, and status update logic. The new method:
1. `company = await session.get(Company, company_id)` — fail fast if missing
2. Load scrape rules: `rules = scrape_rules_store.load_active_rules(session=session)` (the existing `load_rules_for_job` is replaced — see fetch_service rewrite below)
3. Invoke fetch core: `result = await self._fetch_pages(domain=company.domain, normalized_url=company.normalized_url, rules=rules)`
4. Persist: write a `ScrapePage` per fetched page and one `CrawlArtifact` per company (delete pre-existing ScrapePages for this company first to avoid duplicates on retry)
5. `company.pipeline_stage = CompanyStage.SCRAPED` then `await session.commit()`

Keep all actual HTTP fetching, markdown conversion, link-following, stealth/static tier escalation, and circuit-breaker logic — those exist in `fetch_service.py` and are correct.

- [ ] **Step 4: Update `fetch_service.py` — remove ~600 lines of ScrapeJob tracking**

Methods/functions to **delete** (these manage ScrapeJob state, all replaced by Procrastinate retry semantics):
- `_claim_job(...)`, `_release_job(...)`, `_finalize_job(...)`
- `_increment_attempt(...)`, `_reset_lock(...)`, `_record_terminal(...)`
- `_should_skip_already_running(...)`, any `lock_token`/`lock_expires_at`/`terminal_state`/`reconcile_count` reads or writes
- The Celery-side `create_job(...)` API endpoint helper (the API will call into the service differently — see Task 10)
- All `CircuitBreakerOpenError` and `ScrapeJobAlreadyRunningError` raise sites that exist solely to signal job-state conflicts (the circuit-breaker logic for *domain pushback* stays — it's pulled into `domain_policy.py` semantics already; only the ScrapeJob-level errors go)

Methods/functions to **keep and adapt**:
- `_fetch_pages(...)` (or whatever the core fetch loop is called) — change signature: take `domain: str, normalized_url: str, rules: ScrapeRules` instead of `job: ScrapeJob`
- All `_fetch_static`, `_fetch_stealth`, `_fetch_impersonate` tier methods (unchanged)
- Markdown conversion, link extraction, sitemap parsing — unchanged
- Stealth escalation tracking and domain backoff (live in `domain_policy.py` — unchanged)

Replace `job_id` parameters with `company_id: UUID` where the function persists results. When creating `ScrapePage` records: `ScrapePage(company_id=company_id, url=..., markdown_content=...)` (no more `job_id`).

Final result: `fetch_service.py` should be ~400 lines (down from 958), focused entirely on HTTP fetching and content extraction.

- [ ] **Step 5: Write test**

Create `tests/test_worker_scrape.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch


# Procrastinate wraps task functions in a Task object. The underlying coroutine
# is accessible via `.func`. We test that directly — it's the actual code that
# runs inside the worker.


@pytest.mark.asyncio
async def test_scrape_website_marks_scraped_on_success(async_session):
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.scrape import scrape_website

    upload = Upload(filename="test.csv", checksum="abc")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://example.com",
                      normalized_url="https://example.com", domain="example.com")
    async_session.add(company)
    await async_session.commit()

    with patch("app.services.scrape_service.ScrapeService.run", new_callable=AsyncMock):
        with patch("app.worker.tasks.analysis.run_analysis.defer_async",
                   new_callable=AsyncMock) as mock_defer:
            await scrape_website.func(company_id=str(company.id))
            mock_defer.assert_awaited_once_with(company_id=str(company.id))

    await async_session.refresh(company)
    assert company.pipeline_stage == CompanyStage.SCRAPED


@pytest.mark.asyncio
async def test_scrape_website_marks_scrape_failed_on_exception(async_session):
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.scrape import scrape_website

    upload = Upload(filename="test.csv", checksum="def")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://fail.com",
                      normalized_url="https://fail.com", domain="fail.com")
    async_session.add(company)
    await async_session.commit()

    with patch("app.services.scrape_service.ScrapeService.run",
               new_callable=AsyncMock, side_effect=RuntimeError("network error")):
        with pytest.raises(RuntimeError):
            await scrape_website.func(company_id=str(company.id))

    await async_session.refresh(company)
    assert company.pipeline_stage == CompanyStage.SCRAPE_FAILED
```

Note: `scrape_website.func` is the underlying coroutine. Procrastinate exposes this for direct invocation in tests, bypassing the deferral/retry machinery. If `.func` is not the attribute name in the installed Procrastinate version, check `dir(scrape_website)` — alternatives across versions: `.aio`, `.original_func`, or calling the task object directly as a callable.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_worker_scrape.py -v
```
Expected: both tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/worker/tasks/ app/services/scrape_service.py app/services/fetch_service.py tests/test_worker_scrape.py
git commit -m "feat: scrape_website Procrastinate task, remove ScrapeJob tracking"
```

---

## Task 5: Analysis Task + Service

**Files:**
- Create: `app/worker/tasks/analysis.py`
- Modify: `app/services/analysis_service.py`

- [ ] **Step 1: Create `app/worker/tasks/analysis.py`**

```python
from __future__ import annotations

import logging
from uuid import UUID

import procrastinate

from app.core.logging import log_event
from app.db.session import async_session_scope
from app.models.pipeline import Company, CompanyStage
from app.worker.app import app

logger = logging.getLogger(__name__)


@app.task(
    queue="analysis",
    retry=procrastinate.ExponentialRetry(max_attempts=3, wait_minimum=60, wait_multiplier=2),
)
async def run_analysis(*, company_id: str) -> None:
    from app.services.analysis_service import AnalysisService
    from app.worker.tasks.contacts import fetch_contacts  # local to avoid worker boot cycle

    cid = UUID(company_id)

    async with async_session_scope() as session:
        company = await session.get(Company, cid)
        if company is None:
            return
        company.pipeline_stage = CompanyStage.ANALYZING
        await session.commit()

    try:
        async with async_session_scope() as session:
            qualified = await AnalysisService().run(session=session, company_id=cid)
            # AnalysisService is responsible for setting the final stage
            # (QUALIFIED / DISQUALIFIED / UNKNOWN) and label_source='ai'
        if qualified:
            await fetch_contacts.defer_async(company_id=company_id)
        log_event(logger, "analysis_done", company_id=company_id, qualified=qualified)
    except Exception:
        # Service likely didn't reach the stage update — revert to SCRAPED so retry can re-run.
        async with async_session_scope() as session:
            company = await session.get(Company, cid)
            if company is not None and company.pipeline_stage == CompanyStage.ANALYZING:
                company.pipeline_stage = CompanyStage.SCRAPED
                await session.commit()
        raise
```

- [ ] **Step 2: Rewrite `app/services/analysis_service.py`**

New signature:
```python
async def run(self, *, session: AsyncSession, company_id: UUID) -> bool:
    """Run AI classification for one company. Returns True if qualified."""
```

Remove:
- `run_analysis_job()` entry point and all `AnalysisJob` CRUD
- `_fail_job()`, `_claim_job()`, `_release_job()` methods
- CAS lock acquisition

Keep:
- `extract_json_object()`, `normalize_predicted_label()`, `clamp_confidence()`
- All LLM prompt construction and response parsing
- `_record_ai_usage_event()` (keeps cost tracking)
- `ClassificationResult` creation

The service should:
1. Load `CrawlArtifact` for the company
2. Build prompt from scraped content
3. Call LLM API
4. Write `ClassificationResult`
5. Update `company.pipeline_stage` to `qualified`, `disqualified`, or `unknown`
6. Set `company.label_source = "ai"`
7. Return `True` if qualified

- [ ] **Step 3: Write test**

Create `tests/test_worker_analysis.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch


# In these tests, AnalysisService.run is mocked. The test asserts:
# (a) qualified result → fetch_contacts deferred
# (b) non-qualified result → fetch_contacts NOT deferred
# Note: the company's final pipeline_stage (QUALIFIED/DISQUALIFIED/UNKNOWN) is
# set inside AnalysisService.run, which is mocked here — so we don't assert on
# that stage in these task-level tests. AnalysisService stage transitions are
# tested separately in tests/test_analysis_service.py.


@pytest.mark.asyncio
async def test_run_analysis_qualified_enqueues_fetch_contacts(async_session):
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.analysis import run_analysis

    upload = Upload(filename="test.csv", checksum="aaa")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://good.com",
                      normalized_url="https://good.com", domain="good.com",
                      pipeline_stage=CompanyStage.SCRAPED)
    async_session.add(company)
    await async_session.commit()

    with patch("app.services.analysis_service.AnalysisService.run",
               new_callable=AsyncMock, return_value=True):
        with patch("app.worker.tasks.contacts.fetch_contacts.defer_async",
                   new_callable=AsyncMock) as mock_defer:
            await run_analysis.func(company_id=str(company.id))
            mock_defer.assert_awaited_once_with(company_id=str(company.id))


@pytest.mark.asyncio
async def test_run_analysis_disqualified_does_not_enqueue(async_session):
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.analysis import run_analysis

    upload = Upload(filename="test.csv", checksum="bbb")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://bad.com",
                      normalized_url="https://bad.com", domain="bad.com",
                      pipeline_stage=CompanyStage.SCRAPED)
    async_session.add(company)
    await async_session.commit()

    with patch("app.services.analysis_service.AnalysisService.run",
               new_callable=AsyncMock, return_value=False):
        with patch("app.worker.tasks.contacts.fetch_contacts.defer_async",
                   new_callable=AsyncMock) as mock_defer:
            await run_analysis.func(company_id=str(company.id))
            mock_defer.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_analysis_reverts_stage_on_exception(async_session):
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.analysis import run_analysis

    upload = Upload(filename="test.csv", checksum="ccc")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://err.com",
                      normalized_url="https://err.com", domain="err.com",
                      pipeline_stage=CompanyStage.SCRAPED)
    async_session.add(company)
    await async_session.commit()

    with patch("app.services.analysis_service.AnalysisService.run",
               new_callable=AsyncMock, side_effect=RuntimeError("LLM error")):
        with pytest.raises(RuntimeError):
            await run_analysis.func(company_id=str(company.id))

    await async_session.refresh(company)
    assert company.pipeline_stage == CompanyStage.SCRAPED  # reverted from ANALYZING
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_worker_analysis.py -v
```
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/worker/tasks/analysis.py app/services/analysis_service.py tests/test_worker_analysis.py
git commit -m "feat: run_analysis Procrastinate task, remove AnalysisJob/Run/CAS tracking"
```

---

## Task 6: Contacts Task + Service

**Files:**
- Create: `app/worker/tasks/contacts.py`
- Modify: `app/services/contact_service.py` (898 → ~200 lines)
- Delete: `app/services/contact_queue_service.py`, `app/services/contact_runtime_service.py`

- [ ] **Step 1: Create `app/worker/tasks/contacts.py`**

```python
from __future__ import annotations

import logging
from uuid import UUID

import procrastinate

from app.core.logging import log_event
from app.db.session import async_session_scope
from app.models.pipeline import Company, CompanyStage
from app.worker.app import app

logger = logging.getLogger(__name__)


@app.task(
    queue="contacts",
    retry=procrastinate.ExponentialRetry(max_attempts=3, wait_minimum=120, wait_multiplier=2),
)
async def fetch_contacts(*, company_id: str) -> None:
    from app.services.contact_service import ContactService

    cid = UUID(company_id)

    async with async_session_scope() as session:
        company = await session.get(Company, cid)
        if company is None:
            return
        company.pipeline_stage = CompanyStage.CONTACTS_FETCHING
        await session.commit()

    try:
        async with async_session_scope() as session:
            await ContactService().run(session=session, company_id=cid)
            # ContactService sets CONTACTS_READY on success
        log_event(logger, "contacts_fetched", company_id=company_id)
    except Exception:
        async with async_session_scope() as session:
            company = await session.get(Company, cid)
            if company is not None and company.pipeline_stage == CompanyStage.CONTACTS_FETCHING:
                # Revert to whichever label preceded — fall back to QUALIFIED
                # if no record (manual override may have set DISQUALIFIED/UNKNOWN
                # then triggered fetch).
                company.pipeline_stage = (
                    CompanyStage.QUALIFIED if company.label_source != "manual"
                    else CompanyStage.QUALIFIED  # manual overrides also revert here
                )
                await session.commit()
        raise
```

- [ ] **Step 2: Rewrite `app/services/contact_service.py`**

New public interface — one method:
```python
async def run(self, *, session: AsyncSession, company_id: UUID) -> None:
    """Fetch contacts for a company from all configured providers (Snov + Apollo)."""
```

Remove entirely:
- `run_contact_fetch()`, `run_apollo_fetch()`, `run_snov_attempt()`, `run_apollo_attempt()`
- `_run_contact_job()`, `_run_provider_attempt()`
- `_claim_contact_job()`, `_release_contact_job()`, `_finalize_contact_job()`
- `_ensure_provider_attempts()`, `_claim_provider_attempt()`
- `_dispatch_contact_task()`, `_dispatch_provider_attempt()`
- `_mark_job_failure()`

Keep and async-ify:
- `_fetch_snov_contacts()` → calls `snov_client` directly
- `_fetch_apollo_contacts()` → calls `apollo_client` directly
- `_persist_discovered_contacts()` → writes to `DiscoveredContact`

The new `run()`:
1. Try Snov: `contacts = await self._fetch_snov_contacts(domain=company.domain)`
2. Try Apollo if Snov empty: `contacts = await self._fetch_apollo_contacts(domain=company.domain)`
3. Persist results: `await self._persist_discovered_contacts(session, company_id, contacts)`
4. Set `company.pipeline_stage = CompanyStage.CONTACTS_READY`

- [ ] **Step 3: Delete `contact_queue_service.py` and `contact_runtime_service.py`**

```bash
rm app/services/contact_queue_service.py
rm app/services/contact_runtime_service.py
```

- [ ] **Step 4: Write test**

Create `tests/test_worker_contacts.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_fetch_contacts_marks_contacts_fetching_then_calls_service(async_session):
    """ContactService is responsible for the final CONTACTS_READY transition;
    the task only sets CONTACTS_FETCHING and reverts on error."""
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.contacts import fetch_contacts

    upload = Upload(filename="test.csv", checksum="ccc")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://co.com",
                      normalized_url="https://co.com", domain="co.com",
                      pipeline_stage=CompanyStage.QUALIFIED)
    async_session.add(company)
    await async_session.commit()

    with patch("app.services.contact_service.ContactService.run",
               new_callable=AsyncMock) as mock_run:
        await fetch_contacts.func(company_id=str(company.id))
        mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_contacts_reverts_to_qualified_on_error(async_session):
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.contacts import fetch_contacts

    upload = Upload(filename="test.csv", checksum="ddd")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://fail2.com",
                      normalized_url="https://fail2.com", domain="fail2.com",
                      pipeline_stage=CompanyStage.QUALIFIED)
    async_session.add(company)
    await async_session.commit()

    with patch("app.services.contact_service.ContactService.run",
               new_callable=AsyncMock, side_effect=RuntimeError("api error")):
        with pytest.raises(RuntimeError):
            await fetch_contacts.func(company_id=str(company.id))

    await async_session.refresh(company)
    assert company.pipeline_stage == CompanyStage.QUALIFIED
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_worker_contacts.py -v
```

- [ ] **Step 6: Commit**

```bash
git add app/worker/tasks/contacts.py app/services/contact_service.py tests/test_worker_contacts.py
git rm app/services/contact_queue_service.py app/services/contact_runtime_service.py
git commit -m "feat: fetch_contacts task, simplify ContactService, remove CAS/batch/dispatch"
```

---

## Task 7: Reveal Task + Service

**Files:**
- Create: `app/worker/tasks/reveal.py`
- Modify: `app/services/contact_reveal_service.py` (946 → ~200 lines)
- Delete: `app/services/contact_reveal_queue_service.py`

### Reveal data flow (read first)

Before writing the task: in this codebase, `DiscoveredContact` is the raw provider data (Snov/Apollo discovered people, including `provider_native_person_id` used to call reveal endpoints). `ProspectContact` is the user-facing prospect, with a `title_match: bool` flag set by title-rule matching. The current reveal flow:

1. After `fetch_contacts`, `DiscoveredContact` rows exist for a company.
2. User defines title rules → `rematch_discovered_contacts` (in `title_match_service.py`) creates/updates `ProspectContact` rows for matching discovered contacts. Each `ProspectContact` is associated 1:1 with a `DiscoveredContact` (look at the existing schema for the FK or matching key — likely `(company_id, name, title)` or a direct FK).
3. User triggers reveal → for each matching `ProspectContact`, enqueue `reveal_email(contact_id=str(prospect_contact.id))`.
4. `RevealService.run(session, contact_id)` loads the `ProspectContact`, finds its corresponding `DiscoveredContact` (for the provider person ID), calls Snov/Apollo, and writes the resulting email into `ProspectContactEmail`.

**The task argument is `ProspectContact.id`.** All `pipeline_stage` updates in this task target `ProspectContact.pipeline_stage` (the `ContactStage` enum).

- [ ] **Step 1: Create `app/worker/tasks/reveal.py`**

```python
from __future__ import annotations

import logging
from uuid import UUID

import procrastinate

from app.core.logging import log_event
from app.db.session import async_session_scope
from app.models.pipeline import ContactStage, ProspectContact
from app.worker.app import app

logger = logging.getLogger(__name__)


@app.task(
    queue="reveal",
    retry=procrastinate.ExponentialRetry(max_attempts=3, wait_minimum=120, wait_multiplier=2),
)
async def reveal_email(*, contact_id: str) -> None:
    """Reveal email for one ProspectContact. contact_id refers to ProspectContact.id."""
    from app.services.contact_reveal_service import RevealService
    from app.worker.tasks.verify import verify_email

    cid = UUID(contact_id)

    async with async_session_scope() as session:
        contact = await session.get(ProspectContact, cid)
        if contact is None:
            return
        contact.pipeline_stage = ContactStage.REVEALING
        await session.commit()

    try:
        async with async_session_scope() as session:
            await RevealService().run(session=session, contact_id=cid)
            # RevealService sets pipeline_stage = REVEALED on success
        await verify_email.defer_async(contact_id=contact_id)
        log_event(logger, "email_revealed", contact_id=contact_id)
    except Exception:
        async with async_session_scope() as session:
            contact = await session.get(ProspectContact, cid)
            if contact is not None:
                contact.pipeline_stage = ContactStage.REVEAL_FAILED
                await session.commit()
        raise
```

- [ ] **Step 2: Rewrite `app/services/contact_reveal_service.py`**

Rename the class from `ContactRevealService` → `RevealService`. New public interface:
```python
class RevealService:
    async def run(self, *, session: AsyncSession, contact_id: UUID) -> None:
        """Reveal email for one ProspectContact using Snov or Apollo."""
```

Remove entirely:
- `run_contact_reveal()`, `run_contact_reveal_apollo_attempt()`, `run_contact_reveal_snov_attempt()`
- `_run_reveal_attempt()`, `_claim_reveal_job()`, `_claim_reveal_attempt()`
- `_ensure_reveal_attempts()`, `_release_reveal_job()`, `_finalize_reveal_job()`
- `_refresh_reveal_batch_state()`
- All `ContactRevealJob`, `ContactRevealAttempt`, `ContactRevealBatch` references

Keep and async-ify:
- `_reveal_with_apollo(...)` → calls `apollo_client` directly with `provider_native_person_id`
- `_reveal_with_snov(...)` → calls `snov_client` directly
- `_persist_revealed_contact(...)` → writes email to `ProspectContactEmail` (existing logic, change session arg type to `AsyncSession`)
- `_first_member_job_id`, `_find_existing_contact`, `_upsert_contact_email` (helpers — adapt to async session)

The new `run()`:
1. Load `ProspectContact` by `contact_id`. Return early if missing or already has a verified email.
2. Locate the corresponding `DiscoveredContact` for this prospect — use whatever join the current `_load_reveal_members` uses (likely `(company_id + name + title)` or a `discovered_contact_id` FK on `ProspectContact`). This gives access to `provider_native_person_id` for Snov/Apollo.
3. Try Snov: `result = await self._reveal_with_snov(discovered=discovered_contact)`. If no email returned, try Apollo: `result = await self._reveal_with_apollo(discovered=discovered_contact)`.
4. If at least one provider returned an email, call `await self._persist_revealed_contact(session=session, contact=prospect, result=result)` and set `prospect.pipeline_stage = ContactStage.REVEALED`.
5. If both providers returned no email, set `prospect.pipeline_stage = ContactStage.REVEAL_FAILED` and return without raising (this is "no result", not an error).
6. Raise on transport-level errors (network, 5xx) so Procrastinate retries.

- [ ] **Step 3: Delete `contact_reveal_queue_service.py`**

```bash
rm app/services/contact_reveal_queue_service.py
```

- [ ] **Step 4: Write test**

Create `tests/test_worker_reveal.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_reveal_email_calls_service_and_enqueues_verify(async_session):
    from app.models.pipeline import ProspectContact, ContactStage, Company, Upload
    from app.worker.tasks.reveal import reveal_email

    upload = Upload(filename="t.csv", checksum="eee")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://x.com",
                      normalized_url="https://x.com", domain="x.com")
    async_session.add(company)
    await async_session.commit()

    contact = ProspectContact(company_id=company.id, full_name="Jane Doe",
                              pipeline_stage=ContactStage.FETCHED)
    async_session.add(contact)
    await async_session.commit()

    with patch("app.services.contact_reveal_service.RevealService.run",
               new_callable=AsyncMock):
        with patch("app.worker.tasks.verify.verify_email.defer_async",
                   new_callable=AsyncMock) as mock_defer:
            await reveal_email.func(contact_id=str(contact.id))
            mock_defer.assert_awaited_once_with(contact_id=str(contact.id))


@pytest.mark.asyncio
async def test_reveal_email_marks_reveal_failed_on_exception(async_session):
    from app.models.pipeline import ProspectContact, ContactStage, Company, Upload
    from app.worker.tasks.reveal import reveal_email

    upload = Upload(filename="t.csv", checksum="fff")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://x.com",
                      normalized_url="https://x.com", domain="x.com")
    async_session.add(company)
    await async_session.commit()
    contact = ProspectContact(company_id=company.id, full_name="John Doe",
                              pipeline_stage=ContactStage.FETCHED)
    async_session.add(contact)
    await async_session.commit()

    with patch("app.services.contact_reveal_service.RevealService.run",
               new_callable=AsyncMock, side_effect=RuntimeError("provider error")):
        with pytest.raises(RuntimeError):
            await reveal_email.func(contact_id=str(contact.id))

    await async_session.refresh(contact)
    assert contact.pipeline_stage == ContactStage.REVEAL_FAILED
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_worker_reveal.py -v
```

- [ ] **Step 6: Commit**

```bash
git add app/worker/tasks/reveal.py app/services/contact_reveal_service.py tests/test_worker_reveal.py
git rm app/services/contact_reveal_queue_service.py
git commit -m "feat: reveal_email task, simplify RevealService, remove batch/attempt/CAS"
```

---

## Task 8: Verify Task + Service

**Files:**
- Create: `app/worker/tasks/verify.py`
- Modify: `app/services/contact_verify_service.py` (241 → ~150 lines)

- [ ] **Step 1: Create `app/worker/tasks/verify.py`**

```python
from __future__ import annotations

import logging
from uuid import UUID

import procrastinate

from app.core.logging import log_event
from app.db.session import async_session_scope
from app.models.pipeline import ContactStage, ProspectContact
from app.worker.app import app

logger = logging.getLogger(__name__)


@app.task(
    queue="verify",
    retry=procrastinate.ExponentialRetry(max_attempts=3, wait_minimum=60, wait_multiplier=2),
)
async def verify_email(*, contact_id: str) -> None:
    from app.services.contact_verify_service import VerifyService

    cid = UUID(contact_id)

    async with async_session_scope() as session:
        contact = await session.get(ProspectContact, cid)
        if contact is None:
            return
        contact.pipeline_stage = ContactStage.VERIFYING
        await session.commit()

    try:
        async with async_session_scope() as session:
            await VerifyService().run(session=session, contact_id=cid)
            # VerifyService sets pipeline_stage = VERIFIED or CAMPAIGN_READY
        log_event(logger, "email_verified", contact_id=contact_id)
    except Exception:
        async with async_session_scope() as session:
            contact = await session.get(ProspectContact, cid)
            if contact is not None and contact.pipeline_stage == ContactStage.VERIFYING:
                contact.pipeline_stage = ContactStage.REVEALED
                await session.commit()
        raise
```

- [ ] **Step 2: Rewrite `app/services/contact_verify_service.py`**

Rename the class from `ContactVerifyService` → `VerifyService`. New public interface:
```python
class VerifyService:
    async def run(self, *, session: AsyncSession, contact_id: UUID) -> None:
        """Verify email for one ProspectContact via ZeroBounce."""
```

Remove: `run_verify_job()`, `_complete_job()`, `_fail_job()`, all `ContactVerifyJob` CRUD.

Keep: `normalize_zerobounce_status()`, `is_contact_verification_eligible()`, ZeroBounce API call logic (adapt to async HTTP if not already).

The new `run()`:
1. Load `ProspectContact` and its `ProspectContactEmail` rows.
2. If no email rows exist → set `pipeline_stage = ContactStage.REVEALED` (rolled back from VERIFYING) and return.
3. For each `ProspectContactEmail` not yet verified, call ZeroBounce and update `verification_status`.
4. If at least one email comes back with a valid status (`valid` per `normalize_zerobounce_status`) → `contact.pipeline_stage = ContactStage.CAMPAIGN_READY`.
5. Otherwise → `contact.pipeline_stage = ContactStage.VERIFIED` (verified but no valid email).

- [ ] **Step 3: Write test**

Create `tests/test_worker_verify.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_verify_email_calls_service(async_session):
    """VerifyService is responsible for the final stage transition."""
    from app.models.pipeline import ProspectContact, ContactStage, Company, Upload
    from app.worker.tasks.verify import verify_email

    upload = Upload(filename="t.csv", checksum="ggg")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://y.com",
                      normalized_url="https://y.com", domain="y.com")
    async_session.add(company)
    await async_session.commit()
    contact = ProspectContact(company_id=company.id, full_name="Bob Smith",
                              pipeline_stage=ContactStage.REVEALED)
    async_session.add(contact)
    await async_session.commit()

    with patch("app.services.contact_verify_service.VerifyService.run",
               new_callable=AsyncMock) as mock_run:
        await verify_email.func(contact_id=str(contact.id))
        mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_email_reverts_to_revealed_on_exception(async_session):
    from app.models.pipeline import ProspectContact, ContactStage, Company, Upload
    from app.worker.tasks.verify import verify_email

    upload = Upload(filename="t.csv", checksum="hhh")
    async_session.add(upload)
    await async_session.commit()
    company = Company(upload_id=upload.id, raw_url="https://y.com",
                      normalized_url="https://y.com", domain="y.com")
    async_session.add(company)
    await async_session.commit()
    contact = ProspectContact(company_id=company.id, full_name="Eve",
                              pipeline_stage=ContactStage.REVEALED)
    async_session.add(contact)
    await async_session.commit()

    with patch("app.services.contact_verify_service.VerifyService.run",
               new_callable=AsyncMock, side_effect=RuntimeError("zb timeout")):
        with pytest.raises(RuntimeError):
            await verify_email.func(contact_id=str(contact.id))

    await async_session.refresh(contact)
    assert contact.pipeline_stage == ContactStage.REVEALED
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_worker_verify.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/worker/tasks/verify.py app/services/contact_verify_service.py tests/test_worker_verify.py
git commit -m "feat: verify_email task, simplify VerifyService, remove ContactVerifyJob"
```

---

## Task 9: Periodic Tasks (Reconciliation)

**Files:**
- Create: `app/worker/tasks/periodic.py`
- Delete: `app/tasks/beat.py` (after this task)

- [ ] **Step 1: Create `app/worker/tasks/periodic.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import col, select

from app.core.logging import log_event
from app.db.session import async_session_scope
from app.models.pipeline import AiUsageEvent, Company, CompanyStage, ContactStage, ProspectContact
from app.worker.app import app

logger = logging.getLogger(__name__)

_STAGE_TIMEOUT_MINUTES = 35


# Procrastinate periodic tasks must accept a `timestamp` int argument.
# The decorator schedules them via cron; the worker passes the firing time.

@app.periodic(cron="*/10 * * * *")
@app.task(queue="periodic")
async def reconcile_stuck_jobs(timestamp: int) -> None:
    """Reset companies/contacts stuck in transitional states for > 35 min."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STAGE_TIMEOUT_MINUTES)

    company_revert = {
        CompanyStage.SCRAPING:          CompanyStage.UPLOADED,
        CompanyStage.ANALYZING:         CompanyStage.SCRAPED,
        CompanyStage.CONTACTS_FETCHING: CompanyStage.QUALIFIED,
    }
    contact_revert = {
        ContactStage.REVEALING: ContactStage.FETCHED,
        ContactStage.VERIFYING: ContactStage.REVEALED,
    }

    reset_company = 0
    reset_contact = 0

    async with async_session_scope() as session:
        for stuck_stage, revert_stage in company_revert.items():
            result = await session.exec(
                select(Company).where(
                    col(Company.pipeline_stage) == stuck_stage,
                    col(Company.updated_at) < cutoff,
                )
            )
            for company in result.all():
                company.pipeline_stage = revert_stage
                session.add(company)
                reset_company += 1

        for stuck_stage, revert_stage in contact_revert.items():
            result = await session.exec(
                select(ProspectContact).where(
                    col(ProspectContact.pipeline_stage) == stuck_stage,
                    col(ProspectContact.updated_at) < cutoff,
                )
            )
            for contact in result.all():
                contact.pipeline_stage = revert_stage
                session.add(contact)
                reset_contact += 1

        await session.commit()

    log_event(
        logger, "reconciler_done",
        reset_company=reset_company, reset_contact=reset_contact,
    )


@app.periodic(cron="*/15 * * * *")
@app.task(queue="periodic")
async def reconcile_openrouter_costs(timestamp: int) -> None:
    """Mark billable OpenRouter events as reconciled."""
    async with async_session_scope() as session:
        result = await session.exec(
            select(AiUsageEvent).where(
                col(AiUsageEvent.provider) == "openrouter",
                col(AiUsageEvent.billed_cost_usd).is_not(None),
                col(AiUsageEvent.reconciliation_status) != "reconciled",
            )
        )
        rows = list(result.all())
        for row in rows:
            row.reconciliation_status = "reconciled"
            session.add(row)
        await session.commit()

    log_event(logger, "openrouter_cost_reconciliation_done", updated=len(rows))
```

Note: when adding `--queues` to the worker-pipeline command in Task 12, include `periodic` so reconciliation tasks get picked up.

- [ ] **Step 2: Write test**

Create `tests/test_worker_periodic.py`:
```python
import pytest
from datetime import datetime, timedelta, timezone


@pytest.mark.asyncio
async def test_reconcile_stuck_jobs_resets_scraping(async_session):
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.periodic import reconcile_stuck_jobs

    upload = Upload(filename="t.csv", checksum="iii")
    async_session.add(upload)
    await async_session.commit()
    old_time = datetime.now(timezone.utc) - timedelta(minutes=40)
    company = Company(
        upload_id=upload.id,
        raw_url="https://stuck.com",
        normalized_url="https://stuck.com",
        domain="stuck.com",
        pipeline_stage=CompanyStage.SCRAPING,
        updated_at=old_time,
    )
    async_session.add(company)
    await async_session.commit()

    await reconcile_stuck_jobs.func(timestamp=0)

    await async_session.refresh(company)
    assert company.pipeline_stage == CompanyStage.UPLOADED


@pytest.mark.asyncio
async def test_reconcile_stuck_jobs_does_not_reset_recent(async_session):
    """Companies updated within the timeout window must not be reset."""
    from app.models.pipeline import Company, CompanyStage, Upload
    from app.worker.tasks.periodic import reconcile_stuck_jobs

    upload = Upload(filename="t.csv", checksum="jjj")
    async_session.add(upload)
    await async_session.commit()
    company = Company(
        upload_id=upload.id,
        raw_url="https://recent.com",
        normalized_url="https://recent.com",
        domain="recent.com",
        pipeline_stage=CompanyStage.SCRAPING,
    )
    async_session.add(company)
    await async_session.commit()

    await reconcile_stuck_jobs.func(timestamp=0)

    await async_session.refresh(company)
    assert company.pipeline_stage == CompanyStage.SCRAPING
```

- [ ] **Step 3: Run test**

```bash
uv run pytest tests/test_worker_periodic.py -v
```
Expected: passes.

- [ ] **Step 4: Delete old beat task and Celery task files**

```bash
git rm app/tasks/beat.py app/tasks/scrape.py app/tasks/analysis.py app/tasks/contacts.py app/tasks/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add app/worker/tasks/periodic.py tests/test_worker_periodic.py
git commit -m "feat: periodic reconciliation tasks in Procrastinate, delete app/tasks/"
```

---

## Task 10: API Routes Cleanup

**Files:**
- Modify: `app/api/routes/companies.py` — add manual label override + contact fetch trigger
- Modify: `app/api/routes/contacts.py` — replace Celery dispatch with `defer_async`
- Modify: `app/api/routes/scrape_actions.py` — replace Celery dispatch with `defer_async`
- Modify: `app/api/routes/queue_admin.py` — rewrite to query `procrastinate_jobs`
- Modify: `app/api/routes/queue_history.py` — rewrite to query `procrastinate_jobs`
- Delete: `app/api/routes/runs.py`, `app/api/routes/pipeline_runs.py`, `app/api/routes/scrape_jobs.py`
- Modify: `app/main.py` — remove deleted router registrations

- [ ] **Step 1: Add manual override endpoint to `app/api/routes/companies.py`**

Add these imports at the top of the file:
```python
from typing import Literal

from pydantic import BaseModel

from app.models.pipeline import CompanyStage
```

Add this endpoint:
```python
class ManualLabelRequest(BaseModel):
    label: Literal["qualified", "disqualified", "unknown"]
    enqueue_contacts: bool = False


class ManualLabelResponse(BaseModel):
    company_id: UUID
    pipeline_stage: str
    label_source: str
    contacts_enqueued: bool


@router.post("/companies/{company_id}/label", response_model=ManualLabelResponse)
async def manually_label_company(
    company_id: UUID,
    payload: ManualLabelRequest,
    session: Session = Depends(get_session),
) -> ManualLabelResponse:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    company.pipeline_stage = CompanyStage(payload.label)
    company.label_source = "manual"
    session.add(company)
    session.commit()
    session.refresh(company)

    contacts_enqueued = False
    if payload.enqueue_contacts and payload.label == "qualified":
        from app.worker.tasks.contacts import fetch_contacts
        await fetch_contacts.defer_async(company_id=str(company_id))
        contacts_enqueued = True

    return ManualLabelResponse(
        company_id=company_id,
        pipeline_stage=company.pipeline_stage,
        label_source=company.label_source,
        contacts_enqueued=contacts_enqueued,
    )
```

Notes:
- Route is `async def` because it conditionally calls `defer_async`.
- Contact fetch is only enqueued when the manual label is `qualified` — labelling something `disqualified` or `unknown` doesn't trigger fetch even if `enqueue_contacts=true`.

- [ ] **Step 2: Update contact fetch dispatch in `app/api/routes/contacts.py`**

Find the bulk contact fetch endpoint (currently uses `ContactQueueService`). Replace the dispatch call:
```python
# Remove:
from app.services.contact_queue_service import ContactQueueService
result = ContactQueueService().enqueue_jobs(session=session, companies=companies, ...)

# Replace with:
from app.worker.tasks.contacts import fetch_contacts
for company in companies:
    await fetch_contacts.defer_async(company_id=str(company.id))
```

Remove all `idempotency_service` imports and usage from this file.

Change the endpoint functions that call `defer_async` to `async def`.

- [ ] **Step 3: Update reveal dispatch in `app/api/routes/contacts.py`**

Find the reveal trigger endpoint (currently dispatches to `contacts_reveal_orchestrator`). Replace:
```python
from app.worker.tasks.reveal import reveal_email
for contact in contacts_to_reveal:
    await reveal_email.defer_async(contact_id=str(contact.id))
```

- [ ] **Step 4: Update verify dispatch in `app/api/routes/contacts.py`**

Find the verify trigger endpoint. Replace Celery dispatch with:
```python
from app.worker.tasks.verify import verify_email
for contact in contacts_to_verify:
    await verify_email.defer_async(contact_id=str(contact.id))
```

- [ ] **Step 5: Update scrape dispatch in `app/api/routes/scrape_actions.py`**

Find `_enqueue_scrapes_for_companies` (used by scrape_actions and pipeline_runs). Replace Celery:
```python
from app.worker.tasks.scrape import scrape_website

async def _enqueue_scrapes_for_companies(companies: list[Company]) -> int:
    for company in companies:
        await scrape_website.defer_async(company_id=str(company.id))
    return len(companies)
```

Change endpoint functions that call this to `async def`.

- [ ] **Step 6: Rewrite `app/api/routes/queue_admin.py`**

Replace all job-table queries with `procrastinate_jobs` queries. The new file:
```python
"""Queue administration endpoints backed by procrastinate_jobs."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from app.db.session import get_session

router = APIRouter(prefix="/v1", tags=["queue-admin"])


class QueueSummary(BaseModel):
    queue: str
    todo: int
    doing: int
    succeeded: int
    failed: int


class PipelineSummaryResponse(BaseModel):
    queues: list[QueueSummary]


@router.get("/queue/summary", response_model=PipelineSummaryResponse)
def get_queue_summary(session: Session = Depends(get_session)) -> PipelineSummaryResponse:
    rows = session.exec(text("""
        SELECT
            queue_name,
            COUNT(*) FILTER (WHERE status = 'todo') AS todo,
            COUNT(*) FILTER (WHERE status = 'doing') AS doing,
            COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
        FROM procrastinate_jobs
        GROUP BY queue_name
        ORDER BY queue_name
    """)).all()

    return PipelineSummaryResponse(queues=[
        QueueSummary(queue=r.queue_name, todo=r.todo, doing=r.doing,
                     succeeded=r.succeeded, failed=r.failed)
        for r in rows
    ])


class CancelJobsResult(BaseModel):
    cancelled: int


@router.post("/queue/cancel-pending", response_model=CancelJobsResult)
def cancel_pending_jobs(
    queue: str | None = None,
    session: Session = Depends(get_session),
) -> CancelJobsResult:
    if queue:
        result = session.exec(text("""
            UPDATE procrastinate_jobs
            SET status = 'failed', attempts = max_attempts
            WHERE status = 'todo' AND queue_name = :queue
        """), {"queue": queue})
    else:
        result = session.exec(text("""
            UPDATE procrastinate_jobs
            SET status = 'failed', attempts = max_attempts
            WHERE status = 'todo'
        """))
    session.commit()
    return CancelJobsResult(cancelled=result.rowcount or 0)
```

- [ ] **Step 7: Rewrite `app/api/routes/queue_history.py`**

Replace all per-stage table queries with a single `procrastinate_jobs` query:
```python
"""Unified queue history via procrastinate_jobs."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from app.db.session import get_session

router = APIRouter(prefix="/v1", tags=["queue-history"])


class JobHistoryItem(BaseModel):
    id: int
    queue: str
    task_name: str
    status: str
    attempts: int
    scheduled_at: datetime | None
    started_at: datetime | None
    args: dict


class JobHistoryResponse(BaseModel):
    items: list[JobHistoryItem]
    total: int


@router.get("/queue/history", response_model=JobHistoryResponse)
def get_job_history(
    queue: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    session: Session = Depends(get_session),
) -> JobHistoryResponse:
    filters = []
    params: dict = {"limit": limit, "offset": offset}
    if queue:
        filters.append("queue_name = :queue")
        params["queue"] = queue
    if status:
        filters.append("status = :status")
        params["status"] = status

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    rows = session.exec(text(f"""
        SELECT id, queue_name, task_name, status, attempts,
               scheduled_at, started_at, args
        FROM procrastinate_jobs
        {where}
        ORDER BY id DESC
        LIMIT :limit OFFSET :offset
    """), params).all()

    total = session.exec(text(f"""
        SELECT COUNT(*) FROM procrastinate_jobs {where}
    """), params).scalar() or 0

    return JobHistoryResponse(
        items=[
            JobHistoryItem(
                id=r.id, queue=r.queue_name, task_name=r.task_name,
                status=r.status, attempts=r.attempts,
                scheduled_at=r.scheduled_at, started_at=r.started_at,
                args=r.args,
            )
            for r in rows
        ],
        total=total,
    )
```

- [ ] **Step 8: Delete deprecated route files**

```bash
git rm app/api/routes/runs.py
git rm app/api/routes/pipeline_runs.py
git rm app/api/routes/scrape_jobs.py
```

- [ ] **Step 9: Update `app/main.py` router registrations**

Remove these lines:
```python
from app.api.routes.runs import router as runs_router
from app.api.routes.pipeline_runs import router as pipeline_runs_router
from app.api.routes.scrape_jobs import router as scrape_jobs_router
...
app.include_router(runs_router)
app.include_router(pipeline_runs_router)
app.include_router(scrape_jobs_router)
```

- [ ] **Step 10: Run the full test suite**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -20
```
Expected: tests that referenced deleted models/services will fail — fix import errors one by one. Tests for business logic (title matching, snov client, etc.) should pass.

- [ ] **Step 11: Commit**

```bash
git add app/api/routes/ app/main.py
git commit -m "feat: update API routes — procrastinate dispatch, delete runs/pipeline_runs/scrape_jobs routes"
```

---

## Task 11: Delete Remaining Dead Code & Services

**Files:**
- Delete: `app/celery_app.py`, `app/services/celery_app.py` (if exists)
- Delete: `app/services/idempotency_service.py`, `app/services/redis_client.py`
- Delete: `app/services/pipeline_run_orchestrator.py`, `app/services/pipeline_service.py`, `app/services/run_service.py`

- [ ] **Step 1: Verify no remaining imports**

```bash
grep -r "celery_app\|idempotency_service\|redis_client\|pipeline_run_orchestrator\|pipeline_service\|run_service\|contact_queue_service\|contact_reveal_queue_service\|contact_runtime_service" app/ --include="*.py" -l
```
Expected: empty output (no files import the deleted modules).

If any files still import them, fix those imports first before deleting.

- [ ] **Step 2: Delete files**

```bash
git rm app/celery_app.py
git rm app/services/idempotency_service.py
git rm app/services/redis_client.py
git rm app/services/pipeline_run_orchestrator.py
git rm app/services/pipeline_service.py
git rm app/services/run_service.py
```

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -q 2>&1 | tail -30
```
Expected: all remaining tests pass. Fix any stray import errors.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete celery, idempotency, redis, pipeline orchestration — all replaced by procrastinate"
```

---

## Task 12: Docker — 7 Containers, Playwright, No Redis

**Files:**
- Create: `Dockerfile.worker-scrape`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.local.yml`

- [ ] **Step 1: Create `Dockerfile.worker-scrape`**

```dockerfile
FROM python:3.12-slim

# Install system deps for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libx11-6 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

# Install Playwright Chromium browser
RUN uv run playwright install chromium

COPY . .

CMD ["uv", "run", "procrastinate", "--app", "app.worker.app.app", "worker",
     "--queues", "scrape",
     "--concurrency", "6"]
```

### Note on per-queue concurrency

Procrastinate's `--concurrency` flag is a global slot count for a worker process — it does not enforce per-queue limits the way Celery's separate worker pools do. With one worker process listening to all four pipeline queues at `--concurrency 12`, on a busy day you might end up with 12 verify jobs running simultaneously and zero contact jobs.

For this design (rate-limited external APIs per queue), the cleanest answer is **one worker container per queue**. This keeps strict per-queue concurrency. It costs ~50–100MB extra RAM per container — well within the 12GB budget.

This means **5 worker containers total**, not 2. Updated topology:

```
postgres
api
worker-scrape       (concurrency 6,  queue: scrape)
worker-analysis     (concurrency 4,  queue: analysis)
worker-contacts     (concurrency 4,  queue: contacts)
worker-reveal       (concurrency 3,  queue: reveal)
worker-verify       (concurrency 2,  queues: verify, periodic)
```

Total: 7 containers. Still much simpler than the current 10. `worker-verify` also runs the periodic queue (reconciliation) since it's the lowest-traffic worker.

- [ ] **Step 2: Rewrite `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: prospect
      POSTGRES_USER: prospect
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U prospect"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: .
    command: ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    environment:
      DATABASE_URL: postgresql+psycopg2://prospect:${POSTGRES_PASSWORD}@postgres:5432/prospect
      PS_SETTINGS_ENCRYPTION_KEY: ${PS_SETTINGS_ENCRYPTION_KEY}
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8000:8000"

  worker-scrape:
    build:
      context: .
      dockerfile: Dockerfile.worker-scrape
    environment: &worker_env
      DATABASE_URL: postgresql+psycopg2://prospect:${POSTGRES_PASSWORD}@postgres:5432/prospect
      PS_SETTINGS_ENCRYPTION_KEY: ${PS_SETTINGS_ENCRYPTION_KEY}
    depends_on:
      postgres:
        condition: service_healthy

  worker-analysis:
    build: .
    command: ["uv", "run", "procrastinate", "--app", "app.worker.app.app", "worker",
              "--queues", "analysis", "--concurrency", "4"]
    environment: *worker_env
    depends_on:
      postgres:
        condition: service_healthy

  worker-contacts:
    build: .
    command: ["uv", "run", "procrastinate", "--app", "app.worker.app.app", "worker",
              "--queues", "contacts", "--concurrency", "4"]
    environment: *worker_env
    depends_on:
      postgres:
        condition: service_healthy

  worker-reveal:
    build: .
    command: ["uv", "run", "procrastinate", "--app", "app.worker.app.app", "worker",
              "--queues", "reveal", "--concurrency", "3"]
    environment: *worker_env
    depends_on:
      postgres:
        condition: service_healthy

  worker-verify:
    build: .
    command: ["uv", "run", "procrastinate", "--app", "app.worker.app.app", "worker",
              "--queues", "verify,periodic", "--concurrency", "2"]
    environment: *worker_env
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

The `DATABASE_URL` uses the SQLAlchemy `+psycopg2` prefix everywhere because the API uses sync SQLAlchemy with psycopg2-style URLs. The `_async_url` and `procrastinate_dsn` helpers (Tasks 1 Steps 4 and 6) translate it to async/raw forms as needed.

- [ ] **Step 3: Remove Redis env var references from `.env` and `.env.example`**

```bash
grep -r "REDIS_URL\|PS_REDIS" . --include="*.env*" --include="*.example"
```
Remove any found occurrences.

- [ ] **Step 4: Build and verify**

```bash
docker compose build
docker compose up -d postgres
docker compose run --rm api uv run alembic upgrade head
docker compose run --rm api uv run procrastinate --app app.worker.app.app schema --apply
docker compose up
```

Expected: all 7 containers healthy. No Redis container. No Beat container.

- [ ] **Step 5: Smoke test**

- Hit `GET /v1/health/live` → `{"status": "ok"}`
- Hit `GET /v1/queue/summary` → returns queue stats
- Upload a small CSV (5 domains) and confirm scrape jobs appear in `procrastinate_jobs`

- [ ] **Step 6: Commit**

```bash
git add Dockerfile.worker-scrape docker-compose.yml docker-compose.local.yml
git commit -m "feat: 4-container docker-compose — postgres, api, worker-scrape, worker-pipeline; no redis"
```

---

## Task 13: Cleanup & Final Test Run

- [ ] **Step 1: Check for any remaining Celery/Redis references**

```bash
grep -r "celery\|redis\|billiard\|SoftTimeLimitExceeded\|acks_late\|task_routes\|beat_schedule" app/ --include="*.py" -l
```
Expected: empty output.

- [ ] **Step 2: Run linter**

```bash
uv run ruff check app/ --fix
```
Expected: exits 0.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v 2>&1 | tail -40
```
Expected: all tests pass. Note any skipped tests and confirm they are intentionally skipped.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup — no celery/redis references remain"
```

---

## Deployment Runbook (Live DB)

When code is ready and tested on a DB copy:

1. `pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql`
2. Stop all current workers (Celery) via Coolify
3. `uv run alembic upgrade head` against live DB
4. `uv run procrastinate --app app.worker.app.app schema --apply`
5. Deploy new containers via Coolify
6. Verify `GET /v1/health/live` and `GET /v1/queue/summary`
7. Trigger a scrape on one known domain to confirm end-to-end flow

Rollback: stop new containers, restore from pg_dump, redeploy old containers.
