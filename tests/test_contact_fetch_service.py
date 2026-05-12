from __future__ import annotations

import inspect
from uuid import uuid4

import pytest
from sqlmodel import Session, col, select

from app.models import Campaign, Company, Contact, ContactFetchBatch, ContactFetchJob, ContactProviderAttempt, Upload
from app.models.pipeline import ContactFetchJobState, ContactProviderAttemptState


# ── helpers ───────────────────────────────────────────────────────────────────

def _seed_campaign(session: Session, *, seed_rules: bool = True) -> Campaign:
    """Create a test campaign. By default also seeds a permissive wildcard
    title rule so the discovery contract — "save only title-matched contacts"
    — has something to match. Tests that want to exercise the no-rules
    short-circuit should pass `seed_rules=False`."""
    from app.models import TitleMatchRule

    c = Campaign(name="test")
    session.add(c)
    session.flush()
    if seed_rules:
        session.add(TitleMatchRule(
            campaign_id=c.id,
            rule_type="include",
            keywords=".+",
            match_type="regex",
        ))
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

def test_enqueue_creates_batch_and_job(db_session: Session) -> None:
    from app.services.contact_fetch_service import ContactFetchService

    campaign = _seed_campaign(db_session)
    company = _seed_company(db_session, campaign)
    db_session.commit()

    svc = ContactFetchService()
    batch, jobs, reused = svc.enqueue(
        session=db_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    db_session.commit()

    assert batch.id is not None
    assert batch.campaign_id == campaign.id
    assert len(jobs) == 1
    assert jobs[0].company_id == company.id
    assert jobs[0].state == ContactFetchJobState.QUEUED
    assert reused == 0


def test_enqueue_reuses_active_job(db_session: Session) -> None:
    from app.services.contact_fetch_service import ContactFetchService

    campaign = _seed_campaign(db_session)
    company = _seed_company(db_session, campaign)
    db_session.commit()

    svc = ContactFetchService()
    _, jobs1, _ = svc.enqueue(
        session=db_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    db_session.commit()

    _, jobs2, reused = svc.enqueue(
        session=db_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    db_session.commit()

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


def test_run_job_snov_upserts_contacts(db_session: Session, monkeypatch) -> None:
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

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].source_provider == "snov"
    assert contacts[0].first_name == "Alice"
    assert contacts[0].title == "CMO"


def test_run_job_apollo_upserts_contacts(db_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [{"id": "apollo-1", "first_name": "Bob", "last_name": "Jones", "title": "CTO", "linkedin_url": "https://li/bob"}],
    )

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].source_provider == "apollo"
    assert contacts[0].linkedin_url == "https://li/bob"


def test_run_job_apollo_first_skips_snov_when_apollo_finds_matches(
    db_session: Session, monkeypatch
) -> None:
    """Merged S3+S4 flow: Snov is fallback-only; if Apollo returned any match we skip Snov."""
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    snov_called: list[bool] = []

    def _snov_search(self, domain, page=1):
        snov_called.append(True)
        return ([{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}], 1, "")

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", _snov_search)
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [{"id": "apollo-1", "first_name": "Bob", "last_name": "Jones", "title": "CTO"}],
    )

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)
    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert {c.source_provider for c in contacts} == {"apollo"}
    assert snov_called == []  # Snov fallback must not have fired


def test_run_job_succeeds_when_one_provider_finds_contacts_and_other_fails(
    db_session: Session,
    monkeypatch,
) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospects",
        lambda self, domain, page=1: (
            [{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}],
            1,
            "",
        ),
    )

    def _apollo_auth_failed(self, domain, **kw):
        self.last_error_code = "apollo_auth_failed"
        return []

    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", _apollo_auth_failed)

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(
        engine=db_session.bind,
        contact_fetch_job_id=str(job.id),
    )

    db_session.refresh(job)
    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    apollo_attempt = db_session.exec(
        select(ContactProviderAttempt).where(
            col(ContactProviderAttempt.contact_fetch_job_id) == job.id,
            col(ContactProviderAttempt.provider) == "apollo",
        )
    ).one()

    assert job.state == ContactFetchJobState.SUCCEEDED
    assert job.contacts_found == 1
    assert len(contacts) == 1
    assert apollo_attempt.state == ContactProviderAttemptState.FAILED
    assert apollo_attempt.last_error_code == "apollo_auth_failed"


