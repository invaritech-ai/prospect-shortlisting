from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

import app.models.classification  # noqa: F401
import app.models.core  # noqa: F401
import app.models.scrape  # noqa: F401
from app.api.routes import analysis
from app.api.schemas.analysis import AiReviewJobCreate
from app.models.classification import ClassificationBatch, ClassificationResult, DecisionSettings
from app.models.core import Campaign, UploadedDomain
from app.models.scrape import ScrapeResult


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _domain(campaign_id: UUID, domain: str, scrape_status: str = "succeeded") -> UploadedDomain:
    return UploadedDomain(
        id=uuid4(),
        campaign_id=campaign_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        dedupe_key=domain,
        scrape_status=scrape_status,
    )


def _scrape(campaign_id: UUID, domain_id: UUID) -> ScrapeResult:
    return ScrapeResult(
        id=uuid4(),
        campaign_id=campaign_id,
        domain_id=domain_id,
        state="succeeded",
        markdown_pages_count=1,
        scraped_pages_json=[{"url": "https://example.com", "markdown": "# Example"}],
    )


@pytest.mark.asyncio
async def test_create_ai_review_job_requires_active_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    with _session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        domain = _domain(campaign.id, "example.com")
        session.add(campaign)
        session.add(domain)
        session.add(_scrape(campaign.id, domain.id))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            await analysis.create_ai_review_job(
                body=AiReviewJobCreate(campaign_id=campaign.id, domain_ids=[domain.id]),
                session=session,
            )

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_create_ai_review_job_creates_batch_results_and_enqueues(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[str] = []

    async def fake_enqueue(result_ids: list[UUID]) -> None:
        enqueued.extend(str(rid) for rid in result_ids)

    monkeypatch.setattr(analysis, "_enqueue_ai_review_results", fake_enqueue)
    monkeypatch.setattr(analysis, "is_procrastinate_schema_ready", lambda _engine: True)

    with _session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        good = _domain(campaign.id, "good.com")
        no_markdown = _domain(campaign.id, "empty.com")
        failed_scrape = _domain(campaign.id, "failed.com", scrape_status="failed")
        settings = DecisionSettings(
            campaign_id=campaign.id,
            name="Rubric",
            instruction_text="Classify strictly as possible, unknown, or crap.",
            model="inclusionai/ring-2.6-1t",
            settings_hash="abc",
            is_active=True,
        )
        session.add_all([campaign, good, no_markdown, failed_scrape, settings])
        session.add(_scrape(campaign.id, good.id))
        session.add(
            ScrapeResult(
                campaign_id=campaign.id,
                domain_id=no_markdown.id,
                state="succeeded",
                markdown_pages_count=0,
                scraped_pages_json=[],
            )
        )
        session.commit()

        out = await analysis.create_ai_review_job(
            body=AiReviewJobCreate(campaign_id=campaign.id, domain_ids=[good.id, no_markdown.id, failed_scrape.id]),
            session=session,
        )
        batch = session.get(ClassificationBatch, out.id)
        results = session.exec(select(ClassificationResult)).all()

    assert out.selected_domain_count == 1
    assert out.queued_count == 1
    assert batch is not None
    assert batch.settings_snapshot_json == {
        "instruction_text": "Classify strictly as possible, unknown, or crap.",
        "model": "inclusionai/ring-2.6-1t",
    }
    assert len(results) == 1
    assert results[0].state == "queued"
    assert results[0].scrape_result_id is not None
    assert enqueued == [str(results[0].id)]


@pytest.mark.asyncio
async def test_create_ai_review_job_skips_domains_with_live_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_enqueue(result_ids: list[UUID]) -> None:
        raise AssertionError("no jobs should be enqueued")

    monkeypatch.setattr(analysis, "_enqueue_ai_review_results", fake_enqueue)
    monkeypatch.setattr(analysis, "is_procrastinate_schema_ready", lambda _engine: True)

    with _session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        domain = _domain(campaign.id, "live.com")
        settings = DecisionSettings(
            campaign_id=campaign.id,
            name="Rubric",
            instruction_text="Classify.",
            model="inclusionai/ring-2.6-1t",
            settings_hash="abc",
            is_active=True,
        )
        session.add_all([campaign, domain, settings])
        session.add(_scrape(campaign.id, domain.id))
        session.add(ClassificationResult(campaign_id=campaign.id, domain_id=domain.id, state="running"))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            await analysis.create_ai_review_job(
                body=AiReviewJobCreate(campaign_id=campaign.id, domain_ids=[domain.id]),
                session=session,
            )

    assert exc.value.status_code == 400


def test_ai_review_job_status_counts_terminal_states() -> None:
    with _session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        batch = ClassificationBatch(id=uuid4(), campaign_id=campaign.id, selected_domain_count=3)
        session.add(campaign)
        session.add(batch)
        for state in ["queued", "succeeded", "failed"]:
            session.add(
                ClassificationResult(
                    campaign_id=campaign.id,
                    domain_id=uuid4(),
                    classification_batch_id=batch.id,
                    state=state,
                )
            )
        session.commit()

        status = analysis.get_ai_review_job_status(batch_id=batch.id, session=session)

    assert status.state == "running"
    assert status.selected == 3
    assert status.queued == 1
    assert status.succeeded == 1
    assert status.failed == 1


def test_active_ai_review_job_uses_batch_state_without_scanning_results(monkeypatch: pytest.MonkeyPatch) -> None:
    with _session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        batch = ClassificationBatch(
            id=uuid4(),
            campaign_id=campaign.id,
            state="running",
            selected_domain_count=5,
            queued_count=3,
            success_count=1,
            failed_count=1,
        )
        session.add(campaign)
        session.add(batch)
        session.commit()

        def fail_status_scan(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("active AI job discovery should not scan classification results")

        monkeypatch.setattr(analysis, "_build_ai_review_job_status", fail_status_scan)
        active = analysis.get_active_ai_review_job(campaign_id=campaign.id, session=session)

    assert active is not None
    assert active.id == batch.id
    assert active.state == "running"
