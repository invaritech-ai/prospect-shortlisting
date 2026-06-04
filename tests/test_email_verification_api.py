from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.api.schemas.email_verification import (
    EmailVerificationBatchCreate,
    EmailVerificationPreviewRequest,
)
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
        body=EmailVerificationPreviewRequest(
            campaign_id=campaign.id,
            contact_ids=[contact.id],
        ),
        session=db_session,
    )

    assert out.eligible_count == 1
    assert out.paid_validation_count == 1


@pytest.mark.asyncio
async def test_create_batch_endpoint_enqueues_task(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
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
