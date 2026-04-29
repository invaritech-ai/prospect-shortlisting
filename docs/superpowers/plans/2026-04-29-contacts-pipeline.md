# Contacts Pipeline (Stages 4–7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the duplicate contact tables into one `contacts` table and wire up five new API endpoints for contact fetch, title rematch, email reveal, ZeroBounce verify, and CSV export.

**Architecture:** Rename `discovered_contacts` → `contacts`, add email/verification/pipeline_stage fields, drop `prospect_contacts` and `prospect_contact_emails`. New FastAPI endpoints delegate to existing service layer (`ContactQueueService`, `ContactRevealQueueService`, `ContactVerifyService`, `title_match_service`). All writes return 202 and queue Celery tasks; `POST /contacts/rematch` is the only synchronous write.

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy, Alembic, Celery, PostgreSQL

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `alembic/versions/XXXX_consolidate_contacts_table.py` | Create | Rename table, add columns, drop old tables |
| `app/models/pipeline.py` | Modify | Rename `DiscoveredContact` → `Contact`, add new fields, remove `ProspectContact`/`ProspectContactEmail` |
| `app/models/__init__.py` | Modify | Update exports |
| `app/api/schemas/contacts.py` | Modify | Add 8 new request/response schemas |
| `app/api/routes/contacts.py` | Modify | Add 5 new endpoints, update model refs |
| `app/api/routes/discovered_contacts.py` | Delete | Replaced by contacts.py |
| `app/api/routes/stats.py` | Modify | Remove ProspectContact ref |
| `app/services/company_service.py` | Modify | Update cascade delete: `DiscoveredContact` → `Contact`, remove `ProspectContact` |
| `app/services/contact_service.py` | Modify | Replace `DiscoveredContact` → `Contact` throughout |
| `app/services/contact_query_service.py` | Modify | Replace `DiscoveredContact` → `Contact` |
| `app/services/contact_queue_service.py` | Modify | Replace `DiscoveredContact` → `Contact` |
| `app/services/contact_reveal_queue_service.py` | Modify | Replace `DiscoveredContact` → `Contact` |
| `app/services/contact_reveal_service.py` | Modify | Replace `DiscoveredContact` → `Contact` |
| `app/services/contact_verify_service.py` | Modify | Replace `DiscoveredContact` → `Contact` |
| `app/services/title_match_service.py` | Modify | Replace `DiscoveredContact` → `Contact`, rename `rematch_discovered_contacts` → `rematch_contacts` |
| `app/services/pipeline_service.py` | Modify | Remove `ProspectContact` ref if present |
| `app/main.py` | Modify | Remove `discovered_contacts` router |
| `app/db/session.py` | Modify | Update any table refs if present |
| `app/tasks/contacts.py` | Modify | Replace `DiscoveredContact` → `Contact` |

---

## Task 1: Alembic migration — consolidate contacts table

**Files:**
- Create: `alembic/versions/XXXX_consolidate_contacts_table.py`

- [ ] **Step 1: Generate migration stub**

```bash
uv run alembic revision --autogenerate -m "consolidate_contacts_table"
```

Note the generated filename (e.g. `abc123_consolidate_contacts_table.py`). Then **replace its entire body** with the content below.

- [ ] **Step 2: Write migration**

