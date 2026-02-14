from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.core.config import get_settings
from app.core.logging import bind_log_context, get_logger
from app.db.enums import (
    TASK_RUN_TERMINAL_STATUSES,
    ConversationStatus,
    InboxItemType,
    InboxStatus,
    MessageRole,
    MessageType,
    SourceType,
    TaskRunStatus,
    TaskStatus,
)
from app.db.models import (
    Agent,
    Conversation,
    Event,
    InboxItem,
    Message,
    Project,
    Task,
    TaskRun,
    utc_now,
)
from app.db.repositories import MessageRepository
from app.db.session import get_session
from app.events.schemas import (
    RUN_LOG_EVENT_TYPE,
    TASK_STATUS_CHANGED_EVENT_TYPE,
    build_task_status_payload,
)
from app.exporters import sync_tasks_markdown_for_project_if_enabled
from app.llm import (
    LLMErrorCode,
    LLMMessage,
    LLMProviderError,
    LLMRequest,
    LLMRole,
    create_llm_client,
)
from app.orchestration.state_machine import (
    InvalidTaskCommandError,
    InvalidTaskTransitionError,
    TaskCommand,
    ensure_status_transition,
    resolve_command_target_status,
    validate_initial_status,
)
from app.runtime import TaskRunRuntimeService
from app.security import SecurityAuditOutcome, append_security_audit_event

DEFAULT_TASK_EVENT_ACTOR = "api"
TASK_INTERVENTION_AUDIT_EVENT_TYPE = "task.intervention.audit"
MAX_BROADCAST_TASKS = 200
ACTIVE_TASK_RUN_STATUSES: tuple[TaskRunStatus, ...] = (
    TaskRunStatus.QUEUED,
    TaskRunStatus.RUNNING,
    TaskRunStatus.RETRY_SCHEDULED,
)
INBOX_ITEM_CREATED_EVENT_TYPE = "inbox.item.created"

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = get_logger("bbb.api.tasks")


class TaskCreate(BaseModel):
    project_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    description: str | None = None
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: int = Field(default=3, ge=1, le=5)
    assignee_agent_id: int | None = Field(default=None, gt=0)
    parent_task_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    trace_id: str | None = Field(default=None, max_length=64)
    actor: str | None = Field(default=DEFAULT_TASK_EVENT_ACTOR, min_length=1, max_length=120)
    run_id: int | None = Field(default=None, gt=0)
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
                "trace_id": "trace-task-22-create",
                "actor": "api",
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
    trace_id: str | None = Field(default=None, max_length=64)
    actor: str | None = Field(default=DEFAULT_TASK_EVENT_ACTOR, min_length=1, max_length=120)
    run_id: int | None = Field(default=None, gt=0)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "running",
                "priority": 1,
                "assignee_agent_id": 4,
                "trace_id": "trace-task-22-start",
                "actor": "scheduler",
                "run_id": 78,
            }
        }
    )

    @model_validator(mode="after")
    def validate_non_empty_payload(self) -> TaskUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class TaskCommandRequest(BaseModel):
    trace_id: str | None = Field(default=None, max_length=64)
    actor: str | None = Field(default=DEFAULT_TASK_EVENT_ACTOR, min_length=1, max_length=120)
    run_id: int | None = Field(default=None, gt=0)
    expected_version: int | None = Field(default=None, gt=0)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trace_id": "trace-task-22-pause",
                "actor": "operator",
                "expected_version": 2,
            }
        }
    )


class TaskInterventionSource(StrEnum):
    SINGLE = "single"
    BROADCAST = "broadcast"


class TaskInterventionOutcome(StrEnum):
    APPLIED = "applied"
    REJECTED = "rejected"
    CONFLICT = "conflict"


class TaskInterventionAuditPayload(BaseModel):
    task_id: int = Field(gt=0)
    command: str = Field(min_length=1, max_length=32)
    source: TaskInterventionSource
    previous_status: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=32)
    run_id: int | None = Field(default=None, gt=0)
    actor: str = Field(min_length=1, max_length=120)
    outcome: TaskInterventionOutcome
    expected_version: int | None = Field(default=None, gt=0)
    actual_version: int = Field(ge=1)
    error_code: str | None = Field(default=None, min_length=1, max_length=64)
    error_message: str | None = Field(default=None, min_length=1, max_length=512)


