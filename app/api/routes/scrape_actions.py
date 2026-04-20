"""Scrape trigger endpoints: enqueue scrapes for selected or all companies."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from sqlmodel import Session, col, select

from app.api.schemas.upload import CompanyScrapeAllRequest, CompanyScrapeRequest, CompanyScrapeResult
from app.core.config import settings
from app.db.session import get_session
from app.models import Company, ScrapeJob
from app.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyUnavailableError,
    check_idempotency,
    clear_idempotency_reservation,
    normalize_idempotency_key,
    store_idempotency_response,
)
from app.services.scrape_rules_store import persist_rules_for_job
from app.services.url_utils import domain_from_url, normalize_url
from app.tasks.scrape import scrape_website


router = APIRouter(prefix="/v1", tags=["companies"])

SCRAPE_DEFAULTS = {
    "js_fallback": True,
    "include_sitemap": True,
}


def _enqueue_scrapes_for_companies(
    *,
    session: Session,
    companies: list[Company],
    scrape_rules: dict | None = None,
    idempotency_key: str | None = None,
    pipeline_run_id: UUID | None = None,
) -> CompanyScrapeResult:
    failed_company_ids: list[UUID] = []
    valid: list[tuple[Company, str, str]] = []
    for company in companies:
        normalized = normalize_url(company.normalized_url or company.website_url or "")
        if not normalized:
            failed_company_ids.append(company.id)
            continue
        domain = domain_from_url(normalized)
        if not domain:
            failed_company_ids.append(company.id)
            continue
        valid.append((company, normalized, domain))

    if not valid:
        return CompanyScrapeResult(
            requested_count=len(companies),
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=failed_company_ids,
            idempotency_key=idempotency_key,
            idempotency_replayed=False,
        )

    all_normalized = [v[1] for v in valid]
    active_urls: set[str] = set(
        session.exec(
            select(ScrapeJob.normalized_url)
            .where(
                col(ScrapeJob.normalized_url).in_(all_normalized)
                & col(ScrapeJob.terminal_state).is_(False)
            )
        ).all()
    )

    jobs_to_create: list[ScrapeJob] = []
    company_by_url: dict[str, UUID] = {}
    for company, normalized, domain in valid:
        if normalized in active_urls:
            continue
        jobs_to_create.append(
            ScrapeJob(
                website_url=company.normalized_url,
                normalized_url=normalized,
                domain=domain,
                pipeline_run_id=pipeline_run_id,
                js_fallback=(
                    bool(scrape_rules.get("js_fallback"))
                    if scrape_rules and scrape_rules.get("js_fallback") is not None
                    else SCRAPE_DEFAULTS["js_fallback"]
                ),
                include_sitemap=(
                    bool(scrape_rules.get("include_sitemap"))
                    if scrape_rules and scrape_rules.get("include_sitemap") is not None
                    else SCRAPE_DEFAULTS["include_sitemap"]
                ),
                general_model=settings.general_model,
                classify_model=settings.classify_model,
            )
        )
        company_by_url[normalized] = company.id

    if not jobs_to_create:
        return CompanyScrapeResult(
            requested_count=len(companies),
            queued_count=0,
            queued_job_ids=[],
            failed_company_ids=failed_company_ids,
            idempotency_key=idempotency_key,
            idempotency_replayed=False,
        )

    session.add_all(jobs_to_create)
    try:
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        for job in jobs_to_create:
            try:
                session.add(job)
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
                company_id = company_by_url.get(job.normalized_url)
                if company_id:
                    failed_company_ids.append(company_id)
        jobs_to_create = [j for j in jobs_to_create if j.id is not None]

    queued_job_ids: list[UUID] = []
    for job in jobs_to_create:
        if job.id is None:
            continue
        scrape_website.delay(str(job.id), scrape_rules=scrape_rules)
        persist_rules_for_job(session=session, job_id=job.id, rules=scrape_rules)
        queued_job_ids.append(job.id)

    return CompanyScrapeResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        queued_job_ids=queued_job_ids,
        failed_company_ids=failed_company_ids,
        idempotency_key=idempotency_key,
        idempotency_replayed=False,
    )


@router.post("/companies/scrape-selected", response_model=CompanyScrapeResult)
def scrape_selected_companies(
    payload: CompanyScrapeRequest,
    session: Session = Depends(get_session),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> CompanyScrapeResult:
    try:
        idempotency_key = normalize_idempotency_key(x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    request_payload = payload.model_dump(mode="json", exclude_none=True)
    request_payload["route"] = "companies/scrape-selected"
    try:
        replay = check_idempotency(
            namespace="scrape-selected",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
    except IdempotencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if replay.replayed and replay.response is not None:
        response_payload = dict(replay.response)
        response_payload["idempotency_replayed"] = True
        return CompanyScrapeResult(**response_payload)

    try:
        requested_ids = list(dict.fromkeys(payload.company_ids))
        stmt = select(Company).where(col(Company.id).in_(requested_ids))
        if payload.upload_id is not None:
            stmt = stmt.where(col(Company.upload_id) == payload.upload_id)
        companies = list(session.exec(stmt))
        if not companies:
            result = CompanyScrapeResult(
                requested_count=0,
                queued_count=0,
                queued_job_ids=[],
                failed_company_ids=requested_ids,
                idempotency_key=idempotency_key,
                idempotency_replayed=False,
            )
        else:
            result = _enqueue_scrapes_for_companies(
                session=session,
                companies=companies,
                scrape_rules=payload.scrape_rules.model_dump(exclude_none=True) if payload.scrape_rules else None,
                idempotency_key=idempotency_key,
            )
        store_idempotency_response(
            namespace="scrape-selected",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        clear_idempotency_reservation(
            namespace="scrape-selected",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
        raise


@router.post("/companies/scrape-all", response_model=CompanyScrapeResult)
def scrape_all_companies(
    payload: CompanyScrapeAllRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    upload_id: UUID | None = Query(default=None),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> CompanyScrapeResult:
    try:
        idempotency_key = normalize_idempotency_key(x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    effective_upload_id = payload.upload_id if payload and payload.upload_id is not None else upload_id
    scrape_rules = payload.scrape_rules.model_dump(exclude_none=True) if payload and payload.scrape_rules else None
    request_payload = {
        "route": "companies/scrape-all",
        "upload_id": str(effective_upload_id) if effective_upload_id else None,
        "scrape_rules": scrape_rules,
    }
    try:
        replay = check_idempotency(
            namespace="scrape-all",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
    except IdempotencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if replay.replayed and replay.response is not None:
        response_payload = dict(replay.response)
        response_payload["idempotency_replayed"] = True
        return CompanyScrapeResult(**response_payload)

    try:
        stmt = select(Company).order_by(col(Company.created_at).asc())
        if effective_upload_id is not None:
            stmt = stmt.where(col(Company.upload_id) == effective_upload_id)
        companies = list(session.exec(stmt))
        if not companies:
            result = CompanyScrapeResult(
                requested_count=0,
                queued_count=0,
                queued_job_ids=[],
                failed_company_ids=[],
                idempotency_key=idempotency_key,
                idempotency_replayed=False,
            )
        else:
            result = _enqueue_scrapes_for_companies(
                session=session,
                companies=companies,
                scrape_rules=scrape_rules,
                idempotency_key=idempotency_key,
            )

        store_idempotency_response(
            namespace="scrape-all",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response=result.model_dump(mode="json"),
        )
        return result
    except Exception:
        clear_idempotency_reservation(
            namespace="scrape-all",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
        raise
