from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureMode(StrEnum):
    TIMEOUT = "timeout"
    TRANSIENT_ERROR = "transient_error"
    PROCESS_RESTART_INTERRUPT = "process_restart_interrupt"


class InjectedRunTimeoutError(TimeoutError):
    """Raised by the failure injector to emulate runtime timeout."""


class InjectedTransientRunError(RuntimeError):
    """Raised by the failure injector to emulate retryable upstream failure."""


class InjectedProcessRestartInterruptError(RuntimeError):
    """Raised by the failure injector to emulate in-flight run interruption on restart."""


@dataclass(slots=True)
class FailureInjectionRule:
    mode: FailureMode
    point: str
    at_invocation: int = 1
    repeat: int = 1

    def should_inject(self, *, point: str, invocation: int) -> bool:
        if self.repeat <= 0:
            return False
        if point != self.point:
            return False
        if invocation != self.at_invocation:
            return False
        self.repeat -= 1
        return True


class FailureInjectorStub:
    """Deterministic failure injector for runtime reliability tests."""

    def __init__(self, rules: list[FailureInjectionRule] | None = None) -> None:
        self._rules = list(rules or [])
        self._invocations_by_point: dict[str, int] = {}

    def inject(self, *, point: str) -> None:
        invocation = self._invocations_by_point.get(point, 0) + 1
        self._invocations_by_point[point] = invocation

        for rule in self._rules:
            if rule.should_inject(point=point, invocation=invocation):
                raise _to_failure_exception(mode=rule.mode, point=point, invocation=invocation)

    def invocation_count(self, *, point: str) -> int:
        return self._invocations_by_point.get(point, 0)


def _to_failure_exception(*, mode: FailureMode, point: str, invocation: int) -> Exception:
    message = f"Injected failure '{mode.value}' at point '{point}' (invocation={invocation})."
    if mode == FailureMode.TIMEOUT:
        return InjectedRunTimeoutError(message)
    if mode == FailureMode.TRANSIENT_ERROR:
        return InjectedTransientRunError(message)
    if mode == FailureMode.PROCESS_RESTART_INTERRUPT:
        return InjectedProcessRestartInterruptError(message)
    raise RuntimeError(f"Unsupported failure mode: {mode}")