class TaskCommandBroadcastRequest(BaseModel):
    project_id: int = Field(gt=0)
    task_ids: list[int] | None = Field(default=None, min_length=1, max_length=MAX_BROADCAST_TASKS)
    status: TaskStatus | None = None
    limit: int = Field(default=MAX_BROADCAST_TASKS, ge=1, le=MAX_BROADCAST_TASKS)
    trace_id: str | None = Field(default=None, max_length=64)
    actor: str | None = Field(default=DEFAULT_TASK_EVENT_ACTOR, min_length=1, max_length=120)
    run_id: int | None = Field(default=None, gt=0)
    expected_version: int | None = Field(default=None, gt=0)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": 1,
                "status": "running",
                "limit": 100,
                "trace_id": "trace-task-broadcast-pause",
                "actor": "operator",
            }
        }
    )


class TaskCommandBroadcastItemResult(BaseModel):
    task_id: int
    outcome: TaskInterventionOutcome
    previous_status: str | None = None
    status: str | None = None
    version: int | None = Field(default=None, ge=1)
    error_code: str | None = None
    error_message: str | None = None


class TaskCommandBroadcastResponse(BaseModel):
    command: TaskCommand
    project_id: int
    status_filter: TaskStatus | None = None
    total_targets: int
    applied_count: int
    failed_count: int
    items: list[TaskCommandBroadcastItemResult]


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
    version: int
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
                "version": 3,
            }
        },
    )


class TaskRunExecuteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    system_prompt: str | None = Field(default=None, max_length=4000)
    session_id: str | None = Field(default=None, min_length=1, max_length=120)
    conversation_id: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=80)
    max_turns: int | None = Field(default=None, ge=1, le=128)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    trace_id: str | None = Field(default=None, max_length=64)
    actor: str | None = Field(default="runtime", min_length=1, max_length=120)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "prompt": "请先阅读任务并给出执行结果摘要。",
                "provider": "claude_code",
                "model": "claude-sonnet-4-5",
                "session_id": "task-22",
                "conversation_id": 17,
                "idempotency_key": "task-22-request-001",
                "max_turns": 6,
                "timeout_seconds": 90,
                "trace_id": "trace-task-22-run-1",
                "actor": "runtime",
            }
        }
    )


class TaskRunRead(BaseModel):
    id: int
    task_id: int
    agent_id: int | None
    run_status: str
    attempt: int
    idempotency_key: str
    started_at: datetime
    ended_at: datetime | None
    next_retry_at: datetime | None
    error_code: str | None
    error_message: str | None
    token_in: int
    token_out: int
    cost_usd: Decimal
    version: int
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 91,
                "task_id": 22,
                "agent_id": 4,
                "run_status": "succeeded",
                "attempt": 1,
                "idempotency_key": "task-22-request-001",
                "started_at": "2026-02-07T09:00:00Z",
                "ended_at": "2026-02-07T09:00:08Z",
                "next_retry_at": None,
                "error_code": None,
                "error_message": None,
                "token_in": 120,
                "token_out": 48,
                "cost_usd": "0.0123",
                "version": 3,
            }
        },
    )


DbSession = Annotated[Session, Depends(get_session)]


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _to_task_status(value: TaskStatus | str) -> TaskStatus:
    if isinstance(value, TaskStatus):
        return value
    return TaskStatus(str(value))


def _resolve_transition_trace_id(*, task_id: int, trace_id: str | None) -> str:
    provided = _normalized_optional_text(trace_id)
    if provided is not None:
        return provided
    return f"trace-task-{task_id}-{uuid4().hex}"


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
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_ASSIGNEE",
            f"Agent {assignee_agent_id} does not exist.",
        )
    if assignee.project_id != project_id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_TASK_DEPENDENCY",
            "Task cannot depend on itself.",
        )

    parent_task = session.get(Task, parent_task_id)
    if parent_task is None:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_TASK_DEPENDENCY",
            f"Parent task {parent_task_id} does not exist.",
        )
    if parent_task.project_id != project_id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
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


def _flush_or_conflict(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Operation violates a database constraint.",
        ) from exc


def _append_task_status_event(
    session: Session,
    *,
    task: Task,
    previous_status: TaskStatus | str | None,
    trace_id: str | None,
    run_id: int | None,
    actor: str | None,
) -> None:
    if task.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Task missing primary key while writing status event.",
        )
    session.add(
        Event(
            project_id=task.project_id,
            event_type=TASK_STATUS_CHANGED_EVENT_TYPE,
            payload_json=build_task_status_payload(
                task_id=task.id,
                previous_status=previous_status,
                status=task.status,
                run_id=run_id,
                actor=_normalized_optional_text(actor) or DEFAULT_TASK_EVENT_ACTOR,
            ),
            trace_id=_resolve_transition_trace_id(task_id=task.id, trace_id=trace_id),
        )
    )


