from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from sqlmodel import Session, select

from app.core.logging import bind_log_context, get_logger
from app.db.enums import TASK_RUN_TERMINAL_STATUSES, TaskRunStatus
from app.db.models import Event, Task, TaskRun, utc_now
from app.db.repositories import (
    OptimisticLockError,
    Pagination,
    TaskRunFilters,
    TaskRunNotFoundError,
    TaskRunRepository,
)
from app.events.schemas import RUN_LOG_EVENT_TYPE, RunLogLevel
from app.llm.contracts import LLMClient, LLMRequest, LLMResponse
from app.llm.errors import LLMProviderError
from app.llm.usage import record_usage_for_run
from app.orchestration.scheduler import pick_next_schedulable_task
from app.runtime.failure_injection import (
    InjectedProcessRestartInterruptError,
    InjectedRunTimeoutError,
    InjectedTransientRunError,
)
from app.security import redact_sensitive_text

DEFAULT_RUNTIME_ACTOR = "runtime"
DEFAULT_RECOVERY_ACTOR = "recovery"
FAILURE_POINT_BEFORE_LLM = "runtime.before_llm"
FAILURE_POINT_AFTER_LLM = "runtime.after_llm"
_MAX_ERROR_MESSAGE_LENGTH = 512
_MAX_RUN_OUTPUT_LOG_LENGTH = 4000
logger = get_logger("bbb.runtime.execution")


