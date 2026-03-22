from __future__ import annotations

import socket
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

app = Celery("prospect")
app.autodiscover_tasks(["app.tasks.scrape", "app.tasks.analysis", "app.tasks.beat", "app.tasks.contacts"])

app.conf.update(
    broker_url=settings.redis_url,
    broker_connection_retry_on_startup=True,
    # Keep the broker connection alive so Redis doesn't close it after its
    # idle timeout (typically 10 min).  Without this, Celery cancels any
    # in-flight tasks on disconnect and redelivers them on reconnect, causing
    # jobs to be killed and restarted every 10 minutes when the queue is quiet.
    broker_transport_options={
        "socket_keepalive": True,
        "socket_keepalive_options": {
            socket.TCP_KEEPIDLE: 60,   # start probing after 60 s of silence
            socket.TCP_KEEPINTVL: 10,  # probe every 10 s
            socket.TCP_KEEPCNT: 3,     # declare dead after 3 failed probes
        },
        # Send a Redis PING on any connection idle for this many seconds.
        # This resets the Redis server's own idle-timeout clock (typically
        # 600 s on managed Redis), which TCP keepalive alone cannot do.
        "health_check_interval": 25,
    },
    # Celery consumer heartbeat — keeps the consumer socket active between
    # task arrivals so Redis server never sees it as idle for > 25 s.
    broker_heartbeat=10,
    # No result backend — job state lives in the DB, not Celery results.
    result_backend=None,
    # ACK only after the task function returns so a crashed worker causes
    # automatic redelivery rather than silent message loss.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Cancel in-flight tasks on broker disconnect so they are redelivered cleanly
    # rather than silently continuing with no broker connection.
    worker_cancel_long_running_tasks_on_connection_loss=True,
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
        "app.tasks.contacts.fetch_contacts": {"queue": "contacts"},
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