def _append_task_intervention_audit_event(
    session: Session,
    *,
    task: Task,
    command: TaskCommand,
    source: TaskInterventionSource,
    payload: TaskCommandRequest,
    previous_status: TaskStatus,
    current_status: TaskStatus,
    outcome: TaskInterventionOutcome,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    if task.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Task missing primary key while writing intervention audit event.",
        )

    actor = _normalized_optional_text(payload.actor) or DEFAULT_TASK_EVENT_ACTOR
    payload_json = TaskInterventionAuditPayload(
        task_id=task.id,
        command=command.value,
        source=source,
        previous_status=previous_status.value,
        status=current_status.value,
        run_id=payload.run_id,
        actor=actor,
        outcome=outcome,
        expected_version=payload.expected_version,
        actual_version=task.version,
        error_code=error_code,
        error_message=_normalized_optional_text(error_message),
    ).model_dump(mode="json")
    session.add(
        Event(
            project_id=task.project_id,
            event_type=TASK_INTERVENTION_AUDIT_EVENT_TYPE,
            payload_json=payload_json,
            trace_id=_resolve_transition_trace_id(task_id=task.id, trace_id=payload.trace_id),
        )
    )


def _raise_invalid_transition(message: str) -> None:
    raise ApiException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "INVALID_TASK_TRANSITION",
        message,
    )


def _raise_invalid_command(message: str) -> None:
    raise ApiException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "INVALID_TASK_COMMAND",
        message,
    )


def _to_task_run_status(value: TaskRunStatus | str) -> TaskRunStatus:
    if isinstance(value, TaskRunStatus):
        return value
    return TaskRunStatus(str(value))


def _resolve_task_run_target_status(*, run_status: TaskRunStatus) -> TaskStatus:
    if run_status == TaskRunStatus.SUCCEEDED:
        return TaskStatus.REVIEW
    if run_status == TaskRunStatus.FAILED:
        return TaskStatus.FAILED
    if run_status == TaskRunStatus.CANCELLED:
        return TaskStatus.CANCELLED
    if run_status == TaskRunStatus.INTERRUPTED:
        return TaskStatus.BLOCKED
    return TaskStatus.RUNNING


def _resolve_task_assignee(task: Task, session: Session) -> Agent:
    if task.assignee_agent_id is None:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_ASSIGNEE",
            "Task must have an assignee_agent_id before run.",
        )
    agent = session.get(Agent, task.assignee_agent_id)
    if agent is None or agent.project_id != task.project_id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_ASSIGNEE",
            "Task assignee agent is missing or does not belong to the same project.",
        )
    return agent


def _resolve_task_run_conversation(
    *,
    session: Session,
    task: Task,
    assignee: Agent,
    conversation_id: int | None,
) -> Conversation | None:
    if conversation_id is None:
        return None
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "CONVERSATION_NOT_FOUND",
            f"Conversation {conversation_id} does not exist.",
        )
    if conversation.status == ConversationStatus.CLOSED:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "CONVERSATION_CLOSED",
            "Cannot bind task run to a closed conversation.",
        )
    if conversation.project_id != task.project_id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_CONVERSATION_CONTEXT",
            "Conversation must belong to the same project as task.",
        )
    if conversation.agent_id != assignee.id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_CONVERSATION_CONTEXT",
            "Conversation must belong to the task assignee agent.",
        )
    if conversation.task_id != task.id:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_CONVERSATION_CONTEXT",
            "Conversation must be bound to the same task.",
        )
    return conversation


def _find_latest_active_task_run(*, session: Session, task_id: int) -> TaskRun | None:
    run_id_column = cast(Any, TaskRun.id)
    statement = (
        select(TaskRun)
        .where(TaskRun.task_id == task_id)
        .where(
            cast(Any, TaskRun.run_status).in_(
                [run_status.value for run_status in ACTIVE_TASK_RUN_STATUSES]
            )
        )
        .order_by(run_id_column.desc())
        .limit(1)
    )
    return session.exec(statement).first()


def _resolve_run_output_message(*, session: Session, run_id: int) -> str | None:
    event_id_column = cast(Any, Event.id)
    events = list(
        session.exec(
            select(Event)
            .where(Event.event_type == RUN_LOG_EVENT_TYPE)
            .order_by(event_id_column.desc())
            .limit(300)
        ).all()
    )
    for event in events:
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        if payload.get("run_id") != run_id:
            continue
        message = _normalized_optional_text(cast(str | None, payload.get("message")))
        if message is not None:
            return message
    return None


def _build_task_run_summary_text(
    *,
    session: Session,
    run: TaskRun,
    run_status: TaskRunStatus,
) -> str:
    if run_status == TaskRunStatus.SUCCEEDED and run.id is not None:
        output = _resolve_run_output_message(session=session, run_id=run.id)
        if output is not None:
            return output
        return "Task run succeeded, but no textual output was captured."

    error_message = _normalized_optional_text(run.error_message)
    if error_message is not None:
        return f"Task run {run_status.value}: {error_message}"
    return f"Task run {run_status.value}."


