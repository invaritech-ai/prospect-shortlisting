from __future__ import annotations

import inspect
from uuid import uuid4

import pytest
from sqlmodel import Session, col, select

from app.models import Campaign, Company, ContactFetchBatch, ContactFetchJob, Upload
from app.models.pipeline import ContactFetchJobState


# ── helpers ───────────────────────────────────────────────────────────────────

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


# ── Task 1 ────────────────────────────────────────────────────────────────────

def test_fetch_contacts_task_accepts_job_id() -> None:
    from app.jobs.contact_fetch import fetch_contacts

    fn = getattr(fetch_contacts, "original_func", fetch_contacts)
    sig = inspect.signature(fn)
    assert "contact_fetch_job_id" in sig.parameters
    assert "company_id" not in sig.parameters


# ── Task 2: enqueue service ───────────────────────────────────────────────────

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
    _, jobs1, _ = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    sqlite_session.commit()

    _, jobs2, reused = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    sqlite_session.commit()

    assert reused == 1
    assert len(jobs2) == 1
    assert jobs2[0].id == jobs1[0].id


def test_force_refresh_creates_new_job(sqlite_session: Session) -> None:
    from app.services.contact_fetch_service import ContactFetchService

    campaign = _seed_campaign(sqlite_session)
    company = _seed_company(sqlite_session, campaign)
    sqlite_session.commit()

    svc = ContactFetchService()
    _, jobs1, _ = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    sqlite_session.commit()

    _, jobs2, reused = svc.enqueue(
        session=sqlite_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=True,
    )
    sqlite_session.commit()

    assert reused == 0
    assert jobs2[0].id != jobs1[0].id
