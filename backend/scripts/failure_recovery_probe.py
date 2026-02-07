from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlmodel import Session, SQLModel

from app.db.engine import create_engine_from_url
from app.db.enums import AgentStatus, TaskRunStatus, TaskStatus
from app.db.models import Agent, Project, Task
from app.db.repositories import TaskRunRepository
from app.llm.contracts import LLMMessage, LLMRequest, LLMResponse, LLMRole, LLMUsage
from app.runtime import (
    FAILURE_POINT_BEFORE_LLM,
    FailureInjectionRule,
    FailureInjectorStub,
    FailureMode,
    RuntimeRetryPolicy,
    TaskRunRuntimeService,
)

DEFAULT_JSON_REPORT_PATH = "../docs/reports/phase6/failure_recovery_report.json"
DEFAULT_MARKDOWN_REPORT_PATH = "../docs/reports/phase6/failure_recovery_report.md"


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
            raise AssertionError("No LLM outcomes left for failure recovery probe.")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@dataclass(slots=True)
class ScenarioResult:
    name: str
    passed: bool
    duration_ms: float
    detail: dict[str, Any]
    error: str | None = None


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _request(*, session_id: str) -> LLMRequest:
    return LLMRequest(
        provider="claude_code",
        model="claude-sonnet-4-5",
        session_id=session_id,
        messages=[LLMMessage(role=LLMRole.USER, content="execute failure probe")],
        system_prompt="You are a runtime regression probe.",
    )


def _success_response(*, session_id: str, cost: str = "0.0050") -> LLMResponse:
    return LLMResponse(
        provider="claude_code",
        model="claude-sonnet-4-5",
        session_id=session_id,
        text="ok",
        tool_calls=[],
        usage=LLMUsage(
            request_count=1,
            token_in=60,
            token_out=20,
            cost_usd=Decimal(cost),
        ),
        stop_reason="success",
        raw_result="probe-ok",
    )


def _create_project_agent_task(
    session: Session,
    root_path: Path,
    *,
    title: str,
) -> tuple[Project, Agent, Task]:
    project = Project(name="Failure Probe Project", root_path=str(root_path))
    session.add(project)
    session.flush()

    agent = Agent(
        project_id=project.id,
        name=f"{title}-agent",
        role="executor",
        model_provider="claude_code",
        model_name="claude-sonnet-4-5",
        initial_persona_prompt="probe agent",
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


def _scenario_timeout_backoff(temp_root: Path) -> dict[str, Any]:
    db_url = _to_sqlite_url(temp_root / "timeout_backoff.db")
    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            _, agent, task = _create_project_agent_task(
                session,
                temp_root / "timeout-workspace",
                title="timeout-backoff",
            )
            clock = MutableClock(current=datetime(2026, 2, 7, 9, 0, 0, tzinfo=UTC))
            injector = FailureInjectorStub(
                [FailureInjectionRule(mode=FailureMode.TIMEOUT, point=FAILURE_POINT_BEFORE_LLM)]
            )
            llm_client = SequenceLLMClient([_success_response(session_id="timeout-backoff")])
            service = TaskRunRuntimeService(
                llm_client=llm_client,
                retry_policy=RuntimeRetryPolicy(max_retry_attempts=3, base_delay_seconds=10),
                failure_injector=injector,
                now_factory=clock,
            )
            first = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=int(task.id),
                    agent_id=int(agent.id),
                    idempotency_key="timeout-backoff-001",
                    request=_request(session_id="timeout-backoff"),
                )
            )
            assert first.run_status == TaskRunStatus.RETRY_SCHEDULED
            assert first.next_retry_at == clock.current + timedelta(seconds=10)
            clock.current = clock.current + timedelta(seconds=11)
            resumed = service.resume_due_retries(session=session, due_before=clock.current)
            final = asyncio.run(
                service.execute_run(
                    session=session,
                    run_id=int(first.id),
                    request=_request(session_id="timeout-backoff"),
                )
            )
            assert final.run_status == TaskRunStatus.SUCCEEDED
            return {
                "first_status": first.run_status.value,
                "resumed_run_ids": [int(item.id) for item in resumed if item.id is not None],
                "final_status": final.run_status.value,
            }
    finally:
        engine.dispose()