def _append_task_run_messages_to_conversation(
    *,
    session: Session,
    conversation: Conversation,
    task: Task,
    run: TaskRun,
    run_status: TaskRunStatus,
    prompt: str,
    trace_id: str | None,
) -> None:
    conversation_id = conversation.id
    run_id = run.id
    task_id = task.id
    if conversation_id is None or run_id is None or task_id is None:
        return

    normalized_prompt = _normalized_optional_text(prompt)
    if normalized_prompt is None:
        return

    summary_text = _build_task_run_summary_text(
        session=session,
        run=run,
        run_status=run_status,
    )

    repo = MessageRepository(session)
    sequence_num = repo.get_next_sequence_num(conversation_id)
    base_metadata: dict[str, Any] = {
        "source": "task_run",
        "task_id": task_id,
        "run_id": run_id,
        "trace_id": _normalized_optional_text(trace_id),
    }

    session.add(
        Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            message_type=MessageType.TEXT,
            content=normalized_prompt,
            metadata_json={**base_metadata, "kind": "run_prompt"},
            sequence_num=sequence_num,
        )
    )
    session.add(
        Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            message_type=MessageType.TEXT,
            content=summary_text,
            metadata_json={**base_metadata, "kind": "run_result", "run_status": run_status.value},
            sequence_num=sequence_num + 1,
        )
    )
    conversation.updated_at = utc_now()
    conversation.version += 1


def _task_completed_inbox_source_id(*, task_id: int) -> str:
    return f"task:{task_id}"


def _has_open_task_completed_inbox_item(
    *,
    session: Session,
    project_id: int,
    task_id: int,
) -> bool:
    source_id = _task_completed_inbox_source_id(task_id=task_id)
    existing_item = session.exec(
        select(InboxItem.id)
        .where(InboxItem.project_id == project_id)
        .where(InboxItem.source_type == SourceType.TASK.value)
        .where(InboxItem.source_id == source_id)
        .where(InboxItem.item_type == InboxItemType.TASK_COMPLETED.value)
        .where(InboxItem.status == InboxStatus.OPEN.value)
        .limit(1)
    ).first()
    return existing_item is not None


def _append_task_completed_inbox_item(
    *,
    session: Session,
    task: Task,
    run: TaskRun,
    run_status: TaskRunStatus,
    trace_id: str | None,
) -> None:
    if run_status != TaskRunStatus.SUCCEEDED or task.id is None or run.id is None:
        return
    if _has_open_task_completed_inbox_item(
        session=session,
        project_id=task.project_id,
        task_id=task.id,
    ):
        return

    summary_text = _build_task_run_summary_text(
        session=session,
        run=run,
        run_status=run_status,
    )
    source_id = _task_completed_inbox_source_id(task_id=task.id)
    inbox_item = InboxItem(
        project_id=task.project_id,
        source_type=SourceType.TASK,
        source_id=source_id,
        item_type=InboxItemType.TASK_COMPLETED,
        title=f"Task #{task.id} completed, waiting for confirmation",
        content=summary_text,
        status=InboxStatus.OPEN,
    )
    session.add(inbox_item)
    session.flush()

    if inbox_item.id is None:
        return
    session.add(
        Event(
            project_id=task.project_id,
            event_type=INBOX_ITEM_CREATED_EVENT_TYPE,
            payload_json={
                "item_id": inbox_item.id,
                "project_id": task.project_id,
                "item_type": InboxItemType.TASK_COMPLETED.value,
                "source_type": SourceType.TASK.value,
                "source_id": source_id,
                "title": inbox_item.title,
                "status": InboxStatus.OPEN.value,
                "task_id": task.id,
                "run_id": run.id,
            },
            trace_id=trace_id,
        )
    )


def _transition_task_status_for_run(
    session: Session,
    *,
    task: Task,
    target_status: TaskStatus,
    run_id: int | None,
    trace_id: str | None,
    actor: str | None,
) -> None:
    previous_status = _to_task_status(task.status)
    if previous_status == target_status:
        return
    try:
        ensure_status_transition(previous_status, target_status)
    except InvalidTaskTransitionError as exc:
        _raise_invalid_transition(str(exc))

    task.status = target_status
    task.updated_at = utc_now()
    task.version += 1
    _append_task_status_event(
        session,
        task=task,
        previous_status=previous_status,
        trace_id=trace_id,
        run_id=run_id,
        actor=actor,
    )
    _commit_or_conflict(session)
    session.refresh(task)
    _sync_tasks_md_if_enabled(session, project_id=task.project_id)


def _sync_tasks_md_if_enabled(session: Session, *, project_id: int) -> None:
    sync_tasks_markdown_for_project_if_enabled(
        session=session,
        project_id=project_id,
    )


