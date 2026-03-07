from __future__ import annotations

import asyncio
import logging
import signal
import time
from uuid import UUID

from sqlmodel import Session

from app.core.config import settings
from app.core.logging import configure_logging, log_event
from app.db.session import engine
from app.models import AnalysisJob, ScrapeJob
from app.services.analysis_service import AnalysisService
from app.services.artifact_cleanup_service import ArtifactCleanupService
from app.services.queue_service import QueueService, QueueTask
from app.services.scrape_service import ScrapeService


logger = logging.getLogger(__name__)


class Worker:
    def __init__(self) -> None:
        self._running = True
        self._queue = QueueService()
        self._scrape_service = ScrapeService()
        self._analysis_service = AnalysisService()
        self._cleanup_service = ArtifactCleanupService()
        self._last_cleanup_at = 0.0

    def stop(self, *_: object) -> None:
        self._running = False

    def run(self) -> int:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        log_event(
            logger,
            "worker_started",
            queue_key=self._queue.queue_key,
            redis_url=settings.redis_url,
        )
        while self._running:
            self._maybe_cleanup()
            try:
                task = self._queue.pop(timeout_sec=settings.worker_block_timeout_sec)
            except Exception as exc:  # noqa: BLE001
                log_event(logger, "worker_queue_error", error=str(exc))
                time.sleep(2)
                continue
            if task is None:
                continue
            self._handle_task(task)
        log_event(logger, "worker_stopped")
        return 0

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup_at < settings.worker_cleanup_interval_sec:
            return
        self._last_cleanup_at = now
        try:
            with Session(engine) as session:
                stats = self._cleanup_service.cleanup_expired_artifacts(
                    session=session,
                    ttl_hours=settings.upload_file_ttl_hours,
                )
            log_event(
                logger,
                "worker_artifact_cleanup_done",
                pages_scanned=stats.pages_scanned,
                html_snapshots_cleared=stats.html_snapshots_cleared,
                screenshot_files_deleted=stats.screenshot_files_deleted,
                delete_failures=stats.delete_failures,
                ttl_hours=settings.upload_file_ttl_hours,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "worker_artifact_cleanup_failed", error=str(exc))

    def _handle_task(self, task: QueueTask) -> None:
        try:
            if task.task_type == "scrape_step1":
                self._run_step1(task)
            elif task.task_type == "scrape_step2":
                self._run_step2(task)
            elif task.task_type == "scrape_run_all":
                self._run_all(task)
            elif task.task_type == "analysis_job":
                self._run_analysis_job(task)
            else:
                log_event(logger, "worker_task_unknown", task_id=task.task_id, task_type=task.task_type)
        except Exception as exc:  # noqa: BLE001
            log_event(
                logger,
                "worker_task_failed",
                task_id=task.task_id,
                task_type=task.task_type,
                error=str(exc),
            )

    def _run_step1(self, task: QueueTask) -> None:
        job_id = self._payload_job_id(task)
        if not job_id:
            return
        with Session(engine) as session:
            job = session.get(ScrapeJob, job_id)
            if not job:
                log_event(logger, "worker_job_missing", task_id=task.task_id, job_id=str(job_id))
                return
            asyncio.run(self._scrape_service.run_step1(session=session, job=job))
            log_event(logger, "worker_step1_done", task_id=task.task_id, job_id=str(job_id), status=job.status)

    def _run_step2(self, task: QueueTask) -> None:
        job_id = self._payload_job_id(task)
        if not job_id:
            return
        with Session(engine) as session:
            job = session.get(ScrapeJob, job_id)
            if not job:
                log_event(logger, "worker_job_missing", task_id=task.task_id, job_id=str(job_id))
                return
            if job.stage1_status != "completed":
                log_event(
                    logger,
                    "worker_step2_skipped",
                    task_id=task.task_id,
                    job_id=str(job_id),
                    reason="step1_not_completed",
                )
                return
            self._scrape_service.run_step2(session=session, job=job)
            log_event(logger, "worker_step2_done", task_id=task.task_id, job_id=str(job_id), status=job.status)

    def _run_all(self, task: QueueTask) -> None:
        job_id = self._payload_job_id(task)
        if not job_id:
            return
        with Session(engine) as session:
            job = session.get(ScrapeJob, job_id)
            if not job:
                log_event(logger, "worker_job_missing", task_id=task.task_id, job_id=str(job_id))
                return
            asyncio.run(self._scrape_service.run_step1(session=session, job=job))
            if job.stage1_status == "completed":
                self._scrape_service.run_step2(session=session, job=job)
            log_event(logger, "worker_run_all_done", task_id=task.task_id, job_id=str(job_id), status=job.status)

    def _run_analysis_job(self, task: QueueTask) -> None:
        analysis_job_id = self._payload_uuid(task, key="analysis_job_id")
        if not analysis_job_id:
            return
        with Session(engine) as session:
            job = session.get(AnalysisJob, analysis_job_id)
            if not job:
                log_event(logger, "worker_job_missing", task_id=task.task_id, analysis_job_id=str(analysis_job_id))
                return
            self._analysis_service.run_analysis_job(session=session, analysis_job_id=analysis_job_id)
            log_event(
                logger,
                "worker_analysis_done",
                task_id=task.task_id,
                analysis_job_id=str(analysis_job_id),
                state=job.state,
                run_id=str(job.run_id),
            )

    def _payload_job_id(self, task: QueueTask) -> UUID | None:
        return self._payload_uuid(task, key="job_id")

    def _payload_uuid(self, task: QueueTask, *, key: str) -> UUID | None:
        raw = task.payload.get(key, "")
        try:
            return UUID(raw)
        except Exception:  # noqa: BLE001
            log_event(logger, "worker_bad_payload", task_id=task.task_id, task_type=task.task_type, payload=task.payload)
            return None


def main() -> int:
    configure_logging()
    worker = Worker()
    return worker.run()


if __name__ == "__main__":
    raise SystemExit(main())
