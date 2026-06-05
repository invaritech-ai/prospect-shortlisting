from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_
from sqlmodel import Session, col, select

from app.models.contacts import Contact, EmailFetchBatch, FetchedPerson, RoleFetchCriteria
from app.models.core import Campaign, UploadedDomain
from app.services.classification_scope import effective_possible_domain_ids_query, materialized_cte
from app.services.contact_reconciliation import find_reconciled_contact
from app.services.email_fetch_criteria import (
    DEFAULT_TARGET_CONTACTS_PER_COMPANY,
    EmailFetchCriteria,
    criteria_from_snapshot,
    load_current_criteria,
    provider_title_hints,
    title_match_status,
    title_matches_criteria,
)
from app.services.email_fetch_providers import (
    ApolloEmailProvider,
    EmailFetchProvider,
    MAX_SNOV_TITLE_HINT_CHUNKS_PER_DOMAIN,
    ProviderCandidate,
    ProviderEmailResult,
    ProviderSearchResult,
    SNOV_POSITIONS_PER_SEARCH,
    SnovEmailProvider,
)


MAX_DOMAINS_PER_BATCH = 200
PREVIEW_CANDIDATE_MULTIPLIER = 4
FETCH_CANDIDATE_MULTIPLIER = 4
COMPANY_SUCCESS_OUTCOMES = {"email_success", "underfilled", "partial_success"}


class EmailFetchServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreviewCandidate:
    domain_id: UUID
    domain: str
    provider: str
    provider_person_id: str
    first_name: str
    last_name: str
    title: str
    linkedin_url: str | None = None


@dataclass(frozen=True)
class PreviewDomain:
    domain_id: UUID
    domain: str
    matched_candidate_count: int
    estimated_apollo_reveals: int
    estimated_snov_fallback: int
    candidates: list[PreviewCandidate]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EmailFetchPreview:
    campaign_id: UUID
    mode: str
    selected_domain_count: int
    target_contacts_per_company: int
    estimated_apollo_reveals: int
    estimated_snov_fallback_min: int
    credit_plan: dict[str, Any]
    criteria_hash: str
    criteria_snapshot: dict[str, Any]
    domains: list[PreviewDomain]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompanyFetchOutcome:
    domain_id: UUID
    domain: str
    outcome: str
    usable_email_count: int
    matched_candidate_count: int
    provider_errors: list[str]
    stored_contact_ids: list[str]


@dataclass(frozen=True)
class EmailFetchBatchView:
    id: UUID
    campaign_id: UUID
    state: str
    selected_domain_count: int
    queued_count: int
    success_count: int
    failed_count: int
    criteria_hash: str | None
    criteria_snapshot: dict[str, Any] | None
    provider_order: list[str]
    result_summary: dict[str, Any] | None
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class EmailFetchCriteriaView:
    id: UUID | None
    campaign_id: UUID
    include_titles: list[str]
    exclude_titles: list[str]
    target_contacts_per_company: int
    criteria_hash: str
    is_active: bool
    created_at: datetime | None


@dataclass(frozen=True)
class EmailFetchCompanyRowView:
    domain_id: UUID
    campaign_id: UUID
    domain: str
    normalized_url: str
    fetch_status: str | None
    status: str
    contacts_found: int
    emails_found: int
    fetched_people_found: int
    updated_at: datetime


@dataclass(frozen=True)
class EmailFetchCompanyCountsView:
    all: int
    pending: int
    running: int
    done: int
    failed: int
    no_match: int
    contacts_found: int
    emails_found: int
    fetched_people_found: int


@dataclass(frozen=True)
class EmailFetchCompanyListView:
    total: int
    limit: int
    offset: int
    counts: EmailFetchCompanyCountsView
    items: list[EmailFetchCompanyRowView]


