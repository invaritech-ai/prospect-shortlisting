# S4 Email Reveal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement manual per-contact email reveal — the operator selects title-matched contacts, clicks reveal, and the worker fetches the email from the contact's source provider and writes it back.

**Architecture:** `POST /v1/contacts/reveal` filters the selection to eligible contacts (title-matched, no fresh email), creates a `ContactRevealBatch`, and defers one `reveal_email(contact_id)` Procrastinate task per eligible contact. The worker loads the contact, calls Snov or Apollo based on `source_provider`, and writes the result back to the `Contact` row. No new DB models needed.

**Tech Stack:** FastAPI, SQLModel, Procrastinate, SnovClient, ApolloClient, SQLite (tests), pytest

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `app/services/email_reveal_service.py` | **Create** | Eligibility filter, batch creation, `run_reveal` worker logic |
| `app/jobs/email_reveal.py` | **Modify** | Replace stub — call `EmailRevealService().run_reveal(engine, contact_id)` |
| `app/api/routes/contacts.py` | **Modify** | Implement `POST /v1/contacts/reveal` |
| `tests/test_email_reveal_service.py` | **Create** | Service unit tests |
| `tests/test_email_reveal_api.py` | **Create** | API endpoint test |

---

## Task 1 — EmailRevealService: eligibility filter

**Files:**
- Create: `app/services/email_reveal_service.py`
- Create: `tests/test_email_reveal_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_email_reveal_service.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlmodel import Session, col, select

from app.models import Campaign, Company, Contact, ContactRevealBatch, Upload
from app.models.pipeline import ContactFetchBatchState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    email: str | None = None,
    updated_at: datetime | None = None,
    source_provider: str = "snov",
    provider_person_id: str | None = None,
) -> Contact:
    c = Contact(
        company_id=company.id,
        source_provider=source_provider,
        provider_person_id=provider_person_id or str(uuid4()),
        first_name="Alice",
        last_name="Smith",
        title="CMO",
        title_match=title_match,
        email=email,
    )
    session.add(c)
    session.flush()
    if updated_at is not None:
        session.execute(
            __import__("sqlalchemy").update(Contact)
            .where(col(Contact.id) == c.id)
            .values(updated_at=updated_at)
        )
        session.flush()
        session.refresh(c)
    return c


def test_enqueue_creates_batch_and_returns_eligible(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c1 = _seed_contact(sqlite_session, company, title_match=True, email=None)
    sqlite_session.commit()

    svc = EmailRevealService()
    batch, contact_ids, skipped = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c1.id],
    )
    sqlite_session.commit()

    assert batch.campaign_id == campaign.id
    assert len(contact_ids) == 1
    assert contact_ids[0] == c1.id
    assert skipped == 0


def test_enqueue_skips_no_title_match(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(sqlite_session, company, title_match=False, email=None)
    sqlite_session.commit()

    svc = EmailRevealService()
    batch, contact_ids, skipped = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert len(contact_ids) == 0
    assert skipped == 1
    assert batch.skipped_revealed_count == 1


def test_enqueue_skips_fresh_email(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(
        sqlite_session, company,
        title_match=True,
        email="alice@acme.com",
        updated_at=_utcnow() - timedelta(days=5),
    )
    sqlite_session.commit()

    svc = EmailRevealService()
    _, contact_ids, skipped = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert len(contact_ids) == 0
    assert skipped == 1


def test_enqueue_includes_stale_email(sqlite_session: Session) -> None:
    from app.services.email_reveal_service import EmailRevealService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    c = _seed_contact(
        sqlite_session, company,
        title_match=True,
        email="alice@acme.com",
        updated_at=_utcnow() - timedelta(days=31),
    )
    sqlite_session.commit()

    svc = EmailRevealService()
    _, contact_ids, skipped = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        contact_ids=[c.id],
    )
    sqlite_session.commit()

    assert len(contact_ids) == 1
    assert skipped == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_email_reveal_service.py -k "test_enqueue" -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.email_reveal_service'`

