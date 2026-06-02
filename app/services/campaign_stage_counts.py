from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func
from sqlmodel import Session, col, select

from app.api.schemas.campaign import (
    AiReviewStageCounts,
    CampaignStageCounts,
    ContactsStageCounts,
    ScrapingStageCounts,
    ValidationStageCounts,
)
from app.models.contacts import Contact, FetchedPerson
from app.models.core import Campaign, UploadedDomain
from app.models.base import utcnow
from app.models.scrape import ScrapeResult
from app.services.classification_scope import (
    effective_classification_rows_query,
    effective_possible_domain_ids_query,
    materialized_cte,
)


def build_campaign_stage_counts(*, session: Session, campaign_id: UUID) -> CampaignStageCounts | None:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        return None
    return CampaignStageCounts(
        campaign_id=campaign_id,
        updated_at=utcnow(),
        scraping=_scraping_counts(session=session, campaign_id=campaign_id),
        ai_review=_ai_review_counts(session=session, campaign_id=campaign_id),
        contacts=_contact_counts(session=session, campaign_id=campaign_id),
        validation=_validation_counts(session=session, campaign_id=campaign_id),
    )


def _scraping_counts(*, session: Session, campaign_id: UUID) -> ScrapingStageCounts:
    status_rows = session.exec(
        select(col(UploadedDomain.scrape_status), func.count(col(UploadedDomain.id)))
        .where(col(UploadedDomain.campaign_id) == campaign_id)
        .group_by(col(UploadedDomain.scrape_status))
    ).all()
    by_status = {status: int(count or 0) for status, count in status_rows}
    pending = by_status.get(None, 0)
    queued = by_status.get("queued", 0)
    running = by_status.get("running", 0)
    succeeded = by_status.get("succeeded", 0)
    failed = by_status.get("failed", 0)
    retryable_failed = _retryable_failed_count(session=session, campaign_id=campaign_id)
    badge = pending + queued + running + retryable_failed
    return ScrapingStageCounts(
        badge=badge,
        total=sum(by_status.values()),
        pending=pending,
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        retryable_failed=retryable_failed,
        is_live=queued > 0 or running > 0,
    )


def _retryable_failed_count(*, session: Session, campaign_id: UUID) -> int:
    latest_retryable_sq = (
        select(
            col(ScrapeResult.retryable),
        )
        .where(
            col(ScrapeResult.campaign_id) == campaign_id,
            col(ScrapeResult.domain_id) == col(UploadedDomain.id),
        )
        .order_by(col(ScrapeResult.updated_at).desc())
        .limit(1)
        .scalar_subquery()
    )
    return int(
        session.exec(
            select(func.count(col(UploadedDomain.id)))
            .where(
                col(UploadedDomain.campaign_id) == campaign_id,
                col(UploadedDomain.scrape_status) == "failed",
                latest_retryable_sq.is_(True),
            )
        ).one()
        or 0
    )


def _ai_review_counts(*, session: Session, campaign_id: UUID) -> AiReviewStageCounts:
    label_sq = effective_classification_rows_query(campaign_id).subquery()
    label_rows = session.exec(
        select(label_sq.c.effective_label, func.count()).select_from(label_sq).group_by(label_sq.c.effective_label)
    ).all()
    counts = {"unclassified": 0, "possible": 0, "unknown": 0, "crap": 0}
    total = 0
    for label, count in label_rows:
        bucket = (label or "unclassified").lower()
        if bucket not in counts:
            bucket = "unclassified"
        counts[bucket] += int(count or 0)
        total += int(count or 0)

    state_rows = session.exec(
        select(label_sq.c.classification_state, func.count())
        .select_from(label_sq)
        .where(label_sq.c.classification_state.in_(["queued", "running"]))
        .group_by(label_sq.c.classification_state)
    ).all()
    by_state = {state: int(count or 0) for state, count in state_rows}
    queued = by_state.get("queued", 0)
    running = by_state.get("running", 0)
    return AiReviewStageCounts(
        badge=counts["unclassified"],
        all=total,
        unclassified=counts["unclassified"],
        possible=counts["possible"],
        unknown=counts["unknown"],
        crap=counts["crap"],
        queued=queued,
        running=running,
        is_live=queued > 0 or running > 0,
    )


