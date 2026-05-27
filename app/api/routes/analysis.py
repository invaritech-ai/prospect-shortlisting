from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlmodel import Session, col, select

from app.api.schemas.scrape import LetterCountsResponse
from app.api.schemas.analysis import (
    AiReviewDomainAnalysis,
    AiReviewDomainList,
    AiReviewDomainRow,
    AiReviewLabelCounts,
)
from app.db.session import get_session
from app.models.classification import ClassificationResult
from app.models.core import UploadedDomain

router = APIRouter(prefix="/v1", tags=["analysis"])


def _apply_letter_filter(q, letter: str | None):
    if not letter or letter == "all":
        return q
    if letter == "#":
        return q.where(
            ~func.upper(func.left(col(UploadedDomain.domain), 1)).between("A", "Z")
        )
    return q.where(
        func.upper(func.left(col(UploadedDomain.domain), 1)) == letter.upper()
    )


def _apply_search_filter(q, search: str | None):
    if search and search.strip():
        return q.where(col(UploadedDomain.domain).ilike(f"%{search.strip()}%"))
    return q


def _latest_classification_ts_sq(campaign_id: UUID):
    return (
        select(
            col(ClassificationResult.domain_id).label("domain_id"),
            func.max(col(ClassificationResult.created_at)).label("latest_created_at"),
        )
        .where(col(ClassificationResult.campaign_id) == campaign_id)
        .group_by(col(ClassificationResult.domain_id))
        .subquery()
    )


def _classification_joined_query(campaign_id: UUID):
    latest_ts_sq = _latest_classification_ts_sq(campaign_id)
    effective_label = func.lower(
        func.coalesce(
            col(ClassificationResult.manual_label),
            col(ClassificationResult.predicted_label),
        )
    )
    q = (
        select(
            UploadedDomain,
            col(ClassificationResult.id),
            col(ClassificationResult.state),
            col(ClassificationResult.predicted_label),
            col(ClassificationResult.confidence),
            col(ClassificationResult.reasoning_json),
            col(ClassificationResult.evidence_json),
            col(ClassificationResult.manual_label),
            col(ClassificationResult.manual_thumbs),
            col(ClassificationResult.manual_comment),
            col(ClassificationResult.manually_reviewed_at),
            col(ClassificationResult.created_at),
            effective_label.label("effective_label"),
        )
        .outerjoin(latest_ts_sq, col(UploadedDomain.id) == latest_ts_sq.c.domain_id)
        .outerjoin(
            ClassificationResult,
            and_(
                col(ClassificationResult.campaign_id) == campaign_id,
                col(ClassificationResult.domain_id) == col(UploadedDomain.id),
                col(ClassificationResult.created_at) == latest_ts_sq.c.latest_created_at,
            ),
        )
        .where(
            col(UploadedDomain.campaign_id) == campaign_id,
            col(UploadedDomain.scrape_status) == "succeeded",
        )
    )
    return q, effective_label


def _apply_label_filter(q, effective_label, label: str | None):
    normalized = (label or "all").strip().lower()
    if normalized in ("", "all"):
        return q
    if normalized == "unclassified":
        return q.where(col(ClassificationResult.predicted_label).is_(None))
    if normalized == "unknown":
        return q.where(effective_label == "unknown")
    if normalized in ("possible", "crap"):
        return q.where(effective_label == normalized)
    return q


def _ai_review_domain_row_from_result(row) -> AiReviewDomainRow:
    (
        domain,
        classification_result_id,
        classification_state,
        predicted_label,
        confidence,
        reasoning_json,
        evidence_json,
        manual_label,
        manual_thumbs,
        manual_comment,
        manually_reviewed_at,
        classification_created_at,
        _effective_label,
    ) = row
    effective_label = manual_label or predicted_label
    activity_at = manually_reviewed_at or classification_created_at or domain.created_at
    return AiReviewDomainRow(
        domain_id=domain.id,
        campaign_id=domain.campaign_id,
        domain=domain.domain,
        raw_url=domain.raw_url,
        normalized_url=domain.normalized_url,
        classification_result_id=classification_result_id,
        classification_state=classification_state,
        predicted_label=predicted_label,
        confidence=confidence,
        reasoning_json=reasoning_json,
        evidence_json=evidence_json,
        manual_label=manual_label,
        manual_thumbs=manual_thumbs,
        manual_comment=manual_comment,
        manually_reviewed_at=manually_reviewed_at,
        effective_label=effective_label,
        effective_confidence=confidence,
        activity_at=activity_at,
    )


@router.get("/ai-review/letter-counts", response_model=LetterCountsResponse)
def get_ai_review_letter_counts(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> LetterCountsResponse:
    letter_expr = func.upper(func.substring(col(UploadedDomain.domain), 1, 1))
    rows = session.exec(
        select(letter_expr, func.count(UploadedDomain.id))
        .where(
            col(UploadedDomain.campaign_id) == campaign_id,
            col(UploadedDomain.scrape_status) == "succeeded",
        )
        .group_by(letter_expr)
    ).all()

    counts: dict[str, int] = {}
    for first_char, count in rows:
        if first_char and first_char.isalpha():
            counts[first_char] = count
        else:
            counts["#"] = counts.get("#", 0) + count
    return LetterCountsResponse(counts=counts)


@router.get("/ai-review/label-counts", response_model=AiReviewLabelCounts)
def get_ai_review_label_counts(
    campaign_id: UUID = Query(...),
    letter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> AiReviewLabelCounts:
    q, effective_label = _classification_joined_query(campaign_id)
    q = _apply_letter_filter(q, letter)
    q = _apply_search_filter(q, search)

    label_sq = q.subquery()
    rows = session.exec(
        select(label_sq.c.effective_label, func.count())
        .select_from(label_sq)
        .group_by(label_sq.c.effective_label)
    ).all()

    counts = {"unclassified": 0, "possible": 0, "unknown": 0, "crap": 0}
    total = 0
    for label, count in rows:
        bucket = (label or "unclassified").lower()
        if bucket not in counts:
            bucket = "unclassified"
        counts[bucket] += count
        total += count

    return AiReviewLabelCounts(
        all=total,
        unclassified=counts["unclassified"],
        possible=counts["possible"],
        unknown=counts["unknown"],
        crap=counts["crap"],
    )


@router.get("/ai-review/domains/{domain_id}/analysis", response_model=AiReviewDomainAnalysis)
def get_ai_review_domain_analysis(
    domain_id: UUID,
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> AiReviewDomainAnalysis:
    q, _effective_label_expr = _classification_joined_query(campaign_id)
    q = q.where(col(UploadedDomain.id) == domain_id)

    row = session.exec(q).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Domain not found in campaign.")

    data = _ai_review_domain_row_from_result(row).model_dump()
    return AiReviewDomainAnalysis(**data)


@router.get("/ai-review/domains", response_model=AiReviewDomainList)
def list_ai_review_domains(
    campaign_id: UUID = Query(...),
    letter: str | None = Query(default=None),
    label: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> AiReviewDomainList:
    base_q, effective_label_expr = _classification_joined_query(campaign_id)
    base_q = _apply_letter_filter(base_q, letter)
    base_q = _apply_search_filter(base_q, search)
    base_q = _apply_label_filter(base_q, effective_label_expr, label)

    total = session.exec(select(func.count()).select_from(base_q.subquery())).one()
    rows = session.exec(
        base_q.order_by(col(UploadedDomain.domain).asc()).limit(limit).offset(offset)
    ).all()

    items = [_ai_review_domain_row_from_result(row) for row in rows]

    return AiReviewDomainList(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )
