from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.schemas.email_fetch import EmailFetchBatchCreate, EmailFetchPreviewRequest
from app.models import Campaign, ClassificationResult, Contact, EmailFetchBatch, FetchedPerson, RoleFetchCriteria, UploadedDomain


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_campaign_with_domain(session: Session) -> tuple[Campaign, UploadedDomain]:
    campaign = Campaign(id=uuid4(), name="API Campaign")
    domain = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        dedupe_key="example.com",
    )
    criteria = RoleFetchCriteria(
        campaign_id=campaign.id,
        name="Targeting",
        include_rules_json=[{"title": "Marketing Director"}],
        exclude_rules_json=[],
        criteria_hash="seed",
    )
    session.add_all([campaign, domain, criteria])
    session.commit()
    return campaign, domain


def test_preview_endpoint_returns_estimate_without_creating_batch(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    from app.api.routes import email_fetch
    from app.services.email_fetch_providers import ProviderCandidate, ProviderSearchResult

    class Apollo:
        name = "apollo"

        def search_candidates(self, *, domain: str, criteria, limit: int) -> ProviderSearchResult:  # noqa: ARG002
            return ProviderSearchResult(
                provider="apollo",
                candidates=[
                    ProviderCandidate(
                        provider="apollo",
                        provider_person_id="a1",
                        first_name="Ada",
                        last_name="Lovelace",
                        title="Marketing Director",
                    )
                ],
            )

        def fetch_email(self, *, candidate, domain):  # noqa: ANN001, ARG002
            raise AssertionError("preview must not reveal email")

    monkeypatch.setattr(email_fetch, "_service", lambda: email_fetch.EmailFetchService(apollo_provider=Apollo()))
    campaign, domain = _seed_campaign_with_domain(db_session)

    out = email_fetch.preview_email_fetch(
        body=EmailFetchPreviewRequest(campaign_id=campaign.id, domain_ids=[domain.id]),
        session=db_session,
    )

    assert out.selected_domain_count == 1
    assert out.estimated_apollo_reveals == 1
    assert db_session.exec(select(EmailFetchBatch)).all() == []


@pytest.mark.asyncio
async def test_create_batch_endpoint_persists_batch_and_enqueues_task(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    from app.api.routes import email_fetch

    enqueued: list[str] = []

    async def fake_enqueue(batch_id):
        enqueued.append(str(batch_id))

    monkeypatch.setattr(email_fetch, "_enqueue_email_fetch_batch", fake_enqueue)
    campaign, domain = _seed_campaign_with_domain(db_session)

    out = await email_fetch.create_email_fetch_batch(
        body=EmailFetchBatchCreate(campaign_id=campaign.id, domain_ids=[domain.id]),
        session=db_session,
    )

    batch = db_session.get(EmailFetchBatch, out.id)
    db_session.refresh(domain)
    assert batch is not None
    assert batch.selected_domain_ids_json == [str(domain.id)]
    assert domain.fetch_status == "queued"
    assert enqueued == [str(out.id)]


@pytest.mark.asyncio
async def test_create_batch_endpoint_rejects_completed_domain_without_refetch_mode(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    from app.api.routes import email_fetch

    async def fake_enqueue(batch_id):  # noqa: ANN001, ARG001
        raise AssertionError("ineligible fetch must not enqueue")

    monkeypatch.setattr(email_fetch, "_enqueue_email_fetch_batch", fake_enqueue)
    campaign, domain = _seed_campaign_with_domain(db_session)
    domain.fetch_status = "succeeded"
    db_session.add(
        Contact(
            campaign_id=campaign.id,
            domain_id=domain.id,
            first_name="Existing",
            last_name="Contact",
            title="Marketing Director",
            selected_email="existing@example.com",
        )
    )
    db_session.add(domain)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await email_fetch.create_email_fetch_batch(
            body=EmailFetchBatchCreate(campaign_id=campaign.id, domain_ids=[domain.id]),
            session=db_session,
        )

    db_session.refresh(domain)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "domain_not_fetchable"
    assert domain.fetch_status == "succeeded"


@pytest.mark.asyncio
async def test_create_batch_endpoint_refetch_mode_allows_completed_domain(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    from app.api.routes import email_fetch

    enqueued: list[str] = []

    async def fake_enqueue(batch_id):
        enqueued.append(str(batch_id))

    monkeypatch.setattr(email_fetch, "_enqueue_email_fetch_batch", fake_enqueue)
    campaign, domain = _seed_campaign_with_domain(db_session)
    domain.fetch_status = "succeeded"
    db_session.add(
        Contact(
            campaign_id=campaign.id,
            domain_id=domain.id,
            first_name="Existing",
            last_name="Contact",
            title="Marketing Director",
            selected_email="existing@example.com",
        )
    )
    db_session.add(domain)
    db_session.commit()

    out = await email_fetch.create_email_fetch_batch(
        body=EmailFetchBatchCreate(campaign_id=campaign.id, domain_ids=[domain.id], mode="refetch"),
        session=db_session,
    )

    batch = db_session.get(EmailFetchBatch, out.id)
    db_session.refresh(domain)
    assert batch is not None
    assert batch.selected_domain_ids_json == [str(domain.id)]
    assert batch.result_summary_json["mode"] == "refetch"
    assert domain.fetch_status == "queued"
    assert enqueued == [str(out.id)]


def test_get_batch_endpoint_maps_missing_batch_to_404(db_session: Session) -> None:
    from app.api.routes import email_fetch

    with pytest.raises(HTTPException) as exc:
        email_fetch.get_email_fetch_batch(batch_id=uuid4(), session=db_session)

    assert exc.value.status_code == 404


def test_get_active_email_fetch_batch_returns_latest_active_batch(db_session: Session) -> None:
    from app.api.routes import email_fetch

    campaign, domain = _seed_campaign_with_domain(db_session)
    domain.fetch_status = "queued"
    old_active = EmailFetchBatch(
        campaign_id=campaign.id,
        state="running",
        selected_domain_count=1,
        queued_count=1,
        selected_domain_ids_json=[str(domain.id)],
    )
    latest_active = EmailFetchBatch(
        campaign_id=campaign.id,
        state="queued",
        selected_domain_count=2,
        queued_count=2,
        selected_domain_ids_json=[str(domain.id)],
    )
    completed = EmailFetchBatch(
        campaign_id=campaign.id,
        state="succeeded",
        selected_domain_count=3,
        success_count=3,
    )
    db_session.add_all([domain, old_active, latest_active, completed])
    db_session.commit()

    active = email_fetch.get_active_email_fetch_batch(campaign_id=campaign.id, session=db_session)

    assert active is not None
    assert active.id == latest_active.id
    assert active.state == "queued"


def test_get_active_email_fetch_batch_returns_none_when_no_batch_is_active(db_session: Session) -> None:
    from app.api.routes import email_fetch

    campaign, _ = _seed_campaign_with_domain(db_session)
    db_session.add(
        EmailFetchBatch(
            campaign_id=campaign.id,
            state="succeeded",
            selected_domain_count=1,
            success_count=1,
        )
    )
    db_session.commit()

    assert email_fetch.get_active_email_fetch_batch(campaign_id=campaign.id, session=db_session) is None


def test_get_and_save_email_fetch_criteria_deactivates_previous_row(db_session: Session) -> None:
    from app.api.routes import email_fetch
    from app.api.schemas.email_fetch import EmailFetchCriteriaSaveRequest

    campaign, _ = _seed_campaign_with_domain(db_session)
    old = db_session.exec(select(RoleFetchCriteria).where(RoleFetchCriteria.campaign_id == campaign.id)).one()

    saved = email_fetch.save_email_fetch_criteria(
        body=EmailFetchCriteriaSaveRequest(
            campaign_id=campaign.id,
            include_titles=["CEO", "VP Sales"],
            exclude_titles=["Assistant"],
            target_contacts_per_company=3,
        ),
        session=db_session,
    )

    db_session.refresh(old)
    current = email_fetch.get_email_fetch_criteria(campaign_id=campaign.id, session=db_session)
    active_rows = db_session.exec(
        select(RoleFetchCriteria).where(
            RoleFetchCriteria.campaign_id == campaign.id,
            RoleFetchCriteria.is_active == True,  # noqa: E712
        )
    ).all()
    assert old.is_active is False
    assert len(active_rows) == 1
    assert current.id == saved.id
    assert current.include_titles == ["CEO", "VP Sales"]
    assert current.exclude_titles == ["Assistant"]
    assert current.target_contacts_per_company == 3


@pytest.mark.asyncio
async def test_create_batch_endpoint_rejects_missing_include_title_criteria(db_session: Session) -> None:
    from app.api.routes import email_fetch

    campaign = Campaign(id=uuid4(), name="No Criteria Campaign")
    domain = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        dedupe_key="example.com",
    )
    db_session.add_all([campaign, domain])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await email_fetch.create_email_fetch_batch(
            body=EmailFetchBatchCreate(campaign_id=campaign.id, domain_ids=[domain.id]),
            session=db_session,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "no_include_title_criteria"


def test_email_fetch_company_summary_defaults_to_possible_companies_and_counts_contacts(db_session: Session) -> None:
    from app.api.routes import email_fetch

    campaign = Campaign(id=uuid4(), name="Summary Campaign")
    old_uploaded_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    no_match_fetch_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    done = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://done.example",
        normalized_url="https://done.example",
        domain="done.example",
        dedupe_key="done.example",
        scrape_status="succeeded",
        decision_status="crap",
        fetch_status="succeeded",
        created_at=old_uploaded_at,
    )
    queued = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://queued.example",
        normalized_url="https://queued.example",
        domain="queued.example",
        dedupe_key="queued.example",
        scrape_status="succeeded",
        decision_status=None,
        fetch_status="queued",
        created_at=old_uploaded_at,
    )
    no_match = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://nomatch.example",
        normalized_url="https://nomatch.example",
        domain="nomatch.example",
        dedupe_key="nomatch.example",
        scrape_status="succeeded",
        decision_status=None,
        fetch_status="succeeded",
        fetch_updated_at=no_match_fetch_at,
        created_at=old_uploaded_at,
    )
    excluded = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://excluded.example",
        normalized_url="https://excluded.example",
        domain="excluded.example",
        dedupe_key="excluded.example",
        scrape_status="succeeded",
        decision_status="possible",
        fetch_status="succeeded",
        created_at=old_uploaded_at,
    )
    db_session.add_all([campaign, done, queued, no_match, excluded])
    db_session.add_all(
        [
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=done.id,
                state="succeeded",
                predicted_label="crap",
                manual_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=queued.id,
                state="succeeded",
                predicted_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=no_match.id,
                state="succeeded",
                predicted_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=excluded.id,
                state="succeeded",
                predicted_label="crap",
            ),
        ]
    )
    db_session.add_all(
        [
            Contact(
                campaign_id=campaign.id,
                domain_id=done.id,
                first_name="Ada",
                last_name="Lovelace",
                title="CEO",
                selected_email="ada@done.example",
                title_match=True,
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=done.id,
                first_name="Grace",
                last_name="Hopper",
                title="CTO",
                selected_email=None,
                title_match=True,
            ),
            FetchedPerson(
                campaign_id=campaign.id,
                domain_id=done.id,
                provider="snov",
                provider_person_id="snov-ignored",
                first_name="Ignored",
                last_name="Prospect",
                title="Finance Manager",
                match_status="not_matched",
                match_reason="Title did not match",
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=excluded.id,
                first_name="Ignored",
                last_name="Person",
                title="CEO",
                selected_email="ignored@excluded.example",
                title_match=True,
            ),
        ]
    )
    db_session.commit()

    out = email_fetch.list_email_fetch_companies(campaign_id=campaign.id, session=db_session)

    by_domain = {item.domain: item for item in out.items}
    assert set(by_domain) == {"done.example", "nomatch.example", "queued.example"}
    assert by_domain["done.example"].status == "done"
    assert by_domain["done.example"].contacts_found == 2
    assert by_domain["done.example"].emails_found == 1
    assert by_domain["done.example"].fetched_people_found == 3
    assert by_domain["queued.example"].status == "running"
    assert by_domain["nomatch.example"].status == "no_match"
    assert by_domain["nomatch.example"].updated_at == no_match_fetch_at
    assert out.counts.done == 1
    assert out.counts.running == 1
    assert out.counts.no_match == 1
    assert out.counts.contacts_found == 2
    assert out.counts.emails_found == 1
    assert out.counts.fetched_people_found == 3


