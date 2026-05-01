"""Scrape run dispatcher: fast API accept + background Procrastinate batches."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.api.routes.campaigns import create_campaign
from app.api.routes.scrape_runs import get_scrape_run
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.upload import CompanyScrapeRequest
from app.models import Company, ScrapeJob, Upload
from app.models.pipeline import CompanyPipelineStage
from app.models.scrape import ScrapeRun, ScrapeRunItem, ScrapeRunItemStatus
from fastapi import HTTPException


def _seed_upload(session: Session, *, campaign_id) -> Upload:
    upload = Upload(
        campaign_id=campaign_id,
        filename="scrape-run.csv",
        checksum=str(uuid4()),
        row_count=3,
        valid_count=3,
        invalid_count=0,
    )
    session.add(upload)
    session.flush()
    return upload


def _seed_company(session: Session, *, upload_id, domain: str) -> Company:
    company = Company(
        upload_id=upload_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=CompanyPipelineStage.UPLOADED,
    )
    session.add(company)
    session.flush()
    return company


def _count_scrape_jobs(session: Session) -> int:
    return len(list(session.exec(select(ScrapeJob))))


# ---------------------------------------------------------------------------
# Phase A tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_selected_returns_immediately(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import companies as companies_route
    from app.jobs import scrape as scrape_mod

    dispatched: list[dict] = []

    async def fake_dispatch(**kw):
        dispatched.append(kw)

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "defer_async", fake_dispatch)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape Run Immediate"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    companies = [
        _seed_company(sqlite_session, upload_id=upload.id, domain=f"r{i}.example")
        for i in range(5)
    ]
    sqlite_session.commit()
    before_jobs = _count_scrape_jobs(sqlite_session)

    result = await companies_route.scrape_selected_companies(
        payload=CompanyScrapeRequest(
            campaign_id=campaign.id,
            upload_id=upload.id,
            company_ids=[c.id for c in companies],
        ),
        session=sqlite_session,
    )

    assert result.status == "accepted"
    assert result.requested_count == 5
    assert _count_scrape_jobs(sqlite_session) == before_jobs
    assert len(dispatched) == 1
    assert len(list(sqlite_session.exec(
        select(ScrapeRunItem).where(ScrapeRunItem.run_id == result.id)
    ))) == 5


@pytest.mark.asyncio
async def test_scrape_selected_rejects_out_of_scope_ids(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Company IDs from a different campaign → 400 with invalid_ids list."""
    from app.api.routes import companies as companies_route
    from app.jobs import scrape as scrape_mod

    async def fake_dispatch(**kw):  # noqa: ARG001
        pass

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "defer_async", fake_dispatch)

    campaign_a = create_campaign(payload=CampaignCreate(name="Camp A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Camp B"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="a.example")
    company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="b.example")
    sqlite_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await companies_route.scrape_selected_companies(
            payload=CompanyScrapeRequest(
                campaign_id=campaign_a.id,
                company_ids=[company_a.id, company_b.id],
            ),
            session=sqlite_session,
        )

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["code"] == "company_ids_out_of_scope"
    assert str(company_b.id) in detail["invalid_ids"]
    assert str(company_a.id) not in detail["invalid_ids"]


@pytest.mark.asyncio
async def test_dispatcher_creates_jobs_in_batches(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.jobs import scrape as scrape_mod

    monkeypatch.setattr(scrape_mod, "get_engine", lambda: sqlite_session.get_bind())
    monkeypatch.setattr(scrape_mod, "DISPATCH_BATCH_SIZE", 25)
    monkeypatch.setattr(scrape_mod, "available_slots", lambda _e, _q, requested: requested)

    bulk_sizes: list[int] = []

    async def fake_bulk(*, priority: int, job_ids: list, scrape_rules):  # noqa: ARG001
        bulk_sizes.append(len(job_ids))

    monkeypatch.setattr(scrape_mod, "defer_scrape_website_bulk", fake_bulk)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape Run Batches"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    companies = [
        _seed_company(sqlite_session, upload_id=upload.id, domain=f"b{i}.example")
        for i in range(60)
    ]
    run = ScrapeRun(campaign_id=campaign.id, requested_count=60)
    sqlite_session.add(run)
    sqlite_session.flush()
    sqlite_session.add_all(
        [ScrapeRunItem(run_id=run.id, company_id=c.id) for c in companies],
    )
    sqlite_session.commit()

    await scrape_mod.dispatch_scrape_run(str(run.id))

    assert bulk_sizes == [25, 25, 10]
    sqlite_session.expire_all()
    run_r = sqlite_session.get(ScrapeRun, run.id)
    assert run_r is not None
    assert run_r.status == "completed"
    assert run_r.queued_count == 60


