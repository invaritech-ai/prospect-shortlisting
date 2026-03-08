from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analysis import router as analysis_router
from app.api.routes.prompts import router as prompts_router
from app.api.routes.runs import router as runs_router
from app.api.routes.scrape_jobs import router as scrape_jobs_router
from app.api.routes.stats import router as stats_router
from app.api.routes.uploads import router as uploads_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import init_db


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    origins = [value.strip() for value in settings.cors_allow_origins.split(",") if value.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.on_event("startup")
    def startup_event() -> None:
        init_db()

    @app.get("/v1/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    app.include_router(analysis_router)
    app.include_router(prompts_router)
    app.include_router(runs_router)
    app.include_router(scrape_jobs_router)
    app.include_router(stats_router)
    app.include_router(uploads_router)
    return app


app = create_app()
