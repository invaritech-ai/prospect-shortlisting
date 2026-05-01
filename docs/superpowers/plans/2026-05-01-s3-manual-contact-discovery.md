# S3 Manual Contact Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the manual S3 vertical slice — enqueue endpoints, a real contact-fetch worker (Snov + Apollo), and the three read endpoints the frontend already calls.

**Architecture:** API creates a `ContactFetchBatch` + one `ContactFetchJob` per company (reusing any active job), defers a Procrastinate task, and returns counts. The worker runs Snov then Apollo, upserts `Contact` rows keyed by `(company_id, source_provider, provider_person_id)`, applies title-match rules on ingest, then closes the job. No pipeline-run orchestration in this pass.

**Tech Stack:** FastAPI, SQLModel, Procrastinate, SQLite (tests), pytest/pytest-asyncio, SnovClient, ApolloClient

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `app/services/contact_fetch_service.py` | **Create** | Enqueue logic + worker execution |
| `app/jobs/contact_fetch.py` | **Modify** | Change task signature; call service |
| `app/api/routes/companies.py` | **Modify** | Add `POST /{company_id}/fetch-contacts`, `POST /fetch-contacts-selected`, `GET /{company_id}/contacts` |
| `app/api/routes/contacts.py` | **Modify** | Add `GET /contacts/companies`, `GET /contacts/ids` |
| `tests/test_contact_fetch_service.py` | **Create** | Enqueue + worker unit tests |
| `tests/test_contact_fetch_api.py` | **Create** | API endpoint tests |

---

## Task 1 — Change the worker task signature

The current stub accepts `(company_id, campaign_id)`. The service pattern (matching S2) takes a single job ID so the worker is stateless.

**Files:**
- Modify: `app/jobs/contact_fetch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contact_fetch_service.py
from __future__ import annotations

import pytest


def test_fetch_contacts_task_accepts_job_id() -> None:
    from app.jobs.contact_fetch import fetch_contacts
    import inspect
    sig = inspect.signature(fetch_contacts.original_func if hasattr(fetch_contacts, "original_func") else fetch_contacts)
    assert "contact_fetch_job_id" in sig.parameters
    assert "company_id" not in sig.parameters
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_contact_fetch_service.py::test_fetch_contacts_task_accepts_job_id -v
```
Expected: FAIL — `company_id` found in parameters.

- [ ] **Step 3: Update `app/jobs/contact_fetch.py`**

```python
"""Procrastinate task: execute one ContactFetchJob."""
from __future__ import annotations

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app


@app.task(name="fetch_contacts", queue="contact_fetch")
async def fetch_contacts(contact_fetch_job_id: str) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    ContactFetchService().run_contact_fetch_job(
        engine=get_engine(),
        contact_fetch_job_id=contact_fetch_job_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_contact_fetch_service.py::test_fetch_contacts_task_accepts_job_id -v
```

- [ ] **Step 5: Commit**

```bash
git add app/jobs/contact_fetch.py tests/test_contact_fetch_service.py
git commit -m "feat(s3): change fetch_contacts task to accept contact_fetch_job_id"
```

---

## Task 2 — Enqueue service: single-company logic

Create `app/services/contact_fetch_service.py` with a method that creates a `ContactFetchBatch`, finds-or-creates a `ContactFetchJob`, and returns counts. Actual deferral happens in the API layer. `run_contact_fetch_job` is a stub here.

**Files:**
- Create: `app/services/contact_fetch_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contact_fetch_service.py  (add to existing file)
from uuid import uuid4
from sqlmodel import Session, select
from app.models import Campaign, Company, ContactFetchBatch, ContactFetchJob, Upload
from app.models.pipeline import ContactFetchJobState


def _seed_campaign(session: Session) -> Campaign:
    c = Campaign(name="test")
    session.add(c)
    session.flush()
    return c


def _seed_company(session: Session, campaign: Campaign) -> Company:
    u = Upload(campaign_id=campaign.id, filename="f.csv", checksum=str(uuid4()), row_count=1, valid_count=1, invalid_count=0)
    session.add(u)
    session.flush()
    co = Company(upload_id=u.id, raw_url="https://acme.com", normalized_url="https://acme.com", domain="acme.com")
    session.add(co)
    session.flush()
    return co


def test_enqueue_creates_batch_and_job(sqlite_session: Session) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    sqlite_session.commit()

    svc = ContactFetchService()
    batch, jobs, reused = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    sqlite_session.commit()

    assert batch.id is not None
    assert batch.campaign_id == campaign.id
    assert len(jobs) == 1
    assert jobs[0].company_id == company.id
    assert jobs[0].state == ContactFetchJobState.QUEUED
    assert reused == 0


def test_enqueue_reuses_active_job(sqlite_session: Session) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    sqlite_session.commit()

    svc = ContactFetchService()
    batch1, jobs1, _ = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, company_ids=[company.id], force_refresh=False)
    sqlite_session.commit()

    batch2, jobs2, reused = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, company_ids=[company.id], force_refresh=False)
    sqlite_session.commit()

    # second enqueue reuses the existing active job
    assert reused == 1
    assert len(jobs2) == 1
    assert jobs2[0].id == jobs1[0].id


def test_force_refresh_creates_new_job(sqlite_session: Session) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    sqlite_session.commit()

    svc = ContactFetchService()
    _, jobs1, _ = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, company_ids=[company.id], force_refresh=False)
    sqlite_session.commit()
    _, jobs2, reused = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, company_ids=[company.id], force_refresh=True)
    sqlite_session.commit()

    assert reused == 0
    assert jobs2[0].id != jobs1[0].id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_contact_fetch_service.py -k "test_enqueue" -v
```
Expected: FAIL — `ContactFetchService` not found.

