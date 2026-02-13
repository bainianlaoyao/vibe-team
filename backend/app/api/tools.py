from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.errors import ApiException, error_response_docs
from app.core.logging import bind_log_context, get_logger
from app.db.enums import InboxItemType, InboxStatus, SourceType, TaskStatus
from app.db.models import Event, InboxItem, Task, utc_now
from app.db.session import get_session
from app.events.schemas import TASK_STATUS_CHANGED_EVENT_TYPE, build_task_status_payload
from app.exporters import sync_tasks_markdown_for_project_if_enabled
from app.orchestration.state_machine import InvalidTaskTransitionError, ensure_status_transition
from app.security import SecurityAuditOutcome, append_security_audit_event

DbSession = Annotated[Session, Depends(get_session)]

DEFAULT_TOOL_ACTOR = "cli_tool"
TOOL_COMMAND_AUDIT_EVENT_TYPE = "tool.command.audit"
INBOX_ITEM_CREATED_EVENT_TYPE = "inbox.item.created"

router = APIRouter(prefix="/tools", tags=["tools"])
logger = get_logger("bbb.tools.command_api")


class _ToolCommandBase(BaseModel):
    task_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=80)
    trace_id: str | None = Field(default=None, max_length=64)
    actor: str | None = Field(default=DEFAULT_TOOL_ACTOR, min_length=1, max_length=120)


class FinishTaskCommandRequest(_ToolCommandBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 22,
                "idempotency_key": "tool-finish-task-22-001",
                "trace_id": "trace-tool-finish-22",
                "actor": "cli_tool",
            }
        }
    )


class BlockTaskCommandRequest(_ToolCommandBase):
    reason: str | None = Field(default=None, max_length=4000)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 22,
                "reason": "等待上游接口稳定",
                "idempotency_key": "tool-block-task-22-001",
                "trace_id": "trace-tool-block-22",
                "actor": "cli_tool",
            }
        }
    )


class RequestInputCommandRequest(_ToolCommandBase):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=4000)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 22,
                "title": "Need user decision",
                "content": "请选择目标分支（release/main）。",
                "idempotency_key": "tool-request-input-task-22-001",
                "trace_id": "trace-tool-request-input-22",
                "actor": "cli_tool",
            }
        }
    )


class ToolCommandResponse(BaseModel):
    tool: str
    task_id: int
    task_status: str
    task_version: int
    idempotency_key: str
    idempotency_hit: bool = False
    inbox_item_id: int | None = None


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


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


def _get_task_or_404(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "TASK_NOT_FOUND",
            f"Task {task_id} does not exist.",
        )
    return task


def _append_task_status_event(
    session: Session,
    *,
    task: Task,
    previous_status: TaskStatus,
    trace_id: str | None,
    actor: str,
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
                run_id=None,
                actor=actor,
            ),
            trace_id=trace_id,
        )
    )


def _transition_task_status(
    session: Session,
    *,
    task: Task,
    target_status: TaskStatus,
    trace_id: str | None,
    actor: str,
) -> None:
    previous_status = TaskStatus(str(task.status))
    if previous_status == target_status:
        return
    try:
        ensure_status_transition(previous_status, target_status)
    except InvalidTaskTransitionError as exc:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_TASK_TRANSITION",
            str(exc),
        ) from exc
    task.status = target_status
    task.updated_at = utc_now()
    task.version += 1
    _append_task_status_event(
        session,
        task=task,
        previous_status=previous_status,
        trace_id=trace_id,
        actor=actor,
    )


