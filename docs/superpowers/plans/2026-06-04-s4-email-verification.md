# S4 Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the S4 Email Verification stage: a backend-driven contact/email table that validates `contacts.selected_email` through ZeroBounce with 30-day cache reuse, snapshot-safe batches, live counts, and a provider-aware but operator-simple UI.

**Architecture:** Add a small email verification cache table and an `EmailVerificationService` that owns row bucketing, preview, batch creation, cache reuse, and worker writeback. Expose a new `/v1/email-verification` API namespace and a separate `validation` Procrastinate queue. Replace the mock validation view with a real S4 table that mirrors the S1-S3 conventions.

**Tech Stack:** FastAPI, SQLModel, Alembic, Procrastinate, ZeroBounce HTTP API, React/Vite, Node test runner, pytest.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/models/contacts.py` | Modify | Add `EmailVerificationCache`; add batch snapshot/summary fields. |
| `app/models/__init__.py` | Modify | Export the cache model. |
| `alembic/versions/f6a7b8c9d0e1_email_verification_cache.py` | Create | Add cache table and `verification_batches` metadata columns. |
| `alembic/versions/a8b9c0d1e2f3_verification_batch_notify_trigger.py` | Create | Notify `job_events` on S4 batch changes. |
| `app/api/schemas/email_verification.py` | Create | Request/response models for S4 rows, counts, preview, and batches. |
| `app/services/email_verification_service.py` | Create | S4 row bucketing, list/counts, preview, confirm, cache reuse, worker logic. |
| `app/api/routes/email_verification.py` | Create | HTTP API namespace `/v1/email-verification`. |
| `app/jobs/validation.py` | Create | Procrastinate task for S4 batches on queue `validation`. |
| `app/queue.py` | Modify | Register `app.jobs.validation`. |
| `app/api/routes/events.py` | Modify | Emit S4 SSE events for verification batches. |
| `app/main.py` | Modify | Include the email verification router. |
| `app/services/campaign_stage_counts.py` | Modify | Count pending, stale, failed technical, and checking for shared S4 badge. |
| `app/api/schemas/campaign.py` | Modify | Add `stale`, `catch_all`, `undeliverable`, and `failed` fields to validation counts. |
| `app/services/zerobounce_client.py` | Modify | Add credential check and normalize batch response address keys. |
| `scripts/run_worker.sh` | Modify | Default `validation` queue concurrency to 1. |
| `docker-compose.yml` | Modify | Add `worker-validation`. |
| `tests/test_email_verification_service.py` | Create | Backend service tests. |
| `tests/test_email_verification_api.py` | Create | API route tests. |
| `tests/test_campaign_stage_counts.py` | Modify | S4 badge/stale/count behavior. |
| `tests/test_run_worker_script.py` | Modify | Validation worker defaults and compose service. |
| `apps/web/src/lib/types.ts` | Modify | Add S4 API types and replace old S5 validation assumptions. |
| `apps/web/src/lib/api.ts` | Modify | Add S4 API client functions; remove stale `verifyContacts` expectation. |
| `apps/web/src/lib/navigation.ts` | Modify | Replace `s4-reveal`/`s5-validation` with `s4-validation`. |
| `apps/web/src/App.tsx` | Modify | Route real S4 view and wire stage count refresh. |
| `apps/web/src/components/views/validation/ValidationView.tsx` | Rewrite | Real S4 Email Verification screen orchestration. |
| `apps/web/src/components/views/validation/ValidationTable.tsx` | Rewrite | Desktop contact/email table. |
| `apps/web/src/components/views/validation/ValidationCards.tsx` | Rewrite | Mobile contact/email cards. |
| `apps/web/src/components/views/validation/ValidationStatusBadge.tsx` | Rewrite | S4 status bucket labels. |
| `apps/web/src/components/views/validation/EmailVerificationPreviewDialog.tsx` | Create | Preview-confirm dialog for inline, selected, and matching actions. |
| `apps/web/src/components/layout/Sidebar.tsx` | Modify | Use S4 Validation navigation key and shared stage counts. |
| `apps/web/src/components/layout/BottomNav.tsx` | Modify | Use S4 Validation navigation key and shared stage counts. |
| `apps/web/src/components/layout/AppShell.tsx` | Modify | Use S4 Validation route metadata. |
| `apps/web/src/components/layout/header/LiveStatus.tsx` | Modify | Map `s4-validation` to validation live status. |
| `apps/web/tests/validationNavigation.test.ts` | Create | Frontend route naming contract. |
| `apps/web/tests/validationStageParity.test.ts` | Create | S4 table convention contract. |
| `apps/web/tests/validationLiveRefresh.test.ts` | Create | S4 live refresh contract. |
| `apps/web/tests/validationSelection.test.ts` | Create | S4 selection and preview contract. |
| `apps/web/tests/apiContracts.test.ts` | Modify | Replace old `verifyContacts` contract with S4 preview/batch contracts. |

---

## Task 1: Schema And Models

**Files:**
- Modify: `app/models/contacts.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/f6a7b8c9d0e1_email_verification_cache.py`
- Create: `tests/test_email_verification_service.py`

- [ ] **Step 1: Write failing model/cache tests**

Add this starter test file:

```python
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Campaign, Contact, EmailVerificationCache, UploadedDomain
from app.models.base import utcnow


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _campaign_domain(session: Session) -> tuple[Campaign, UploadedDomain]:
    campaign = Campaign(id=uuid4(), name="S4 Campaign")
    domain = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        dedupe_key="example.com",
    )
    session.add_all([campaign, domain])
    session.commit()
    return campaign, domain


def _contact(session: Session, campaign: Campaign, domain: UploadedDomain, email: str | None = "ada@example.com") -> Contact:
    contact = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Ada",
        last_name="Lovelace",
        title="Marketing Director",
        title_match=True,
        selected_email=email,
    )
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


def test_email_verification_cache_persists_normalized_email(db_session: Session) -> None:
    row = EmailVerificationCache(
        normalized_email="ada@example.com",
        provider="zerobounce",
        status="valid",
        sub_status=None,
        raw_json={"address": "ada@example.com", "status": "valid"},
        validated_at=utcnow(),
    )
    db_session.add(row)
    db_session.commit()

    saved = db_session.exec(select(EmailVerificationCache)).one()
    assert saved.normalized_email == "ada@example.com"
    assert saved.provider == "zerobounce"
    assert saved.status == "valid"
    assert saved.raw_json["status"] == "valid"


