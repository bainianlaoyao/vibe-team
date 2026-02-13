from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.api.errors import error_response_docs
from app.db.enums import TaskStatus
from app.db.models import Agent, Event, Task
from app.db.session import get_session
from app.events.schemas import (
    RUN_LOG_EVENT_TYPE,
    RUN_STATUS_CHANGED_EVENT_TYPE,
    TASK_STATUS_CHANGED_EVENT_TYPE,
)

router = APIRouter(tags=["dashboard"])

DbSession = Annotated[Session, Depends(get_session)]


class TaskStatsRead(BaseModel):
    project_id: int | None = None
    total: int
    todo: int
    running: int
    review: int
    done: int
    blocked: int
    failed: int
    cancelled: int
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "total": 12,
                "todo": 5,
                "running": 2,
                "review": 1,
                "done": 3,
                "blocked": 1,
                "failed": 0,
                "cancelled": 0,
            }
        }
    )


class ProjectUpdateRead(BaseModel):
    id: str
    event_id: int
    event_type: str
    summary: str
    task_id: int | None = None
    run_id: int | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    created_at: datetime
    trace_id: str | None = None


def _task_status_counts(tasks: list[Task]) -> TaskStatsRead:
    counts = {status.value: 0 for status in TaskStatus}
    for task in tasks:
        counts[str(task.status)] = counts.get(str(task.status), 0) + 1
    return TaskStatsRead(
        total=len(tasks),
        todo=counts[TaskStatus.TODO.value],
        running=counts[TaskStatus.RUNNING.value],
        review=counts[TaskStatus.REVIEW.value],
        done=counts[TaskStatus.DONE.value],
        blocked=counts[TaskStatus.BLOCKED.value],
        failed=counts[TaskStatus.FAILED.value],
        cancelled=counts[TaskStatus.CANCELLED.value],
    )


def _truncate(message: str, *, max_len: int = 180) -> str:
    if len(message) <= max_len:
        return message
    return f"{message[: max_len - 3]}..."


def _resolve_agent_for_task(session: Session, task_id: int | None) -> tuple[int | None, str | None]:
    if task_id is None:
        return None, None
    task = session.get(Task, task_id)
    if task is None or task.assignee_agent_id is None:
        return None, None
    agent = session.get(Agent, task.assignee_agent_id)
    if agent is None:
        return task.assignee_agent_id, None
    return agent.id, agent.name


def _build_update_summary(event: Event) -> tuple[str, int | None, int | None, list[str]]:
    payload = event.payload_json
    task_id = payload.get("task_id")
    run_id = payload.get("run_id")
    files_changed_raw = payload.get("files_changed")
    files_changed = (
        [str(item) for item in files_changed_raw] if isinstance(files_changed_raw, list) else []
    )
    if event.event_type == TASK_STATUS_CHANGED_EVENT_TYPE:
        status_name = str(payload.get("status", "unknown"))
        return (
            f"Task #{task_id} transitioned to {status_name}.",
            int(task_id) if isinstance(task_id, int) else None,
            int(run_id) if isinstance(run_id, int) else None,
            files_changed,
        )
    if event.event_type == RUN_STATUS_CHANGED_EVENT_TYPE:
        status_name = str(payload.get("status", "unknown"))
        return (
            f"Run #{run_id} transitioned to {status_name}.",
            int(task_id) if isinstance(task_id, int) else None,
            int(run_id) if isinstance(run_id, int) else None,
            files_changed,
        )
    message = str(payload.get("message", "Run log update."))
    return (
        f"Run #{run_id}: {_truncate(message)}",
        int(task_id) if isinstance(task_id, int) else None,
        int(run_id) if isinstance(run_id, int) else None,
        files_changed,
    )


@router.get(
    "/tasks/stats",
    response_model=TaskStatsRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_CONTENT),
    ),
)
def get_task_stats(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
) -> TaskStatsRead:
    statement = select(Task)
    if project_id is not None:
        statement = statement.where(Task.project_id == project_id)
    tasks = list(session.exec(statement).all())
    stats = _task_status_counts(tasks)
    stats.project_id = project_id
    return stats


@router.get(
    "/updates",
    response_model=list[ProjectUpdateRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_CONTENT),
    ),
)
def list_recent_updates(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ProjectUpdateRead]:
    event_id = cast(Any, Event.id)
    statement = (
        select(Event)
        .where(
            cast(Any, Event.event_type).in_(
                [
                    TASK_STATUS_CHANGED_EVENT_TYPE,
                    RUN_STATUS_CHANGED_EVENT_TYPE,
                    RUN_LOG_EVENT_TYPE,
                ]
            )
        )
        .order_by(event_id.desc())
        .limit(limit * 4)
    )
    if project_id is not None:
        statement = statement.where(Event.project_id == project_id)
    rows = list(session.exec(statement).all())

    updates: list[ProjectUpdateRead] = []
    for row in rows:
        if row.id is None:
            continue
        summary, task_id, run_id, files_changed = _build_update_summary(row)
        agent_id, agent_name = _resolve_agent_for_task(session, task_id)
        updates.append(
            ProjectUpdateRead(
                id=f"update-{row.id}",
                event_id=row.id,
                event_type=row.event_type,
                summary=summary,
                task_id=task_id,
                run_id=run_id,
                agent_id=agent_id,
                agent_name=agent_name,
                files_changed=files_changed,
                created_at=row.created_at,
                trace_id=row.trace_id,
            )
        )
        if len(updates) >= limit:
            break
    return updates
