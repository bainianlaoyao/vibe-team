from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlmodel import Session, select

from app.db.bootstrap import initialize_database
from app.db.engine import create_engine_from_url
from app.db.enums import AgentStatus, TaskRunStatus, TaskStatus
from app.db.models import Agent, Event, Project, Task
from app.db.repositories import TaskRunRepository
from app.llm.contracts import LLMMessage, LLMRequest, LLMResponse, LLMRole, LLMUsage
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.runtime import (
    FAILURE_POINT_BEFORE_LLM,
    FailureInjectionRule,
    FailureInjectorStub,
    FailureMode,
    RuntimeRetryPolicy,
    TaskRunRuntimeService,
)


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass(slots=True)
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


class SequenceLLMClient:
    def __init__(self, outcomes: list[LLMResponse | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.invocation_count = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        _ = request
        self.invocation_count += 1
        if not self._outcomes:
            raise AssertionError("No LLM outcomes left for test sequence.")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _request(*, session_id: str = "runtime-demo") -> LLMRequest:
    return LLMRequest(
        provider="claude_code",
        model="claude-sonnet-4-5",
        session_id=session_id,
        messages=[LLMMessage(role=LLMRole.USER, content="请执行任务")],
        system_prompt="You are a runtime test assistant.",
    )


def _success_response(
    *,
    session_id: str = "runtime-demo",
    token_in: int = 120,
    token_out: int = 40,
    cost_usd: str = "0.0123",
) -> LLMResponse:
    return LLMResponse(
        provider="claude_code",
        model="claude-sonnet-4-5",
        session_id=session_id,
        text="done",
        usage=LLMUsage(
            request_count=1,
            token_in=token_in,
            token_out=token_out,
            cost_usd=Decimal(cost_usd),
        ),
        stop_reason="success",
        raw_result="ok",
    )


def _create_project_agent_task(
    session: Session,
    root: Path,
    *,
    title: str,
) -> tuple[Project, Agent, Task]:
    slug = title.lower().replace(" ", "-")
    project = Project(name="Runtime Project", root_path=str(root / f"workspace-{slug}"))
    session.add(project)
    session.flush()

    agent = Agent(
        project_id=project.id,
        name="Runtime Agent",
        role="executor",
        model_provider="claude_code",
        model_name="claude-sonnet-4-5",
        initial_persona_prompt="Runtime test agent",
        enabled_tools_json=[],
        status=AgentStatus.ACTIVE,
    )
    session.add(agent)
    session.flush()

    task = Task(
        project_id=project.id,
        title=title,
        status=TaskStatus.TODO,
        priority=2,
        assignee_agent_id=agent.id,
    )
    session.add(task)
    session.commit()
    session.refresh(project)
    session.refresh(agent)
    session.refresh(task)
    return project, agent, task


def test_runtime_execute_task_success_and_idempotency(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "runtime-success.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            _, agent, task = _create_project_agent_task(
                session,
                tmp_path,
                title="Runtime Success Task",
            )
            assert task.id is not None
            assert agent.id is not None

            llm_client = SequenceLLMClient([_success_response()])
            service = TaskRunRuntimeService(
                llm_client=llm_client,
                retry_policy=RuntimeRetryPolicy(max_retry_attempts=3),
                default_timeout_seconds=5.0,
            )
            request = _request()
            idempotency_key = f"task-{task.id}-request-success"

            run = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=task.id,
                    agent_id=agent.id,
                    idempotency_key=idempotency_key,
                    request=request,
                    trace_id="trace-runtime-success",
                )
            )
            assert run.id is not None
            assert run.run_status == TaskRunStatus.SUCCEEDED
            assert run.attempt == 1
            assert run.token_in == 120
            assert run.token_out == 40
            assert run.cost_usd == Decimal("0.0123")

            duplicate = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=task.id,
                    agent_id=agent.id,
                    idempotency_key=idempotency_key,
                    request=request,
                )
            )
            assert duplicate.id == run.id
            assert duplicate.run_status == TaskRunStatus.SUCCEEDED
            assert llm_client.invocation_count == 1

            event_id = cast(Any, Event.id)
            events = list(
                session.exec(
                    select(Event)
                    .where(Event.project_id == task.project_id)
                    .where(Event.event_type == "run.status.changed")
                    .order_by(event_id.asc())
                ).all()
            )
            scoped = [event for event in events if event.payload_json.get("run_id") == run.id]
            assert [event.payload_json["status"] for event in scoped] == [
                "queued",
                "running",
                "succeeded",
            ]
    finally:
        engine.dispose()