def test_email_fetch_letter_counts_and_ids_use_possible_scope_and_fetchable_filter(db_session: Session) -> None:
    from app.api.routes import email_fetch

    campaign = Campaign(id=uuid4(), name="S3 Controls Campaign")
    possible_pending_a = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://alpha.example",
        normalized_url="https://alpha.example",
        domain="alpha.example",
        dedupe_key="alpha.example",
        scrape_status="succeeded",
        fetch_status=None,
    )
    possible_pending_b = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://beta.example",
        normalized_url="https://beta.example",
        domain="beta.example",
        dedupe_key="beta.example",
        scrape_status="succeeded",
        fetch_status=None,
    )
    possible_done_a = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://active.example",
        normalized_url="https://active.example",
        domain="active.example",
        dedupe_key="active.example",
        scrape_status="succeeded",
        fetch_status="succeeded",
    )
    excluded_pending_a = UploadedDomain(
        id=uuid4(),
        campaign_id=campaign.id,
        raw_url="https://archived.example",
        normalized_url="https://archived.example",
        domain="archived.example",
        dedupe_key="archived.example",
        scrape_status="succeeded",
        fetch_status=None,
    )
    db_session.add_all([campaign, possible_pending_a, possible_pending_b, possible_done_a, excluded_pending_a])
    db_session.add_all(
        [
            ClassificationResult(campaign_id=campaign.id, domain_id=possible_pending_a.id, state="succeeded", predicted_label="possible"),
            ClassificationResult(campaign_id=campaign.id, domain_id=possible_pending_b.id, state="succeeded", predicted_label="possible"),
            ClassificationResult(campaign_id=campaign.id, domain_id=possible_done_a.id, state="succeeded", predicted_label="possible"),
            ClassificationResult(campaign_id=campaign.id, domain_id=excluded_pending_a.id, state="succeeded", predicted_label="crap"),
            Contact(
                campaign_id=campaign.id,
                domain_id=possible_done_a.id,
                first_name="Done",
                last_name="Contact",
                selected_email="done@active.example",
            ),
        ]
    )
    db_session.commit()

    all_letters = email_fetch.get_email_fetch_letter_counts(campaign_id=campaign.id, status="all", search=None, session=db_session)
    pending_letters = email_fetch.get_email_fetch_letter_counts(campaign_id=campaign.id, status="pending", search=None, session=db_session)
    done_letters = email_fetch.get_email_fetch_letter_counts(campaign_id=campaign.id, status="done", search=None, session=db_session)
    ids = email_fetch.list_email_fetch_company_ids(
        campaign_id=campaign.id,
        status="all",
        search=None,
        letter=None,
        fetchable_only=True,
        limit=200,
        offset=0,
        session=db_session,
    )

    assert all_letters.counts == {"A": 2, "B": 1}
    assert pending_letters.counts == {"A": 1, "B": 1}
    assert done_letters.counts == {"A": 1}
    assert ids.total == 2
    assert ids.ids == [possible_pending_a.id, possible_pending_b.id]
