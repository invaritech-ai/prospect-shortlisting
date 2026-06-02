from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, bindparam, func, text
from sqlmodel import Session, col, select

from app.api.schemas.scrape import LetterCountsResponse
from app.api.schemas.analysis import (
    AiReviewDomainAnalysis,
    AiReviewDomainList,
    AiReviewDomainRow,
    AiReviewJobCreate,
    AiReviewJobRead,
    AiReviewJobStatusRead,
    AiReviewLabelCounts,
)
from app.db.session import get_engine, get_session
from app.models.classification import ClassificationBatch, ClassificationResult, DecisionSettings
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeResult
from app.services.queue_guard import is_procrastinate_schema_ready

router = APIRouter(prefix="/v1", tags=["analysis"])

_ACTIVE_CLASSIFICATION_STATES = {"queued", "running"}


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
        .cte("latest_classification")
        .prefix_with("MATERIALIZED", dialect="postgresql")
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


def _job_read(batch: ClassificationBatch) -> AiReviewJobRead:
    return AiReviewJobRead(
        id=batch.id,
        campaign_id=batch.campaign_id,
        state=batch.state,
        selected_domain_count=batch.selected_domain_count,
        queued_count=batch.queued_count,
        success_count=batch.success_count,
        failed_count=batch.failed_count,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )


async def _enqueue_ai_review_results(result_ids: list[UUID]) -> None:
    from app.jobs.ai_decision import classify_domain

    for result_id in result_ids:
        await classify_domain.defer_async(result_id=str(result_id))


def _active_settings(session: Session, campaign_id: UUID) -> DecisionSettings | None:
    return session.exec(
        select(DecisionSettings)
        .where(
            col(DecisionSettings.campaign_id) == campaign_id,
            col(DecisionSettings.is_active).is_(True),
        )
        .order_by(col(DecisionSettings.created_at).desc())
        .limit(1)
    ).first()


def _latest_successful_scrapes(session: Session, campaign_id: UUID, domain_ids: list[UUID]) -> dict[UUID, ScrapeResult]:
    if not domain_ids:
        return {}
    latest_sq = (
        select(
            col(ScrapeResult.domain_id).label("domain_id"),
            func.max(col(ScrapeResult.created_at)).label("latest_created_at"),
        )
        .where(
            col(ScrapeResult.campaign_id) == campaign_id,
            col(ScrapeResult.domain_id).in_(domain_ids),
            col(ScrapeResult.state) == "succeeded",
        )
        .group_by(col(ScrapeResult.domain_id))
        .subquery()
    )
    rows = session.exec(
        select(ScrapeResult)
        .join(
            latest_sq,
            and_(
                col(ScrapeResult.domain_id) == latest_sq.c.domain_id,
                col(ScrapeResult.created_at) == latest_sq.c.latest_created_at,
            ),
        )
        .where(col(ScrapeResult.campaign_id) == campaign_id)
    ).all()
    return {row.domain_id: row for row in rows if row.scraped_pages_json}