def test_runtime_timeout_uses_exponential_backoff(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "runtime-backoff.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            _, agent, task = _create_project_agent_task(
                session,
                tmp_path,
                title="Runtime Backoff Task",
            )
            assert task.id is not None
            assert agent.id is not None

            clock = MutableClock(current=datetime(2026, 2, 7, 9, 0, 0, tzinfo=UTC))
            injector = FailureInjectorStub(
                [
                    FailureInjectionRule(
                        mode=FailureMode.TIMEOUT,
                        point=FAILURE_POINT_BEFORE_LLM,
                        at_invocation=1,
                    ),
                    FailureInjectionRule(
                        mode=FailureMode.TIMEOUT,
                        point=FAILURE_POINT_BEFORE_LLM,
                        at_invocation=2,
                    ),
                ]
            )
            llm_client = SequenceLLMClient([_success_response()])
            service = TaskRunRuntimeService(
                llm_client=llm_client,
                retry_policy=RuntimeRetryPolicy(
                    max_retry_attempts=3,
                    base_delay_seconds=10,
                    max_delay_seconds=120,
                ),
                failure_injector=injector,
                now_factory=clock,
            )
            request = _request(session_id="backoff-session")

            run = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=task.id,
                    agent_id=agent.id,
                    idempotency_key=f"task-{task.id}-request-backoff",
                    request=request,
                )
            )
            assert run.id is not None
            assert run.run_status == TaskRunStatus.RETRY_SCHEDULED
            assert run.next_retry_at == clock.current + timedelta(seconds=10)

            clock.current = clock.current + timedelta(seconds=11)
            resumed_once = service.resume_due_retries(
                session=session,
                due_before=clock.current,
            )
            assert [item.id for item in resumed_once] == [run.id]

            second = asyncio.run(
                service.execute_run(
                    session=session,
                    run_id=run.id,
                    request=request,
                )
            )
            assert second.run_status == TaskRunStatus.RETRY_SCHEDULED
            assert second.next_retry_at == clock.current + timedelta(seconds=20)

            assert second.next_retry_at is not None
            clock.current = second.next_retry_at + timedelta(seconds=1)
            resumed_twice = service.resume_due_retries(
                session=session,
                due_before=clock.current,
            )
            assert [item.id for item in resumed_twice] == [run.id]

            final = asyncio.run(
                service.execute_run(
                    session=session,
                    run_id=run.id,
                    request=request,
                )
            )
            assert final.run_status == TaskRunStatus.SUCCEEDED
            assert llm_client.invocation_count == 1
    finally:
        engine.dispose()


def test_runtime_recovery_marks_interrupted_and_resumes_due_retries(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "runtime-recover.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            _, agent, task_running = _create_project_agent_task(
                session,
                tmp_path,
                title="Runtime Running Task",
            )
            _, _, task_retry = _create_project_agent_task(
                session,
                tmp_path,
                title="Runtime Retry Task",
            )
            assert task_running.id is not None
            assert task_retry.id is not None
            assert agent.id is not None

            repository = TaskRunRepository(session)
            running_run = repository.create_for_task(
                task_id=task_running.id,
                agent_id=agent.id,
                idempotency_key=f"task-{task_running.id}-recover-running",
            )
            assert running_run.id is not None
            running_run = repository.mark_running(
                run_id=running_run.id,
                expected_version=running_run.version,
            )

            retry_run = repository.create_for_task(
                task_id=task_retry.id,
                agent_id=agent.id,
                idempotency_key=f"task-{task_retry.id}-recover-retry",
            )
            assert retry_run.id is not None
            retry_run = repository.mark_running(
                run_id=retry_run.id,
                expected_version=retry_run.version,
            )
            assert retry_run.id is not None
            retry_run = repository.mark_failed(
                run_id=retry_run.id,
                expected_version=retry_run.version,
                error_code="TEMP_UPSTREAM",
                error_message="retry later",
                next_retry_at=datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC),
            )
            assert retry_run.run_status == TaskRunStatus.RETRY_SCHEDULED
            assert running_run.id is not None
            assert retry_run.id is not None

            service = TaskRunRuntimeService(llm_client=SequenceLLMClient([]))
            summary = service.recover_after_restart(
                session=session,
                due_before=datetime(2026, 2, 7, 10, 1, 0, tzinfo=UTC),
                trace_id="trace-runtime-recovery",
            )
            assert summary.interrupted_run_ids == (running_run.id,)
            assert summary.resumed_run_ids == (retry_run.id,)

            latest_running = repository.get(running_run.id)
            latest_retry = repository.get(retry_run.id)
            assert latest_running is not None
            assert latest_retry is not None
            assert latest_running.run_status == TaskRunStatus.INTERRUPTED
            assert latest_retry.run_status == TaskRunStatus.RUNNING
    finally:
        engine.dispose()