- [ ] **Step 3: Create `app/services/contact_fetch_service.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Session, col, select

from app.models import Company, ContactFetchBatch, ContactFetchJob, Upload
from app.models.pipeline import ContactFetchBatchState, ContactFetchJobState

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _active_job_for_company(session: Session, company_id: UUID) -> ContactFetchJob | None:
    return session.exec(
        select(ContactFetchJob)
        .where(
            col(ContactFetchJob.company_id) == company_id,
            col(ContactFetchJob.terminal_state).is_(False),
            col(ContactFetchJob.state).in_([ContactFetchJobState.QUEUED, ContactFetchJobState.RUNNING]),
        )
        .order_by(col(ContactFetchJob.created_at).desc())
    ).first()


class ContactFetchService:
    def enqueue(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        company_ids: list[UUID],
        force_refresh: bool = False,
    ) -> tuple[ContactFetchBatch, list[ContactFetchJob], int]:
        """Create a batch, find-or-create a job per company.

        Returns (batch, jobs_to_defer, reused_count).
        `jobs_to_defer` contains only newly created jobs — caller defers Procrastinate tasks for these.
        Reused jobs are still returned in the list when reused (same object), but reused_count > 0
        lets the caller report them correctly.
        """
        batch = ContactFetchBatch(
            campaign_id=campaign_id,
            trigger_source="manual",
            requested_provider_mode="both",
            auto_enqueued=False,
            force_refresh=force_refresh,
            state=ContactFetchBatchState.QUEUED,
            requested_count=len(company_ids),
        )
        session.add(batch)
        session.flush()

        jobs: list[ContactFetchJob] = []
        reused = 0

        for company_id in company_ids:
            if not force_refresh:
                existing = _active_job_for_company(session, company_id)
                if existing is not None:
                    reused += 1
                    jobs.append(existing)
                    continue

            job = ContactFetchJob(
                company_id=company_id,
                contact_fetch_batch_id=batch.id,
                provider="snov",
                requested_providers_json=["snov", "apollo"],
                auto_enqueued=False,
                state=ContactFetchJobState.QUEUED,
            )
            session.add(job)
            jobs.append(job)

        session.flush()

        batch.queued_count = sum(1 for j in jobs if j.contact_fetch_batch_id == batch.id)
        batch.already_fetching_count = reused
        batch.reused_count = reused
        session.add(batch)

        return batch, jobs, reused

    def run_contact_fetch_job(self, *, engine: Any, contact_fetch_job_id: str) -> None:
        """Execute a ContactFetchJob: run Snov then Apollo, upsert contacts, close job."""
        raise NotImplementedError("Implemented in Task 4")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_contact_fetch_service.py -k "test_enqueue" -v
```

- [ ] **Step 5: Commit**

```bash
git add app/services/contact_fetch_service.py tests/test_contact_fetch_service.py
git commit -m "feat(s3): enqueue service — create batch + find-or-create job"
```

---

## Task 3 — Enqueue API endpoints

Add the two POST endpoints to `companies.py`. Both validate campaign scope, call `enqueue()`, defer tasks for new jobs, and return `ContactFetchResult`.

