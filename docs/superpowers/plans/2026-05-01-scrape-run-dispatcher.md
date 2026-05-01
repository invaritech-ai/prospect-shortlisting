# ScrapeRun Bulk Dispatcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /v1/companies/scrape-selected` returns in < 200 ms for any selection size; a background Procrastinate dispatcher does the actual job-creation in batches, resumably, with correct state transitions.

**Architecture:** Three phases. Phase A fixes correctness bugs in the already-scaffolded dispatcher. Phase B adds a composite index and migrates `scrape-all` onto the same pattern. Phase C adds filter-based selection so the frontend never fetches tens-of-thousands of IDs just to send them back.

**Tech Stack:** FastAPI, SQLModel, Procrastinate (PostgreSQL-backed), Alembic, SQLite (tests), React/TypeScript (frontend)

---

## Context: what already exists

The engineer already scaffolded the skeleton. Most files are in place. The bugs are surgical.

| File | State |
|---|---|
| `app/models/scrape.py` | Has `ScrapeRun`, `ScrapeRunItem`, `ScrapeRunStatus`, `ScrapeRunItemStatus` — **missing `JOB_CREATED`** |
| `app/jobs/scrape.py` | Has `dispatch_scrape_run` and `defer_scrape_website_bulk` — **3 bugs** |
| `app/api/routes/companies.py` | `scrape_selected_companies` rewritten to accept-and-defer — **missing ID scope validation** |
| `app/api/routes/scrape_runs.py` | `GET /v1/scrape-runs/{run_id}` — correct, done |
| `app/api/schemas/scrape.py` | `ScrapeRunRead` — correct, done |
| `app/main.py` | `scrape_runs_router` registered — done |
| `alembic/versions/e0f2a8c9d7b1_add_scrape_run_tables.py` | Migration exists and is applied |
| `tests/test_scrape_run.py` | Tests exist but some will fail due to bugs |
| `apps/web/src/lib/api.ts` | `scrapeSelectedCompanies` already returns `ScrapeRunRead` |
| `apps/web/src/lib/types.ts` | `ScrapeRunRead` type exists |

## File map

```
app/models/scrape.py                      — add JOB_CREATED status (Phase A)
app/jobs/scrape.py                        — fix 3 bugs in dispatcher (Phase A)
app/api/routes/companies.py               — add ID scope validation (Phase A); rewrite scrape-all (Phase B); add scrape-matching (Phase C)
app/api/schemas/upload.py                 — add CompanyScrapeByFiltersRequest (Phase C)
tests/test_scrape_run.py                  — fix + extend tests (all phases)
alembic/versions/<hash>_scrape_run_...    — Phase B: composite index migration
apps/web/src/lib/api.ts                   — Phase B: scrapeAllCompanies returns ScrapeRunRead; Phase C: scrapeMatchingCompanies
apps/web/src/lib/types.ts                 — Phase C: CompanyScrapeByFiltersRequest type
apps/web/src/hooks/usePipelineViews.ts    — Phase C: replace select-all + scrape flow
```

---

## Phase A — Correctness

**Three bugs to fix + one missing validation.**

### Bug 1: No `JOB_CREATED` intermediate state

**The problem:** The dispatcher calls `create_job()` (creates a `ScrapeJob` row), immediately sets `item.status = QUEUED`, commits, then calls `defer_scrape_website_bulk`. If the defer fails, the item is stuck in `QUEUED` with no live Procrastinate task — the job will never run.

**The fix:** Add `JOB_CREATED` status. Set it after `create_job`, commit, then try to defer. Only update to `QUEUED` after a successful defer. On retry, the dispatcher re-fetches `PENDING | JOB_CREATED` items; for `JOB_CREATED` items it skips `create_job` (already done) and only retries the defer.

### Bug 2: `schedule_in` passed as task kwarg instead of via `.configure()`

**The problem:**
```python
# WRONG — schedule_in is not a task parameter
await dispatch_scrape_run.defer_async(run_id=run_id, schedule_in={"seconds": 60})
```
Procrastinate silently ignores or errors on unknown kwargs. The scheduled delay is lost.

**The fix:**
```python
# CORRECT
await dispatch_scrape_run.configure(schedule_in={"seconds": 60}).defer_async(run_id=run_id)
```

### Bug 3: `defer_scrape_website_bulk` swallows per-item defer errors

**The problem:** Uses `asyncio.gather()` without `return_exceptions=True`. If any single `defer_async` call fails, the entire gather raises and the caller loses track of which defers succeeded.

