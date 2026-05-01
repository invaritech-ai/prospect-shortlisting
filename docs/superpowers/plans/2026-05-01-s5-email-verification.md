# S5 Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement manual batch email verification via ZeroBounce — operator selects revealed contacts, one API call verifies the whole batch, and verified contacts become `campaign_ready`.

**Architecture:** `POST /v1/contacts/verify` filters the selection to eligible contacts (title-matched, has email, unverified), creates one `ContactVerifyJob` storing all contact IDs, and defers a single `verify_contacts(job_id)` Procrastinate task. The worker CAS-claims the job, calls `ZeroBounceClient.validate_batch()` once, writes `verification_status` / `zerobounce_raw` back to each contact, and advances `pipeline_stage` to `"campaign_ready"` for valid ones.

**Tech Stack:** FastAPI, SQLModel, Procrastinate, ZeroBounceClient, SQLite (tests), pytest

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `app/services/contact_verify_service.py` | **Create** | Eligibility filter, job creation, batch worker logic |
| `app/jobs/validation.py` | **Modify** | Replace stub — `verify_contacts(job_id)` calls service |
| `app/api/routes/contacts.py` | **Modify** | Implement `POST /v1/contacts/verify` |
| `tests/test_contact_verify_service.py` | **Create** | Service unit tests |
| `tests/test_contact_verify_api.py` | **Create** | API endpoint test |

---

## Task 1 — ContactVerifyService: enqueue

**Files:**
- Create: `app/services/contact_verify_service.py`
- Create: `tests/test_contact_verify_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contact_verify_service.py
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.models import Campaign, Company, Contact, ContactVerifyJob, Upload
from app.models.pipeline import ContactVerifyJobState


def _seed_campaign(session: Session) -> Campaign:
    c = Campaign(name="test")
    session.add(c)
    session.flush()
    return c


def _seed_company(session: Session, campaign: Campaign) -> Company:
    u = Upload(
        campaign_id=campaign.id,
        filename="f.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    session.add(u)
    session.flush()
    co = Company(
        upload_id=u.id,
        raw_url="https://acme.com",
        normalized_url="https://acme.com",
        domain="acme.com",
    )
    session.add(co)
    session.flush()
    return co


def _seed_contact(
    session: Session,
    company: Company,
    *,
    title_match: bool = True,
    email: str | None = "alice@acme.com",
    verification_status: str = "unverified",
) -> Contact:
    c = Contact(
        company_id=company.id,
        source_provider="snov",
        provider_person_id=str(uuid4()),
        first_name="Alice",
        last_name="Smith",
        title_match=title_match,
        email=email,
        verification_status=verification_status,
        pipeline_stage="email_revealed",
    )
    session.add(c)
    session.flush()
    return c


def test_enqueue_creates_job_with_eligible_contacts(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c1 = _seed_contact(sqlite_session, company)
    sqlite_session.commit()

    svc = ContactVerifyService()
    job, skipped = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c1.id],
    )
    sqlite_session.commit()

    assert job.state == ContactVerifyJobState.QUEUED
    assert job.selected_count == 1
    assert job.skipped_count == 0
    assert str(c1.id) in job.contact_ids_json


def test_enqueue_skips_no_title_match(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(sqlite_session, company, title_match=False)
    sqlite_session.commit()

    job, skipped = ContactVerifyService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert job.contact_ids_json == []
    assert job.skipped_count == 1
    assert skipped == 1


def test_enqueue_skips_no_email(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(sqlite_session, company, email=None)
    sqlite_session.commit()

    job, skipped = ContactVerifyService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert job.contact_ids_json == []
    assert skipped == 1


def test_enqueue_skips_already_verified(sqlite_session: Session) -> None:
    from app.services.contact_verify_service import ContactVerifyService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(sqlite_session, company, verification_status="valid")
    sqlite_session.commit()

    job, skipped = ContactVerifyService().enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert job.contact_ids_json == []
    assert skipped == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_contact_verify_service.py -k "test_enqueue" -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.contact_verify_service'`

