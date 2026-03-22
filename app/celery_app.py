from __future__ import annotations

import socket
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

app = Celery("prospect")
app.autodiscover_tasks(["app.tasks.scrape", "app.tasks.analysis", "app.tasks.beat", "app.tasks.contacts"])

# Build TCP keepalive options conditionally — TCP_KEEPIDLE is Linux-only;
# macOS/BSD uses TCP_KEEPALIVE instead.
_keepalive_opts: dict[int, int] = {}
_idle_const = getattr(socket, "TCP_KEEPIDLE", None) or getattr(socket, "TCP_KEEPALIVE", None)
if _idle_const is not None:
    _keepalive_opts[_idle_const] = 60       # start probing after 60 s of silence
_intvl_const = getattr(socket, "TCP_KEEPINTVL", None)
if _intvl_const is not None:
    _keepalive_opts[_intvl_const] = 10      # probe every 10 s
_cnt_const = getattr(socket, "TCP_KEEPCNT", None)
if _cnt_const is not None:
    _keepalive_opts[_cnt_const] = 3         # declare dead after 3 failed probes

app.conf.update(
    broker_url=settings.redis_url,
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=None,  # retry forever on disconnect
    broker_transport_options={
        "socket_keepalive": True,
        "socket_keepalive_options": _keepalive_opts,
        # Send a Redis PING on any connection idle for this many seconds.
        # Resets the Redis server's application-level idle-timeout clock
        # (typically 600 s on managed Redis), which TCP keepalive cannot do.
        "health_check_interval": 15,
        "socket_connect_timeout": 10,
        # No socket_timeout — the consumer socket sits idle during long tasks
        # (up to 31 min); a hard 30s timeout kills it mid-run.  TCP keepalive
        # + health_check_interval=15 keep the connection alive instead.
        "retry_on_timeout": True,
        # Must exceed the longest task hard time limit (31 min = 1860 s).
        # Prevents Redis from redelivering a message while its worker is
        # still executing.
        "visibility_timeout": 7200,
    },
    # Celery consumer heartbeat — keeps the consumer socket active between
    # task arrivals so Redis server never sees it as idle.
    broker_heartbeat=10,
    # No result backend — job state lives in the DB, not Celery results.
    result_backend=None,
    # ACK only after the task function returns so a crashed worker causes
    # automatic redelivery rather than silent message loss.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Let running tasks finish on broker disconnect.  CAS locks protect
    # against duplicate execution if the same message is redelivered after
    # reconnect, so cancelling in-flight work is unnecessary and destructive.
    worker_cancel_long_running_tasks_on_connection_loss=False,
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