```python
"""consolidate_contacts_table

Revision ID: <keep generated id>
Revises: <keep generated revises>
Create Date: 2026-04-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "<keep generated>"
down_revision = "<keep generated>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename table
    op.rename_table("discovered_contacts", "contacts")

    # 2. Rename unique constraint
    op.drop_constraint("uq_discovered_contacts_provider_key", "contacts", type_="unique")
    op.create_unique_constraint(
        "uq_contacts_provider_key",
        "contacts",
        ["company_id", "provider", "provider_person_id"],
    )

    # 3. Rename indexes (PostgreSQL requires explicit rename)
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_id RENAME TO ix_contacts_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_company_id RENAME TO ix_contacts_company_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_contact_fetch_job_id RENAME TO ix_contacts_contact_fetch_job_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_provider RENAME TO ix_contacts_provider")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_provider_person_id RENAME TO ix_contacts_provider_person_id")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_title_match RENAME TO ix_contacts_title_match")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_provider_has_email RENAME TO ix_contacts_provider_has_email")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_is_active RENAME TO ix_contacts_is_active")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_backfilled RENAME TO ix_contacts_backfilled")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_discovered_at RENAME TO ix_contacts_discovered_at")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_last_seen_at RENAME TO ix_contacts_last_seen_at")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_created_at RENAME TO ix_contacts_created_at")
    op.execute("ALTER INDEX IF EXISTS ix_discovered_contacts_updated_at RENAME TO ix_contacts_updated_at")

    # 4. Add new columns
    op.add_column("contacts", sa.Column("email", sa.String(512), nullable=True))
    op.add_column("contacts", sa.Column("email_provider", sa.String(32), nullable=True))
    op.add_column("contacts", sa.Column("email_confidence", sa.Float(), nullable=True))
    op.add_column("contacts", sa.Column("provider_email_status", sa.String(32), nullable=True))
    op.add_column("contacts", sa.Column("reveal_raw_json", sa.JSON(), nullable=True))
    op.add_column("contacts", sa.Column("verification_status", sa.String(32), nullable=False, server_default="unverified"))
    op.add_column("contacts", sa.Column("zerobounce_raw", sa.JSON(), nullable=True))
    op.add_column("contacts", sa.Column("pipeline_stage", sa.String(32), nullable=False, server_default="fetched"))

    # 5. Create indexes on new columns
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_verification_status", "contacts", ["verification_status"])
    op.create_index("ix_contacts_pipeline_stage", "contacts", ["pipeline_stage"])

    # 6. Drop prospect_contact_emails first (has FK → prospect_contacts)
    op.drop_table("prospect_contact_emails")

    # 7. Drop prospect_contacts
    op.drop_table("prospect_contacts")


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported — data loss would occur.")
```

- [ ] **Step 3: Run migration**

```bash
uv run alembic upgrade head
```

