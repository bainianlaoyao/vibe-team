from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.models import Project
from app.llm import LLMResponse, LLMUsage

DEFAULT_JSON_REPORT_PATH = "../docs/reports/phase6/api_probe_report.json"
DEFAULT_MARKDOWN_REPORT_PATH = "../docs/reports/phase6/api_probe_report.md"
TRACKED_ENV_VARS = ("APP_ENV", "DATABASE_URL", "LOG_LEVEL")


@dataclass(slots=True)
class ProbeStepResult:
    name: str
    passed: bool
    latency_ms: float
    status_code: int | None
    detail: str
    failure: str | None = None


@dataclass(slots=True)
class ProbeScenarioResult:
    name: str
    steps: list[ProbeStepResult]
    duration_ms: float

    @property
    def passed(self) -> bool:
        return all(step.passed for step in self.steps)


class ProbeLLMClient:
    def __init__(self) -> None:
        self.invocation_count = 0

    async def generate(self, request: Any) -> LLMResponse:
        self.invocation_count += 1
        session_id = str(getattr(request, "session_id", "api-probe-session"))
        return LLMResponse(
            provider="claude_code",
            model="claude-sonnet-4-5",
            session_id=session_id,
            text="api probe completed",
            tool_calls=[],
            usage=LLMUsage(
                request_count=1,
                token_in=64,
                token_out=16,
                cost_usd=Decimal("0.0042"),
            ),
            stop_reason="success",
            raw_result="probe-ok",
        )


@dataclass(slots=True)
class ApiProbeContext:
    client: TestClient
    project_id: int
    llm_client: ProbeLLMClient