def _scenario_transient_retry(temp_root: Path) -> dict[str, Any]:
    db_url = _to_sqlite_url(temp_root / "transient_retry.db")
    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            _, agent, task = _create_project_agent_task(
                session,
                temp_root / "transient-workspace",
                title="transient-retry",
            )
            clock = MutableClock(current=datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC))
            injector = FailureInjectorStub(
                [
                    FailureInjectionRule(
                        mode=FailureMode.TRANSIENT_ERROR,
                        point=FAILURE_POINT_BEFORE_LLM,
                    )
                ]
            )
            llm_client = SequenceLLMClient([_success_response(session_id="transient-retry")])
            service = TaskRunRuntimeService(
                llm_client=llm_client,
                retry_policy=RuntimeRetryPolicy(max_retry_attempts=2, base_delay_seconds=5),
                failure_injector=injector,
                now_factory=clock,
            )
            first = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=int(task.id),
                    agent_id=int(agent.id),
                    idempotency_key="transient-retry-001",
                    request=_request(session_id="transient-retry"),
                )
            )
            assert first.run_status == TaskRunStatus.RETRY_SCHEDULED
            clock.current = clock.current + timedelta(seconds=6)
            resumed = service.resume_due_retries(session=session, due_before=clock.current)
            final = asyncio.run(
                service.execute_run(
                    session=session,
                    run_id=int(first.id),
                    request=_request(session_id="transient-retry"),
                )
            )
            assert final.run_status == TaskRunStatus.SUCCEEDED
            return {
                "first_status": first.run_status.value,
                "resumed_count": len(resumed),
                "final_status": final.run_status.value,
            }
    finally:
        engine.dispose()


def _scenario_duplicate_request_idempotency(temp_root: Path) -> dict[str, Any]:
    db_url = _to_sqlite_url(temp_root / "idempotency.db")
    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            _, agent, task = _create_project_agent_task(
                session,
                temp_root / "idempotency-workspace",
                title="idempotency",
            )
            llm_client = SequenceLLMClient([_success_response(session_id="idempotency")])
            service = TaskRunRuntimeService(llm_client=llm_client)
            request = _request(session_id="idempotency")
            first = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=int(task.id),
                    agent_id=int(agent.id),
                    idempotency_key="idempotency-001",
                    request=request,
                )
            )
            second = asyncio.run(
                service.execute_task(
                    session=session,
                    task_id=int(task.id),
                    agent_id=int(agent.id),
                    idempotency_key="idempotency-001",
                    request=request,
                )
            )
            assert first.id == second.id
            assert second.run_status == TaskRunStatus.SUCCEEDED
            assert llm_client.invocation_count == 1
            return {
                "run_id": int(first.id),
                "second_status": second.run_status.value,
                "llm_invocations": llm_client.invocation_count,
            }
    finally:
        engine.dispose()


