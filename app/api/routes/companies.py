from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.api.schemas.analysis import FeedbackRead, FeedbackUpsert
from app.api.schemas.upload import (
    CompanyDeleteQueued,
    CompanyDeleteRequest,
    CompanyList,
    CompanyListItem,
)
from app.db.session import get_session
from app.models import Company, CompanyFeedback, Upload
from app.models.pipeline import utcnow
from app.services.company_service import (
    CompanyFilters,
    build_company_count_stmt,
    build_company_list_stmt,
    validate_campaign_upload_scope,
    validate_company_filters,
)
from app.services.pipeline_service import recompute_company_stages

router = APIRouter(prefix="/v1", tags=["companies"])


@router.get("/companies", response_model=CompanyList)
def list_companies(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision_filter: str = Query(default="all"),
    scrape_filter: str = Query(default="all"),
    include_total: bool = Query(default=False),
    letter: str | None = Query(default=None, min_length=1, max_length=1),
    letters: str | None = Query(default=None),
    stage_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    search: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="last_activity"),
    sort_dir: str = Query(default="desc"),
    upload_id: UUID | None = Query(default=None),
) -> CompanyList:
    filters: CompanyFilters = validate_company_filters(
        decision_filter=decision_filter,
        scrape_filter=scrape_filter,
        stage_filter=stage_filter,
        status_filter=status_filter,
        search=search,
        letter=letter,
        letters=letters,
        sort_by=sort_by,
        sort_dir=sort_dir,
        upload_id=upload_id,
        include_total=include_total,
    )
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    stmt = build_company_list_stmt(campaign_id, filters)
    rows = list(session.exec(stmt.offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    total: int | None = None
    if include_total:
        total = session.exec(build_company_count_stmt(campaign_id, filters)).one()

    items = [
        CompanyListItem(
            id=row[0], upload_id=row[1], upload_filename=row[2],
            raw_url=row[3], normalized_url=row[4], domain=row[5],
            pipeline_stage=str(row[6]), created_at=row[7],
            latest_decision=str(row[8]).lower() if row[8] is not None else None,
            latest_confidence=row[9],
            latest_scrape_job_id=row[10],
            latest_scrape_status=str(row[11]) if row[11] is not None else None,
            latest_scrape_terminal=row[12],
            latest_analysis_pipeline_run_id=row[13],
            latest_analysis_status=str(row[14]) if row[14] is not None else None,
            latest_analysis_terminal=row[15],
            latest_analysis_job_id=row[16],
            feedback_thumbs=str(row[17]) if row[17] is not None else None,
            feedback_comment=str(row[18]) if row[18] is not None else None,
            feedback_manual_label=str(row[19]) if row[19] is not None else None,
            latest_scrape_error_code=str(row[20]) if row[20] is not None else None,
            contact_count=int(row[21]) if row[21] is not None else 0,
            revealed_contact_count=int(row[21]) if row[21] is not None else 0,
            discovered_contact_count=int(row[21]) if row[21] is not None else 0,
            discovered_title_matched_count=int(row[22]) if row[22] is not None else 0,
            contact_fetch_status=str(row[23]) if row[23] is not None else None,
            last_activity=row[24],
        )
        for row in page_rows
    ]
    return CompanyList(total=total, has_more=has_more, limit=limit, offset=offset, items=items)


@router.put("/companies/{company_id}/feedback", response_model=FeedbackRead)
def upsert_company_feedback(
    company_id: UUID,
    payload: FeedbackUpsert,
    session: Session = Depends(get_session),
) -> FeedbackRead:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    feedback = session.get(CompanyFeedback, company_id)
    now = utcnow()
    if feedback is None:
        feedback = CompanyFeedback(
            company_id=company_id,
            thumbs=payload.thumbs,
            comment=payload.comment,
            manual_label=payload.manual_label,
            created_at=now,
            updated_at=now,
        )
        session.add(feedback)
    else:
        feedback.thumbs = payload.thumbs
        feedback.comment = payload.comment
        feedback.manual_label = payload.manual_label
        feedback.updated_at = now
        session.add(feedback)

    recompute_company_stages(session, company_ids=[company_id])
    session.commit()
    session.refresh(feedback)
    return FeedbackRead(
        thumbs=feedback.thumbs,
        comment=feedback.comment,
        manual_label=feedback.manual_label,
        updated_at=feedback.updated_at,
    )


@router.delete("/companies", response_model=CompanyDeleteQueued)
def delete_companies(
    payload: CompanyDeleteRequest,
    session: Session = Depends(get_session),
) -> CompanyDeleteQueued:
    from app.tasks.company import cascade_delete_companies as delete_task

    company_ids = list(dict.fromkeys(payload.company_ids))
    queued_ids = list(
        session.exec(
            select(Company.id)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == payload.campaign_id,
                col(Company.id).in_(company_ids),
            )
        )
    )
    if not queued_ids:
        raise HTTPException(status_code=404, detail="No matching companies found in this campaign.")

    delete_task.delay(
        company_ids=[str(cid) for cid in queued_ids],
        campaign_id=str(payload.campaign_id),
    )
    return CompanyDeleteQueued(queued_count=len(queued_ids), queued_ids=queued_ids)