def test_run_job_repeated_run_upserts_not_duplicates(db_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: ([{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}], 1, ""),
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(db_session)
    company, job1 = _seed_job(db_session, campaign)
    svc = ContactFetchService()
    svc.run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job1.id))

    _, job2 = _seed_job(db_session, campaign)
    svc.run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job2.id))

    contacts = list(db_session.exec(
        select(Contact).where(col(Contact.company_id) == company.id, col(Contact.source_provider) == "snov")
    ))
    assert len(contacts) == 1


def test_run_job_title_match_applied(db_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models import TitleMatchRule

    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: ([{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "marketing director"}], 1, ""),
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(db_session)
    db_session.add(TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="marketing, director", match_type="keyword"))
    db_session.flush()
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contact = db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)).first()
    assert contact is not None
    assert contact.title_match is True


def test_run_job_sets_succeeded_state(db_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)
    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    db_session.refresh(job)
    assert job.state == ContactFetchJobState.SUCCEEDED
    assert job.terminal_state is True


def test_run_job_reuses_existing_provider_attempt_on_retry(db_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(
        snov_mod.SnovClient,
        "search_prospects",
        lambda self, domain, page=1: ([{"id": "snov-1", "first_name": "Alice", "last_name": "Smith", "position": "CMO"}], 1, ""),
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)
    db_session.add(
        ContactProviderAttempt(
            contact_fetch_job_id=job.id,
            provider="snov",
            sequence_index=0,
            state=ContactProviderAttemptState.FAILED,
            terminal_state=True,
        )
    )
    db_session.commit()

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    attempts = list(
        db_session.exec(
            select(ContactProviderAttempt).where(col(ContactProviderAttempt.contact_fetch_job_id) == job.id)
        )
    )
    snov_attempts = [attempt for attempt in attempts if attempt.provider == "snov"]
    assert len(snov_attempts) == 1
    assert snov_attempts[0].state == ContactProviderAttemptState.SUCCEEDED


# ── Task 2 (cont.) ───────────────────────────────────────────────��────────────

def test_force_refresh_creates_new_job(db_session: Session) -> None:
    from app.services.contact_fetch_service import ContactFetchService

    campaign = _seed_campaign(db_session)
    company = _seed_company(db_session, campaign)
    db_session.commit()

    svc = ContactFetchService()
    _, jobs1, _ = svc.enqueue(
        session=db_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=False,
    )
    db_session.commit()

    _, jobs2, reused = svc.enqueue(
        session=db_session,
        campaign_id=campaign.id,
        company_ids=[company.id],
        force_refresh=True,
    )
    db_session.commit()

    assert reused == 0
    assert jobs2[0].id != jobs1[0].id


# ── Gap 2: batch finalization ─────────────────────────────────────────────────

def test_batch_finalized_when_all_jobs_terminal(db_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models.pipeline import ContactFetchBatchState

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)
    batch_id = job.contact_fetch_batch_id

    ContactFetchService().run_contact_fetch_job(
        engine=db_session.bind,
        contact_fetch_job_id=str(job.id),
    )

    batch = db_session.get(ContactFetchBatch, batch_id)
    assert batch.state == ContactFetchBatchState.SUCCEEDED
    assert batch.finished_at is not None


def test_batch_marked_failed_when_any_job_fails(db_session: Session, monkeypatch) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models.pipeline import ContactFetchBatchState

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, "snov_failed"))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)
    batch_id = job.contact_fetch_batch_id

    ContactFetchService().run_contact_fetch_job(
        engine=db_session.bind,
        contact_fetch_job_id=str(job.id),
    )

    batch = db_session.get(ContactFetchBatch, batch_id)
    assert batch.state == ContactFetchBatchState.FAILED
    assert batch.finished_at is not None


# ── lock_expires_at ───────────────────────────────────────────────────────────