def _scenario_restart_recovery(temp_root: Path) -> dict[str, Any]:
    db_url = _to_sqlite_url(temp_root / "restart_recovery.db")
    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            _, agent, running_task = _create_project_agent_task(
                session,
                temp_root / "restart-running-workspace",
                title="restart-running",
            )
            _, _, retry_task = _create_project_agent_task(
                session,
                temp_root / "restart-retry-workspace",
                title="restart-retry",
            )
            repository = TaskRunRepository(session)
            running_run = repository.create_for_task(
                task_id=int(running_task.id),
                agent_id=int(agent.id),
                idempotency_key="restart-running-001",
            )
            running_run = repository.mark_running(
                run_id=int(running_run.id),
                expected_version=running_run.version,
            )
            retry_run = repository.create_for_task(
                task_id=int(retry_task.id),
                agent_id=int(agent.id),
                idempotency_key="restart-retry-001",
            )
            retry_run = repository.mark_running(
                run_id=int(retry_run.id),
                expected_version=retry_run.version,
            )
            retry_run = repository.mark_failed(
                run_id=int(retry_run.id),
                expected_version=retry_run.version,
                error_code="TEMP_UPSTREAM",
                error_message="retry later",
                next_retry_at=datetime(2026, 2, 7, 11, 0, 0, tzinfo=UTC),
            )
            service = TaskRunRuntimeService(llm_client=SequenceLLMClient([]))
            summary = service.recover_after_restart(
                session=session,
                due_before=datetime(2026, 2, 7, 11, 1, 0, tzinfo=UTC),
            )
            latest_running = repository.get(int(running_run.id))
            latest_retry = repository.get(int(retry_run.id))
            assert latest_running is not None
            assert latest_running.run_status == TaskRunStatus.INTERRUPTED
            assert latest_retry is not None and latest_retry.run_status == TaskRunStatus.RUNNING
            return {
                "interrupted_run_ids": list(summary.interrupted_run_ids),
                "resumed_run_ids": list(summary.resumed_run_ids),
            }
    finally:
        engine.dispose()


SCENARIOS: list[tuple[str, Callable[[Path], dict[str, Any]]]] = [
    ("timeout_backoff", _scenario_timeout_backoff),
    ("transient_retry", _scenario_transient_retry),
    ("duplicate_request_idempotency", _scenario_duplicate_request_idempotency),
    ("restart_recovery", _scenario_restart_recovery),
]


def _execute_scenarios() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for name, runner in SCENARIOS:
        with TemporaryDirectory(prefix=f"bbb-{name}-") as temp_dir:
            started = time.perf_counter()
            try:
                detail = runner(Path(temp_dir))
                results.append(
                    ScenarioResult(
                        name=name,
                        passed=True,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                        detail=detail,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    ScenarioResult(
                        name=name,
                        passed=False,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                        detail={},
                        error=str(exc),
                    )
                )
    return results


def _build_report(results: list[ScenarioResult]) -> dict[str, Any]:
    passed = [result for result in results if result.passed]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "scenario_total": len(results),
            "scenario_passed": len(passed),
            "pass_rate": round((len(passed) / len(results) * 100) if results else 0.0, 2),
            "total_duration_ms": round(sum(result.duration_ms for result in results), 2),
        },
        "scenarios": [asdict(result) for result in results],
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Failure Recovery Probe Report",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- scenario_passed: {summary['scenario_passed']}/{summary['scenario_total']}",
        f"- pass_rate: {summary['pass_rate']}%",
        f"- total_duration_ms: {summary['total_duration_ms']}",
        "",
        "| Scenario | Result | Duration(ms) | Detail |",
        "| --- | --- | ---: | --- |",
    ]
    for item in report["scenarios"]:
        result = "PASS" if item["passed"] else "FAIL"
        detail = json.dumps(item["detail"], ensure_ascii=True) if item["detail"] else "-"
        if item["error"] is not None:
            detail = f"error={item['error']}"
        lines.append(f"| {item['name']} | {result} | {item['duration_ms']} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run failure recovery regression probe.")
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--fail-on-error", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    json_path = Path(args.json_report_path)
    markdown_path = Path(args.markdown_report_path)

    results = _execute_scenarios()
    report = _build_report(results)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(
        "failure_recovery_probe: "
        f"scenarios={summary['scenario_passed']}/{summary['scenario_total']} "
        f"pass_rate={summary['pass_rate']}% "
        f"json_report={json_path} markdown_report={markdown_path}"
    )

    if bool(args.fail_on_error) and summary["scenario_passed"] != summary["scenario_total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
