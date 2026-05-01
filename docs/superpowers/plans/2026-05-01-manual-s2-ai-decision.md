# Manual S2 AI Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore manual S2 so operators can pick an enabled prompt, run AI decisions only for companies with scraped info, and see truthful run progress in the frontend.

**Architecture:** Preserve the existing S2 UI and prompt CRUD. Add a thin backend pipeline-run orchestration path that validates eligibility, creates `PipelineRun` and `AnalysisJob` rows, bridges scrape data into crawl adapters, and defers Procrastinate analysis tasks. Replace the `ai_decision` worker stub with a wrapper around `AnalysisService.run_analysis_job()`.

**Tech Stack:** FastAPI, SQLModel, Procrastinate, PostgreSQL/SQLite, React, TypeScript, Vitest, Pytest

---

## File map

| File | Responsibility |
|---|---|
| `app/api/routes/pipeline_runs.py` | Create manual S2 runs and expose run progress |
| `app/main.py` | Register the new pipeline-run router |
| `app/jobs/ai_decision.py` | Defer target that executes one `AnalysisJob` |
| `app/services/context_service.py` | Reuse `bulk_ensure_crawl_adapters()` and latest scrape helpers |
| `app/services/pipeline_service.py` | Reuse `latest_usable_scrape()` eligibility rule |
| `app/api/schemas/pipeline_run.py` | Reuse existing request/response schemas; extend only if absolutely required |
| `tests/test_pipeline_runs.py` | New backend coverage for manual S2 dispatch and progress |
| `tests/test_procrastinate_queue_architecture.py` | Extend worker-level coverage for `run_ai_decision` |
| `apps/web/src/lib/api.ts` | Return real `createRuns()` data from the backend response |
| `apps/web/tests/apiContracts.test.ts` | Keep API contract aligned with the backend |

No prompt schema or prompt CRUD changes are needed.

---

## Task 1: Add failing backend tests for manual S2 run creation

**Files:**
- Create: `tests/test_pipeline_runs.py`
- Test: `tests/test_pipeline_runs.py`

- [ ] **Step 1: Write the failing test for eligible vs skipped companies**

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.pipeline_run import PipelineRunStartRequest
from app.api.routes.pipeline_runs import start_pipeline_run, get_pipeline_run_progress
from app.models import AnalysisJob, Company, Prompt, ScrapeJob, ScrapePage, Upload
from app.models.pipeline import PipelineRun, PipelineRunStatus


def _seed_upload(session: Session, *, campaign_id) -> Upload:
    upload = Upload(
        campaign_id=campaign_id,
        filename="s2.csv",
        checksum=str(uuid4()),
        row_count=2,
        valid_count=2,
        invalid_count=0,
    )
    session.add(upload)
    session.flush()
    return upload


def _seed_company(session: Session, *, upload_id, domain: str) -> Company:
    company = Company(
        upload_id=upload_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
    )
    session.add(company)
    session.flush()
    return company


def _seed_prompt(session: Session) -> Prompt:
    prompt = Prompt(name="ICP v1", prompt_text="Classify {domain}\\n\\n{context}", enabled=True)
    session.add(prompt)
    session.flush()
    return prompt


def _seed_scrape(session: Session, *, company: Company) -> None:
    job = ScrapeJob(
        website_url=company.normalized_url,
        normalized_url=company.normalized_url,
        domain=company.domain,
        status="completed",
        state="succeeded",
        terminal_state=True,
        markdown_pages_count=1,
        pages_fetched_count=1,
    )
    session.add(job)
    session.flush()
    session.add(
        ScrapePage(
            job_id=job.id,
            url=company.normalized_url,
            canonical_url=company.normalized_url,
            page_kind="home",
            markdown_content="# Home",
        )
    )
    session.flush()


