from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.comments import router as comments_router
from app.api.conversations import router as conversations_router
from app.api.dashboard import router as dashboard_router
from app.api.debug import router as debug_router
from app.api.errors import register_exception_handlers
from app.api.events import router as events_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.api.inbox import router as inbox_router
from app.api.logs import router as logs_router
from app.api.metrics import router as metrics_router
from app.api.roles import router as roles_router
from app.api.tasks import router as tasks_router
from app.api.tools import router as tools_router
from app.api.usage import router as usage_router
from app.api.ws_conversations import router as ws_conversations_router
from app.core.auth import LocalApiKeyMiddleware
from app.core.config import get_settings
from app.core.logging import TraceContextMiddleware, configure_logging
from app.db.bootstrap import initialize_database
from app.db.engine import dispose_engine, get_engine
from app.runtime import build_stuck_run_detector, run_stuck_detector_loop


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.db_auto_init:
            initialize_database(
                database_url=settings.database_url,
                seed=settings.db_auto_seed,
            )
        get_engine()
        detector_task: asyncio.Task[None] | None = None
        detector = build_stuck_run_detector(settings)
        detector_task = asyncio.create_task(
            run_stuck_detector_loop(
                detector=detector,
                interval_seconds=settings.stuck_scan_interval_s,
            )
        )
        try:
            yield
        finally:
            if detector_task is not None:
                detector_task.cancel()
                with suppress(asyncio.CancelledError):
                    await detector_task
            dispose_engine()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LocalApiKeyMiddleware, api_key=settings.local_api_key)
    app.add_middleware(TraceContextMiddleware)
    app.include_router(debug_router)
    app.include_router(health_router)
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(comments_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(inbox_router, prefix="/api/v1")
    app.include_router(logs_router, prefix="/api/v1")
    app.include_router(metrics_router, prefix="/api/v1")
    app.include_router(roles_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(tools_router, prefix="/api/v1")
    app.include_router(usage_router, prefix="/api/v1")
    app.include_router(ws_conversations_router)
    return app


app = create_app()
