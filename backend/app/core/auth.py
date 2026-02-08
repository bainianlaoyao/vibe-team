from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


def _extract_api_key(request: Request) -> str | None:
    header_key = request.headers.get("X-API-Key")
    if header_key is not None:
        normalized = header_key.strip()
        if normalized:
            return normalized

    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    prefix = "bearer "
    lowered = authorization.lower()
    if not lowered.startswith(prefix):
        return None
    token = authorization[len(prefix) :].strip()
    return token if token else None


class LocalApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, api_key: str | None) -> None:
        super().__init__(app)
        normalized = api_key.strip() if api_key is not None else ""
        self._api_key = normalized or None

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if self._api_key is None:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        provided = _extract_api_key(request)
        if provided is not None and secrets.compare_digest(provided, self._api_key):
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Missing or invalid API key.",
                }
            },
        )