**The fix:** Inline the defer loop in the dispatcher with `return_exceptions=True`; update each item to `QUEUED` only if its defer succeeded; leave `JOB_CREATED` if it failed (will be retried).

### Missing: ID scope validation → 400

**The problem:** `scrape_selected_companies` accepts any list of UUIDs and blindly creates run items, even for IDs from other campaigns.

**The fix:** Before creating the run, query `Company JOIN Upload WHERE upload.campaign_id = payload.campaign_id` (and `upload.id = payload.upload_id` if set). If any submitted ID is not in the result, return 400 with the list of invalid IDs.

---

### Task A1: Add `JOB_CREATED` status to the model

**Files:**
- Modify: `app/models/scrape.py`

- [ ] **Step 1: Add `JOB_CREATED` to the enum**

In `app/models/scrape.py`, change `ScrapeRunItemStatus`:

```python
class ScrapeRunItemStatus(StrEnum):
    PENDING     = "pending"
    JOB_CREATED = "job_created"   # ScrapeJob row exists; defer not yet attempted
    QUEUED      = "queued"
    SKIPPED     = "skipped"
    FAILED      = "failed"
```

- [ ] **Step 2: Verify tests still import cleanly**

```bash
uv run python -c "from app.models.scrape import ScrapeRunItemStatus; print(list(ScrapeRunItemStatus))"
```

Expected output includes `job_created`.

---

### Task A2: Fix `_pending_stmt` to include `JOB_CREATED` items

**Files:**
- Modify: `app/jobs/scrape.py`

- [ ] **Step 1: Update `_pending_stmt`**

```python
def _pending_stmt(engine: Engine, run_id: UUID):
    stmt = (
        select(ScrapeRunItem)
        .where(
            col(ScrapeRunItem.run_id) == run_id,
            col(ScrapeRunItem.status).in_([
                ScrapeRunItemStatus.PENDING,
                ScrapeRunItemStatus.JOB_CREATED,
            ]),
        )
        .order_by(col(ScrapeRunItem.created_at), col(ScrapeRunItem.id))
    )
    if engine.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    stmt = stmt.limit(DISPATCH_BATCH_SIZE)
    return stmt
```

---

### Task A3: Fix the dispatcher state machine (3 bugs)

**Files:**
- Modify: `app/jobs/scrape.py`

Replace the `dispatch_scrape_run` function body entirely. Here is the complete corrected function:

- [ ] **Step 1: Replace `dispatch_scrape_run` with the corrected version**