def _contact_counts(*, session: Session, campaign_id: UUID) -> ContactsStageCounts:
    possible_ids_sq = materialized_cte(
        effective_possible_domain_ids_query(campaign_id),
        "possible_contact_stage_domains",
    )
    contact_stats_sq = materialized_cte(
        select(
            col(Contact.domain_id).label("domain_id"),
            func.count(col(Contact.id)).label("contacts_found"),
            func.count(col(Contact.selected_email)).label("emails_found"),
        )
        .join(possible_ids_sq, col(Contact.domain_id) == possible_ids_sq.c.domain_id)
        .where(col(Contact.campaign_id) == campaign_id)
        .group_by(col(Contact.domain_id)),
        "contact_stage_contact_stats",
    )
    fetched_stats_sq = materialized_cte(
        select(
            col(FetchedPerson.domain_id).label("domain_id"),
            func.count(col(FetchedPerson.id)).label("fetched_people_found"),
        )
        .join(possible_ids_sq, col(FetchedPerson.domain_id) == possible_ids_sq.c.domain_id)
        .where(col(FetchedPerson.campaign_id) == campaign_id)
        .group_by(col(FetchedPerson.domain_id)),
        "contact_stage_fetched_stats",
    )
    contacts_found = func.coalesce(contact_stats_sq.c.contacts_found, 0)
    emails_found = func.coalesce(contact_stats_sq.c.emails_found, 0)
    fetched_people_found = func.coalesce(fetched_stats_sq.c.fetched_people_found, 0)
    status_expr = case(
        (col(UploadedDomain.fetch_status).in_(["queued", "running"]), "running"),
        (col(UploadedDomain.fetch_status) == "failed", "failed"),
        (
            col(UploadedDomain.fetch_status) == "succeeded",
            case((contacts_found > 0, "done"), else_="no_match"),
        ),
        else_="pending",
    )
    rows = session.execute(
        select(
            status_expr.label("status"),
            func.count(col(UploadedDomain.id)).label("domain_count"),
            func.coalesce(func.sum(contacts_found), 0).label("contacts_found"),
            func.coalesce(func.sum(emails_found), 0).label("emails_found"),
            func.coalesce(func.sum(fetched_people_found), 0).label("fetched_people_found"),
        )
        .join(possible_ids_sq, col(UploadedDomain.id) == possible_ids_sq.c.domain_id)
        .outerjoin(contact_stats_sq, col(UploadedDomain.id) == contact_stats_sq.c.domain_id)
        .outerjoin(fetched_stats_sq, col(UploadedDomain.id) == fetched_stats_sq.c.domain_id)
        .where(col(UploadedDomain.campaign_id) == campaign_id)
        .group_by(status_expr)
    ).all()

    buckets = {"pending": 0, "running": 0, "done": 0, "failed": 0, "no_match": 0}
    contacts_found = 0
    emails_found = 0
    fetched_people_found = 0
    total = 0
    for status, domain_count, contact_count, email_count, fetched_people_count in rows:
        normalized_status = str(status)
        amount = int(domain_count or 0)
        if normalized_status in buckets:
            buckets[normalized_status] += amount
        total += amount
        contacts_found += int(contact_count or 0)
        emails_found += int(email_count or 0)
        fetched_people_found += int(fetched_people_count or 0)
    return ContactsStageCounts(
        badge=buckets["pending"] + buckets["running"] + buckets["failed"] + buckets["no_match"],
        all=total,
        pending=buckets["pending"],
        running=buckets["running"],
        done=buckets["done"],
        failed=buckets["failed"],
        no_match=buckets["no_match"],
        contacts_found=contacts_found,
        emails_found=emails_found,
        fetched_people_found=fetched_people_found,
        is_live=buckets["running"] > 0,
    )


def _validation_counts(*, session: Session, campaign_id: UUID) -> ValidationStageCounts:
    rows = session.exec(
        select(
            col(Contact.verification_status),
            col(Contact.verification_applied),
            col(Contact.verification_batch_id),
            func.count(col(Contact.id)),
        )
        .where(
            col(Contact.campaign_id) == campaign_id,
            col(Contact.selected_email).is_not(None),
        )
        .group_by(
            col(Contact.verification_status),
            col(Contact.verification_applied),
            col(Contact.verification_batch_id),
        )
    ).all()
    pending = 0
    running = 0
    valid = 0
    invalid = 0
    unknown = 0
    total = 0
    for status, applied, batch_id, count in rows:
        amount = int(count or 0)
        total += amount
        normalized = (status or "").lower()
        if not applied:
            if batch_id:
                running += amount
            else:
                pending += amount
        elif normalized in {"valid", "deliverable"}:
            valid += amount
        elif normalized in {"invalid", "do_not_mail"}:
            invalid += amount
        else:
            unknown += amount
    return ValidationStageCounts(
        badge=pending + running,
        total=total,
        pending=pending,
        running=running,
        valid=valid,
        invalid=invalid,
        unknown=unknown,
        is_live=running > 0,
    )