- [ ] **Step 3: Create `app/services/email_reveal_service.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Company, Contact, ContactRevealBatch, Upload
from app.models.pipeline import ContactFetchBatchState

logger = logging.getLogger(__name__)

_REVEAL_FRESHNESS_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_eligible(contact: Contact) -> bool:
    if not contact.title_match:
        return False
    if contact.email is None:
        return True
    stale_cutoff = _utcnow() - timedelta(days=_REVEAL_FRESHNESS_DAYS)
    return contact.updated_at < stale_cutoff


def _smtp_to_confidence(smtp_status: str) -> float:
    if smtp_status == "valid":
        return 1.0
    if smtp_status == "unknown":
        return 0.5
    return 0.0


class EmailRevealService:
    def enqueue(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        contact_ids: list[UUID],
    ) -> tuple[ContactRevealBatch, list[UUID], int]:
        """Filter contact_ids to eligible, create batch, return (batch, eligible_ids, skipped).

        Caller defers reveal_email(contact_id) for each id in eligible_ids.
        """
        contacts = list(
            session.exec(
                select(Contact).where(col(Contact.id).in_(contact_ids))
            )
        )

        eligible: list[UUID] = []
        skipped = 0
        for contact in contacts:
            if _is_eligible(contact):
                eligible.append(contact.id)
            else:
                skipped += 1

        batch = ContactRevealBatch(
            campaign_id=campaign_id,
            trigger_source="manual",
            reveal_scope="selected",
            state=ContactFetchBatchState.QUEUED,
            selected_count=len(contact_ids),
            requested_count=len(eligible),
            queued_count=len(eligible),
            skipped_revealed_count=skipped,
        )
        session.add(batch)
        session.flush()

        return batch, eligible, skipped

    def run_reveal(self, *, engine: Any, contact_id: str) -> None:
        """Fetch email for one contact from its source provider and write it back."""
        raise NotImplementedError("Implemented in Task 2")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_email_reveal_service.py -k "test_enqueue" -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/email_reveal_service.py tests/test_email_reveal_service.py
git commit -m "feat(s4): enqueue service — eligibility filter + ContactRevealBatch creation"
```

---

## Task 2 — Worker: Snov reveal

**Files:**
- Modify: `app/services/email_reveal_service.py`
- Modify: `tests/test_email_reveal_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_email_reveal_service.py`:

```python
def test_run_reveal_snov_writes_email(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: (
            [{"email": "alice@acme.com", "smtp_status": "valid"}],
            "",
        ),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session, company,
        source_provider="snov",
        provider_person_id="snov-hash-1",
    )
    sqlite_session.commit()

    EmailRevealService().run_reveal(
        engine=sqlite_session.bind, contact_id=str(contact.id)
    )

    sqlite_session.refresh(contact)
    assert contact.email == "alice@acme.com"
    assert contact.email_provider == "snov"
    assert contact.email_confidence == 1.0
    assert contact.provider_email_status == "valid"
    assert contact.pipeline_stage == "email_revealed"


def test_run_reveal_snov_fallback_to_find_email_by_name(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: ([], ""),
    )
    monkeypatch.setattr(
        snov_mod.SnovClient,
        "find_email_by_name",
        lambda self, first, last, domain: (
            [{"email": "alice@acme.com", "smtp_status": "unknown"}],
            "",
        ),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session, company,
        source_provider="snov",
        provider_person_id="snov-hash-1",
    )
    sqlite_session.commit()

    EmailRevealService().run_reveal(
        engine=sqlite_session.bind, contact_id=str(contact.id)
    )

    sqlite_session.refresh(contact)
    assert contact.email == "alice@acme.com"
    assert contact.email_confidence == 0.5
    assert contact.pipeline_stage == "email_revealed"


def test_run_reveal_snov_no_email_leaves_contact_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: ([], ""),
    )
    monkeypatch.setattr(
        snov_mod.SnovClient,
        "find_email_by_name",
        lambda self, first, last, domain: ([], ""),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, source_provider="snov")
    sqlite_session.commit()

    EmailRevealService().run_reveal(
        engine=sqlite_session.bind, contact_id=str(contact.id)
    )

    sqlite_session.refresh(contact)
    assert contact.email is None
    assert contact.pipeline_stage == "fetched"


def test_run_reveal_snov_api_error_leaves_contact_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import snov_client as snov_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospect_email",
        lambda self, prospect_hash: ([], "snov_rate_limited"),
    )

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, source_provider="snov")
    sqlite_session.commit()

    EmailRevealService().run_reveal(
        engine=sqlite_session.bind, contact_id=str(contact.id)
    )

    sqlite_session.refresh(contact)
    assert contact.email is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_email_reveal_service.py -k "test_run_reveal_snov" -v
```
Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Implement `run_reveal` (Snov branch) in `app/services/email_reveal_service.py`**

