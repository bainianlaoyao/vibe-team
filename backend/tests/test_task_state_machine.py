from __future__ import annotations

import pytest

from app.db.enums import TaskStatus
from app.orchestration.state_machine import (
    InvalidTaskCommandError,
    InvalidTaskTransitionError,
    TaskCommand,
    ensure_status_transition,
    resolve_command_target_status,
    validate_initial_status,
)


def test_state_machine_allows_expected_transitions() -> None:
    ensure_status_transition(TaskStatus.TODO, TaskStatus.RUNNING)
    ensure_status_transition(TaskStatus.RUNNING, TaskStatus.REVIEW)
    ensure_status_transition(TaskStatus.REVIEW, TaskStatus.DONE)
    ensure_status_transition(TaskStatus.RUNNING, TaskStatus.BLOCKED)
    ensure_status_transition(TaskStatus.FAILED, TaskStatus.TODO)
    ensure_status_transition(TaskStatus.CANCELLED, TaskStatus.TODO)


def test_state_machine_rejects_invalid_transition() -> None:
    with pytest.raises(InvalidTaskTransitionError):
        ensure_status_transition(TaskStatus.TODO, TaskStatus.DONE)

    with pytest.raises(InvalidTaskTransitionError):
        ensure_status_transition(TaskStatus.DONE, TaskStatus.RUNNING)


def test_initial_status_is_restricted_to_todo() -> None:
    validate_initial_status(TaskStatus.TODO)
    with pytest.raises(InvalidTaskTransitionError):
        validate_initial_status(TaskStatus.RUNNING)


def test_task_commands_map_to_expected_target_status() -> None:
    assert (
        resolve_command_target_status(TaskStatus.RUNNING, TaskCommand.PAUSE) == TaskStatus.BLOCKED
    )
    assert (
        resolve_command_target_status(TaskStatus.BLOCKED, TaskCommand.RESUME) == TaskStatus.RUNNING
    )
    assert resolve_command_target_status(TaskStatus.FAILED, TaskCommand.RETRY) == TaskStatus.TODO
    assert (
        resolve_command_target_status(TaskStatus.RUNNING, TaskCommand.CANCEL)
        == TaskStatus.CANCELLED
    )


def test_task_command_rejects_invalid_source_status() -> None:
    with pytest.raises(InvalidTaskCommandError):
        resolve_command_target_status(TaskStatus.TODO, TaskCommand.PAUSE)

    with pytest.raises(InvalidTaskCommandError):
        resolve_command_target_status(TaskStatus.DONE, TaskCommand.CANCEL)
