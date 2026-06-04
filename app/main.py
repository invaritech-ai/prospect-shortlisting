from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analysis import router as analysis_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.contacts import router as contacts_router
from app.api.routes.email_fetch import router as email_fetch_router
from app.api.routes.email_verification import router as email_verification_router
from app.api.routes.events import router as events_router
from app.api.routes.companies import router as companies_router
from app.api.routes.pipeline_runs import router as pipeline_runs_router
from app.api.routes.prompts import router as prompts_router
from app.api.routes.queue_history import router as queue_history_router
from app.api.routes.scrape_jobs import router as scrape_jobs_router
from app.api.routes.scrape_runs import router as scrape_runs_router
from app.api.routes.scrape_prompts import router as scrape_prompts_router
from app.api.routes.settings import router as settings_router
from app.api.routes.stats import router as stats_router
from app.api.routes.uploads import router as uploads_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import init_db

logger = logging.getLogger(__name__)


def cors_middleware_options(raw_origins: str) -> dict[str, object] | None:
    origins = [value.strip() for value in raw_origins.split(",") if value.strip()]
    if not origins:
        return None
    if "*" in origins:
        # Browsers reject `Access-Control-Allow-Origin: *` when frontend fetches
        # use credentials. A regex keeps wildcard dev config usable by reflecting
        # the request origin through Starlette's CORSMiddleware.
        return {"allow_origins": [], "allow_origin_regex": ".*"}
    return {"allow_origins": origins}


def create_app() -> FastAPI:
    configure_logging()

    from contextlib import asynccontextmanager
    from app.queue import app as queue_app
    from app.services.event_pubsub import pubsub as event_pubsub

    @asynccontextmanager
    async def lifespan(fast_app: FastAPI):  # noqa: ARG001
        init_db()
        if not (settings.settings_encryption_key or "").strip():
            logger.warning(
                "settings_encryption_key_missing: integration settings writes are disabled until "
                "PS_SETTINGS_ENCRYPTION_KEY is configured"
            )
        async with queue_app.open_async():
            try:
                await event_pubsub.start()
            except Exception as exc:
                logger.warning("event_pubsub_start_failed: %s", exc)
            try:
                yield
            finally:
                try:
                    await event_pubsub.stop()
                except Exception:
                    pass

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    cors_options = cors_middleware_options(settings.cors_allow_origins)
    if cors_options:
        app.add_middleware(
            CORSMiddleware,
            **cors_options,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/v1/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/v1/health/ping-job", status_code=202)
    async def queue_ping_job() -> dict[str, str]:
        from app.jobs.health import ping
        await ping.defer_async()
        return {"status": "queued"}

    app.include_router(analysis_router)
    app.include_router(campaigns_router)
    app.include_router(contacts_router)
    app.include_router(email_fetch_router)
    app.include_router(email_verification_router)
    app.include_router(companies_router)
    app.include_router(events_router)
    app.include_router(pipeline_runs_router)
    app.include_router(prompts_router)
    app.include_router(queue_history_router)
    app.include_router(scrape_jobs_router)
    app.include_router(scrape_runs_router)
    app.include_router(scrape_prompts_router)
    app.include_router(settings_router)
    app.include_router(stats_router)
    app.include_router(uploads_router)
    return app


app = create_app()
