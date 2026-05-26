# S1 Scrape Procrastinate Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make S1 scraping use `scrape_results` as the only app-owned work/result table while Procrastinate owns queue execution, removing S1 dispatcher races and stale frontend running state.

**Architecture:** `POST /v1/scrape-jobs` creates a batch and one `scrape_results` row per domain, then directly enqueues one Procrastinate `scrape_domain(result_id)` job per result. Worker processing is idempotent against `scrape_results`; batch/progress UI reads one status projection that derives app status from `scrape_results` and queue status from `procrastinate_jobs`.

**Tech Stack:** FastAPI, SQLModel/SQLAlchemy, PostgreSQL, Procrastinate 2.15.1, React/Vite/TypeScript.

---

## Current Starting State

There are already uncommitted code changes from the previous S1 sidebar-count/race investigation. Do not discard them. Treat them as work-in-progress unless the owner explicitly asks to revert.

Known current files with changes include:

- `app/api/routes/companies.py`
- `app/api/schemas/scrape.py`
- `app/services/scrape_service.py`
- `apps/web/src/App.tsx`
- `apps/web/src/components/layout/AppShell.tsx`
- `apps/web/src/components/layout/BottomNav.tsx`
- `apps/web/src/components/layout/Sidebar.tsx`
- `apps/web/src/components/layout/bottom-nav/BottomSheet.tsx`
- `apps/web/src/components/layout/sidebar/StageNavItem.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/types.ts`
- `app/tests/test_scrape_counts.py`
- `app/tests/test_scrape_service_claim.py`
- `apps/web/src/lib/format.ts`

Before implementing, run:

```bash
git status --short
```

Expected: the above files may be modified/untracked. Continue without reverting them.

---

## File Structure

### Backend

- Modify: `app/api/schemas/scrape.py`
  - Add queue/product status schemas for S1 batch status projection.
  - Keep existing `ScrapeBatchRead` for compatibility.

- Modify: `app/api/routes/scrape_runs.py`
  - Add `POST /v1/scrape-jobs`.
  - Add `GET /v1/scrape-jobs/{batch_id}/status`.
  - Keep `POST /v1/scrape-batches` as compatibility wrapper around the new creation function.
  - Keep `GET /v1/scrape-batches/active` as compatibility projection around the new derived status.
  - Stop using S1 `dispatch_scrape_batch` in the creation path.

- Modify: `app/jobs/scrape.py`
  - Keep `scrape_domain` task.
  - Stop relying on `dispatch_scrape_batch` for new S1 path.
  - Leave `dispatch_scrape_batch` temporarily for backward compatibility/tests unless cleanup is explicitly requested.

- Modify: `app/services/scrape_service.py`
  - Make worker idempotent over `queued` and `running` rows.
  - Return normally for terminal `succeeded` or permanent `failed` rows.
  - Raise only for infra/unexpected failures that Procrastinate should retry.
  - Ensure final writes update `scrape_results` and `uploaded_domains.scrape_status` atomically.

- Create: `app/services/scrape_job_status.py`
  - Own derived status calculations.
  - Query `scrape_results` by batch.
  - Query `procrastinate_jobs` by `args->>'result_id'` for matching result IDs.
  - Produce status projection and consistency flags.

- Create/modify tests under `app/tests/`
  - `app/tests/test_scrape_job_create.py`
  - `app/tests/test_scrape_job_status.py`
  - `app/tests/test_scrape_service_idempotency.py`

### Frontend

- Modify: `apps/web/src/lib/types.ts`
  - Add `ScrapeJobStatusRead`, `ScrapeJobProductCounts`, `ScrapeJobQueueCounts`.

- Modify: `apps/web/src/lib/api.ts`
  - Add `createScrapeJob`.
  - Add `getScrapeJobStatus`.
  - Keep old `createScrapeBatch` during transition if needed.

- Modify: `apps/web/src/App.tsx`
  - Store one S1 active status projection instead of relying on stale batch counters.
  - Pass derived S1 count/live state into shell.

- Modify: `apps/web/src/components/views/scraping/ScrapingView.tsx`
  - Create jobs using `POST /v1/scrape-jobs`.
  - Poll `GET /v1/scrape-jobs/{batch_id}/status` while active.
  - Use status projection for banner/header stats/action lock.
  - Keep domain-list polling for row updates only.

- Modify: `apps/web/src/components/layout/header/LiveStatus.tsx`
  - No major API change expected if `StatsResponse` mapping remains in `App.tsx`.

---

## Task 1: Backend Status Schema

**Files:**
- Modify: `app/api/schemas/scrape.py`

- [ ] **Step 1: Add failing import-level schema test**

