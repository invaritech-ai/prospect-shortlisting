from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, update
from sqlmodel import Session, col, select

from app.api.schemas.campaign import (
    CampaignAssignUploadsRequest,
    CampaignCreate,
    CampaignList,
    CampaignRead,
    CampaignUpdate,
)
from app.db.session import get_session
from app.models import Campaign, Company, Upload
from app.models.pipeline import utcnow

router = APIRouter(prefix="/v1", tags=["campaigns"])


def _as_campaign_read(
    *,
    campaign: Campaign,
    upload_count: int = 0,
    company_count: int = 0,
) -> CampaignRead:
    return CampaignRead(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        upload_count=upload_count,
        company_count=company_count,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def _get_campaign_counts(session: Session, campaign_id: UUID) -> tuple[int, int]:
    upload_count = session.exec(
        select(func.count()).select_from(Upload).where(col(Upload.campaign_id) == campaign_id)
    ).one()
    company_count = session.exec(
        select(func.count())
        .select_from(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(col(Upload.campaign_id) == campaign_id)
    ).one()
    return int(upload_count), int(company_count)


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
    upload_counts = (
        select(
            Upload.campaign_id.label("campaign_id"),
            func.count().label("upload_count"),
        )
        .where(col(Upload.campaign_id).is_not(None))
        .group_by(col(Upload.campaign_id))
        .subquery()
    )
    company_counts = (
        select(
            Upload.campaign_id.label("campaign_id"),
            func.count(Company.id).label("company_count"),
        )
        .join(Company, col(Company.upload_id) == col(Upload.id))
        .where(col(Upload.campaign_id).is_not(None))
        .group_by(col(Upload.campaign_id))
        .subquery()
    )

    statement = (
        select(
            Campaign,
            func.coalesce(upload_counts.c.upload_count, 0).label("upload_count"),
            func.coalesce(company_counts.c.company_count, 0).label("company_count"),
        )
        .outerjoin(upload_counts, upload_counts.c.campaign_id == col(Campaign.id))
        .outerjoin(company_counts, company_counts.c.campaign_id == col(Campaign.id))
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
            _as_campaign_read(campaign=campaign, upload_count=int(upload_count), company_count=int(company_count))
            for campaign, upload_count, company_count in page_rows
        ],
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignRead)
def get_campaign(campaign_id: UUID, session: Session = Depends(get_session)) -> CampaignRead:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    upload_count, company_count = _get_campaign_counts(session, campaign_id)
    return _as_campaign_read(campaign=campaign, upload_count=upload_count, company_count=company_count)


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
    return _as_campaign_read(campaign=campaign)


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: UUID, session: Session = Depends(get_session)) -> None:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    session.execute(update(Upload).where(col(Upload.campaign_id) == campaign_id).values(campaign_id=None))
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
    session.execute(
        update(Upload).where(col(Upload.id).in_(upload_ids)).values(campaign_id=campaign_id)
    )
    campaign.updated_at = utcnow()
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    upload_count, company_count = _get_campaign_counts(session, campaign_id)
    return _as_campaign_read(campaign=campaign, upload_count=upload_count, company_count=company_count)


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
    session.execute(
        update(Upload).where(col(Upload.id).in_(upload_ids)).values(campaign_id=None)
    )
    campaign.updated_at = utcnow()
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    upload_count, company_count = _get_campaign_counts(session, campaign_id)
    return _as_campaign_read(campaign=campaign, upload_count=upload_count, company_count=company_count)