Replace the `raise NotImplementedError` stub with:

```python
def run_reveal(self, *, engine: Any, contact_id: str) -> None:
    """Fetch email for one contact from its source provider and write it back."""
    from sqlmodel import Session

    cid = UUID(contact_id)

    with Session(engine) as session:
        contact = session.get(Contact, cid)
        if contact is None:
            logger.warning("reveal_email: contact %s not found", cid)
            return

        # Extract plain values before session closes
        provider = contact.source_provider
        provider_person_id = contact.provider_person_id
        first_name = contact.first_name
        last_name = contact.last_name
        company_id = contact.company_id

    with Session(engine) as session:
        company = session.get(Company, company_id)
        domain = company.domain if company else ""

    email: str | None = None
    smtp_status: str | None = None
    raw: dict = {}
    err = ""

    if provider == "snov":
        from app.services.snov_client import SnovClient
        client = SnovClient()
        emails, err = client.search_prospect_email(provider_person_id)
        if not err and emails:
            best = _best_email(emails)
            email = best.get("email")
            smtp_status = best.get("smtp_status")
            raw = best
        elif not err:
            # Fallback: name-based lookup
            emails, err = client.find_email_by_name(first_name, last_name, domain)
            if not err and emails:
                best = _best_email(emails)
                email = best.get("email")
                smtp_status = best.get("smtp_status")
                raw = best

    elif provider == "apollo":
        from app.services.apollo_client import ApolloClient
        client = ApolloClient()
        person = client.reveal_email(provider_person_id)
        if person:
            email = person.get("email") or None
            smtp_status = "valid" if email else None
            raw = person
        err = client.last_error_code if not person else ""

    else:
        logger.warning("reveal_email: unknown source_provider %r for contact %s", provider, cid)
        return

    if err:
        logger.warning("reveal_email: provider error %r for contact %s", err, cid)
        return

    if not email:
        return

    confidence = _smtp_to_confidence(smtp_status or "")

    with Session(engine) as session:
        contact = session.get(Contact, cid)
        if contact is None:
            return
        contact.email = email
        contact.email_provider = provider
        contact.email_confidence = confidence
        contact.provider_email_status = smtp_status
        contact.reveal_raw_json = raw
        contact.pipeline_stage = "email_revealed"
        contact.updated_at = _utcnow()
        session.add(contact)
        session.commit()
```

Add the helper at module level (before the class):

```python
def _best_email(emails: list[dict]) -> dict:
    """Pick the highest-confidence email from a Snov email list."""
    order = {"valid": 0, "unknown": 1}
    return min(emails, key=lambda e: order.get(e.get("smtp_status", ""), 2))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_email_reveal_service.py -k "test_run_reveal_snov" -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/email_reveal_service.py tests/test_email_reveal_service.py
git commit -m "feat(s4): run_reveal — Snov branch with hash lookup + name fallback"
```

---

## Task 3 — Worker: Apollo reveal

