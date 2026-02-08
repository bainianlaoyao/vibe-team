from __future__ import annotations

import pytest

from app.runtime.failure_injection import (
    FailureInjectionRule,
    FailureInjectorStub,
    FailureMode,
    InjectedDatabaseLockError,
    InjectedFilePermissionError,
    InjectedProcessRestartInterruptError,
    InjectedRunTimeoutError,
    InjectedTransientRunError,
)


def test_failure_injector_can_inject_timeout() -> None:
    injector = FailureInjectorStub(
        [
            FailureInjectionRule(
                mode=FailureMode.TIMEOUT,
                point="llm.call",
                at_invocation=1,
            )
        ]
    )

    with pytest.raises(InjectedRunTimeoutError):
        injector.inject(point="llm.call")

    injector.inject(point="llm.call")
    assert injector.invocation_count(point="llm.call") == 2


def test_failure_injector_can_inject_transient_error() -> None:
    injector = FailureInjectorStub(
        [
            FailureInjectionRule(
                mode=FailureMode.TRANSIENT_ERROR,
                point="tool.invoke",
                at_invocation=2,
            )
        ]
    )

    injector.inject(point="tool.invoke")
    with pytest.raises(InjectedTransientRunError):
        injector.inject(point="tool.invoke")


def test_failure_injector_can_inject_process_restart_interrupt() -> None:
    injector = FailureInjectorStub(
        [
            FailureInjectionRule(
                mode=FailureMode.PROCESS_RESTART_INTERRUPT,
                point="worker.heartbeat",
                at_invocation=1,
            )
        ]
    )

    with pytest.raises(InjectedProcessRestartInterruptError):
        injector.inject(point="worker.heartbeat")


def test_failure_injector_does_not_affect_other_points() -> None:
    injector = FailureInjectorStub(
        [
            FailureInjectionRule(
                mode=FailureMode.TIMEOUT,
                point="llm.call",
                at_invocation=1,
            )
        ]
    )

    injector.inject(point="tool.invoke")
    assert injector.invocation_count(point="tool.invoke") == 1


def test_failure_injector_can_inject_database_lock() -> None:
    injector = FailureInjectorStub(
        [
            FailureInjectionRule(
                mode=FailureMode.DATABASE_LOCK,
                point="db.commit",
                at_invocation=1,
            )
        ]
    )

    with pytest.raises(InjectedDatabaseLockError):
        injector.inject(point="db.commit")


def test_failure_injector_can_inject_file_permission_error() -> None:
    injector = FailureInjectorStub(
        [
            FailureInjectionRule(
                mode=FailureMode.FILE_PERMISSION_ERROR,
                point="file.write",
                at_invocation=1,
            )
        ]
    )

    with pytest.raises(InjectedFilePermissionError):
        injector.inject(point="file.write")