- [ ] **Step 3: Create `app/services/contact_verify_service.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.models import Company, Contact, ContactVerifyJob, Upload
from app.models.pipeline import ContactVerifyJobState
from app.services.contact_query_service import verification_eligible_condition

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContactVerifyService:
    def enqueue(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        contact_ids: list[UUID],
    ) -> tuple[ContactVerifyJob, int]:
        """Filter contact_ids to eligible, create ContactVerifyJob.

        Returns (job, skipped_count).
        Caller defers verify_contacts(job_id) after commit.
        """
        from app.services.contact_query_service import campaign_upload_scope

        eligible_ids: list[str] = []
        skipped = 0

        if contact_ids:
            rows = list(
                session.exec(
                    select(Contact.id)
                    .join(Company, col(Company.id) == col(Contact.company_id))
                    .where(
                        col(Contact.id).in_(contact_ids),
                        campaign_upload_scope(campaign_id),
                        *verification_eligible_condition(),
                    )
                )
            )
            eligible_set = {r for r in rows}
            eligible_ids = [str(cid) for cid in contact_ids if cid in eligible_set]
            skipped = len(contact_ids) - len(eligible_ids)

        job = ContactVerifyJob(
            state=ContactVerifyJobState.QUEUED,
            contact_ids_json=eligible_ids,
            selected_count=len(contact_ids),
            verified_count=0,
            skipped_count=skipped,
        )
        session.add(job)
        session.flush()

        return job, skipped

    def run_verify(self, *, engine: Any, job_id: str) -> None:
        """CAS-claim the job, call ZeroBounce batch, write results, finalize."""
        raise NotImplementedError("Implemented in Task 2")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_contact_verify_service.py -k "test_enqueue" -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/contact_verify_service.py tests/test_contact_verify_service.py
git commit -m "feat(s5): ContactVerifyService.enqueue — eligibility filter + job creation"
```

---

## Task 2 — Worker: CAS-claim, validate_batch, write results

**Files:**
- Modify: `app/services/contact_verify_service.py`
- Modify: `tests/test_contact_verify_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_contact_verify_service.py`:

```python
def test_run_verify_writes_valid_status(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: (
            [{"email_address": "alice@acme.com", "status": "valid"}],
            "",
        ),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company)
    sqlite_session.commit()

    svc = ContactVerifyService()
    job, _ = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )
    sqlite_session.commit()

    svc.run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    sqlite_session.refresh(contact)
    assert contact.verification_status == "valid"
    assert contact.verification_provider == "zerobounce"
    assert contact.pipeline_stage == "campaign_ready"
    assert contact.zerobounce_raw is not None

    sqlite_session.refresh(job)
    assert job.state == ContactVerifyJobState.SUCCEEDED
    assert job.verified_count == 1
    assert job.terminal_state is True
    assert job.finished_at is not None


def test_run_verify_invalid_status_does_not_set_campaign_ready(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: (
            [{"email_address": "alice@acme.com", "status": "invalid"}],
            "",
        ),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company)
    sqlite_session.commit()

    svc = ContactVerifyService()
    job, _ = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, contact_ids=[contact.id])
    sqlite_session.commit()
    svc.run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    sqlite_session.refresh(contact)
    assert contact.verification_status == "invalid"
    assert contact.pipeline_stage == "email_revealed"


def test_run_verify_api_error_leaves_contacts_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: ([], "zerobounce_rate_limited"),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company)
    sqlite_session.commit()

    svc = ContactVerifyService()
    job, _ = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, contact_ids=[contact.id])
    sqlite_session.commit()
    svc.run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    sqlite_session.refresh(contact)
    assert contact.verification_status == "unverified"

    sqlite_session.refresh(job)
    assert job.state == ContactVerifyJobState.FAILED
    assert job.terminal_state is True


def test_run_verify_skips_malformed_result_row(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: (
            [
                {"status": "valid"},                                          # missing email_address
                {"email_address": "alice@acme.com", "status": "valid"},      # valid row
            ],
            "",
        ),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company)
    sqlite_session.commit()

    svc = ContactVerifyService()
    job, _ = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, contact_ids=[contact.id])
    sqlite_session.commit()
    svc.run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    sqlite_session.refresh(contact)
    assert contact.verification_status == "valid"

    sqlite_session.refresh(job)
    assert job.state == ContactVerifyJobState.SUCCEEDED


def test_run_verify_empty_job_succeeds_immediately(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    from app.services import zerobounce_client as zb_mod

    called = []
    monkeypatch.setattr(
        zb_mod.ZeroBounceClient,
        "validate_batch",
        lambda self, emails, **kw: called.append(emails) or ([], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    # Contact is ineligible so job has empty contact_ids_json
    contact = _seed_contact(sqlite_session, company, title_match=False)
    sqlite_session.commit()

    svc = ContactVerifyService()
    job, _ = svc.enqueue(session=sqlite_session, campaign_id=campaign.id, contact_ids=[contact.id])
    sqlite_session.commit()
    svc.run_verify(engine=sqlite_session.bind, job_id=str(job.id))

    # No ZeroBounce call should be made for an empty job
    assert called == []
    sqlite_session.refresh(job)
    assert job.state == ContactVerifyJobState.SUCCEEDED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_contact_verify_service.py -k "test_run_verify" -v
```
Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Implement `run_verify` in `app/services/contact_verify_service.py`**