**Files:**
- Modify: `app/api/routes/companies.py`
- Create: `tests/test_contact_fetch_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contact_fetch_api.py
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.models import Company, Upload


def _seed(session: Session, campaign_id) -> Company:
    u = Upload(campaign_id=campaign_id, filename="f.csv", checksum=str(uuid4()), row_count=1, valid_count=1, invalid_count=0)
    session.add(u)
    session.flush()
    co = Company(upload_id=u.id, raw_url="https://acme.com", normalized_url="https://acme.com", domain="acme.com")
    session.add(co)
    session.flush()
    return co


@pytest.mark.asyncio
async def test_fetch_contacts_for_company_creates_job(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import fetch_contacts_for_company
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    company = _seed(sqlite_session, campaign.id)
    sqlite_session.commit()

    result = await fetch_contacts_for_company(
        campaign_id=campaign.id,
        company_id=company.id,
        force_refresh=False,
        session=sqlite_session,
    )

    assert result.queued_count == 1
    assert result.already_fetching_count == 0
    assert len(deferred) == 1


@pytest.mark.asyncio
async def test_fetch_contacts_selected_queues_eligible_companies(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import fetch_contacts_selected
    from app.api.schemas.contacts import BulkContactFetchRequest
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    company = _seed(sqlite_session, campaign.id)
    sqlite_session.commit()

    result = await fetch_contacts_selected(
        payload=BulkContactFetchRequest(campaign_id=campaign.id, company_ids=[company.id]),
        session=sqlite_session,
    )

    assert result.queued_count == 1
    assert len(deferred) == 1


@pytest.mark.asyncio
async def test_fetch_contacts_rejects_out_of_scope_company(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest as pt
    from fastapi import HTTPException
    from app.api.routes.companies import fetch_contacts_for_company
    from app.jobs import contact_fetch as cf_mod

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", lambda **kw: None)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    other_campaign = create_campaign(payload=CampaignCreate(name="other"), session=sqlite_session)
    company = _seed(sqlite_session, other_campaign.id)
    sqlite_session.commit()

    with pt.raises(HTTPException) as exc_info:
        await fetch_contacts_for_company(
            campaign_id=campaign.id,
            company_id=company.id,
            force_refresh=False,
            session=sqlite_session,
        )
    assert exc_info.value.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_contact_fetch_api.py -v
```
Expected: FAIL — functions not found.

- [ ] **Step 3: Add endpoints to `app/api/routes/companies.py`**

Add these imports at the top of `companies.py` (after existing imports):

```python
from app.api.schemas.contacts import BulkContactFetchRequest, ContactFetchResult
from app.jobs.contact_fetch import fetch_contacts as _fetch_contacts_task
from app.models import ContactFetchBatch
from app.models.pipeline import ContactFetchJobState
from app.services.contact_fetch_service import ContactFetchService

_contact_fetch_service = ContactFetchService()
```

Add these endpoints (before the `/{company_id}/feedback` route so fixed paths match before the path param):

```python
@router.post("/companies/{company_id}/fetch-contacts", response_model=ContactFetchResult)
async def fetch_contacts_for_company(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    force_refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    upload = session.get(Upload, company.upload_id)
    if upload is None or upload.campaign_id != campaign_id:
        raise HTTPException(status_code=400, detail="Company is not in the selected campaign.")

    batch, jobs, reused = _contact_fetch_service.enqueue(
        session=session,
        campaign_id=campaign_id,
        company_ids=[company_id],
        force_refresh=force_refresh,
    )
    session.commit()
    session.refresh(batch)
    for j in jobs:
        session.refresh(j)

    new_jobs = [j for j in jobs if j.contact_fetch_batch_id == batch.id]
    defer_failed = 0
    for job in new_jobs:
        try:
            await _fetch_contacts_task.defer_async(contact_fetch_job_id=str(job.id))
        except Exception:
            defer_failed += 1

    return ContactFetchResult(
        requested_count=1,
        queued_count=len(new_jobs) - defer_failed,
        already_fetching_count=reused,
        queued_job_ids=[j.id for j in new_jobs if j.state == ContactFetchJobState.QUEUED],
        reused_count=reused,
        batch_id=batch.id,
    )


@router.post("/companies/fetch-contacts-selected", response_model=ContactFetchResult)
async def fetch_contacts_selected(
    payload: BulkContactFetchRequest,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    # Validate all company_ids are in scope
    from sqlmodel import col as _col
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, _col(Upload.id) == _col(Company.upload_id))
            .where(
                _col(Upload.campaign_id) == payload.campaign_id,
                _col(Company.id).in_(payload.company_ids),
            )
        )
    )
    if {c.id for c in companies} != set(payload.company_ids):
        raise HTTPException(status_code=400, detail="One or more company_ids are outside campaign scope.")

    batch, jobs, reused = _contact_fetch_service.enqueue(
        session=session,
        campaign_id=payload.campaign_id,
        company_ids=payload.company_ids,
        force_refresh=payload.force_refresh,
    )
    session.commit()
    session.refresh(batch)

    new_jobs = [j for j in jobs if j.contact_fetch_batch_id == batch.id]
    defer_failed = 0
    for job in new_jobs:
        try:
            await _fetch_contacts_task.defer_async(contact_fetch_job_id=str(job.id))
        except Exception:
            defer_failed += 1

    return ContactFetchResult(
        requested_count=len(payload.company_ids),
        queued_count=len(new_jobs) - defer_failed,
        already_fetching_count=reused,
        queued_job_ids=[j.id for j in new_jobs if j.state == ContactFetchJobState.QUEUED],
        reused_count=reused,
        batch_id=batch.id,
    )
```

