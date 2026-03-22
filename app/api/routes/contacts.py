"""Contact fetching endpoints: queue jobs, list contacts, title-match rules."""
from __future__ import annotations

import csv
import io
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.schemas.contacts import (
    ContactFetchResult,
    ContactListResponse,
    ProspectContactRead,
    TitleMatchRuleCreate,
    TitleMatchRuleRead,
    TitleRuleSeedResult,
)
from app.db.session import get_session
from app.models import AnalysisJob, ClassificationResult, Company, ContactFetchJob, ProspectContact, Run, TitleMatchRule
from app.models.pipeline import AnalysisJobState, ContactFetchJobState, PredictedLabel
from app.services.contact_service import seed_title_rules
from app.tasks.contacts import fetch_contacts


router = APIRouter(prefix="/v1", tags=["contacts"])


# ── Helper: bulk create + enqueue ─────────────────────────────────────────────

def _enqueue_contact_fetches(
    *, session: Session, companies: list[Company]
) -> ContactFetchResult:
    if not companies:
        return ContactFetchResult(
            requested_count=0, queued_count=0, already_fetching_count=0, queued_job_ids=[]
        )

    company_ids = [c.id for c in companies]

    # Find companies already with an active (non-terminal) job
    active_company_ids: set[UUID] = set(
        session.exec(
            select(ContactFetchJob.company_id).where(
                col(ContactFetchJob.company_id).in_(company_ids),
                col(ContactFetchJob.terminal_state).is_(False),
            )
        ).all()
    )

    jobs_to_create: list[ContactFetchJob] = []
    for company in companies:
        if company.id in active_company_ids:
            continue
        jobs_to_create.append(ContactFetchJob(company_id=company.id))

    if jobs_to_create:
        session.add_all(jobs_to_create)
        session.commit()

    queued_job_ids: list[UUID] = []
    for job in jobs_to_create:
        if job.id:
            fetch_contacts.delay(str(job.id))
            queued_job_ids.append(job.id)

    return ContactFetchResult(
        requested_count=len(companies),
        queued_count=len(queued_job_ids),
        already_fetching_count=len(active_company_ids),
        queued_job_ids=queued_job_ids,
    )


# ── Single company fetch ───────────────────────────────────────────────────────

