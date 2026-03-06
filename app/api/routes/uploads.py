from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import case, func
from sqlmodel import Session, col, delete, select

from app.api.schemas.upload import (
    CompanyDeleteRequest,
    CompanyDeleteResult,
    CompanyList,
    CompanyListItem,
    CompanyRead,
    UploadCompanyList,
    UploadCreateResult,
    UploadDetail,
    UploadList,
    UploadRead,
    UploadValidationError,
)
from app.db.session import get_session
from app.models import (
    AnalysisJob,
    ClassificationResult,
    Company,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    Upload,
)
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
    session: Session = Depends(get_session),
) -> UploadCreateResult:
    try:
        raw_bytes = await file.read()
        upload, issues = upload_service.create_upload_from_file(
            session=session,
            filename=file.filename or "upload",
            raw_bytes=raw_bytes,
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
            .order_by(col(Company.created_at).asc(), col(Company.domain).asc())
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


@router.get("/companies", response_model=CompanyList)
def list_companies(
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision_filter: str = Query(default="all"),
) -> CompanyList:
    latest_decision = (
        select(ClassificationResult.predicted_label)
        .join(AnalysisJob, AnalysisJob.id == ClassificationResult.analysis_job_id)
        .where(AnalysisJob.company_id == Company.id)
        .order_by(ClassificationResult.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    latest_confidence = (
        select(ClassificationResult.confidence)
        .join(AnalysisJob, AnalysisJob.id == ClassificationResult.analysis_job_id)
        .where(AnalysisJob.company_id == Company.id)
        .order_by(ClassificationResult.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    decision_lower = func.lower(func.coalesce(latest_decision, ""))
    decision_rank = case(
        (decision_lower == "", 0),
        (decision_lower == "possible", 1),
        (decision_lower == "unknown", 2),
        (decision_lower == "crap", 3),
        else_=4,
    )
    normalized_filter = decision_filter.strip().lower()
    allowed_filters = {"all", "unlabeled", "possible", "unknown", "crap"}
    if normalized_filter not in allowed_filters:
        raise HTTPException(status_code=422, detail="Invalid decision_filter.")
    statement = (
        select(
            Company.id,
            Company.upload_id,
            Upload.filename,
            Company.raw_url,
            Company.normalized_url,
            Company.domain,
            Company.created_at,
            latest_decision,
            latest_confidence,
        )
        .join(Upload, Upload.id == Company.upload_id)
    )
    if normalized_filter == "unlabeled":
        statement = statement.where(decision_lower == "")
    elif normalized_filter in {"possible", "unknown", "crap"}:
        statement = statement.where(decision_lower == normalized_filter)

    rows = list(
        session.exec(
            statement.order_by(
                decision_rank.asc(),
                col(Company.created_at).desc(),
                col(Company.domain).asc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )

    total_stmt = select(func.count()).select_from(Company)
    if normalized_filter == "unlabeled":
        total_stmt = total_stmt.where(decision_lower == "")
    elif normalized_filter in {"possible", "unknown", "crap"}:
        total_stmt = total_stmt.where(decision_lower == normalized_filter)
    total = session.exec(total_stmt).one()
    items = [
        CompanyListItem(
            id=row[0],
            upload_id=row[1],
            upload_filename=row[2],
            raw_url=row[3],
            normalized_url=row[4],
            domain=row[5],
            created_at=row[6],
            latest_decision=str(row[7]) if row[7] is not None else None,
            latest_confidence=row[8],
        )
        for row in rows
    ]
    return CompanyList(total=total, limit=limit, offset=offset, items=items)


@router.post("/companies/delete", response_model=CompanyDeleteResult)
def delete_companies(
    payload: CompanyDeleteRequest,
    session: Session = Depends(get_session),
) -> CompanyDeleteResult:
    requested_ids = list(dict.fromkeys(payload.company_ids))
    companies = list(
        session.exec(select(Company).where(col(Company.id).in_(requested_ids)))
    )
    found_ids = {company.id for company in companies}
    missing_ids = [company_id for company_id in requested_ids if company_id not in found_ids]

    if companies:
        company_ids = [company.id for company in companies]
        upload_delete_counts: dict[UUID, int] = {}
        for company in companies:
            upload_delete_counts[company.upload_id] = upload_delete_counts.get(company.upload_id, 0) + 1

        crawl_job_ids = list(
            session.exec(
                select(CrawlJob.id).where(col(CrawlJob.company_id).in_(company_ids))
            )
        )
        analysis_job_ids = list(
            session.exec(
                select(AnalysisJob.id).where(col(AnalysisJob.company_id).in_(company_ids))
            )
        )

        if analysis_job_ids:
            session.exec(
                delete(ClassificationResult).where(col(ClassificationResult.analysis_job_id).in_(analysis_job_ids))
            )
            session.exec(
                delete(JobEvent).where(
                    (col(JobEvent.job_type) == "analysis") & col(JobEvent.job_id).in_(analysis_job_ids)
                )
            )
            session.exec(
                delete(AnalysisJob).where(col(AnalysisJob.id).in_(analysis_job_ids))
            )

        if crawl_job_ids:
            session.exec(
                delete(JobEvent).where(
                    (col(JobEvent.job_type) == "crawl") & col(JobEvent.job_id).in_(crawl_job_ids)
                )
            )
            session.exec(
                delete(CrawlArtifact).where(col(CrawlArtifact.crawl_job_id).in_(crawl_job_ids))
            )
            session.exec(
                delete(CrawlJob).where(col(CrawlJob.id).in_(crawl_job_ids))
            )

        session.exec(delete(Company).where(col(Company.id).in_(company_ids)))

        uploads = list(
            session.exec(select(Upload).where(col(Upload.id).in_(list(upload_delete_counts.keys()))))
        )
        for upload in uploads:
            decrement = upload_delete_counts.get(upload.id, 0)
            upload.valid_count = max(upload.valid_count - decrement, 0)
            session.add(upload)

        session.commit()

    deleted_ids = [company_id for company_id in requested_ids if company_id in found_ids]
    return CompanyDeleteResult(
        requested_count=len(requested_ids),
        deleted_count=len(deleted_ids),
        deleted_ids=deleted_ids,
        missing_ids=missing_ids,
    )