def _find_idempotent_response(
    session: Session,
    *,
    project_id: int,
    tool: str,
    task_id: int,
    idempotency_key: str,
) -> ToolCommandResponse | None:
    statement = (
        select(Event)
        .where(Event.project_id == project_id)
        .where(Event.event_type == TOOL_COMMAND_AUDIT_EVENT_TYPE)
        .order_by(cast(Any, Event.id).desc())
        .limit(500)
    )
    for event in session.exec(statement).all():
        payload = event.payload_json
        if (
            payload.get("tool") == tool
            and payload.get("task_id") == task_id
            and payload.get("idempotency_key") == idempotency_key
            and payload.get("outcome") == "applied"
        ):
            response_payload = payload.get("response")
            if isinstance(response_payload, dict):
                return ToolCommandResponse.model_validate(response_payload)
    return None


def _request_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def _append_tool_audit_event(
    session: Session,
    *,
    task: Task,
    tool: str,
    idempotency_key: str,
    actor: str,
    trace_id: str | None,
    outcome: str,
    response: ToolCommandResponse | None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "tool": tool,
        "task_id": task.id,
        "project_id": task.project_id,
        "idempotency_key": idempotency_key,
        "actor": actor,
        "outcome": outcome,
        "timestamp": datetime.now().isoformat(),
        "response": response.model_dump(mode="json") if response is not None else None,
        "error_code": error_code,
        "error_message": _normalized_optional_text(error_message),
    }
    session.add(
        Event(
            project_id=task.project_id,
            event_type=TOOL_COMMAND_AUDIT_EVENT_TYPE,
            payload_json=payload,
            trace_id=trace_id,
        )
    )


@router.post(
    "/finish_task",
    response_model=ToolCommandResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def finish_task(
    payload: FinishTaskCommandRequest,
    request: Request,
    session: DbSession,
) -> ToolCommandResponse:
    task = _get_task_or_404(session, payload.task_id)
    bind_log_context(trace_id=payload.trace_id, task_id=payload.task_id)
    actor = _normalized_optional_text(payload.actor) or DEFAULT_TOOL_ACTOR
    idempotency_key = payload.idempotency_key.strip()

    replayed = _find_idempotent_response(
        session,
        project_id=task.project_id,
        tool="finish_task",
        task_id=payload.task_id,
        idempotency_key=idempotency_key,
    )
    if replayed is not None:
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=actor,
            action="finish_task",
            resource=f"task:{payload.task_id}",
            outcome=SecurityAuditOutcome.ALLOWED,
            reason="idempotency_replay",
            ip=_request_ip(request),
            metadata={"idempotency_key": idempotency_key},
            trace_id=payload.trace_id,
        )
        _commit_or_conflict(session)
        return replayed.model_copy(update={"idempotency_hit": True})

    try:
        _transition_task_status(
            session,
            task=task,
            target_status=TaskStatus.DONE,
            trace_id=payload.trace_id,
            actor=actor,
        )
    except ApiException as exc:
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=actor,
            action="finish_task",
            resource=f"task:{payload.task_id}",
            outcome=SecurityAuditOutcome.DENIED,
            reason=f"{exc.code}: {exc.message}",
            ip=_request_ip(request),
            metadata={"idempotency_key": idempotency_key},
            trace_id=payload.trace_id,
        )
        _append_tool_audit_event(
            session,
            task=task,
            tool="finish_task",
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=payload.trace_id,
            outcome="rejected",
            response=None,
            error_code=exc.code,
            error_message=exc.message,
        )
        _commit_or_conflict(session)
        raise

    response = ToolCommandResponse(
        tool="finish_task",
        task_id=payload.task_id,
        task_status=str(task.status),
        task_version=task.version,
        idempotency_key=idempotency_key,
        idempotency_hit=False,
        inbox_item_id=None,
    )
    _append_tool_audit_event(
        session,
        task=task,
        tool="finish_task",
        idempotency_key=idempotency_key,
        actor=actor,
        trace_id=payload.trace_id,
        outcome="applied",
        response=response,
    )
    append_security_audit_event(
        session,
        project_id=task.project_id,
        actor=actor,
        action="finish_task",
        resource=f"task:{payload.task_id}",
        outcome=SecurityAuditOutcome.ALLOWED,
        reason="task transitioned to done",
        ip=_request_ip(request),
        metadata={"idempotency_key": idempotency_key},
        trace_id=payload.trace_id,
    )
    _commit_or_conflict(session)
    sync_tasks_markdown_for_project_if_enabled(session=session, project_id=task.project_id)
    logger.info(
        "tool.finish_task.applied",
        task_id=payload.task_id,
        idempotency_key=idempotency_key,
        actor=actor,
    )
    return response


