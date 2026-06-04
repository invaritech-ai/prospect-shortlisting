from __future__ import annotations

import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from app.api.schemas.email_verification import (
    EmailVerificationBatchCreate,
    EmailVerificationBatchRead,
    EmailVerificationContactIds,
    EmailVerificationContactList,
    EmailVerificationPreviewRead,
    EmailVerificationPreviewRequest,
)
from app.api.schemas.scrape import LetterCountsResponse
from app.db.session import get_session
from app.services.email_verification_service import (
    EmailVerificationService,
    EmailVerificationServiceError,
)

router = APIRouter(prefix="/v1/email-verification", tags=["email-verification"])

VALID_EMAIL_EXPORT_COLUMNS = (
    "first_name",
    "last_name",
    "title",
    "company_domain",
    "email",
    "linkedin_url",
    "verified_at",
)


def _service() -> EmailVerificationService:
    return EmailVerificationService()


async def _enqueue_email_verification_batch(batch_id: UUID) -> None:
    from app.jobs.validation import run_email_verification_batch

    await run_email_verification_batch.defer_async(batch_id=str(batch_id))


def _http_error(exc: EmailVerificationServiceError) -> HTTPException:
    status_by_code = {
        "campaign_not_found": status.HTTP_404_NOT_FOUND,
        "batch_not_found": status.HTTP_404_NOT_FOUND,
        "no_eligible_contacts": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "zerobounce_api_key_missing": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "zerobounce_auth_failed": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "zerobounce_failed": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "zerobounce_rate_limited": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    return HTTPException(
        status_code=status_by_code.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


@router.get("/contacts", response_model=EmailVerificationContactList)
def list_email_verification_contacts(
    campaign_id: UUID = Query(...),
    status: str = Query(default="all"),
    search: str | None = Query(default=None),
    letter: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> EmailVerificationContactList:
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
        contacts = _service().list_contacts(
            session=session,
            campaign_id=campaign_id,
            status=status,
            search=search,
            letter=letter,
            limit=limit,
            offset=offset,
        )
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc
    return EmailVerificationContactList.model_validate(contacts, from_attributes=True)


@router.get("/contact-ids", response_model=EmailVerificationContactIds)
def list_email_verification_contact_ids(
    campaign_id: UUID = Query(...),
    status: str = Query(default="all"),
    search: str | None = Query(default=None),
    letter: str | None = Query(default=None),
    actionable_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> EmailVerificationContactIds:
    if not isinstance(status, str):
        status = "all"
    if not isinstance(search, str):
        search = None
    if not isinstance(letter, str):
        letter = None
    if not isinstance(actionable_only, bool):
        actionable_only = False
    if not isinstance(limit, int):
        limit = 200
    if not isinstance(offset, int):
        offset = 0
    try:
        ids = _service().list_contact_ids(
            session=session,
            campaign_id=campaign_id,
            status=status,
            search=search,
            letter=letter,
            actionable_only=actionable_only,
            limit=limit,
            offset=offset,
        )
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc
    return EmailVerificationContactIds.model_validate(ids, from_attributes=True)


@router.get("/letter-counts", response_model=LetterCountsResponse)
def get_email_verification_letter_counts(
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
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc
    return LetterCountsResponse(counts=counts)


@router.get("/exports/valid.csv")
def export_valid_email_verification_contacts(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> Response:
    try:
        rows = _service().list_fresh_valid_email_exports(
            session=session,
            campaign_id=campaign_id,
        )
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(VALID_EMAIL_EXPORT_COLUMNS))
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _csv_value(row.get(column)) for column in VALID_EMAIL_EXPORT_COLUMNS})

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="valid-emails-{campaign_id}.csv"'
            ),
        },
    )


@router.post("/preview", response_model=EmailVerificationPreviewRead)
def preview_email_verification(
    body: EmailVerificationPreviewRequest,
    session: Session = Depends(get_session),
) -> EmailVerificationPreviewRead:
    try:
        preview = _service().preview(
            session=session,
            campaign_id=body.campaign_id,
            contact_ids=body.contact_ids,
        )
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc
    return EmailVerificationPreviewRead.model_validate(preview, from_attributes=True)


@router.post(
    "/batches",
    response_model=EmailVerificationBatchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_email_verification_batch(
    body: EmailVerificationBatchCreate,
    session: Session = Depends(get_session),
) -> EmailVerificationBatchRead:
    try:
        batch = _service().create_batch(
            session=session,
            campaign_id=body.campaign_id,
            contact_ids=body.contact_ids,
        )
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc
    await _enqueue_email_verification_batch(batch.id)
    return EmailVerificationBatchRead.model_validate(
        _service().get_batch(session=session, batch_id=batch.id),
        from_attributes=True,
    )


@router.get("/batches/active", response_model=EmailVerificationBatchRead | None)
def get_active_email_verification_batch(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> EmailVerificationBatchRead | None:
    try:
        batch = _service().get_active_batch(session=session, campaign_id=campaign_id)
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc
    if batch is None:
        return None
    return EmailVerificationBatchRead.model_validate(batch, from_attributes=True)


@router.get("/batches/{batch_id}", response_model=EmailVerificationBatchRead)
def get_email_verification_batch(
    batch_id: UUID,
    session: Session = Depends(get_session),
) -> EmailVerificationBatchRead:
    try:
        batch = _service().get_batch(session=session, batch_id=batch_id)
    except EmailVerificationServiceError as exc:
        raise _http_error(exc) from exc
    return EmailVerificationBatchRead.model_validate(batch, from_attributes=True)