@pytest.mark.asyncio
async def test_start_pipeline_run_only_enqueues_companies_with_scraped_info(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.jobs import ai_decision as ai_decision_mod

    campaign = create_campaign(payload=CampaignCreate(name="S2"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    eligible = _seed_company(sqlite_session, upload_id=upload.id, domain="eligible.example")
    skipped = _seed_company(sqlite_session, upload_id=upload.id, domain="skipped.example")
    prompt = _seed_prompt(sqlite_session)
    _seed_scrape(sqlite_session, company=eligible)
    sqlite_session.commit()

    deferred: list[dict] = []

    async def fake_defer_async(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(ai_decision_mod.run_ai_decision, "defer_async", fake_defer_async)

    result = await start_pipeline_run(
        payload=PipelineRunStartRequest(
            campaign_id=campaign.id,
            company_ids=[str(eligible.id), str(skipped.id)],
            analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
        ),
        session=sqlite_session,
    )

    assert result.requested_count == 2
    assert result.queued_count == 1
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert len(deferred) == 1

    run = sqlite_session.get(PipelineRun, result.pipeline_run_id)
    assert run is not None
    jobs = list(sqlite_session.exec(select(AnalysisJob).where(AnalysisJob.pipeline_run_id == run.id)))
    assert len(jobs) == 1
    assert jobs[0].company_id == eligible.id

    progress = get_pipeline_run_progress(run.id, session=sqlite_session)
    assert progress.pipeline_run_id == run.id
    assert progress.requested_count == 2
    assert progress.queued_count == 1
    assert progress.skipped_count == 1
    assert progress.state in (PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING)
    assert progress.stages["analysis"].total == 1
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest tests/test_pipeline_runs.py::test_start_pipeline_run_only_enqueues_companies_with_scraped_info -q
```

Expected: fail with import error or missing `start_pipeline_run` route implementation.

- [ ] **Step 3: Add a failing test for disabled prompts**

```python
@pytest.mark.asyncio
async def test_start_pipeline_run_rejects_disabled_prompt(
    sqlite_session: Session,
) -> None:
    from fastapi import HTTPException

    campaign = create_campaign(payload=CampaignCreate(name="S2"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    company = _seed_company(sqlite_session, upload_id=upload.id, domain="eligible.example")
    prompt = Prompt(name="Disabled", prompt_text="Classify {context}", enabled=False)
    sqlite_session.add(prompt)
    _seed_scrape(sqlite_session, company=company)
    sqlite_session.commit()

    with pytest.raises(HTTPException) as exc:
        await start_pipeline_run(
            payload=PipelineRunStartRequest(
                campaign_id=campaign.id,
                company_ids=[str(company.id)],
                analysis_prompt_snapshot={"prompt_id": str(prompt.id)},
            ),
            session=sqlite_session,
        )

    assert exc.value.status_code == 400
```

- [ ] **Step 4: Run both tests**

Run:

```bash
uv run pytest tests/test_pipeline_runs.py -q
```

Expected: multiple failures until the route exists.

---

## Task 2: Implement backend manual S2 orchestration

**Files:**
- Create: `app/api/routes/pipeline_runs.py`
- Modify: `app/main.py`
- Test: `tests/test_pipeline_runs.py`

- [ ] **Step 1: Create the route module with manual S2 start + progress**

Create `app/api/routes/pipeline_runs.py` with this implementation:

```python
from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, cast, func
from sqlmodel import Session, col, select

from app.api.schemas.pipeline_run import (
    PipelineRunProgressRead,
    PipelineRunStartRequest,
    PipelineRunStartResponse,
    PipelineStageProgressRead,
)
from app.core.config import settings
from app.db.session import get_session
from app.jobs.ai_decision import run_ai_decision
from app.models import AnalysisJob, Company, PipelineRun, Prompt, Upload
from app.models.pipeline import AnalysisJobState, PipelineRunStatus, utcnow
from app.services.context_service import bulk_ensure_crawl_adapters, bulk_latest_completed_scrape_jobs
from app.services.pipeline_service import latest_usable_scrape


router = APIRouter(prefix="/v1", tags=["pipeline-runs"])


def _analysis_prompt_id(payload: PipelineRunStartRequest) -> UUID:
    snapshot = payload.analysis_prompt_snapshot or {}
    raw = snapshot.get("prompt_id")
    if not raw:
        raise HTTPException(status_code=400, detail="analysis_prompt_snapshot.prompt_id is required.")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid prompt_id.") from exc


def _refresh_run_counts(session: Session, run: PipelineRun) -> None:
    rows = list(
        session.exec(
            select(cast(AnalysisJob.state, String()), func.count(AnalysisJob.id))
            .where(col(AnalysisJob.pipeline_run_id) == run.id)
            .group_by(cast(AnalysisJob.state, String()))
        )
    )
    counts = {state: int(count) for state, count in rows}
    queued = counts.get("queued", 0)
    running = counts.get("running", 0)
    succeeded = counts.get("succeeded", 0)
    failed = counts.get("failed", 0) + counts.get("dead", 0)
    total = queued + running + succeeded + failed

    run.queued_count = queued
    run.failed_count = failed
    if total == 0:
        run.state = PipelineRunStatus.QUEUED
    elif queued > 0 or running > 0:
        run.state = PipelineRunStatus.RUNNING
        run.started_at = run.started_at or utcnow()
    elif failed > 0:
        run.state = PipelineRunStatus.FAILED
        run.finished_at = utcnow()
    else:
        run.state = PipelineRunStatus.SUCCEEDED
        run.finished_at = utcnow()
    run.updated_at = utcnow()
    session.add(run)


@router.post("/pipeline-runs/start", response_model=PipelineRunStartResponse)
async def start_pipeline_run(
    payload: PipelineRunStartRequest,
    session: Session = Depends(get_session),
) -> PipelineRunStartResponse:
    if not payload.company_ids:
        raise HTTPException(status_code=400, detail="company_ids is required for manual S2.")

    prompt = session.get(Prompt, _analysis_prompt_id(payload))
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    if not prompt.enabled:
        raise HTTPException(status_code=400, detail="Prompt must be enabled for manual S2.")

    company_ids = [UUID(str(company_id)) for company_id in payload.company_ids]
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == payload.campaign_id,
                col(Company.id).in_(company_ids),
            )
        )
    )
    found_ids = {company.id for company in companies}
    if found_ids != set(company_ids):
        raise HTTPException(status_code=400, detail="One or more company_ids are outside campaign scope.")

    run = PipelineRun(
        campaign_id=payload.campaign_id,
        requested_count=len(company_ids),
        analysis_prompt_snapshot={"prompt_id": str(prompt.id), "prompt_text": prompt.prompt_text},
        company_ids_snapshot=[str(company_id) for company_id in company_ids],
        state=PipelineRunStatus.QUEUED,
    )
    session.add(run)
    session.flush()

    eligible: list[Company] = []
    for company in companies:
        if latest_usable_scrape(session, company.normalized_url) is not None:
            eligible.append(company)

    scrape_map = bulk_latest_completed_scrape_jobs(
        session=session,
        normalized_urls=[company.normalized_url for company in eligible],
    )
    artifact_map = bulk_ensure_crawl_adapters(
        session=session,
        companies=eligible,
        scrape_map=scrape_map,
    )

    prompt_hash = hashlib.sha256(prompt.prompt_text.encode()).hexdigest()[:32]
    jobs: list[AnalysisJob] = []
    for company in eligible:
        artifact = artifact_map.get(company.id)
        if artifact is None:
            continue
        jobs.append(
            AnalysisJob(
                pipeline_run_id=run.id,
                upload_id=company.upload_id,
                company_id=company.id,
                crawl_artifact_id=artifact.id,
                prompt_id=prompt.id,
                general_model=settings.general_model,
                classify_model=settings.classify_model,
                state=AnalysisJobState.QUEUED,
                terminal_state=False,
                prompt_hash=prompt_hash,
            )
        )

    session.add_all(jobs)
    run.skipped_count = len(company_ids) - len(jobs)
    run.queued_count = len(jobs)
    run.failed_count = 0
    run.started_at = utcnow() if jobs else None
    run.updated_at = utcnow()
    session.add(run)
    session.commit()

    defer_failed = 0
    for job in jobs:
        try:
            await run_ai_decision.defer_async(analysis_job_id=str(job.id))
        except Exception:
            defer_failed += 1

    if defer_failed:
        with Session(session.get_bind()) as update_session:
            persisted_run = update_session.get(PipelineRun, run.id)
            if persisted_run is not None:
                persisted_run.failed_count += defer_failed
                persisted_run.queued_count -= defer_failed
                persisted_run.updated_at = utcnow()
                update_session.add(persisted_run)
                update_session.commit()
                update_session.refresh(persisted_run)
                run = persisted_run

    return PipelineRunStartResponse(
        pipeline_run_id=run.id,
        requested_count=run.requested_count,
        reused_count=0,
        queued_count=run.queued_count,
        skipped_count=run.skipped_count,
        failed_count=run.failed_count,
    )


@router.get("/pipeline-runs/{pipeline_run_id}/progress", response_model=PipelineRunProgressRead)
def get_pipeline_run_progress(
    pipeline_run_id: UUID,
    session: Session = Depends(get_session),
) -> PipelineRunProgressRead:
    run = session.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")

    _refresh_run_counts(session, run)
    session.commit()
    session.refresh(run)

    rows = list(
        session.exec(
            select(cast(AnalysisJob.state, String()), func.count(AnalysisJob.id))
            .where(col(AnalysisJob.pipeline_run_id) == pipeline_run_id)
            .group_by(cast(AnalysisJob.state, String()))
        )
    )
    counts = {state: int(count) for state, count in rows}
    analysis_progress = PipelineStageProgressRead(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        succeeded=counts.get("succeeded", 0),
        failed=counts.get("failed", 0) + counts.get("dead", 0),
        total=sum(counts.values()),
    )

    return PipelineRunProgressRead(
        pipeline_run_id=run.id,
        campaign_id=run.campaign_id,
        state=run.state,
        requested_count=run.requested_count,
        reused_count=run.reused_count,
        queued_count=run.queued_count,
        skipped_count=run.skipped_count,
        failed_count=run.failed_count,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stages={"analysis": analysis_progress},
    )
```

- [ ] **Step 2: Register the router**

In `app/main.py`, add:

```python
from app.api.routes.pipeline_runs import router as pipeline_runs_router
```

and register:

```python
app.include_router(pipeline_runs_router)
```

- [ ] **Step 3: Run the new tests**

Run:

```bash
uv run pytest tests/test_pipeline_runs.py -q
```

Expected: pass.

---

## Task 3: Replace the S2 worker stub with a real Procrastinate task

**Files:**
- Modify: `app/jobs/ai_decision.py`
- Modify: `tests/test_procrastinate_queue_architecture.py`

- [ ] **Step 1: Write the failing worker test**

Append to `tests/test_procrastinate_queue_architecture.py`:

```python
@pytest.mark.asyncio
async def test_run_ai_decision_calls_analysis_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.jobs.ai_decision import run_ai_decision

    calls: list[tuple[str, str]] = []

    class _DummyService:
        def run_analysis_job(self, *, engine, analysis_job_id):  # noqa: ANN001
            calls.append((str(engine.url), str(analysis_job_id)))
            return None

    monkeypatch.setattr("app.jobs.ai_decision.AnalysisService", lambda: _DummyService())

    await run_ai_decision("11111111-1111-1111-1111-111111111111")

    assert calls
    assert calls[0][1] == "11111111-1111-1111-1111-111111111111"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest tests/test_procrastinate_queue_architecture.py::test_run_ai_decision_calls_analysis_service -q
```

Expected: fail because `app/jobs/ai_decision.py` is still a stub.

- [ ] **Step 3: Implement the worker task**

Replace `app/jobs/ai_decision.py` with:

```python
"""Procrastinate task: execute one AnalysisJob."""
from __future__ import annotations

from uuid import UUID

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app
from app.services.analysis_service import AnalysisService


_service = AnalysisService()


@app.task(name="run_ai_decision", queue="ai_decision")
async def run_ai_decision(analysis_job_id: str) -> None:
    _service.run_analysis_job(
        engine=get_engine(),
        analysis_job_id=UUID(analysis_job_id),
    )
```

- [ ] **Step 4: Re-run the worker test**

Run:

```bash
uv run pytest tests/test_procrastinate_queue_architecture.py::test_run_ai_decision_calls_analysis_service -q
```

Expected: pass.

---

## Task 4: Make the frontend use real backend S2 counts

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/tests/apiContracts.test.ts`

- [ ] **Step 1: Write the failing contract test for `createRuns()`**

Add to `apps/web/tests/apiContracts.test.ts`:

```ts
test('createRuns maps pipeline run start response into run create result', async () => {
  mockFetch(() => ({
    pipeline_run_id: 'run-1',
    requested_count: 3,
    reused_count: 0,
    queued_count: 2,
    skipped_count: 1,
    failed_count: 0,
  }))

  const result = await createRuns({
    campaign_id: 'camp-1',
    prompt_id: 'prompt-1',
    scope: 'selected',
    company_ids: ['c1', 'c2', 'c3'],
  })

  assert.equal(result.requested_count, 3)
  assert.equal(result.queued_count, 2)
  assert.deepEqual(result.skipped_company_ids, [])
  assert.equal(result.runs.length, 1)
  assert.equal(result.runs[0]?.id, 'run-1')
})
```

- [ ] **Step 2: Run the contract test**

Run:

```bash
npm test -- --runInBand apps/web/tests/apiContracts.test.ts
```

Expected: fail because `createRuns()` still returns placeholder `runs: []`.

- [ ] **Step 3: Update `createRuns()`**

In `apps/web/src/lib/api.ts`, replace `createRuns()` with:

```ts
export async function createRuns(payload: RunCreateRequest): Promise<RunCreateResult> {
  const response = await startPipelineRun({
    campaign_id: payload.campaign_id,
    company_ids: payload.company_ids,
    analysis_prompt_snapshot: { prompt_id: payload.prompt_id },
  })
  return {
    requested_count: response.requested_count,
    queued_count: response.queued_count,
    skipped_company_ids: [],
    runs: [
      {
        id: response.pipeline_run_id,
        company_id: '',
        prompt_id: payload.prompt_id,
        status: response.failed_count > 0 ? 'failed' : response.queued_count > 0 ? 'queued' : 'skipped',
        created_at: new Date().toISOString(),
      },
    ],
  }
}
```

This is intentionally minimal. The UI only needs a non-empty run list and truthful queue counts.

- [ ] **Step 4: Re-run the frontend contract test**

Run:

```bash
npm test -- --runInBand apps/web/tests/apiContracts.test.ts
```

Expected: pass.

---

## Task 5: Run focused verification

**Files:**
- Test: `tests/test_pipeline_runs.py`
- Test: `tests/test_procrastinate_queue_architecture.py`
- Test: `apps/web/tests/apiContracts.test.ts`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
uv run pytest \
  tests/test_pipeline_runs.py \
  tests/test_procrastinate_queue_architecture.py::test_run_ai_decision_calls_analysis_service \
  tests/test_prompt_library.py \
  -q
```

Expected: pass.

- [ ] **Step 2: Run focused frontend contract tests**

Run:

```bash
cd apps/web && npm test -- --runInBand tests/apiContracts.test.ts
```

Expected: pass.

- [ ] **Step 3: Run a FastAPI import smoke test**

Run:

```bash
uv run python -c "from app.main import create_app; create_app(); print('OK')"
```

Expected output:

```text
OK
```

- [ ] **Step 4: Commit**

```bash
git add app/api/routes/pipeline_runs.py app/main.py app/jobs/ai_decision.py tests/test_pipeline_runs.py tests/test_procrastinate_queue_architecture.py apps/web/src/lib/api.ts apps/web/tests/apiContracts.test.ts docs/plans/2026-05-01-manual-s2-ai-decision-design.md docs/superpowers/plans/2026-05-01-manual-s2-ai-decision.md
git commit -m "plan: restore manual s2 ai decision flow"
```

---

## Self-review

Spec coverage:

- matching criteria -> covered by campaign selection plus backend `latest_usable_scrape()` eligibility
- prompt CRUD -> preserved; no rewrite required
- trigger AI decision -> covered by `POST /v1/pipeline-runs/start`
- frontend progress -> covered by `GET /v1/pipeline-runs/{id}/progress`
- procrastinate worker -> covered by `app/jobs/ai_decision.py`

Placeholder scan:

- no `TODO`
- no undefined file paths
- no implied-but-unspecified task bodies

Type consistency:

- `PipelineRunStartRequest.analysis_prompt_snapshot.prompt_id` is the prompt selector throughout
- `PipelineRunStartResponse.pipeline_run_id` feeds `RunCreateResult.runs[0].id`
- `AnalysisJobState` strings are the source of analysis progress aggregation