Expected: no errors. Verify:
```bash
uv run python -c "
from sqlalchemy import text
from app.db.session import get_engine
with get_engine().connect() as c:
    tables = c.execute(text(\"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename\")).scalars().all()
    print([t for t in tables if 'contact' in t])
"
```
Expected output includes `contacts` and NOT `discovered_contacts`, `prospect_contacts`, `prospect_contact_emails`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat(db): consolidate contacts table — rename discovered_contacts, add email/verify fields, drop prospect_contacts"
```

---

## Task 2: Update Contact model in pipeline.py

**Files:**
- Modify: `app/models/pipeline.py`

- [ ] **Step 1: Replace `DiscoveredContact` class**

Find the `class DiscoveredContact` block (around line 647) and replace it entirely:

```python
class Contact(SQLModel, table=True):
    """Unified contact record: fetch → title match → email reveal → verification."""

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("company_id", "provider", "provider_person_id", name="uq_contacts_provider_key"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    contact_fetch_job_id: UUID | None = Field(default=None, foreign_key="contact_fetch_jobs.id", index=True)
    provider: str = Field(max_length=32, index=True)
    provider_person_id: str = Field(max_length=255, index=True)
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    title: str | None = Field(default=None, max_length=512)
    title_match: bool = Field(default=False, index=True)
    linkedin_url: str | None = Field(default=None, max_length=2048)
    source_url: str | None = Field(default=None, max_length=2048)
    provider_has_email: bool | None = Field(default=None, index=True)
    provider_metadata_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    raw_payload_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    is_active: bool = Field(default=True, index=True)
    backfilled: bool = Field(default=False, index=True)

    # Email reveal
    email: str | None = Field(default=None, max_length=512, index=True)
    email_provider: str | None = Field(default=None, max_length=32)
    email_confidence: float | None = Field(default=None)
    provider_email_status: str | None = Field(default=None, max_length=32, index=True)
    reveal_raw_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    # Verification
    verification_status: str = Field(default="unverified", max_length=32, index=True)
    zerobounce_raw: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    # Pipeline stage: fetched | email_revealed | campaign_ready
    pipeline_stage: str = Field(default="fetched", max_length=32, index=True)

    discovered_at: datetime = Field(default_factory=utcnow, index=True)
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
```

- [ ] **Step 2: Remove `ProspectContact` and `ProspectContactEmail` classes**

Delete both class definitions entirely from `pipeline.py` (ProspectContact ~line 688, ProspectContactEmail ~line 731).

Also remove `ContactPipelineStage` enum if it was only used by `ProspectContact`:
```bash
grep -n "ContactPipelineStage" app/models/pipeline.py
```
If only referenced in the now-deleted classes, delete it.

- [ ] **Step 3: Update `app/models/__init__.py`**

Replace:
```python
DiscoveredContact,
ProspectContact,
ProspectContactEmail,
```
With:
```python
Contact,
```

Remove any `ContactPipelineStage` export if deleted.

- [ ] **Step 4: Verify model loads**

```bash
uv run python -c "from app.models import Contact; print(Contact.__tablename__)"
```
Expected: `contacts`

- [ ] **Step 5: Commit**

```bash
git add app/models/
git commit -m "feat(model): rename DiscoveredContact → Contact, drop ProspectContact/ProspectContactEmail models"
```

---

## Task 3: Update all references across the codebase

**Files:**
- Modify: all files listed in the File Map

- [ ] **Step 1: Mechanical rename — DiscoveredContact → Contact**

```bash
# Find every reference
grep -rn "DiscoveredContact\|ProspectContact\|ProspectContactEmail\|discovered_contacts\|prospect_contacts\|prospect_contact_emails" \
  app/ --include="*.py" -l | grep -v __pycache__
```

For each file, replace:
- `DiscoveredContact` → `Contact`
- `ProspectContact` → `Contact` (where used as a data model — review each case)
- `ProspectContactEmail` → remove (table dropped)
- `discovered_contacts` → `contacts` (string table name references)
- `prospect_contacts` → remove

- [ ] **Step 2: Update `title_match_service.py` function name**

Find `def rematch_discovered_contacts(` and rename to `def rematch_contacts(`.

Update all callers:
```bash
grep -rn "rematch_discovered_contacts" app/ --include="*.py"
```
Replace each call with `rematch_contacts`.

- [ ] **Step 3: Update `company_service.py` cascade delete**

In `cascade_delete_companies`, replace:
```python
session.exec(delete(DiscoveredContact).where(col(DiscoveredContact.company_id).in_(confirmed_ids)))
session.exec(delete(ProspectContact).where(col(ProspectContact.company_id).in_(confirmed_ids)))
session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(confirmed_ids)))
session.exec(delete(CompanyFeedback).where(col(CompanyFeedback.company_id).in_(confirmed_ids)))
```
With:
```python
session.exec(delete(Contact).where(col(Contact.company_id).in_(confirmed_ids)))
session.exec(delete(ContactFetchJob).where(col(ContactFetchJob.company_id).in_(confirmed_ids)))
session.exec(delete(CompanyFeedback).where(col(CompanyFeedback.company_id).in_(confirmed_ids)))
```
Also remove `DiscoveredContact` and `ProspectContact` from the subquery helpers `_discovered_contact_count_subquery`. Replace with a `Contact` subquery:

```python
def _contact_count_subquery():
    return (
        select(
            Contact.company_id.label("company_id"),
            func.count().label("contact_count"),
            func.coalesce(
                func.sum(case((col(Contact.title_match).is_(True), 1), else_=0)), 0
            ).label("title_matched_count"),
        )
        .where(col(Contact.is_active).is_(True))
        .group_by(Contact.company_id)
        .subquery()
    )
```

Remove `_discovered_contact_count_subquery` — it's now merged into `_contact_count_subquery`.

Update all usages of the old subquery in `build_company_list_stmt` and `build_company_count_stmt`.

- [ ] **Step 4: Delete `discovered_contacts.py` router and remove from main.py**

```bash
rm app/api/routes/discovered_contacts.py
```

In `app/main.py`, remove:
```python
from app.api.routes.discovered_contacts import router as discovered_contacts_router
# ...
app.include_router(discovered_contacts_router)
```

- [ ] **Step 5: Verify app starts**

```bash
uv run python -c "from app.main import create_app; create_app(); print('OK')"
```

- [ ] **Step 6: Run ruff to catch remaining broken imports**

```bash
uv run ruff check app/ --select F401,F811 2>&1 | grep -v __pycache__
```

Fix any flagged unused imports.

- [ ] **Step 7: Commit**

```bash
git add app/
git commit -m "refactor: rename DiscoveredContact → Contact across all services, routes, tasks"
```

---

## Task 4: New request/response schemas

**Files:**
- Modify: `app/api/schemas/contacts.py`

- [ ] **Step 1: Add schemas**

Append to `app/api/schemas/contacts.py`:

```python
from uuid import UUID
from pydantic import BaseModel, Field


class ContactFetchRequest(BaseModel):
    campaign_id: UUID
    company_ids: list[UUID] | None = Field(default=None, min_length=1)


class ContactFetchQueued(BaseModel):
    queued_count: int
    job_ids: list[UUID]


class ContactRematchRequest(BaseModel):
    campaign_id: UUID


class ContactRematchResult(BaseModel):
    campaign_id: UUID
    matched_count: int
    total_count: int


class ContactRevealRequest(BaseModel):
    campaign_id: UUID


class ContactRevealQueued(BaseModel):
    queued_count: int
    job_id: UUID


class ContactVerifyRequest(BaseModel):
    campaign_id: UUID


class ContactVerifyQueued(BaseModel):
    queued_count: int
    job_id: UUID
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from app.api.schemas.contacts import ContactFetchRequest, ContactRematchResult, ContactRevealQueued, ContactVerifyQueued; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/schemas/contacts.py
git commit -m "feat(schemas): add contact pipeline request/response schemas"
```

---

## Task 5: New API endpoints in contacts.py

**Files:**
- Modify: `app/api/routes/contacts.py`

- [ ] **Step 1: Add POST /contacts/fetch**

Add to `app/api/routes/contacts.py`:

```python
from fastapi import status as http_status

@router.post("/contacts/fetch", response_model=ContactFetchQueued, status_code=http_status.HTTP_202_ACCEPTED)
def fetch_contacts_endpoint(
    payload: ContactFetchRequest,
    session: Session = Depends(get_session),
) -> ContactFetchQueued:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    query = (
        select(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(
            col(Upload.campaign_id) == payload.campaign_id,
            col(Company.pipeline_stage) == "contact_ready",
        )
    )
    if payload.company_ids:
        query = query.where(col(Company.id).in_(payload.company_ids))

    companies = list(session.exec(query).all())
    if not companies:
        raise HTTPException(status_code=422, detail="No contact_ready companies found for this campaign.")

    queue_service = ContactQueueService()
    result = queue_service.enqueue_fetches(
        session=session,
        companies=companies,
        provider_mode="both",
        campaign_id=payload.campaign_id,
        trigger_source="manual",
    )
    return ContactFetchQueued(
        queued_count=result.queued_count,
        job_ids=result.job_ids,
    )
```

Check `ContactEnqueueResult` fields in `contact_queue_service.py` and align field names with the actual result object (may be `.queued_count` and `.job_ids` or similar — verify before writing).

- [ ] **Step 2: Add POST /contacts/rematch**

```python
@router.post("/contacts/rematch", response_model=ContactRematchResult)
def rematch_contacts_endpoint(
    payload: ContactRematchRequest,
    session: Session = Depends(get_session),
) -> ContactRematchResult:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    matched, total = rematch_contacts(session, campaign_id=payload.campaign_id)
    return ContactRematchResult(
        campaign_id=payload.campaign_id,
        matched_count=matched,
        total_count=total,
    )
```

Import `rematch_contacts` from `app.services.title_match_service` (renamed in Task 3).

- [ ] **Step 3: Add POST /contacts/reveal**

```python
@router.post("/contacts/reveal", response_model=ContactRevealQueued, status_code=http_status.HTTP_202_ACCEPTED)
def reveal_contacts_endpoint(
    payload: ContactRevealRequest,
    session: Session = Depends(get_session),
) -> ContactRevealQueued:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    reveal_service = ContactRevealQueueService()
    result = reveal_service.enqueue_reveals(
        session=session,
        campaign_id=payload.campaign_id,
    )
    return ContactRevealQueued(
        queued_count=result.queued_count,
        job_id=result.job_id,
    )
```

Check `ContactRevealQueueService.enqueue_reveals()` signature in `contact_reveal_queue_service.py` and align parameter names.

- [ ] **Step 4: Add POST /contacts/verify**

```python
@router.post("/contacts/verify", response_model=ContactVerifyQueued, status_code=http_status.HTTP_202_ACCEPTED)
def verify_contacts_endpoint(
    payload: ContactVerifyRequest,
    session: Session = Depends(get_session),
) -> ContactVerifyQueued:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    verify_service = ContactVerifyService()
    result = verify_service.enqueue_verify(
        session=session,
        campaign_id=payload.campaign_id,
    )
    return ContactVerifyQueued(
        queued_count=result.queued_count,
        job_id=result.job_id,
    )
```

Check `ContactVerifyService` for the correct enqueue method name and signature.

- [ ] **Step 5: Add GET /contacts/export.csv**

```python
import csv
import io
from fastapi import Response

@router.get("/contacts/export.csv")
def export_contacts_csv(
    campaign_id: UUID = Query(...),
    include_statuses: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> Response:
    query = (
        select(
            col(Company.domain),
            col(Contact.first_name),
            col(Contact.last_name),
            col(Contact.title),
            col(Contact.email),
            col(Contact.verification_status),
            col(Contact.provider),
            col(Contact.email_provider),
        )
        .join(Company, col(Company.id) == col(Contact.company_id))
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(
            col(Upload.campaign_id) == campaign_id,
            col(Contact.email).is_not(None),
            col(Contact.is_active).is_(True),
        )
        .order_by(col(Company.domain).asc(), col(Contact.last_name).asc())
    )
    if include_statuses:
        query = query.where(col(Contact.verification_status).in_(include_statuses))

    rows = session.exec(query).all()  # type: ignore[call-overload]

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["domain", "first_name", "last_name", "title", "email",
                     "verification_status", "fetch_provider", "email_provider"])
    for row in rows:
        writer.writerow(list(row))

    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="contacts-{timestamp}.csv"'},
    )
```

- [ ] **Step 6: Add missing imports at top of contacts.py**

Ensure these are present:
```python
from app.api.schemas.contacts import (
    ContactFetchQueued,
    ContactFetchRequest,
    ContactRematchRequest,
    ContactRematchResult,
    ContactRevealQueued,
    ContactRevealRequest,
    ContactVerifyQueued,
    ContactVerifyRequest,
)
from app.models import Campaign, Company, Contact, Upload
from app.services.contact_queue_service import ContactQueueService
from app.services.contact_reveal_queue_service import ContactRevealQueueService
from app.services.contact_verify_service import ContactVerifyService
from app.services.title_match_service import rematch_contacts
```

- [ ] **Step 7: Verify routes register**

```bash
uv run python -c "
from app.main import create_app
app = create_app()
contact_routes = [r.path for r in app.routes if hasattr(r, 'path') and 'contact' in r.path]
for r in sorted(contact_routes): print(r)
"
```

Expected output includes:
```
/v1/contacts
/v1/contacts/fetch
/v1/contacts/rematch
/v1/contacts/reveal
/v1/contacts/verify
/v1/contacts/export.csv
/v1/title-match-rules
/v1/title-match-rules/...
```

- [ ] **Step 8: Commit**

```bash
git add app/api/routes/contacts.py app/api/schemas/contacts.py
git commit -m "feat(api): add contact fetch, rematch, reveal, verify, export endpoints"
```

---

## Task 6: Final verification

- [ ] **Step 1: Full ruff check**

```bash
uv run ruff check app/ 2>&1 | grep -v __pycache__ | grep -v "^warning:"
```
Expected: no errors.

- [ ] **Step 2: App starts clean**

```bash
uv run python -c "from app.main import create_app; create_app(); print('OK')"
```

- [ ] **Step 3: DB state check**

```bash
uv run python -c "
from sqlmodel import Session, select, func
from app.db.session import get_engine
from app.models import Contact
with Session(get_engine()) as s:
    count = s.exec(select(func.count()).select_from(Contact)).one()
    print(f'Contact rows: {count}')
"
```
Expected: same count as `discovered_contacts` had (127,668).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: contacts pipeline stages 4-7 — table consolidation + API endpoints complete"
```

---

## Known Adapter Points (verify before implementing)

These require checking existing service signatures before writing endpoint code:

| Service | Method | What to verify |
|---------|--------|----------------|
| `ContactQueueService` | `enqueue_fetches()` | Return type fields: `queued_count`, `job_ids` |
| `ContactRevealQueueService` | `enqueue_reveals()` | Params and return type |
| `ContactVerifyService` | enqueue method name and params | May be `enqueue_verify` or different |
| `title_match_service` | `rematch_contacts()` | Return type: `tuple[int, int]` (matched, total) |