Replace the `raise NotImplementedError` stub with:

```python
def run_verify(self, *, engine: Any, job_id: str) -> None:
    """CAS-claim the job, call ZeroBounce batch, write results, finalize."""
    from sqlmodel import Session

    jid = UUID(job_id)
    lock_token = str(uuid4())
    now = _utcnow()

    # ── Phase 1: CAS-claim ─────────────────────────────────────────────────
    with Session(engine) as session:
        updated = session.execute(
            sa_update(ContactVerifyJob)
            .where(
                col(ContactVerifyJob.id) == jid,
                col(ContactVerifyJob.terminal_state).is_(False),
                col(ContactVerifyJob.state).in_(
                    [ContactVerifyJobState.QUEUED, ContactVerifyJobState.RUNNING]
                ),
            )
            .values(
                state=ContactVerifyJobState.RUNNING,
                lock_token=lock_token,
                started_at=now,
                updated_at=now,
                attempt_count=ContactVerifyJob.attempt_count + 1,
            )
            .returning(ContactVerifyJob.id)
        )
        if not updated.fetchone():
            logger.warning("contact_verify_job %s already claimed or terminal, skipping", jid)
            return

        job = session.get(ContactVerifyJob, jid)
        contact_ids_json = list(job.contact_ids_json or [])
        session.commit()

    # ── Phase 2: Short-circuit empty job ───────────────────────────────────
    if not contact_ids_json:
        with Session(engine) as session:
            job = session.get(ContactVerifyJob, jid)
            job.state = ContactVerifyJobState.SUCCEEDED
            job.terminal_state = True
            job.finished_at = _utcnow()
            job.updated_at = _utcnow()
            session.add(job)
            session.commit()
        return

    # ── Phase 3: Load contacts, collect emails ─────────────────────────────
    contact_uuids = [UUID(cid) for cid in contact_ids_json]
    with Session(engine) as session:
        contacts = list(
            session.exec(select(Contact).where(col(Contact.id).in_(contact_uuids)))
        )
        # Map email → contact for result matching
        email_to_contact = {c.email: c.id for c in contacts if c.email}

    emails = list(email_to_contact.keys())

    # ── Phase 4: ZeroBounce batch call ─────────────────────────────────────
    from app.services.zerobounce_client import ZeroBounceClient

    client = ZeroBounceClient()
    results, err = client.validate_batch(emails)

    if err:
        logger.warning("contact_verify_job %s: ZeroBounce error %r", jid, err)
        with Session(engine) as session:
            job = session.get(ContactVerifyJob, jid)
            job.state = ContactVerifyJobState.FAILED
            job.terminal_state = True
            job.last_error_code = err
            job.finished_at = _utcnow()
            job.updated_at = _utcnow()
            session.add(job)
            session.commit()
        return

    # ── Phase 5: Write results back to contacts ────────────────────────────
    verified_count = 0
    with Session(engine) as session:
        for row in results:
            email_addr = row.get("email_address")
            status = row.get("status")
            if not email_addr or not status:
                continue
            contact_id = email_to_contact.get(email_addr)
            if contact_id is None:
                continue
            contact = session.get(Contact, contact_id)
            if contact is None:
                continue
            contact.verification_status = status
            contact.verification_provider = "zerobounce"
            contact.zerobounce_raw = row
            contact.updated_at = _utcnow()
            if status == "valid" and contact.title_match:
                contact.pipeline_stage = "campaign_ready"
            session.add(contact)
            verified_count += 1
        session.commit()

    # ── Phase 6: Finalize job ──────────────────────────────────────────────
    with Session(engine) as session:
        job = session.get(ContactVerifyJob, jid)
        job.state = ContactVerifyJobState.SUCCEEDED
        job.terminal_state = True
        job.verified_count = verified_count
        job.finished_at = _utcnow()
        job.updated_at = _utcnow()
        session.add(job)
        session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_contact_verify_service.py -k "test_run_verify" -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/contact_verify_service.py tests/test_contact_verify_service.py
git commit -m "feat(s5): run_verify — CAS-claim, ZeroBounce batch, write results"
```