def _build_llm_request(
    payload: TaskRunExecuteRequest,
    *,
    provider: str,
    model: str,
    task_id: int,
    cwd: Path | None = None,
) -> LLMRequest:
    session_id = _normalized_optional_text(payload.session_id) or f"task-{task_id}"
    return LLMRequest(
        provider=provider,
        model=model,
        messages=[LLMMessage(role=LLMRole.USER, content=payload.prompt)],
        session_id=session_id,
        system_prompt=payload.system_prompt,
        max_turns=payload.max_turns,
        cwd=cwd,
        trace_id=payload.trace_id,
    )


def _raise_provider_error(error: LLMProviderError) -> None:
    if error.code in {LLMErrorCode.UNSUPPORTED_PROVIDER, LLMErrorCode.INVALID_REQUEST}:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_LLM_PROVIDER",
            error.message,
        )
    if error.code == LLMErrorCode.AUTHENTICATION_FAILED:
        raise ApiException(
            status.HTTP_401_UNAUTHORIZED,
            "LLM_AUTHENTICATION_FAILED",
            error.message,
        )
    raise ApiException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "LLM_PROVIDER_UNAVAILABLE",
        error.message,
    )


def _request_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _apply_task_command(
    session: Session,
    *,
    task_id: int,
    command: TaskCommand,
    payload: TaskCommandRequest,
    source: TaskInterventionSource = TaskInterventionSource.SINGLE,
    request_ip: str | None = None,
) -> TaskRead:
    task = _get_task_or_404(session, task_id)
    bind_log_context(trace_id=payload.trace_id, task_id=task_id, run_id=payload.run_id)
    previous_status = _to_task_status(task.status)

    if payload.expected_version is not None and payload.expected_version != task.version:
        message = (
            "Task "
            f"{task_id} version mismatch, "
            f"expected {payload.expected_version}, got {task.version}."
        )
        _append_task_intervention_audit_event(
            session,
            task=task,
            command=command,
            source=source,
            payload=payload,
            previous_status=previous_status,
            current_status=previous_status,
            outcome=TaskInterventionOutcome.CONFLICT,
            error_code="TASK_VERSION_CONFLICT",
            error_message=message,
        )
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=_normalized_optional_text(payload.actor) or DEFAULT_TASK_EVENT_ACTOR,
            action=f"task.{command.value}",
            resource=f"task:{task_id}",
            outcome=SecurityAuditOutcome.DENIED,
            reason="TASK_VERSION_CONFLICT",
            ip=request_ip,
            metadata={"source": source.value, "expected_version": payload.expected_version},
            trace_id=payload.trace_id,
        )
        _commit_or_conflict(session)
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "TASK_VERSION_CONFLICT",
            message,
        )

    try:
        target_status = resolve_command_target_status(previous_status, command)
    except InvalidTaskCommandError as exc:
        _append_task_intervention_audit_event(
            session,
            task=task,
            command=command,
            source=source,
            payload=payload,
            previous_status=previous_status,
            current_status=previous_status,
            outcome=TaskInterventionOutcome.REJECTED,
            error_code="INVALID_TASK_COMMAND",
            error_message=str(exc),
        )
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=_normalized_optional_text(payload.actor) or DEFAULT_TASK_EVENT_ACTOR,
            action=f"task.{command.value}",
            resource=f"task:{task_id}",
            outcome=SecurityAuditOutcome.DENIED,
            reason=f"INVALID_TASK_COMMAND: {exc}",
            ip=request_ip,
            metadata={"source": source.value},
            trace_id=payload.trace_id,
        )
        _commit_or_conflict(session)
        _raise_invalid_command(str(exc))
    except InvalidTaskTransitionError as exc:
        _append_task_intervention_audit_event(
            session,
            task=task,
            command=command,
            source=source,
            payload=payload,
            previous_status=previous_status,
            current_status=previous_status,
            outcome=TaskInterventionOutcome.REJECTED,
            error_code="INVALID_TASK_TRANSITION",
            error_message=str(exc),
        )
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=_normalized_optional_text(payload.actor) or DEFAULT_TASK_EVENT_ACTOR,
            action=f"task.{command.value}",
            resource=f"task:{task_id}",
            outcome=SecurityAuditOutcome.DENIED,
            reason=f"INVALID_TASK_TRANSITION: {exc}",
            ip=request_ip,
            metadata={"source": source.value},
            trace_id=payload.trace_id,
        )
        _commit_or_conflict(session)
        _raise_invalid_transition(str(exc))

    task.status = target_status
    task.updated_at = utc_now()
    task.version += 1
    _append_task_status_event(
        session,
        task=task,
        previous_status=previous_status,
        trace_id=payload.trace_id,
        run_id=payload.run_id,
        actor=payload.actor,
    )
    _append_task_intervention_audit_event(
        session,
        task=task,
        command=command,
        source=source,
        payload=payload,
        previous_status=previous_status,
        current_status=target_status,
        outcome=TaskInterventionOutcome.APPLIED,
    )
    append_security_audit_event(
        session,
        project_id=task.project_id,
        actor=_normalized_optional_text(payload.actor) or DEFAULT_TASK_EVENT_ACTOR,
        action=f"task.{command.value}",
        resource=f"task:{task_id}",
        outcome=SecurityAuditOutcome.ALLOWED,
        reason=f"status transitioned to {target_status.value}",
        ip=request_ip,
        metadata={"source": source.value},
        trace_id=payload.trace_id,
    )

    _commit_or_conflict(session)
    session.refresh(task)
    _sync_tasks_md_if_enabled(session, project_id=task.project_id)
    logger.info(
        "task.command.applied",
        task_id=task_id,
        command=command.value,
        previous_status=previous_status.value,
        status=target_status.value,
        source=source.value,
    )
    return TaskRead.model_validate(task)


