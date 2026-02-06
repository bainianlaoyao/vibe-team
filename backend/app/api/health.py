from fastapi import APIRouter

from app.api.schemas import HealthzResponse, ReadinessChecks, ReadyzResponse
from app.core.config import get_settings

router = APIRouter()


@router.get("/healthz", response_model=HealthzResponse)
def healthz() -> HealthzResponse:
    settings = get_settings()
    return HealthzResponse(status="ok", service=settings.app_name, env=settings.app_env)


@router.get("/readyz", response_model=ReadyzResponse)
def readyz() -> ReadyzResponse:
    _ = get_settings()
    return ReadyzResponse(status="ready", checks=ReadinessChecks(configuration="ok"))