**Important:** The route `POST /companies/fetch-contacts-selected` has no path parameter and must be registered **before** `POST /companies/{company_id}/...` routes. In FastAPI, routes with fixed path segments always take priority over parameterized ones when placed first, but it is cleaner to ensure fixed routes come first in the file. Confirm the order is: scrape-selected → fetch-contacts-selected → scrape-all → `/{company_id}/...`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_contact_fetch_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/companies.py tests/test_contact_fetch_api.py
git commit -m "feat(s3): add POST fetch-contacts endpoints"
```

---

## Task 4 — Worker: run Snov, upsert contacts, apply title-match

Implement `run_contact_fetch_job` in `ContactFetchService`. Uses a CAS-lock (same pattern as `AnalysisService`). Runs Snov first, then Apollo. Upserts `Contact` rows. Applies title-match rules from the company's campaign.

**Snov data mapping:**
- `provider_person_id` = `prospect.get("id") or prospect.get("hash") or sha256(first|last|domain)[:32]`
- `first_name` = `prospect.get("first_name", "")`
- `last_name` = `prospect.get("last_name", "")`
- `title` = `prospect.get("position") or prospect.get("title") or ""`
- `provider_has_email` = bool(`prospect.get("search_emails_start")`)
- `source_provider` = `"snov"`

**Apollo data mapping:**
- `provider_person_id` = `person.get("id", "") or sha256(first|last|domain)[:32]`
- `first_name` = `person.get("first_name", "")`
- `last_name` = `person.get("last_name", "")`
- `title` = `person.get("title") or person.get("headline") or ""`
- `linkedin_url` = `person.get("linkedin_url")`
- `provider_has_email` = bool(`person.get("email")`)
- `source_provider` = `"apollo"`

**Files:**
- Modify: `app/services/contact_fetch_service.py`
- Modify: `tests/test_contact_fetch_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contact_fetch_service.py  (add to existing file)
from app.models import Contact, ContactProviderAttempt
from app.models.pipeline import ContactFetchJobState, ContactProviderAttemptState


def _seed_job(session: Session, campaign: Campaign) -> tuple[Company, "ContactFetchJob"]:
    from app.services.contact_fetch_service import ContactFetchService
    company = _seed_company(session, campaign)
    session.commit()
    svc = ContactFetchService()
    batch, jobs, _ = svc.enqueue(
        session=session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    session.commit()
    return company, jobs[0]


def test_run_job_snov_upserts_contacts(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: (
        [{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO", "search_emails_start": "https://x"}],
        1,
        "",
    ))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)

    svc = ContactFetchService()
    svc.run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].source_provider == "snov"
    assert contacts[0].first_name == "Alice"
    assert contacts[0].title == "CMO"


def test_run_job_apollo_upserts_contacts(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [
        {"id": "apollo-1", "first_name": "Bob", "last_name": "Jones", "title": "CTO", "linkedin_url": "https://li/bob"},
    ])

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)

    svc = ContactFetchService()
    svc.run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].source_provider == "apollo"
    assert contacts[0].first_name == "Bob"
    assert contacts[0].linkedin_url == "https://li/bob"


def test_run_job_both_providers_kept(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: (
        [{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}],
        1,
        "",
    ))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [
        {"id": "apollo-1", "first_name": "Bob", "last_name": "Jones", "title": "CTO"},
    ])

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)
    svc = ContactFetchService()
    svc.run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    providers = {c.source_provider for c in contacts}
    assert providers == {"snov", "apollo"}


def test_run_job_repeated_run_upserts_not_duplicates(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: (
        [{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}],
        1,
        "",
    ))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    company, job1 = _seed_job(sqlite_session, campaign)
    svc = ContactFetchService()
    svc.run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job1.id))

    _, job2 = _seed_job(sqlite_session, campaign)
    svc.run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job2.id))

    contacts = list(sqlite_session.exec(
        select(Contact).where(col(Contact.company_id) == company.id, col(Contact.source_provider) == "snov")
    ))
    assert len(contacts) == 1  # upserted, not duplicated


def test_run_job_title_match_applied(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models import TitleMatchRule

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: (
        [{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "marketing director"}],
        1,
        "",
    ))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    sqlite_session.add(TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="marketing, director", match_type="keyword"))
    sqlite_session.flush()
    company, job = _seed_job(sqlite_session, campaign)

    svc = ContactFetchService()
    svc.run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    contact = sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company.id)).first()
    assert contact is not None
    assert contact.title_match is True


def test_run_job_sets_succeeded_state(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)
    svc = ContactFetchService()
    svc.run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    sqlite_session.refresh(job)
    assert job.state == ContactFetchJobState.SUCCEEDED
    assert job.terminal_state is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_contact_fetch_service.py -k "test_run_job" -v
```
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement `run_contact_fetch_job` in `app/services/contact_fetch_service.py`**

Add these imports to the top of the file:

```python
import hashlib
from typing import Any

from sqlalchemy import update as sa_update
from sqlmodel import col