def _request(
    context: ApiProbeContext,
    method: str,
    path: str,
    *,
    json_payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[Any, float]:
    started = time.perf_counter()
    response = context.client.request(
        method=method,
        url=path,
        json=json_payload,
        params=params,
        headers=headers,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    return response, latency_ms


def _record_step(
    steps: list[ProbeStepResult],
    *,
    name: str,
    response: Any,
    latency_ms: float,
    validator: Any,
) -> bool:
    try:
        detail = str(validator(response))
        steps.append(
            ProbeStepResult(
                name=name,
                passed=True,
                latency_ms=round(latency_ms, 2),
                status_code=getattr(response, "status_code", None),
                detail=detail,
            )
        )
        return True
    except Exception as exc:  # noqa: BLE001
        steps.append(
            ProbeStepResult(
                name=name,
                passed=False,
                latency_ms=round(latency_ms, 2),
                status_code=getattr(response, "status_code", None),
                detail=f"response_status={getattr(response, 'status_code', None)}",
                failure=str(exc),
            )
        )
        return False


def _create_agent(context: ApiProbeContext, *, name: str) -> tuple[int, ProbeStepResult]:
    response, latency_ms = _request(
        context,
        "POST",
        "/api/v1/agents",
        json_payload={
            "project_id": context.project_id,
            "name": name,
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute probe tasks.",
            "enabled_tools_json": ["read_file_tool"],
            "status": "active",
        },
    )

    def validate(res: Any) -> str:
        if res.status_code != 201:
            raise AssertionError(f"expected 201, got {res.status_code}")
        payload = res.json()
        if payload["project_id"] != context.project_id:
            raise AssertionError("agent project mismatch")
        if not isinstance(payload["id"], int):
            raise AssertionError("agent id missing")
        return f"agent_id={payload['id']}"

    step = ProbeStepResult(
        name=f"create_agent:{name}",
        passed=False,
        latency_ms=round(latency_ms, 2),
        status_code=getattr(response, "status_code", None),
        detail=f"response_status={getattr(response, 'status_code', None)}",
    )
    try:
        detail = validate(response)
        step.passed = True
        step.detail = detail
    except Exception as exc:  # noqa: BLE001
        step.failure = str(exc)

    payload = response.json() if response.status_code == 201 else {}
    agent_id = int(payload.get("id", 0)) if payload else 0
    return agent_id, step


def _create_task(
    context: ApiProbeContext,
    *,
    title: str,
    assignee_agent_id: int | None = None,
) -> tuple[int, ProbeStepResult]:
    payload: dict[str, Any] = {
        "project_id": context.project_id,
        "title": title,
        "priority": 2,
    }
    if assignee_agent_id is not None:
        payload["assignee_agent_id"] = assignee_agent_id

    response, latency_ms = _request(
        context,
        "POST",
        "/api/v1/tasks",
        json_payload=payload,
    )

    def validate(res: Any) -> str:
        if res.status_code != 201:
            raise AssertionError(f"expected 201, got {res.status_code}")
        body = res.json()
        if body["project_id"] != context.project_id:
            raise AssertionError("task project mismatch")
        if not isinstance(body["id"], int):
            raise AssertionError("task id missing")
        return f"task_id={body['id']}"

    step = ProbeStepResult(
        name=f"create_task:{title}",
        passed=False,
        latency_ms=round(latency_ms, 2),
        status_code=getattr(response, "status_code", None),
        detail=f"response_status={getattr(response, 'status_code', None)}",
    )
    try:
        detail = validate(response)
        step.passed = True
        step.detail = detail
    except Exception as exc:  # noqa: BLE001
        step.failure = str(exc)

    body = response.json() if response.status_code == 201 else {}
    task_id = int(body.get("id", 0)) if body else 0
    return task_id, step


def _run_health_ready_scenario(context: ApiProbeContext) -> ProbeScenarioResult:
    started = time.perf_counter()
    steps: list[ProbeStepResult] = []

    health_response, health_latency = _request(context, "GET", "/healthz")
    _record_step(
        steps,
        name="healthz",
        response=health_response,
        latency_ms=health_latency,
        validator=lambda res: (
            "service healthy"
            if res.status_code == 200 and res.json().get("status") == "ok"
            else (_ for _ in ()).throw(AssertionError("healthz invalid payload"))
        ),
    )

    ready_response, ready_latency = _request(context, "GET", "/readyz")
    _record_step(
        steps,
        name="readyz",
        response=ready_response,
        latency_ms=ready_latency,
        validator=lambda res: (
            "service ready"
            if res.status_code == 200 and res.json().get("status") == "ready"
            else (_ for _ in ()).throw(AssertionError("readyz invalid payload"))
        ),
    )

    return ProbeScenarioResult(
        name="health_ready",
        steps=steps,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _run_agents_tasks_crud_scenario(context: ApiProbeContext) -> ProbeScenarioResult:
    started = time.perf_counter()
    steps: list[ProbeStepResult] = []

    agent_id, create_agent_step = _create_agent(context, name="Probe CRUD Agent")
    steps.append(create_agent_step)
    if not create_agent_step.passed:
        return ProbeScenarioResult(
            name="agents_tasks_crud",
            steps=steps,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    list_agents_response, list_agents_latency = _request(
        context,
        "GET",
        "/api/v1/agents",
        params={"project_id": context.project_id},
    )
    _record_step(
        steps,
        name="list_agents",
        response=list_agents_response,
        latency_ms=list_agents_latency,
        validator=lambda res: (
            "agent visible in list"
            if res.status_code == 200 and any(item["id"] == agent_id for item in res.json())
            else (_ for _ in ()).throw(AssertionError("agent not listed"))
        ),
    )

    get_agent_response, get_agent_latency = _request(
        context,
        "GET",
        f"/api/v1/agents/{agent_id}",
    )
    _record_step(
        steps,
        name="get_agent",
        response=get_agent_response,
        latency_ms=get_agent_latency,
        validator=lambda res: (
            "agent fetched"
            if res.status_code == 200 and res.json()["id"] == agent_id
            else (_ for _ in ()).throw(AssertionError("agent fetch failed"))
        ),
    )

    update_agent_response, update_agent_latency = _request(
        context,
        "PATCH",
        f"/api/v1/agents/{agent_id}",
        json_payload={"status": "inactive", "role": "reviewer"},
    )
    _record_step(
        steps,
        name="update_agent",
        response=update_agent_response,
        latency_ms=update_agent_latency,
        validator=lambda res: (
            "agent updated"
            if res.status_code == 200 and res.json()["status"] == "inactive"
            else (_ for _ in ()).throw(AssertionError("agent update failed"))
        ),
    )

    task_id, create_task_step = _create_task(
        context,
        title="Probe CRUD Task",
        assignee_agent_id=agent_id,
    )
    steps.append(create_task_step)
    if not create_task_step.passed:
        return ProbeScenarioResult(
            name="agents_tasks_crud",
            steps=steps,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    list_tasks_response, list_tasks_latency = _request(
        context,
        "GET",
        "/api/v1/tasks",
        params={"project_id": context.project_id},
    )
    _record_step(
        steps,
        name="list_tasks",
        response=list_tasks_response,
        latency_ms=list_tasks_latency,
        validator=lambda res: (
            "task visible in list"
            if res.status_code == 200 and any(item["id"] == task_id for item in res.json())
            else (_ for _ in ()).throw(AssertionError("task not listed"))
        ),
    )

    patch_task_response, patch_task_latency = _request(
        context,
        "PATCH",
        f"/api/v1/tasks/{task_id}",
        json_payload={"description": "updated by api probe", "priority": 1},
    )
    _record_step(
        steps,
        name="update_task",
        response=patch_task_response,
        latency_ms=patch_task_latency,
        validator=lambda res: (
            "task updated"
            if res.status_code == 200 and res.json()["priority"] == 1
            else (_ for _ in ()).throw(AssertionError("task update failed"))
        ),
    )

    get_task_response, get_task_latency = _request(
        context,
        "GET",
        f"/api/v1/tasks/{task_id}",
    )
    _record_step(
        steps,
        name="get_task",
        response=get_task_response,
        latency_ms=get_task_latency,
        validator=lambda res: (
            "task fetched"
            if res.status_code == 200 and res.json()["id"] == task_id
            else (_ for _ in ()).throw(AssertionError("task fetch failed"))
        ),
    )

    delete_task_response, delete_task_latency = _request(
        context,
        "DELETE",
        f"/api/v1/tasks/{task_id}",
    )
    _record_step(
        steps,
        name="delete_task",
        response=delete_task_response,
        latency_ms=delete_task_latency,
        validator=lambda res: (
            "task deleted"
            if res.status_code == 204
            else (_ for _ in ()).throw(AssertionError("task delete failed"))
        ),
    )

    delete_agent_response, delete_agent_latency = _request(
        context,
        "DELETE",
        f"/api/v1/agents/{agent_id}",
    )
    _record_step(
        steps,
        name="delete_agent",
        response=delete_agent_response,
        latency_ms=delete_agent_latency,
        validator=lambda res: (
            "agent deleted"
            if res.status_code == 204
            else (_ for _ in ()).throw(AssertionError("agent delete failed"))
        ),
    )

    return ProbeScenarioResult(
        name="agents_tasks_crud",
        steps=steps,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _run_run_and_commands_scenario(context: ApiProbeContext) -> ProbeScenarioResult:
    started = time.perf_counter()
    steps: list[ProbeStepResult] = []

    agent_id, create_agent_step = _create_agent(context, name="Probe Runtime Agent")
    steps.append(create_agent_step)
    if not create_agent_step.passed:
        return ProbeScenarioResult(
            name="run_and_commands",
            steps=steps,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    command_task_id, create_command_task_step = _create_task(
        context,
        title="Probe Command Task",
        assignee_agent_id=agent_id,
    )
    steps.append(create_command_task_step)
    if not create_command_task_step.passed:
        return ProbeScenarioResult(
            name="run_and_commands",
            steps=steps,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    command_calls = [
        (
            "task_start",
            "PATCH",
            f"/api/v1/tasks/{command_task_id}",
            {"status": "running"},
            "running",
        ),
        ("task_pause", "POST", f"/api/v1/tasks/{command_task_id}/pause", {}, "blocked"),
        ("task_resume", "POST", f"/api/v1/tasks/{command_task_id}/resume", {}, "running"),
        ("task_cancel", "POST", f"/api/v1/tasks/{command_task_id}/cancel", {}, "cancelled"),
        ("task_retry", "POST", f"/api/v1/tasks/{command_task_id}/retry", {}, "todo"),
    ]
    for step_name, method, path, payload, expected_status in command_calls:
        response, latency = _request(context, method, path, json_payload=payload)
        _record_step(
            steps,
            name=step_name,
            response=response,
            latency_ms=latency,
            validator=lambda res, expected=expected_status: (
                f"task status={expected}"
                if res.status_code == 200 and res.json()["status"] == expected
                else (_ for _ in ()).throw(AssertionError(f"expected status={expected}"))
            ),
        )

    run_task_id, create_run_task_step = _create_task(
        context,
        title="Probe Run Task",
        assignee_agent_id=agent_id,
    )
    steps.append(create_run_task_step)
    if not create_run_task_step.passed:
        return ProbeScenarioResult(
            name="run_and_commands",
            steps=steps,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    run_response, run_latency = _request(
        context,
        "POST",
        f"/api/v1/tasks/{run_task_id}/run",
        json_payload={
            "prompt": "run this probe task",
            "session_id": f"probe-run-{run_task_id}",
            "idempotency_key": f"probe-run-{run_task_id}-001",
            "trace_id": "trace-api-probe-run",
        },
    )
    first_run_id = 0

    def validate_run(res: Any) -> str:
        nonlocal first_run_id
        if res.status_code != 200:
            raise AssertionError(f"expected 200, got {res.status_code}")
        body = res.json()
        if body["run_status"] != "succeeded":
            raise AssertionError(f"run status mismatch: {body['run_status']}")
        first_run_id = int(body["id"])
        return f"run_id={first_run_id}"

    _record_step(
        steps,
        name="task_run",
        response=run_response,
        latency_ms=run_latency,
        validator=validate_run,
    )

    duplicate_response, duplicate_latency = _request(
        context,
        "POST",
        f"/api/v1/tasks/{run_task_id}/run",
        json_payload={
            "prompt": "run this probe task",
            "session_id": f"probe-run-{run_task_id}",
            "idempotency_key": f"probe-run-{run_task_id}-001",
        },
    )
    _record_step(
        steps,
        name="task_run_idempotent_replay",
        response=duplicate_response,
        latency_ms=duplicate_latency,
        validator=lambda res: (
            "idempotent replay confirmed"
            if (
                res.status_code == 200
                and int(res.json()["id"]) == first_run_id
                and context.llm_client.invocation_count == 1
            )
            else (_ for _ in ()).throw(AssertionError("run replay/idempotency failed"))
        ),
    )

    return ProbeScenarioResult(
        name="run_and_commands",
        steps=steps,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _run_inbox_close_scenario(context: ApiProbeContext) -> ProbeScenarioResult:
    started = time.perf_counter()
    steps: list[ProbeStepResult] = []

    agent_id, create_agent_step = _create_agent(context, name="Probe Inbox Agent")
    steps.append(create_agent_step)
    if not create_agent_step.passed:
        return ProbeScenarioResult(
            name="inbox_close_with_user_input",
            steps=steps,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    task_id, create_task_step = _create_task(
        context,
        title="Probe Inbox Task",
        assignee_agent_id=agent_id,
    )
    steps.append(create_task_step)
    if not create_task_step.passed:
        return ProbeScenarioResult(
            name="inbox_close_with_user_input",
            steps=steps,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    request_input_response, request_input_latency = _request(
        context,
        "POST",
        "/api/v1/tools/request_input",
        json_payload={
            "task_id": task_id,
            "title": "Need operator confirmation",
            "content": "Please confirm to continue probe execution.",
            "idempotency_key": f"probe-request-input-{task_id}",
        },
    )
    inbox_item_id = 0

    def validate_request_input(res: Any) -> str:
        nonlocal inbox_item_id
        if res.status_code != 200:
            raise AssertionError(f"expected 200, got {res.status_code}")
        body = res.json()
        if body["tool"] != "request_input":
            raise AssertionError("unexpected tool response")
        raw_item_id = body.get("inbox_item_id")
        if not isinstance(raw_item_id, int):
            raise AssertionError("inbox item id missing")
        inbox_item_id = raw_item_id
        return f"inbox_item_id={inbox_item_id}"

    _record_step(
        steps,
        name="tool_request_input",
        response=request_input_response,
        latency_ms=request_input_latency,
        validator=validate_request_input,
    )

    close_response, close_latency = _request(
        context,
        "POST",
        f"/api/v1/inbox/{inbox_item_id}/close",
        json_payload={
            "user_input": "approved by api probe",
            "resolver": "api-probe-user",
            "trace_id": "trace-api-probe-inbox-close",
        },
    )
    _record_step(
        steps,
        name="inbox_close",
        response=close_response,
        latency_ms=close_latency,
        validator=lambda res: (
            "inbox item closed"
            if (
                res.status_code == 200
                and res.json()["status"] == "closed"
                and res.json()["resolver"] == "api-probe-user"
            )
            else (_ for _ in ()).throw(AssertionError("inbox close failed"))
        ),
    )

    list_response, list_latency = _request(
        context,
        "GET",
        "/api/v1/inbox",
        params={"project_id": context.project_id, "status": "closed"},
    )
    _record_step(
        steps,
        name="inbox_query_closed",
        response=list_response,
        latency_ms=list_latency,
        validator=lambda res: (
            "closed item query success"
            if (res.status_code == 200 and any(item["id"] == inbox_item_id for item in res.json()))
            else (_ for _ in ()).throw(AssertionError("closed inbox query failed"))
        ),
    )

    return ProbeScenarioResult(
        name="inbox_close_with_user_input",
        steps=steps,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _normalize_sse_line(raw_line: str | bytes) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8")
    return raw_line


def _collect_sse_events(response: Any, *, expected_count: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_id: int | None = None
    current_event_type: str | None = None
    data_lines: list[str] = []

    for raw_line in response.iter_lines():
        line = _normalize_sse_line(raw_line)
        if line.startswith(":"):
            continue
        if line.startswith("id:"):
            current_id = int(line.split(":", maxsplit=1)[1].strip())
            continue
        if line.startswith("event:"):
            current_event_type = line.split(":", maxsplit=1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", maxsplit=1)[1].strip())
            continue
        if line != "":
            continue

        if current_id is not None and data_lines:
            data = json.loads("\n".join(data_lines))
            events.append({"id": current_id, "event_type": current_event_type, "data": data})
            if len(events) >= expected_count:
                break

        current_id = None
        current_event_type = None
        data_lines = []

    return events


def _run_events_stream_scenario(context: ApiProbeContext) -> ProbeScenarioResult:
    started = time.perf_counter()
    steps: list[ProbeStepResult] = []

    first_event_response, first_event_latency = _request(
        context,
        "POST",
        "/api/v1/events",
        json_payload={
            "project_id": context.project_id,
            "event_type": "run.log",
            "payload": {
                "run_id": 501,
                "task_id": 601,
                "level": "info",
                "message": "probe-event-1",
                "sequence": 1,
            },
            "trace_id": "trace-api-probe-events-1",
        },
    )
    first_event_id = 0

    def validate_first_event(res: Any) -> str:
        nonlocal first_event_id
        if res.status_code != 201:
            raise AssertionError(f"expected 201, got {res.status_code}")
        body = res.json()
        first_event_id = int(body["id"])
        if body["event_type"] != "run.log":
            raise AssertionError("unexpected event type")
        return f"event_id={first_event_id}"

    _record_step(
        steps,
        name="events_create_first",
        response=first_event_response,
        latency_ms=first_event_latency,
        validator=validate_first_event,
    )

    replay_started = time.perf_counter()
    replayed_events: list[dict[str, Any]] = []
    with context.client.stream(
        "GET",
        "/api/v1/events/stream",
        params={
            "project_id": context.project_id,
            "replay_last": 1,
            "max_events": 1,
            "batch_size": 10,
            "poll_interval_ms": 100,
        },
    ) as replay_response:
        replay_latency = (time.perf_counter() - replay_started) * 1000
        replayed_events = _collect_sse_events(replay_response, expected_count=1)
        _record_step(
            steps,
            name="events_stream_replay_last",
            response=replay_response,
            latency_ms=replay_latency,
            validator=lambda res: (
                f"replayed_event_id={replayed_events[0]['id']}"
                if (
                    res.status_code == 200
                    and len(replayed_events) == 1
                    and replayed_events[0]["id"] == first_event_id
                )
                else (_ for _ in ()).throw(AssertionError("replay_last stream failed"))
            ),
        )

    second_event_response, second_event_latency = _request(
        context,
        "POST",
        "/api/v1/events",
        json_payload={
            "project_id": context.project_id,
            "event_type": "run.log",
            "payload": {
                "run_id": 501,
                "task_id": 601,
                "level": "info",
                "message": "probe-event-2",
                "sequence": 2,
            },
            "trace_id": "trace-api-probe-events-2",
        },
    )
    second_event_id = 0

    def validate_second_event(res: Any) -> str:
        nonlocal second_event_id
        if res.status_code != 201:
            raise AssertionError(f"expected 201, got {res.status_code}")
        second_event_id = int(res.json()["id"])
        return f"event_id={second_event_id}"

    _record_step(
        steps,
        name="events_create_second",
        response=second_event_response,
        latency_ms=second_event_latency,
        validator=validate_second_event,
    )

    stream_started = time.perf_counter()
    streamed_events: list[dict[str, Any]] = []
    with context.client.stream(
        "GET",
        "/api/v1/events/stream",
        params={
            "project_id": context.project_id,
            "max_events": 1,
            "batch_size": 10,
            "poll_interval_ms": 100,
        },
        headers={"Last-Event-ID": str(first_event_id)},
    ) as stream_response:
        stream_latency = (time.perf_counter() - stream_started) * 1000
        streamed_events = _collect_sse_events(stream_response, expected_count=1)
        _record_step(
            steps,
            name="events_stream_resume",
            response=stream_response,
            latency_ms=stream_latency,
            validator=lambda res: (
                f"streamed_event_id={streamed_events[0]['id']}"
                if (
                    res.status_code == 200
                    and len(streamed_events) == 1
                    and streamed_events[0]["id"] == second_event_id
                )
                else (_ for _ in ()).throw(AssertionError("resume stream failed"))
            ),
        )

    return ProbeScenarioResult(
        name="events_query_and_stream",
        steps=steps,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )


def _build_report(scenarios: list[ProbeScenarioResult]) -> dict[str, Any]:
    all_steps = [step for scenario in scenarios for step in scenario.steps]
    passed_steps = [step for step in all_steps if step.passed]
    passed_scenarios = [scenario for scenario in scenarios if scenario.passed]
    failures = [
        {
            "scenario": scenario.name,
            "step": step.name,
            "status_code": step.status_code,
            "failure": step.failure,
            "detail": step.detail,
        }
        for scenario in scenarios
        for step in scenario.steps
        if not step.passed
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "scenario_total": len(scenarios),
            "scenario_passed": len(passed_scenarios),
            "step_total": len(all_steps),
            "step_passed": len(passed_steps),
            "pass_rate": round((len(passed_steps) / len(all_steps) * 100) if all_steps else 0.0, 2),
            "total_duration_ms": round(sum(scenario.duration_ms for scenario in scenarios), 2),
        },
        "scenarios": [
            {
                "name": scenario.name,
                "passed": scenario.passed,
                "duration_ms": scenario.duration_ms,
                "steps": [asdict(step) for step in scenario.steps],
            }
            for scenario in scenarios
        ],
        "failed_samples": failures[:10],
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines: list[str] = [
        "# API Probe Report",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- scenario_passed: {summary['scenario_passed']}/{summary['scenario_total']}",
        f"- step_passed: {summary['step_passed']}/{summary['step_total']}",
        f"- pass_rate: {summary['pass_rate']}%",
        f"- total_duration_ms: {summary['total_duration_ms']}",
        "",
    ]

    for scenario in report["scenarios"]:
        status_text = "PASS" if scenario["passed"] else "FAIL"
        lines.extend(
            [
                f"## {scenario['name']} [{status_text}]",
                "",
                f"- duration_ms: {scenario['duration_ms']}",
                "",
                "| Step | Result | HTTP | Latency(ms) | Detail |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for step in scenario["steps"]:
            result_text = "PASS" if step["passed"] else "FAIL"
            detail_text = step["detail"]
            if step["failure"]:
                detail_text = f"{detail_text}; failure={step['failure']}"
            lines.append(
                f"| {step['name']} | {result_text} | {step['status_code']} | "
                f"{step['latency_ms']} | {detail_text} |"
            )
        lines.append("")

    failed_samples = report.get("failed_samples", [])
    if failed_samples:
        lines.extend(
            [
                "## Failed Samples",
                "",
                "| Scenario | Step | HTTP | Failure |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in failed_samples:
            lines.append(
                f"| {item['scenario']} | {item['step']} | {item['status_code']} | "
                f"{item['failure']} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _write_reports(
    report: dict[str, Any],
    *,
    json_report_path: Path,
    markdown_report_path: Path,
) -> None:
    json_report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_report_path.parent.mkdir(parents=True, exist_ok=True)

    json_report_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_report_path.write_text(_render_markdown(report), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run API probe scenarios and emit structured JSON/Markdown reports.",
    )
    parser.add_argument(
        "--json-report-path",
        default=DEFAULT_JSON_REPORT_PATH,
        help="Path for JSON report output.",
    )
    parser.add_argument(
        "--markdown-report-path",
        default=DEFAULT_MARKDOWN_REPORT_PATH,
        help="Path for Markdown report output.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with code 1 when any probe step fails.",
    )
    return parser


def _snapshot_env() -> dict[str, str | None]:
    return {name: os.getenv(name) for name in TRACKED_ENV_VARS}


def _restore_env(snapshot: dict[str, str | None]) -> None:
    for name, value in snapshot.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@contextmanager
def _build_probe_context() -> Any:
    snapshot = _snapshot_env()
    with TemporaryDirectory(prefix="bbb-api-probe-") as temp_dir:
        temp_path = Path(temp_dir)
        database_path = temp_path / "api-probe.db"
        workspace_path = temp_path / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{database_path.as_posix()}"

        os.environ["APP_ENV"] = "test"
        os.environ["DATABASE_URL"] = database_url
        os.environ["LOG_LEVEL"] = "WARNING"
        get_settings.cache_clear()
        dispose_engine()

        engine = create_engine_from_url(database_url)
        SQLModel.metadata.create_all(engine)

        with Session(engine) as session:
            project = Project(name="API Probe Project", root_path=str(workspace_path.resolve()))
            session.add(project)
            session.commit()
            session.refresh(project)
            if project.id is None:
                raise RuntimeError("Failed to create probe project.")
            project_id = int(project.id)

        llm_client = ProbeLLMClient()
        try:
            from app.main import create_app

            with patch("app.api.tasks.create_llm_client", lambda **_: llm_client):
                with TestClient(create_app()) as client:
                    yield ApiProbeContext(
                        client=client,
                        project_id=project_id,
                        llm_client=llm_client,
                    )
        finally:
            engine.dispose()
            dispose_engine()
            get_settings.cache_clear()
            _restore_env(snapshot)


def _run_probe() -> list[ProbeScenarioResult]:
    with _build_probe_context() as context:
        return [
            _run_health_ready_scenario(context),
            _run_agents_tasks_crud_scenario(context),
            _run_run_and_commands_scenario(context),
            _run_inbox_close_scenario(context),
            _run_events_stream_scenario(context),
        ]


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    json_report_path = Path(args.json_report_path)
    markdown_report_path = Path(args.markdown_report_path)

    scenarios = _run_probe()
    report = _build_report(scenarios)
    _write_reports(
        report,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
    )

    summary = report["summary"]
    print(
        "api_probe: "
        f"scenarios={summary['scenario_passed']}/{summary['scenario_total']} "
        f"steps={summary['step_passed']}/{summary['step_total']} "
        f"pass_rate={summary['pass_rate']}% "
        f"json_report={json_report_path} markdown_report={markdown_report_path}"
    )

    has_failure = summary["step_passed"] != summary["step_total"]
    if has_failure and bool(args.fail_on_error):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