def test_cas_claim_sets_lock_expires_at(db_session: Session, monkeypatch) -> None:
    """Active jobs must have lock_expires_at set so reset-stuck won't touch them."""
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from datetime import timezone

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)
    db_session.commit()

    # Capture state mid-run by patching the apollo phase
    lock_expires_at_during_run: list = []
    original_run_apollo = ContactFetchService._run_apollo

    def patched_run_apollo(self, *, engine, **kwargs):
        with Session(engine) as s:
            j = s.get(ContactFetchJob, kwargs.get("job_id") or job.id)
            if j:
                lock_expires_at_during_run.append(j.lock_expires_at)
        return original_run_apollo(self, engine=engine, **kwargs)

    monkeypatch.setattr(ContactFetchService, "_run_apollo", patched_run_apollo)

    ContactFetchService().run_contact_fetch_job(
        engine=db_session.bind,
        contact_fetch_job_id=str(job.id),
    )

    assert len(lock_expires_at_during_run) > 0
    assert lock_expires_at_during_run[0] is not None
    assert lock_expires_at_during_run[0].tzinfo is not None  # timezone-aware


# ── Merged S3+S4 flow ────────────────────────────────────────────────────────

def test_snov_fallback_fires_when_apollo_returns_zero_matches(
    db_session: Session, monkeypatch
) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod
    from app.models import TitleMatchRule

    monkeypatch.setattr(apollo_mod.ApolloClient, "search_people", lambda self, domain, **kw: [])
    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: (
            [{"id": "snov-1", "first_name": "Alice", "last_name": "S", "position": "marketing director"}],
            1,
            "",
        ),
    )

    campaign = _seed_campaign(db_session)
    db_session.add(TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="marketing, director", match_type="keyword"))
    db_session.flush()
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].source_provider == "snov"
    assert contacts[0].title_match is True


def test_inline_reveal_attempted_for_apollo_without_search_email(
    db_session: Session, monkeypatch
) -> None:
    """Apollo search rarely returns the real email — reveal must be attempted
    regardless of `provider_has_email`, otherwise every Apollo contact would
    land in DB with email=NULL."""
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [{
            "id": "apollo-1", "first_name": "Bob", "last_name": "J", "title": "CTO",
            # no "email" key → provider_has_email becomes False, but reveal
            # should still be attempted via /people/match.
        }],
    )
    reveal_calls: list[str] = []
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "reveal_email",
        lambda self, pid: (reveal_calls.append(pid), None)[1],
    )

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].pipeline_stage == "fetched_no_email"
    assert contacts[0].email is None
    assert reveal_calls == ["apollo-1"]  # reveal must have been attempted


def test_inline_reveal_succeeds_promotes_to_email_revealed(
    db_session: Session, monkeypatch
) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [{
            "id": "apollo-1", "first_name": "Bob", "last_name": "J", "title": "CTO",
            "email": "b****@acme.com",  # masked → triggers provider_has_email=True
        }],
    )
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "reveal_email",
        lambda self, pid: {"id": pid, "email": "bob@acme.com"},
    )

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].email == "bob@acme.com"
    assert contacts[0].pipeline_stage == "email_revealed"
    assert contacts[0].email_provider == "apollo"


def test_no_title_rules_short_circuits_without_provider_calls(
    db_session: Session, monkeypatch
) -> None:
    """When the campaign has no include rules there is nothing to match
    against — the job must short-circuit without burning provider credits
    and without saving any contact rows."""
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    snov_calls: list[str] = []
    apollo_calls: list[str] = []
    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: (snov_calls.append(domain), ([], 0, ""))[1],
    )
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: (apollo_calls.append(domain), [])[1],
    )

    campaign = _seed_campaign(db_session, seed_rules=False)
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(
        engine=db_session.bind, contact_fetch_job_id=str(job.id),
    )

    db_session.refresh(job)
    assert job.state == ContactFetchJobState.SUCCEEDED
    assert job.terminal_state is True
    assert job.contacts_found == 0
    assert job.title_matched_count == 0
    assert job.last_error_code == "no_title_rules"
    assert snov_calls == []  # no provider calls — no wasted credits
    assert apollo_calls == []
    contacts = list(db_session.exec(
        select(Contact).where(col(Contact.company_id) == company.id)
    ))
    assert contacts == []  # nothing saved


