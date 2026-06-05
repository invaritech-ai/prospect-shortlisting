from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func
from sqlmodel import Session, col, select

from app.api.schemas.full_pipeline import FullPipelineCompanyList, FullPipelineCompanyRow
from app.models.base import coerce_utc_datetime, utcnow
from app.models.classification import ClassificationResult
from app.models.contacts import Contact
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeResult
from app.services.email_verification_service import RESULT_VALID, VERIFICATION_STALE_AFTER_DAYS


def _coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return coerce_utc_datetime(value)
    if isinstance(value, str):
        return coerce_utc_datetime(datetime.fromisoformat(value))
    return None


def _latest_datetime(*values: object) -> datetime:
    datetimes = [value for value in (_coerce_datetime(value) for value in values) if value]
    if datetimes:
        return max(datetimes)
    return utcnow()


class FullPipelineService:
    def list_companies(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> FullPipelineCompanyList:
        capped_limit = max(1, min(int(limit), 200))
        safe_offset = max(0, int(offset))
        base_q = select(UploadedDomain).where(col(UploadedDomain.campaign_id) == campaign_id)
        if search and search.strip():
            base_q = base_q.where(col(UploadedDomain.domain).ilike(f"%{search.strip()}%"))

        total = int(session.exec(select(func.count()).select_from(base_q.subquery())).one() or 0)
        domains = session.exec(
            base_q.order_by(col(UploadedDomain.domain).asc())
            .limit(capped_limit)
            .offset(safe_offset)
        ).all()
        domain_ids = [domain.id for domain in domains]
        scrape_by_domain = self._latest_scrapes(
            session=session,
            campaign_id=campaign_id,
            domain_ids=domain_ids,
        )
        classification_by_domain = self._latest_classifications(
            session=session,
            campaign_id=campaign_id,
            domain_ids=domain_ids,
        )
        contact_by_domain = self._contact_summaries(
            session=session,
            campaign_id=campaign_id,
            domain_ids=domain_ids,
        )
        return FullPipelineCompanyList(
            total=total,
            limit=capped_limit,
            offset=safe_offset,
            items=[
                self._row(
                    domain=domain,
                    scrape=scrape_by_domain.get(domain.id),
                    classification=classification_by_domain.get(domain.id),
                    contacts=contact_by_domain.get(domain.id),
                )
                for domain in domains
            ],
        )

    def _latest_scrapes(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
    ) -> dict[UUID, dict[str, object]]:
        if not domain_ids:
            return {}
        latest_ts_sq = (
            select(
                col(ScrapeResult.domain_id).label("domain_id"),
                func.max(col(ScrapeResult.updated_at)).label("latest_updated_at"),
            )
            .where(
                col(ScrapeResult.campaign_id) == campaign_id,
                col(ScrapeResult.domain_id).in_(domain_ids),
            )
            .group_by(col(ScrapeResult.domain_id))
            .subquery()
        )
        rows = session.execute(
            select(
                col(ScrapeResult.domain_id).label("domain_id"),
                col(ScrapeResult.updated_at).label("updated_at"),
                col(ScrapeResult.error_code).label("error_code"),
                col(ScrapeResult.failure_class).label("failure_class"),
                col(ScrapeResult.retryable).label("retryable"),
                col(ScrapeResult.final_url).label("final_url"),
            ).join(
                latest_ts_sq,
                and_(
                    col(ScrapeResult.domain_id) == latest_ts_sq.c.domain_id,
                    col(ScrapeResult.updated_at) == latest_ts_sq.c.latest_updated_at,
                ),
            )
        ).all()
        return {
            row.domain_id: {
                "updated_at": row.updated_at,
                "error_code": row.error_code,
                "failure_class": row.failure_class,
                "retryable": row.retryable,
                "final_url": row.final_url,
            }
            for row in rows
        }

    def _latest_classifications(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
    ) -> dict[UUID, dict[str, object]]:
        if not domain_ids:
            return {}
        latest_ts_sq = (
            select(
                col(ClassificationResult.domain_id).label("domain_id"),
                func.max(col(ClassificationResult.created_at)).label("latest_created_at"),
            )
            .where(
                col(ClassificationResult.campaign_id) == campaign_id,
                col(ClassificationResult.domain_id).in_(domain_ids),
            )
            .group_by(col(ClassificationResult.domain_id))
            .subquery()
        )
        effective_label = func.lower(
            func.coalesce(
                col(ClassificationResult.manual_label),
                col(ClassificationResult.predicted_label),
            )
        )
        rows = session.execute(
            select(
                col(ClassificationResult.domain_id).label("domain_id"),
                col(ClassificationResult.state).label("state"),
                effective_label.label("effective_label"),
            ).join(
                latest_ts_sq,
                and_(
                    col(ClassificationResult.domain_id) == latest_ts_sq.c.domain_id,
                    col(ClassificationResult.created_at) == latest_ts_sq.c.latest_created_at,
                ),
            )
        ).all()
        return {
            row.domain_id: {
                "state": row.state,
                "effective_label": row.effective_label,
            }
            for row in rows
        }

    def _contact_summaries(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
    ) -> dict[UUID, dict[str, object]]:
        if not domain_ids:
            return {}
        cutoff = utcnow() - timedelta(days=VERIFICATION_STALE_AFTER_DAYS)
        has_email = and_(
            col(Contact.selected_email).is_not(None),
            func.trim(col(Contact.selected_email)) != "",
        )
        selected_email = func.lower(func.trim(col(Contact.selected_email)))
        verified_snapshot = func.lower(func.trim(col(Contact.verified_email_snapshot)))
        verification_status = func.lower(func.trim(col(Contact.verification_status)))
        fresh_current_valid = and_(
            has_email,
            col(Contact.verified_email_snapshot).is_not(None),
            selected_email == verified_snapshot,
            col(Contact.verification_applied).is_(True),
            verification_status.in_(sorted(RESULT_VALID)),
            col(Contact.verified_at).is_not(None),
            col(Contact.verified_at) >= cutoff,
        )
        rows = session.execute(
            select(
                col(Contact.domain_id).label("domain_id"),
                func.count(col(Contact.id)).label("contacts_found"),
                func.coalesce(func.sum(case((has_email, 1), else_=0)), 0).label("emails_found"),
                func.coalesce(func.sum(case((has_email, 1), else_=0)), 0).label("email_contact_count"),
                func.coalesce(func.sum(case((fresh_current_valid, 1), else_=0)), 0).label("valid_email_count"),
                func.max(col(Contact.updated_at)).label("latest_contact_updated_at"),
            )
            .where(
                col(Contact.campaign_id) == campaign_id,
                col(Contact.domain_id).in_(domain_ids),
            )
            .group_by(col(Contact.domain_id))
        ).all()
        return {
            row.domain_id: {
                "contacts_found": int(row.contacts_found or 0),
                "emails_found": int(row.emails_found or 0),
                "email_contact_count": int(row.email_contact_count or 0),
                "valid_email_count": int(row.valid_email_count or 0),
                "latest_contact_updated_at": row.latest_contact_updated_at,
            }
            for row in rows
        }

    def _row(
        self,
        *,
        domain: UploadedDomain,
        scrape: dict[str, object] | None,
        classification: dict[str, object] | None,
        contacts: dict[str, object] | None,
    ) -> FullPipelineCompanyRow:
        contacts = contacts or {}
        scrape = scrape or {}
        classification = classification or {}
        latest_scrape_updated_at = _coerce_datetime(scrape.get("updated_at"))
        latest_contact_updated_at = _coerce_datetime(contacts.get("latest_contact_updated_at"))
        return FullPipelineCompanyRow(
            domain_id=domain.id,
            campaign_id=domain.campaign_id,
            raw_url=domain.raw_url,
            normalized_url=domain.normalized_url,
            domain=domain.domain,
            scrape_status=domain.scrape_status,
            decision_status=domain.decision_status,
            fetch_status=domain.fetch_status,
            verify_status=domain.verify_status,
            created_at=domain.created_at,
            latest_scrape_updated_at=latest_scrape_updated_at,
            latest_scrape_error_code=scrape.get("error_code"),
            latest_scrape_failure_class=scrape.get("failure_class"),
            latest_scrape_retryable=scrape.get("retryable"),
            latest_scrape_final_url=scrape.get("final_url"),
            classification_state=classification.get("state"),
            effective_label=classification.get("effective_label"),
            contacts_found=int(contacts.get("contacts_found") or 0),
            emails_found=int(contacts.get("emails_found") or 0),
            email_contact_count=int(contacts.get("email_contact_count") or 0),
            valid_email_count=int(contacts.get("valid_email_count") or 0),
            latest_contact_updated_at=latest_contact_updated_at,
            last_activity=_latest_datetime(
                latest_contact_updated_at,
                latest_scrape_updated_at,
                domain.fetch_updated_at,
                domain.created_at,
            ),
        )