Create `app/tests/test_scrape_status_schema.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.api.schemas.scrape import ScrapeJobStatusRead


def test_scrape_job_status_schema_accepts_projection_payload() -> None:
    payload = {
        "batch_id": uuid4(),
        "campaign_id": uuid4(),
        "state": "running",
        "selected": 3,
        "queued": 1,
        "running": 1,
        "succeeded": 1,
        "failed": 0,
        "terminal": 1,
        "queue_todo": 1,
        "queue_doing": 1,
        "queue_succeeded": 1,
        "queue_failed": 0,
        "queue_cancelled": 0,
        "queue_aborting": 0,
        "queue_aborted": 0,
        "eta_seconds": 120.0,
        "inconsistency_reason": None,
        "created_at": datetime.now(timezone.utc),
        "finished_at": None,
    }

    status = ScrapeJobStatusRead.model_validate(payload)

    assert status.state == "running"
    assert status.selected == 3
    assert status.queue_todo == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_status_schema.py
```

Expected: fail with `ImportError` or `cannot import name 'ScrapeJobStatusRead'`.

- [ ] **Step 3: Add schema classes**

In `app/api/schemas/scrape.py`, add below `ScrapeBatchList` and above `ScrapeResultRead`:

```python
class ScrapeJobStatusRead(UTCReadModel):
    batch_id: UUID
    campaign_id: UUID
    state: str
    selected: int
    queued: int
    running: int
    succeeded: int
    failed: int
    terminal: int
    queue_todo: int
    queue_doing: int
    queue_succeeded: int
    queue_failed: int
    queue_cancelled: int
    queue_aborting: int
    queue_aborted: int
    eta_seconds: float | None = None
    inconsistency_reason: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_status_schema.py
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas/scrape.py app/tests/test_scrape_status_schema.py
git commit -m "test: add S1 scrape status schema"
```

---

## Task 2: Derived Status Service

**Files:**
- Create: `app/services/scrape_job_status.py`
- Create: `app/tests/test_scrape_job_status.py`

- [ ] **Step 1: Write failing tests for completed and inconsistent batches**

Create `app/tests/test_scrape_job_status.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlmodel import SQLModel, Session, create_engine

from app.models.scrape import ScrapeBatch, ScrapeResult
from app.services.scrape_job_status import build_scrape_job_status


def test_status_completed_when_all_results_terminal() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    batch_id = uuid4()
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add(ScrapeBatch(id=batch_id, campaign_id=campaign_id, selected_domain_count=2, created_at=now - timedelta(minutes=3)))
        session.add(ScrapeResult(campaign_id=campaign_id, domain_id=uuid4(), scrape_batch_id=batch_id, state="succeeded"))
        session.add(ScrapeResult(campaign_id=campaign_id, domain_id=uuid4(), scrape_batch_id=batch_id, state="failed"))
        session.commit()

        status = build_scrape_job_status(session=session, batch_id=batch_id)

    assert status is not None
    assert status.state == "completed"
    assert status.selected == 2
    assert status.terminal == 2
    assert status.inconsistency_reason is None


def test_status_inconsistent_when_non_terminal_results_have_no_live_queue_jobs() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    batch_id = uuid4()

    with Session(engine) as session:
        session.add(ScrapeBatch(id=batch_id, campaign_id=campaign_id, selected_domain_count=1))
        session.add(ScrapeResult(campaign_id=campaign_id, domain_id=uuid4(), scrape_batch_id=batch_id, state="running"))
        session.commit()

        status = build_scrape_job_status(session=session, batch_id=batch_id)

    assert status is not None
    assert status.state == "inconsistent"
    assert status.running == 1
    assert status.inconsistency_reason == "non_terminal_results_without_live_queue_jobs"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_job_status.py
```

Expected: fail with missing module `app.services.scrape_job_status`.

- [ ] **Step 3: Implement status service**

Create `app/services/scrape_job_status.py`:

