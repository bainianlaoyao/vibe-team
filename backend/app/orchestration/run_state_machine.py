from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from app.db.enums import TaskRunStatus

INITIAL_TASK_RUN_STATUS = TaskRunStatus.QUEUED

TASK_RUN_STATUS_TRANSITIONS: Mapping[TaskRunStatus, frozenset[TaskRunStatus]] = {
    TaskRunStatus.QUEUED: frozenset({TaskRunStatus.RUNNING, TaskRunStatus.CANCELLED}),
    TaskRunStatus.RUNNING: frozenset(
        {
            TaskRunStatus.SUCCEEDED,
            TaskRunStatus.FAILED,
            TaskRunStatus.RETRY_SCHEDULED,
            TaskRunStatus.CANCELLED,
            TaskRunStatus.INTERRUPTED,
        }
    ),
    TaskRunStatus.RETRY_SCHEDULED: frozenset({TaskRunStatus.RUNNING, TaskRunStatus.CANCELLED}),
    TaskRunStatus.INTERRUPTED: frozenset(
        {
            TaskRunStatus.RUNNING,
            TaskRunStatus.FAILED,
            TaskRunStatus.CANCELLED,
        }
    ),
    TaskRunStatus.SUCCEEDED: frozenset(),
    TaskRunStatus.FAILED: frozenset(),
    TaskRunStatus.CANCELLED: frozenset(),
}


class InvalidTaskRunTransitionError(ValueError):
    """Raised when a run status transition is not allowed by the state machine."""


class InvalidTaskRunContractError(ValueError):
    """Raised when task run data violates the runtime reliability contract."""


def allowed_run_transitions_for(status: TaskRunStatus) -> frozenset[TaskRunStatus]:
    return TASK_RUN_STATUS_TRANSITIONS.get(status, frozenset())


def ensure_run_status_transition(
    current_status: TaskRunStatus,
    target_status: TaskRunStatus,
) -> None:
    if current_status == target_status:
        return

    allowed = allowed_run_transitions_for(current_status)
    if target_status not in allowed:
        allowed_values = ", ".join(sorted(status.value for status in allowed))
        raise InvalidTaskRunTransitionError(
            "Invalid task run status transition: "
            f"'{current_status.value}' -> '{target_status.value}'. "
            f"Allowed targets: [{allowed_values}]"
        )


def validate_task_run_contract(
    *,
    status: TaskRunStatus,
    idempotency_key: str,
    next_retry_at: datetime | None,
) -> None:
    if not idempotency_key.strip():
        raise InvalidTaskRunContractError("idempotency_key cannot be empty.")
    if status == TaskRunStatus.RETRY_SCHEDULED and next_retry_at is None:
        raise InvalidTaskRunContractError(
            "next_retry_at is required when run_status is 'retry_scheduled'."
        )
    if status != TaskRunStatus.RETRY_SCHEDULED and next_retry_at is not None:
        raise InvalidTaskRunContractError(
            "next_retry_at can only be set when run_status is 'retry_scheduled'."
        )


def resolve_failed_target_status(*, next_retry_at: datetime | None) -> TaskRunStatus:
    if next_retry_at is not None:
        return TaskRunStatus.RETRY_SCHEDULED
    return TaskRunStatus.FAILED
