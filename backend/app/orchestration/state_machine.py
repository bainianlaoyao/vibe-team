from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum

from app.db.enums import TaskStatus

logger = logging.getLogger(__name__)


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
    """
    Validate if a transition from current_status to target_status is allowed.

    Args:
        current_status: The current status of the task.
        target_status: The desired new status.

    Raises:
        InvalidTaskTransitionError: If the transition is not allowed.
    """
    if current_status == target_status:
        return

    allowed = allowed_transitions_for(current_status)
    if target_status not in allowed:
        allowed_values = ", ".join(sorted(status.value for status in allowed))
        error_msg = (
            "Invalid task status transition: "
            f"'{current_status.value}' -> '{target_status.value}'. "
            f"Allowed targets: [{allowed_values}]"
        )
        logger.warning(error_msg)
        raise InvalidTaskTransitionError(error_msg)

    logger.info(f"Transitioning task status: {current_status.value} -> {target_status.value}")


def resolve_command_target_status(current_status: TaskStatus, command: TaskCommand) -> TaskStatus:
    """
    Resolve the target status for a given command based on the current status.

    Args:
        current_status: The current status of the task.
        command: The command to execute (pause, resume, etc.).

    Returns:
        TaskStatus: The resulting status after applying the command.

    Raises:
        InvalidTaskCommandError: If the command is not supported or applicable.
        InvalidTaskTransitionError: If the implied transition is invalid.
    """
    transition_map = TASK_COMMAND_TRANSITIONS.get(command)
    if transition_map is None:
        raise InvalidTaskCommandError(f"Unsupported task command '{command.value}'.")

    target_status = transition_map.get(current_status)
    if target_status is None:
        allowed_from = ", ".join(sorted(status.value for status in transition_map))
        error_msg = (
            f"Command '{command.value}' is not allowed from '{current_status.value}'. "
            f"Allowed source statuses: [{allowed_from}]"
        )
        logger.warning(error_msg)
        raise InvalidTaskCommandError(error_msg)

    ensure_status_transition(current_status, target_status)
    return target_status
