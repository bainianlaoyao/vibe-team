from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.db.models import Agent, Project, Task, utc_now
from app.db.session import get_session

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskStatus(StrEnum):
    TODO = "todo"
    RUNNING = "running"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    project_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    description: str | None = None
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: int = Field(default=3, ge=1, le=5)
    assignee_agent_id: int | None = Field(default=None, gt=0)
    parent_task_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "title": "Implement tasks CRUD API",
                "description": "Support create/list/get/update/delete for tasks.",
                "status": "todo",
                "priority": 2,
                "assignee_agent_id": 4,
                "parent_task_id": 3,
                "due_at": "2026-02-10T18:00:00Z",
            }
        }
    )


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    assignee_agent_id: int | None = Field(default=None, gt=0)
    parent_task_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "running",
                "priority": 1,
                "assignee_agent_id": 4,
            }
        }
    )

    @model_validator(mode="after")
    def validate_non_empty_payload(self) -> TaskUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class TaskRead(BaseModel):
    id: int
    project_id: int
    title: str
    description: str | None
    status: str
    priority: int
    assignee_agent_id: int | None
    parent_task_id: int | None
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 22,
                "project_id": 1,
                "title": "Implement tasks CRUD API",
                "description": "Support create/list/get/update/delete for tasks.",
                "status": "todo",
                "priority": 2,
                "assignee_agent_id": 4,
                "parent_task_id": 3,
                "created_at": "2026-02-06T17:00:00Z",
                "updated_at": "2026-02-06T17:00:00Z",
                "due_at": "2026-02-10T18:00:00Z",
            }
        },
    )


DbSession = Annotated[Session, Depends(get_session)]


def _require_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_NOT_FOUND",
            f"Project {project_id} does not exist.",
        )
    return project


def _get_task_or_404(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "TASK_NOT_FOUND",
            f"Task {task_id} does not exist.",
        )
    return task


def _ensure_assignee_is_valid(
    session: Session,
    project_id: int,
    assignee_agent_id: int | None,
) -> None:
    if assignee_agent_id is None:
        return

    assignee = session.get(Agent, assignee_agent_id)
    if assignee is None:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_ASSIGNEE",
            f"Agent {assignee_agent_id} does not exist.",
        )
    if assignee.project_id != project_id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_ASSIGNEE",
            "Assignee agent must belong to the same project.",
        )


def _ensure_parent_task_is_valid(
    session: Session,
    project_id: int,
    parent_task_id: int | None,
    *,
    current_task_id: int | None = None,
) -> None:
    if parent_task_id is None:
        return
    if current_task_id is not None and current_task_id == parent_task_id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_TASK_DEPENDENCY",
            "Task cannot depend on itself.",
        )

    parent_task = session.get(Task, parent_task_id)
    if parent_task is None:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_TASK_DEPENDENCY",
            f"Parent task {parent_task_id} does not exist.",
        )
    if parent_task.project_id != project_id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_TASK_DEPENDENCY",
            "Parent task must belong to the same project.",
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


@router.get(
    "",
    response_model=list[TaskRead],
    responses=error_response_docs(status.HTTP_422_UNPROCESSABLE_ENTITY),
)
def list_tasks(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    assignee_agent_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskRead]:
    statement = select(Task).order_by(Task.id).offset(offset).limit(limit)
    if project_id is not None:
        statement = statement.where(Task.project_id == project_id)
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter.value)
    if assignee_agent_id is not None:
        statement = statement.where(Task.assignee_agent_id == assignee_agent_id)
    return [TaskRead.model_validate(task) for task in session.exec(statement).all()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskRead,
    responses=error_response_docs(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
)
def create_task(payload: TaskCreate, session: DbSession) -> TaskRead:
    _require_project(session, payload.project_id)
    _ensure_assignee_is_valid(session, payload.project_id, payload.assignee_agent_id)
    _ensure_parent_task_is_valid(session, payload.project_id, payload.parent_task_id)

    task = Task(**payload.model_dump(mode="python"))
    session.add(task)
    _commit_or_conflict(session)
    session.refresh(task)
    return TaskRead.model_validate(task)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    responses=error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY),
)
def get_task(task_id: int, session: DbSession) -> TaskRead:
    return TaskRead.model_validate(_get_task_or_404(session, task_id))


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    responses=error_response_docs(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
)
def update_task(task_id: int, payload: TaskUpdate, session: DbSession) -> TaskRead:
    task = _get_task_or_404(session, task_id)
    update_data = payload.model_dump(exclude_unset=True, mode="python")

    if "assignee_agent_id" in update_data:
        _ensure_assignee_is_valid(session, task.project_id, update_data["assignee_agent_id"])
    if "parent_task_id" in update_data:
        _ensure_parent_task_is_valid(
            session,
            task.project_id,
            update_data["parent_task_id"],
            current_task_id=task.id,
        )

    for field_name, value in update_data.items():
        setattr(task, field_name, value)
    task.updated_at = utc_now()

    _commit_or_conflict(session)
    session.refresh(task)
    return TaskRead.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_response_docs(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
)
def delete_task(task_id: int, session: DbSession) -> Response:
    task = _get_task_or_404(session, task_id)
    has_dependents_query = select(Task.id).where(Task.parent_task_id == task_id).limit(1)
    has_dependents = session.exec(has_dependents_query).first() is not None
    if has_dependents:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "TASK_HAS_DEPENDENTS",
            "Delete dependent tasks first.",
        )

    session.delete(task)
    _commit_or_conflict(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
