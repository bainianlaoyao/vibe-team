from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.agents import router as agents_router
from app.api.errors import register_exception_handlers
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.inbox import router as inbox_router
from app.api.tasks import router as tasks_router
from app.core.config import get_settings
from app.db.engine import dispose_engine, get_engine


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        get_engine()
        try:
            yield
        finally:
            dispose_engine()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(inbox_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    return app


app = create_app()