**Files:**
- Modify: `tests/test_email_reveal_service.py`
- (No new service code needed — Apollo branch is already included in Task 2's `run_reveal`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_email_reveal_service.py`:

```python
def test_run_reveal_apollo_writes_email(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        apollo_mod.ApolloClient,
        "reveal_email",
        lambda self, person_id: {"id": person_id, "email": "bob@acme.com"},
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "last_error_code", "", raising=False)

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(
        sqlite_session, company,
        source_provider="apollo",
        provider_person_id="apollo-id-1",
    )
    sqlite_session.commit()

    EmailRevealService().run_reveal(
        engine=sqlite_session.bind, contact_id=str(contact.id)
    )

    sqlite_session.refresh(contact)
    assert contact.email == "bob@acme.com"
    assert contact.email_provider == "apollo"
    assert contact.email_confidence == 1.0
    assert contact.pipeline_stage == "email_revealed"


def test_run_reveal_apollo_no_email_leaves_contact_untouched(sqlite_session: Session, monkeypatch) -> None:
    from app.services.email_reveal_service import EmailRevealService
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        apollo_mod.ApolloClient,
        "reveal_email",
        lambda self, person_id: {"id": person_id, "email": None},
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "last_error_code", "", raising=False)

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    contact = _seed_contact(sqlite_session, company, source_provider="apollo")
    sqlite_session.commit()

    EmailRevealService().run_reveal(
        engine=sqlite_session.bind, contact_id=str(contact.id)
    )

    sqlite_session.refresh(contact)
    assert contact.email is None
    assert contact.pipeline_stage == "fetched"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_email_reveal_service.py -k "test_run_reveal_apollo" -v
```
Expected: FAIL — Apollo branch in `run_reveal` checks `client.last_error_code` as instance attribute but monkeypatch sets it on the class. Verify exact failure message.

- [ ] **Step 3: Fix `run_reveal` Apollo branch — `last_error_code` is an instance attribute**

In the Apollo branch of `run_reveal`, `err = client.last_error_code if not person else ""` already reads from the instance. The monkeypatch in the test sets it on the class which propagates to the instance. Tests should pass — run them before assuming a fix is needed.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_email_reveal_service.py -k "test_run_reveal_apollo" -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_email_reveal_service.py
git commit -m "test(s4): add Apollo reveal tests"
```

---

## Task 4 — Update the job stub

**Files:**
- Modify: `app/jobs/email_reveal.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_email_reveal_service.py`:

```python
def test_reveal_email_task_accepts_contact_id() -> None:
    import inspect
    from app.jobs.email_reveal import reveal_email

    fn = getattr(reveal_email, "original_func", reveal_email)
    sig = inspect.signature(fn)
    assert "contact_id" in sig.parameters
```

- [ ] **Step 2: Run to verify it passes (already passes — stub has contact_id)**

```bash
uv run pytest tests/test_email_reveal_service.py::test_reveal_email_task_accepts_contact_id -v
```
Expected: PASS (the existing stub already has `contact_id: str`).

- [ ] **Step 3: Replace the stub body in `app/jobs/email_reveal.py`**

```python
"""Procrastinate task: reveal email for one Contact."""
from __future__ import annotations

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app


@app.task(name="reveal_email", queue="email_reveal")
async def reveal_email(contact_id: str) -> None:
    from app.services.email_reveal_service import EmailRevealService
    EmailRevealService().run_reveal(
        engine=get_engine(),
        contact_id=contact_id,
    )
```

- [ ] **Step 4: Run all service tests**

```bash
uv run pytest tests/test_email_reveal_service.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/jobs/email_reveal.py tests/test_email_reveal_service.py
git commit -m "feat(s4): wire reveal_email task to EmailRevealService"
```

---

## Task 5 — API endpoint: `POST /v1/contacts/reveal`

**Files:**
- Modify: `app/api/routes/contacts.py`
- Create: `tests/test_email_reveal_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email_reveal_api.py
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
        provider_person_id="snov-1",
        first_name="Alice",
        last_name="Smith",
        title_match=True,
        email=None,
    )
    session.add(contact)
    session.flush()
    return co, contact