```python
@app.task(
    name="dispatch_scrape_run",
    queue="scrape",
    retry=RetryStrategy(max_attempts=5, wait=30),
)
async def dispatch_scrape_run(run_id: str) -> None:
    engine = get_engine()
    run_uuid = UUID(run_id)

    with Session(engine) as session:
        row = session.get(ScrapeRun, run_uuid)
        if row is None or row.status in (ScrapeRunStatus.COMPLETED, ScrapeRunStatus.FAILED):
            return
        row.status = ScrapeRunStatus.DISPATCHING
        if row.started_at is None:
            row.started_at = utcnow()
        session.add(row)
        session.commit()

    while True:
        with Session(engine) as session:
            pending = list(session.exec(_pending_stmt(engine, run_uuid)))

            if not pending:
                run = session.get(ScrapeRun, run_uuid)
                if run is not None and run.status != ScrapeRunStatus.FAILED:
                    run.status = ScrapeRunStatus.COMPLETED
                    run.finished_at = utcnow()
                    session.add(run)
                    session.commit()
                return

            slots = available_slots(engine, "scrape", len(pending))
            if slots == 0:
                # Bug 2 fix: use .configure() for schedule_in, not a kwarg
                await dispatch_scrape_run.configure(
                    schedule_in={"seconds": 60}
                ).defer_async(run_id=run_id)
                return

            batch = pending[:slots]
            run_row = session.get(ScrapeRun, run_uuid)
            scrape_rules_val = run_row.scrape_rules if run_row else None

            cids = [item.company_id for item in batch]
            companies_by_id = {
                c.id: c
                for c in session.exec(
                    select(Company).where(col(Company.id).in_(cids))
                ).all()
            }

            now_ts = utcnow()
            # Map job_id → item for post-defer status update (Bug 1 fix)
            job_id_to_item: dict[UUID, ScrapeRunItem] = {}
            skipped_inc = failed_inc = 0

            for item in batch:
                if item.scrape_job_id is not None:
                    # Resume case: job already created, only need to defer
                    job_id_to_item[item.scrape_job_id] = item
                    continue

                company = companies_by_id.get(item.company_id)
                if company is None:
                    item.status = ScrapeRunItemStatus.FAILED
                    item.error_code = "company_not_found"
                    item.updated_at = now_ts
                    session.add(item)
                    failed_inc += 1
                    continue

                try:
                    with session.begin_nested():
                        job = _manager.create_job(
                            session=session,
                            website_url=company.normalized_url,
                            js_fallback=True,
                            include_sitemap=True,
                            general_model=DEFAULT_GENERAL_MODEL,
                            classify_model=DEFAULT_CLASSIFY_MODEL,
                        )
                    # Bug 1 fix: JOB_CREATED, not QUEUED — defer hasn't happened yet
                    item.scrape_job_id = job.id
                    item.status = ScrapeRunItemStatus.JOB_CREATED
                    item.updated_at = now_ts
                    session.add(item)
                    job_id_to_item[job.id] = item
                except (ScrapeJobAlreadyRunningError, CircuitBreakerOpenError, ValueError) as exc:
                    item.status = ScrapeRunItemStatus.SKIPPED
                    item.error_code = type(exc).__name__
                    item.updated_at = now_ts
                    session.add(item)
                    skipped_inc += 1

            # Commit JOB_CREATED / SKIPPED / FAILED before attempting defers
            session.commit()

        if not job_id_to_item:
            # All items in this batch were skipped/failed; update run counters and loop
            with Session(engine) as session:
                run = session.get(ScrapeRun, run_uuid)
                if run is not None:
                    run.skipped_count += skipped_inc
                    run.failed_count += failed_inc
                    session.add(run)
                    session.commit()
            continue

        # Bug 3 fix: per-item defer with return_exceptions=True
        task = scrape_website.configure(priority=BULK_USER)
        job_ids = list(job_id_to_item.keys())
        results = await asyncio.gather(
            *(
                task.defer_async(job_id=str(jid), scrape_rules=scrape_rules_val)
                for jid in job_ids
            ),
            return_exceptions=True,
        )

        queued_inc = 0
        defer_failed_count = 0
        with Session(engine) as session:
            now_ts = utcnow()
            for jid, result in zip(job_ids, results):
                item = job_id_to_item[jid]
                # Reload item in this new session
                db_item = session.get(ScrapeRunItem, item.id)
                if db_item is None:
                    continue
                if isinstance(result, Exception):
                    # Leave JOB_CREATED — will be retried on next dispatch
                    logger.warning("defer failed for job %s: %s", jid, result)
                    defer_failed_count += 1
                else:
                    db_item.status = ScrapeRunItemStatus.QUEUED
                    db_item.updated_at = now_ts
                    session.add(db_item)
                    queued_inc += 1

            run = session.get(ScrapeRun, run_uuid)
            if run is not None:
                run.queued_count += queued_inc
                run.skipped_count += skipped_inc
                run.failed_count += failed_inc
                session.add(run)
            session.commit()

        if defer_failed_count > 0:
            logger.warning(
                "dispatch_scrape_run %s: %d defer(s) failed; items left in job_created for retry",
                run_id,
                defer_failed_count,
            )
```

---

### Task A4: Add ID scope validation to `scrape_selected_companies`

**Files:**
- Modify: `app/api/routes/companies.py`

- [ ] **Step 1: Add the scope check**

Replace the body of `scrape_selected_companies` up to the `ScrapeRun` creation. Add imports `from fastapi import HTTPException` (already present) and ensure `Upload` is imported (already is).

Replace from `company_ids = payload.company_ids` down to `session.add(run)`:

```python
    company_ids = payload.company_ids
    scrape_rules_kw = payload.scrape_rules.model_dump() if payload.scrape_rules else None

    # Validate all submitted IDs belong to this campaign (and upload if scoped).
    # 400 rather than silent drop: the user must know if their selection was stale.
    scope_q = (
        select(col(Company.id))
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(col(Upload.campaign_id) == payload.campaign_id)
    )
    if payload.upload_id is not None:
        scope_q = scope_q.where(col(Upload.id) == payload.upload_id)
    authorized = {row for row in session.exec(scope_q)}
    invalid = [cid for cid in company_ids if cid not in authorized]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "company_ids_out_of_scope",
                "invalid_ids": [str(i) for i in invalid],
            },
        )

    run = ScrapeRun(
        campaign_id=payload.campaign_id,
        requested_count=len(company_ids),
        scrape_rules=scrape_rules_kw,
    )
```

The rest of the function (add items, commit, defer, return) stays exactly as is.