def _resolve_broadcast_status_filter(payload: TaskCommandBroadcastRequest) -> TaskStatus | None:
    if payload.status is not None:
        return payload.status
    if payload.task_ids is None:
        return TaskStatus.RUNNING
    return None


def _list_broadcast_target_task_ids(
    session: Session,
    *,
    payload: TaskCommandBroadcastRequest,
    status_filter: TaskStatus | None,
) -> list[int]:
    statement = select(cast(Any, Task.id)).where(Task.project_id == payload.project_id)
    if payload.task_ids is not None:
        statement = statement.where(cast(Any, Task.id).in_(payload.task_ids))
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter.value)
    statement = statement.order_by(cast(Any, Task.id).asc()).limit(payload.limit)
    task_ids = [int(task_id) for task_id in session.exec(statement).all()]
    if payload.task_ids is not None:
        order = {task_id: index for index, task_id in enumerate(payload.task_ids)}
        task_ids.sort(key=lambda task_id: order.get(task_id, len(order)))
    return task_ids


@router.get(
    "",
    response_model=list[TaskRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_CONTENT),
    ),
)
def list_tasks(
    session: DbSession,
    project_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    assignee_agent_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskRead]:
    statement = select(Task).order_by(Task.id).offset(offset).limit(limit)  # type: ignore[arg-type]
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
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def create_task(payload: TaskCreate, session: DbSession) -> TaskRead:
    bind_log_context(trace_id=payload.trace_id, task_id=None, run_id=payload.run_id)
    _require_project(session, payload.project_id)
    _ensure_assignee_is_valid(session, payload.project_id, payload.assignee_agent_id)
    _ensure_parent_task_is_valid(session, payload.project_id, payload.parent_task_id)

    try:
        validate_initial_status(payload.status)
    except InvalidTaskTransitionError as exc:
        _raise_invalid_transition(str(exc))

    task_data = payload.model_dump(mode="python", exclude={"trace_id", "actor", "run_id"})
    task = Task(**task_data)
    session.add(task)
    _flush_or_conflict(session)
    _append_task_status_event(
        session,
        task=task,
        previous_status=None,
        trace_id=payload.trace_id,
        run_id=payload.run_id,
        actor=payload.actor,
    )
    _commit_or_conflict(session)
    session.refresh(task)
    _sync_tasks_md_if_enabled(session, project_id=task.project_id)
    logger.info(
        "task.created",
        project_id=task.project_id,
        task_id=task.id,
        status=str(task.status),
    )
    return TaskRead.model_validate(task)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_CONTENT),
    ),
)
def get_task(task_id: int, session: DbSession) -> TaskRead:
    return TaskRead.model_validate(_get_task_or_404(session, task_id))


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def update_task(task_id: int, payload: TaskUpdate, session: DbSession) -> TaskRead:
    task = _get_task_or_404(session, task_id)
    bind_log_context(trace_id=payload.trace_id, task_id=task_id, run_id=payload.run_id)
    previous_status = _to_task_status(task.status)
    update_data = payload.model_dump(exclude_unset=True, mode="python")
    trace_id = update_data.pop("trace_id", None)
    actor = update_data.pop("actor", None)
    run_id = update_data.pop("run_id", None)

    requested_status_raw = update_data.get("status")
    requested_status = _to_task_status(requested_status_raw) if requested_status_raw else None
    if requested_status is not None:
        update_data["status"] = requested_status

    status_changed = False
    if requested_status is not None and requested_status != previous_status:
        status_changed = True
        try:
            ensure_status_transition(previous_status, requested_status)
        except InvalidTaskTransitionError as exc:
            _raise_invalid_transition(str(exc))

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
    task.version += 1
    if status_changed:
        _append_task_status_event(
            session,
            task=task,
            previous_status=previous_status,
            trace_id=trace_id,
            run_id=run_id,
            actor=actor,
        )

    _commit_or_conflict(session)
    session.refresh(task)
    if status_changed:
        _sync_tasks_md_if_enabled(session, project_id=task.project_id)
    logger.info(
        "task.updated",
        task_id=task_id,
        status=str(task.status),
        status_changed=status_changed,
    )
    return TaskRead.model_validate(task)