def test_runtime_exception_recovery_end_to_end(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "runtime-e2e-recovery.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            project, agent, task = _create_project_agent_task(
                session,
                tmp_path,
                title="Runtime E2E Recovery Task",
            )
            assert task.id is not None
            assert agent.id is not None

            clock = MutableClock(current=datetime(2026, 2, 7, 11, 0, 0, tzinfo=UTC))
            llm_client = SequenceLLMClient(
                [
                    LLMProviderError(
                        code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                        provider="claude_code",
                        message="temporary provider outage",
                        retryable=True,
                    ),
                    _success_response(
                        session_id="e2e-recovery",
                        token_in=90,
                        token_out=30,
                        cost_usd="0.0099",
                    ),
                ]
            )
            service = TaskRunRuntimeService(
                llm_client=llm_client,
                retry_policy=RuntimeRetryPolicy(
                    max_retry_attempts=2,
                    base_delay_seconds=5,
                    max_delay_seconds=30,
                ),
                now_factory=clock,
            )
            request = _request(session_id="e2e-recovery")

            first = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=task.id,
                    agent_id=agent.id,
                    idempotency_key=f"task-{task.id}-request-e2e",
                    request=request,
                    trace_id="trace-runtime-e2e",
                )
            )
            assert first.id is not None
            assert first.run_status == TaskRunStatus.RETRY_SCHEDULED
            assert first.next_retry_at == clock.current + timedelta(seconds=5)

            not_due = service.recover_after_restart(
                session=session,
                due_before=clock.current + timedelta(seconds=4),
            )
            assert not_due.resumed_run_ids == ()

            clock.current = clock.current + timedelta(seconds=6)
            due = service.recover_after_restart(
                session=session,
                due_before=clock.current,
            )
            assert due.resumed_run_ids == (first.id,)

            final = asyncio.run(
                service.execute_run(
                    session=session,
                    run_id=first.id,
                    request=request,
                    trace_id="trace-runtime-e2e-final",
                )
            )
            assert final.run_status == TaskRunStatus.SUCCEEDED
            assert final.token_in == 90
            assert final.token_out == 30
            assert final.cost_usd == Decimal("0.0099")

            event_id = cast(Any, Event.id)
            events = list(
                session.exec(
                    select(Event)
                    .where(Event.project_id == project.id)
                    .where(Event.event_type == "run.status.changed")
                    .order_by(event_id.asc())
                ).all()
            )
            scoped = [event for event in events if event.payload_json.get("run_id") == first.id]
            assert [event.payload_json["status"] for event in scoped] == [
                "queued",
                "running",
                "retry_scheduled",
                "running",
                "succeeded",
            ]
    finally:
        engine.dispose()


def test_runtime_error_message_is_redacted(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "runtime-redaction.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            _, agent, task = _create_project_agent_task(
                session,
                tmp_path,
                title="Runtime Redaction Task",
            )
            assert task.id is not None
            assert agent.id is not None

            llm_client = SequenceLLMClient(
                [
                    LLMProviderError(
                        code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                        provider="claude_code",
                        message="api_key=abc123 temporary outage",
                        retryable=False,
                    )
                ]
            )
            service = TaskRunRuntimeService(llm_client=llm_client)
            run = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=task.id,
                    agent_id=agent.id,
                    idempotency_key=f"task-{task.id}-request-redact",
                    request=_request(session_id="runtime-redact"),
                )
            )
            assert run.run_status == TaskRunStatus.FAILED
            assert run.error_message is not None
            assert "abc123" not in run.error_message
            assert "***REDACTED***" in run.error_message
    finally:
        engine.dispose()
