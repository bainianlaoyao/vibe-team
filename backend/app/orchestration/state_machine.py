from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from app.db.enums import TaskStatus


class TaskCommand(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"
    CANCEL = "cancel"


INITIAL_TASK_STATUS = TaskStatus.TODO

TASK_STATUS_TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.TODO: frozenset({TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.REVIEW,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.REVIEW: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.DONE,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.BLOCKED: frozenset({TaskStatus.TODO, TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.FAILED: frozenset({TaskStatus.TODO, TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.CANCELLED: frozenset({TaskStatus.TODO}),
    TaskStatus.DONE: frozenset(),
}

TASK_COMMAND_TRANSITIONS: Mapping[TaskCommand, Mapping[TaskStatus, TaskStatus]] = {
    TaskCommand.PAUSE: {TaskStatus.RUNNING: TaskStatus.BLOCKED},
    TaskCommand.RESUME: {TaskStatus.BLOCKED: TaskStatus.RUNNING},
    TaskCommand.RETRY: {
        TaskStatus.FAILED: TaskStatus.TODO,
        TaskStatus.CANCELLED: TaskStatus.TODO,
    },
    TaskCommand.CANCEL: {
        TaskStatus.TODO: TaskStatus.CANCELLED,
        TaskStatus.RUNNING: TaskStatus.CANCELLED,
        TaskStatus.REVIEW: TaskStatus.CANCELLED,
        TaskStatus.BLOCKED: TaskStatus.CANCELLED,
        TaskStatus.FAILED: TaskStatus.CANCELLED,
    },
}


class InvalidTaskTransitionError(ValueError):
    """Raised when a task status transition is not allowed by the state machine."""


class InvalidTaskCommandError(ValueError):
    """Raised when a command cannot be applied to the current task status."""


def allowed_transitions_for(status: TaskStatus) -> frozenset[TaskStatus]:
    return TASK_STATUS_TRANSITIONS.get(status, frozenset())


def validate_initial_status(status: TaskStatus) -> None:
    if status != INITIAL_TASK_STATUS:
        raise InvalidTaskTransitionError(
            f"Task creation only allows '{INITIAL_TASK_STATUS.value}' status, got '{status.value}'."
        )


def ensure_status_transition(current_status: TaskStatus, target_status: TaskStatus) -> None:
    if current_status == target_status:
        return

    allowed = allowed_transitions_for(current_status)
    if target_status not in allowed:
        allowed_values = ", ".join(sorted(status.value for status in allowed))
        raise InvalidTaskTransitionError(
            "Invalid task status transition: "
            f"'{current_status.value}' -> '{target_status.value}'. "
            f"Allowed targets: [{allowed_values}]"
        )


def resolve_command_target_status(current_status: TaskStatus, command: TaskCommand) -> TaskStatus:
    transition_map = TASK_COMMAND_TRANSITIONS.get(command)
    if transition_map is None:
        raise InvalidTaskCommandError(f"Unsupported task command '{command.value}'.")

    target_status = transition_map.get(current_status)
    if target_status is None:
        allowed_from = ", ".join(sorted(status.value for status in transition_map))
        raise InvalidTaskCommandError(
            f"Command '{command.value}' is not allowed from '{current_status.value}'. "
            f"Allowed source statuses: [{allowed_from}]"
        )

    ensure_status_transition(current_status, target_status)
    return target_status