@router.post(
    "/broadcast/{command}",
    response_model=TaskCommandBroadcastResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_CONTENT),
    ),
)
def broadcast_task_command(
    command: TaskCommand,
    payload: TaskCommandBroadcastRequest,
    request: Request,
    session: DbSession,
) -> TaskCommandBroadcastResponse:
    _require_project(session, payload.project_id)
    status_filter = _resolve_broadcast_status_filter(payload)
    task_ids = _list_broadcast_target_task_ids(
        session,
        payload=payload,
        status_filter=status_filter,
    )
    command_payload = TaskCommandRequest(
        trace_id=payload.trace_id,
        actor=payload.actor,
        run_id=payload.run_id,
        expected_version=payload.expected_version,
    )

    items: list[TaskCommandBroadcastItemResult] = []
    applied_count = 0
    for task_id in task_ids:
        previous_status: str | None = None
        try:
            task = _get_task_or_404(session, task_id)
            previous_status = _to_task_status(task.status).value
            updated_task = _apply_task_command(
                session,
                task_id=task_id,
                command=command,
                payload=command_payload,
                source=TaskInterventionSource.BROADCAST,
                request_ip=_request_ip(request),
            )
            applied_count += 1
            items.append(
                TaskCommandBroadcastItemResult(
                    task_id=task_id,
                    outcome=TaskInterventionOutcome.APPLIED,
                    previous_status=previous_status,
                    status=updated_task.status,
                    version=updated_task.version,
                )
            )
        except ApiException as exc:
            current_task = session.get(Task, task_id)
            current_status = None
            current_version = None
            if current_task is not None:
                current_status = _to_task_status(current_task.status).value
                current_version = current_task.version
            outcome = (
                TaskInterventionOutcome.CONFLICT
                if exc.status_code == status.HTTP_409_CONFLICT
                else TaskInterventionOutcome.REJECTED
            )
            items.append(
                TaskCommandBroadcastItemResult(
                    task_id=task_id,
                    outcome=outcome,
                    previous_status=previous_status or current_status,
                    status=current_status,
                    version=current_version,
                    error_code=exc.code,
                    error_message=exc.message,
                )
            )

    failed_count = len(items) - applied_count
    return TaskCommandBroadcastResponse(
        command=command,
        project_id=payload.project_id,
        status_filter=status_filter,
        total_targets=len(task_ids),
        applied_count=applied_count,
        failed_count=failed_count,
        items=items,
    )