class FailureInjectorLike(Protocol):
    def inject(self, *, point: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeRetryPolicy:
    max_retry_attempts: int = 3
    base_delay_seconds: int = 15
    max_delay_seconds: int = 300

    def __post_init__(self) -> None:
        if self.max_retry_attempts < 0:
            raise ValueError("max_retry_attempts cannot be negative")
        if self.base_delay_seconds <= 0:
            raise ValueError("base_delay_seconds must be greater than 0")
        if self.max_delay_seconds <= 0:
            raise ValueError("max_delay_seconds must be greater than 0")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")

    def next_retry_at(self, *, failure_count: int, now: datetime) -> datetime | None:
        if failure_count <= 0:
            raise ValueError("failure_count must be greater than 0")
        if failure_count > self.max_retry_attempts:
            return None

        raw_delay = self.base_delay_seconds * (2 ** (failure_count - 1))
        bounded_delay = min(raw_delay, self.max_delay_seconds)
        normalized_now = _normalize_utc_datetime(now)
        return normalized_now + timedelta(seconds=bounded_delay)


@dataclass(frozen=True, slots=True)
class RuntimeRecoverySummary:
    interrupted_run_ids: tuple[int, ...]
    resumed_run_ids: tuple[int, ...]


class TaskRunRuntimeService:
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        retry_policy: RuntimeRetryPolicy | None = None,
        failure_injector: FailureInjectorLike | None = None,
        default_timeout_seconds: float = 90.0,
        now_factory: Callable[[], datetime] = utc_now,
    ) -> None:
        if default_timeout_seconds <= 0:
            raise ValueError("default_timeout_seconds must be greater than 0")
        self._llm_client = llm_client
        self._retry_policy = retry_policy or RuntimeRetryPolicy()
        self._failure_injector = failure_injector
        self._default_timeout_seconds = default_timeout_seconds
        self._now_factory = now_factory

    def create_run(
        self,
        *,
        session: Session,
        task_id: int,
        agent_id: int | None,
        idempotency_key: str,
        trace_id: str | None = None,
        actor: str = DEFAULT_RUNTIME_ACTOR,
    ) -> TaskRun:
        repository = TaskRunRepository(session)
        return repository.create_for_task(
            task_id=task_id,
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            actor=actor,
        )

    def enqueue_next_schedulable_run(
        self,
        *,
        session: Session,
        project_id: int,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
        actor: str = DEFAULT_RUNTIME_ACTOR,
    ) -> TaskRun | None:
        task = pick_next_schedulable_task(session, project_id=project_id)
        if task is None or task.id is None:
            return None

        resolved_idempotency_key = _resolve_idempotency_key(
            task_id=task.id,
            provided=idempotency_key,
        )
        return self.create_run(
            session=session,
            task_id=task.id,
            agent_id=task.assignee_agent_id,
            idempotency_key=resolved_idempotency_key,
            trace_id=trace_id,
            actor=actor,
        )

    async def execute_task(
        self,
        *,
        session: Session,
        task_id: int,
        agent_id: int | None,
        idempotency_key: str,
        request: LLMRequest,
        trace_id: str | None = None,
        actor: str = DEFAULT_RUNTIME_ACTOR,
        timeout_seconds: float | None = None,
    ) -> TaskRun:
        run = self.create_run(
            session=session,
            task_id=task_id,
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            actor=actor,
        )
        if run.id is None:
            raise TaskRunNotFoundError("run id missing after create_for_task")
        return await self.execute_run(
            session=session,
            run_id=run.id,
            request=request,
            trace_id=trace_id,
            actor=actor,
            timeout_seconds=timeout_seconds,
        )

    async def execute_run(
        self,
        *,
        session: Session,
        run_id: int,
        request: LLMRequest,
        trace_id: str | None = None,
        actor: str = DEFAULT_RUNTIME_ACTOR,
        timeout_seconds: float | None = None,
    ) -> TaskRun:
        repository = TaskRunRepository(session)
        run = repository.get(run_id)
        if run is None:
            raise TaskRunNotFoundError(f"task_run {run_id} does not exist")
        bind_log_context(
            trace_id=trace_id,
            run_id=run.id,
            task_id=run.task_id,
            agent_id=run.agent_id,
        )

        if _to_task_run_status(run.run_status) in TASK_RUN_TERMINAL_STATUSES:
            logger.info(
                "runtime.execute.skipped_terminal",
                run_id=run_id,
                run_status=_to_task_run_status(run.run_status).value,
            )
            return run

        _ensure_run_is_running(
            repository=repository,
            run=run,
            trace_id=trace_id,
            actor=actor,
        )
        timeout = timeout_seconds or self._default_timeout_seconds
        if timeout <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        logger.info("runtime.execute.started", run_id=run_id, timeout_seconds=timeout)

        try:
            self._inject_failure(point=FAILURE_POINT_BEFORE_LLM)
            response = await asyncio.wait_for(self._llm_client.generate(request), timeout=timeout)
            self._inject_failure(point=FAILURE_POINT_AFTER_LLM)
            return self._mark_succeeded(
                session=session,
                repository=repository,
                run_id=run_id,
                request=request,
                response=response,
                trace_id=trace_id,
                actor=actor,
            )
        except InjectedProcessRestartInterruptError as exc:
            logger.warning("runtime.execute.interrupted", run_id=run_id, reason=str(exc))
            return self._mark_interrupted(
                repository=repository,
                run_id=run_id,
                trace_id=trace_id,
                actor=actor,
                message=str(exc),
            )
        except (TimeoutError, InjectedRunTimeoutError) as exc:
            logger.warning("runtime.execute.timeout", run_id=run_id, reason=str(exc))
            return self._mark_failed(
                repository=repository,
                run_id=run_id,
                retryable=True,
                error_code="RUN_TIMEOUT",
                error_message=str(exc),
                trace_id=trace_id,
                actor=actor,
            )
        except InjectedTransientRunError as exc:
            logger.warning("runtime.execute.transient_error", run_id=run_id, reason=str(exc))
            return self._mark_failed(
                repository=repository,
                run_id=run_id,
                retryable=True,
                error_code="TRANSIENT_ERROR",
                error_message=str(exc),
                trace_id=trace_id,
                actor=actor,
            )
        except LLMProviderError as exc:
            logger.warning(
                "runtime.execute.provider_error",
                run_id=run_id,
                provider=exc.provider,
                code=exc.code.value,
                retryable=exc.retryable,
            )
            return self._mark_failed(
                repository=repository,
                run_id=run_id,
                retryable=exc.retryable,
                error_code=_resolve_provider_error_code(exc),
                error_message=exc.message,
                trace_id=trace_id,
                actor=actor,
            )
        except Exception as exc:
            logger.exception("runtime.execute.unexpected_error", run_id=run_id)
            return self._mark_failed(
                repository=repository,
                run_id=run_id,
                retryable=False,
                error_code="RUNTIME_UNEXPECTED_ERROR",
                error_message=str(exc),
                trace_id=trace_id,
                actor=actor,
            )

    def interrupt_inflight_runs(
        self,
        *,
        session: Session,
        limit: int = 100,
        trace_id: str | None = None,
        actor: str = DEFAULT_RECOVERY_ACTOR,
    ) -> list[TaskRun]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        repository = TaskRunRepository(session)
        page_size = min(limit, 100)
        running_runs = repository.list(
            pagination=Pagination(page=1, page_size=page_size),
            filters=TaskRunFilters(run_status=TaskRunStatus.RUNNING),
        ).items

        interrupted: list[TaskRun] = []
        for run in running_runs:
            if run.id is None:
                continue
            try:
                updated = repository.mark_interrupted(
                    run_id=run.id,
                    expected_version=run.version,
                    trace_id=trace_id,
                    actor=actor,
                )
                interrupted.append(updated)
            except OptimisticLockError:
                continue
        return interrupted

    def resume_due_retries(
        self,
        *,
        session: Session,
        due_before: datetime | None = None,
        limit: int = 100,
        trace_id: str | None = None,
        actor: str = DEFAULT_RECOVERY_ACTOR,
    ) -> list[TaskRun]:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        repository = TaskRunRepository(session)
        due_at = _normalize_utc_datetime(due_before or self._now_factory())
        due_runs = repository.list_due_retries(due_before=due_at, limit=limit)

        resumed: list[TaskRun] = []
        for run in due_runs:
            if run.id is None:
                continue
            try:
                updated = repository.mark_running(
                    run_id=run.id,
                    expected_version=run.version,
                    trace_id=trace_id,
                    actor=actor,
                )
                resumed.append(updated)
            except OptimisticLockError:
                continue
        return resumed

    def recover_after_restart(
        self,
        *,
        session: Session,
        due_before: datetime | None = None,
        limit: int = 100,
        trace_id: str | None = None,
        actor: str = DEFAULT_RECOVERY_ACTOR,
    ) -> RuntimeRecoverySummary:
        interrupted = self.interrupt_inflight_runs(
            session=session,
            limit=limit,
            trace_id=trace_id,
            actor=actor,
        )
        resumed = self.resume_due_retries(
            session=session,
            due_before=due_before,
            limit=limit,
            trace_id=trace_id,
            actor=actor,
        )
        return RuntimeRecoverySummary(
            interrupted_run_ids=tuple(run.id for run in interrupted if run.id is not None),
            resumed_run_ids=tuple(run.id for run in resumed if run.id is not None),
        )

    def _inject_failure(self, *, point: str) -> None:
        if self._failure_injector is None:
            return
        self._failure_injector.inject(point=point)

    def _mark_succeeded(
        self,
        *,
        session: Session,
        repository: TaskRunRepository,
        run_id: int,
        request: LLMRequest,
        response: LLMResponse,
        trace_id: str | None,
        actor: str,
    ) -> TaskRun:
        model_name = response.model or request.model or "default"
        record_usage_for_run(
            session,
            run_id=run_id,
            provider=response.provider,
            model_name=model_name,
            usage=response.usage,
        )
        latest = repository.get(run_id)
        if latest is None:
            raise TaskRunNotFoundError(f"task_run {run_id} does not exist")
        logger.info(
            "runtime.execute.succeeded",
            run_id=run_id,
            model_name=model_name,
            token_in=response.usage.token_in,
            token_out=response.usage.token_out,
            cost_usd=str(response.usage.cost_usd),
        )
        updated = repository.mark_succeeded(
            run_id=run_id,
            expected_version=latest.version,
            trace_id=trace_id,
            actor=actor,
        )
        self._append_result_log_event(
            session=session,
            task_id=updated.task_id,
            run_id=run_id,
            trace_id=trace_id,
            output_text=response.text,
        )
        return updated

    def _mark_failed(
        self,
        *,
        repository: TaskRunRepository,
        run_id: int,
        retryable: bool,
        error_code: str,
        error_message: str,
        trace_id: str | None,
        actor: str,
    ) -> TaskRun:
        latest = repository.get(run_id)
        if latest is None:
            raise TaskRunNotFoundError(f"task_run {run_id} does not exist")
        latest_status = _to_task_run_status(latest.run_status)
        if latest_status in TASK_RUN_TERMINAL_STATUSES:
            return latest

        next_retry_at: datetime | None = None
        if retryable:
            failure_count = _derive_failure_count(latest)
            next_retry_at = self._retry_policy.next_retry_at(
                failure_count=failure_count,
                now=self._now_factory(),
            )
        logger.warning(
            "runtime.execute.failed",
            run_id=run_id,
            error_code=_normalize_error_code(error_code),
            retryable=retryable,
            next_retry_at=next_retry_at.isoformat() if next_retry_at is not None else None,
        )
        return repository.mark_failed(
            run_id=run_id,
            expected_version=latest.version,
            error_code=_normalize_error_code(error_code),
            error_message=_normalize_error_message(error_message),
            next_retry_at=next_retry_at,
            trace_id=trace_id,
            actor=actor,
        )

    def _mark_interrupted(
        self,
        *,
        repository: TaskRunRepository,
        run_id: int,
        trace_id: str | None,
        actor: str,
        message: str,
    ) -> TaskRun:
        latest = repository.get(run_id)
        if latest is None:
            raise TaskRunNotFoundError(f"task_run {run_id} does not exist")
        latest_status = _to_task_run_status(latest.run_status)
        if latest_status in TASK_RUN_TERMINAL_STATUSES:
            return latest
        if latest_status == TaskRunStatus.INTERRUPTED:
            return latest
        if latest_status != TaskRunStatus.RUNNING:
            raise TaskRunNotFoundError(
                f"task_run {run_id} is in '{latest_status.value}', cannot mark interrupted"
            )
        logger.warning("runtime.execute.mark_interrupted", run_id=run_id, reason=message)
        return repository.mark_interrupted(
            run_id=run_id,
            expected_version=latest.version,
            error_message=_normalize_error_message(message),
            trace_id=trace_id,
            actor=actor,
        )

    def _append_result_log_event(
        self,
        *,
        session: Session,
        task_id: int,
        run_id: int,
        trace_id: str | None,
        output_text: str,
    ) -> None:
        normalized_output = _normalize_run_output(output_text)
        if normalized_output is None:
            return

        project_id = session.exec(select(Task.project_id).where(Task.id == task_id)).first()
        if project_id is None:
            logger.warning(
                "runtime.execute.output_log_skipped_missing_task",
                task_id=task_id,
                run_id=run_id,
            )
            return

        session.add(
            Event(
                project_id=project_id,
                event_type=RUN_LOG_EVENT_TYPE,
                payload_json={
                    "run_id": run_id,
                    "task_id": task_id,
                    "level": RunLogLevel.INFO.value,
                    "message": normalized_output,
                },
                trace_id=trace_id,
            )
        )
        try:
            session.commit()
        except Exception:
            session.rollback()
            logger.exception(
                "runtime.execute.output_log_commit_failed",
                task_id=task_id,
                run_id=run_id,
            )


