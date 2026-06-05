from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, update
from sqlmodel import Session, col, select

from app.api.schemas.campaign import (
    CampaignAssignUploadsRequest,
    CampaignCreate,
    CampaignList,
    CampaignRead,
    CampaignStageCounts,
    CampaignUpdate,
)
from app.api.schemas.pipeline_run import PipelineCostSummaryRead
from app.db.session import get_session
from app.models.classification import ClassificationResult
from app.models.contacts import Contact
from app.models.core import Campaign, Upload, UploadedDomain
from app.models.base import utcnow
from app.services.campaign_stage_counts import build_campaign_stage_counts
from app.services.email_verification_service import VERIFICATION_STALE_AFTER_DAYS

router = APIRouter(prefix="/v1", tags=["campaigns"])


def _domain_stats_subquery():
    """Single subquery: all per-campaign domain counts in one GROUP BY pass."""
    return (
        select(
            col(UploadedDomain.campaign_id).label("campaign_id"),
            func.count().label("company_count"),
            func.count(col(UploadedDomain.scrape_status)).label("scrape_count"),
            func.count(col(UploadedDomain.fetch_status)).label("contact_count"),
        )
        .where(col(UploadedDomain.campaign_id).is_not(None))
        .group_by(col(UploadedDomain.campaign_id))
        .subquery()
    )


def _classification_stats_subquery():
    latest_ts_sq = (
        select(
            col(ClassificationResult.campaign_id).label("campaign_id"),
            col(ClassificationResult.domain_id).label("domain_id"),
            func.max(col(ClassificationResult.created_at)).label("latest_created_at"),
        )
        .group_by(col(ClassificationResult.campaign_id), col(ClassificationResult.domain_id))
        .subquery()
    )
    effective_label = func.lower(
        func.coalesce(
            col(ClassificationResult.manual_label),
            col(ClassificationResult.predicted_label),
        )
    )
    return (
        select(
            col(UploadedDomain.campaign_id).label("campaign_id"),
            func.coalesce(
                func.sum(case((effective_label.in_(["unknown", "crap"]), 1), else_=0)),
                0,
            ).label("classified_count"),
            func.coalesce(
                func.sum(case((effective_label == "possible", 1), else_=0)),
                0,
            ).label("possible_count"),
        )
        .outerjoin(
            latest_ts_sq,
            and_(
                col(UploadedDomain.campaign_id) == latest_ts_sq.c.campaign_id,
                col(UploadedDomain.id) == latest_ts_sq.c.domain_id,
            ),
        )
        .outerjoin(
            ClassificationResult,
            and_(
                col(ClassificationResult.campaign_id) == latest_ts_sq.c.campaign_id,
                col(ClassificationResult.domain_id) == latest_ts_sq.c.domain_id,
                col(ClassificationResult.created_at) == latest_ts_sq.c.latest_created_at,
            ),
        )
        .where(
            col(UploadedDomain.campaign_id).is_not(None),
            col(UploadedDomain.scrape_status) == "succeeded",
        )
        .group_by(col(UploadedDomain.campaign_id))
        .subquery()
    )


def _valid_email_stats_subquery():
    cutoff = utcnow() - timedelta(days=VERIFICATION_STALE_AFTER_DAYS)
    selected_email = func.lower(func.trim(col(Contact.selected_email)))
    verified_snapshot = func.lower(func.trim(col(Contact.verified_email_snapshot)))
    verification_status = func.lower(func.trim(col(Contact.verification_status)))
    return (
        select(
            col(Contact.campaign_id).label("campaign_id"),
            func.count(col(Contact.id)).label("valid_email_count"),
        )
        .where(
            col(Contact.selected_email).is_not(None),
            func.trim(col(Contact.selected_email)) != "",
            col(Contact.verified_email_snapshot).is_not(None),
            selected_email == verified_snapshot,
            col(Contact.verification_applied).is_(True),
            verification_status.in_(["valid", "deliverable"]),
            col(Contact.verified_at).is_not(None),
            col(Contact.verified_at) >= cutoff,
        )
        .group_by(col(Contact.campaign_id))
        .subquery()
    )