```python
from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, text
from sqlmodel import Session, col, select

from app.api.schemas.scrape import ScrapeJobStatusRead
from app.models.scrape import ScrapeBatch, ScrapeResult

_TERMINAL_RESULT_STATES = {"succeeded", "failed"}
_LIVE_QUEUE_STATES = {"todo", "doing"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _eta_seconds(*, batch: ScrapeBatch, terminal: int, selected: int) -> float | None:
    remaining = selected - terminal
    if remaining <= 0:
        return 0.0
    elapsed = (_utcnow() - batch.created_at).total_seconds()
    if elapsed < 5 or terminal <= 0:
        return None
    rate = terminal / elapsed
    if rate <= 0:
        return None
    return float(math.ceil(remaining / rate))


def _queue_counts_for_results(session: Session, result_ids: list[UUID]) -> dict[str, int]:
    if not result_ids:
        return {}
    # SQLite unit tests do not have Procrastinate tables. Treat missing queue
    # visibility as zero queue counts; Postgres runtime will use this projection.
    dialect_name = session.get_bind().dialect.name
    if dialect_name != "postgresql":
        return {}

    rows = session.exec(
        text(
            """
            select status::text, count(*)
            from procrastinate_jobs
            where task_name = 'scrape_domain'
              and args->>'result_id' = any(:result_ids)
            group by status::text
            """
        ),
        params={"result_ids": [str(rid) for rid in result_ids]},
    ).all()
    return {str(status): int(count) for status, count in rows}


def build_scrape_job_status(*, session: Session, batch_id: UUID) -> ScrapeJobStatusRead | None:
    batch = session.get(ScrapeBatch, batch_id)
    if batch is None:
        return None

    state_rows = session.exec(
        select(col(ScrapeResult.state), func.count(ScrapeResult.id))
        .where(col(ScrapeResult.scrape_batch_id) == batch_id)
        .group_by(col(ScrapeResult.state))
    ).all()
    by_state = {str(state): int(count) for state, count in state_rows}

    result_ids = list(
        session.exec(
            select(col(ScrapeResult.id)).where(col(ScrapeResult.scrape_batch_id) == batch_id)
        ).all()
    )
    queue_counts = _queue_counts_for_results(session, result_ids)

    queued = by_state.get("queued", 0)
    running = by_state.get("running", 0)
    succeeded = by_state.get("succeeded", 0)
    failed = by_state.get("failed", 0)
    selected = len(result_ids)
    terminal = succeeded + failed

    queue_todo = queue_counts.get("todo", 0)
    queue_doing = queue_counts.get("doing", 0)
    live_queue = queue_todo + queue_doing
    non_terminal = queued + running

    inconsistency_reason = None
    if selected > 0 and terminal >= selected:
        state = "completed"
    elif non_terminal > 0 and live_queue > 0:
        state = "running"
    elif non_terminal > 0 and live_queue == 0:
        state = "inconsistent"
        inconsistency_reason = "non_terminal_results_without_live_queue_jobs"
    else:
        state = "completed"

    return ScrapeJobStatusRead(
        batch_id=batch.id,
        campaign_id=batch.campaign_id,
        state=state,
        selected=selected,
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        terminal=terminal,
        queue_todo=queue_todo,
        queue_doing=queue_doing,
        queue_succeeded=queue_counts.get("succeeded", 0),
        queue_failed=queue_counts.get("failed", 0),
        queue_cancelled=queue_counts.get("cancelled", 0),
        queue_aborting=queue_counts.get("aborting", 0),
        queue_aborted=queue_counts.get("aborted", 0),
        eta_seconds=_eta_seconds(batch=batch, terminal=terminal, selected=selected) if state == "running" else None,
        inconsistency_reason=inconsistency_reason,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_job_status.py
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/services/scrape_job_status.py app/tests/test_scrape_job_status.py
git commit -m "feat: derive S1 scrape job status"
```

---

## Task 3: Direct Scrape Job Creation API

**Files:**
- Modify: `app/api/routes/scrape_runs.py`
- Create: `app/tests/test_scrape_job_create.py`

- [ ] **Step 1: Write failing test for direct enqueue**

Create `app/tests/test_scrape_job_create.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from app.api.routes import scrape_runs
from app.api.schemas.scrape import ScrapeBatchCreate
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeResult


@pytest.mark.asyncio
async def test_create_scrape_job_creates_results_and_enqueues_each_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    domain_id = uuid4()

    with Session(engine) as session:
        session.add(
            UploadedDomain(
                id=domain_id,
                campaign_id=campaign_id,
                raw_url="https://example.com",
                normalized_url="https://example.com",
                domain="example.com",
                dedupe_key="example.com",
            )
        )
        session.commit()

    enqueued: list[str] = []

    async def fake_enqueue(result_ids):
        enqueued.extend(str(result_id) for result_id in result_ids)

    monkeypatch.setattr(scrape_runs, "is_procrastinate_schema_ready", lambda _engine: True)
    monkeypatch.setattr(scrape_runs, "get_engine", lambda: engine)
    monkeypatch.setattr(scrape_runs, "_enqueue_scrape_results", fake_enqueue)

    with Session(engine) as session:
        batch = await scrape_runs.create_scrape_job(
            body=ScrapeBatchCreate(campaign_id=campaign_id, domain_ids=[domain_id]),
            session=session,
        )
        results = session.exec(select(ScrapeResult).where(ScrapeResult.scrape_batch_id == batch.id)).all()

    assert batch.selected_domain_count == 1
    assert len(results) == 1
    assert results[0].state == "queued"
    assert enqueued == [str(results[0].id)]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_job_create.py
```

