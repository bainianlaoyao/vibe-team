from __future__ import annotations

import logging
import logging.config
from typing import Literal
from uuid import uuid4

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import Settings

LogFormat = Literal["json", "console"]

_TRACE_HEADER = "X-Trace-ID"


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _normalize_optional_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    normalized = value.strip()
    if not normalized:
        return None
    if not normalized.isdigit():
        return None
    parsed = int(normalized)
    return parsed if parsed > 0 else None


def bind_log_context(
    *,
    trace_id: str | None = None,
    task_id: int | str | None = None,
    run_id: int | str | None = None,
    agent_id: int | str | None = None,
) -> None:
    payload: dict[str, object] = {}
    normalized_trace_id = _normalize_optional_text(trace_id)
    if normalized_trace_id is not None:
        payload["trace_id"] = normalized_trace_id
    normalized_task_id = _normalize_optional_int(task_id)
    if normalized_task_id is not None:
        payload["task_id"] = normalized_task_id
    normalized_run_id = _normalize_optional_int(run_id)
    if normalized_run_id is not None:
        payload["run_id"] = normalized_run_id
    normalized_agent_id = _normalize_optional_int(agent_id)
    if normalized_agent_id is not None:
        payload["agent_id"] = normalized_agent_id
    if payload:
        structlog.contextvars.bind_contextvars(**payload)


def clear_log_context() -> None:
    structlog.contextvars.clear_contextvars()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)


def configure_logging(settings: Settings) -> None:
    level = settings.log_level.upper()
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[object] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
    ]

    renderer: object
    if settings.log_format == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    handlers: dict[str, dict[str, object]] = {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "level": level,
        }
    }
    if settings.log_file is not None:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "structured",
            "level": level,
            "filename": settings.log_file,
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
        }

    configured_handlers = list(handlers)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "foreign_pre_chain": shared_processors,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        structlog.processors.format_exc_info,
                        structlog.processors.EventRenamer("message"),
                        renderer,
                    ],
                }
            },
            "handlers": handlers,
            "loggers": {
                "": {
                    "handlers": configured_handlers,
                    "level": level,
                },
                "uvicorn": {
                    "handlers": configured_handlers,
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": configured_handlers,
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": configured_handlers,
                    "level": level,
                    "propagate": False,
                },
                "sqlalchemy": {
                    "handlers": configured_handlers,
                    "level": level,
                    "propagate": False,
                },
            },
        }
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class TraceContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = get_logger("bbb.api.request")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = _resolve_request_trace_id(request)
        request.state.trace_id = trace_id
        clear_log_context()
        bind_log_context(trace_id=trace_id)
        self._logger.info(
            "request.received",
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception:
            self._logger.exception(
                "request.failed",
                method=request.method,
                path=request.url.path,
            )
            clear_log_context()
            raise
        response.headers[_TRACE_HEADER] = trace_id
        self._logger.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        clear_log_context()
        return response


def _resolve_request_trace_id(request: Request) -> str:
    incoming = _normalize_optional_text(request.headers.get(_TRACE_HEADER))
    if incoming is not None:
        return incoming
    return f"trace-http-{uuid4().hex}"