def _latest_classification_states(session: Session, campaign_id: UUID, domain_ids: list[UUID]) -> dict[UUID, str | None]:
    if not domain_ids:
        return {}
    latest_sq = (
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
    rows = session.exec(
        select(col(ClassificationResult.domain_id), col(ClassificationResult.state))
        .join(
            latest_sq,
            and_(
                col(ClassificationResult.domain_id) == latest_sq.c.domain_id,
                col(ClassificationResult.created_at) == latest_sq.c.latest_created_at,
            ),
        )
        .where(col(ClassificationResult.campaign_id) == campaign_id)
    ).all()
    return {domain_id: state for domain_id, state in rows}


def _resolve_ai_review_domains(session: Session, body: AiReviewJobCreate) -> list[UploadedDomain]:
    if body.domain_ids:
        q = select(UploadedDomain).where(
            col(UploadedDomain.campaign_id) == body.campaign_id,
            col(UploadedDomain.id).in_(body.domain_ids),
            col(UploadedDomain.scrape_status) == "succeeded",
        )
    else:
        q, effective_label_expr = _classification_joined_query(body.campaign_id)
        q = _apply_letter_filter(q, body.letter)
        q = _apply_search_filter(q, body.search)
        q = _apply_label_filter(q, effective_label_expr, body.label)
        rows = session.exec(q).all()
        domains_by_id = {row[0].id: row[0] for row in rows}
        return list(domains_by_id.values())
    return list(session.exec(q).all())


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


@router.post("/ai-review/jobs", response_model=AiReviewJobRead, status_code=201)
async def create_ai_review_job(
    body: AiReviewJobCreate,
    session: Session = Depends(get_session),
) -> AiReviewJobRead:
    if not is_procrastinate_schema_ready(get_engine()):
        raise HTTPException(
            status_code=503,
            detail=(
                "Queue schema is not initialized. Run "
                "`uv run python scripts/apply_procrastinate_schema_maybe.py` "
                "and start the AI decision worker."
            ),
        )

    settings = _active_settings(session, body.campaign_id)
    if settings is None or not (settings.instruction_text or "").strip():
        raise HTTPException(status_code=422, detail="Active AI decision prompt is required.")

    domains = _resolve_ai_review_domains(session, body)
    domain_ids = [domain.id for domain in domains]
    scrape_by_domain = _latest_successful_scrapes(session, body.campaign_id, domain_ids)
    live_states = _latest_classification_states(session, body.campaign_id, domain_ids)

    eligible = [
        domain for domain in domains
        if domain.id in scrape_by_domain
        and (live_states.get(domain.id) not in _ACTIVE_CLASSIFICATION_STATES)
    ]
    if not eligible:
        raise HTTPException(status_code=400, detail="No eligible scraped domains found.")

    settings_snapshot = {
        "instruction_text": settings.instruction_text.strip(),
        "model": settings.model,
    }
    batch = ClassificationBatch(
        campaign_id=body.campaign_id,
        decision_settings_id=settings.id,
        settings_snapshot_json=settings_snapshot,
        settings_hash=settings.settings_hash,
        state="queued",
        selected_domain_count=len(eligible),
    )
    session.add(batch)
    session.flush()

    results = [
        ClassificationResult(
            campaign_id=body.campaign_id,
            domain_id=domain.id,
            scrape_result_id=scrape_by_domain[domain.id].id,
            classification_batch_id=batch.id,
            state="queued",
            settings_hash=settings.settings_hash,
        )
        for domain in eligible
    ]
    session.add_all(results)
    session.commit()
    session.refresh(batch)

    result_ids = [result.id for result in results]
    await _enqueue_ai_review_results(result_ids)
    batch.queued_count = len(result_ids)
    batch.state = "running"
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return _job_read(batch)


def _queue_counts_for_classification_results(session: Session, result_ids: list[UUID]) -> dict[str, int]:
    if not result_ids or session.get_bind().dialect.name != "postgresql":
        return {}
    stmt = (
        text(
            """
            select status::text, count(*)
            from procrastinate_jobs
            where task_name = 'classify_domain'
              and args->>'result_id' in :result_ids
            group by status::text
            """
        ).bindparams(bindparam("result_ids", expanding=True))
    )
    rows = session.execute(stmt, {"result_ids": [str(rid) for rid in result_ids]}).all()
    return {str(status): int(count) for status, count in rows}


def _build_ai_review_job_status(session: Session, batch_id: UUID) -> AiReviewJobStatusRead | None:
    batch = session.get(ClassificationBatch, batch_id)
    if batch is None:
        return None
    state_rows = session.exec(
        select(col(ClassificationResult.state), func.count(ClassificationResult.id))
        .where(col(ClassificationResult.classification_batch_id) == batch_id)
        .group_by(col(ClassificationResult.state))
    ).all()
    by_state = {str(state): int(count) for state, count in state_rows}
    result_ids = list(
        session.exec(
            select(col(ClassificationResult.id)).where(
                col(ClassificationResult.classification_batch_id) == batch_id
            )
        ).all()
    )
    queue_counts = _queue_counts_for_classification_results(session, result_ids)
    selected = len(result_ids)
    queued = by_state.get("queued", 0)
    running = by_state.get("running", 0)
    succeeded = by_state.get("succeeded", 0)
    failed = by_state.get("failed", 0)
    terminal = succeeded + failed
    state = "completed" if selected > 0 and terminal >= selected else ("running" if selected else batch.state)
    return AiReviewJobStatusRead(
        batch_id=batch.id,
        campaign_id=batch.campaign_id,
        state=state,
        selected=selected,
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        terminal=terminal,
        queue_todo=queue_counts.get("todo", 0),
        queue_doing=queue_counts.get("doing", 0),
        queue_succeeded=queue_counts.get("succeeded", 0),
        queue_failed=queue_counts.get("failed", 0),
        queue_cancelled=queue_counts.get("cancelled", 0),
        queue_aborting=queue_counts.get("aborting", 0),
        queue_aborted=queue_counts.get("aborted", 0),
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )


@router.get("/ai-review/jobs/active", response_model=AiReviewJobRead | None)
def get_active_ai_review_job(
    campaign_id: UUID = Query(...),
    session: Session = Depends(get_session),
) -> AiReviewJobRead | None:
    batch = session.exec(
        select(ClassificationBatch)
        .where(
            col(ClassificationBatch.campaign_id) == campaign_id,
            col(ClassificationBatch.state).in_(["queued", "running"]),
        )
        .order_by(col(ClassificationBatch.created_at).desc())
        .limit(1)
    ).first()
    if batch is None:
        return None
    return _job_read(batch)


@router.get("/ai-review/jobs/{batch_id}/status", response_model=AiReviewJobStatusRead)
def get_ai_review_job_status(
    batch_id: UUID,
    session: Session = Depends(get_session),
) -> AiReviewJobStatusRead:
    status = _build_ai_review_job_status(session, batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="AI review job not found.")
    return status


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
