from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings
from app.db.engine import dispose_engine, get_engine

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

app.include_router(health_router)
