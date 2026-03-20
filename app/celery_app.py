from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

app = Celery("prospect")
app.autodiscover_tasks(["app.tasks.scrape", "app.tasks.analysis", "app.tasks.beat"])

app.conf.update(
    broker_url=settings.redis_url,
    broker_connection_retry_on_startup=True,
    # No result backend — job state lives in the DB, not Celery results.
    result_backend=None,
    # ACK only after the task function returns so a crashed worker causes
    # automatic redelivery rather than silent message loss.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # One task at a time per worker process — prevents head-of-line blocking
    # where a slow task starves everything behind it.
    worker_prefetch_multiplier=1,
    # Hard time limits per task.  Scrape tasks can legitimately take up to
    # 20 min; 30 min soft + 31 min hard gives a clean signal before the kill.
    task_soft_time_limit=1800,   # 30 min → raises SoftTimeLimitExceeded
    task_time_limit=1860,        # 31 min → SIGKILL
    # Route tasks to purpose-specific queues.
    task_routes={
        "app.tasks.scrape.scrape_website": {"queue": "scrape"},
        "app.tasks.analysis.run_analysis_job": {"queue": "analysis"},
        "app.tasks.beat.reconcile_stuck_jobs": {"queue": "beat"},
    },
    # Celery Beat periodic schedule.
    beat_schedule={
        "reconcile-stuck-jobs": {
            "task": "app.tasks.beat.reconcile_stuck_jobs",
            "schedule": crontab(minute="*/30"),
        },
    },
    timezone="UTC",
    enable_utc=True,
)
