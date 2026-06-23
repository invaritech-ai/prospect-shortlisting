from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, update
from sqlmodel import Session, col, select

from app.api.schemas.upload import UploadCreateResult, UploadList, UploadRead
from app.db.session import get_session
from app.models.core import Campaign, Upload, UploadedDomain
from app.services.upload_service import UploadService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["uploads"])
upload_service = UploadService()


@router.post("/uploads", response_model=UploadCreateResult, status_code=status.HTTP_201_CREATED)
async def create_upload(
    campaign_id: UUID = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> UploadCreateResult:
    """Parse a CSV/XLSX of company URLs and bulk-insert into the campaign."""
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    content = await file.read()
    filename = file.filename or "upload"
    try:
        upload, issues, already_in_campaign_count = upload_service.create_upload_from_file(
            session=session,
            filename=filename,
            raw_bytes=content,
            campaign_id=campaign_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    dupe_count = len(issues) + already_in_campaign_count
    return UploadCreateResult(
        upload=UploadRead.model_validate(upload),
        new_count=max(upload.row_count - dupe_count, 0),
        dupe_count=dupe_count,
    )


@router.get("/uploads", response_model=UploadList)
def list_uploads(
    campaign_id: UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> UploadList:
    base_q = select(Upload).where(col(Upload.campaign_id) == campaign_id)
    total = session.exec(select(func.count()).select_from(base_q.subquery())).one()
    items = session.exec(
        base_q.order_by(col(Upload.created_at).desc()).limit(limit).offset(offset)
    ).all()
    return UploadList(
        total=total,
        limit=limit,
        offset=offset,
        items=[UploadRead.model_validate(u, from_attributes=True) for u in items],
    )


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(
    upload_id: UUID,
    session: Session = Depends(get_session),
) -> None:
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    # Preserve domains in the campaign — just sever the upload link
    session.execute(
        update(UploadedDomain)
        .where(col(UploadedDomain.upload_id) == upload_id)
        .values(upload_id=None)
    )
    session.delete(upload)
    session.commit()
