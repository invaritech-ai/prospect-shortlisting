from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.contacts import fetch_contacts_selected
from app.api.schemas.contacts import BulkContactFetchRequest
from app.models import Company, Upload
from app.models.pipeline import CompanyPipelineStage


def _company(session: Session, *, domain: str, stage: CompanyPipelineStage) -> Company:
    upload = Upload(filename="t.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0)
    session.add(upload)
    session.flush()
    c = Company(
        upload_id=upload.id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=stage,
    )
    session.add(c)
    session.flush()
    return c


def test_bulk_fetch_snov(sqlite_session: Session) -> None:
    c = _company(sqlite_session, domain="snov.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()
    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock:
        r = fetch_contacts_selected(
            BulkContactFetchRequest(company_ids=[c.id], source="snov"),
            session=sqlite_session,
        )
    assert r.queued_count == 1
    assert mock.call_count == 1


def test_bulk_fetch_apollo(sqlite_session: Session) -> None:
    c = _company(sqlite_session, domain="apollo.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()
    with patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as mock:
        r = fetch_contacts_selected(
            BulkContactFetchRequest(company_ids=[c.id], source="apollo"),
            session=sqlite_session,
        )
    assert r.queued_count == 1
    assert mock.call_count == 1


def test_bulk_fetch_both_enqueues_snov_and_apollo(sqlite_session: Session) -> None:
    """source='both' must create one snov job AND one apollo job per company."""
    c = _company(sqlite_session, domain="both.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()
    with (
        patch("app.api.routes.contacts.fetch_contacts.delay") as snov,
        patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as apollo,
    ):
        r = fetch_contacts_selected(
            BulkContactFetchRequest(company_ids=[c.id], source="both"),
            session=sqlite_session,
        )
    assert r.queued_count == 2
    assert snov.call_count == 1
    assert apollo.call_count == 1


def test_bulk_fetch_allows_non_contact_ready(sqlite_session: Session) -> None:
    c = _company(sqlite_session, domain="skip.example", stage=CompanyPipelineStage.UPLOADED)
    sqlite_session.commit()
    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock:
        r = fetch_contacts_selected(
            BulkContactFetchRequest(company_ids=[c.id], source="snov"),
            session=sqlite_session,
        )
    assert r.queued_count == 1
    assert mock.call_count == 1


def test_bulk_fetch_missing_ids_raises_404(sqlite_session: Session) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        fetch_contacts_selected(
            BulkContactFetchRequest(company_ids=[uuid4()], source="snov"),
            session=sqlite_session,
        )
    assert exc.value.status_code == 404
