"""Integration: `ScrapeService.run_scrape` — the same code path Celery runs when the UI starts a scrape.

Not a CLI script: this is what your Docker worker executes after you enqueue a job from the app.

Enable the live network case with:
  PS_SCRAPE_PIPELINE_E2E=1 uv run pytest tests/test_scrape_pipeline_integration.py -q
"""
from __future__ import annotations

import os

import pytest
from sqlmodel import Session, select

from app.models import ScrapeJob, ScrapePage
from app.services.domain_policy import reset_default_manager_for_tests
from app.services.markdown_service import MarkdownService
from app.services.scrape_service import ScrapeService


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_domain_policy() -> None:
    reset_default_manager_for_tests()
    yield
    reset_default_manager_for_tests()


async def _fake_discover(**kwargs):  # noqa: ANN003
    del kwargs
    return {
        "home": "https://example.com/",
        "about": "",
        "products": "",
        "services": "",
        "pricing": "",
        "contact": "",
        "team": "",
        "leadership": "",
    }


def _fake_markdown_batch(self, pages, model):  # noqa: ANN001, ANN202
    return [("# Title\n\nBody.\n", False, "") for _ in pages]


@pytest.mark.skipif(
    os.environ.get("PS_SCRAPE_PIPELINE_E2E", "").strip() != "1",
    reason="Set PS_SCRAPE_PIPELINE_E2E=1 to run live pipeline (hits example.com)",
)
async def test_run_scrape_completes_for_example_com(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_engine,
    sqlite_session: Session,
) -> None:
    """End-to-end: DB job → run_scrape → pages persisted with static/impersonate tier."""
    from app.services import scrape_service as scrape_service_mod

    monkeypatch.setattr(scrape_service_mod, "discover_focus_targets", _fake_discover)
    monkeypatch.setattr(
        scrape_service_mod,
        "enqueue_s2_for_scrape_success",
        lambda **_: None,
    )
    monkeypatch.setattr(MarkdownService, "to_markdown_batch", _fake_markdown_batch)

    svc = ScrapeService()
    job = svc.create_job(
        session=sqlite_session,
        website_url="https://example.com/",
        js_fallback=True,
        include_sitemap=False,
        general_model="m",
        classify_model="m",
    )
    sqlite_session.commit()
    job_id = job.id

    await svc.run_scrape(engine=sqlite_engine, job_id=job_id, scrape_rules=None)

    sqlite_session.expire_all()
    rows = list(sqlite_session.exec(select(ScrapePage).where(ScrapePage.job_id == job_id)).all())
    assert rows, "expected at least one ScrapePage row"
    modes = {r.fetch_mode for r in rows if r.fetch_mode}
    assert modes & {"static", "impersonate", "stealth"}, f"unexpected fetch modes: {modes}"

    job_after = sqlite_session.get(ScrapeJob, job_id)
    assert job_after is not None
    assert job_after.status == "completed"
    assert job_after.terminal_state is True
