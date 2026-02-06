from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.enums import TaskRunStatus
from app.orchestration.run_state_machine import (
    InvalidTaskRunContractError,
    InvalidTaskRunTransitionError,
    ensure_run_status_transition,
    resolve_failed_target_status,
    validate_task_run_contract,
)


def test_run_state_machine_allows_expected_transitions() -> None:
    ensure_run_status_transition(TaskRunStatus.QUEUED, TaskRunStatus.RUNNING)
    ensure_run_status_transition(TaskRunStatus.RUNNING, TaskRunStatus.RETRY_SCHEDULED)
    ensure_run_status_transition(TaskRunStatus.RETRY_SCHEDULED, TaskRunStatus.RUNNING)
    ensure_run_status_transition(TaskRunStatus.RUNNING, TaskRunStatus.SUCCEEDED)
    ensure_run_status_transition(TaskRunStatus.RUNNING, TaskRunStatus.INTERRUPTED)


def test_run_state_machine_rejects_invalid_transition() -> None:
    with pytest.raises(InvalidTaskRunTransitionError):
        ensure_run_status_transition(TaskRunStatus.QUEUED, TaskRunStatus.SUCCEEDED)

    with pytest.raises(InvalidTaskRunTransitionError):
        ensure_run_status_transition(TaskRunStatus.SUCCEEDED, TaskRunStatus.RUNNING)


def test_run_contract_requires_idempotency_key_and_retry_timestamp() -> None:
    with pytest.raises(InvalidTaskRunContractError):
        validate_task_run_contract(
            status=TaskRunStatus.QUEUED,
            idempotency_key=" ",
            next_retry_at=None,
        )

    with pytest.raises(InvalidTaskRunContractError):
        validate_task_run_contract(
            status=TaskRunStatus.RETRY_SCHEDULED,
            idempotency_key="run-key-1",
            next_retry_at=None,
        )

    with pytest.raises(InvalidTaskRunContractError):
        validate_task_run_contract(
            status=TaskRunStatus.RUNNING,
            idempotency_key="run-key-2",
            next_retry_at=datetime.now(UTC),
        )

    validate_task_run_contract(
        status=TaskRunStatus.RETRY_SCHEDULED,
        idempotency_key="run-key-3",
        next_retry_at=datetime.now(UTC),
    )


def test_failed_target_status_resolver() -> None:
    assert resolve_failed_target_status(next_retry_at=None) == TaskRunStatus.FAILED
    assert (
        resolve_failed_target_status(next_retry_at=datetime.now(UTC))
        == TaskRunStatus.RETRY_SCHEDULED
    )
