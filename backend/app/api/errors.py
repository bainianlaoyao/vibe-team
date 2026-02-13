from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.security import redact_sensitive_text


class ValidationIssue(BaseModel):
    field: str
    message: str


class ErrorPayload(BaseModel):
    code: str
    message: str
    issues: list[ValidationIssue] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorPayload
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "issues": [
                        {
                            "field": "body.name",
                            "message": "String should have at least 1 character",
                        }
                    ],
                }
            }
        }
    )


class ApiException(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        issues: list[ValidationIssue] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.issues = issues or []
        super().__init__(message)


def _status_to_code(status_code: int) -> str:
    mapping: dict[int, str] = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_ERROR",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    }
    return mapping.get(status_code, "UNKNOWN_ERROR")


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Unknown Error"


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    issues: list[ValidationIssue] | None = None,
) -> JSONResponse:
    safe_message = redact_sensitive_text(message)
    payload = ErrorResponse(
        error=ErrorPayload(
            code=code,
            message=safe_message,
            issues=issues or [],
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _extract_validation_issues(exc: RequestValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = str(error.get("msg", "Invalid value"))
        issues.append(ValidationIssue(field=location, message=message))
    return issues


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def handle_api_exception(_: Request, exc: ApiException) -> JSONResponse:
        return build_error_response(
            exc.status_code,
            exc.code,
            exc.message,
            issues=exc.issues,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return build_error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "VALIDATION_ERROR",
            "Request validation failed.",
            issues=_extract_validation_issues(exc),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else _status_phrase(exc.status_code)
        return build_error_response(exc.status_code, _status_to_code(exc.status_code), message)

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(_: Request, __: Exception) -> JSONResponse:
        return build_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "Unexpected server error.",
        )


def error_response_docs(*status_codes: int) -> dict[int, dict[str, Any]]:
    responses: dict[int, dict[str, Any]] = {}
    for status_code in status_codes:
        code = _status_to_code(status_code)
        responses[status_code] = {
            "model": ErrorResponse,
            "description": _status_phrase(status_code),
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": code,
                            "message": _status_phrase(status_code),
                            "issues": [],
                        }
                    }
                }
            },
        }
    return responses