@pytest.mark.asyncio
async def test_reveal_endpoint_defers_tasks_for_eligible(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import reveal_contacts
    from app.api.schemas.contacts import ContactRevealRequest
    from app.jobs import email_reveal as er_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(er_mod.reveal_email, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s4"), session=sqlite_session)
    _, contact = _seed(sqlite_session, campaign.id)
    sqlite_session.commit()

    result = await reveal_contacts(
        payload=ContactRevealRequest(
            campaign_id=campaign.id,
            discovered_contact_ids=[contact.id],
        ),
        session=sqlite_session,
    )

    assert result.queued_count == 1
    assert result.skipped_revealed_count == 0
    assert len(deferred) == 1
    assert deferred[0]["contact_id"] == str(contact.id)


@pytest.mark.asyncio
async def test_reveal_endpoint_skips_no_title_match(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import reveal_contacts
    from app.api.schemas.contacts import ContactRevealRequest
    from app.jobs import email_reveal as er_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(er_mod.reveal_email, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s4"), session=sqlite_session)
    _, contact = _seed(sqlite_session, campaign.id)
    contact.title_match = False
    sqlite_session.flush()
    sqlite_session.commit()

    result = await reveal_contacts(
        payload=ContactRevealRequest(
            campaign_id=campaign.id,
            discovered_contact_ids=[contact.id],
        ),
        session=sqlite_session,
    )

    assert result.queued_count == 0
    assert result.skipped_revealed_count == 1
    assert len(deferred) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_email_reveal_api.py -v
```
Expected: FAIL — `cannot import name 'reveal_contacts'`

- [ ] **Step 3: Add imports to `app/api/routes/contacts.py`**

Add to the imports block in `contacts.py`:

```python
from app.api.schemas.contacts import (
    ...existing imports...,
    ContactRevealRequest,
    ContactRevealResult,
)
from app.jobs.email_reveal import reveal_email as _reveal_email_task
from app.services.email_reveal_service import EmailRevealService

_email_reveal_service = EmailRevealService()
```

- [ ] **Step 4: Add the endpoint to `app/api/routes/contacts.py`**

Add before the `title-match-rules` block:

```python
@router.post("/contacts/reveal", response_model=ContactRevealResult)
async def reveal_contacts(
    payload: ContactRevealRequest,
    session: Session = Depends(get_session),
) -> ContactRevealResult:
    _campaign_or_404(session=session, campaign_id=payload.campaign_id)

    contact_ids = list(payload.discovered_contact_ids or [])
    if not contact_ids:
        return ContactRevealResult(
            selected_count=0,
            queued_count=0,
            already_revealing_count=0,
            skipped_revealed_count=0,
            message="No contacts selected.",
        )

    batch, eligible_ids, skipped = _email_reveal_service.enqueue(
        session=session,
        campaign_id=payload.campaign_id,
        contact_ids=contact_ids,
    )
    session.commit()
    session.refresh(batch)

    defer_failed = 0
    for cid in eligible_ids:
        try:
            await _reveal_email_task.defer_async(contact_id=str(cid))
        except Exception:
            defer_failed += 1

    queued = len(eligible_ids) - defer_failed

    return ContactRevealResult(
        batch_id=batch.id,
        selected_count=len(contact_ids),
        queued_count=queued,
        already_revealing_count=0,
        skipped_revealed_count=skipped,
        message=f"Queued email reveal for {queued} contact(s). {skipped} skipped.",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_email_reveal_api.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes/contacts.py app/jobs/email_reveal.py tests/test_email_reveal_api.py
git commit -m "feat(s4): implement POST /v1/contacts/reveal"
```

---

## Task 6 — Full suite + regression check

- [ ] **Step 1: Run all S4 tests**

```bash
uv run pytest tests/test_email_reveal_service.py tests/test_email_reveal_api.py -v
```
Expected: all pass.

- [ ] **Step 2: Run the full suite (excluding known pre-existing failures)**

```bash
uv run pytest tests/ --ignore=tests/test_analysis_usage_events.py -q --tb=short
```
Expected: no new failures beyond the pre-existing 16.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(s4): complete email reveal vertical slice"
```
