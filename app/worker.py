from __future__ import annotations

import asyncio
import logging
import multiprocessing
import signal
import time
import traceback
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.logging import configure_logging, log_event
from app.db.session import engine
from app.models import AnalysisJob, ScrapeJob
from app.models.pipeline import AnalysisJobState
from app.services.analysis_service import AnalysisService
from app.services.artifact_cleanup_service import ArtifactCleanupService
from app.services.queue_service import QueueService, QueueTask
from app.services.scrape_service import ScrapeService


logger = logging.getLogger(__name__)


def _redact_url(url: str) -> str:
    """Return the URL with any password replaced by '***'."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:  # noqa: BLE001
        pass
    return url


class Worker:
    def __init__(self, *, cleanup_enabled: bool = True) -> None:
        self._running = True
        self._queue = QueueService()
        self._scrape_service = ScrapeService()
        self._analysis_service = AnalysisService()
        self._cleanup_service = ArtifactCleanupService()
        self._last_cleanup_at = 0.0
        self._cleanup_enabled = cleanup_enabled

    def stop(self, *_: object) -> None:
        self._running = False

    def run(self) -> int:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        log_event(
            logger,
            "worker_started",
            queue_key=self._queue.queue_key,
            redis_url=_redact_url(settings.redis_url),
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
        if not self._cleanup_enabled:
            return
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
                payload=task.payload,
                error=str(exc),
                traceback=traceback.format_exc(),
            )

    def _run_step1(self, task: QueueTask) -> None:
        job_id = self._payload_job_id(task)
        if not job_id:
            return
        with Session(engine) as session:
            if not session.get(ScrapeJob, job_id):
                log_event(logger, "worker_job_missing", task_id=task.task_id, job_id=str(job_id))
                return
        # Session closed before the long async I/O; run_step1 manages its own sessions.
        asyncio.run(self._scrape_service.run_step1(engine=engine, job_id=job_id))
        log_event(logger, "worker_step1_done", task_id=task.task_id, job_id=str(job_id))

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
        # Session closed before the long sync I/O; run_step2 manages its own sessions.
        self._scrape_service.run_step2(engine=engine, job_id=job_id)
        log_event(logger, "worker_step2_done", task_id=task.task_id, job_id=str(job_id))

    def _run_all(self, task: QueueTask) -> None:
        job_id = self._payload_job_id(task)
        if not job_id:
            return
        with Session(engine) as session:
            if not session.get(ScrapeJob, job_id):
                log_event(logger, "worker_job_missing", task_id=task.task_id, job_id=str(job_id))
                return
        asyncio.run(self._scrape_service.run_step1(engine=engine, job_id=job_id))
        # Check step1 result before proceeding.
        with Session(engine) as session:
            job = session.get(ScrapeJob, job_id)
            if not job or job.stage1_status != "completed":
                log_event(logger, "worker_run_all_done", task_id=task.task_id, job_id=str(job_id), reason="step1_not_completed")
                return
        self._scrape_service.run_step2(engine=engine, job_id=job_id)
        log_event(logger, "worker_run_all_done", task_id=task.task_id, job_id=str(job_id))

    def _run_analysis_job(self, task: QueueTask) -> None:
        analysis_job_id = self._payload_uuid(task, key="analysis_job_id")
        if not analysis_job_id:
            return
        with Session(engine) as session:
            job = session.get(AnalysisJob, analysis_job_id)
            if not job:
                log_event(logger, "worker_job_missing", task_id=task.task_id, analysis_job_id=str(analysis_job_id))
                return
            result = self._analysis_service.run_analysis_job(session=session, analysis_job_id=analysis_job_id)
            log_event(
                logger,
                "worker_analysis_done",
                task_id=task.task_id,
                analysis_job_id=str(analysis_job_id),
                state=result.state,
                attempt_count=result.attempt_count,
                run_id=str(result.run_id),
            )
            # Re-enqueue if the job failed transiently and has retries remaining.
            if not result.terminal_state:
                # Exponential backoff: 5s, 10s, 20s … capped at 60s.
                delay = min(5 * (2 ** (result.attempt_count - 1)), 60)
                time.sleep(delay)
                self._queue.enqueue(
                    task_type="analysis_job",
                    payload={"analysis_job_id": str(analysis_job_id)},
                )
                log_event(
                    logger,
                    "worker_analysis_requeued",
                    analysis_job_id=str(analysis_job_id),
                    attempt_count=result.attempt_count,
                    max_attempts=result.max_attempts,
                    error_code=result.last_error_code,
                    backoff_sec=delay,
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
    concurrency = max(1, settings.worker_concurrency)
    if concurrency == 1:
        _recover_stuck_jobs(QueueService())
        return Worker().run()
    return WorkerSupervisor(concurrency=concurrency).run()


def _run_worker_process(slot: int, *, cleanup_enabled: bool) -> int:
    configure_logging()
    # Discard any DB connections inherited from the parent process via fork.
    # PostgreSQL sockets cannot be shared across fork boundaries — each child
    # must establish its own connections. close=False avoids closing sockets
    # that the parent process still owns.
    engine.dispose(close=False)
    log_event(logger, "worker_process_started", slot=slot, cleanup_enabled=cleanup_enabled)
    worker = Worker(cleanup_enabled=cleanup_enabled)
    return worker.run()


def _recover_stuck_jobs(queue: QueueService) -> None:
    """Reset jobs left in running states from a previous crashed run and re-enqueue them.

    Safe to call at supervisor startup because at that point all worker processes are
    guaranteed to be dead — no job in a running/queued-but-lost state has a live owner.
    """
    stuck_scrape_statuses = ["running_step1", "running_step2", "step1_completed"]
    scrape_count = 0
    analysis_count = 0

    stuck_scrape_ids: list[str] = []
    with Session(engine) as session:
        stuck_scrape = list(
            session.exec(
                select(ScrapeJob).where(
                    col(ScrapeJob.terminal_state).is_(False)
                    & col(ScrapeJob.status).in_(stuck_scrape_statuses)
                )
            )
        )
        for job in stuck_scrape:
            job.status = "created"
            job.terminal_state = False
            session.add(job)
        # Collect IDs before commit expires the objects
        stuck_scrape_ids = [str(job.id) for job in stuck_scrape]
        session.commit()
        scrape_count = len(stuck_scrape_ids)

    stuck_analysis_ids: list[str] = []
    with Session(engine) as session:
        stuck_analysis = list(
            session.exec(
                select(AnalysisJob).where(
                    col(AnalysisJob.terminal_state).is_(False)
                    & col(AnalysisJob.state).in_([AnalysisJobState.RUNNING, AnalysisJobState.QUEUED])
                )
            )
        )
        for job in stuck_analysis:
            job.state = AnalysisJobState.QUEUED
            job.started_at = None
            session.add(job)
        # Collect IDs before commit expires the objects
        stuck_analysis_ids = [str(job.id) for job in stuck_analysis]
        session.commit()
        analysis_count = len(stuck_analysis_ids)

    for job_id in stuck_scrape_ids:
        queue.enqueue(task_type="scrape_run_all", payload={"job_id": job_id})
    for job_id in stuck_analysis_ids:
        queue.enqueue(task_type="analysis_job", payload={"analysis_job_id": job_id})

    log_event(
        logger,
        "worker_startup_recovery",
        scrape_jobs_recovered=scrape_count,
        analysis_jobs_recovered=analysis_count,
    )


class WorkerSupervisor:
    def __init__(self, *, concurrency: int) -> None:
        self._concurrency = concurrency
        self._running = True
        self._children: dict[int, multiprocessing.Process] = {}
        self._queue = QueueService()

    def stop(self, *_: object) -> None:
        self._running = False

    def run(self) -> int:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        log_event(logger, "worker_supervisor_started", concurrency=self._concurrency)

        _recover_stuck_jobs(self._queue)

        for slot in range(self._concurrency):
            self._spawn(slot)

        while self._running:
            time.sleep(1)
            for slot, process in list(self._children.items()):
                if process.is_alive():
                    continue
                exit_code = process.exitcode
                log_event(logger, "worker_process_exited", slot=slot, exit_code=exit_code)
                if self._running:
                    self._spawn(slot)

        for process in self._children.values():
            if process.is_alive():
                process.terminate()
        for process in self._children.values():
            process.join(timeout=10)
        log_event(logger, "worker_supervisor_stopped")
        return 0

    def _spawn(self, slot: int) -> None:
        cleanup_enabled = slot == 0
        process = multiprocessing.Process(
            target=_run_worker_process,
            args=(slot,),
            kwargs={"cleanup_enabled": cleanup_enabled},
            name=f"worker-{slot}",
        )
        process.start()
        self._children[slot] = process
        log_event(logger, "worker_process_spawned", slot=slot, pid=process.pid, cleanup_enabled=cleanup_enabled)


if __name__ == "__main__":
    raise SystemExit(main())