---

## Task 3 — Update the job stub

**Files:**
- Modify: `app/jobs/validation.py`
- Modify: `tests/test_contact_verify_service.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_contact_verify_service.py`:

```python
def test_verify_contacts_task_accepts_job_id() -> None:
    import inspect
    from app.jobs.validation import verify_contacts

    fn = getattr(verify_contacts, "original_func", verify_contacts)
    sig = inspect.signature(fn)
    assert "job_id" in sig.parameters
    assert "contact_id" not in sig.parameters
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_contact_verify_service.py::test_verify_contacts_task_accepts_job_id -v
```
Expected: FAIL — `cannot import name 'verify_contacts'` (stub is named `validate_email`)

- [ ] **Step 3: Replace `app/jobs/validation.py`**

```python
"""Procrastinate task: verify a batch of contacts via ZeroBounce."""
from __future__ import annotations

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app


@app.task(name="verify_contacts", queue="validation")
async def verify_contacts(job_id: str) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    ContactVerifyService().run_verify(
        engine=get_engine(),
        job_id=job_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_contact_verify_service.py::test_verify_contacts_task_accepts_job_id -v
```
Expected: PASS.

- [ ] **Step 5: Update `app/queue.py` import path**

Open `app/queue.py`. The `import_paths` list includes `"app.jobs.validation"` — this is already correct and no change is needed since the module path hasn't changed.

- [ ] **Step 6: Commit**

```bash
git add app/jobs/validation.py tests/test_contact_verify_service.py
git commit -m "feat(s5): wire verify_contacts task to ContactVerifyService"
```

---

## Task 4 — API endpoint: `POST /v1/contacts/verify`

