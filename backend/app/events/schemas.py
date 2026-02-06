from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.db.models import Event

TASK_STATUS_CHANGED_EVENT_TYPE = "task.status.changed"
RUN_LOG_EVENT_TYPE = "run.log"
ALERT_RAISED_EVENT_TYPE = "alert.raised"


class EventCategory(StrEnum):
    TASK_STATUS = "task_status"
    RUN_LOG = "run_log"
    ALERT = "alert"
    GENERIC = "generic"


class TaskStatusEventPayload(BaseModel):
    task_id: int = Field(gt=0)
    previous_status: str | None = Field(default=None, min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=32)
    run_id: int | None = Field(default=None, gt=0)
    actor: str | None = Field(default=None, min_length=1, max_length=120)


class RunLogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RunLogEventPayload(BaseModel):
    run_id: int = Field(gt=0)
    task_id: int | None = Field(default=None, gt=0)
    level: RunLogLevel = Field(default=RunLogLevel.INFO)
    message: str = Field(min_length=1, max_length=4000)
    sequence: int | None = Field(default=None, ge=1)


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertEventPayload(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    severity: AlertSeverity
    title: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=4000)
    task_id: int | None = Field(default=None, gt=0)
    run_id: int | None = Field(default=None, gt=0)


KnownEventPayload = TaskStatusEventPayload | RunLogEventPayload | AlertEventPayload
StreamPayload = KnownEventPayload | dict[str, Any]


class StreamEventRecord(BaseModel):
    id: int
    project_id: int
    event_type: str
    category: EventCategory
    payload: StreamPayload
    created_at: datetime
    trace_id: str | None
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 120,
                "project_id": 1,
                "event_type": "task.status.changed",
                "category": "task_status",
                "payload": {
                    "task_id": 22,
                    "previous_status": "todo",
                    "status": "running",
                    "run_id": 78,
                    "actor": "scheduler",
                },
                "created_at": "2026-02-06T18:40:00Z",
                "trace_id": "trace-task-22-run-78",
            }
        }
    )


def _normalize_status(value: str | StrEnum | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, StrEnum):
        return value.value
    return str(value)


def build_task_status_payload(
    *,
    task_id: int,
    previous_status: str | StrEnum | None,
    status: str | StrEnum,
    run_id: int | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    normalized_status = _normalize_status(status)
    if normalized_status is None:
        raise ValueError("status cannot be None")
    return TaskStatusEventPayload(
        task_id=task_id,
        previous_status=_normalize_status(previous_status),
        status=normalized_status,
        run_id=run_id,
        actor=actor,
    ).model_dump(mode="json")


def _parse_known_payload(
    event_type: str, payload: dict[str, Any]
) -> tuple[EventCategory, StreamPayload]:
    try:
        if event_type == TASK_STATUS_CHANGED_EVENT_TYPE:
            return EventCategory.TASK_STATUS, TaskStatusEventPayload.model_validate(payload)
        if event_type == RUN_LOG_EVENT_TYPE:
            return EventCategory.RUN_LOG, RunLogEventPayload.model_validate(payload)
        if event_type == ALERT_RAISED_EVENT_TYPE:
            return EventCategory.ALERT, AlertEventPayload.model_validate(payload)
    except ValidationError:
        return EventCategory.GENERIC, payload
    return EventCategory.GENERIC, payload


def to_stream_event_record(event: Event) -> StreamEventRecord:
    if event.id is None:
        raise ValueError("Event must be persisted before converting to a stream record.")

    category, payload = _parse_known_payload(event.event_type, event.payload_json)
    return StreamEventRecord(
        id=event.id,
        project_id=event.project_id,
        event_type=event.event_type,
        category=category,
        payload=payload,
        created_at=event.created_at,
        trace_id=event.trace_id,
    )


def serialize_sse_event(record: StreamEventRecord) -> str:
    return f"id: {record.id}\nevent: {record.event_type}\ndata: {record.model_dump_json()}\n\n"