@dataclass(frozen=True)
class EmailFetchCompanyIdsView:
    ids: list[UUID]
    total: int
    limit: int
    offset: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _latest_datetime(values: list[datetime | None], default: datetime) -> datetime:
    concrete = [value for value in values if value is not None]
    if not concrete:
        return default
    return max(
        concrete,
        key=lambda value: (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp(),
    )


class EmailFetchService:
    def __init__(
        self,
        *,
        apollo_provider: EmailFetchProvider | None = None,
        snov_provider: EmailFetchProvider | None = None,
        target_contacts_per_company: int = DEFAULT_TARGET_CONTACTS_PER_COMPANY,
    ) -> None:
        self.apollo_provider = apollo_provider or ApolloEmailProvider()
        self.snov_provider = snov_provider or SnovEmailProvider()
        self.target_contacts_per_company = target_contacts_per_company

    def get_criteria(self, *, session: Session, campaign_id: UUID) -> EmailFetchCriteriaView:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        criteria, row = load_current_criteria(session, campaign_id=campaign_id)
        criteria = self._with_default_target(criteria)
        return EmailFetchCriteriaView(
            id=row.id if row else None,
            campaign_id=campaign_id,
            include_titles=criteria.include_titles,
            exclude_titles=criteria.exclude_titles,
            target_contacts_per_company=criteria.target_contacts_per_company,
            criteria_hash=criteria.targeting_hash(),
            is_active=bool(row and row.is_active),
            created_at=row.created_at if row else None,
        )

    def save_criteria(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        include_titles: list[str],
        exclude_titles: list[str],
        target_contacts_per_company: int,
    ) -> EmailFetchCriteriaView:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        target = max(1, min(target_contacts_per_company, self.target_contacts_per_company))
        criteria = EmailFetchCriteria(
            include_titles=self._clean_rules(include_titles),
            exclude_titles=self._clean_rules(exclude_titles),
            target_contacts_per_company=target,
        )
        active_rows = session.exec(
            select(RoleFetchCriteria).where(
                col(RoleFetchCriteria.campaign_id) == campaign_id,
                col(RoleFetchCriteria.is_active).is_(True),
            )
        ).all()
        for row in active_rows:
            row.is_active = False
            session.add(row)
        new_row = RoleFetchCriteria(
            campaign_id=campaign_id,
            name="Current targeting",
            include_rules_json=[{"title": title} for title in criteria.include_titles],
            exclude_rules_json=[{"title": title} for title in criteria.exclude_titles],
            criteria_hash=criteria.targeting_hash(),
            is_active=True,
        )
        session.add(new_row)
        session.commit()
        session.refresh(new_row)
        return EmailFetchCriteriaView(
            id=new_row.id,
            campaign_id=campaign_id,
            include_titles=criteria.include_titles,
            exclude_titles=criteria.exclude_titles,
            target_contacts_per_company=criteria.target_contacts_per_company,
            criteria_hash=new_row.criteria_hash,
            is_active=True,
            created_at=new_row.created_at,
        )

    def list_companies(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        status: str = "all",
        search: str | None = None,
        letter: str | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> EmailFetchCompanyListView:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        base_sq = self._company_summary_query(
            campaign_id=campaign_id,
            search=search,
            letter=letter,
        ).subquery()
        counts = self._company_counts_from_summary(session=session, summary_sq=base_sq)
        filtered_q = select(base_sq).select_from(base_sq)
        if status and status != "all":
            filtered_q = filtered_q.where(base_sq.c.status == status)
        total = self._company_total_for_status(counts, status)
        filtered_q = self._apply_company_sort(
            filtered_q,
            summary_sq=base_sq,
            sort_by=sort_by,
            sort_dir=sort_dir,
            dialect_name=session.get_bind().dialect.name,
        )
        page_rows = session.execute(
            filtered_q.offset(offset).limit(limit)
        ).mappings().all()
        return EmailFetchCompanyListView(
            total=total,
            limit=limit,
            offset=offset,
            counts=counts,
            items=[self._company_row_from_summary(row) for row in page_rows],
        )

    def get_letter_counts(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        status: str = "all",
        search: str | None = None,
    ) -> dict[str, int]:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        base_sq = self._company_summary_query(
            campaign_id=campaign_id,
            search=search,
            letter=None,
        ).subquery()
        q = select(base_sq.c.letter_bucket, func.count()).select_from(base_sq)
        if status and status != "all":
            q = q.where(base_sq.c.status == status)
        rows = session.execute(q.group_by(base_sq.c.letter_bucket)).all()
        return {str(bucket): int(count or 0) for bucket, count in rows}

    def list_company_ids(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        status: str = "all",
        search: str | None = None,
        letter: str | None = None,
        fetchable_only: bool = False,
        limit: int = MAX_DOMAINS_PER_BATCH,
        offset: int = 0,
    ) -> EmailFetchCompanyIdsView:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        base_sq = self._company_summary_query(
            campaign_id=campaign_id,
            search=search,
            letter=letter,
        ).subquery()
        q = select(base_sq.c.domain_id).select_from(base_sq)
        if status and status != "all":
            q = q.where(base_sq.c.status == status)
        if fetchable_only:
            q = q.where(base_sq.c.status.in_(["pending", "failed"]))
        total = int(session.exec(select(func.count()).select_from(q.subquery())).one() or 0)
        capped_limit = max(1, min(limit, MAX_DOMAINS_PER_BATCH))
        rows = session.execute(
            q.order_by(base_sq.c.domain.asc()).offset(offset).limit(capped_limit)
        ).all()
        return EmailFetchCompanyIdsView(
            ids=[row[0] for row in rows],
            total=total,
            limit=capped_limit,
            offset=offset,
        )

    def get_active_batch(self, *, session: Session, campaign_id: UUID) -> EmailFetchBatchView | None:
        self._ensure_campaign(session=session, campaign_id=campaign_id)
        batches = session.exec(
            select(EmailFetchBatch)
            .where(
                col(EmailFetchBatch.campaign_id) == campaign_id,
                col(EmailFetchBatch.state).in_(["queued", "running"]),
            )
            .order_by(col(EmailFetchBatch.created_at).desc())
            .limit(10)
        ).all()
        for batch in batches:
            if self._batch_has_active_domains(session=session, batch=batch):
                return self._batch_view(batch)
        return None

    def preview(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
        mode: str = "fetch",
    ) -> EmailFetchPreview:
        domains = self._resolve_domains(session=session, campaign_id=campaign_id, domain_ids=domain_ids)
        self._validate_mode_for_domains(session=session, campaign_id=campaign_id, domains=domains, mode=mode)
        criteria, _ = load_current_criteria(session, campaign_id=campaign_id)
        criteria = self._with_default_target(criteria)
        warnings: list[str] = []
        domain_previews: list[PreviewDomain] = []
        estimated_apollo_reveals = 0
        estimated_snov_fallback = 0

        if not criteria.include_titles:
            warnings.append("no_include_title_criteria")

        for domain in domains:
            if not criteria.include_titles:
                domain_previews.append(
                    PreviewDomain(
                        domain_id=domain.id,
                        domain=domain.domain,
                        matched_candidate_count=0,
                        estimated_apollo_reveals=0,
                        estimated_snov_fallback=criteria.target_contacts_per_company,
                        candidates=[],
                        warnings=["no_include_title_criteria"],
                    )
                )
                estimated_snov_fallback += criteria.target_contacts_per_company
                continue

            search_limit = criteria.target_contacts_per_company * PREVIEW_CANDIDATE_MULTIPLIER
            search = self.apollo_provider.search_candidates(
                domain=domain.domain,
                criteria=criteria,
                limit=search_limit,
            )
            matched = self._rank_candidates(
                [candidate for candidate in search.candidates if title_matches_criteria(candidate.title, criteria)]
            )
            preview_candidates = matched[: criteria.target_contacts_per_company]
            reveal_estimate = len(preview_candidates)
            fallback_estimate = max(criteria.target_contacts_per_company - reveal_estimate, 0)
            estimated_apollo_reveals += reveal_estimate
            estimated_snov_fallback += fallback_estimate
            domain_warnings = []
            if search.error_code:
                domain_warnings.append(search.error_code)
            if not matched:
                domain_warnings.append("no_apollo_title_matches")
            domain_previews.append(
                PreviewDomain(
                    domain_id=domain.id,
                    domain=domain.domain,
                    matched_candidate_count=len(matched),
                    estimated_apollo_reveals=reveal_estimate,
                    estimated_snov_fallback=fallback_estimate,
                    candidates=[
                        PreviewCandidate(
                            domain_id=domain.id,
                            domain=domain.domain,
                            provider=candidate.provider,
                            provider_person_id=candidate.provider_person_id,
                            first_name=candidate.first_name,
                            last_name=candidate.last_name,
                            title=candidate.title,
                            linkedin_url=candidate.linkedin_url,
                        )
                        for candidate in preview_candidates
                    ],
                    warnings=domain_warnings,
                )
            )

        return EmailFetchPreview(
            campaign_id=campaign_id,
            mode=mode,
            selected_domain_count=len(domains),
            target_contacts_per_company=criteria.target_contacts_per_company,
            estimated_apollo_reveals=estimated_apollo_reveals,
            estimated_snov_fallback_min=estimated_snov_fallback,
            credit_plan=self._credit_plan(
                criteria=criteria,
                selected_domain_count=len(domains),
                estimated_apollo_reveals=estimated_apollo_reveals,
                estimated_snov_email_lookups=estimated_snov_fallback,
            ),
            criteria_hash=criteria.targeting_hash(),
            criteria_snapshot=criteria.snapshot(),
            domains=domain_previews,
            warnings=warnings,
        )

    def create_batch(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
        mode: str = "fetch",
    ) -> EmailFetchBatch:
        domains = self._resolve_domains(session=session, campaign_id=campaign_id, domain_ids=domain_ids)
        self._validate_mode_for_domains(session=session, campaign_id=campaign_id, domains=domains, mode=mode)
        criteria, criteria_row = load_current_criteria(session, campaign_id=campaign_id)
        criteria = self._with_default_target(criteria)
        if not criteria.include_titles:
            raise EmailFetchServiceError("no_include_title_criteria", "Add at least one target title before fetching contacts.")
        snapshot = criteria.snapshot()
        batch = EmailFetchBatch(
            campaign_id=campaign_id,
            role_fetch_criteria_id=criteria_row.id if criteria_row else None,
            criteria_snapshot_json=snapshot,
            criteria_hash=criteria.targeting_hash(),
            provider_order_json=criteria.normalized_provider_order(),
            selected_domain_ids_json=[str(domain.id) for domain in domains],
            result_summary_json={
                "mode": mode,
                "planned_usage": self._credit_plan(
                    criteria=criteria,
                    selected_domain_count=len(domains),
                    estimated_apollo_reveals=len(domains) * criteria.target_contacts_per_company,
                    estimated_snov_email_lookups=len(domains) * criteria.target_contacts_per_company,
                ),
                "domains": [],
                "warnings": [],
                "provider_usage": {},
            },
            state="queued",
            selected_domain_count=len(domains),
            queued_count=len(domains),
        )
        session.add(batch)
        queued_at = _utcnow()
        for domain in domains:
            domain.fetch_status = "queued"
            domain.fetch_updated_at = queued_at
            session.add(domain)
        session.commit()
        session.refresh(batch)
        return batch

    def get_batch(self, *, session: Session, batch_id: UUID) -> EmailFetchBatchView:
        batch = session.get(EmailFetchBatch, batch_id)
        if batch is None:
            raise EmailFetchServiceError("batch_not_found", "Email fetch batch not found.")
        return self._batch_view(batch)

    def _batch_has_active_domains(self, *, session: Session, batch: EmailFetchBatch) -> bool:
        domain_ids: list[UUID] = []
        for raw_id in batch.selected_domain_ids_json or []:
            try:
                domain_ids.append(UUID(str(raw_id)))
            except (TypeError, ValueError):
                continue
        if not domain_ids:
            return False
        active_count = session.exec(
            select(func.count())
            .select_from(UploadedDomain)
            .where(
                col(UploadedDomain.campaign_id) == batch.campaign_id,
                col(UploadedDomain.id).in_(domain_ids),
                col(UploadedDomain.fetch_status).in_(["queued", "running"]),
            )
        ).one()
        return int(active_count or 0) > 0

    def run_batch(self, *, session: Session, batch_id: UUID) -> EmailFetchBatch:
        batch = session.get(EmailFetchBatch, batch_id)
        if batch is None:
            raise EmailFetchServiceError("batch_not_found", "Email fetch batch not found.")
        if batch.state in {"succeeded", "failed"}:
            return batch

        criteria = criteria_from_snapshot(batch.criteria_snapshot_json)
        criteria = self._with_default_target(criteria)
        domain_ids = [UUID(raw) for raw in batch.selected_domain_ids_json or []]
        domains = self._resolve_domains(session=session, campaign_id=batch.campaign_id, domain_ids=domain_ids)

        batch.state = "running"
        session.add(batch)
        running_at = _utcnow()
        for domain in domains:
            domain.fetch_status = "running"
            domain.fetch_updated_at = running_at
            session.add(domain)
        session.commit()

        outcomes: list[CompanyFetchOutcome] = []
        provider_usage: dict[str, dict[str, int]] = {
            "apollo": {
                "searches": 0,
                "email_fetches": 0,
                "usable_emails": 0,
                "candidates_returned": 0,
                "rejected": 0,
                "promoted": 0,
            },
            "snov": {
                "searches": 0,
                "email_fetches": 0,
                "usable_emails": 0,
                "candidates_returned": 0,
                "rejected": 0,
                "promoted": 0,
            },
        }

        for domain in domains:
            outcome = self._fetch_for_domain(
                session=session,
                batch=batch,
                domain=domain,
                criteria=criteria,
                provider_usage=provider_usage,
            )
            outcomes.append(outcome)
            domain.fetch_status = "failed" if outcome.outcome == "provider_failed" else "succeeded"
            domain.fetch_updated_at = _utcnow()
            session.add(domain)
            session.commit()

        batch.success_count = sum(1 for outcome in outcomes if outcome.outcome in COMPANY_SUCCESS_OUTCOMES)
        batch.failed_count = sum(1 for outcome in outcomes if outcome.outcome == "provider_failed")
        batch.queued_count = 0
        batch.state = "failed" if batch.failed_count == batch.selected_domain_count and batch.selected_domain_count else "succeeded"
        batch.finished_at = _utcnow()
        previous_summary = batch.result_summary_json or {}
        batch.result_summary_json = {
            "mode": previous_summary.get("mode", "fetch"),
            "planned_usage": previous_summary.get("planned_usage", {}),
            "domains": [self._outcome_dict(outcome) for outcome in outcomes],
            "provider_usage": provider_usage,
            "warnings": self._batch_warnings(outcomes),
        }
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return batch

    def _fetch_for_domain(
        self,
        *,
        session: Session,
        batch: EmailFetchBatch,
        domain: UploadedDomain,
        criteria: EmailFetchCriteria,
        provider_usage: dict[str, dict[str, int]],
    ) -> CompanyFetchOutcome:
        if not criteria.include_titles:
            return CompanyFetchOutcome(
                domain_id=domain.id,
                domain=domain.domain,
                outcome="no_matches",
                usable_email_count=0,
                matched_candidate_count=0,
                provider_errors=[],
                stored_contact_ids=[],
            )

        stored_contact_ids: list[str] = []
        matched_count = 0
        provider_errors: list[str] = []
        usable_count = 0

        apollo_result = self._search_provider(
            provider=self.apollo_provider,
            domain=domain,
            criteria=criteria,
            limit=criteria.target_contacts_per_company * FETCH_CANDIDATE_MULTIPLIER,
            provider_usage=provider_usage,
        )
        if apollo_result.error_code:
            provider_errors.append(apollo_result.error_code)
        apollo_matched = self._store_fetched_candidates(
            session=session,
            batch=batch,
            domain=domain,
            criteria=criteria,
            candidates=apollo_result.candidates,
            provider_usage=provider_usage,
        )
        apollo_matched = self._rank_candidates(apollo_matched)
        matched_count += len(apollo_matched)
        usable_count += self._fetch_and_store_candidates(
            session=session,
            batch=batch,
            domain=domain,
            criteria=criteria,
            candidates=apollo_matched,
            remaining=criteria.target_contacts_per_company,
            provider_usage=provider_usage,
            stored_contact_ids=stored_contact_ids,
            provider_errors=provider_errors,
        )

        remaining = criteria.target_contacts_per_company - usable_count
        if remaining > 0:
            snov_result = self._search_provider(
                provider=self.snov_provider,
                domain=domain,
                criteria=criteria,
                limit=remaining * FETCH_CANDIDATE_MULTIPLIER,
                provider_usage=provider_usage,
            )
            if snov_result.error_code:
                provider_errors.append(snov_result.error_code)
            snov_matched = self._store_fetched_candidates(
                session=session,
                batch=batch,
                domain=domain,
                criteria=criteria,
                candidates=snov_result.candidates,
                provider_usage=provider_usage,
            )
            snov_matched = self._rank_candidates(snov_matched)
            matched_count += len(snov_matched)
            usable_count += self._fetch_and_store_candidates(
                session=session,
                batch=batch,
                domain=domain,
                criteria=criteria,
                candidates=snov_matched,
                remaining=remaining,
                provider_usage=provider_usage,
                stored_contact_ids=stored_contact_ids,
                provider_errors=provider_errors,
            )

        return CompanyFetchOutcome(
            domain_id=domain.id,
            domain=domain.domain,
            outcome=self._company_outcome(
                usable_count=usable_count,
                matched_count=matched_count,
                provider_errors=provider_errors,
                target=criteria.target_contacts_per_company,
                attempted_provider_count=2,
            ),
            usable_email_count=usable_count,
            matched_candidate_count=matched_count,
            provider_errors=provider_errors,
            stored_contact_ids=stored_contact_ids,
        )

    def _search_provider(
        self,
        *,
        provider: EmailFetchProvider,
        domain: UploadedDomain,
        criteria: EmailFetchCriteria,
        limit: int,
        provider_usage: dict[str, dict[str, int]],
    ) -> ProviderSearchResult:
        result = provider.search_candidates(domain=domain.domain, criteria=criteria, limit=limit)
        provider_usage[provider.name]["searches"] += int(result.raw_summary.get("searches") or 1)
        provider_usage[provider.name]["candidates_returned"] += len(result.candidates)
        return result

    def _store_fetched_candidates(
        self,
        *,
        session: Session,
        batch: EmailFetchBatch,
        domain: UploadedDomain,
        criteria: EmailFetchCriteria,
        candidates: list[ProviderCandidate],
        provider_usage: dict[str, dict[str, int]],
    ) -> list[ProviderCandidate]:
        qualified: list[ProviderCandidate] = []
        for candidate in candidates:
            status, reason = title_match_status(candidate.title, criteria)
            if status == "qualified":
                match_status = "qualified_not_used"
                match_reason = "Matched but target already filled"
                qualified.append(candidate)
            else:
                match_status = status
                match_reason = reason
                provider_usage[candidate.provider]["rejected"] += 1
            self._upsert_fetched_person(
                session=session,
                batch=batch,
                domain=domain,
                criteria=criteria,
                candidate=candidate,
                match_status=match_status,
                match_reason=match_reason,
            )
        session.flush()
        return qualified

    def _upsert_fetched_person(
        self,
        *,
        session: Session,
        batch: EmailFetchBatch,
        domain: UploadedDomain,
        criteria: EmailFetchCriteria,
        candidate: ProviderCandidate,
        match_status: str,
        match_reason: str,
    ) -> FetchedPerson:
        now = _utcnow()
        person = self._find_fetched_person(session=session, batch=batch, domain=domain, candidate=candidate)
        if person is None:
            person = FetchedPerson(
                campaign_id=batch.campaign_id,
                domain_id=domain.id,
                email_fetch_batch_id=batch.id,
                criteria_hash=criteria.targeting_hash(),
                provider=candidate.provider,
                provider_person_id=candidate.provider_person_id,
                created_at=now,
            )
        person.first_name = candidate.first_name
        person.last_name = candidate.last_name
        person.title = candidate.title
        person.linkedin_url = candidate.linkedin_url
        person.raw_summary_json = candidate.raw_summary
        person.match_status = match_status
        person.match_reason = match_reason
        if person.contact_id is None:
            match = find_reconciled_contact(
                session=session,
                campaign_id=batch.campaign_id,
                domain_id=domain.id,
                provider=candidate.provider,
                provider_person_id=candidate.provider_person_id,
                first_name=candidate.first_name,
                last_name=candidate.last_name,
                title=candidate.title,
                linkedin_url=candidate.linkedin_url,
            )
            if match.contact:
                person.contact_id = match.contact.id
        person.updated_at = now
        session.add(person)
        return person

    def _find_fetched_person(
        self,
        *,
        session: Session,
        batch: EmailFetchBatch,
        domain: UploadedDomain,
        candidate: ProviderCandidate,
    ) -> FetchedPerson | None:
        return session.exec(
            select(FetchedPerson)
            .where(
                col(FetchedPerson.email_fetch_batch_id) == batch.id,
                col(FetchedPerson.domain_id) == domain.id,
                col(FetchedPerson.provider) == candidate.provider,
                col(FetchedPerson.provider_person_id) == candidate.provider_person_id,
            )
            .limit(1)
        ).first()

    def _mark_fetched_person_email_result(
        self,
        *,
        session: Session,
        batch: EmailFetchBatch,
        domain: UploadedDomain,
        candidate: ProviderCandidate,
        email_result: ProviderEmailResult,
        contact: Contact | None,
    ) -> None:
        person = self._find_fetched_person(session=session, batch=batch, domain=domain, candidate=candidate)
        if person is None:
            return
        person.email_lookup_attempted = True
        person.email_result = email_result.email or None
        person.email_status = email_result.status
        person.email_error_code = email_result.error_code
        person.email_raw_json = email_result.raw_summary
        person.contact_id = contact.id if contact else None
        if contact:
            person.match_status = "qualified_promoted"
            person.match_reason = "Title matched"
        person.updated_at = _utcnow()
        session.add(person)

    def _fetch_and_store_candidates(
        self,
        *,
        session: Session,
        batch: EmailFetchBatch,
        domain: UploadedDomain,
        criteria: EmailFetchCriteria,
        candidates: list[ProviderCandidate],
        remaining: int,
        provider_usage: dict[str, dict[str, int]],
        stored_contact_ids: list[str],
        provider_errors: list[str],
    ) -> int:
        usable_count = 0
        for candidate in candidates:
            if usable_count >= remaining:
                break
            provider_usage[candidate.provider]["email_fetches"] += 1
            email_result = self._provider_for(candidate.provider).fetch_email(candidate=candidate, domain=domain.domain)
            if email_result.error_code:
                provider_errors.append(email_result.error_code)
            contact = self._upsert_contact(
                session=session,
                batch=batch,
                domain=domain,
                criteria=criteria,
                candidate=candidate,
                email_result=email_result,
            )
            self._mark_fetched_person_email_result(
                session=session,
                batch=batch,
                domain=domain,
                candidate=candidate,
                email_result=email_result,
                contact=contact,
            )
            if contact and str(contact.id) not in stored_contact_ids:
                stored_contact_ids.append(str(contact.id))
                provider_usage[candidate.provider]["promoted"] += 1
            if email_result.usable:
                usable_count += 1
                provider_usage[candidate.provider]["usable_emails"] += 1
        return usable_count

    def _upsert_contact(
        self,
        *,
        session: Session,
        batch: EmailFetchBatch,
        domain: UploadedDomain,
        criteria: EmailFetchCriteria,
        candidate: ProviderCandidate,
        email_result: ProviderEmailResult,
    ) -> Contact | None:
        contact = self._find_existing_contact(session=session, domain=domain, candidate=candidate, email=email_result.email)
        now = _utcnow()
        if contact is None:
            contact = Contact(
                campaign_id=batch.campaign_id,
                domain_id=domain.id,
                email_fetch_batch_id=batch.id,
                criteria_hash=criteria.targeting_hash(),
                first_name=candidate.first_name,
                last_name=candidate.last_name,
                title=candidate.title,
                linkedin_url=candidate.linkedin_url,
                title_match=True,
                created_at=now,
                updated_at=now,
            )
        else:
            contact.email_fetch_batch_id = batch.id
            contact.criteria_hash = criteria.targeting_hash()
            contact.first_name = candidate.first_name or contact.first_name
            contact.last_name = candidate.last_name or contact.last_name
            contact.title = candidate.title or contact.title
            contact.linkedin_url = candidate.linkedin_url or contact.linkedin_url
            contact.title_match = True
            contact.updated_at = now

        if candidate.provider == "apollo":
            contact.apollo_person_id = candidate.provider_person_id
            if email_result.usable:
                contact.apollo_email = email_result.email
        elif candidate.provider == "snov":
            contact.snov_person_id = candidate.provider_person_id
            if email_result.usable:
                contact.snov_email = email_result.email

        evidence = dict(contact.provider_evidence_json or {})
        evidence[candidate.provider] = {
            "person_id": candidate.provider_person_id,
            "candidate": candidate.raw_summary,
            "email": email_result.raw_summary,
            "email_status": email_result.status,
            "error_code": email_result.error_code,
        }
        contact.provider_evidence_json = evidence

        if email_result.usable and not contact.selected_email:
            contact.selected_email = email_result.email
            contact.selected_email_provider = candidate.provider
            contact.verification_status = None
            contact.verification_sub_status = None
            contact.verification_raw_json = None
            contact.verification_applied = False
            contact.verified_at = None
            contact.verified_email_snapshot = None

        session.add(contact)
        session.flush()
        return contact

    def _find_existing_contact(
        self,
        *,
        session: Session,
        domain: UploadedDomain,
        candidate: ProviderCandidate,
        email: str,
    ) -> Contact | None:
        if email:
            by_email = session.exec(
                select(Contact)
                .where(
                    col(Contact.domain_id) == domain.id,
                    func.lower(Contact.selected_email) == email.lower(),
                )
                .limit(1)
            ).first()
            if by_email:
                return by_email
        if candidate.linkedin_url:
            by_linkedin = session.exec(
                select(Contact)
                .where(
                    col(Contact.domain_id) == domain.id,
                    col(Contact.linkedin_url) == candidate.linkedin_url,
                )
                .limit(1)
            ).first()
            if by_linkedin:
                return by_linkedin
        provider_column = Contact.apollo_person_id if candidate.provider == "apollo" else Contact.snov_person_id
        by_provider_id = session.exec(
            select(Contact)
            .where(
                col(Contact.domain_id) == domain.id,
                provider_column == candidate.provider_person_id,
            )
            .limit(1)
        ).first()
        if by_provider_id:
            return by_provider_id
        if candidate.first_name and candidate.last_name:
            return session.exec(
                select(Contact)
                .where(
                    col(Contact.domain_id) == domain.id,
                    func.lower(Contact.first_name) == candidate.first_name.lower(),
                    func.lower(Contact.last_name) == candidate.last_name.lower(),
                )
                .limit(1)
            ).first()
        return None

    def _ensure_campaign(self, *, session: Session, campaign_id: UUID) -> None:
        if session.get(Campaign, campaign_id) is None:
            raise EmailFetchServiceError("campaign_not_found", "Campaign not found.")

    def _clean_rules(self, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in values:
            value = str(raw).strip()
            if not value or value.startswith("#"):
                continue
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

    def _company_summary_query(
        self,
        *,
        campaign_id: UUID,
        search: str | None,
        letter: str | None,
    ):
        possible_ids_sq = materialized_cte(
            effective_possible_domain_ids_query(campaign_id),
            "possible_email_fetch_domains",
        )
        contact_stats_sq = materialized_cte(
            select(
                col(Contact.domain_id).label("domain_id"),
                func.count(col(Contact.id)).label("contacts_found"),
                func.count(col(Contact.selected_email)).label("emails_found"),
                func.max(col(Contact.updated_at)).label("contacts_updated_at"),
            )
            .join(possible_ids_sq, col(Contact.domain_id) == possible_ids_sq.c.domain_id)
            .where(col(Contact.campaign_id) == campaign_id)
            .group_by(col(Contact.domain_id)),
            "email_fetch_contact_stats",
        )
        fetched_stats_sq = materialized_cte(
            select(
                col(FetchedPerson.domain_id).label("domain_id"),
                func.count(col(FetchedPerson.id)).label("fetched_count"),
                func.count(func.distinct(col(FetchedPerson.contact_id))).label("linked_contact_count"),
                func.max(col(FetchedPerson.updated_at)).label("fetched_updated_at"),
            )
            .join(possible_ids_sq, col(FetchedPerson.domain_id) == possible_ids_sq.c.domain_id)
            .where(col(FetchedPerson.campaign_id) == campaign_id)
            .group_by(col(FetchedPerson.domain_id)),
            "email_fetch_fetched_stats",
        )
        contacts_found = func.coalesce(contact_stats_sq.c.contacts_found, 0)
        emails_found = func.coalesce(contact_stats_sq.c.emails_found, 0)
        fetched_count = func.coalesce(fetched_stats_sq.c.fetched_count, 0)
        linked_contact_count = func.coalesce(fetched_stats_sq.c.linked_contact_count, 0)
        legacy_contact_count = case(
            (contacts_found > linked_contact_count, contacts_found - linked_contact_count),
            else_=0,
        )
        fetched_people_found = fetched_count + legacy_contact_count
        status_expr = case(
            (col(UploadedDomain.fetch_status).in_(["queued", "running"]), "running"),
            (col(UploadedDomain.fetch_status) == "failed", "failed"),
            (
                col(UploadedDomain.fetch_status) == "succeeded",
                case((contacts_found > 0, "done"), else_="no_match"),
            ),
            else_="pending",
        )
        first_char = func.upper(func.substr(col(UploadedDomain.domain), 1, 1))
        letter_bucket = case(
            (first_char.between("A", "Z"), first_char),
            else_="#",
        )
        query = (
            select(
                col(UploadedDomain.id).label("domain_id"),
                col(UploadedDomain.campaign_id).label("campaign_id"),
                col(UploadedDomain.domain).label("domain"),
                col(UploadedDomain.normalized_url).label("normalized_url"),
                col(UploadedDomain.fetch_status).label("fetch_status"),
                col(UploadedDomain.fetch_updated_at).label("fetch_updated_at"),
                col(UploadedDomain.created_at).label("domain_created_at"),
                contacts_found.label("contacts_found"),
                emails_found.label("emails_found"),
                fetched_people_found.label("fetched_people_found"),
                contact_stats_sq.c.contacts_updated_at.label("contacts_updated_at"),
                fetched_stats_sq.c.fetched_updated_at.label("fetched_updated_at"),
                status_expr.label("status"),
                letter_bucket.label("letter_bucket"),
            )
            .join(possible_ids_sq, col(UploadedDomain.id) == possible_ids_sq.c.domain_id)
            .outerjoin(contact_stats_sq, col(UploadedDomain.id) == contact_stats_sq.c.domain_id)
            .outerjoin(fetched_stats_sq, col(UploadedDomain.id) == fetched_stats_sq.c.domain_id)
            .where(col(UploadedDomain.campaign_id) == campaign_id)
        )
        if search and search.strip():
            query = query.where(col(UploadedDomain.domain).ilike(f"%{search.strip()}%"))
        if letter and letter != "all":
            normalized_letter = letter.upper()
            if normalized_letter == "#":
                query = query.where(or_(first_char < "A", first_char > "Z"))
            else:
                query = query.where(first_char == normalized_letter)
        return query

    def _company_counts_from_summary(self, *, session: Session, summary_sq) -> EmailFetchCompanyCountsView:
        rows = session.execute(
            select(
                summary_sq.c.status,
                func.count().label("domain_count"),
                func.coalesce(func.sum(summary_sq.c.contacts_found), 0).label("contacts_found"),
                func.coalesce(func.sum(summary_sq.c.emails_found), 0).label("emails_found"),
                func.coalesce(func.sum(summary_sq.c.fetched_people_found), 0).label("fetched_people_found"),
            )
            .select_from(summary_sq)
            .group_by(summary_sq.c.status)
        ).all()
        counts = {"pending": 0, "running": 0, "done": 0, "failed": 0, "no_match": 0}
        contacts_found = 0
        emails_found = 0
        fetched_people_found = 0
        total = 0
        for status, domain_count, contact_count, email_count, fetched_count in rows:
            amount = int(domain_count or 0)
            if status in counts:
                counts[str(status)] = amount
            total += amount
            contacts_found += int(contact_count or 0)
            emails_found += int(email_count or 0)
            fetched_people_found += int(fetched_count or 0)
        return EmailFetchCompanyCountsView(
            all=total,
            pending=counts["pending"],
            running=counts["running"],
            done=counts["done"],
            failed=counts["failed"],
            no_match=counts["no_match"],
            contacts_found=contacts_found,
            emails_found=emails_found,
            fetched_people_found=fetched_people_found,
        )

    def _company_total_for_status(self, counts: EmailFetchCompanyCountsView, status: str | None) -> int:
        if not status or status == "all":
            return counts.all
        if status == "pending":
            return counts.pending
        if status == "running":
            return counts.running
        if status == "done":
            return counts.done
        if status == "failed":
            return counts.failed
        if status == "no_match":
            return counts.no_match
        return 0

    def _apply_company_sort(
        self,
        query,
        *,
        summary_sq,
        sort_by: str | None,
        sort_dir: str | None,
        dialect_name: str,
    ):
        normalized = (sort_by or "").strip().lower()
        descending = (sort_dir or "").strip().lower() == "desc"
        order_expr = None
        if normalized == "domain":
            order_expr = summary_sq.c.domain
        elif normalized == "status":
            order_expr = summary_sq.c.status
        elif normalized == "fetched":
            order_expr = summary_sq.c.fetched_people_found
        elif normalized == "contacts":
            order_expr = summary_sq.c.contacts_found
        elif normalized == "emails":
            order_expr = summary_sq.c.emails_found
        elif normalized == "updated":
            fallback = summary_sq.c.domain_created_at
            updated_args = [
                func.coalesce(summary_sq.c.contacts_updated_at, fallback),
                func.coalesce(summary_sq.c.fetched_updated_at, fallback),
                func.coalesce(summary_sq.c.fetch_updated_at, fallback),
                fallback,
            ]
            order_expr = (
                func.max(*updated_args)
                if dialect_name == "sqlite"
                else func.greatest(*updated_args)
            )
        if order_expr is None:
            return query.order_by(summary_sq.c.domain.asc())
        ordered = order_expr.desc() if descending else order_expr.asc()
        return query.order_by(ordered, summary_sq.c.domain.asc())

    def _company_row_from_summary(self, row) -> EmailFetchCompanyRowView:
        contacts_updated_at = row["contacts_updated_at"]
        fetched_updated_at = row["fetched_updated_at"]
        fetch_updated_at = row["fetch_updated_at"]
        domain_created_at = row["domain_created_at"]
        return EmailFetchCompanyRowView(
            domain_id=row["domain_id"],
            campaign_id=row["campaign_id"],
            domain=row["domain"],
            normalized_url=row["normalized_url"],
            fetch_status=row["fetch_status"],
            status=row["status"],
            contacts_found=int(row["contacts_found"] or 0),
            emails_found=int(row["emails_found"] or 0),
            fetched_people_found=int(row["fetched_people_found"] or 0),
            updated_at=_latest_datetime(
                [contacts_updated_at, fetched_updated_at, fetch_updated_at, domain_created_at],
                domain_created_at,
            ),
        )

    def _company_rows(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        search: str | None,
        letter: str | None,
    ) -> list[EmailFetchCompanyRowView]:
        possible_ids_sq = effective_possible_domain_ids_query(campaign_id).subquery()
        base_q = (
            select(UploadedDomain)
            .join(possible_ids_sq, col(UploadedDomain.id) == possible_ids_sq.c.domain_id)
            .where(col(UploadedDomain.campaign_id) == campaign_id)
        )
        if search and search.strip():
            base_q = base_q.where(col(UploadedDomain.domain).ilike(f"%{search.strip()}%"))

        domains = list(session.exec(base_q.order_by(col(UploadedDomain.domain).asc())).all())
        if letter and letter != "all":
            domains = [domain for domain in domains if self._domain_matches_letter(domain.domain, letter)]

        contact_stats = self._contact_stats_by_domain(
            session=session,
            campaign_id=campaign_id,
            domain_ids=[domain.id for domain in domains],
        )
        fetched_stats = self._fetched_people_stats_by_domain(
            session=session,
            campaign_id=campaign_id,
            domain_ids=[domain.id for domain in domains],
            contact_stats=contact_stats,
        )
        return [
            self._company_row_from_domain(
                domain=domain,
                contact_stats=contact_stats.get(domain.id),
                fetched_stats=fetched_stats.get(domain.id),
            )
            for domain in domains
        ]

    def _domain_matches_letter(self, domain: str, letter: str) -> bool:
        return self._letter_bucket(domain) == letter.upper()

    def _letter_bucket(self, domain: str) -> str:
        first_char = domain[:1].upper()
        return first_char if "A" <= first_char <= "Z" else "#"

    def _contact_stats_by_domain(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
    ) -> dict[UUID, tuple[int, int, datetime | None]]:
        if not domain_ids:
            return {}
        rows = session.exec(
            select(
                col(Contact.domain_id),
                func.count(col(Contact.id)),
                func.count(col(Contact.selected_email)),
                func.max(col(Contact.updated_at)),
            )
            .where(
                col(Contact.campaign_id) == campaign_id,
                col(Contact.domain_id).in_(domain_ids),
            )
            .group_by(col(Contact.domain_id))
        ).all()
        return {row[0]: (int(row[1] or 0), int(row[2] or 0), row[3]) for row in rows}

    def _fetched_people_stats_by_domain(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
        contact_stats: dict[UUID, tuple[int, int, datetime | None]],
    ) -> dict[UUID, tuple[int, datetime | None]]:
        if not domain_ids:
            return {}
        fetched_rows = session.exec(
            select(
                col(FetchedPerson.domain_id),
                func.count(col(FetchedPerson.id)),
                func.max(col(FetchedPerson.updated_at)),
            )
            .where(
                col(FetchedPerson.campaign_id) == campaign_id,
                col(FetchedPerson.domain_id).in_(domain_ids),
            )
            .group_by(col(FetchedPerson.domain_id))
        ).all()
        stats: dict[UUID, tuple[int, datetime | None]] = {
            row[0]: (int(row[1] or 0), row[2]) for row in fetched_rows
        }

        linked_contact_rows = session.exec(
            select(
                col(FetchedPerson.domain_id),
                func.count(func.distinct(col(FetchedPerson.contact_id))),
            )
            .where(
                col(FetchedPerson.campaign_id) == campaign_id,
                col(FetchedPerson.domain_id).in_(domain_ids),
                col(FetchedPerson.contact_id).is_not(None),
            )
            .group_by(col(FetchedPerson.domain_id))
        ).all()
        linked_by_domain = {row[0]: int(row[1] or 0) for row in linked_contact_rows}
        for domain_id, (contacts_found, _emails_found, contacts_updated_at) in contact_stats.items():
            current_count, current_updated_at = stats.get(domain_id, (0, None))
            legacy_count = max(contacts_found - linked_by_domain.get(domain_id, 0), 0)
            latest = _latest_datetime([current_updated_at, contacts_updated_at], contacts_updated_at)
            stats[domain_id] = (current_count + legacy_count, latest)
        return stats

    def _company_row_from_domain(
        self,
        *,
        domain: UploadedDomain,
        contact_stats: tuple[int, int, datetime | None] | None,
        fetched_stats: tuple[int, datetime | None] | None,
    ) -> EmailFetchCompanyRowView:
        contacts_found, emails_found, contacts_updated_at = contact_stats or (0, 0, None)
        fetched_people_found, fetched_updated_at = fetched_stats or (0, None)
        return EmailFetchCompanyRowView(
            domain_id=domain.id,
            campaign_id=domain.campaign_id,
            domain=domain.domain,
            normalized_url=domain.normalized_url,
            fetch_status=domain.fetch_status,
            status=self._company_status(domain.fetch_status, contacts_found),
            contacts_found=contacts_found,
            emails_found=emails_found,
            fetched_people_found=fetched_people_found,
            updated_at=_latest_datetime(
                [contacts_updated_at, fetched_updated_at, domain.fetch_updated_at, domain.created_at],
                domain.created_at,
            ),
        )

    def _company_status(self, fetch_status: str | None, contacts_found: int) -> str:
        if fetch_status in {"queued", "running"}:
            return "running"
        if fetch_status == "failed":
            return "failed"
        if fetch_status == "succeeded":
            return "done" if contacts_found > 0 else "no_match"
        return "pending"

    def _validate_mode_for_domains(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domains: list[UploadedDomain],
        mode: str,
    ) -> None:
        if mode not in {"fetch", "refetch"}:
            raise EmailFetchServiceError("invalid_fetch_mode", "Email fetch mode must be 'fetch' or 'refetch'.")

        stats = self._contact_stats_by_domain(
            session=session,
            campaign_id=campaign_id,
            domain_ids=[domain.id for domain in domains],
        )
        allowed = {"pending", "failed"} if mode == "fetch" else {"done", "no_match", "failed"}
        invalid: list[str] = []
        for domain in domains:
            contacts_found = (stats.get(domain.id) or (0, 0, None))[0]
            status = self._company_status(domain.fetch_status, contacts_found)
            if status not in allowed:
                invalid.append(f"{domain.domain} ({status})")

        if invalid:
            action = "fetched" if mode == "fetch" else "refetched"
            raise EmailFetchServiceError(
                "domain_not_fetchable",
                f"Selected companies cannot be {action} in this state: {', '.join(invalid[:5])}.",
            )

    def _company_counts(self, rows: list[EmailFetchCompanyRowView]) -> EmailFetchCompanyCountsView:
        counts = {
            "pending": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
            "no_match": 0,
        }
        contacts_found = 0
        emails_found = 0
        fetched_people_found = 0
        for row in rows:
            if row.status in counts:
                counts[row.status] += 1
            contacts_found += row.contacts_found
            emails_found += row.emails_found
            fetched_people_found += row.fetched_people_found
        return EmailFetchCompanyCountsView(
            all=len(rows),
            pending=counts["pending"],
            running=counts["running"],
            done=counts["done"],
            failed=counts["failed"],
            no_match=counts["no_match"],
            contacts_found=contacts_found,
            emails_found=emails_found,
            fetched_people_found=fetched_people_found,
        )

    def _resolve_domains(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        domain_ids: list[UUID],
    ) -> list[UploadedDomain]:
        if session.get(Campaign, campaign_id) is None:
            raise EmailFetchServiceError("campaign_not_found", "Campaign not found.")
        unique_ids = list(dict.fromkeys(domain_ids))
        if not unique_ids:
            raise EmailFetchServiceError("no_domains", "Select at least one company.")
        if len(unique_ids) > MAX_DOMAINS_PER_BATCH:
            raise EmailFetchServiceError("too_many_domains", "A single email fetch batch supports at most 200 companies.")
        domains = list(
            session.exec(
                select(UploadedDomain)
                .where(
                    col(UploadedDomain.campaign_id) == campaign_id,
                    col(UploadedDomain.id).in_(unique_ids),
                )
                .order_by(col(UploadedDomain.domain))
            )
        )
        if len(domains) != len(unique_ids):
            raise EmailFetchServiceError("domain_not_found", "One or more selected companies were not found in the campaign.")
        return domains

    def _rank_candidates(self, candidates: list[ProviderCandidate]) -> list[ProviderCandidate]:
        return sorted(
            candidates,
            key=lambda candidate: (
                0 if candidate.linkedin_url else 1,
                candidate.title.lower(),
                candidate.last_name.lower(),
                candidate.first_name.lower(),
                candidate.provider_person_id,
            ),
        )

    def _with_default_target(self, criteria: EmailFetchCriteria) -> EmailFetchCriteria:
        if criteria.target_contacts_per_company == self.target_contacts_per_company:
            return criteria
        return EmailFetchCriteria(
            include_titles=criteria.include_titles,
            exclude_titles=criteria.exclude_titles,
            target_contacts_per_company=self.target_contacts_per_company,
            provider_order=criteria.normalized_provider_order(),
        )

    def _credit_plan(
        self,
        *,
        criteria: EmailFetchCriteria,
        selected_domain_count: int,
        estimated_apollo_reveals: int,
        estimated_snov_email_lookups: int,
    ) -> dict[str, Any]:
        title_hint_count = len(provider_title_hints(criteria))
        snov_chunks = self._snov_title_chunks_per_company(criteria)
        return {
            "apollo_preview_is_free": True,
            "title_hint_count": title_hint_count,
            "snov_positions_per_search": SNOV_POSITIONS_PER_SEARCH,
            "snov_title_chunks_per_company": snov_chunks,
            "estimated_apollo_reveals": estimated_apollo_reveals,
            "estimated_snov_discovery_searches": selected_domain_count * snov_chunks,
            "estimated_snov_email_lookups": estimated_snov_email_lookups,
        }

    def _snov_title_chunks_per_company(self, criteria: EmailFetchCriteria) -> int:
        hint_count = len(provider_title_hints(criteria))
        if hint_count == 0:
            return 0
        chunks = (hint_count + SNOV_POSITIONS_PER_SEARCH - 1) // SNOV_POSITIONS_PER_SEARCH
        return min(chunks, MAX_SNOV_TITLE_HINT_CHUNKS_PER_DOMAIN)

    def _provider_for(self, provider: str) -> EmailFetchProvider:
        if provider == "apollo":
            return self.apollo_provider
        if provider == "snov":
            return self.snov_provider
        raise EmailFetchServiceError("unknown_provider", f"Unknown email fetch provider: {provider}")

    def _company_outcome(
        self,
        *,
        usable_count: int,
        matched_count: int,
        provider_errors: list[str],
        target: int,
        attempted_provider_count: int,
    ) -> str:
        if usable_count >= target:
            return "email_success"
        if usable_count > 0 and provider_errors:
            return "partial_success"
        if usable_count > 0:
            return "underfilled"
        if matched_count > 0:
            return "contacts_no_email"
        if len(provider_errors) >= attempted_provider_count:
            return "provider_failed"
        return "no_matches"

    def _outcome_dict(self, outcome: CompanyFetchOutcome) -> dict[str, Any]:
        return {
            "domain_id": str(outcome.domain_id),
            "domain": outcome.domain,
            "outcome": outcome.outcome,
            "usable_email_count": outcome.usable_email_count,
            "matched_candidate_count": outcome.matched_candidate_count,
            "provider_errors": outcome.provider_errors,
            "stored_contact_ids": outcome.stored_contact_ids,
        }

    def _batch_warnings(self, outcomes: list[CompanyFetchOutcome]) -> list[str]:
        warnings: list[str] = []
        if any(outcome.outcome == "underfilled" for outcome in outcomes):
            warnings.append("some_companies_underfilled")
        if any(outcome.outcome == "provider_failed" for outcome in outcomes):
            warnings.append("some_companies_provider_failed")
        if any(outcome.outcome == "no_matches" for outcome in outcomes):
            warnings.append("some_companies_no_matches")
        return warnings

    def _batch_view(self, batch: EmailFetchBatch) -> EmailFetchBatchView:
        return EmailFetchBatchView(
            id=batch.id,
            campaign_id=batch.campaign_id,
            state=batch.state,
            selected_domain_count=batch.selected_domain_count,
            queued_count=batch.queued_count,
            success_count=batch.success_count,
            failed_count=batch.failed_count,
            criteria_hash=batch.criteria_hash,
            criteria_snapshot=batch.criteria_snapshot_json,
            provider_order=list(batch.provider_order_json or []),
            result_summary=batch.result_summary_json,
            created_at=batch.created_at,
            finished_at=batch.finished_at,
        )