Also add the missing import at the top of `companies.py` if not present:

```python
from app.models.scrape import ScrapeRun, ScrapeRunItem
from app.api.schemas.scrape import ScrapeRunRead
```

---

### Task A5: Fix and extend tests

**Files:**
- Modify: `tests/test_scrape_run.py`

- [ ] **Step 1: Fix `test_dispatcher_respects_backpressure`**

The existing test patches `dispatch_scrape_run.defer_async` directly, but the fixed code calls `dispatch_scrape_run.configure(...).defer_async(...)`. Patch `configure` instead:

```python
@pytest.mark.asyncio
async def test_dispatcher_respects_backpressure(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.jobs import scrape as scrape_mod

    monkeypatch.setattr(scrape_mod, "get_engine", lambda: sqlite_session.get_bind())
    bulk_calls: list[int] = []
    configure_kwargs: list[dict] = []
    defer_kwargs: list[dict] = []

    class FakeConfigured:
        async def defer_async(self, **kw):
            defer_kwargs.append(kw)

    def fake_configure(**kw):
        configure_kwargs.append(kw)
        return FakeConfigured()

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "configure", fake_configure)

    async def fake_bulk(*, priority: int, job_ids: list, scrape_rules):  # noqa: ARG001
        bulk_calls.append(len(job_ids))

    monkeypatch.setattr(scrape_mod, "defer_scrape_website_bulk", fake_bulk)
    monkeypatch.setattr(scrape_mod, "available_slots", lambda *_a, **_k: 0)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape Run Backpressure"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    c = _seed_company(sqlite_session, upload_id=upload.id, domain="bp.example")
    run = ScrapeRun(campaign_id=campaign.id, requested_count=1)
    sqlite_session.add(run)
    sqlite_session.flush()
    sqlite_session.add(ScrapeRunItem(run_id=run.id, company_id=c.id))
    sqlite_session.commit()

    await scrape_mod.dispatch_scrape_run(str(run.id))

    assert bulk_calls == []
    assert len(configure_kwargs) == 1
    assert configure_kwargs[0] == {"schedule_in": {"seconds": 60}}
    assert len(defer_kwargs) == 1
    assert defer_kwargs[0] == {"run_id": str(run.id)}
```

- [ ] **Step 2: Fix `test_dispatcher_is_resumable` to use `JOB_CREATED` items**

The existing test pre-seeds 20 `QUEUED` items (already done). Update to also test `JOB_CREATED` resumption (has `scrape_job_id` but not yet deferred):

```python
@pytest.mark.asyncio
async def test_dispatcher_resumes_job_created_items(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Items in JOB_CREATED state (job exists, defer failed) are re-deferred without creating new jobs."""
    from app.jobs import scrape as scrape_mod
    from app.models.scrape import ScrapeRunItemStatus

    monkeypatch.setattr(scrape_mod, "get_engine", lambda: sqlite_session.get_bind())
    monkeypatch.setattr(scrape_mod, "available_slots", lambda _e, _q, r: r)

    deferred_job_ids: list[str] = []

    async def fake_bulk(*, priority, job_ids, scrape_rules):  # noqa: ARG001
        deferred_job_ids.extend(str(j) for j in job_ids)

    monkeypatch.setattr(scrape_mod, "defer_scrape_website_bulk", fake_bulk)

    campaign = create_campaign(
        payload=CampaignCreate(name="Resume JOB_CREATED"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    c = _seed_company(sqlite_session, upload_id=upload.id, domain="jc.example")

    # Pre-create a ScrapeJob to simulate a prior partial run
    from app.models.scrape import ScrapeJob
    existing_job = ScrapeJob(
        website_url="https://jc.example",
        normalized_url="https://jc.example",
        domain="jc.example",
    )
    sqlite_session.add(existing_job)
    sqlite_session.flush()

    run = ScrapeRun(campaign_id=campaign.id, requested_count=1)
    sqlite_session.add(run)
    sqlite_session.flush()
    item = ScrapeRunItem(
        run_id=run.id,
        company_id=c.id,
        scrape_job_id=existing_job.id,
        status=ScrapeRunItemStatus.JOB_CREATED,
    )
    sqlite_session.add(item)
    sqlite_session.commit()

    before_jobs = _count_scrape_jobs(sqlite_session)
    await scrape_mod.dispatch_scrape_run(str(run.id))

    # No new ScrapeJob rows created — only the existing one was deferred
    assert _count_scrape_jobs(sqlite_session) == before_jobs
    assert str(existing_job.id) in deferred_job_ids

    sqlite_session.expire_all()
    updated_item = sqlite_session.get(ScrapeRunItem, item.id)
    assert updated_item.status == ScrapeRunItemStatus.QUEUED
```