def _ensure_run_is_running(
    *,
    repository: TaskRunRepository,
    run: TaskRun,
    trace_id: str | None,
    actor: str,
) -> TaskRun:
    status = _to_task_run_status(run.run_status)
    if status == TaskRunStatus.RUNNING:
        return run
    if status in {TaskRunStatus.QUEUED, TaskRunStatus.RETRY_SCHEDULED, TaskRunStatus.INTERRUPTED}:
        if run.id is None:
            raise TaskRunNotFoundError("task_run is missing id")
        return repository.mark_running(
            run_id=run.id,
            expected_version=run.version,
            trace_id=trace_id,
            actor=actor,
        )
    if status in TASK_RUN_TERMINAL_STATUSES:
        return run
    raise TaskRunNotFoundError(f"Unsupported run status: {status.value}")


def _resolve_provider_error_code(error: LLMProviderError) -> str:
    return _normalize_error_code(f"LLM_{error.code.value}")


def _normalize_error_code(value: str) -> str:
    normalized = value.strip().upper().replace("-", "_")
    if not normalized:
        return "RUNTIME_ERROR"
    return normalized[:64]


def _normalize_error_message(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return "Runtime execution failed."
    redacted = redact_sensitive_text(normalized)
    return redacted[:_MAX_ERROR_MESSAGE_LENGTH]


def _normalize_run_output(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    redacted = redact_sensitive_text(normalized)
    return redacted[:_MAX_RUN_OUTPUT_LOG_LENGTH]


def _to_task_run_status(value: TaskRunStatus | str) -> TaskRunStatus:
    if isinstance(value, TaskRunStatus):
        return value
    return TaskRunStatus(str(value))


def _derive_failure_count(run: TaskRun) -> int:
    # run.version starts from 1 (queued) and advances on every transition.
    # For running->retry_scheduled loops, version roughly tracks retry rounds.
    return max(1, run.version // 2)


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_idempotency_key(*, task_id: int, provided: str | None) -> str:
    if provided is not None:
        normalized = provided.strip()
        if normalized:
            return normalized
    return f"task-{task_id}-{uuid4().hex}"
