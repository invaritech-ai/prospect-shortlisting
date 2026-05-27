"""Procrastinate task: classify one scraped domain with an AI decision prompt."""
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
from uuid import UUID

from procrastinate import RetryStrategy
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.db.session import get_engine
from app.models.classification import ClassificationBatch, ClassificationResult
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeResult
from app.queue import app
from app.services.llm_client import ERR_RATE_LIMITED, ERR_SERVER_ERROR, ERR_TIMEOUT, LLMClient
from app.services.llm_rate_limiter import wait_for_llm_slot

logger = logging.getLogger(__name__)

_client = LLMClient(purpose="ai_decision", max_retries=1, default_timeout=180)
_RETRYABLE_LLM_ERRORS = {ERR_RATE_LIMITED, ERR_SERVER_ERROR, ERR_TIMEOUT}
_ALLOWED_LABELS = {"possible", "unknown", "crap"}


@app.task(
    name="classify_domain",
    queue="ai_decision",
    retry=RetryStrategy(max_attempts=3, wait=60),
)
async def classify_domain(result_id: str) -> None:
    _run_classify_domain(result_id)


def _normalize_label(value: Any) -> str | None:
    label = str(value or "").strip().lower()
    return label if label in _ALLOWED_LABELS else None


def _normalize_confidence(value: Any) -> Decimal | None:
    try:
        confidence = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if confidence > 1:
        confidence = confidence / Decimal("100")
    if confidence < 0:
        confidence = Decimal("0")
    if confidence > 1:
        confidence = Decimal("1")
    return confidence.quantize(Decimal("0.0001"))


def _page_markdown(page: dict[str, Any]) -> str:
    for key in ("markdown", "content", "text"):
        value = page.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _input_payload(*, domain: UploadedDomain, scrape: ScrapeResult) -> dict[str, Any]:
    pages = []
    for page in scrape.scraped_pages_json or []:
        markdown = _page_markdown(page)
        if not markdown:
            continue
        pages.append({
            "url": page.get("url") or page.get("final_url") or domain.normalized_url,
            "markdown": markdown[:60000],
        })
    return {
        "domain": domain.domain,
        "raw_url": domain.raw_url,
        "normalized_url": domain.normalized_url,
        "pages": pages,
    }


def _build_messages(*, instruction_text: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                instruction_text.strip()
                + "\n\nReturn JSON only with keys: predicted_label, confidence, reasoning, evidence. "
                + "predicted_label must be one of possible, unknown, crap. confidence must be 0-1."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=True),
        },
    ]


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_llm_json") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid_llm_json")
    return parsed


def _mark_failed(session: Session, result: ClassificationResult, *, error_code: str, message: str) -> None:
    result.state = "failed"
    result.reasoning_json = {"error_code": error_code, "message": message}
    session.add(result)
    _refresh_batch(session, result.classification_batch_id)


def _refresh_batch(session: Session, batch_id: UUID | None) -> None:
    if batch_id is None:
        return
    batch = session.get(ClassificationBatch, batch_id)
    if batch is None:
        return
    rows = session.exec(
        select(col(ClassificationResult.state))
        .where(col(ClassificationResult.classification_batch_id) == batch_id)
    ).all()
    batch.success_count = sum(1 for state in rows if state == "succeeded")
    batch.failed_count = sum(1 for state in rows if state == "failed")
    batch.queued_count = sum(1 for state in rows if state in {"queued", "running"})
    terminal = batch.success_count + batch.failed_count
    if rows and terminal >= len(rows):
        batch.state = "succeeded" if batch.failed_count == 0 else "failed"
        from app.models.base import utcnow
        batch.finished_at = utcnow()
    else:
        batch.state = "running"
    session.add(batch)


