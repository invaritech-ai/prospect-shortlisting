from __future__ import annotations

from fastapi import FastAPI

from app.api.routes.scrape_jobs import router as scrape_jobs_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import init_db


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.on_event("startup")
    def startup_event() -> None:
        init_db()

    @app.get("/v1/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    app.include_router(scrape_jobs_router)
    return app


app = create_app()

