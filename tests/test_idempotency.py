"""Duplicate delivery idempotency test.

test_duplicate_delivery_idempotent — same analysis_job_id delivered twice;
                                     only one ClassificationResult row persists.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session, col, select

from app.models.pipeline import (
    AnalysisJob,
    AnalysisJobState,
    ClassificationResult,
    Company,
    CrawlArtifact,
    CrawlJob,
    CrawlJobState,
    Prompt,
    Run,
    Upload,
    utcnow,
)


def _build_analysis_job(session: Session) -> AnalysisJob:
    """Create the full object graph needed for one AnalysisJob."""
    upload = Upload(filename="dup-test.csv", checksum="ck-dup", valid_count=1, invalid_count=0)
    session.add(upload)
    session.flush()

    prompt = Prompt(name="dup-prompt", prompt_text="classify", enabled=True)
    session.add(prompt)
    session.flush()

    company = Company(
        upload_id=upload.id,
        raw_url="https://dup-test.com",
        normalized_url="https://dup-test.com",
        domain="dup-test.com",
    )
    session.add(company)
    session.flush()

    crawl_job = CrawlJob(
        company_id=company.id,
        state=CrawlJobState.SUCCEEDED,
        terminal_state=True,
    )
    session.add(crawl_job)
    session.flush()

    artifact = CrawlArtifact(
        crawl_job_id=crawl_job.id,
        company_id=company.id,
    )
    session.add(artifact)
    session.flush()

    run = Run(
        upload_id=upload.id,
        prompt_id=prompt.id,
        general_model="test",
        classify_model="test",
        status="running",
        total_jobs=1,
        completed_jobs=0,
        failed_jobs=0,
        started_at=utcnow(),
    )
    session.add(run)
    session.flush()

    analysis_job = AnalysisJob(
        run_id=run.id,
        upload_id=upload.id,
        company_id=company.id,
        crawl_artifact_id=artifact.id,
        state=AnalysisJobState.QUEUED,
        terminal_state=False,
        attempt_count=0,
        max_attempts=3,
        prompt_hash="abc123",
    )
    session.add(analysis_job)
    session.commit()
    session.refresh(analysis_job)
    return analysis_job


class TestDuplicateDeliveryIdempotent:
    """CAS ensures only one worker writes a ClassificationResult even if the
    same analysis_job_id is delivered twice to the stream.
    """

    def test_only_one_result_written(self, session: Session, db_engine):
        from datetime import timedelta
        from sqlalchemy import update as sa_update

        analysis_job = _build_analysis_job(session)
        job_id = analysis_job.id

        # Simulate first delivery: claim job with a lock token.
        lock_token_1 = str(uuid4())
        now = utcnow()
        with Session(db_engine) as s:
            s.execute(
                sa_update(AnalysisJob)
                .where(
                    AnalysisJob.id == job_id,
                    col(AnalysisJob.terminal_state).is_(False),
                    col(AnalysisJob.state).in_([AnalysisJobState.QUEUED, AnalysisJobState.RUNNING]),
                    (col(AnalysisJob.lock_token).is_(None) | (col(AnalysisJob.lock_expires_at) < now)),
                )
                .values(
                    state=AnalysisJobState.RUNNING,
                    lock_token=lock_token_1,
                    lock_expires_at=now + timedelta(minutes=15),
                    attempt_count=AnalysisJob.attempt_count + 1,
                )
                .execution_options(synchronize_session=False)
            )
            s.commit()

        # Simulate second delivery (duplicate): CAS should fail.
        lock_token_2 = str(uuid4())
        with Session(db_engine) as s:
            result = s.execute(
                sa_update(AnalysisJob)
                .where(
                    AnalysisJob.id == job_id,
                    col(AnalysisJob.terminal_state).is_(False),
                    col(AnalysisJob.state).in_([AnalysisJobState.QUEUED, AnalysisJobState.RUNNING]),
                    (col(AnalysisJob.lock_token).is_(None) | (col(AnalysisJob.lock_expires_at) < now)),
                )
                .values(
                    state=AnalysisJobState.RUNNING,
                    lock_token=lock_token_2,
                    lock_expires_at=now + timedelta(minutes=15),
                    attempt_count=AnalysisJob.attempt_count + 1,
                )
                .execution_options(synchronize_session=False)
            )
            s.commit()
            assert result.rowcount == 0, "Duplicate CAS should not claim the job"

        # First worker writes the result.
        with Session(db_engine) as s:
            job = s.get(AnalysisJob, job_id)
            assert job is not None
            assert job.lock_token == lock_token_1  # first worker still owns it

            result_row = ClassificationResult(
                analysis_job_id=job_id,
                predicted_label="possible",
                confidence=0.9,
                reasoning_json={"reason": "looks good"},
                evidence_json=[],
            )
            s.add(result_row)
            job.state = AnalysisJobState.SUCCEEDED
            job.terminal_state = True
            s.add(job)
            s.commit()

        # Exactly one ClassificationResult should exist.
        session.expire_all()
        results = session.exec(
            select(ClassificationResult).where(col(ClassificationResult.analysis_job_id) == job_id)
        ).all()
        assert len(results) == 1
        assert str(results[0].predicted_label) == "possible"