from app.models import Company, Contact, ContactFetchJob, ContactProviderAttempt, TitleMatchRule, Upload
from app.models.pipeline import ContactFetchJobState, ContactProviderAttemptState
from app.services.snov_client import SnovClient
from app.services.apollo_client import ApolloClient
from app.services.title_match_service import load_title_rules, match_title
```

Replace the `run_contact_fetch_job` stub with:

```python
def run_contact_fetch_job(self, *, engine: Any, contact_fetch_job_id: str) -> None:
    from sqlmodel import Session

    job_id = UUID(contact_fetch_job_id)
    lock_token = str(uuid4())
    now = _utcnow()

    # ── CAS-claim ─────────────────────────────────────────────────────────
    with Session(engine) as session:
        updated = session.execute(
            sa_update(ContactFetchJob)
            .where(
                col(ContactFetchJob.id) == job_id,
                col(ContactFetchJob.terminal_state).is_(False),
                col(ContactFetchJob.state).in_([ContactFetchJobState.QUEUED, ContactFetchJobState.RUNNING]),
            )
            .values(
                state=ContactFetchJobState.RUNNING,
                lock_token=lock_token,
                started_at=now,
                updated_at=now,
                attempt_count=ContactFetchJob.attempt_count + 1,
            )
            .returning(ContactFetchJob.id)
        )
        if not updated.fetchone():
            logger.warning("contact_fetch_job %s already claimed or terminal, skipping", job_id)
            return

        job = session.get(ContactFetchJob, job_id)
        company = session.get(Company, job.company_id)
        upload = session.get(Upload, company.upload_id)
        campaign_id = upload.campaign_id
        include_rules, exclude_words = load_title_rules(session, campaign_id=campaign_id)
        session.commit()

    providers = (job.requested_providers_json or []) or ["snov", "apollo"]

    total_found = 0
    total_matched = 0
    any_failure = False

    for seq_idx, provider in enumerate(providers):
        err = self._run_provider(
            engine=engine,
            job_id=job_id,
            company=company,
            provider=provider,
            seq_idx=seq_idx,
            include_rules=include_rules,
            exclude_words=exclude_words,
        )
        if err:
            any_failure = True
        else:
            with Session(engine) as session:
                attempt = session.exec(
                    select(ContactProviderAttempt)
                    .where(
                        col(ContactProviderAttempt.contact_fetch_job_id) == job_id,
                        col(ContactProviderAttempt.provider) == provider,
                    )
                ).first()
                if attempt:
                    total_found += attempt.contacts_found
                    total_matched += attempt.title_matched_count

    # ── Finalise job ──────────────────────────────────────────────────────
    final_state = ContactFetchJobState.FAILED if any_failure else ContactFetchJobState.SUCCEEDED
    with Session(engine) as session:
        job = session.get(ContactFetchJob, job_id)
        job.state = final_state
        job.terminal_state = True
        job.contacts_found = total_found
        job.title_matched_count = total_matched
        job.finished_at = _utcnow()
        job.updated_at = _utcnow()
        session.add(job)
        session.commit()

def _run_provider(
    self,
    *,
    engine: Any,
    job_id: UUID,
    company: Company,
    provider: str,
    seq_idx: int,
    include_rules: list[list[str]],
    exclude_words: list[str],
) -> str:
    """Run a single provider, upsert contacts, return error code or ''."""
    from sqlmodel import Session

    now = _utcnow()
    with Session(engine) as session:
        attempt = ContactProviderAttempt(
            contact_fetch_job_id=job_id,
            provider=provider,
            sequence_index=seq_idx,
            state=ContactProviderAttemptState.RUNNING,
            started_at=now,
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)
        attempt_id = attempt.id

    people: list[dict] = []
    err = ""

    if provider == "snov":
        client = SnovClient()
        prospects, _total, err = client.search_prospects(company.domain)
        people = [_snov_to_person(p, company.domain) for p in prospects]
    elif provider == "apollo":
        client = ApolloClient()
        raw = client.search_people(company.domain)
        err = client.last_error_code
        people = [_apollo_to_person(p) for p in raw]
    else:
        err = f"unknown_provider_{provider}"

    contacts_found = 0
    title_matched = 0

    if not err:
        with Session(engine) as session:
            for person in people:
                if not person.get("provider_person_id"):
                    continue
                existing = session.exec(
                    select(Contact).where(
                        col(Contact.company_id) == company.id,
                        col(Contact.source_provider) == provider,
                        col(Contact.provider_person_id) == person["provider_person_id"],
                    )
                ).first()
                is_match = match_title(person.get("title") or "", include_rules, exclude_words) if include_rules else False
                if existing:
                    existing.first_name = person.get("first_name", existing.first_name)
                    existing.last_name = person.get("last_name", existing.last_name)
                    existing.title = person.get("title", existing.title)
                    existing.linkedin_url = person.get("linkedin_url", existing.linkedin_url)
                    existing.provider_has_email = person.get("provider_has_email", existing.provider_has_email)
                    existing.title_match = is_match
                    existing.last_seen_at = _utcnow()
                    existing.updated_at = _utcnow()
                    existing.contact_fetch_job_id = job_id
                    session.add(existing)
                else:
                    session.add(Contact(
                        company_id=company.id,
                        contact_fetch_job_id=job_id,
                        source_provider=provider,
                        provider_person_id=person["provider_person_id"],
                        first_name=person.get("first_name", ""),
                        last_name=person.get("last_name", ""),
                        title=person.get("title"),
                        linkedin_url=person.get("linkedin_url"),
                        provider_has_email=person.get("provider_has_email"),
                        provider_metadata_json=person.get("provider_metadata_json"),
                        raw_payload_json=person.get("raw_payload_json"),
                        title_match=is_match,
                    ))
                contacts_found += 1
                if is_match:
                    title_matched += 1
            session.commit()

    state = ContactProviderAttemptState.SUCCEEDED if not err else ContactProviderAttemptState.FAILED
    with Session(engine) as session:
        attempt = session.get(ContactProviderAttempt, attempt_id)
        attempt.state = state
        attempt.terminal_state = True
        attempt.contacts_found = contacts_found
        attempt.title_matched_count = title_matched
        attempt.finished_at = _utcnow()
        attempt.updated_at = _utcnow()
        if err:
            attempt.last_error_code = err
        session.add(attempt)
        session.commit()

    return err