Expected: fail because `create_scrape_job` or `_enqueue_scrape_results` does not exist.

- [ ] **Step 3: Implement direct enqueue helper**

In `app/api/routes/scrape_runs.py`, add near `_resolve_domains`:

```python
async def _enqueue_scrape_results(result_ids: list[UUID]) -> None:
    from app.jobs.scrape import scrape_domain

    for result_id in result_ids:
        await scrape_domain.defer_async(result_id=str(result_id))
```

- [ ] **Step 4: Extract shared creation function and route**

In `app/api/routes/scrape_runs.py`, replace the body of `create_scrape_batch` with a wrapper and add new route:

```python
async def _create_scrape_job_impl(
    body: ScrapeBatchCreate,
    session: Session,
) -> ScrapeBatchRead:
    if not is_procrastinate_schema_ready(get_engine()):
        raise HTTPException(
            status_code=503,
            detail=(
                "Queue schema is not initialized. Run "
                "`uv run python scripts/apply_procrastinate_schema_maybe.py` "
                "and start the scrape worker (`./scripts/run_worker.sh scrape 2`)."
            ),
        )

    active_status = _active_batch_for_campaign(session=session, campaign_id=body.campaign_id)
    if active_status is not None:
        raise HTTPException(
            status_code=409,
            detail="A scrape batch is already active for this campaign. Wait for it to finish.",
        )

    domains = _resolve_domains(session, body.campaign_id, body)
    if not domains:
        raise HTTPException(status_code=400, detail="No matching domains found.")

    settings_row = session.exec(
        select(ScrapeSettings).where(
            col(ScrapeSettings.campaign_id) == body.campaign_id,
            col(ScrapeSettings.is_active).is_(True),
        ).order_by(col(ScrapeSettings.created_at).desc()).limit(1)
    ).first()

    settings_snapshot = build_scrape_rules_snapshot(
        instruction_text=settings_row.instruction_text if settings_row else None,
        structured_rules=settings_row.structured_rules_json if settings_row else None,
        default_rules=DEFAULT_STRUCTURED_RULES,
    )

    batch = ScrapeBatch(
        campaign_id=body.campaign_id,
        scrape_settings_id=settings_row.id if settings_row else None,
        settings_snapshot_json=settings_snapshot,
        state="queued",
        selected_domain_count=len(domains),
    )
    session.add(batch)
    session.flush()

    results = [
        ScrapeResult(
            campaign_id=body.campaign_id,
            domain_id=d.id,
            scrape_batch_id=batch.id,
            state="queued",
        )
        for d in domains
    ]
    session.add_all(results)

    for domain in domains:
        domain.scrape_status = "queued"
        session.add(domain)

    session.commit()
    session.refresh(batch)

    await _enqueue_scrape_results([result.id for result in results])

    return _batch_read(batch)


@router.post("/scrape-jobs", response_model=ScrapeBatchRead, status_code=201)
async def create_scrape_job(
    body: ScrapeBatchCreate,
    session: Session = Depends(get_session),
) -> ScrapeBatchRead:
    return await _create_scrape_job_impl(body=body, session=session)


@router.post("/scrape-batches", response_model=ScrapeBatchRead, status_code=201)
async def create_scrape_batch(
    body: ScrapeBatchCreate,
    session: Session = Depends(get_session),
) -> ScrapeBatchRead:
    return await _create_scrape_job_impl(body=body, session=session)
```

Also add helper before `_create_scrape_job_impl`:

```python
def _active_batch_for_campaign(*, session: Session, campaign_id: UUID) -> ScrapeBatch | None:
    batch = session.exec(
        select(ScrapeBatch)
        .where(col(ScrapeBatch.campaign_id) == campaign_id)
        .order_by(col(ScrapeBatch.created_at).desc())
        .limit(1)
    ).first()
    if batch is None:
        return None
    status = build_scrape_job_status(session=session, batch_id=batch.id)
    if status and status.state in {"queued", "running"}:
        return batch
    return None
```

Import:

```python
from app.services.scrape_job_status import build_scrape_job_status
```

- [ ] **Step 5: Run test**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_job_create.py
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes/scrape_runs.py app/tests/test_scrape_job_create.py
git commit -m "feat: create S1 scrape jobs directly"
```

---

## Task 4: Status API And Active Compatibility

**Files:**
- Modify: `app/api/routes/scrape_runs.py`
- Create/modify: `app/tests/test_scrape_job_status_api.py`

- [ ] **Step 1: Write failing route-level tests by direct function call**

Create `app/tests/test_scrape_job_status_api.py`:

```python
from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