def _run_classify_domain(result_id: str) -> None:
    result_uuid = UUID(result_id)
    engine = get_engine()
    log_event(logger, "ai_decision_task_start", result_id=result_id)

    with Session(engine) as session:
        updated = session.execute(
            sa_update(ClassificationResult)
            .where(
                col(ClassificationResult.id) == result_uuid,
                col(ClassificationResult.state) == "queued",
            )
            .values(state="running")
            .returning(ClassificationResult.id)
        )
        claimed = updated.first()
        session.commit()
        if not claimed:
            log_event(logger, "ai_decision_skipped_unclaimable", result_id=result_id)
            return

    with Session(engine) as session:
        result = session.get(ClassificationResult, result_uuid)
        if result is None:
            return
        domain = session.get(UploadedDomain, result.domain_id)
        scrape = session.get(ScrapeResult, result.scrape_result_id) if result.scrape_result_id else None
        batch = session.get(ClassificationBatch, result.classification_batch_id) if result.classification_batch_id else None
        if domain is None or scrape is None:
            _mark_failed(session, result, error_code="missing_scrape_input", message="Missing domain or scrape result.")
            session.commit()
            return
        settings = batch.settings_snapshot_json if batch and batch.settings_snapshot_json else {}
        instruction_text = str(settings.get("instruction_text") or "").strip()
        model = str(settings.get("model") or "").strip()
        if not instruction_text or not model:
            _mark_failed(session, result, error_code="missing_decision_settings", message="Missing AI decision prompt or model.")
            session.commit()
            return
        payload = _input_payload(domain=domain, scrape=scrape)
        if not payload["pages"]:
            _mark_failed(session, result, error_code="no_markdown_input", message="No markdown pages available for AI decision.")
            session.commit()
            return

    wait_for_llm_slot(session_factory=lambda: Session(engine), provider="openrouter", purpose="ai_decision")
    content, error, usage = _client.chat_with_usage(
        model=model,
        messages=_build_messages(instruction_text=instruction_text, payload=payload),
        temperature=0.0,
        response_format={"type": "json_object"},
        timeout=180,
    )

    if error:
        if error in _RETRYABLE_LLM_ERRORS:
            with Session(engine) as session:
                result = session.get(ClassificationResult, result_uuid)
                if result is not None:
                    result.state = "queued"
                    session.add(result)
                    session.commit()
            raise RuntimeError(f"retryable AI decision error: {error}")
        with Session(engine) as session:
            result = session.get(ClassificationResult, result_uuid)
            if result is not None:
                _mark_failed(session, result, error_code=error, message="AI decision call failed.")
                session.commit()
        return

    try:
        parsed = _extract_json_object(content)
        label = _normalize_label(parsed.get("predicted_label") or parsed.get("label"))
        confidence = _normalize_confidence(parsed.get("confidence"))
        if label is None or confidence is None:
            raise ValueError("invalid_llm_schema")
    except ValueError as exc:
        with Session(engine) as session:
            result = session.get(ClassificationResult, result_uuid)
            if result is not None:
                _mark_failed(session, result, error_code=str(exc), message="AI decision returned invalid JSON.")
                session.commit()
        return

    reasoning = parsed.get("reasoning") if isinstance(parsed.get("reasoning"), dict) else {"summary": str(parsed.get("reasoning") or "")}
    evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), dict) else {"evidence": parsed.get("evidence") or []}
    input_hash = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    with Session(engine) as session:
        result = session.get(ClassificationResult, result_uuid)
        domain = session.get(UploadedDomain, result.domain_id) if result else None
        if result is None:
            return
        result.predicted_label = label
        result.confidence = confidence
        result.reasoning_json = {**reasoning, "usage": usage}
        result.evidence_json = evidence
        result.input_hash = input_hash
        result.state = "succeeded"
        session.add(result)
        if domain is not None:
            domain.decision_status = label
            session.add(domain)
        _refresh_batch(session, result.classification_batch_id)
        session.commit()
        log_event(logger, "ai_decision_completed", result_id=result_id, domain=domain.domain if domain else None, label=label)