**Files:**
- Modify: `app/api/routes/contacts.py`
- Create: `tests/test_contact_verify_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contact_verify_api.py
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.models import Company, Contact, Upload


def _seed(session: Session, campaign_id) -> tuple[Company, Contact]:
    u = Upload(
        campaign_id=campaign_id,
        filename="f.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    session.add(u)
    session.flush()
    co = Company(
        upload_id=u.id,
        raw_url="https://acme.com",
        normalized_url="https://acme.com",
        domain="acme.com",
    )
    session.add(co)
    session.flush()
    contact = Contact(
        company_id=co.id,
        source_provider="snov",
        provider_person_id=str(uuid4()),
        first_name="Alice",
        last_name="Smith",
        title_match=True,
        email="alice@acme.com",
        verification_status="unverified",
        pipeline_stage="email_revealed",
    )
    session.add(contact)
    session.flush()
    return co, contact


@pytest.mark.asyncio
async def test_verify_endpoint_creates_job_and_defers_task(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import verify_contacts
    from app.api.schemas.contacts import ContactVerifyRequest
    from app.jobs import validation as val_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(val_mod.verify_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s5"), session=sqlite_session)
    _, contact = _seed(sqlite_session, campaign.id)
    sqlite_session.commit()

    result = await verify_contacts(
        payload=ContactVerifyRequest(
            campaign_id=campaign.id,
            contact_ids=[contact.id],
        ),
        session=sqlite_session,
    )

    assert result.job_id is not None
    assert result.selected_count == 1
    assert len(deferred) == 1
    assert "job_id" in deferred[0]


@pytest.mark.asyncio
async def test_verify_endpoint_skips_ineligible_contacts(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import verify_contacts
    from app.api.schemas.contacts import ContactVerifyRequest
    from app.jobs import validation as val_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(val_mod.verify_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s5"), session=sqlite_session)
    _, contact = _seed(sqlite_session, campaign.id)
    contact.title_match = False
    sqlite_session.flush()
    sqlite_session.commit()

    result = await verify_contacts(
        payload=ContactVerifyRequest(
            campaign_id=campaign.id,
            contact_ids=[contact.id],
        ),
        session=sqlite_session,
    )

    # Job is created but with 0 eligible contacts; task still deferred
    assert result.job_id is not None
    assert result.selected_count == 1
    assert len(deferred) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_contact_verify_api.py -v
```
Expected: FAIL — `cannot import name 'verify_contacts' from 'app.api.routes.contacts'`

- [ ] **Step 3: Add imports to `app/api/routes/contacts.py`**

Add to the existing imports block:

```python
from app.api.schemas.contacts import (
    ...existing...,
    ContactVerifyRequest,
    ContactVerifyResult,
)
from app.jobs.validation import verify_contacts as _verify_contacts_task
from app.services.contact_verify_service import ContactVerifyService

_contact_verify_service = ContactVerifyService()
```

- [ ] **Step 4: Add the endpoint to `app/api/routes/contacts.py`**

Add before the `title-match-rules` block:

```python
@router.post("/contacts/verify", response_model=ContactVerifyResult)
async def verify_contacts(
    payload: ContactVerifyRequest,
    session: Session = Depends(get_session),
) -> ContactVerifyResult:
    _campaign_or_404(session=session, campaign_id=payload.campaign_id)

    contact_ids = list(payload.contact_ids or [])

    job, skipped = _contact_verify_service.enqueue(
        session=session,
        campaign_id=payload.campaign_id,
        contact_ids=contact_ids,
    )
    session.commit()
    session.refresh(job)

    try:
        await _verify_contacts_task.defer_async(job_id=str(job.id))
    except Exception:
        pass

    queued = len(job.contact_ids_json or [])
    return ContactVerifyResult(
        job_id=job.id,
        selected_count=job.selected_count,
        message=f"Queued verification for {queued} contact(s). {skipped} skipped.",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_contact_verify_api.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes/contacts.py app/jobs/validation.py tests/test_contact_verify_api.py
git commit -m "feat(s5): implement POST /v1/contacts/verify"
```

---

## Task 5 — Full suite + regression check

- [ ] **Step 1: Run all S5 tests**

```bash
uv run pytest tests/test_contact_verify_service.py tests/test_contact_verify_api.py -v
```
Expected: all pass.

- [ ] **Step 2: Run full suite**

```bash
uv run pytest tests/ --ignore=tests/test_analysis_usage_events.py -q --tb=short
```
Expected: no new failures beyond the pre-existing 16.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(s5): complete email verification vertical slice"
```