def _as_campaign_read(
    *,
    campaign: Campaign,
    upload_count: int = 0,
    company_count: int = 0,
    scrape_count: int = 0,
    classified_count: int = 0,
    possible_count: int = 0,
    contact_count: int = 0,
    valid_email_count: int = 0,
) -> CampaignRead:
    return CampaignRead(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        upload_count=upload_count,
        company_count=company_count,
        scrape_count=scrape_count,
        classified_count=classified_count,
        possible_count=possible_count,
        contact_count=contact_count,
        valid_email_count=valid_email_count,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def _get_campaign_counts(session: Session, campaign_id: UUID) -> dict:
    upload_count = session.exec(
        select(func.count()).select_from(Upload).where(col(Upload.campaign_id) == campaign_id)
    ).one()
    sq = _domain_stats_subquery()
    classification_sq = _classification_stats_subquery()
    valid_sq = _valid_email_stats_subquery()
    row = session.execute(
        select(
            sq.c.company_count,
            sq.c.scrape_count,
            sq.c.contact_count,
            func.coalesce(classification_sq.c.classified_count, 0).label("classified_count"),
            func.coalesce(classification_sq.c.possible_count, 0).label("possible_count"),
            func.coalesce(valid_sq.c.valid_email_count, 0).label("valid_email_count"),
        )
        .select_from(sq)
        .outerjoin(classification_sq, classification_sq.c.campaign_id == sq.c.campaign_id)
        .outerjoin(valid_sq, valid_sq.c.campaign_id == sq.c.campaign_id)
        .where(sq.c.campaign_id == campaign_id)
    ).first()
    if row:
        return dict(
            upload_count=int(upload_count),
            company_count=int(row.company_count),
            scrape_count=int(row.scrape_count),
            classified_count=int(row.classified_count),
            possible_count=int(row.possible_count or 0),
            contact_count=int(row.contact_count),
            valid_email_count=int(row.valid_email_count or 0),
        )
    return dict(upload_count=int(upload_count), company_count=0, scrape_count=0,
                classified_count=0, possible_count=0, contact_count=0, valid_email_count=0)


@router.post("/campaigns", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreate, session: Session = Depends(get_session)) -> CampaignRead:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Campaign name is required.")
    exists = session.exec(
        select(Campaign.id).where(func.lower(col(Campaign.name)) == name.lower()).limit(1)
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Campaign name already exists.")
    now = utcnow()
    campaign = Campaign(
        name=name,
        description=(payload.description or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return _as_campaign_read(campaign=campaign)


@router.get("/campaigns", response_model=CampaignList)
def list_campaigns(
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CampaignList:
    domain_stats = _domain_stats_subquery()
    classification_stats = _classification_stats_subquery()
    valid_email_stats = _valid_email_stats_subquery()
    upload_counts = (
        select(
            col(Upload.campaign_id).label("campaign_id"),
            func.count().label("upload_count"),
        )
        .where(col(Upload.campaign_id).is_not(None))
        .group_by(col(Upload.campaign_id))
        .subquery()
    )

    statement = (
        select(
            Campaign,
            func.coalesce(upload_counts.c.upload_count, 0).label("upload_count"),
            func.coalesce(domain_stats.c.company_count, 0).label("company_count"),
            func.coalesce(domain_stats.c.scrape_count, 0).label("scrape_count"),
            func.coalesce(classification_stats.c.classified_count, 0).label("classified_count"),
            func.coalesce(classification_stats.c.possible_count, 0).label("possible_count"),
            func.coalesce(domain_stats.c.contact_count, 0).label("contact_count"),
            func.coalesce(valid_email_stats.c.valid_email_count, 0).label("valid_email_count"),
        )
        .outerjoin(upload_counts, upload_counts.c.campaign_id == col(Campaign.id))
        .outerjoin(domain_stats, domain_stats.c.campaign_id == col(Campaign.id))
        .outerjoin(classification_stats, classification_stats.c.campaign_id == col(Campaign.id))
        .outerjoin(valid_email_stats, valid_email_stats.c.campaign_id == col(Campaign.id))
        .order_by(col(Campaign.updated_at).desc(), col(Campaign.created_at).desc())
    )
    rows = list(session.exec(statement.offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    total = session.exec(select(func.count()).select_from(Campaign)).one()
    return CampaignList(
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
        items=[
            _as_campaign_read(
                campaign=campaign,
                upload_count=int(upload_count),
                company_count=int(company_count),
                scrape_count=int(scrape_count),
                classified_count=int(classified_count),
                possible_count=int(possible_count or 0),
                contact_count=int(contact_count),
                valid_email_count=int(valid_email_count),
            )
            for campaign, upload_count, company_count, scrape_count, classified_count, possible_count, contact_count, valid_email_count in page_rows
        ],
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignRead)
def get_campaign(campaign_id: UUID, session: Session = Depends(get_session)) -> CampaignRead:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    counts = _get_campaign_counts(session, campaign_id)
    return _as_campaign_read(campaign=campaign, **counts)


@router.get("/campaigns/{campaign_id}/stage-counts", response_model=CampaignStageCounts)
def get_campaign_stage_counts(campaign_id: UUID, session: Session = Depends(get_session)) -> CampaignStageCounts:
    counts = build_campaign_stage_counts(session=session, campaign_id=campaign_id)
    if counts is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return counts


@router.get("/campaigns/{campaign_id}/costs", response_model=PipelineCostSummaryRead)
def get_campaign_costs(campaign_id: UUID, session: Session = Depends(get_session)) -> PipelineCostSummaryRead:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    # AI usage tracking not yet implemented in new schema
    return PipelineCostSummaryRead(campaign_id=campaign_id)


@router.patch("/campaigns/{campaign_id}", response_model=CampaignRead)
def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    session: Session = Depends(get_session),
) -> CampaignRead:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Campaign name cannot be empty.")
        exists = session.exec(
            select(Campaign.id)
            .where(func.lower(col(Campaign.name)) == name.lower(), col(Campaign.id) != campaign_id)
            .limit(1)
        ).first()
        if exists:
            raise HTTPException(status_code=409, detail="Campaign name already exists.")
        campaign.name = name
    if payload.description is not None:
        campaign.description = payload.description.strip() or None
    campaign.updated_at = utcnow()
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    counts = _get_campaign_counts(session, campaign_id)
    return _as_campaign_read(campaign=campaign, **counts)


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: UUID, session: Session = Depends(get_session)) -> None:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    session.execute(update(Upload).where(col(Upload.campaign_id) == campaign_id).values(campaign_id=None))
    session.execute(update(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id).values(campaign_id=None))
    session.delete(campaign)
    session.commit()


@router.post("/campaigns/{campaign_id}/assign-uploads", response_model=CampaignRead)
def assign_uploads_to_campaign(
    campaign_id: UUID,
    payload: CampaignAssignUploadsRequest,
    session: Session = Depends(get_session),
) -> CampaignRead:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    upload_ids = list(dict.fromkeys(payload.upload_ids))
    already_claimed = session.exec(
        select(func.count())
        .select_from(Upload)
        .where(
            col(Upload.id).in_(upload_ids),
            col(Upload.campaign_id).is_not(None),
            col(Upload.campaign_id) != campaign_id,
        )
    ).one()
    if already_claimed:
        raise HTTPException(status_code=409, detail="One or more uploads are already assigned to another campaign.")
    session.execute(update(Upload).where(col(Upload.id).in_(upload_ids)).values(campaign_id=campaign_id))
    campaign.updated_at = utcnow()
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    counts = _get_campaign_counts(session, campaign_id)
    return _as_campaign_read(campaign=campaign, **counts)


@router.post("/campaigns/{campaign_id}/unassign-uploads", response_model=CampaignRead)
def unassign_uploads_from_campaign(
    campaign_id: UUID,
    payload: CampaignAssignUploadsRequest,
    session: Session = Depends(get_session),
) -> CampaignRead:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    upload_ids = list(dict.fromkeys(payload.upload_ids))
    session.execute(update(Upload).where(col(Upload.id).in_(upload_ids)).values(campaign_id=None))
    campaign.updated_at = utcnow()
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    counts = _get_campaign_counts(session, campaign_id)
    return _as_campaign_read(campaign=campaign, **counts)
