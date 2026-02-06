from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import func, update
from sqlmodel import Session, select

from app.db.enums import TaskRunStatus
from app.db.models import Event, Task, TaskRun, utc_now
from app.db.repositories.common import OptimisticLockError, Page, Pagination, paginate
from app.events.schemas import RUN_STATUS_CHANGED_EVENT_TYPE, build_run_status_payload
from app.orchestration.run_state_machine import (
    InvalidTaskRunContractError,
    ensure_run_status_transition,
    resolve_failed_target_status,
    validate_task_run_contract,
)

DEFAULT_RUN_EVENT_ACTOR = "runtime"


class TaskRunNotFoundError(LookupError):
    """Raised when a run row does not exist."""


@dataclass(frozen=True, slots=True)
class TaskRunFilters:
    task_id: int | None = None
    agent_id: int | None = None
    run_status: TaskRunStatus | None = None
    idempotency_key: str | None = None
    retry_due_before: datetime | None = None


class TaskRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        task_run: TaskRun,
        *,
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        task_run.idempotency_key = task_run.idempotency_key.strip()
        validate_task_run_contract(
            status=task_run.run_status,
            idempotency_key=task_run.idempotency_key,
            next_retry_at=task_run.next_retry_at,
        )
        project_id = _require_task_project_id(self.session, task_run.task_id)

        self.session.add(task_run)
        self.session.flush()
        self._append_status_event(
            project_id=project_id,
            task_run=task_run,
            previous_status=None,
            trace_id=trace_id,
            actor=actor,
        )
        self.session.commit()
        self.session.refresh(task_run)
        return task_run

    def create_for_task(
        self,
        *,
        task_id: int,
        agent_id: int | None,
        idempotency_key: str,
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        normalized_idempotency_key = idempotency_key.strip()
        if not normalized_idempotency_key:
            raise InvalidTaskRunContractError("idempotency_key cannot be empty.")

        existing = self.get_by_idempotency_key(normalized_idempotency_key)
        if existing is not None:
            if existing.task_id != task_id:
                raise InvalidTaskRunContractError(
                    "idempotency_key already exists for a different task."
                )
            return existing

        attempt = self._next_attempt_for_task(task_id)
        return self.create(
            TaskRun(
                task_id=task_id,
                agent_id=agent_id,
                run_status=TaskRunStatus.QUEUED,
                attempt=attempt,
                idempotency_key=normalized_idempotency_key,
            ),
            trace_id=trace_id,
            actor=actor,
        )

    def get(self, run_id: int) -> TaskRun | None:
        return self.session.get(TaskRun, run_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> TaskRun | None:
        normalized = idempotency_key.strip()
        if not normalized:
            return None
        statement = select(TaskRun).where(TaskRun.idempotency_key == normalized)
        return self.session.exec(statement).first()

    def list(
        self,
        *,
        pagination: Pagination | None = None,
        filters: TaskRunFilters | None = None,
    ) -> Page[TaskRun]:
        active_filters = filters or TaskRunFilters()
        active_pagination = pagination or Pagination()

        statement = select(TaskRun)
        if active_filters.task_id is not None:
            statement = statement.where(TaskRun.task_id == active_filters.task_id)
        if active_filters.agent_id is not None:
            statement = statement.where(TaskRun.agent_id == active_filters.agent_id)
        if active_filters.run_status is not None:
            statement = statement.where(TaskRun.run_status == active_filters.run_status.value)
        if active_filters.idempotency_key is not None:
            statement = statement.where(TaskRun.idempotency_key == active_filters.idempotency_key)
        if active_filters.retry_due_before is not None:
            retry_at_column = cast(Any, TaskRun.next_retry_at)
            statement = (
                statement.where(TaskRun.run_status == TaskRunStatus.RETRY_SCHEDULED.value)
                .where(retry_at_column.is_not(None))
                .where(retry_at_column <= active_filters.retry_due_before)
            )

        statement = statement.order_by(TaskRun.started_at.desc(), TaskRun.id.desc())  # type: ignore[attr-defined,union-attr]
        return paginate(self.session, statement, pagination=active_pagination)

    def list_due_retries(self, *, due_before: datetime, limit: int = 50) -> Sequence[TaskRun]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        retry_at_column = cast(Any, TaskRun.next_retry_at)
        run_id_column = cast(Any, TaskRun.id)
        statement = (
            select(TaskRun)
            .where(TaskRun.run_status == TaskRunStatus.RETRY_SCHEDULED.value)
            .where(retry_at_column.is_not(None))
            .where(retry_at_column <= due_before)
            .order_by(retry_at_column.asc(), run_id_column.asc())
            .limit(limit)
        )
        return list(self.session.exec(statement).all())

    def mark_running(
        self,
        *,
        run_id: int,
        expected_version: int,
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        return self._transition(
            run_id=run_id,
            expected_version=expected_version,
            target_status=TaskRunStatus.RUNNING,
            trace_id=trace_id,
            actor=actor,
        )

    def mark_succeeded(
        self,
        *,
        run_id: int,
        expected_version: int,
        token_in: int | None = None,
        token_out: int | None = None,
        cost_usd: Decimal | None = None,
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        return self._transition(
            run_id=run_id,
            expected_version=expected_version,
            target_status=TaskRunStatus.SUCCEEDED,
            token_in=token_in,
            token_out=token_out,
            cost_usd=cost_usd,
            trace_id=trace_id,
            actor=actor,
        )

    def mark_failed(
        self,
        *,
        run_id: int,
        expected_version: int,
        error_code: str | None = None,
        error_message: str | None = None,
        next_retry_at: datetime | None = None,
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        target_status = resolve_failed_target_status(next_retry_at=next_retry_at)
        return self._transition(
            run_id=run_id,
            expected_version=expected_version,
            target_status=target_status,
            error_code=error_code,
            error_message=error_message,
            next_retry_at=next_retry_at,
            trace_id=trace_id,
            actor=actor,
        )

    def mark_cancelled(
        self,
        *,
        run_id: int,
        expected_version: int,
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        return self._transition(
            run_id=run_id,
            expected_version=expected_version,
            target_status=TaskRunStatus.CANCELLED,
            trace_id=trace_id,
            actor=actor,
        )

    def mark_interrupted(
        self,
        *,
        run_id: int,
        expected_version: int,
        error_code: str | None = "PROCESS_RESTARTED",
        error_message: str | None = "Run interrupted before completion.",
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        return self._transition(
            run_id=run_id,
            expected_version=expected_version,
            target_status=TaskRunStatus.INTERRUPTED,
            error_code=error_code,
            error_message=error_message,
            trace_id=trace_id,
            actor=actor,
        )

    def _next_attempt_for_task(self, task_id: int) -> int:
        max_attempt_raw = self.session.exec(
            select(func.max(TaskRun.attempt)).where(TaskRun.task_id == task_id)
        ).one()
        max_attempt = (
            max_attempt_raw[0] if hasattr(max_attempt_raw, "__getitem__") else max_attempt_raw
        )
        return int(max_attempt or 0) + 1

    def _transition(
        self,
        *,
        run_id: int,
        expected_version: int,
        target_status: TaskRunStatus,
        next_retry_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        token_in: int | None = None,
        token_out: int | None = None,
        cost_usd: Decimal | None = None,
        trace_id: str | None = None,
        actor: str | None = DEFAULT_RUN_EVENT_ACTOR,
    ) -> TaskRun:
        current = self.get(run_id)
        if current is None:
            raise TaskRunNotFoundError(f"task_run {run_id} does not exist")

        previous_status = _to_task_run_status(current.run_status)
        if previous_status == target_status:
            current.run_status = previous_status
            current.next_retry_at = _normalize_utc_datetime(current.next_retry_at)
            return current

        normalized_next_retry_at = _normalize_utc_datetime(next_retry_at)
        ensure_run_status_transition(previous_status, target_status)
        validate_task_run_contract(
            status=target_status,
            idempotency_key=current.idempotency_key,
            next_retry_at=normalized_next_retry_at,
        )

        values: dict[str, object] = {
            "run_status": target_status.value,
            "version": expected_version + 1,
        }
        terminal_timestamp = utc_now()

        if target_status == TaskRunStatus.RUNNING:
            values["ended_at"] = None
            values["next_retry_at"] = None
            values["error_code"] = None
            values["error_message"] = None
        elif target_status == TaskRunStatus.RETRY_SCHEDULED:
            values["ended_at"] = terminal_timestamp
            values["next_retry_at"] = normalized_next_retry_at
            values["error_code"] = _normalized_optional_text(error_code)
            values["error_message"] = _normalized_optional_text(error_message)
        elif target_status in {
            TaskRunStatus.SUCCEEDED,
            TaskRunStatus.FAILED,
            TaskRunStatus.CANCELLED,
            TaskRunStatus.INTERRUPTED,
        }:
            values["ended_at"] = terminal_timestamp
            values["next_retry_at"] = None
            if target_status in {TaskRunStatus.SUCCEEDED, TaskRunStatus.CANCELLED}:
                values["error_code"] = None
                values["error_message"] = None
            else:
                values["error_code"] = _normalized_optional_text(error_code)
                values["error_message"] = _normalized_optional_text(error_message)

        if token_in is not None:
            values["token_in"] = token_in
        if token_out is not None:
            values["token_out"] = token_out
        if cost_usd is not None:
            values["cost_usd"] = cost_usd

        statement = (
            update(TaskRun)
            .where(TaskRun.id == run_id)  # type: ignore[arg-type]
            .where(TaskRun.version == expected_version)  # type: ignore[arg-type]
            .values(**values)
        )
        result = self.session.exec(statement)
        if result.rowcount != 1:
            self.session.rollback()
            raise OptimisticLockError(
                f"task_run {run_id} version mismatch, expected {expected_version}"
            )

        self.session.expire_all()
        updated = self.session.get(TaskRun, run_id)
        if updated is None:
            raise TaskRunNotFoundError(f"task_run {run_id} missing after optimistic update")
        updated.run_status = _to_task_run_status(updated.run_status)
        updated.next_retry_at = _normalize_utc_datetime(updated.next_retry_at)

        project_id = _require_task_project_id(self.session, updated.task_id)
        self._append_status_event(
            project_id=project_id,
            task_run=updated,
            previous_status=previous_status,
            trace_id=trace_id,
            actor=actor,
        )
        self.session.commit()
        self.session.refresh(updated)
        updated.run_status = _to_task_run_status(updated.run_status)
        updated.next_retry_at = _normalize_utc_datetime(updated.next_retry_at)
        return updated

    def _append_status_event(
        self,
        *,
        project_id: int,
        task_run: TaskRun,
        previous_status: TaskRunStatus | None,
        trace_id: str | None,
        actor: str | None,
    ) -> None:
        if task_run.id is None:
            raise ValueError("Task run must be persisted before creating an event payload.")
        self.session.add(
            Event(
                project_id=project_id,
                event_type=RUN_STATUS_CHANGED_EVENT_TYPE,
                payload_json=build_run_status_payload(
                    run_id=task_run.id,
                    task_id=task_run.task_id,
                    previous_status=previous_status,
                    status=task_run.run_status,
                    attempt=task_run.attempt,
                    idempotency_key=task_run.idempotency_key,
                    next_retry_at=task_run.next_retry_at,
                    error_code=task_run.error_code,
                    actor=_normalized_optional_text(actor) or DEFAULT_RUN_EVENT_ACTOR,
                ),
                trace_id=_resolve_run_trace_id(run_id=task_run.id, trace_id=trace_id),
            )
        )


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_task_run_status(value: TaskRunStatus | str) -> TaskRunStatus:
    if isinstance(value, TaskRunStatus):
        return value
    return TaskRunStatus(str(value))


def _resolve_run_trace_id(*, run_id: int, trace_id: str | None) -> str:
    provided = _normalized_optional_text(trace_id)
    if provided is not None:
        return provided
    return f"trace-run-{run_id}-{uuid4().hex}"


def _require_task_project_id(session: Session, task_id: int) -> int:
    statement = select(Task.project_id).where(Task.id == task_id)
    project_id = session.exec(statement).first()
    if project_id is None:
        raise TaskRunNotFoundError(f"task {task_id} does not exist")
    return project_id