from app.api.routes.scrape_runs import get_active_batch, get_scrape_job_status
from app.models.scrape import ScrapeBatch, ScrapeResult


def test_get_scrape_job_status_returns_projection() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    batch_id = uuid4()

    with Session(engine) as session:
        session.add(ScrapeBatch(id=batch_id, campaign_id=campaign_id, selected_domain_count=1))
        session.add(ScrapeResult(campaign_id=campaign_id, domain_id=uuid4(), scrape_batch_id=batch_id, state="succeeded"))
        session.commit()

        status = get_scrape_job_status(batch_id=batch_id, session=session)

    assert status.state == "completed"
    assert status.succeeded == 1


def test_get_scrape_job_status_404_for_missing_batch() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        try:
            get_scrape_job_status(batch_id=uuid4(), session=session)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Expected HTTPException")


def test_active_batch_ignores_completed_latest_batch() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    batch_id = uuid4()

    with Session(engine) as session:
        session.add(ScrapeBatch(id=batch_id, campaign_id=campaign_id, selected_domain_count=1))
        session.add(ScrapeResult(campaign_id=campaign_id, domain_id=uuid4(), scrape_batch_id=batch_id, state="succeeded"))
        session.commit()

        active = get_active_batch(campaign_id=campaign_id, session=session)

    assert active is None
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_job_status_api.py
```

Expected: fail because `get_scrape_job_status` route does not exist or active still trusts batch state.

- [ ] **Step 3: Add status route and update active route**

In `app/api/routes/scrape_runs.py`, import schema:

```python
from app.api.schemas.scrape import ScrapeJobStatusRead
```

Add route before `get_scrape_batch`:

```python
@router.get("/scrape-jobs/{batch_id}/status", response_model=ScrapeJobStatusRead)
def get_scrape_job_status(
    batch_id: UUID,
    session: Session = Depends(get_session),
) -> ScrapeJobStatusRead:
    status = build_scrape_job_status(session=session, batch_id=batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return status
```

Replace `get_active_batch` implementation with derived status:

```python
@router.get("/scrape-batches/active", response_model=ScrapeBatchRead | None)
def get_active_batch(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ScrapeBatchRead | None:
    batches = session.exec(
        select(ScrapeBatch)
        .where(col(ScrapeBatch.campaign_id) == campaign_id)
        .order_by(col(ScrapeBatch.created_at).desc())
        .limit(10)
    ).all()
    for batch in batches:
        status = build_scrape_job_status(session=session, batch_id=batch.id)
        if status and status.state in {"queued", "running"}:
            return ScrapeBatchRead(
                id=batch.id,
                campaign_id=batch.campaign_id,
                state=status.state,
                selected_domain_count=status.selected,
                queued_count=status.queued + status.running,
                success_count=status.succeeded,
                failed_count=status.failed,
                created_at=batch.created_at,
                finished_at=batch.finished_at,
                eta_seconds=status.eta_seconds,
            )
    return None
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_job_status_api.py app/tests/test_scrape_job_status.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/scrape_runs.py app/tests/test_scrape_job_status_api.py
git commit -m "feat: expose S1 scrape job status"
```

---

## Task 5: Worker Idempotency Contract

**Files:**
- Modify: `app/services/scrape_service.py`
- Create/modify: `app/tests/test_scrape_service_idempotency.py`

- [ ] **Step 1: Write failing tests for terminal no-op and running recovery**

Create `app/tests/test_scrape_service_idempotency.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from app.models.core import UploadedDomain
from app.models.scrape import ScrapeBatch, ScrapeResult
from app.services import scrape_service
from app.services.scrape_service import ScrapeService


def _seed(engine, *, result_state: str, retryable: bool | None = None):
    campaign_id = uuid4()
    batch_id = uuid4()
    domain_id = uuid4()
    result_id = uuid4()
    with Session(engine) as session:
        session.add(UploadedDomain(
            id=domain_id,
            campaign_id=campaign_id,
            raw_url="https://recover.test",
            normalized_url="https://recover.test",
            domain="recover.test",
            dedupe_key="recover.test",
            scrape_status=result_state if result_state in {"succeeded", "failed"} else "running",
        ))
        session.add(ScrapeBatch(id=batch_id, campaign_id=campaign_id, selected_domain_count=1))
        session.add(ScrapeResult(
            id=result_id,
            campaign_id=campaign_id,
            domain_id=domain_id,
            scrape_batch_id=batch_id,
            state=result_state,
            retryable=retryable,
        ))
        session.commit()
    return result_id


@pytest.mark.asyncio
async def test_worker_returns_for_terminal_success_without_reprocessing(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    result_id = _seed(engine, result_state="succeeded")
    called = False

    async def fake_resolve_domain(_domain: str) -> bool:
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(scrape_service, "resolve_domain", fake_resolve_domain)

    await ScrapeService().run_scrape(engine=engine, result_id=result_id)

    assert called is False


@pytest.mark.asyncio
async def test_worker_reprocesses_running_result_after_worker_death(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    result_id = _seed(engine, result_state="running")

    async def fake_resolve_domain(_domain: str) -> bool:
        return False

    monkeypatch.setattr(scrape_service, "resolve_domain", fake_resolve_domain)

    await ScrapeService().run_scrape(engine=engine, result_id=result_id)

    with Session(engine) as session:
        result = session.exec(select(ScrapeResult).where(ScrapeResult.id == result_id)).one()

    assert result.state == "failed"
    assert result.error_code == "dns_not_resolved"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_service_idempotency.py
```

Expected: at least the `running` recovery test fails with skipped owner/claim behavior.

- [ ] **Step 3: Update worker claim logic**

In `app/services/scrape_service.py`, replace the claim section with explicit terminal checks:

```python
        # ── Claim ──────────────────────────────────────────────────────────────
        with Session(engine) as session:
            existing = session.get(ScrapeResult, result_id)
            if existing is None:
                return
            if existing.state == "succeeded":
                log_event(logger, "scrape_skipped_terminal_success", result_id=str(result_id))
                return
            if existing.state == "failed" and existing.retryable is False:
                log_event(logger, "scrape_skipped_terminal_failure", result_id=str(result_id))
                return

            updated = session.execute(
                sa_update(ScrapeResult)
                .where(
                    col(ScrapeResult.id) == result_id,
                    col(ScrapeResult.state).in_(["queued", "running", "failed"]),
                )
                .values(state="running", updated_at=_utcnow())
                .returning(ScrapeResult.id)
            )
            claimed = updated.first()
            session.commit()
            if not claimed:
                log_event(logger, "scrape_skipped_already_claimed", result_id=str(result_id))
                return
```

Then narrow retryable failed processing to only retryable rows by adding `existing.retryable is True` guard if needed. Do not process permanent failed rows.

- [ ] **Step 4: Update final write guard**

In final result write, keep:

```python
if result_row is None or result_row.state != "running":
```

This remains correct because the worker sets `running` before processing.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run python -m pytest -q app/tests/test_scrape_service_idempotency.py app/tests/test_scrape_service_claim.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/scrape_service.py app/tests/test_scrape_service_idempotency.py app/tests/test_scrape_service_claim.py
git commit -m "fix: make S1 scrape worker idempotent"
```

---

## Task 6: Frontend API Types

**Files:**
- Modify: `apps/web/src/lib/types.ts`
- Modify: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Add TypeScript types**

In `apps/web/src/lib/types.ts`, add near `ScrapeBatchRead`:

```ts
export type ScrapeJobStatusRead = {
  batch_id: string
  campaign_id: string
  state: 'queued' | 'running' | 'completed' | 'failed' | 'inconsistent' | string
  selected: number
  queued: number
  running: number
  succeeded: number
  failed: number
  terminal: number
  queue_todo: number
  queue_doing: number
  queue_succeeded: number
  queue_failed: number
  queue_cancelled: number
  queue_aborting: number
  queue_aborted: number
  eta_seconds: number | null
  inconsistency_reason: string | null
  created_at: string
  finished_at: string | null
}
```

- [ ] **Step 2: Add API functions**

In `apps/web/src/lib/api.ts`, import `ScrapeJobStatusRead` and add below batch functions:

```ts
export async function createScrapeJob(body: ScrapeBatchCreate): Promise<ScrapeBatchRead> {
  return request<ScrapeBatchRead>('/v1/scrape-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function getScrapeJobStatus(batchId: string): Promise<ScrapeJobStatusRead> {
  return request<ScrapeJobStatusRead>(`/v1/scrape-jobs/${encodeURIComponent(batchId)}/status`)
}
```

- [ ] **Step 3: Build check**

Run:

```bash
npm run build
```

Expected: TypeScript build passes or fails only because functions are unused; unused exports are allowed.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/types.ts apps/web/src/lib/api.ts
git commit -m "feat: add S1 scrape job API client"
```

---

## Task 7: Frontend Status Projection Wiring

**Files:**
- Modify: `apps/web/src/components/views/scraping/ScrapingView.tsx`
- Modify: `apps/web/src/App.tsx`

- [ ] **Step 1: Replace creation call**

In `ScrapingView.tsx`, change imports:

```ts
import {
  buildApiUrl,
  getDomainLetterCounts,
  createScrapeJob,
  getActiveBatch,
  getScrapeJobStatus,
  listDomains,
} from '../../../lib/api'
import type { DomainRead, ScrapeBatchRead, DomainLetterCounts, ScrapeJobStatusRead } from '../../../lib/types'
```

Replace:

```ts
const batch = await createScrapeBatch(body as Parameters<typeof createScrapeBatch>[0])
```

with:

```ts
const batch = await createScrapeJob(body as Parameters<typeof createScrapeJob>[0])
```

- [ ] **Step 2: Add status state**

Inside `ScrapingView` state declarations:

```ts
const [activeStatus, setActiveStatus] = useState<ScrapeJobStatusRead | null>(null)
```

- [ ] **Step 3: Poll job status when active batch exists**

Add callback:

```ts
const loadActiveStatus = useCallback(async (): Promise<ScrapeJobStatusRead | null> => {
  if (!activeBatch) {
    setActiveStatus(null)
    return null
  }
  try {
    const status = await getScrapeJobStatus(activeBatch.id)
    setActiveStatus(status)
    if (status.state === 'completed' || status.state === 'failed' || status.state === 'inconsistent') {
      setActiveBatch(null)
      void loadDomains(page)
      void loadLetterCounts()
    }
    return status
  } catch {
    return null
  }
}, [activeBatch, loadDomains, loadLetterCounts, page])
```

- [ ] **Step 4: Update polling effect**

In the existing polling fallback effect, call `loadActiveStatus()` when `activeBatch` exists and use `loadActiveBatch()` only for initial/compatibility discovery.

The logic should be:

```ts
const batchTick = async () => {
  if (activeBatch) {
    await loadActiveStatus()
    return
  }
  const batch = await loadActiveBatch()
  if (cancelled) return
  if (!batch || ['completed', 'failed'].includes(batch.state)) {
    setActiveBatch(null)
    setActiveStatus(null)
    void loadDomains(page)
    void loadLetterCounts()
  }
}
```

Add `loadActiveStatus` to effect dependencies.

- [ ] **Step 5: Use status for display counts**

Replace `statusCounts` calculation with:

```ts
const progress = activeStatus
const runningCount = progress ? Math.max(0, progress.queued + progress.running) : 0
const completedCount = progress ? progress.terminal : 0
const selectedCount = progress ? progress.selected : activeBatch?.selected_domain_count ?? 0

const scrapeStats = [
  { label: 'total', value: domainTotal },
  { label: 'running', value: runningCount, live: runningCount > 0, color: 'var(--s1)' },
]
```

Update banner text to use:

```tsx
{completedCount} / {selectedCount.toLocaleString()} done
{progress?.eta_seconds != null && ...}
{progress?.state === 'inconsistent' && 'Queue state needs reconciliation'}
```

- [ ] **Step 6: Send status to App shell**

Change `ScrapingViewProps`:

```ts
onActiveBatchChange?: (batch: ScrapeBatchRead | null, status?: ScrapeJobStatusRead | null) => void
```

Update effect:

```ts
useEffect(() => {
  onActiveBatchChange?.(activeBatch, activeStatus)
}, [activeBatch, activeStatus, onActiveBatchChange])
```

In `App.tsx`, add:

```ts
const [activeScrapeStatus, setActiveScrapeStatus] = useState<ScrapeJobStatusRead | null>(null)
```

Update handler:

```tsx
onActiveBatchChange={(batch, status) => {
  setActiveScrapeBatch(batch)
  setActiveScrapeStatus(status ?? null)
}}
```

Map shell stats from `activeScrapeStatus` first, falling back to batch only during creation.

- [ ] **Step 7: Build check**

Run:

```bash
npm run build
```

Expected: build passes.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/components/views/scraping/ScrapingView.tsx apps/web/src/App.tsx
git commit -m "feat: drive S1 UI from scrape job status"
```

---

## Task 8: Remove S1 Dispatcher Dependence And Recheck Existing Tests

**Files:**
- Modify: `app/jobs/scrape.py`
- Modify: existing tests if they assert dispatcher behavior for S1 as primary path.

- [ ] **Step 1: Mark dispatcher as legacy compatibility**

In `app/jobs/scrape.py`, add comment above `dispatch_scrape_batch`:

```python
# Legacy compatibility task. New S1 creation enqueues scrape_domain jobs directly.
# Keep this temporarily so older queued dispatcher jobs can drain safely.
```

Do not delete it in this pass.

- [ ] **Step 2: Ensure no new S1 route calls dispatcher**

Run:

```bash
rg -n "dispatch_scrape_batch\.defer|dispatch_scrape_batch" app/api app/jobs app/services
```

Expected:

- Definition remains in `app/jobs/scrape.py`.
- Tests may reference it.
- `app/api/routes/scrape_runs.py` should not call `dispatch_scrape_batch.defer_async`.

- [ ] **Step 3: Run focused backend test suite**

Run:

```bash
uv run python -m pytest -q \
  app/tests/test_scrape_status_schema.py \
  app/tests/test_scrape_job_status.py \
  app/tests/test_scrape_job_create.py \
  app/tests/test_scrape_job_status_api.py \
  app/tests/test_scrape_service_idempotency.py \
  app/tests/test_scrape_service_claim.py \
  app/tests/test_scrape_counts.py \
  app/tests/test_scrape_batch_queue_gate.py \
  app/tests/test_queue_guard.py \
  app/tests/test_link_classifier_prompt.py \
  app/tests/test_scrape_failure_classification.py
```

Expected: all pass.

- [ ] **Step 4: Run lint**

Run:

```bash
uv run ruff check app/api/routes/scrape_runs.py app/api/schemas/scrape.py app/jobs/scrape.py app/services/scrape_service.py app/services/scrape_job_status.py app/tests/
```

Expected: all checks passed.

- [ ] **Step 5: Commit**

```bash
git add app/jobs/scrape.py app/tests app/api/routes/scrape_runs.py app/api/schemas/scrape.py app/services/scrape_service.py app/services/scrape_job_status.py
git commit -m "chore: keep S1 dispatcher as legacy compatibility"
```

---

## Task 9: Final Integration Verification

**Files:**
- No planned edits unless checks fail.

- [ ] **Step 1: Apply Procrastinate schema if needed**

Run only if local queue schema is missing:

```bash
uv run python scripts/apply_procrastinate_schema_maybe.py
```

Expected: `procrastinate SQL schema OK`.

- [ ] **Step 2: Start worker manually in another terminal**

Run:

```bash
./scripts/run_worker.sh scrape 2
```

Expected: worker starts without import errors.

- [ ] **Step 3: Start API/frontend if not already running**

API command depends on local workflow. Common command:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
npm run dev
```

Expected: API on `localhost:8000`, frontend on Vite port.

- [ ] **Step 4: Trigger a small scrape batch**

From UI, select 2-3 pending domains and click scrape.

Expected:

- Batch creation returns quickly.
- Header, S1 panel, progress banner, and sidebar all show same live state.
- No dispatcher job appears for S1.
- Procrastinate jobs appear as `todo/doing/succeeded` for `scrape_domain`.
- `scrape_results` rows move `queued -> running -> succeeded/failed`.

- [ ] **Step 5: Query status endpoint manually**

Replace `<batch_id>`:

```bash
curl -sS http://localhost:8000/v1/scrape-jobs/<batch_id>/status | python -m json.tool
```

Expected fields:

```json
{
  "state": "running",
  "selected": 3,
  "terminal": 1,
  "queue_todo": 1,
  "queue_doing": 1
}
```

Or after completion:

```json
{
  "state": "completed",
  "selected": 3,
  "terminal": 3
}
```

- [ ] **Step 6: Final build**

Run:

```bash
npm run build
```

Expected: build passes.

- [ ] **Step 7: Final status check**

Run:

```bash
git status --short
```

Expected: only intentional files modified or clean after commits.

- [ ] **Step 8: Final commit if any integration fixes were needed**

```bash
git add <changed-files>
git commit -m "fix: stabilize S1 scrape job integration"
```

---

## Self-Review

Spec coverage:

- No new tables: covered.
- `scrape_results` as only app data/work/result table: covered in creation, worker, status tasks.
- Procrastinate as queue lifecycle only: covered in status projection and worker contract.
- Worker death recovery: covered by idempotent processing of `running` rows.
- Frontend does not read Procrastinate directly: covered by status API.
- Frontend no stale multi-source status: covered by Task 7.
- Dispatcher race removal: covered by direct enqueue and legacy-only dispatcher.

Placeholder scan:

- No `TBD`, `TODO`, or undefined implementation placeholders remain.
- Integration step has environment-dependent commands, but concrete commands are provided.

Type consistency:

- Backend schema `ScrapeJobStatusRead` fields match frontend `ScrapeJobStatusRead` fields.
- API functions `createScrapeJob` and `getScrapeJobStatus` match planned routes.
- Worker state vocabulary is consistently `queued`, `running`, `succeeded`, `failed`.