def test_contact_ready_rule_uses_current_email_snapshot(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    contact = _contact(db_session, campaign, domain)
    contact.verified_email_snapshot = "ada@example.com"
    contact.verification_status = "valid"
    contact.verification_applied = True
    contact.verified_at = utcnow() - timedelta(days=2)
    db_session.add(contact)
    db_session.commit()

    from app.services.email_verification_service import is_campaign_ready_contact

    assert is_campaign_ready_contact(contact, now=utcnow()) is True

    contact.selected_email = "new@example.com"
    assert is_campaign_ready_contact(contact, now=utcnow()) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py -k "cache_persists or ready_rule"
```

Expected: FAIL because `EmailVerificationCache` and `app.services.email_verification_service` do not exist.

- [ ] **Step 3: Add the cache model**

In `app/models/contacts.py`, add:

```python
class EmailVerificationCache(SQLModel, table=True):
    """Reusable ZeroBounce result keyed by normalized email."""

    __tablename__ = "email_verification_cache"
    __table_args__ = (
        Index("ux_email_verification_cache_provider_email", "provider", "normalized_email", unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    provider: str = Field(default="zerobounce", max_length=32, index=True)
    normalized_email: str = Field(max_length=512, index=True)
    status: str = Field(max_length=32, index=True)
    sub_status: str | None = Field(default=None, max_length=64)
    raw_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    validated_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    updated_at: datetime = utc_datetime_field(default_factory=utcnow)
```

Also add optional metadata to `VerificationBatch`:

```python
    selected_contact_snapshots_json: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    result_summary_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
```

Export `EmailVerificationCache` from `app/models/__init__.py`.

- [ ] **Step 4: Add Alembic migration**

Create `alembic/versions/f6a7b8c9d0e1_email_verification_cache.py` with `revision = "f6a7b8c9d0e1"` and `down_revision = "a7b8c9d0e1f2"`. The migration must:

```python
op.create_table(
    "email_verification_cache",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("provider", sa.String(length=32), nullable=False),
    sa.Column("normalized_email", sa.String(length=512), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("sub_status", sa.String(length=64), nullable=True),
    sa.Column("raw_json", sa.JSON(), nullable=True),
    sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("id"),
)
op.create_index("ix_email_verification_cache_id", "email_verification_cache", ["id"])
op.create_index("ix_email_verification_cache_provider", "email_verification_cache", ["provider"])
op.create_index("ix_email_verification_cache_normalized_email", "email_verification_cache", ["normalized_email"])
op.create_index("ix_email_verification_cache_status", "email_verification_cache", ["status"])
op.create_index("ix_email_verification_cache_validated_at", "email_verification_cache", ["validated_at"])
op.create_index(
    "ux_email_verification_cache_provider_email",
    "email_verification_cache",
    ["provider", "normalized_email"],
    unique=True,
)
op.add_column("verification_batches", sa.Column("selected_contact_snapshots_json", sa.JSON(), nullable=True))
op.add_column("verification_batches", sa.Column("result_summary_json", sa.JSON(), nullable=True))
```

Downgrade drops those columns, indexes, and table in reverse order.

- [ ] **Step 5: Add minimal ready-rule helper**

Create `app/services/email_verification_service.py` with:

```python
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.contacts import Contact

VERIFICATION_STALE_AFTER_DAYS = 30
MAX_EMAILS_PER_BATCH = 200


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def is_fresh_verified_at(verified_at: datetime | None, *, now: datetime) -> bool:
    if verified_at is None:
        return False
    return verified_at >= now - timedelta(days=VERIFICATION_STALE_AFTER_DAYS)


def is_campaign_ready_contact(contact: Contact, *, now: datetime) -> bool:
    selected = normalize_email(contact.selected_email)
    snapshot = normalize_email(contact.verified_email_snapshot)
    return (
        bool(selected)
        and contact.verification_applied is True
        and (contact.verification_status or "").lower() == "valid"
        and selected == snapshot
        and is_fresh_verified_at(contact.verified_at, now=now)
    )
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py -k "cache_persists or ready_rule"
```

Expected: PASS.

Commit:

```bash
git add app/models/contacts.py app/models/__init__.py app/services/email_verification_service.py alembic/versions/f6a7b8c9d0e1_email_verification_cache.py tests/test_email_verification_service.py
git commit -m "feat(s4): add email verification cache schema"
```

---

## Task 2: Status Buckets And Shared Counts

**Files:**
- Modify: `app/services/email_verification_service.py`
- Modify: `app/services/campaign_stage_counts.py`
- Modify: `app/api/schemas/campaign.py`
- Modify: `tests/test_email_verification_service.py`
- Modify: `tests/test_campaign_stage_counts.py`

- [ ] **Step 1: Write failing status bucket tests**

Append to `tests/test_email_verification_service.py`:

```python
from datetime import timedelta


def test_status_bucket_pending_stale_and_checking(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    pending = _contact(db_session, campaign, domain, "pending@example.com")
    checking = _contact(db_session, campaign, domain, "checking@example.com")
    stale = _contact(db_session, campaign, domain, "stale@example.com")

    checking.verification_batch_id = uuid4()
    checking.verified_email_snapshot = "checking@example.com"
    checking.verification_applied = False

    stale.verified_email_snapshot = "stale@example.com"
    stale.verification_status = "valid"
    stale.verification_applied = True
    stale.verified_at = utcnow() - timedelta(days=31)
    db_session.add_all([pending, checking, stale])
    db_session.commit()

    from app.services.email_verification_service import contact_verification_bucket

    now = utcnow()
    assert contact_verification_bucket(pending, now=now) == "pending"
    assert contact_verification_bucket(checking, now=now) == "checking"
    assert contact_verification_bucket(stale, now=now) == "stale"


def test_status_bucket_maps_zerobounce_results(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    valid = _contact(db_session, campaign, domain, "valid@example.com")
    invalid = _contact(db_session, campaign, domain, "invalid@example.com")
    catch_all = _contact(db_session, campaign, domain, "catch@example.com")
    unknown = _contact(db_session, campaign, domain, "unknown@example.com")
    failed = _contact(db_session, campaign, domain, "failed@example.com")

    for contact, status in [
        (valid, "valid"),
        (invalid, "do_not_mail"),
        (catch_all, "catch_all"),
        (unknown, "unknown"),
    ]:
        contact.verified_email_snapshot = contact.selected_email
        contact.verification_status = status
        contact.verification_applied = True
        contact.verified_at = utcnow()

    failed.verified_email_snapshot = failed.selected_email
    failed.verification_status = "failed"
    failed.verification_sub_status = "zerobounce_failed"
    failed.verification_applied = False

    db_session.add_all([valid, invalid, catch_all, unknown, failed])
    db_session.commit()

    from app.services.email_verification_service import contact_verification_bucket

    now = utcnow()
    assert contact_verification_bucket(valid, now=now) == "valid"
    assert contact_verification_bucket(invalid, now=now) == "undeliverable"
    assert contact_verification_bucket(catch_all, now=now) == "catch_all"
    assert contact_verification_bucket(unknown, now=now) == "unknown"
    assert contact_verification_bucket(failed, now=now) == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py -k "status_bucket"
```

Expected: FAIL because `contact_verification_bucket` is not defined.

- [ ] **Step 3: Implement bucket helpers**

Add to `app/services/email_verification_service.py`:

```python
RESULT_UNDELIVERABLE = {"invalid", "do_not_mail", "spamtrap", "abuse"}
RESULT_VALID = {"valid", "deliverable"}
RESULT_CATCH_ALL = {"catch-all", "catch_all"}
RESULT_UNKNOWN = {"unknown"}
ACTIONABLE_BUCKETS = {"pending", "stale", "failed"}


def normalize_zerobounce_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value == "catch-all":
        return "catch_all"
    return value or "unknown"


def contact_verification_bucket(contact: Contact, *, now: datetime) -> str:
    selected = normalize_email(contact.selected_email)
    if not selected:
        return "no_email"
    snapshot = normalize_email(contact.verified_email_snapshot)
    status = normalize_zerobounce_status(contact.verification_status)
    if contact.verification_batch_id and contact.verification_applied is False:
        return "checking"
    if status == "failed" and contact.verification_applied is False:
        return "failed"
    if not contact.verification_applied or not snapshot:
        return "pending"
    if snapshot != selected:
        return "pending"
    if not is_fresh_verified_at(contact.verified_at, now=now):
        return "stale"
    if status in RESULT_VALID:
        return "valid"
    if status in RESULT_UNDELIVERABLE:
        return "undeliverable"
    if status in RESULT_CATCH_ALL:
        return "catch_all"
    if status in RESULT_UNKNOWN:
        return "unknown"
    return "unknown"
```

- [ ] **Step 4: Extend campaign validation counts**

In `app/api/schemas/campaign.py`, replace `ValidationStageCounts` with:

```python
class ValidationStageCounts(BaseModel):
    badge: int = 0
    total: int = 0
    pending: int = 0
    checking: int = 0
    running: int = 0
    stale: int = 0
    valid: int = 0
    undeliverable: int = 0
    catch_all: int = 0
    unknown: int = 0
    failed: int = 0
    invalid: int = 0
    is_live: bool = False
```

Keep `running` as an alias for compatibility in shared code until the frontend is migrated. Set `invalid` equal to `undeliverable` during this transition.

In `app/services/campaign_stage_counts.py`, replace `_validation_counts` with a contact iteration using `contact_verification_bucket`. Query only `Contact.selected_email IS NOT NULL` for the campaign. Badge must be:

```python
badge = pending + stale + failed + checking
```

Set `running=checking`, `invalid=undeliverable`, and `is_live=checking > 0`.

- [ ] **Step 5: Add failing shared count assertion**

Update `tests/test_campaign_stage_counts.py` to seed one stale, one failed, and one catch-all contact. Add assertions:

```python
assert out.validation.pending == 1
assert out.validation.valid == 1
assert out.validation.stale == 1
assert out.validation.failed == 1
assert out.validation.catch_all == 1
assert out.validation.badge == 3
```

The badge is `pending + stale + failed + checking`; valid and catch-all do not count as actionable work.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py tests/test_campaign_stage_counts.py
```

Expected: PASS.

Commit:

```bash
git add app/services/email_verification_service.py app/services/campaign_stage_counts.py app/api/schemas/campaign.py tests/test_email_verification_service.py tests/test_campaign_stage_counts.py
git commit -m "feat(s4): derive email verification status counts"
```

---

## Task 3: S4 Listing, IDs, Letter Counts, And Preview

**Files:**
- Create: `app/api/schemas/email_verification.py`
- Modify: `app/services/email_verification_service.py`
- Modify: `tests/test_email_verification_service.py`

- [ ] **Step 1: Write failing list and preview tests**

Append to `tests/test_email_verification_service.py`:

```python
def test_list_contacts_shows_only_contacts_with_email_and_filters_by_domain_letter(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    _contact(db_session, campaign, domain, "ada@example.com")
    _contact(db_session, campaign, domain, None)

    from app.services.email_verification_service import EmailVerificationService

    out = EmailVerificationService().list_contacts(
        session=db_session,
        campaign_id=campaign.id,
        status="all",
        search=None,
        letter="E",
        limit=50,
        offset=0,
    )

    assert out.total == 1
    assert out.counts.all == 1
    assert out.items[0].selected_email == "ada@example.com"
    assert out.items[0].domain == "example.com"
    assert out.items[0].status == "pending"


def test_preview_reports_cached_paid_and_skipped_counts(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    pending = _contact(db_session, campaign, domain, "pending@example.com")
    cached = _contact(db_session, campaign, domain, "cached@example.com")
    valid = _contact(db_session, campaign, domain, "valid@example.com")

    valid.verified_email_snapshot = "valid@example.com"
    valid.verification_status = "valid"
    valid.verification_applied = True
    valid.verified_at = utcnow()
    db_session.add(valid)
    db_session.add(
        EmailVerificationCache(
            provider="zerobounce",
            normalized_email="cached@example.com",
            status="valid",
            raw_json={"address": "cached@example.com", "status": "valid"},
            validated_at=utcnow(),
        )
    )
    db_session.commit()

    from app.services.email_verification_service import EmailVerificationService

    preview = EmailVerificationService().preview(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[pending.id, cached.id, valid.id],
    )

    assert preview.selected_count == 3
    assert preview.eligible_count == 2
    assert preview.cached_count == 1
    assert preview.paid_validation_count == 1
    assert preview.skipped_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py -k "list_contacts_shows_only or preview_reports"
```

Expected: FAIL because service methods and schemas do not exist.

- [ ] **Step 3: Add S4 schemas**

Create `app/api/schemas/email_verification.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.base import UTCReadModel

EmailVerificationStatus = Literal[
    "pending",
    "checking",
    "stale",
    "valid",
    "undeliverable",
    "catch_all",
    "unknown",
    "failed",
]


class EmailVerificationCounts(BaseModel):
    all: int = 0
    pending: int = 0
    checking: int = 0
    stale: int = 0
    valid: int = 0
    undeliverable: int = 0
    catch_all: int = 0
    unknown: int = 0
    failed: int = 0

    model_config = ConfigDict(from_attributes=True)


class EmailVerificationContactRow(UTCReadModel):
    contact_id: UUID
    campaign_id: UUID
    domain_id: UUID
    domain: str
    first_name: str
    last_name: str
    title: str | None
    linkedin_url: str | None
    selected_email: str
    status: str
    raw_status: str | None
    sub_status: str | None
    verified_at: datetime | None
    updated_at: datetime
    action_label: str | None

    model_config = ConfigDict(from_attributes=True)


class EmailVerificationContactList(BaseModel):
    total: int
    limit: int
    offset: int
    counts: EmailVerificationCounts
    items: list[EmailVerificationContactRow]


class EmailVerificationContactIds(BaseModel):
    ids: list[UUID]
    total: int
    limit: int
    offset: int


class EmailVerificationPreviewRequest(BaseModel):
    campaign_id: UUID
    contact_ids: list[UUID] = Field(min_length=1, max_length=200)


class EmailVerificationPreviewRead(BaseModel):
    campaign_id: UUID
    selected_count: int
    eligible_count: int
    cached_count: int
    paid_validation_count: int
    skipped_count: int
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
    max_batch_size: int = 200
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Implement list, ids, letters, and preview**

In `EmailVerificationService`, add:

```python
class EmailVerificationServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
```

Implement these public methods with the same query style as `EmailFetchService`:

```text
list_contacts(session, campaign_id, status="all", search=None, letter=None, limit=50, offset=0) -> EmailVerificationContactList
list_contact_ids(session, campaign_id, status="all", search=None, letter=None, actionable_only=False, limit=200, offset=0) -> EmailVerificationContactIds
get_letter_counts(session, campaign_id, status="all", search=None) -> dict[str, int]
preview(session, campaign_id, contact_ids) -> EmailVerificationPreviewRead
```

Implementation rules:

- Ensure campaign exists or raise `campaign_not_found`.
- Base list joins `Contact` to `UploadedDomain`.
- Include only `Contact.selected_email IS NOT NULL`.
- Letter bucket is based on `UploadedDomain.domain`.
- Search uses `domain`, `first_name`, `last_name`, `title`, and `selected_email`.
- Compute buckets with `contact_verification_bucket`.
- `actionable_only` includes only `pending`, `stale`, `failed`.
- Preview resolves selected ids in campaign scope, caps at 200, skips non-actionable rows, and checks fresh cache rows within 30 days.
- `action_label` is `Revalidate` for `stale`, `Validate` for `pending` or `failed`, and `None` otherwise.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py
```

Expected: PASS.

Commit:

```bash
git add app/api/schemas/email_verification.py app/services/email_verification_service.py tests/test_email_verification_service.py
git commit -m "feat(s4): list and preview email verification contacts"
```

---

## Task 4: Batch Creation, Cache Reuse, And Worker Writeback

**Files:**
- Modify: `app/services/email_verification_service.py`
- Create: `app/jobs/validation.py`
- Modify: `app/services/zerobounce_client.py`
- Modify: `tests/test_email_verification_service.py`

- [ ] **Step 1: Write failing batch and worker tests**

Append to `tests/test_email_verification_service.py`:

```python
class FakeZeroBounce:
    def __init__(self, results: list[dict], error: str = "") -> None:
        self.results = results
        self.error = error
        self.calls: list[list[str]] = []

    def check_credentials(self) -> tuple[bool, str, str]:
        return True, "", "ok"

    def validate_batch(self, emails: list[str], *, timeout_sec: int = 45):  # noqa: ANN001
        self.calls.append(emails)
        return self.results, self.error


def test_create_batch_snapshots_contacts_and_marks_checking(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    contact = _contact(db_session, campaign, domain, "ada@example.com")

    from app.services.email_verification_service import EmailVerificationService

    batch = EmailVerificationService(zerobounce=FakeZeroBounce([])).create_batch(
        session=db_session,
        campaign_id=campaign.id,
        contact_ids=[contact.id],
    )

    db_session.refresh(contact)
    assert batch.selected_count == 1
    assert batch.queued_count == 1
    assert batch.selected_contact_snapshots_json == [{"contact_id": str(contact.id), "email": "ada@example.com"}]
    assert contact.verification_batch_id == batch.id
    assert contact.verified_email_snapshot == "ada@example.com"
    assert contact.verification_applied is False


def test_run_batch_applies_cache_without_provider_call(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    contact = _contact(db_session, campaign, domain, "cached@example.com")
    db_session.add(
        EmailVerificationCache(
            provider="zerobounce",
            normalized_email="cached@example.com",
            status="valid",
            raw_json={"address": "cached@example.com", "status": "valid"},
            validated_at=utcnow(),
        )
    )
    db_session.commit()

    fake = FakeZeroBounce([])
    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(session=db_session, campaign_id=campaign.id, contact_ids=[contact.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(contact)
    assert fake.calls == []
    assert contact.verification_status == "valid"
    assert contact.verification_applied is True
    assert contact.verification_batch_id is None


def test_run_batch_calls_zerobounce_and_writes_cache(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    contact = _contact(db_session, campaign, domain, "paid@example.com")

    fake = FakeZeroBounce([{"address": "paid@example.com", "status": "catch-all", "sub_status": "mailbox_quota_exceeded"}])
    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(session=db_session, campaign_id=campaign.id, contact_ids=[contact.id])
    service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(contact)
    cache = db_session.exec(select(EmailVerificationCache)).one()
    assert fake.calls == [["paid@example.com"]]
    assert contact.verification_status == "catch_all"
    assert contact.verification_sub_status == "mailbox_quota_exceeded"
    assert contact.verification_applied is True
    assert cache.normalized_email == "paid@example.com"
    assert cache.status == "catch_all"


def test_run_batch_skips_writeback_when_email_changed(db_session: Session) -> None:
    campaign, domain = _campaign_domain(db_session)
    contact = _contact(db_session, campaign, domain, "old@example.com")

    fake = FakeZeroBounce([{"address": "old@example.com", "status": "valid"}])
    from app.services.email_verification_service import EmailVerificationService

    service = EmailVerificationService(zerobounce=fake)
    batch = service.create_batch(session=db_session, campaign_id=campaign.id, contact_ids=[contact.id])
    contact.selected_email = "new@example.com"
    db_session.add(contact)
    db_session.commit()

    service.run_batch(session=db_session, batch_id=batch.id)

    db_session.refresh(contact)
    assert contact.verification_status is None
    assert contact.verification_applied is False
    assert contact.verification_batch_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py -k "create_batch or run_batch"
```

Expected: FAIL because batch methods do not exist.

- [ ] **Step 3: Implement batch creation**

Add `EmailVerificationBatchCreate` and `EmailVerificationBatchRead` schemas to `app/api/schemas/email_verification.py`.

Implement `EmailVerificationService.create_batch`:

- Resolve eligible contacts from `contact_ids`.
- Use preview logic to reject zero eligible rows with `no_eligible_contacts`.
- If `paid_validation_count > 0`, call `zerobounce.check_credentials()` and raise `zerobounce_api_key_missing` or `zerobounce_auth_failed` when not ok.
- Create `VerificationBatch` with:
  - `state="queued"`
  - `selected_count=len(contact_ids)`
  - `queued_count=len(eligible)`
  - `selected_contact_snapshots_json=[{"contact_id": str(id), "email": normalized_email}]`
  - `result_summary_json={"cached_count": preview.cached_count, "paid_validation_count": preview.paid_validation_count, "skipped_count": preview.skipped_count}`
- Set each eligible contact to checking:
  - `verification_batch_id=batch.id`
  - `verified_email_snapshot=normalized_email`
  - `verification_applied=False`
  - `verification_status=None`
  - `verification_sub_status=None`
  - `verification_raw_json=None`

- [ ] **Step 4: Implement worker run path**

Implement `EmailVerificationService.run_batch`:

- Load batch and snapshots.
- If batch terminal state is `succeeded` or `failed`, return it.
- Set batch `state="running"`.
- For each snapshot, load current contact.
- If contact missing, email missing, or current `selected_email` no longer equals snapshot email, clear any matching `verification_batch_id` and count skipped.
- For remaining snapshots, apply fresh cache results first.
- For paid misses, call `zerobounce.validate_batch(emails)`.
- Normalize provider result address using `address` or `email_address`.
- Upsert each provider result into `EmailVerificationCache`.
- Apply each result to matching contact:
  - `verification_status=normalize_zerobounce_status(result["status"])`
  - `verification_sub_status=result.get("sub_status")`
  - `verification_raw_json={"provider": "zerobounce", "source": "cache" | "api", "result": result}`
  - `verification_applied=True`
  - `verified_at=cache.validated_at or utcnow()`
  - `verification_batch_id=None`
- On provider technical error, set remaining contacts to technical failed:
  - `verification_status="failed"`
  - `verification_sub_status=error_code`
  - `verification_raw_json={"provider": "zerobounce", "error_code": error_code}`
  - `verification_applied=False`
  - `verification_batch_id=None`
- Finalize batch with `verified_count`, `valid_count`, `invalid_count`, `skipped_count`, `queued_count=0`, and `finished_at`.

- [ ] **Step 5: Add ZeroBounce credential check**

In `app/services/zerobounce_client.py`, add:

```python
    def check_credentials(self) -> tuple[bool, str, str]:
        api_key = self._resolve_api_key()
        if not api_key:
            return False, ERR_ZEROBOUNCE_KEY_MISSING, "ZeroBounce API key is missing."
        try:
            response = httpx.get(
                f"{self._base_url}/v2/getcredits",
                params={"api_key": api_key},
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "zerobounce_credential_check_http_error", error=str(exc))
            return False, ERR_ZEROBOUNCE_FAILED, "ZeroBounce credential check failed."
        if response.status_code in {401, 403}:
            return False, ERR_ZEROBOUNCE_AUTH_FAILED, "ZeroBounce rejected the API key."
        if response.status_code >= 400:
            return False, ERR_ZEROBOUNCE_FAILED, f"ZeroBounce returned HTTP {response.status_code}."
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            return False, ERR_ZEROBOUNCE_FAILED, "ZeroBounce returned invalid JSON."
        credits = body.get("Credits") if isinstance(body, dict) else None
        if credits == -1:
            return False, ERR_ZEROBOUNCE_AUTH_FAILED, "ZeroBounce rejected the API key."
        return True, "", "ZeroBounce credentials are valid."
```

- [ ] **Step 6: Create validation task**

Create `app/jobs/validation.py`:

```python
"""Procrastinate task: run one S4 email verification batch."""
from __future__ import annotations

from uuid import UUID

from procrastinate import RetryStrategy
from sqlmodel import Session

from app.db.session import get_engine
from app.jobs._priority import BULK_USER  # noqa: F401
from app.queue import app
from app.services.email_verification_service import EmailVerificationService


@app.task(
    name="run_email_verification_batch",
    queue="validation",
    retry=RetryStrategy(max_attempts=2, wait=60),
)
async def run_email_verification_batch(batch_id: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        EmailVerificationService().run_batch(session=session, batch_id=UUID(batch_id))
```

- [ ] **Step 7: Run tests and commit**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py
```

Expected: PASS.

Commit:

```bash
git add app/services/email_verification_service.py app/api/schemas/email_verification.py app/jobs/validation.py app/services/zerobounce_client.py tests/test_email_verification_service.py
git commit -m "feat(s4): run snapshot-safe email verification batches"
```

---

## Task 5: API Routes, Queue Registration, Worker Deployment, And SSE

**Files:**
- Create: `app/api/routes/email_verification.py`
- Modify: `app/main.py`
- Modify: `app/queue.py`
- Modify: `app/api/routes/events.py`
- Create: `alembic/versions/a8b9c0d1e2f3_verification_batch_notify_trigger.py`
- Modify: `scripts/run_worker.sh`
- Modify: `docker-compose.yml`
- Create: `tests/test_email_verification_api.py`
- Modify: `tests/test_run_worker_script.py`

- [ ] **Step 1: Write failing API route tests**

Create `tests/test_email_verification_api.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.api.schemas.email_verification import EmailVerificationBatchCreate, EmailVerificationPreviewRequest
from app.models import Campaign, Contact, UploadedDomain, VerificationBatch


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(session: Session) -> tuple[Campaign, UploadedDomain, Contact]:
    campaign = Campaign(id=uuid4(), name="S4 API")
    domain = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        dedupe_key="example.com",
    )
    contact = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Ada",
        last_name="Lovelace",
        selected_email="ada@example.com",
    )
    session.add_all([campaign, domain, contact])
    session.commit()
    session.refresh(contact)
    return campaign, domain, contact


def test_list_endpoint_returns_real_email_rows(db_session: Session) -> None:
    from app.api.routes import email_verification

    campaign, _domain, contact = _seed(db_session)
    out = email_verification.list_email_verification_contacts(
        campaign_id=campaign.id,
        session=db_session,
    )

    assert out.total == 1
    assert out.items[0].contact_id == contact.id
    assert out.items[0].selected_email == "ada@example.com"


def test_preview_endpoint_returns_paid_count(db_session: Session) -> None:
    from app.api.routes import email_verification

    campaign, _domain, contact = _seed(db_session)
    out = email_verification.preview_email_verification(
        body=EmailVerificationPreviewRequest(campaign_id=campaign.id, contact_ids=[contact.id]),
        session=db_session,
    )

    assert out.eligible_count == 1
    assert out.paid_validation_count == 1


@pytest.mark.asyncio
async def test_create_batch_endpoint_enqueues_task(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    from app.api.routes import email_verification

    enqueued: list[str] = []

    async def fake_enqueue(batch_id):
        enqueued.append(str(batch_id))

    monkeypatch.setattr(email_verification, "_enqueue_email_verification_batch", fake_enqueue)
    monkeypatch.setattr(
        email_verification.EmailVerificationService,
        "_check_paid_credentials",
        lambda self, paid_count: None,
        raising=False,
    )
    campaign, _domain, contact = _seed(db_session)

    out = await email_verification.create_email_verification_batch(
        body=EmailVerificationBatchCreate(campaign_id=campaign.id, contact_ids=[contact.id]),
        session=db_session,
    )

    assert db_session.get(VerificationBatch, out.id) is not None
    assert enqueued == [str(out.id)]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_email_verification_api.py
```

Expected: FAIL because route module does not exist.

- [ ] **Step 3: Add API routes**

Create `app/api/routes/email_verification.py` with router prefix `/v1/email-verification`. Implement:

- `GET /contacts`
- `GET /contact-ids`
- `GET /letter-counts`
- `POST /preview`
- `POST /batches`
- `GET /batches/active`
- `GET /batches/{batch_id}`

Use the same `_service()` and `_http_error()` pattern as `app/api/routes/email_fetch.py`.

Add:

```python
async def _enqueue_email_verification_batch(batch_id: UUID) -> None:
    from app.jobs.validation import run_email_verification_batch

    await run_email_verification_batch.defer_async(batch_id=str(batch_id))
```

Include router in `app/main.py`.

- [ ] **Step 4: Register worker import and deployment**

In `app/queue.py`, add `"app.jobs.validation"` to `_DEFAULT_IMPORT_PATHS`.

In `scripts/run_worker.sh`, update usage and default concurrency:

```bash
# Usage: ./scripts/run_worker.sh scrape 2
#        ./scripts/run_worker.sh ai_decision 2
#        ./scripts/run_worker.sh contact_fetch 1
#        ./scripts/run_worker.sh validation 1
set -euo pipefail

QUEUE="${1:-scrape}"
if [ "${2+x}" ]; then
    CONCURRENCY="$2"
else
    case "$QUEUE" in
        contact_fetch|validation) CONCURRENCY="1" ;;
        *) CONCURRENCY="2" ;;
    esac
fi
```

In `docker-compose.yml`, add a `worker-validation` service mirroring `worker-provider`, with:

```yaml
environment:
    PS_WORKER_PROCESS: "1"
    PS_WORKER_CONCURRENCY: "1"
command:
    - "uv"
    - "run"
    - "python"
    - "-m"
    - "procrastinate"
    - "--app=app.queue.app"
    - "worker"
    - "-q"
    - "validation"
    - "-c"
    - "1"
```

Update `tests/test_run_worker_script.py` with:

```python
def test_run_worker_defaults_validation_to_single_worker() -> None:
    source = Path("scripts/run_worker.sh").read_text()

    assert "./scripts/run_worker.sh validation 1" in source
    assert "contact_fetch|validation) CONCURRENCY=\"1\" ;;" in source


def test_compose_has_single_validation_worker() -> None:
    source = Path("docker-compose.yml").read_text()
    worker = re.search(r"worker-validation:(?P<body>.*?)(?:\n    [a-zA-Z0-9_-]+:|\Z)", source, re.S)

    assert worker is not None
    assert 'PS_WORKER_CONCURRENCY: "1"' in worker.group("body")
    assert '- "validation"' in worker.group("body")
    assert '- "1"' in worker.group("body")
```

- [ ] **Step 5: Add verification batch notify trigger and SSE mapping**

Create `alembic/versions/a8b9c0d1e2f3_verification_batch_notify_trigger.py` with `revision = "a8b9c0d1e2f3"` and `down_revision = "f6a7b8c9d0e1"`. Its upgrade SQL is:

```python
_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION notify_verification_batch_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
  payload TEXT;
BEGIN
  payload := json_build_object(
    'job_type',       'verification_batch',
    'job_id',         NEW.id,
    'batch_id',       NEW.id,
    'campaign_id',    NEW.campaign_id,
    'state',          NEW.state,
    'selected_count', NEW.selected_count,
    'queued_count',   NEW.queued_count,
    'verified_count', NEW.verified_count,
    'valid_count',    NEW.valid_count,
    'invalid_count',  NEW.invalid_count,
    'skipped_count',  NEW.skipped_count,
    'finished_at',    NEW.finished_at
  )::text;
  PERFORM pg_notify('job_events', payload);
  RETURN NEW;
END;
$$;

CREATE TRIGGER verification_batches_notify
AFTER INSERT OR UPDATE ON verification_batches
FOR EACH ROW EXECUTE FUNCTION notify_verification_batch_update();
"""
```

Update `app/api/routes/events.py`:

- `_RESOLVE_SQL["verification_batch"] = "SELECT campaign_id::text FROM verification_batches WHERE id = :jid"`
- `_STAGE_LABEL["verification_batch"] = "s4"`
- Batch event fast path includes `verification_batch`.
- `_batch_event_payload` includes `selected_count`, `verified_count`, `valid_count`, `invalid_count`, and `skipped_count` when present.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
uv run pytest -q tests/test_email_verification_api.py tests/test_run_worker_script.py
```

Expected: PASS.

Commit:

```bash
git add app/api/routes/email_verification.py app/main.py app/queue.py app/api/routes/events.py app/jobs/validation.py scripts/run_worker.sh docker-compose.yml alembic/versions/a8b9c0d1e2f3_verification_batch_notify_trigger.py tests/test_email_verification_api.py tests/test_run_worker_script.py
git commit -m "feat(s4): add email verification API and worker"
```

---

## Task 6: Frontend API, Types, And Navigation Cleanup

**Files:**
- Modify: `apps/web/src/lib/types.ts`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/lib/navigation.ts`
- Modify: `apps/web/src/components/layout/Sidebar.tsx`
- Modify: `apps/web/src/components/layout/BottomNav.tsx`
- Modify: `apps/web/src/components/layout/AppShell.tsx`
- Modify: `apps/web/src/components/layout/header/LiveStatus.tsx`
- Modify: `apps/web/src/components/views/pipeline/DashboardView.tsx`
- Modify: `apps/web/src/components/views/dashboard/StageCards.tsx`
- Modify: `apps/web/tests/apiContracts.test.ts`
- Create: `apps/web/tests/validationNavigation.test.ts`

- [ ] **Step 1: Write failing frontend contract tests**

Add `apps/web/tests/validationNavigation.test.ts`:

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('validation is product S4 and old reveal/S5 routes are removed', () => {
  const navigation = readFileSync(new URL('../src/lib/navigation.ts', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const dashboard = readFileSync(new URL('../src/components/views/pipeline/DashboardView.tsx', import.meta.url), 'utf8')

  assert.match(navigation, /'s4-validation'/)
  assert.doesNotMatch(navigation, /'s4-reveal'/)
  assert.doesNotMatch(navigation, /'s5-validation'/)
  assert.match(app, /activeView === 's4-validation'/)
  assert.doesNotMatch(app, /S4 · Reveal/)
  assert.match(dashboard, /stageNum:\s*'S4'/)
  assert.match(dashboard, /Email Verification|Validation/)
})
```

In `apps/web/tests/apiContracts.test.ts`, replace the stale `verifyContacts` import and test with S4 API contracts:

```ts
import {
  createEmailVerificationBatch,
  getActiveEmailVerificationBatch,
  listEmailVerificationContactIds,
  listEmailVerificationContacts,
  previewEmailVerification,
} from '../src/lib/api.ts'

test('email verification APIs use the S4 namespace', async () => {
  const requested: string[] = []
  mockFetch((url) => {
    requested.push(url)
    return { total: 0, limit: 50, offset: 0, counts: {}, items: [] }
  })

  await listEmailVerificationContacts('camp-1', { status: 'pending', letter: 'A', search: 'ada', limit: 50, offset: 0 })

  assert.match(requested[0], /\/v1\/email-verification\/contacts/)
  assert.match(requested[0], /campaign_id=camp-1/)
  assert.match(requested[0], /status=pending/)
  assert.match(requested[0], /letter=A/)
  assert.match(requested[0], /search=ada/)
})

test('email verification preview and batch post contact ids', async () => {
  const bodies: string[] = []
  mockFetch((_url, init) => {
    bodies.push(String(init?.body ?? ''))
    return { id: 'batch-1', campaign_id: 'camp-1', state: 'queued', selected_count: 2, queued_count: 2, verified_count: 0, valid_count: 0, invalid_count: 0, skipped_count: 0, created_at: '2026-06-04T00:00:00Z', finished_at: null }
  })

  await previewEmailVerification({ campaign_id: 'camp-1', contact_ids: ['c1', 'c2'] })
  await createEmailVerificationBatch({ campaign_id: 'camp-1', contact_ids: ['c1', 'c2'] })

  assert.match(bodies[0], /"contact_ids":\["c1","c2"\]/)
  assert.match(bodies[1], /"contact_ids":\["c1","c2"\]/)
})
```

- [ ] **Step 2: Run frontend tests to verify they fail**

Run:

```bash
node --test apps/web/tests/validationNavigation.test.ts apps/web/tests/apiContracts.test.ts
```

Expected: FAIL because `s4-validation` and S4 API client functions do not exist.

- [ ] **Step 3: Add frontend types and API functions**

In `apps/web/src/lib/types.ts`, add S4 types matching backend schemas:

```ts
export type EmailVerificationStatus = 'pending' | 'checking' | 'stale' | 'valid' | 'undeliverable' | 'catch_all' | 'unknown' | 'failed'

export type EmailVerificationCounts = {
  all: number
  pending: number
  checking: number
  stale: number
  valid: number
  undeliverable: number
  catch_all: number
  unknown: number
  failed: number
}

export type EmailVerificationContactRow = {
  contact_id: string
  campaign_id: string
  domain_id: string
  domain: string
  first_name: string
  last_name: string
  title: string | null
  linkedin_url: string | null
  selected_email: string
  status: EmailVerificationStatus
  raw_status: string | null
  sub_status: string | null
  verified_at: string | null
  updated_at: string
  action_label: string | null
}
```

Add preview and batch request/response types:

```ts
export type EmailVerificationContactList = {
  total: number
  limit: number
  offset: number
  counts: EmailVerificationCounts
  items: EmailVerificationContactRow[]
}

export type EmailVerificationContactIds = {
  ids: string[]
  total: number
  limit: number
  offset: number
}

export type EmailVerificationPreviewRequest = {
  campaign_id: string
  contact_ids: string[]
}

export type EmailVerificationPreviewRead = {
  campaign_id: string
  selected_count: number
  eligible_count: number
  cached_count: number
  paid_validation_count: number
  skipped_count: number
  skipped_reasons: Record<string, number>
  max_batch_size: number
  warnings: string[]
}

export type EmailVerificationBatchCreate = {
  campaign_id: string
  contact_ids: string[]
}

export type EmailVerificationBatchRead = {
  id: string
  campaign_id: string
  state: string
  selected_count: number
  queued_count: number
  verified_count: number
  valid_count: number
  invalid_count: number
  skipped_count: number
  result_summary: Record<string, unknown> | null
  created_at: string
  finished_at: string | null
}
```

In `apps/web/src/lib/api.ts`, add:

```ts
export async function listEmailVerificationContacts(
  campaignId: string,
  { status, letter, search, limit = 50, offset = 0 }: { status?: string; letter?: string; search?: string; limit?: number; offset?: number } = {},
): Promise<EmailVerificationContactList> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  return request<EmailVerificationContactList>(`/v1/email-verification/contacts?${params.toString()}`)
}

export async function listEmailVerificationContactIds(
  campaignId: string,
  { status, letter, search, actionableOnly = false, limit = 200, offset = 0 }: { status?: string; letter?: string; search?: string; actionableOnly?: boolean; limit?: number; offset?: number } = {},
): Promise<EmailVerificationContactIds> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  if (actionableOnly) params.set('actionable_only', 'true')
  return request<EmailVerificationContactIds>(`/v1/email-verification/contact-ids?${params.toString()}`)
}

export async function getEmailVerificationLetterCounts(
  campaignId: string,
  { status, search }: { status?: string; search?: string } = {},
): Promise<DomainLetterCounts> {
  const params = new URLSearchParams({ campaign_id: campaignId })
  if (status) params.set('status', status)
  if (search?.trim()) params.set('search', search.trim())
  return request<DomainLetterCounts>(`/v1/email-verification/letter-counts?${params.toString()}`)
}

export async function previewEmailVerification(body: EmailVerificationPreviewRequest): Promise<EmailVerificationPreviewRead> {
  return request<EmailVerificationPreviewRead>('/v1/email-verification/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function createEmailVerificationBatch(body: EmailVerificationBatchCreate): Promise<EmailVerificationBatchRead> {
  return request<EmailVerificationBatchRead>('/v1/email-verification/batches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function getEmailVerificationBatch(batchId: string): Promise<EmailVerificationBatchRead> {
  return request<EmailVerificationBatchRead>(`/v1/email-verification/batches/${encodeURIComponent(batchId)}`)
}

export async function getActiveEmailVerificationBatch(campaignId: string): Promise<EmailVerificationBatchRead | null> {
  return request<EmailVerificationBatchRead | null>(`/v1/email-verification/batches/active?campaign_id=${encodeURIComponent(campaignId)}`)
}
```

- [ ] **Step 4: Rename product navigation key**

In `apps/web/src/lib/navigation.ts`:

- Remove `s4-reveal`.
- Remove `s5-validation`.
- Add `s4-validation`.

Update layout and dashboard files so the pipeline is:

```ts
['s1-scraping', 's2-ai', 's3-contacts', 's4-validation']
```

Use `stageCounts.validation` for the S4 badge and live state.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
node --test apps/web/tests/validationNavigation.test.ts apps/web/tests/apiContracts.test.ts
```

Expected: PASS.

Commit:

```bash
git add apps/web/src/lib/types.ts apps/web/src/lib/api.ts apps/web/src/lib/navigation.ts apps/web/src/components/layout apps/web/src/components/views/pipeline/DashboardView.tsx apps/web/src/components/views/dashboard/StageCards.tsx apps/web/tests/apiContracts.test.ts apps/web/tests/validationNavigation.test.ts
git commit -m "feat(s4): wire email verification API and navigation"
```

---

## Task 7: Real S4 Validation View

**Files:**
- Rewrite: `apps/web/src/components/views/validation/ValidationView.tsx`
- Rewrite: `apps/web/src/components/views/validation/ValidationTable.tsx`
- Rewrite: `apps/web/src/components/views/validation/ValidationCards.tsx`
- Rewrite: `apps/web/src/components/views/validation/ValidationStatusBadge.tsx`
- Delete: `apps/web/src/components/views/validation/ValidationSettingsDrawer.tsx`
- Create: `apps/web/src/components/views/validation/EmailVerificationPreviewDialog.tsx`
- Modify: `apps/web/src/App.tsx`
- Create: `apps/web/tests/validationStageParity.test.ts`
- Create: `apps/web/tests/validationLiveRefresh.test.ts`
- Create: `apps/web/tests/validationSelection.test.ts`

- [ ] **Step 1: Write failing S4 view source tests**

Create `apps/web/tests/validationStageParity.test.ts`:

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('S4 validation view follows S1-S3 table conventions with real backend data', () => {
  const source = readFileSync(new URL('../src/components/views/validation/ValidationView.tsx', import.meta.url), 'utf8')

  assert.match(source, /const PAGE_SIZE = 50/)
  assert.match(source, /const MAX_VERIFICATION_BATCH_SIZE = 200/)
  assert.match(source, /const LETTERS = \['#'/)
  assert.match(source, /listEmailVerificationContacts/)
  assert.match(source, /listEmailVerificationContactIds/)
  assert.match(source, /getEmailVerificationLetterCounts/)
  assert.match(source, /previewEmailVerification/)
  assert.match(source, /createEmailVerificationBatch/)
  assert.match(source, /Company A-Z/)
  assert.match(source, /Validate first/)
  assert.match(source, /Select all/)
  assert.match(source, /← Prev/)
  assert.match(source, /Next →/)
  assert.doesNotMatch(source, /MOCK_VALIDATION_ROWS/)
  assert.doesNotMatch(source, /MOCK_VALIDATION_STATS/)
  assert.doesNotMatch(source, /ValidationSettingsDrawer/)
})
```

Create `apps/web/tests/validationLiveRefresh.test.ts`:

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('S4 validation view refreshes from campaign events and active batch polling', () => {
  const source = readFileSync(new URL('../src/components/views/validation/ValidationView.tsx', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/lib/api.ts', import.meta.url), 'utf8')

  assert.match(source, /useCampaignEventStream/)
  assert.match(source, /event\.stage === 's4'/)
  assert.match(source, /getActiveEmailVerificationBatch/)
  assert.match(source, /POLL_STATUS_ACTIVE_MS/)
  assert.match(source, /POLL_HEAVY_ACTIVE_MS/)
  assert.match(source, /statusPollBusyRef/)
  assert.match(source, /heavyPollBusyRef/)
  assert.doesNotMatch(source, /setInterval/)
  assert.match(api, /\/v1\/email-verification\/batches\/active/)
})
```

Create `apps/web/tests/validationSelection.test.ts`:

```ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('S4 selection allows mixed rows and previews eligible subset', () => {
  const source = readFileSync(new URL('../src/components/views/validation/ValidationView.tsx', import.meta.url), 'utf8')

  assert.match(source, /selectedActionableIds/)
  assert.match(source, /No selected emails need validation/)
  assert.match(source, /skipped_count/)
  assert.match(source, /cached_count/)
  assert.match(source, /paid_validation_count/)
  assert.doesNotMatch(source, /disabled=\{row\.status === 'valid'\}/)
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
node --test apps/web/tests/validationStageParity.test.ts apps/web/tests/validationLiveRefresh.test.ts apps/web/tests/validationSelection.test.ts
```

Expected: FAIL because the view still uses mock data and old S5 patterns.

- [ ] **Step 3: Rewrite status badge**

`ValidationStatusBadge.tsx` should accept `EmailVerificationStatus`, map:

- `pending` -> Pending
- `checking` -> Checking with live dot
- `stale` -> Stale
- `valid` -> Valid
- `undeliverable` -> Undeliverable
- `catch_all` -> Catch-all
- `unknown` -> Unknown
- `failed` -> Failed

Show `subStatus` as a small secondary label when present.

- [ ] **Step 4: Rewrite table and cards**

`ValidationTable.tsx` and `ValidationCards.tsx` take `EmailVerificationContactRow[]`.

Table columns:

- checkbox
- Contact
- Company
- Email
- Status
- Verified
- Action

Keep selection enabled for every row. Row action button appears only when `row.action_label` is not null.

- [ ] **Step 5: Add preview dialog**

Create `EmailVerificationPreviewDialog.tsx` that shows:

- selected count
- eligible count
- cached count
- paid validations
- skipped count
- skipped reasons
- confirm/cancel controls

Copy should use ZeroBounce for paid validations, for example:

```text
ZeroBounce paid validations: 37
Cached results reused: 12
Skipped: 5
```

- [ ] **Step 6: Rewrite `ValidationView.tsx`**

Use the same request gate, pagination, selection, live polling, visibility refresh, and event-stream patterns as `ContactsView.tsx`.

State:

```ts
const [filter, setFilter] = useState<FilterValue>('all')
const [letterFilter, setLetterFilter] = useState('all')
const [search, setSearch] = useState('')
const [rows, setRows] = useState<EmailVerificationContactRow[]>([])
const [counts, setCounts] = useState<EmailVerificationCounts>(EMPTY_COUNTS)
const [selected, setSelected] = useState<Set<string>>(new Set())
const [allMatchingSelected, setAllMatchingSelected] = useState(false)
const [activeBatch, setActiveBatch] = useState<EmailVerificationBatchRead | null>(null)
```

Header stats:

- pending
- checking
- stale
- valid
- undeliverable
- catch-all
- unknown
- failed

Bulk behavior:

- `selectedActionableIds` includes selected rows with `action_label`.
- If selected rows exist but none actionable, show toast/error panel text `No selected emails need validation. Fresh results can be revalidated after 30 days.`
- Mixed selection sends actionable ids to preview.
- `selectMatchingActionable` calls `listEmailVerificationContactIds(campaignId, { status: filter, search, letter, actionableOnly: true, limit: 200 })`.

- [ ] **Step 7: Wire App route and refresh**

In `App.tsx`, route:

```tsx
{selectedCampaignId && activeView === 's4-validation' && (
  <ValidationView
    campaignId={selectedCampaignId}
    onStageCountsRefresh={refreshSelectedStageCounts}
    onActiveBatchChange={setActiveVerificationBatch}
  />
)}
```

Add active verification batch state only if needed for shell live behavior. Do not synthesize validation counts from local batch counters; shared counts remain the source of truth.

- [ ] **Step 8: Run tests and commit**

Run:

```bash
node --test apps/web/tests/validationStageParity.test.ts apps/web/tests/validationLiveRefresh.test.ts apps/web/tests/validationSelection.test.ts
```

Expected: PASS.

Commit:

```bash
git add apps/web/src/components/views/validation apps/web/src/App.tsx apps/web/tests/validationStageParity.test.ts apps/web/tests/validationLiveRefresh.test.ts apps/web/tests/validationSelection.test.ts
git commit -m "feat(s4): replace mock validation view with real email verification"
```

---

## Task 8: Final Verification And Cleanup

**Files:**
- Modify if referenced by `rg`: `apps/web/src/lib/mockData.ts`
- Modify if referenced by `rg`: `apps/web/src/lib/useAppData.ts`
- Modify if referenced by `rg`: `apps/web/src/lib/stageViewSort.ts`
- Modify if referenced by `rg`: `apps/web/src/lib/contactPreview.ts`
- Modify if referenced by `rg`: `apps/web/tests/contactPreview.test.ts`
- Modify if referenced by `rg`: `apps/web/tests/stageCountsApi.test.ts`

- [ ] **Step 1: Remove stale mock validation exports if unused**

Run:

```bash
rg -n "MOCK_VALIDATION|MockValidationRow|ValidationStatus|s5-validation|s4-reveal|verifyContacts|ContactVerifyRequest|ContactVerifyResult" apps/web/src apps/web/tests app tests
```

Expected after cleanup: no product code references old mock validation rows, `s5-validation`, `s4-reveal`, or `verifyContacts`.

If `apps/web/src/lib/mockData.ts` exports validation-only mocks that are unused, delete those exports and update `useAppData.ts` exports.

- [ ] **Step 2: Run backend tests**

Run:

```bash
uv run pytest -q tests/test_email_verification_service.py tests/test_email_verification_api.py tests/test_campaign_stage_counts.py tests/test_run_worker_script.py tests/test_contacts_api.py
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused tests**

Run:

```bash
node --test apps/web/tests/apiContracts.test.ts apps/web/tests/stageCountsApi.test.ts apps/web/tests/validationNavigation.test.ts apps/web/tests/validationStageParity.test.ts apps/web/tests/validationLiveRefresh.test.ts apps/web/tests/validationSelection.test.ts apps/web/tests/sharedLayoutCounts.test.ts
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd apps/web && npm run build
```

Expected: PASS.

- [ ] **Step 5: Run Alembic upgrade smoke**

Run:

```bash
uv run alembic upgrade head
```

Expected: PASS.

- [ ] **Step 6: Commit final cleanup**

Commit:

```bash
git add app apps tests alembic scripts docker-compose.yml
git commit -m "chore(s4): clean up obsolete validation remnants"
```

---

## Self-Review

Spec coverage:

- Contact/email table only: Task 7.
- Currently matching actions and 200 cap: Tasks 3 and 7.
- Preview-confirm for every action: Tasks 3, 4, 5, and 7.
- ZeroBounce-only validation with 30-day cache: Tasks 1, 3, and 4.
- Stale/actionable semantics: Tasks 2, 3, and 7.
- Technical `Failed` separate from ZeroBounce verdicts: Tasks 2 and 4.
- Provider snapshot safety: Task 4.
- Separate validation queue and deployed worker: Task 5.
- Batch detail, active batch, and SSE: Task 5.
- Shared stage counts and badge rule: Task 2.
- Removal of old reveal/S5 UI route: Task 6.

Known implementation risk:

- `VerificationBatch` has no per-item table. The batch snapshot JSON is acceptable for v1 because the contact rows hold current row state, while the batch summary holds aggregate outcome counts.
- Confirm-time "invalid credential" requires a ZeroBounce credential check call when paid validations are needed. If that check has a transient network failure, the operator sees a confirm-time error instead of a queued failed batch.

Execution gate:

- Do not start implementation until Avi approves this plan and chooses an execution mode.