def test_rerun_upserts_into_existing_row_by_name_not_duplicate(
    db_session: Session, monkeypatch
) -> None:
    """Re-running Discover after Snov's `provider_person_id` scheme changed
    (commit a9922fc) must update the existing row by (first_name, last_name)
    instead of inserting a duplicate."""
    from app.models import TitleMatchRule
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    # Apollo not configured — Snov fallback fires.
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [],
    )
    # Snov returns the same prospect we already have in DB but with a *new*
    # provider_person_id (this is exactly the schema-drift scenario).
    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospects",
        lambda self, domain, page=1: ([{
            "first_name": "Vic",
            "last_name": "Alfonsi",
            "position": "Vice President of Sales and Marketing",
            "search_emails_start": "https://api.snov.io/v2/.../newhashABC",
        }], 1, "") if page == 1 else ([], 0, ""),
    )
    monkeypatch.setattr(
        snov_mod.SnovClient, "search_prospect_email",
        lambda self, pid: ([{"email": "valfonsi@acme.com", "smtp_status": "valid"}], ""),
    )

    campaign = _seed_campaign(db_session)
    db_session.add(TitleMatchRule(
        campaign_id=campaign.id, rule_type="include",
        keywords="vice president", match_type="keyword",
    ))
    db_session.flush()
    company, job = _seed_job(db_session, campaign)

    # Pre-seed the stale row that an older Discover run left behind: same
    # person, but old-style provider_person_id and no email.
    db_session.add(Contact(
        company_id=company.id,
        source_provider="snov",
        provider_person_id="OLDHASH_xyz",
        first_name="Vic",
        last_name="Alfonsi",
        title="Vice President of Sales and Marketing",
        title_match=True,
        pipeline_stage="fetched",
    ))
    db_session.commit()

    ContactFetchService().run_contact_fetch_job(
        engine=db_session.bind, contact_fetch_job_id=str(job.id),
    )

    contacts = list(db_session.exec(
        select(Contact).where(col(Contact.company_id) == company.id)
    ))
    # Critical: exactly one row, no duplicate. The stale row was upserted in
    # place — pid migrated to the new value, email populated.
    assert len(contacts) == 1
    assert contacts[0].first_name == "Vic"
    assert contacts[0].last_name == "Alfonsi"
    assert contacts[0].email == "valfonsi@acme.com"
    assert contacts[0].provider_person_id == "newhashABC"
    assert contacts[0].pipeline_stage == "email_revealed"


def test_inline_reveal_failure_marks_fetched_no_email(
    db_session: Session, monkeypatch
) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    from app.services import snov_client as snov_mod
    from app.services import apollo_client as apollo_mod

    monkeypatch.setattr(snov_mod.SnovClient, "search_prospects", lambda self, domain, page=1: ([], 0, ""))
    monkeypatch.setattr(
        apollo_mod.ApolloClient, "search_people",
        lambda self, domain, **kw: [{
            "id": "apollo-1", "first_name": "Bob", "last_name": "J", "title": "CTO",
            "email": "b****@acme.com",
        }],
    )
    monkeypatch.setattr(apollo_mod.ApolloClient, "reveal_email", lambda self, pid: None)

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)

    ContactFetchService().run_contact_fetch_job(engine=db_session.bind, contact_fetch_job_id=str(job.id))

    contacts = list(db_session.exec(select(Contact).where(col(Contact.company_id) == company.id)))
    assert len(contacts) == 1
    assert contacts[0].pipeline_stage == "fetched_no_email"
    assert contacts[0].email is None


@pytest.mark.asyncio
async def test_reset_stuck_skips_active_job_with_future_lock(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reset-stuck must not reset a job whose lock hasn't expired yet."""
    from datetime import timedelta
    from sqlalchemy import update as _update
    from app.models.pipeline import utcnow
    from app.api.routes.companies import reset_stuck_contact_fetch_jobs
    from app.jobs import contact_fetch as cf_mod

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", lambda **kw: None)

    campaign = _seed_campaign(db_session)
    company, job = _seed_job(db_session, campaign)
    # Simulate active run: RUNNING + future lock
    future = utcnow() + timedelta(hours=1)
    db_session.execute(
        _update(ContactFetchJob)
        .where(col(ContactFetchJob.id) == job.id)
        .values(state=ContactFetchJobState.RUNNING, lock_expires_at=future, terminal_state=False)
    )
    db_session.commit()

    result = await reset_stuck_contact_fetch_jobs(session=db_session)

    assert result.reset_count == 0
    db_session.refresh(job)
    assert job.state == ContactFetchJobState.RUNNING  # untouched
