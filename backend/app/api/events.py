from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.db.models import Event, Project
from app.db.session import get_session, session_scope
from app.events.schemas import (
    AlertEventPayload,
    RunLogEventPayload,
    StreamEventRecord,
    TaskStatusEventPayload,
    serialize_sse_event,
    to_stream_event_record,
)

router = APIRouter(prefix="/events", tags=["events"])

DbSession = Annotated[Session, Depends(get_session)]


class TaskStatusEventCreate(BaseModel):
    project_id: int = Field(gt=0)
    event_type: Literal["task.status.changed"] = "task.status.changed"
    payload: TaskStatusEventPayload
    trace_id: str | None = Field(default=None, max_length=64)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "event_type": "task.status.changed",
                "payload": {
                    "task_id": 22,
                    "previous_status": "todo",
                    "status": "running",
                    "run_id": 78,
                    "actor": "scheduler",
                },
                "trace_id": "trace-task-22-run-78",
            }
        }
    )


class RunLogEventCreate(BaseModel):
    project_id: int = Field(gt=0)
    event_type: Literal["run.log"] = "run.log"
    payload: RunLogEventPayload
    trace_id: str | None = Field(default=None, max_length=64)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "event_type": "run.log",
                "payload": {
                    "run_id": 78,
                    "task_id": 22,
                    "level": "info",
                    "message": "Tool execution started",
                    "sequence": 11,
                },
                "trace_id": "trace-run-78",
            }
        }
    )


class AlertEventCreate(BaseModel):
    project_id: int = Field(gt=0)
    event_type: Literal["alert.raised"] = "alert.raised"
    payload: AlertEventPayload
    trace_id: str | None = Field(default=None, max_length=64)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "event_type": "alert.raised",
                "payload": {
                    "code": "RUN_TIMEOUT",
                    "severity": "error",
                    "title": "Run timeout",
                    "message": "Run exceeded the configured timeout threshold.",
                    "task_id": 22,
                    "run_id": 78,
                },
                "trace_id": "trace-run-timeout-78",
            }
        }
    )


EventCreateRequest = Annotated[
    TaskStatusEventCreate | RunLogEventCreate | AlertEventCreate,
    Field(discriminator="event_type"),
]


def _require_project(session: Session, project_id: int) -> None:
    if session.get(Project, project_id) is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_NOT_FOUND",
            f"Project {project_id} does not exist.",
        )


def _commit_or_conflict(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Operation violates a database constraint.",
        ) from exc


def _parse_last_event_id_header(last_event_id_header: str | None) -> int | None:
    if last_event_id_header is None:
        return None
    normalized = last_event_id_header.strip()
    if not normalized:
        return None
    if not normalized.isdigit():
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_LAST_EVENT_ID",
            "Last-Event-ID header must be a positive integer.",
        )
    parsed = int(normalized)
    if parsed <= 0:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_LAST_EVENT_ID",
            "Last-Event-ID header must be a positive integer.",
        )
    return parsed


def _resolve_start_event_id(
    *,
    last_event_id: int | None,
    last_event_id_header: str | None,
) -> int | None:
    header_value = _parse_last_event_id_header(last_event_id_header)
    if last_event_id is not None and header_value is not None and last_event_id != header_value:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_LAST_EVENT_ID",
            "Query parameter last_event_id conflicts with Last-Event-ID header.",
        )
    return last_event_id if last_event_id is not None else header_value


def _list_events_after(
    *,
    after_id: int,
    project_id: int | None,
    limit: int,
) -> list[Event]:
    with session_scope() as session:
        event_id = cast(Any, Event.id)
        statement = select(Event).where(event_id > after_id)
        if project_id is not None:
            statement = statement.where(Event.project_id == project_id)
        statement = statement.order_by(event_id).limit(limit)
        return list(session.exec(statement).all())


def _list_recent_events(*, project_id: int | None, limit: int) -> list[Event]:
    with session_scope() as session:
        statement = select(Event)
        if project_id is not None:
            statement = statement.where(Event.project_id == project_id)
        statement = statement.order_by(cast(Any, Event.id).desc()).limit(limit)
        rows = list(session.exec(statement).all())
        rows.sort(key=lambda row: row.id or 0)
        return rows


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=StreamEventRecord,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
    ),
)
def create_event(payload: EventCreateRequest, session: DbSession) -> StreamEventRecord:
    _require_project(session, payload.project_id)
    event = Event(
        project_id=payload.project_id,
        event_type=payload.event_type,
        payload_json=payload.payload.model_dump(mode="json"),
        trace_id=payload.trace_id,
    )
    session.add(event)
    _commit_or_conflict(session)
    session.refresh(event)
    return to_stream_event_record(event)


@router.get(
    "/stream",
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
async def stream_events(
    request: Request,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    last_event_id: Annotated[int | None, Query(gt=0)] = None,
    replay_last: Annotated[int, Query(ge=0, le=500)] = 0,
    max_events: Annotated[int | None, Query(ge=1, le=1000)] = None,
    batch_size: Annotated[int, Query(ge=1, le=200)] = 50,
    poll_interval_ms: Annotated[int, Query(ge=100, le=5000)] = 500,
    heartbeat_seconds: Annotated[int, Query(ge=5, le=60)] = 15,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    start_id = _resolve_start_event_id(
        last_event_id=last_event_id,
        last_event_id_header=last_event_id_header,
    )
    initial_replay: list[Event]
    if start_id is None and replay_last > 0:
        initial_replay = _list_recent_events(project_id=project_id, limit=replay_last)
    else:
        initial_replay = []

    async def generator() -> AsyncIterator[str]:
        cursor = start_id or 0
        sent_events = 0
        pending = initial_replay.copy()
        heartbeat_deadline = time.monotonic() + heartbeat_seconds

        while True:
            if await request.is_disconnected():
                return

            batch = pending
            if pending:
                pending = []
            else:
                batch = _list_events_after(
                    after_id=cursor,
                    project_id=project_id,
                    limit=batch_size,
                )

            if batch:
                for event in batch:
                    if event.id is None:
                        continue
                    record = to_stream_event_record(event)
                    yield serialize_sse_event(record)
                    cursor = max(cursor, event.id)
                    sent_events += 1
                    if max_events is not None and sent_events >= max_events:
                        return
                heartbeat_deadline = time.monotonic() + heartbeat_seconds
                continue

            if time.monotonic() >= heartbeat_deadline:
                yield ": heartbeat\n\n"
                heartbeat_deadline = time.monotonic() + heartbeat_seconds

            await asyncio.sleep(poll_interval_ms / 1000)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