@router.post(
    "/block_task",
    response_model=ToolCommandResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def block_task(
    payload: BlockTaskCommandRequest,
    request: Request,
    session: DbSession,
) -> ToolCommandResponse:
    task = _get_task_or_404(session, payload.task_id)
    bind_log_context(trace_id=payload.trace_id, task_id=payload.task_id)
    actor = _normalized_optional_text(payload.actor) or DEFAULT_TOOL_ACTOR
    idempotency_key = payload.idempotency_key.strip()

    replayed = _find_idempotent_response(
        session,
        project_id=task.project_id,
        tool="block_task",
        task_id=payload.task_id,
        idempotency_key=idempotency_key,
    )
    if replayed is not None:
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=actor,
            action="block_task",
            resource=f"task:{payload.task_id}",
            outcome=SecurityAuditOutcome.ALLOWED,
            reason="idempotency_replay",
            ip=_request_ip(request),
            metadata={"idempotency_key": idempotency_key},
            trace_id=payload.trace_id,
        )
        _commit_or_conflict(session)
        return replayed.model_copy(update={"idempotency_hit": True})

    try:
        _transition_task_status(
            session,
            task=task,
            target_status=TaskStatus.BLOCKED,
            trace_id=payload.trace_id,
            actor=actor,
        )
    except ApiException as exc:
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=actor,
            action="block_task",
            resource=f"task:{payload.task_id}",
            outcome=SecurityAuditOutcome.DENIED,
            reason=f"{exc.code}: {exc.message}",
            ip=_request_ip(request),
            metadata={"idempotency_key": idempotency_key},
            trace_id=payload.trace_id,
        )
        _append_tool_audit_event(
            session,
            task=task,
            tool="block_task",
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=payload.trace_id,
            outcome="rejected",
            response=None,
            error_code=exc.code,
            error_message=exc.message,
        )
        _commit_or_conflict(session)
        raise

    response = ToolCommandResponse(
        tool="block_task",
        task_id=payload.task_id,
        task_status=str(task.status),
        task_version=task.version,
        idempotency_key=idempotency_key,
        idempotency_hit=False,
        inbox_item_id=None,
    )
    _append_tool_audit_event(
        session,
        task=task,
        tool="block_task",
        idempotency_key=idempotency_key,
        actor=actor,
        trace_id=payload.trace_id,
        outcome="applied",
        response=response,
    )
    append_security_audit_event(
        session,
        project_id=task.project_id,
        actor=actor,
        action="block_task",
        resource=f"task:{payload.task_id}",
        outcome=SecurityAuditOutcome.ALLOWED,
        reason="task transitioned to blocked",
        ip=_request_ip(request),
        metadata={"idempotency_key": idempotency_key},
        trace_id=payload.trace_id,
    )
    _commit_or_conflict(session)
    sync_tasks_markdown_for_project_if_enabled(session=session, project_id=task.project_id)
    logger.info(
        "tool.block_task.applied",
        task_id=payload.task_id,
        idempotency_key=idempotency_key,
        actor=actor,
    )
    return response