- [ ] **Step 3: Add test for out-of-scope company IDs → 400**

```python
@pytest.mark.asyncio
async def test_scrape_selected_rejects_out_of_scope_ids(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import companies as companies_route

    async def fake_dispatch(*_a, **_k):
        pass

    monkeypatch.setattr(scrape_mod_ref := __import__("app.jobs.scrape", fromlist=["dispatch_scrape_run"]).dispatch_scrape_run, "defer_async", fake_dispatch)

    campaign_a = create_campaign(payload=CampaignCreate(name="Camp A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Camp B"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="a.example")
    company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="b.example")
    sqlite_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await companies_route.scrape_selected_companies(
            payload=CompanyScrapeRequest(
                campaign_id=campaign_a.id,
                company_ids=[company_a.id, company_b.id],  # company_b is from campaign_b
            ),
            session=sqlite_session,
        )

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["code"] == "company_ids_out_of_scope"
    assert str(company_b.id) in detail["invalid_ids"]
```

- [ ] **Step 4: Run all scrape_run tests**

```bash
uv run pytest tests/test_scrape_run.py -v
```

Expected: all pass.

- [ ] **Step 5: Run ruff on changed files**

```bash
uv run ruff check app/models/scrape.py app/jobs/scrape.py app/api/routes/companies.py tests/test_scrape_run.py
```

Expected: no errors.

- [ ] **Step 6: Commit Phase A**

```bash
git add app/models/scrape.py app/jobs/scrape.py app/api/routes/companies.py tests/test_scrape_run.py
git commit -m "fix(scrape-run): correct dispatcher state machine, schedule_in, and ID scope validation"
```

---

## Phase B — Index + scrape-all migration

### Task B1: Composite index migration

**Files:**
- Create: `alembic/versions/<new>_scrape_run_items_composite_index.py`

- [ ] **Step 1: Generate migration**

```bash
uv run alembic revision -m "scrape_run_items_composite_index"
```

- [ ] **Step 2: Edit the generated file**

```python
def upgrade() -> None:
    op.create_index(
        "ix_scrape_run_items_run_status_created_id",
        "scrape_run_items",
        ["run_id", "status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scrape_run_items_run_status_created_id", table_name="scrape_run_items")
```

- [ ] **Step 3: Apply migration**

```bash
uv run alembic upgrade head
```

Expected: no error.

---

### Task B2: Rewrite `scrape_all_companies` to use ScrapeRun

**Files:**
- Modify: `app/api/routes/companies.py`

- [ ] **Step 1: Replace `scrape_all_companies`**

```python
@router.post("/companies/scrape-all", response_model=ScrapeRunRead)
async def scrape_all_companies(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> ScrapeRunRead:
    """Queue scrape for every company in the campaign with no active job.

    Returns a ScrapeRun immediately; a dispatcher task creates individual jobs in batches.
    """
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=None)

    active_subq = (
        select(col(ScrapeJob.domain))
        .where(col(ScrapeJob.terminal_state).is_(False))
        .scalar_subquery()
    )
    company_ids = list(
        session.exec(
            select(col(Company.id))
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == campaign_id,
                col(Company.domain).not_in(active_subq),
            )
        ).all()
    )

    run = ScrapeRun(
        campaign_id=campaign_id,
        requested_count=len(company_ids),
    )
    session.add(run)
    session.add_all([ScrapeRunItem(run_id=run.id, company_id=cid) for cid in company_ids])
    session.commit()
    session.refresh(run)

    await dispatch_scrape_run.defer_async(run_id=str(run.id))
    return ScrapeRunRead.model_validate(run, from_attributes=True)
```