@pytest.mark.asyncio
async def test_dispatcher_is_resumable(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Items already QUEUED are skipped; only PENDING items get new jobs."""
    from app.jobs import scrape as scrape_mod

    monkeypatch.setattr(scrape_mod, "get_engine", lambda: sqlite_session.get_bind())
    monkeypatch.setattr(scrape_mod, "DISPATCH_BATCH_SIZE", 100)
    monkeypatch.setattr(scrape_mod, "available_slots", lambda _e, _q, requested: requested)

    async def noop_bulk(**kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(scrape_mod, "defer_scrape_website_bulk", noop_bulk)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape Run Resume"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    companies = [
        _seed_company(sqlite_session, upload_id=upload.id, domain=f"s{i}.example")
        for i in range(50)
    ]
    run = ScrapeRun(campaign_id=campaign.id, requested_count=50)
    sqlite_session.add(run)
    sqlite_session.flush()
    items = [ScrapeRunItem(run_id=run.id, company_id=c.id) for c in companies]
    sqlite_session.add_all(items)
    sqlite_session.flush()
    for item in items[:20]:
        item.status = ScrapeRunItemStatus.QUEUED
        sqlite_session.add(item)
    sqlite_session.commit()

    before = _count_scrape_jobs(sqlite_session)
    await scrape_mod.dispatch_scrape_run(str(run.id))
    assert _count_scrape_jobs(sqlite_session) - before == 30


@pytest.mark.asyncio
async def test_dispatcher_resumes_job_created_items(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JOB_CREATED items (job exists, prior defer failed) are re-deferred without creating new jobs."""
    from app.jobs import scrape as scrape_mod

    monkeypatch.setattr(scrape_mod, "get_engine", lambda: sqlite_session.get_bind())
    monkeypatch.setattr(scrape_mod, "available_slots", lambda _e, _q, r: r)

    deferred_job_ids: list[str] = []

    async def fake_bulk(*, priority, job_ids, scrape_rules):  # noqa: ARG001
        deferred_job_ids.extend(str(j) for j in job_ids)

    monkeypatch.setattr(scrape_mod, "defer_scrape_website_bulk", fake_bulk)

    campaign = create_campaign(
        payload=CampaignCreate(name="Resume JOB_CREATED"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    c = _seed_company(sqlite_session, upload_id=upload.id, domain="jc.example")

    existing_job = ScrapeJob(
        website_url="https://jc.example",
        normalized_url="https://jc.example",
        domain="jc.example",
    )
    sqlite_session.add(existing_job)
    sqlite_session.flush()

    run = ScrapeRun(campaign_id=campaign.id, requested_count=1)
    sqlite_session.add(run)
    sqlite_session.flush()
    item = ScrapeRunItem(
        run_id=run.id,
        company_id=c.id,
        scrape_job_id=existing_job.id,
        status=ScrapeRunItemStatus.JOB_CREATED,
    )
    sqlite_session.add(item)
    sqlite_session.commit()

    before_jobs = _count_scrape_jobs(sqlite_session)
    await scrape_mod.dispatch_scrape_run(str(run.id))

    # No new ScrapeJob rows — only the existing one was deferred
    assert _count_scrape_jobs(sqlite_session) == before_jobs
    assert str(existing_job.id) in deferred_job_ids

    sqlite_session.expire_all()
    updated_item = sqlite_session.get(ScrapeRunItem, item.id)
    assert updated_item.status == ScrapeRunItemStatus.QUEUED


@pytest.mark.asyncio
async def test_dispatcher_respects_backpressure(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.jobs import scrape as scrape_mod

    monkeypatch.setattr(scrape_mod, "get_engine", lambda: sqlite_session.get_bind())
    bulk_calls: list[int] = []
    configure_kwargs: list[dict] = []
    defer_kwargs: list[dict] = []

    class FakeConfigured:
        async def defer_async(self, **kw):
            defer_kwargs.append(kw)

    def fake_configure(**kw):
        configure_kwargs.append(kw)
        return FakeConfigured()

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "configure", fake_configure)

    async def fake_bulk(*, priority: int, job_ids: list, scrape_rules):  # noqa: ARG001
        bulk_calls.append(len(job_ids))

    monkeypatch.setattr(scrape_mod, "defer_scrape_website_bulk", fake_bulk)
    monkeypatch.setattr(scrape_mod, "available_slots", lambda *_a, **_k: 0)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape Run Backpressure"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    c = _seed_company(sqlite_session, upload_id=upload.id, domain="bp.example")
    run = ScrapeRun(campaign_id=campaign.id, requested_count=1)
    sqlite_session.add(run)
    sqlite_session.flush()
    sqlite_session.add(ScrapeRunItem(run_id=run.id, company_id=c.id))
    sqlite_session.commit()

    await scrape_mod.dispatch_scrape_run(str(run.id))

    assert bulk_calls == []
    assert len(configure_kwargs) == 1
    assert configure_kwargs[0] == {"schedule_in": {"seconds": 60}}
    assert len(defer_kwargs) == 1
    assert defer_kwargs[0] == {"run_id": str(run.id)}


def test_scrape_run_status_endpoint(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Run Status"), session=sqlite_session)
    run = ScrapeRun(campaign_id=campaign.id, requested_count=3)
    sqlite_session.add(run)
    sqlite_session.commit()

    read = get_scrape_run(run.id, session=sqlite_session)
    assert read.id == run.id
    assert read.status == "accepted"
    assert read.requested_count == 3


def test_scrape_run_unknown_returns_404(sqlite_session: Session) -> None:
    import uuid

    with pytest.raises(HTTPException) as excinfo:
        get_scrape_run(uuid.uuid4(), session=sqlite_session)
    assert excinfo.value.status_code == 404


# ---------------------------------------------------------------------------
# Phase B tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_all_returns_scrape_run(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import companies as companies_route
    from app.jobs import scrape as scrape_mod

    dispatched: list[dict] = []

    async def fake_dispatch(**kw):
        dispatched.append(kw)

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "defer_async", fake_dispatch)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape All Run"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    companies = [
        _seed_company(sqlite_session, upload_id=upload.id, domain=f"sa{i}.example")
        for i in range(4)
    ]
    sqlite_session.commit()
    before_jobs = _count_scrape_jobs(sqlite_session)

    result = await companies_route.scrape_all_companies(
        campaign_id=campaign.id,
        session=sqlite_session,
    )

    assert result.status == "accepted"
    assert result.requested_count == 4
    assert _count_scrape_jobs(sqlite_session) == before_jobs
    assert len(dispatched) == 1
    items = list(sqlite_session.exec(
        select(ScrapeRunItem).where(ScrapeRunItem.run_id == result.id)
    ))
    assert len(items) == 4


# ---------------------------------------------------------------------------
# Phase C tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_matching_creates_run_from_filters(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import companies as companies_route
    from app.api.schemas.upload import CompanyScrapeByFiltersRequest
    from app.jobs import scrape as scrape_mod

    dispatched: list[dict] = []

    async def fake_dispatch(**kw):
        dispatched.append(kw)

    monkeypatch.setattr(scrape_mod.dispatch_scrape_run, "defer_async", fake_dispatch)

    campaign = create_campaign(
        payload=CampaignCreate(name="Scrape Matching"), session=sqlite_session
    )
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    [
        _seed_company(sqlite_session, upload_id=upload.id, domain=f"fm{i}.example")
        for i in range(7)
    ]
    sqlite_session.commit()
    before_jobs = _count_scrape_jobs(sqlite_session)

    result = await companies_route.scrape_matching_companies(
        payload=CompanyScrapeByFiltersRequest(campaign_id=campaign.id),
        session=sqlite_session,
    )

    assert result.status == "accepted"
    assert result.requested_count == 7
    assert _count_scrape_jobs(sqlite_session) == before_jobs
    assert len(dispatched) == 1
    items = list(sqlite_session.exec(
        select(ScrapeRunItem).where(ScrapeRunItem.run_id == result.id)
    ))
    assert len(items) == 7