@router.post(
    "/request_input",
    response_model=ToolCommandResponse,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def request_input(
    payload: RequestInputCommandRequest,
    request: Request,
    session: DbSession,
) -> ToolCommandResponse:
    task = _get_task_or_404(session, payload.task_id)
    bind_log_context(trace_id=payload.trace_id, task_id=payload.task_id)
    actor = _normalized_optional_text(payload.actor) or DEFAULT_TOOL_ACTOR
    idempotency_key = payload.idempotency_key.strip()

    replayed = _find_idempotent_response(
        session,
        project_id=task.project_id,
        tool="request_input",
        task_id=payload.task_id,
        idempotency_key=idempotency_key,
    )
    if replayed is not None:
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=actor,
            action="request_input",
            resource=f"task:{payload.task_id}",
            outcome=SecurityAuditOutcome.ALLOWED,
            reason="idempotency_replay",
            ip=_request_ip(request),
            metadata={"idempotency_key": idempotency_key},
            trace_id=payload.trace_id,
        )
        _commit_or_conflict(session)
        return replayed.model_copy(update={"idempotency_hit": True})

    try:
        _transition_task_status(
            session,
            task=task,
            target_status=TaskStatus.BLOCKED,
            trace_id=payload.trace_id,
            actor=actor,
        )
    except ApiException as exc:
        append_security_audit_event(
            session,
            project_id=task.project_id,
            actor=actor,
            action="request_input",
            resource=f"task:{payload.task_id}",
            outcome=SecurityAuditOutcome.DENIED,
            reason=f"{exc.code}: {exc.message}",
            ip=_request_ip(request),
            metadata={"idempotency_key": idempotency_key},
            trace_id=payload.trace_id,
        )
        _append_tool_audit_event(
            session,
            task=task,
            tool="request_input",
            idempotency_key=idempotency_key,
            actor=actor,
            trace_id=payload.trace_id,
            outcome="rejected",
            response=None,
            error_code=exc.code,
            error_message=exc.message,
        )
        _commit_or_conflict(session)
        raise

    source_task_id = task.id
    if source_task_id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Task missing primary key while creating inbox item.",
        )
    inbox_item = InboxItem(
        project_id=task.project_id,
        source_type=SourceType.TASK,
        source_id=f"task:{source_task_id}",
        item_type=InboxItemType.AWAIT_USER_INPUT,
        title=payload.title,
        content=payload.content,
        status=InboxStatus.OPEN,
    )
    session.add(inbox_item)
    session.flush()
    if inbox_item.id is None:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "RESOURCE_CONFLICT",
            "Inbox item was created without primary key.",
        )
    session.add(
        Event(
            project_id=task.project_id,
            event_type=INBOX_ITEM_CREATED_EVENT_TYPE,
            payload_json={
                "item_id": inbox_item.id,
                "project_id": task.project_id,
                "item_type": InboxItemType.AWAIT_USER_INPUT.value,
                "source_type": SourceType.TASK.value,
                "source_id": f"task:{source_task_id}",
                "title": payload.title,
                "status": InboxStatus.OPEN.value,
            },
            trace_id=payload.trace_id,
        )
    )

    response = ToolCommandResponse(
        tool="request_input",
        task_id=payload.task_id,
        task_status=str(task.status),
        task_version=task.version,
        idempotency_key=idempotency_key,
        idempotency_hit=False,
        inbox_item_id=inbox_item.id,
    )
    _append_tool_audit_event(
        session,
        task=task,
        tool="request_input",
        idempotency_key=idempotency_key,
        actor=actor,
        trace_id=payload.trace_id,
        outcome="applied",
        response=response,
    )
    append_security_audit_event(
        session,
        project_id=task.project_id,
        actor=actor,
        action="request_input",
        resource=f"task:{payload.task_id}",
        outcome=SecurityAuditOutcome.ALLOWED,
        reason="task blocked and inbox item created",
        ip=_request_ip(request),
        metadata={"idempotency_key": idempotency_key, "inbox_item_id": inbox_item.id},
        trace_id=payload.trace_id,
    )
    _commit_or_conflict(session)
    sync_tasks_markdown_for_project_if_enabled(session=session, project_id=task.project_id)
    logger.info(
        "tool.request_input.applied",
        task_id=payload.task_id,
        idempotency_key=idempotency_key,
        actor=actor,
        inbox_item_id=inbox_item.id,
    )
    return response