Add `dispatch_scrape_run` to the imports from `app.jobs.scrape` (it's likely already imported; double-check).

Remove `current_depth`, `available_slots`, `_scrape_manager`, `CompanyScrapeResult`, `CompanyScrapeAllRequest` from companies.py imports if they're now unused (check first with `grep`).

- [ ] **Step 2: Update frontend — `scrapeAllCompanies` return type**

In `apps/web/src/lib/api.ts`, change:

```typescript
export async function scrapeAllCompanies(
  options: { uploadId?: string; idempotencyKey?: string; scrapeRules?: ScrapeRules } = {},
): Promise<ScrapeRunRead> {
  return request<ScrapeRunRead>('/v1/companies/scrape-all', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.idempotencyKey ? { 'X-Idempotency-Key': options.idempotencyKey } : {}),
    },
    body: JSON.stringify({
      upload_id: options.uploadId,
      scrape_rules: options.scrapeRules,
    }),
  })
}
```

- [ ] **Step 3: Fix call sites in `usePipelineViews.ts` that use `CompanyScrapeResult` fields from `scrapeAllCompanies`**

Search: `grep -n "scrapeAllCompanies" apps/web/src/hooks/usePipelineViews.ts`

For any toast/notice that reads `result.queued_count` or `result.requested_count`, update to use `result.requested_count` (the run is accepted, not yet queued). Example:

```typescript
setNotice(`Accepted ${result.requested_count.toLocaleString()} companies for scraping.`)
```

- [ ] **Step 4: Build frontend**

```bash
cd apps/web && npm run build
```

Expected: no type errors.

- [ ] **Step 5: Add tests**

Add to `tests/test_scrape_run.py`:

```python
@pytest.mark.asyncio
async def test_scrape_all_returns_scrape_run(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import companies as companies_route
    from app.jobs import scrape as scrape_mod

    dispatched: list[dict] = []

    async def fake_dispatch(**kw):
        dispatched.append(kw)

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "defer_async", fake_dispatch)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape All Run"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    companies = [
        _seed_company(sqlite_session, upload_id=upload.id, domain=f"sa{i}.example")
        for i in range(4)
    ]
    sqlite_session.commit()
    before_jobs = _count_scrape_jobs(sqlite_session)

    result = await companies_route.scrape_all_companies(
        campaign_id=campaign.id,
        session=sqlite_session,
    )

    assert result.status == "accepted"
    assert result.requested_count == 4
    assert _count_scrape_jobs(sqlite_session) == before_jobs  # no jobs created synchronously
    assert len(dispatched) == 1
    items = list(sqlite_session.exec(
        select(ScrapeRunItem).where(ScrapeRunItem.run_id == result.id)
    ))
    assert len(items) == 4
```

- [ ] **Step 6: Run tests + ruff**

```bash
uv run pytest tests/test_scrape_run.py -v
uv run ruff check app/api/routes/companies.py apps/web/src/lib/api.ts tests/test_scrape_run.py
```

- [ ] **Step 7: Commit Phase B**

```bash
git add alembic/versions/ app/api/routes/companies.py apps/web/src/lib/api.ts apps/web/src/hooks/usePipelineViews.ts tests/test_scrape_run.py
git commit -m "feat(scrape-run): composite index + migrate scrape-all onto ScrapeRun dispatcher"
```

---

## Phase C — Filter-based selection

**Goal:** Replace the "fetch all IDs → POST scrape-selected" round-trip with a single `POST /v1/companies/scrape-matching` that accepts filter params server-side. Eliminates O(N) ID payloads.

### Task C1: Add `CompanyScrapeByFiltersRequest` schema

**Files:**
- Modify: `app/api/schemas/upload.py`

- [ ] **Step 1: Add the schema**

```python
class CompanyScrapeByFiltersRequest(BaseModel):
    campaign_id: UUID
    upload_id: UUID | None = None
    scrape_rules: ScrapeRules | None = None
    decision_filter: str = "all"
    scrape_filter: str = "all"
    stage_filter: str = "all"
    status_filter: str = "all"
    letter: str | None = None
    letters: list[str] | None = None
    search: str | None = Field(default=None, max_length=200)
```

---

### Task C2: Add `POST /v1/companies/scrape-matching` endpoint

**Files:**
- Modify: `app/api/routes/companies.py`

- [ ] **Step 1: Add the endpoint**

```python
@router.post("/companies/scrape-matching", response_model=ScrapeRunRead)
async def scrape_matching_companies(
    payload: CompanyScrapeByFiltersRequest,
    session: Session = Depends(get_session),
) -> ScrapeRunRead:
    """Create a ScrapeRun for all companies matching the given filters.

    Uses INSERT-SELECT to materialise run items in one query — no Python loop over IDs.
    The dispatcher processes items in controlled batches independently.
    """
    validate_campaign_upload_scope(
        session=session,
        campaign_id=payload.campaign_id,
        upload_id=payload.upload_id,
    )
    filters = validate_company_filters(
        decision_filter=payload.decision_filter,
        scrape_filter=payload.scrape_filter,
        stage_filter=payload.stage_filter,
        status_filter=payload.status_filter,
        search=payload.search,
        letter=payload.letter,
        letters=payload.letters,
        upload_id=payload.upload_id,
    )
    scrape_rules_kw = payload.scrape_rules.model_dump() if payload.scrape_rules else None

    ctx = build_company_query_context()

    # COUNT — how many will be accepted
    count_stmt = (
        build_company_count_stmt(ctx)
        .where(col(Upload.campaign_id) == payload.campaign_id)
    )
    count_stmt = apply_company_filters(count_stmt, filters, ctx)
    requested_count = session.exec(count_stmt).one()

    run = ScrapeRun(
        campaign_id=payload.campaign_id,
        requested_count=requested_count,
        scrape_rules=scrape_rules_kw,
    )
    session.add(run)
    session.flush()  # get run.id before INSERT-SELECT

    # INSERT-SELECT: materialise run items in one statement (no Python loop)
    id_stmt = (
        select(col(Company.id))
        .select_from(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .outerjoin(ctx.latest_classification, ctx.latest_classification.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_scrape, ctx.latest_scrape.c.normalized_url == col(Company.normalized_url))
        .outerjoin(ctx.latest_analysis, ctx.latest_analysis.c.company_id == col(Company.id))
        .outerjoin(ctx.latest_contact_fetch, ctx.latest_contact_fetch.c.company_id == col(Company.id))
        .outerjoin(CompanyFeedback, col(CompanyFeedback.company_id) == col(Company.id))
        .where(col(Upload.campaign_id) == payload.campaign_id)
    )
    id_stmt = apply_company_filters(id_stmt, filters, ctx)

    from sqlalchemy import insert
    from app.models.scrape import ScrapeRunItem as ScrapeRunItemTable

    session.execute(
        insert(ScrapeRunItemTable).from_select(
            ["company_id"],
            id_stmt,
        ).values(
            run_id=run.id,
            status=ScrapeRunItemStatus.PENDING,
        )
    )
    session.commit()
    session.refresh(run)

    await dispatch_scrape_run.defer_async(run_id=str(run.id))
    return ScrapeRunRead.model_validate(run, from_attributes=True)
```

Add `CompanyScrapeByFiltersRequest` to the imports in companies.py from `app.api.schemas.upload`.

**Note on INSERT-SELECT syntax:** SQLAlchemy's `insert().from_select()` requires the column list to match the SELECT columns exactly. `ScrapeRunItem` has more columns (`id`, `run_id`, `status`, `error_code`, `created_at`, `updated_at`) with defaults. Since we can only set `company_id` via INSERT-SELECT, the other columns must have DB-level defaults. Verify `id` is a UUID with a server default or generate via Python. If not, fall back to a batched Python loop with `session.add_all` in chunks of 500 — correctness over cleverness.

**Fallback if INSERT-SELECT doesn't work with SQLModel/SQLite (tests):**

```python
# Fallback: chunked Python insert (works on all dialects)
company_ids = list(session.exec(id_stmt))
CHUNK = 500
for i in range(0, len(company_ids), CHUNK):
    session.add_all([
        ScrapeRunItem(run_id=run.id, company_id=cid)
        for cid in company_ids[i:i + CHUNK]
    ])
    session.flush()
run.requested_count = len(company_ids)  # re-set accurate count
```

Use this fallback if INSERT-SELECT runs into dialect issues. It's still far faster than loading companies into Python objects.

---

### Task C3: Update frontend — replace ID-fetch + scrape-selected with scrape-matching

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/lib/types.ts`
- Modify: `apps/web/src/hooks/usePipelineViews.ts`

- [ ] **Step 1: Add `CompanyScrapeByFiltersRequest` type and `scrapeMatchingCompanies` to `api.ts`**

In `apps/web/src/lib/types.ts`:

```typescript
export type CompanyScrapeByFiltersRequest = {
  campaign_id: string
  upload_id?: string
  scrape_rules?: ScrapeRules
  decision_filter?: string
  scrape_filter?: string
  stage_filter?: string
  status_filter?: string
  letter?: string | null
  letters?: string[]
  search?: string | null
}
```

In `apps/web/src/lib/api.ts`:

```typescript
export async function scrapeMatchingCompanies(
  payload: CompanyScrapeByFiltersRequest,
): Promise<ScrapeRunRead> {
  return request<ScrapeRunRead>('/v1/companies/scrape-matching', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
```

- [ ] **Step 2: Replace `selectAllMatchingAsync` → scrape flow in `usePipelineViews.ts`**

Find `scrapeSelectedAsync` (the "select all matching" + scrape path). Currently it calls `listCompanyIds` then stores IDs then `scrapeSelectedCompanies`. Replace with a direct `scrapeMatchingCompanies` call using the current filter state.

Locate the "select all matching → scrape" button handler. Add a new `scrapeAllMatchingAsync` callback:

```typescript
const scrapeAllMatchingAsync = useCallback(async () => {
  if (!selectedCampaignId) return
  const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
  if (query === null) return
  setError('')
  setNotice('')
  setIsPipelineScraping(true)
  try {
    const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
    const letters = [...pipelineActiveLetters]
    const result = await scrapeMatchingCompanies({
      campaign_id: selectedCampaignId,
      decision_filter: query.decisionFilter,
      scrape_filter: sf,
      stage_filter: query.stageFilter,
      letters: letters.length > 0 ? letters : undefined,
      status_filter: 'all',
      search: pipelineSearch || undefined,
      scrape_rules: selectedScrapePrompt?.scrape_rules_structured ?? undefined,
    })
    setNotice(
      `Accepted ${result.requested_count.toLocaleString()} compan${result.requested_count === 1 ? 'y' : 'ies'} for scraping.`,
    )
    setPipelineSelectedIds([])
  } catch (err) {
    setError(parseApiError(err))
  } finally {
    setIsPipelineScraping(false)
  }
}, [activeView, pipelineActiveLetters, pipelineDecisionFilter, pipelineScrapeSubFilter, pipelineSearch, selectedCampaignId, selectedScrapePrompt, setError, setNotice])
```

Wire the "scrape all matching" SelectionBar button to `scrapeAllMatchingAsync` instead of the old `selectAllMatchingAsync` → `scrapeSelected` chain.

Keep `scrapeSelectedAsync` (explicit IDs) for the per-row and partial-selection scrape buttons.

- [ ] **Step 3: Build frontend**

```bash
cd apps/web && npm run build
```

Expected: no type errors.

- [ ] **Step 4: Add tests**

Add to `tests/test_scrape_run.py`:

```python
@pytest.mark.asyncio
async def test_scrape_matching_creates_run_from_filters(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import companies as companies_route
    from app.api.schemas.upload import CompanyScrapeByFiltersRequest
    from app.jobs import scrape as scrape_mod

    dispatched: list[dict] = []

    async def fake_dispatch(**kw):
        dispatched.append(kw)

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "defer_async", fake_dispatch)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape Matching"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    companies = [
        _seed_company(sqlite_session, upload_id=upload.id, domain=f"fm{i}.example")
        for i in range(7)
    ]
    sqlite_session.commit()
    before_jobs = _count_scrape_jobs(sqlite_session)

    result = await companies_route.scrape_matching_companies(
        payload=CompanyScrapeByFiltersRequest(campaign_id=campaign.id),
        session=sqlite_session,
    )

    assert result.status == "accepted"
    assert result.requested_count == 7
    assert _count_scrape_jobs(sqlite_session) == before_jobs
    assert len(dispatched) == 1
    items = list(sqlite_session.exec(
        select(ScrapeRunItem).where(ScrapeRunItem.run_id == result.id)
    ))
    assert len(items) == 7
```

- [ ] **Step 5: Run tests + ruff + build**

```bash
uv run pytest tests/test_scrape_run.py -v
uv run ruff check app/api/routes/companies.py app/api/schemas/upload.py tests/test_scrape_run.py
cd apps/web && npm run build
```

- [ ] **Step 6: Commit Phase C**

```bash
git add app/api/routes/companies.py app/api/schemas/upload.py \
        apps/web/src/lib/api.ts apps/web/src/lib/types.ts \
        apps/web/src/hooks/usePipelineViews.ts \
        tests/test_scrape_run.py
git commit -m "feat(scrape-run): filter-based scrape-matching endpoint + frontend flow"
```

---

## Self-review checklist

- [x] Bug 1 (JOB_CREATED): Task A1 adds enum, A2 fixes query, A3 fixes dispatcher  
- [x] Bug 2 (schedule_in): Task A3 uses `.configure()`; Task A5 fixes test  
- [x] Bug 3 (per-item defer errors): Task A3 inlines gather with `return_exceptions=True`  
- [x] Scope validation (400): Task A4  
- [x] Composite index: Task B1  
- [x] scrape-all migration: Task B2  
- [x] Frontend scrapeAllCompanies type: Task B2 step 2  
- [x] scrape-matching endpoint: Task C2  
- [x] INSERT-SELECT or chunked fallback: Task C2 — fallback documented  
- [x] Frontend filter-based flow: Task C3  
- [x] All phases have tests with exact code  
- [x] All phases have ruff + build verification steps  
- [x] All phases have commit steps  
