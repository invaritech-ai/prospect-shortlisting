from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.schemas.email_fetch import (
    EmailFetchBatchCreate,
    EmailFetchBatchRead,
    EmailFetchCompanyIds,
    EmailFetchCompanyList,
    EmailFetchCriteriaRead,
    EmailFetchCriteriaSaveRequest,
    EmailFetchPreviewRead,
    EmailFetchPreviewRequest,
)
from app.api.schemas.scrape import LetterCountsResponse
from app.db.session import get_session
from app.services.email_fetch_service import EmailFetchService, EmailFetchServiceError

router = APIRouter(prefix="/v1/email-fetch", tags=["email-fetch"])


def _service() -> EmailFetchService:
    return EmailFetchService()


async def _enqueue_email_fetch_batch(batch_id: UUID) -> None:
    from app.jobs.email_fetch import run_email_fetch_batch

    await run_email_fetch_batch.defer_async(batch_id=str(batch_id))


def _http_error(exc: EmailFetchServiceError) -> HTTPException:
    status_by_code = {
        "campaign_not_found": status.HTTP_404_NOT_FOUND,
        "domain_not_found": status.HTTP_404_NOT_FOUND,
        "batch_not_found": status.HTTP_404_NOT_FOUND,
        "no_domains": 422,
        "too_many_domains": 422,
        "no_include_title_criteria": 422,
        "invalid_fetch_mode": 422,
        "domain_not_fetchable": 422,
    }
    return HTTPException(
        status_code=status_by_code.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("/criteria", response_model=EmailFetchCriteriaRead)
def get_email_fetch_criteria(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> EmailFetchCriteriaRead:
    try:
        criteria = _service().get_criteria(session=session, campaign_id=campaign_id)
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    return EmailFetchCriteriaRead.model_validate(criteria, from_attributes=True)


@router.post("/criteria", response_model=EmailFetchCriteriaRead)
def save_email_fetch_criteria(
    body: EmailFetchCriteriaSaveRequest,
    session: Session = Depends(get_session),
) -> EmailFetchCriteriaRead:
    try:
        criteria = _service().save_criteria(
            session=session,
            campaign_id=body.campaign_id,
            include_titles=body.include_titles,
            exclude_titles=body.exclude_titles,
            target_contacts_per_company=body.target_contacts_per_company,
        )
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    return EmailFetchCriteriaRead.model_validate(criteria, from_attributes=True)


@router.get("/companies", response_model=EmailFetchCompanyList)
def list_email_fetch_companies(
    campaign_id: UUID = Query(...),
    status: str = Query(default="all"),
    search: str | None = Query(default=None),
    letter: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> EmailFetchCompanyList:
    if not isinstance(status, str):
        status = "all"
    if not isinstance(search, str):
        search = None
    if not isinstance(letter, str):
        letter = None
    if not isinstance(limit, int):
        limit = 50
    if not isinstance(offset, int):
        offset = 0
    try:
        companies = _service().list_companies(
            session=session,
            campaign_id=campaign_id,
            status=status,
            search=search,
            letter=letter,
            limit=limit,
            offset=offset,
        )
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    return EmailFetchCompanyList.model_validate(companies, from_attributes=True)


@router.get("/letter-counts", response_model=LetterCountsResponse)
def get_email_fetch_letter_counts(
    campaign_id: UUID = Query(...),
    status: str = Query(default="all"),
    search: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> LetterCountsResponse:
    if not isinstance(status, str):
        status = "all"
    if not isinstance(search, str):
        search = None
    try:
        counts = _service().get_letter_counts(
            session=session,
            campaign_id=campaign_id,
            status=status,
            search=search,
        )
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    return LetterCountsResponse(counts=counts)


@router.get("/company-ids", response_model=EmailFetchCompanyIds)
def list_email_fetch_company_ids(
    campaign_id: UUID = Query(...),
    status: str = Query(default="all"),
    search: str | None = Query(default=None),
    letter: str | None = Query(default=None),
    fetchable_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> EmailFetchCompanyIds:
    if not isinstance(status, str):
        status = "all"
    if not isinstance(search, str):
        search = None
    if not isinstance(letter, str):
        letter = None
    try:
        ids = _service().list_company_ids(
            session=session,
            campaign_id=campaign_id,
            status=status,
            search=search,
            letter=letter,
            fetchable_only=fetchable_only,
            limit=limit,
            offset=offset,
        )
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    return EmailFetchCompanyIds.model_validate(ids, from_attributes=True)


@router.post("/preview", response_model=EmailFetchPreviewRead)
def preview_email_fetch(
    body: EmailFetchPreviewRequest,
    session: Session = Depends(get_session),
) -> EmailFetchPreviewRead:
    try:
        preview = _service().preview(
            session=session,
            campaign_id=body.campaign_id,
            domain_ids=body.domain_ids,
            mode=body.mode,
        )
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    return EmailFetchPreviewRead.model_validate(preview, from_attributes=True)


@router.post("/batches", response_model=EmailFetchBatchRead, status_code=status.HTTP_201_CREATED)
async def create_email_fetch_batch(
    body: EmailFetchBatchCreate,
    session: Session = Depends(get_session),
) -> EmailFetchBatchRead:
    try:
        batch = _service().create_batch(
            session=session,
            campaign_id=body.campaign_id,
            domain_ids=body.domain_ids,
            mode=body.mode,
        )
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    await _enqueue_email_fetch_batch(batch.id)
    return EmailFetchBatchRead.model_validate(_service().get_batch(session=session, batch_id=batch.id), from_attributes=True)


@router.get("/batches/active", response_model=EmailFetchBatchRead | None)
def get_active_email_fetch_batch(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> EmailFetchBatchRead | None:
    try:
        batch = _service().get_active_batch(session=session, campaign_id=campaign_id)
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    if batch is None:
        return None
    return EmailFetchBatchRead.model_validate(batch, from_attributes=True)


@router.get("/batches/{batch_id}", response_model=EmailFetchBatchRead)
def get_email_fetch_batch(
    batch_id: UUID,
    session: Session = Depends(get_session),
) -> EmailFetchBatchRead:
    try:
        batch = _service().get_batch(session=session, batch_id=batch_id)
    except EmailFetchServiceError as exc:
        raise _http_error(exc) from exc
    return EmailFetchBatchRead.model_validate(batch, from_attributes=True)