@router.post(
    "/companies/{company_id}/fetch-contacts",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_contacts_for_company(
    company_id: UUID,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    return _enqueue_contact_fetches(session=session, companies=[company])


# ── Bulk: all "Possible" in a run ─────────────────────────────────────────────

@router.post(
    "/runs/{run_id}/fetch-contacts",
    response_model=ContactFetchResult,
    status_code=status.HTTP_201_CREATED,
)
def fetch_contacts_for_run(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    # Find all "Possible" companies from this run's analysis jobs
    possible_rows = list(session.exec(
        select(Company)
        .join(AnalysisJob, col(AnalysisJob.company_id) == col(Company.id))
        .join(ClassificationResult, col(ClassificationResult.analysis_job_id) == col(AnalysisJob.id))
        .where(
            col(AnalysisJob.run_id) == run_id,
            col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED,
            col(ClassificationResult.predicted_label) == PredictedLabel.POSSIBLE,
        )
    ).all())

    return _enqueue_contact_fetches(session=session, companies=possible_rows)


# ── List contacts for a company ───────────────────────────────────────────────

@router.get("/companies/{company_id}/contacts", response_model=ContactListResponse)
def list_company_contacts(
    company_id: UUID,
    title_match: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    q = select(ProspectContact).where(col(ProspectContact.company_id) == company_id)
    if title_match is not None:
        q = q.where(col(ProspectContact.title_match) == title_match)

    total = session.exec(select(func.count()).select_from(q.subquery())).one()
    items = list(session.exec(q.order_by(col(ProspectContact.title_match).desc(), col(ProspectContact.created_at).desc()).offset(offset).limit(limit)).all())

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=[ProspectContactRead.model_validate(c, from_attributes=True) for c in items],
    )


# ── Global contacts list ──────────────────────────────────────────────────────

@router.get("/contacts", response_model=ContactListResponse)
def list_all_contacts(
    title_match: bool | None = Query(default=None),
    email_status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactListResponse:
    from sqlalchemy import or_
    from sqlalchemy import func as sa_func

    q = select(ProspectContact, Company.domain).join(
        Company, col(Company.id) == col(ProspectContact.company_id)
    )
    if title_match is not None:
        q = q.where(col(ProspectContact.title_match) == title_match)
    if email_status:
        q = q.where(col(ProspectContact.email_status) == email_status)
    if search:
        term = f"%{search.lower()}%"
        q = q.where(
            or_(
                sa_func.lower(ProspectContact.first_name).like(term),
                sa_func.lower(ProspectContact.last_name).like(term),
                sa_func.lower(ProspectContact.email).like(term),
                sa_func.lower(ProspectContact.title).like(term),
                sa_func.lower(Company.domain).like(term),
            )
        )

    total = session.exec(select(func.count()).select_from(q.subquery())).one()
    rows = list(session.exec(
        q.order_by(col(ProspectContact.title_match).desc(), col(ProspectContact.created_at).desc())
        .offset(offset)
        .limit(limit)
    ).all())

    items = []
    for contact, domain in rows:
        data = {**contact.__dict__, "domain": domain}
        items.append(ProspectContactRead.model_validate(data))

    return ContactListResponse(
        total=total,
        has_more=(offset + len(items)) < total,
        limit=limit,
        offset=offset,
        items=items,
    )


# ── CSV export ────────────────────────────────────────────────────────────────

@router.get("/contacts/export.csv")
def export_contacts_csv(
    title_match: bool | None = Query(default=None),
    email_status: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> Response:
    q = select(ProspectContact, Company.domain).join(
        Company, col(Company.id) == col(ProspectContact.company_id)
    )
    if title_match is not None:
        q = q.where(col(ProspectContact.title_match) == title_match)
    if email_status:
        q = q.where(col(ProspectContact.email_status) == email_status)

    rows = list(session.exec(q.order_by(col(ProspectContact.created_at).desc())).all())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "domain", "first_name", "last_name", "title", "title_match",
        "email", "email_status", "snov_confidence", "linkedin_url",
    ])
    for contact, domain in rows:
        writer.writerow([
            domain,
            contact.first_name,
            contact.last_name,
            contact.title or "",
            contact.title_match,
            contact.email or "",
            contact.email_status,
            contact.snov_confidence or "",
            contact.linkedin_url or "",
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


# ── ZeroBounce placeholder ────────────────────────────────────────────────────

@router.post("/contacts/verify", status_code=501)
def verify_contacts() -> dict:
    raise HTTPException(status_code=501, detail="ZeroBounce email verification not yet implemented.")


# ── Title match rules ─────────────────────────────────────────────────────────

@router.get("/title-match-rules", response_model=list[TitleMatchRuleRead])
def list_title_rules(session: Session = Depends(get_session)) -> list[TitleMatchRuleRead]:
    rules = list(session.exec(select(TitleMatchRule).order_by(col(TitleMatchRule.rule_type), col(TitleMatchRule.created_at))).all())
    return [TitleMatchRuleRead.model_validate(r, from_attributes=True) for r in rules]


@router.post("/title-match-rules", response_model=TitleMatchRuleRead, status_code=status.HTTP_201_CREATED)
def create_title_rule(
    payload: TitleMatchRuleCreate,
    session: Session = Depends(get_session),
) -> TitleMatchRuleRead:
    rule = TitleMatchRule(rule_type=payload.rule_type, keywords=payload.keywords)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return TitleMatchRuleRead.model_validate(rule, from_attributes=True)


@router.delete("/title-match-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_title_rule(
    rule_id: UUID,
    session: Session = Depends(get_session),
) -> None:
    rule = session.get(TitleMatchRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    session.delete(rule)
    session.commit()


@router.post("/title-match-rules/seed", response_model=TitleRuleSeedResult)
def seed_rules(session: Session = Depends(get_session)) -> TitleRuleSeedResult:
    """Idempotent: insert default title match rules, skipping any already present."""
    inserted = seed_title_rules(session)
    return TitleRuleSeedResult(
        inserted=inserted,
        message=f"Inserted {inserted} new rules (duplicates skipped).",
    )
