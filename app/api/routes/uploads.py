"""Upload CRUD: create upload, list uploads, get upload, list companies in upload."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import case, func
from sqlmodel import Session, col, select

from app.api.schemas.upload import (
    CompanyRead,
    UploadCompanyList,
    UploadCreateResult,
    UploadDetail,
    UploadList,
    UploadRead,
    UploadValidationError,
)
from app.db.session import get_session
from app.models import Campaign, Company, Upload
from app.services.upload_service import UploadIssue, UploadService


router = APIRouter(prefix="/v1", tags=["uploads"])
upload_service = UploadService()


def _as_upload_read(upload: Upload) -> UploadRead:
    return UploadRead.model_validate(upload, from_attributes=True)


def _as_issues(items: list[UploadIssue]) -> list[UploadValidationError]:
    return [
        UploadValidationError(
            row_number=item.row_number,
            raw_value=item.raw_value,
            error_code=item.error_code,
            error_message=item.error_message,
        )
        for item in items
    ]


def _issues_from_upload(upload: Upload) -> list[UploadValidationError]:
    items: list[UploadValidationError] = []
    for raw in upload.validation_errors_json or []:
        try:
            row_number = int(raw.get("row_number", 0))
            if row_number < 1:
                continue
            items.append(
                UploadValidationError(
                    row_number=row_number,
                    raw_value=str(raw.get("raw_value", "") or ""),
                    error_code=str(raw.get("error_code", "") or ""),
                    error_message=str(raw.get("error_message", "") or ""),
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return items


@router.post("/uploads", response_model=UploadCreateResult, status_code=status.HTTP_201_CREATED)
async def create_upload(
    file: UploadFile = File(...),
    campaign_id: UUID | None = Form(default=None),
    session: Session = Depends(get_session),
) -> UploadCreateResult:
    try:
        if campaign_id is not None and session.get(Campaign, campaign_id) is None:
            raise ValueError("Campaign not found.")
        raw_bytes = await file.read()
        upload, issues = upload_service.create_upload_from_file(
            session=session,
            filename=file.filename or "upload",
            raw_bytes=raw_bytes,
            campaign_id=campaign_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadCreateResult(upload=_as_upload_read(upload), validation_errors=_as_issues(issues))


@router.get("/uploads", response_model=UploadList)
def list_uploads(
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UploadList:
    items = list(
        session.exec(
            select(Upload)
            .order_by(col(Upload.created_at).desc())
            .offset(offset)
            .limit(limit)
        )
    )
    total = session.exec(select(func.count()).select_from(Upload)).one()
    return UploadList(
        total=total,
        limit=limit,
        offset=offset,
        items=[_as_upload_read(item) for item in items],
    )


@router.get("/uploads/{upload_id}", response_model=UploadDetail)
def get_upload(upload_id: UUID, session: Session = Depends(get_session)) -> UploadDetail:
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return UploadDetail(upload=_as_upload_read(upload), validation_errors=_issues_from_upload(upload))


@router.get("/uploads/{upload_id}/companies", response_model=UploadCompanyList)
def list_upload_companies(
    upload_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UploadCompanyList:
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")

    items = list(
        session.exec(
            select(Company)
            .where(col(Company.upload_id) == upload_id)
            .order_by(
                case((col(Company.source_row_number).is_(None), 1), else_=0).asc(),
                col(Company.source_row_number).asc(),
                col(Company.created_at).asc(),
                col(Company.domain).asc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )
    return UploadCompanyList(
        upload_id=upload_id,
        total=upload.valid_count,
        limit=limit,
        offset=offset,
        items=[CompanyRead.model_validate(item, from_attributes=True) for item in items],
    )
