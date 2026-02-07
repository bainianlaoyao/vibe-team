from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from app.api.errors import error_response_docs
from app.core.logging import bind_log_context, get_logger
from app.db.models import Event
from app.db.session import get_session
from app.events.schemas import RUN_LOG_EVENT_TYPE, RunLogEventPayload, RunLogLevel

router = APIRouter(prefix="/logs", tags=["logs"])
logger = get_logger("bbb.api.logs")

DbSession = Annotated[Session, Depends(get_session)]


class RunLogRecordRead(BaseModel):
    id: int
    project_id: int
    run_id: int
    task_id: int | None
    level: RunLogLevel
    message: str
    sequence: int | None
    trace_id: str | None
    created_at: datetime


def _parse_run_log_payload(payload: dict[str, Any]) -> RunLogEventPayload | None:
    try:
        return RunLogEventPayload.model_validate(payload)
    except ValidationError:
        return None


@router.get(
    "",
    response_model=list[RunLogRecordRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
    ),
)
def list_run_logs(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    task_id: Annotated[int | None, Query(gt=0)] = None,
    run_id: Annotated[int | None, Query(gt=0)] = None,
    level: Annotated[RunLogLevel | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunLogRecordRead]:
    bind_log_context(task_id=task_id, run_id=run_id)
    fetch_limit = min(5000, max(200, offset + (limit * 20)))
    event_id = cast(Any, Event.id)
    statement = select(Event).where(Event.event_type == RUN_LOG_EVENT_TYPE)
    if project_id is not None:
        statement = statement.where(Event.project_id == project_id)
    statement = statement.order_by(event_id.desc()).limit(fetch_limit)
    rows = list(session.exec(statement).all())

    logs: list[RunLogRecordRead] = []
    for row in rows:
        parsed_payload = _parse_run_log_payload(row.payload_json)
        if parsed_payload is None:
            continue
        if run_id is not None and parsed_payload.run_id != run_id:
            continue
        if task_id is not None and parsed_payload.task_id != task_id:
            continue
        if level is not None and parsed_payload.level != level:
            continue
        if row.id is None:
            continue
        logs.append(
            RunLogRecordRead(
                id=row.id,
                project_id=row.project_id,
                run_id=parsed_payload.run_id,
                task_id=parsed_payload.task_id,
                level=parsed_payload.level,
                message=parsed_payload.message,
                sequence=parsed_payload.sequence,
                trace_id=row.trace_id,
                created_at=row.created_at,
            )
        )

    selected = logs[offset : offset + limit]
    logger.info(
        "logs.query.completed",
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        level=level.value if level is not None else None,
        limit=limit,
        offset=offset,
        result_count=len(selected),
    )
    return selected
