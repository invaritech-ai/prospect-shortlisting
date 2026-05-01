from __future__ import annotations

import inspect
from uuid import uuid4

import pytest
from sqlmodel import Session, col, select

from app.models import Campaign, Company, Contact, ContactFetchBatch, ContactFetchJob, Upload
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


# ── Task 4: worker execution ──────────────────────────────────────────────────

def _seed_job(
    session: Session, campaign: Campaign
) -> tuple[Company, "ContactFetchJob"]:
    from app.services.contact_fetch_service import ContactFetchService
    company = _seed_company(session, campaign)
    session.commit()
    svc = ContactFetchService()
    _, jobs, _ = svc.enqueue(
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

    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: (
            [{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO", "search_emails_start": "https://x"}],
            1,
            "",
        ),
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

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
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [{"id": "apollo-1", "first_name": "Bob", "last_name": "Jones", "title": "CTO", "linkedin_url": "https://li/bob"}],
    )

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].source_provider == "apollo"
    assert contacts[0].linkedin_url == "https://li/bob"


def test_run_job_both_providers_kept(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: ([{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}], 1, ""),
    )
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [{"id": "apollo-1", "first_name": "Bob", "last_name": "Jones", "title": "CTO"}],
    )

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)
    ContactFetchService().run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(sqlite_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert {c.source_provider for c in contacts} == {"snov", "apollo"}


def test_run_job_repeated_run_upserts_not_duplicates(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: ([{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}], 1, ""),
    )
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
    assert len(contacts) == 1


def test_run_job_title_match_applied(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models import TitleMatchRule

    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: ([{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "marketing director"}], 1, ""),
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    sqlite_session.add(TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="marketing, director", match_type="keyword"))
    sqlite_session.flush()
    company, job = _seed_job(sqlite_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

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
    ContactFetchService().run_contact_fetch_job(engine=sqlite_session.bind, contact_fetch_job_id=str(job.id))

    sqlite_session.refresh(job)
    assert job.state == ContactFetchJobState.SUCCEEDED
    assert job.terminal_state is True


# ── Task 2 (cont.) ───────────────────────────────────────────────��────────────

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


# ── Gap 2: batch finalization ─────────────────────────────────────────────────

def test_batch_finalized_when_all_jobs_terminal(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models.pipeline import ContactFetchBatchState

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)
    batch_id = job.contact_fetch_batch_id

    ContactFetchService().run_contact_fetch_job(
        engine=sqlite_session.bind,
        contact_fetch_job_id=str(job.id),
    )

    batch = sqlite_session.get(ContactFetchBatch, batch_id)
    assert batch.state == ContactFetchBatchState.SUCCEEDED
    assert batch.finished_at is not None


def test_batch_marked_failed_when_any_job_fails(sqlite_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models.pipeline import ContactFetchBatchState

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, "snov_failed"))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(sqlite_session)
    company, job = _seed_job(sqlite_session, campaign)
    batch_id = job.contact_fetch_batch_id

    ContactFetchService().run_contact_fetch_job(
        engine=sqlite_session.bind,
        contact_fetch_job_id=str(job.id),
    )

    batch = sqlite_session.get(ContactFetchBatch, batch_id)
    assert batch.state == ContactFetchBatchState.FAILED
    assert batch.finished_at is not None
