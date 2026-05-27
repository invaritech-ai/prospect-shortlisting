from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine

import app.models.classification  # noqa: F401
import app.models.core  # noqa: F401
import app.models.llm_rate_limit  # noqa: F401
import app.models.scrape  # noqa: F401
from app.jobs import ai_decision
from app.models.classification import ClassificationBatch, ClassificationResult
from app.models.core import Campaign, UploadedDomain
from app.models.scrape import ScrapeResult


def _engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


def test_classify_domain_writes_successful_result(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    campaign_id = uuid4()
    domain_id = uuid4()
    batch_id = uuid4()
    result_id = uuid4()
    scrape_id = uuid4()
    with Session(engine) as session:
        session.add(Campaign(id=campaign_id, name="C1"))
        session.add(
            UploadedDomain(
                id=domain_id,
                campaign_id=campaign_id,
                raw_url="https://example.com",
                normalized_url="https://example.com",
                domain="example.com",
                dedupe_key="example.com",
                scrape_status="succeeded",
            )
        )
        session.add(
            ScrapeResult(
                id=scrape_id,
                campaign_id=campaign_id,
                domain_id=domain_id,
                state="succeeded",
                markdown_pages_count=1,
                scraped_pages_json=[{"url": "https://example.com", "markdown": "Distributor catalog"}],
            )
        )
        session.add(
            ClassificationBatch(
                id=batch_id,
                campaign_id=campaign_id,
                selected_domain_count=1,
                queued_count=1,
                settings_hash="hash1",
                settings_snapshot_json={"instruction_text": "Return JSON", "model": "model-a"},
            )
        )
        session.add(
            ClassificationResult(
                id=result_id,
                campaign_id=campaign_id,
                domain_id=domain_id,
                scrape_result_id=scrape_id,
                classification_batch_id=batch_id,
                state="queued",
                settings_hash="hash1",
            )
        )
        session.commit()

    class FakeClient:
        def chat_with_usage(self, **kwargs):
            return json.dumps({
                "predicted_label": "possible",
                "confidence": 0.92,
                "reasoning": {"summary": "Good fit"},
                "evidence": {"evidence": [{"quote": "Distributor catalog"}]},
            }), "", {"prompt_tokens": 10, "completion_tokens": 20}

    monkeypatch.setattr(ai_decision, "get_engine", lambda: engine)
    monkeypatch.setattr(ai_decision, "_client", FakeClient())
    monkeypatch.setattr(ai_decision, "wait_for_llm_slot", lambda **kwargs: None)

    ai_decision._run_classify_domain(str(result_id))

    with Session(engine) as session:
        result = session.get(ClassificationResult, result_id)
        batch = session.get(ClassificationBatch, batch_id)
        domain = session.get(UploadedDomain, domain_id)

    assert result is not None
    assert result.state == "succeeded"
    assert result.predicted_label == "possible"
    assert result.confidence == Decimal("0.9200")
    assert result.reasoning_json["summary"] == "Good fit"
    assert result.evidence_json["evidence"][0]["quote"] == "Distributor catalog"
    assert batch is not None and batch.success_count == 1 and batch.state == "succeeded"
    assert domain is not None and domain.decision_status == "possible"


def test_classify_domain_marks_invalid_json_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    campaign_id = uuid4()
    domain_id = uuid4()
    batch_id = uuid4()
    result_id = uuid4()
    scrape_id = uuid4()
    with Session(engine) as session:
        session.add(Campaign(id=campaign_id, name="C1"))
        session.add(UploadedDomain(id=domain_id, campaign_id=campaign_id, raw_url="https://x.com", normalized_url="https://x.com", domain="x.com", dedupe_key="x.com", scrape_status="succeeded"))
        session.add(ScrapeResult(id=scrape_id, campaign_id=campaign_id, domain_id=domain_id, state="succeeded", markdown_pages_count=1, scraped_pages_json=[{"markdown": "Text"}]))
        session.add(ClassificationBatch(id=batch_id, campaign_id=campaign_id, selected_domain_count=1, queued_count=1, settings_snapshot_json={"instruction_text": "Return JSON", "model": "model-a"}))
        session.add(ClassificationResult(id=result_id, campaign_id=campaign_id, domain_id=domain_id, scrape_result_id=scrape_id, classification_batch_id=batch_id, state="queued"))
        session.commit()

    class FakeClient:
        def chat_with_usage(self, **kwargs):
            return "not json", "", {}

    monkeypatch.setattr(ai_decision, "get_engine", lambda: engine)
    monkeypatch.setattr(ai_decision, "_client", FakeClient())
    monkeypatch.setattr(ai_decision, "wait_for_llm_slot", lambda **kwargs: None)

    ai_decision._run_classify_domain(str(result_id))

    with Session(engine) as session:
        result = session.get(ClassificationResult, result_id)
        batch = session.get(ClassificationBatch, batch_id)

    assert result is not None and result.state == "failed"
    assert result.reasoning_json["error_code"] == "invalid_llm_json"
    assert batch is not None and batch.failed_count == 1 and batch.state == "failed"


def test_classify_domain_raises_retryable_llm_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    campaign_id = uuid4()
    domain_id = uuid4()
    result_id = uuid4()
    scrape_id = uuid4()
    batch_id = uuid4()
    with Session(engine) as session:
        session.add(Campaign(id=campaign_id, name="C1"))
        session.add(UploadedDomain(id=domain_id, campaign_id=campaign_id, raw_url="https://x.com", normalized_url="https://x.com", domain="x.com", dedupe_key="x.com", scrape_status="succeeded"))
        session.add(ScrapeResult(id=scrape_id, campaign_id=campaign_id, domain_id=domain_id, state="succeeded", markdown_pages_count=1, scraped_pages_json=[{"markdown": "Text"}]))
        session.add(ClassificationBatch(id=batch_id, campaign_id=campaign_id, selected_domain_count=1, queued_count=1, settings_snapshot_json={"instruction_text": "Return JSON", "model": "model-a"}))
        session.add(ClassificationResult(id=result_id, campaign_id=campaign_id, domain_id=domain_id, scrape_result_id=scrape_id, classification_batch_id=batch_id, state="queued"))
        session.commit()

    class FakeClient:
        def chat_with_usage(self, **kwargs):
            return "", "llm_rate_limited", {}

    monkeypatch.setattr(ai_decision, "get_engine", lambda: engine)
    monkeypatch.setattr(ai_decision, "_client", FakeClient())
    monkeypatch.setattr(ai_decision, "wait_for_llm_slot", lambda **kwargs: None)

    with pytest.raises(RuntimeError):
        ai_decision._run_classify_domain(str(result_id))

    with Session(engine) as session:
        result = session.get(ClassificationResult, result_id)
    assert result is not None and result.state == "queued"