@router.post(
    "/{task_id}/run",
    response_model=TaskRunRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
    ),
)
def run_task(
    task_id: int,
    payload: TaskRunExecuteRequest,
    request: Request,
    session: DbSession,
) -> TaskRunRead:
    task = _get_task_or_404(session, task_id)
    project = _require_project(session, task.project_id)
    bind_log_context(trace_id=payload.trace_id, task_id=task_id)
    assignee = _resolve_task_assignee(task, session)
    conversation = _resolve_task_run_conversation(
        session=session,
        task=task,
        assignee=assignee,
        conversation_id=payload.conversation_id,
    )

    provider = _normalized_optional_text(payload.provider) or assignee.model_provider
    model = _normalized_optional_text(payload.model) or assignee.model_name
    idempotency_key = _normalized_optional_text(payload.idempotency_key) or (
        f"task-{task_id}-request-{uuid4().hex}"
    )
    active_run = _find_latest_active_task_run(session=session, task_id=task_id)
    if active_run is not None:
        active_status = _to_task_run_status(active_run.run_status)
        active_run_id = active_run.id
        if active_run.idempotency_key != idempotency_key:
            raise ApiException(
                status.HTTP_409_CONFLICT,
                "TASK_RUN_ALREADY_ACTIVE",
                (
                    f"Task {task_id} already has an active run {active_run_id} "
                    f"({active_status.value})."
                ),
            )
        if active_status in {TaskRunStatus.RUNNING, TaskRunStatus.RETRY_SCHEDULED}:
            logger.info(
                "task.run.reuse_active",
                task_id=task_id,
                run_id=active_run_id,
                run_status=active_status.value,
            )
            return TaskRunRead.model_validate(active_run)

    settings = get_settings()
    try:
        llm_client = create_llm_client(provider=provider, settings=settings)
    except LLMProviderError as exc:
        _raise_provider_error(exc)

    runtime_service = TaskRunRuntimeService(llm_client=llm_client)
    run = runtime_service.create_run(
        session=session,
        task_id=task_id,
        agent_id=assignee.id,
        idempotency_key=idempotency_key,
        trace_id=payload.trace_id,
        actor=payload.actor or "runtime",
    )
    if run.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Task run was created without primary key.",
        )
    bind_log_context(run_id=run.id, task_id=task_id, agent_id=assignee.id)

    run_status = _to_task_run_status(run.run_status)
    if run_status not in TASK_RUN_TERMINAL_STATUSES:
        _transition_task_status_for_run(
            session,
            task=task,
            target_status=TaskStatus.RUNNING,
            run_id=run.id,
            trace_id=payload.trace_id,
            actor=payload.actor,
        )

        llm_request = _build_llm_request(
            payload,
            provider=provider,
            model=model,
            task_id=task_id,
            cwd=settings.project_root or Path(project.root_path),
        )
        run = asyncio.run(
            runtime_service.execute_run(
                session=session,
                run_id=run.id,
                request=llm_request,
                trace_id=payload.trace_id,
                actor=payload.actor or "runtime",
                timeout_seconds=payload.timeout_seconds,
            )
        )
        run_status = _to_task_run_status(run.run_status)

    target_status = _resolve_task_run_target_status(run_status=run_status)
    _transition_task_status_for_run(
        session,
        task=task,
        target_status=target_status,
        run_id=run.id,
        trace_id=payload.trace_id,
        actor=payload.actor,
    )

    if conversation is not None:
        _append_task_run_messages_to_conversation(
            session=session,
            conversation=conversation,
            task=task,
            run=run,
            run_status=run_status,
            prompt=payload.prompt,
            trace_id=payload.trace_id,
        )
    if run_status == TaskRunStatus.SUCCEEDED and target_status == TaskStatus.REVIEW:
        _append_task_completed_inbox_item(
            session=session,
            task=task,
            run=run,
            run_status=run_status,
            trace_id=payload.trace_id,
        )

    persisted_run = session.get(TaskRun, run.id)
    if persisted_run is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "TASK_RUN_NOT_FOUND",
            f"Task run {run.id} does not exist.",
        )
    append_security_audit_event(
        session,
        project_id=task.project_id,
        actor=_normalized_optional_text(payload.actor) or "runtime",
        action="task.run",
        resource=f"task:{task_id}",
        outcome=SecurityAuditOutcome.ALLOWED,
        reason=f"run_status={run_status.value}",
        ip=_request_ip(request),
        metadata={"run_id": run.id, "provider": provider, "model": model},
        trace_id=payload.trace_id,
    )
    _commit_or_conflict(session)
    logger.info(
        "task.run.completed",
        task_id=task_id,
        run_id=run.id,
        run_status=run_status.value,
        task_status=target_status.value,
    )
    return TaskRunRead.model_validate(persisted_run)


@router.post(
    "/{task_id}/pause",
    response_model=TaskRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def pause_task(
    task_id: int,
    payload: TaskCommandRequest,
    request: Request,
    session: DbSession,
) -> TaskRead:
    return _apply_task_command(
        session,
        task_id=task_id,
        command=TaskCommand.PAUSE,
        payload=payload,
        request_ip=_request_ip(request),
    )


@router.post(
    "/{task_id}/resume",
    response_model=TaskRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def resume_task(
    task_id: int,
    payload: TaskCommandRequest,
    request: Request,
    session: DbSession,
) -> TaskRead:
    return _apply_task_command(
        session,
        task_id=task_id,
        command=TaskCommand.RESUME,
        payload=payload,
        request_ip=_request_ip(request),
    )


@router.post(
    "/{task_id}/retry",
    response_model=TaskRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def retry_task(
    task_id: int,
    payload: TaskCommandRequest,
    request: Request,
    session: DbSession,
) -> TaskRead:
    return _apply_task_command(
        session,
        task_id=task_id,
        command=TaskCommand.RETRY,
        payload=payload,
        request_ip=_request_ip(request),
    )


@router.post(
    "/{task_id}/cancel",
    response_model=TaskRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def cancel_task(
    task_id: int,
    payload: TaskCommandRequest,
    request: Request,
    session: DbSession,
) -> TaskRead:
    return _apply_task_command(
        session,
        task_id=task_id,
        command=TaskCommand.CANCEL,
        payload=payload,
        request_ip=_request_ip(request),
    )


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
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
