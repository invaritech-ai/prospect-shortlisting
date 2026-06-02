from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func
from sqlmodel import col, select

from app.models.classification import ClassificationResult
from app.models.core import UploadedDomain


def materialized_cte(query, name: str):
    return query.cte(name).prefix_with("MATERIALIZED", dialect="postgresql")


def latest_classification_timestamp_subquery(campaign_id: UUID):
    return materialized_cte(
        select(
            col(ClassificationResult.domain_id).label("domain_id"),
            func.max(col(ClassificationResult.created_at)).label("latest_created_at"),
        )
        .where(col(ClassificationResult.campaign_id) == campaign_id)
        .group_by(col(ClassificationResult.domain_id)),
        "latest_classification",
    )


def effective_classification_label_expr():
    return func.lower(
        func.coalesce(
            col(ClassificationResult.manual_label),
            col(ClassificationResult.predicted_label),
        )
    )


def effective_classification_rows_query(campaign_id: UUID):
    latest_ts_sq = latest_classification_timestamp_subquery(campaign_id)
    effective_label = effective_classification_label_expr()
    return (
        select(
            col(UploadedDomain.id).label("domain_id"),
            col(ClassificationResult.state).label("classification_state"),
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


def effective_possible_domain_ids_query(campaign_id: UUID):
    latest_ts_sq = latest_classification_timestamp_subquery(campaign_id)
    effective_label = effective_classification_label_expr()
    return (
        select(col(UploadedDomain.id).label("domain_id"))
        .join(latest_ts_sq, col(UploadedDomain.id) == latest_ts_sq.c.domain_id)
        .join(
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
            effective_label == "possible",
        )
    )