```

Add these helper functions at module level (after imports, before the class):

```python
def _stable_id(first: str, last: str, domain: str) -> str:
    raw = f"{first.lower()}|{last.lower()}|{domain.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _snov_to_person(prospect: dict, domain: str) -> dict:
    pid = (str(prospect.get("id") or prospect.get("hash") or "").strip()
           or _stable_id(prospect.get("first_name", ""), prospect.get("last_name", ""), domain))
    return {
        "provider_person_id": pid,
        "first_name": prospect.get("first_name") or "",
        "last_name": prospect.get("last_name") or "",
        "title": prospect.get("position") or prospect.get("title") or "",
        "provider_has_email": bool(prospect.get("search_emails_start")),
        "raw_payload_json": prospect,
    }


def _apollo_to_person(person: dict) -> dict:
    pid = str(person.get("id") or "").strip()
    if not pid:
        pid = _stable_id(person.get("first_name", ""), person.get("last_name", ""), "")
    return {
        "provider_person_id": pid,
        "first_name": person.get("first_name") or "",
        "last_name": person.get("last_name") or "",
        "title": person.get("title") or person.get("headline") or "",
        "linkedin_url": person.get("linkedin_url"),
        "provider_has_email": bool(person.get("email")),
        "raw_payload_json": person,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_contact_fetch_service.py -k "test_run_job" -v
```

- [ ] **Step 5: Commit**

```bash
git add app/services/contact_fetch_service.py tests/test_contact_fetch_service.py
git commit -m "feat(s3): implement run_contact_fetch_job — Snov + Apollo, upsert, title-match"
```

---

## Task 5 — Read endpoint: `GET /v1/companies/{company_id}/contacts`

Returns a paginated `ContactListResponse` scoped to one company. Reuses the existing `apply_contact_filters` helper.

**Files:**
- Modify: `app/api/routes/companies.py`
- Modify: `tests/test_contact_fetch_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contact_fetch_api.py  (add)
def test_list_company_contacts_returns_contacts(sqlite_session: Session) -> None:
    from app.api.routes.companies import list_company_contacts
    from app.models import Contact

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    company = _seed(sqlite_session, campaign.id)
    sqlite_session.add(Contact(
        company_id=company.id,
        source_provider="snov",
        provider_person_id="snov-1",
        first_name="Alice",
        last_name="Smith",
    ))
    sqlite_session.commit()

    result = list_company_contacts(
        company_id=company.id,
        campaign_id=campaign.id,
        limit=50,
        offset=0,
        session=sqlite_session,
    )

    assert result.total == 1
    assert result.items[0].first_name == "Alice"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_contact_fetch_api.py::test_list_company_contacts_returns_contacts -v
```

- [ ] **Step 3: Add endpoint to `app/api/routes/companies.py`**

Add imports if not already present:
```python
from app.api.schemas.contacts import ContactListResponse, ContactRead
from app.services.contact_query_service import apply_contact_filters as _apply_contact_filters, campaign_upload_scope as _campaign_upload_scope
```

Add the endpoint:

```python
@router.get("/companies/{company_id}/contacts", response_model=ContactListResponse)
def list_company_contacts(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    title_match: bool | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    from app.models import Contact as _Contact
    from sqlalchemy import func as _func

    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    upload = session.get(Upload, company.upload_id)
    if upload is None or upload.campaign_id != campaign_id:
        raise HTTPException(status_code=400, detail="Company is not in the selected campaign.")

    q = select(_Contact, Company.domain).join(Company, col(Company.id) == col(_Contact.company_id))
    q = q.where(_campaign_upload_scope(campaign_id), col(_Contact.company_id) == company_id)
    q = _apply_contact_filters(q, title_match=title_match, verification_status=verification_status, stage_filter=stage_filter)

    total = session.exec(select(_func.count()).select_from(q.subquery())).one()
    rows = list(session.exec(q.order_by(col(_Contact.created_at).desc()).offset(offset).limit(limit)).all())

    from app.services.contact_query_service import contact_emails_map as _contact_emails_map
    contacts_only = [c for c, _ in rows]
    email_map = _contact_emails_map(session, contacts_only)

    items = [
        ContactRead.model_validate({
            **c.__dict__,
            "domain": domain,
            "emails": email_map.get(c.id, []),
            "freshness_status": "fresh",
            "group_key": str(c.id),
            "last_seen_at": c.last_seen_at,
            "provider_has_email": c.provider_has_email,
            "source_provider": c.source_provider,
        })
        for c, domain in rows
    ]

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=items,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_contact_fetch_api.py::test_list_company_contacts_returns_contacts -v
```

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/companies.py tests/test_contact_fetch_api.py
git commit -m "feat(s3): add GET /companies/{company_id}/contacts"
```

---

## Task 6 — Read endpoint: `GET /v1/contacts/companies`

Returns a paginated `ContactCompanyListResponse` — one row per company summarising discovered contacts. Used by the S3 audit panel.

**Files:**
- Modify: `app/api/routes/contacts.py`
- Modify: `tests/test_contact_fetch_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contact_fetch_api.py  (add)
def test_list_contacts_companies_groups_by_company(sqlite_session: Session) -> None:
    from app.api.routes.contacts import list_contacts_companies
    from app.models import Contact

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    company = _seed(sqlite_session, campaign.id)
    sqlite_session.add(Contact(company_id=company.id, source_provider="snov", provider_person_id="s1", first_name="A", last_name="B", title_match=True))
    sqlite_session.add(Contact(company_id=company.id, source_provider="apollo", provider_person_id="a1", first_name="C", last_name="D"))
    sqlite_session.commit()

    result = list_contacts_companies(
        campaign_id=campaign.id,
        search=None,
        title_match=None,
        match_gap_filter="all",
        limit=50,
        offset=0,
        session=sqlite_session,
    )

    assert result.total == 1
    assert result.items[0].company_id == company.id
    assert result.items[0].total_count == 2
    assert result.items[0].title_matched_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_contact_fetch_api.py::test_list_contacts_companies_groups_by_company -v
```

- [ ] **Step 3: Add endpoint to `app/api/routes/contacts.py`**

Add import at top of contacts.py:
```python
from app.api.schemas.contacts import ContactCompanyListResponse, ContactCompanySummary, MatchGapFilter
```

Add endpoint (place before the `title-match-rules` block):

```python
@router.get("/contacts/companies", response_model=ContactCompanyListResponse)
def list_contacts_companies(
    campaign_id: UUID = Query(...),
    search: str | None = Query(default=None),
    title_match: bool | None = Query(default=None),
    match_gap_filter: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactCompanyListResponse:
    from sqlalchemy import case as sa_case
    from app.services.contact_query_service import (
        validate_match_gap_filter as _vmgf,
        campaign_upload_scope as _cup_scope,
    )
    _campaign_or_404(session=session, campaign_id=campaign_id)
    mgf = _vmgf(match_gap_filter)

    subq = (
        select(
            col(Contact.company_id),
            func.count(col(Contact.id)).label("total_count"),
            func.coalesce(func.sum(sa_case((col(Contact.title_match).is_(True), 1), else_=0)), 0).label("title_matched_count"),
            func.coalesce(func.sum(sa_case((col(Contact.email).is_not(None), 1), else_=0)), 0).label("email_count"),
            func.coalesce(func.sum(sa_case((col(Contact.pipeline_stage) == "fetched", 1), else_=0)), 0).label("fetched_count"),
            func.coalesce(func.sum(sa_case((col(Contact.verification_status) == "valid", 1), else_=0)), 0).label("verified_count"),
            func.coalesce(func.sum(sa_case((col(Contact.pipeline_stage) == "campaign_ready", 1), else_=0)), 0).label("campaign_ready_count"),
            func.max(col(Contact.created_at)).label("last_contact_attempted_at"),
        )
        .join(Company, col(Company.id) == col(Contact.company_id))
        .where(_cup_scope(campaign_id), col(Contact.is_active).is_(True))
        .group_by(col(Contact.company_id))
        .subquery()
    )

    stmt = (
        select(Company.id, Company.domain, subq)
        .join(subq, col(Company.id) == subq.c.company_id)
    )

    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(func.lower(col(Company.domain)).like(term))
    if title_match is not None:
        if title_match:
            stmt = stmt.where(subq.c.title_matched_count > 0)
        else:
            stmt = stmt.where(subq.c.title_matched_count == 0)
    if mgf == "contacts_no_match":
        stmt = stmt.where(subq.c.title_matched_count == 0)
    elif mgf == "matched_no_email":
        stmt = stmt.where(subq.c.title_matched_count > 0, subq.c.email_count == 0)
    elif mgf == "ready_candidates":
        stmt = stmt.where(subq.c.campaign_ready_count > 0)

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = list(session.exec(stmt.order_by(col(Company.domain)).offset(offset).limit(limit)).all())

    items = [
        ContactCompanySummary(
            company_id=row[0],
            domain=row[1],
            total_count=int(row[3]),
            title_matched_count=int(row[4]),
            unmatched_count=int(row[3]) - int(row[4]),
            matched_no_email_count=max(0, int(row[4]) - int(row[5])),
            email_count=int(row[5]),
            fetched_count=int(row[6]),
            verified_count=int(row[7]),
            campaign_ready_count=int(row[8]),
            eligible_verify_count=int(row[4]),
            last_contact_attempted_at=row[9],
        )
        for row in rows
    ]

    return ContactCompanyListResponse(
        total=int(total),
        has_more=(offset + len(items)) < int(total),
        limit=limit,
        offset=offset,
        items=items,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_contact_fetch_api.py::test_list_contacts_companies_groups_by_company -v
```

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/contacts.py tests/test_contact_fetch_api.py
git commit -m "feat(s3): add GET /contacts/companies"
```

---

## Task 7 — Read endpoint: `GET /v1/contacts/ids`

Returns all matching contact IDs (no pagination) for the current filter — used by the S3 "select all matching" flow.

**Files:**
- Modify: `app/api/routes/contacts.py`
- Modify: `tests/test_contact_fetch_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contact_fetch_api.py  (add)
def test_list_contact_ids_returns_matching_ids(sqlite_session: Session) -> None:
    from app.api.routes.contacts import list_contact_ids
    from app.models import Contact

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    company = _seed(sqlite_session, campaign.id)
    c1 = Contact(company_id=company.id, source_provider="snov", provider_person_id="s1", first_name="A", last_name="B", title_match=True)
    c2 = Contact(company_id=company.id, source_provider="apollo", provider_person_id="a1", first_name="C", last_name="D", title_match=False)
    sqlite_session.add(c1)
    sqlite_session.add(c2)
    sqlite_session.commit()
    sqlite_session.refresh(c1)
    sqlite_session.refresh(c2)

    result = list_contact_ids(
        campaign_id=campaign.id,
        title_match=True,
        session=sqlite_session,
    )

    assert result.total == 1
    assert c1.id in result.ids
    assert c2.id not in result.ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_contact_fetch_api.py::test_list_contact_ids_returns_matching_ids -v
```

- [ ] **Step 3: Add endpoint to `app/api/routes/contacts.py`**

Add import at top:
```python
from app.api.schemas.contacts import ContactIdsResult
```

Add endpoint (after `list_contacts_companies`, before title-match-rules block):

```python
@router.get("/contacts/ids", response_model=ContactIdsResult)
def list_contact_ids(
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    stale_days: int | None = Query(default=None, ge=1, le=365),
    letters: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ContactIdsResult:
    from app.services.contact_query_service import (
        apply_contact_filters as _acf,
        campaign_upload_scope as _cup_scope,
        parse_letters as _parse_letters,
    )
    _campaign_or_404(session=session, campaign_id=campaign_id)
    letter_values = _parse_letters(letters)

    q = select(Contact.id).join(Company, col(Company.id) == col(Contact.company_id))
    q = q.where(_cup_scope(campaign_id))
    q = _acf(q, title_match=title_match, search=search, stale_days=stale_days, letters=letter_values or None)

    ids = list(session.exec(q).all())
    return ContactIdsResult(ids=ids, total=len(ids))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_contact_fetch_api.py::test_list_contact_ids_returns_matching_ids -v
```

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/contacts.py tests/test_contact_fetch_api.py
git commit -m "feat(s3): add GET /contacts/ids"
```

---

## Task 8 — Full test suite + regression check

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/ -v --tb=short
```
Expected: all pass. Fix any import errors or signature mismatches before proceeding.

- [ ] **Step 2: Confirm route ordering in companies.py**

Open `app/api/routes/companies.py` and verify the route order is:
1. `GET /companies` (list)
2. `GET /companies/letter-counts`
3. `GET /companies/ids`
4. `POST /companies/scrape-selected`
5. `POST /companies/scrape-all`
6. **`POST /companies/fetch-contacts-selected`** ← must be before `/{company_id}/...`
7. `GET /companies/{company_id}/contacts` ← path param routes last
8. `POST /companies/{company_id}/fetch-contacts`
9. `PUT /companies/{company_id}/feedback`

FastAPI matches routes in registration order. Fixed-segment routes must precede `{company_id}` routes.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(s3): complete manual contact discovery vertical slice"
```
