from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from pytest import MonkeyPatch
from sqlmodel import Session, select

from app.core.config import Settings
from app.db.enums import TaskRunStatus
from app.db.models import Event
from app.db.repositories import TaskRunRepository
from app.llm import LLMErrorCode, LLMProviderError, LLMRequest, LLMResponse, LLMUsage
from tests.shared import ApiTestContext


class SequenceLLMClient:
    def __init__(self, outcomes: list[LLMResponse | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.invocation_count = 0
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.invocation_count += 1
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("No more fake LLM outcomes configured.")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _success_llm_response(*, session_id: str) -> LLMResponse:
    return LLMResponse(
        provider="claude_code",
        model="claude-sonnet-4-5",
        session_id=session_id,
        text="任务执行完成",
        tool_calls=[],
        usage=LLMUsage(
            request_count=1,
            token_in=80,
            token_out=20,
            cost_usd=Decimal("0.0065"),
        ),
        stop_reason="success",
        raw_result="ok",
    )


def test_agents_crud_and_validation(api_context: ApiTestContext) -> None:
    payload = {
        "project_id": api_context.project_id,
        "name": "Planning Agent",
        "role": "planner",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        "initial_persona_prompt": "Plan and coordinate implementation steps.",
        "enabled_tools_json": ["list_path_tool", "read_file_tool"],
        "status": "active",
    }

    create_response = api_context.client.post("/api/v1/agents", json=payload)
    assert create_response.status_code == 201
    created_agent = create_response.json()
    agent_id = created_agent["id"]
    assert created_agent["name"] == "Planning Agent"

    list_response = api_context.client.get(
        "/api/v1/agents",
        params={"project_id": api_context.project_id},
    )
    assert list_response.status_code == 200
    assert any(agent["id"] == agent_id for agent in list_response.json())

    get_response = api_context.client.get(f"/api/v1/agents/{agent_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "active"

    update_response = api_context.client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"status": "inactive", "role": "reviewer"},
    )
    assert update_response.status_code == 200
    updated_agent = update_response.json()
    assert updated_agent["status"] == "inactive"
    assert updated_agent["role"] == "reviewer"

    invalid_payload_response = api_context.client.post(
        "/api/v1/agents",
        json={**payload, "name": ""},
    )
    assert invalid_payload_response.status_code == 422
    assert invalid_payload_response.json()["error"]["code"] == "VALIDATION_ERROR"

    missing_project_response = api_context.client.post(
        "/api/v1/agents",
        json={**payload, "project_id": 999999},
    )
    assert missing_project_response.status_code == 404
    assert missing_project_response.json()["error"]["code"] == "PROJECT_NOT_FOUND"

    delete_response = api_context.client.delete(f"/api/v1/agents/{agent_id}")
    assert delete_response.status_code == 204

    deleted_get_response = api_context.client.get(f"/api/v1/agents/{agent_id}")
    assert deleted_get_response.status_code == 404
    assert deleted_get_response.json()["error"]["code"] == "AGENT_NOT_FOUND"


def test_tasks_crud_dependencies_and_validation(api_context: ApiTestContext) -> None:
    agent_response = api_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": api_context.project_id,
            "name": "Task Agent",
            "role": "executor",
            "model_provider": "openai",
            "model_name": "gpt-4.1-mini",
            "initial_persona_prompt": "Execute assigned tasks.",
            "enabled_tools_json": ["read_file_tool"],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    parent_task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Parent Task",
            "description": "Top-level task.",
            "priority": 1,
            "assignee_agent_id": agent_id,
        },
    )
    assert parent_task_response.status_code == 201
    parent_task_id = parent_task_response.json()["id"]

    child_task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Child Task",
            "description": "Depends on parent task.",
            "priority": 2,
            "assignee_agent_id": agent_id,
            "parent_task_id": parent_task_id,
        },
    )
    assert child_task_response.status_code == 201
    child_task_id = child_task_response.json()["id"]

    list_response = api_context.client.get(
        "/api/v1/tasks",
        params={"project_id": api_context.project_id},
    )
    assert list_response.status_code == 200
    returned_ids = {task["id"] for task in list_response.json()}
    assert parent_task_id in returned_ids
    assert child_task_id in returned_ids

    update_response = api_context.client.patch(
        f"/api/v1/tasks/{child_task_id}",
        json={"status": "running", "priority": 1},
    )
    assert update_response.status_code == 200
    updated_task = update_response.json()
    assert updated_task["status"] == "running"
    assert updated_task["priority"] == 1

    other_project_task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.other_project_id,
            "title": "Other Project Task",
            "priority": 3,
        },
    )
    assert other_project_task_response.status_code == 201
    other_project_task_id = other_project_task_response.json()["id"]

    invalid_dependency_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Invalid Dependency Task",
            "priority": 3,
            "parent_task_id": other_project_task_id,
        },
    )
    assert invalid_dependency_response.status_code == 422
    assert invalid_dependency_response.json()["error"]["code"] == "INVALID_TASK_DEPENDENCY"

    invalid_priority_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Invalid Priority",
            "priority": 9,
        },
    )
    assert invalid_priority_response.status_code == 422
    assert invalid_priority_response.json()["error"]["code"] == "VALIDATION_ERROR"

    invalid_assignee_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Invalid Assignee",
            "priority": 2,
            "assignee_agent_id": 987654,
        },
    )
    assert invalid_assignee_response.status_code == 422
    assert invalid_assignee_response.json()["error"]["code"] == "INVALID_ASSIGNEE"

    dependent_delete_response = api_context.client.delete(f"/api/v1/tasks/{parent_task_id}")
    assert dependent_delete_response.status_code == 409
    assert dependent_delete_response.json()["error"]["code"] == "TASK_HAS_DEPENDENTS"

    child_delete_response = api_context.client.delete(f"/api/v1/tasks/{child_task_id}")
    assert child_delete_response.status_code == 204
    parent_delete_response = api_context.client.delete(f"/api/v1/tasks/{parent_task_id}")
    assert parent_delete_response.status_code == 204

    deleted_task_response = api_context.client.get(f"/api/v1/tasks/{parent_task_id}")
    assert deleted_task_response.status_code == 404
    assert deleted_task_response.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_openapi_examples_for_agents_and_tasks(api_context: ApiTestContext) -> None:
    openapi_response = api_context.client.get("/openapi.json")
    assert openapi_response.status_code == 200
    schema = openapi_response.json()
    components = schema["components"]["schemas"]

    assert "example" in components["AgentCreate"]
    assert "example" in components["AgentRead"]
    assert "example" in components["TaskCreate"]
    assert "example" in components["TaskRead"]
    assert "example" in components["ErrorResponse"]


def test_create_task_rejects_non_todo_initial_status(api_context: ApiTestContext) -> None:
    response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Invalid Initial Status",
            "status": "running",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TASK_TRANSITION"


def test_task_state_machine_rejects_invalid_changes(
    api_context: ApiTestContext,
) -> None:
    create_task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Transition Validation Task",
        },
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    invalid_transition_response = api_context.client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
    )
    assert invalid_transition_response.status_code == 422
    assert invalid_transition_response.json()["error"]["code"] == "INVALID_TASK_TRANSITION"

    invalid_command_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/pause",
        json={},
    )
    assert invalid_command_response.status_code == 422
    assert invalid_command_response.json()["error"]["code"] == "INVALID_TASK_COMMAND"

    with Session(api_context.engine) as session:
        event_id = cast(Any, Event.id)
        audit_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(Event.event_type == "task.intervention.audit")
                .order_by(event_id.asc())
            ).all()
        )

    task_audit_events = [
        event for event in audit_events if event.payload_json.get("task_id") == task_id
    ]
    assert len(task_audit_events) == 1
    assert task_audit_events[0].payload_json["command"] == "pause"
    assert task_audit_events[0].payload_json["outcome"] == "rejected"
    assert task_audit_events[0].payload_json["error_code"] == "INVALID_TASK_COMMAND"


def test_task_commands_and_transitions_write_event_trace_id(api_context: ApiTestContext) -> None:
    create_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Traceable Task",
            "trace_id": "trace-create-task",
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    start_response = api_context.client.patch(
        f"/api/v1/tasks/{task_id}",
        json={
            "status": "running",
            "trace_id": "trace-start-task",
            "actor": "scheduler",
            "run_id": 8,
        },
    )
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "running"

    pause_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/pause",
        json={"actor": "operator"},
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "blocked"

    resume_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/resume",
        json={"trace_id": "trace-resume-task"},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "running"

    cancel_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"trace_id": "trace-cancel-task"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    with Session(api_context.engine) as session:
        event_id = cast(Any, Event.id)
        events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(Event.event_type == "task.status.changed")
                .order_by(event_id.asc())
            ).all()
        )
        security_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(
                    cast(Any, Event.event_type).in_(
                        ["security.audit.allowed", "security.audit.denied"]
                    )
                )
                .order_by(event_id.asc())
            ).all()
        )

    task_events = [event for event in events if event.payload_json.get("task_id") == task_id]
    assert [event.payload_json["status"] for event in task_events] == [
        "todo",
        "running",
        "blocked",
        "running",
        "cancelled",
    ]
    assert all(event.trace_id for event in task_events)
    assert task_events[0].trace_id == "trace-create-task"
    assert task_events[1].trace_id == "trace-start-task"
    assert task_events[3].trace_id == "trace-resume-task"
    assert task_events[4].trace_id == "trace-cancel-task"
    assert len(security_events) == 3
    assert {event.event_type for event in security_events} == {"security.audit.allowed"}
    assert {event.payload_json["action"] for event in security_events} == {
        "task.pause",
        "task.resume",
        "task.cancel",
    }


def test_broadcast_pause_applies_to_running_tasks_and_writes_audit_events(
    api_context: ApiTestContext,
) -> None:
    created_ids: list[int] = []
    for title in ("Broadcast Run 1", "Broadcast Run 2", "Broadcast Todo"):
        response = api_context.client.post(
            "/api/v1/tasks",
            json={
                "project_id": api_context.project_id,
                "title": title,
            },
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    running_task_ids = created_ids[:2]
    for task_id in running_task_ids:
        start_response = api_context.client.patch(
            f"/api/v1/tasks/{task_id}",
            json={
                "status": "running",
                "trace_id": f"trace-start-{task_id}",
            },
        )
        assert start_response.status_code == 200
        assert start_response.json()["status"] == "running"

    broadcast_response = api_context.client.post(
        "/api/v1/tasks/broadcast/pause",
        json={
            "project_id": api_context.project_id,
            "status": "running",
            "actor": "operator",
            "trace_id": "trace-broadcast-pause",
        },
    )
    assert broadcast_response.status_code == 200
    payload = broadcast_response.json()
    assert payload["command"] == "pause"
    assert payload["total_targets"] == 2
    assert payload["applied_count"] == 2
    assert payload["failed_count"] == 0
    assert {item["task_id"] for item in payload["items"]} == set(running_task_ids)
    assert all(item["outcome"] == "applied" for item in payload["items"])

    for task_id in running_task_ids:
        task_response = api_context.client.get(f"/api/v1/tasks/{task_id}")
        assert task_response.status_code == 200
        assert task_response.json()["status"] == "blocked"

    todo_response = api_context.client.get(f"/api/v1/tasks/{created_ids[2]}")
    assert todo_response.status_code == 200
    assert todo_response.json()["status"] == "todo"

    with Session(api_context.engine) as session:
        event_id = cast(Any, Event.id)
        audit_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(Event.event_type == "task.intervention.audit")
                .order_by(event_id.asc())
            ).all()
        )
    scoped_events = [
        event
        for event in audit_events
        if event.payload_json.get("task_id") in set(running_task_ids)
    ]
    assert len(scoped_events) == 2
    assert {event.payload_json["source"] for event in scoped_events} == {"broadcast"}
    assert {event.payload_json["command"] for event in scoped_events} == {"pause"}
    assert {event.payload_json["outcome"] for event in scoped_events} == {"applied"}


def test_task_command_expected_version_conflict_writes_audit_event(
    api_context: ApiTestContext,
) -> None:
    create_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Version Guarded Task",
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    start_response = api_context.client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "running", "trace_id": "trace-start-version"},
    )
    assert start_response.status_code == 200
    expected_version = start_response.json()["version"]

    first_pause_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/pause",
        json={"expected_version": expected_version, "trace_id": "trace-pause-v1"},
    )
    assert first_pause_response.status_code == 200
    assert first_pause_response.json()["status"] == "blocked"
    assert first_pause_response.json()["version"] == expected_version + 1

    stale_pause_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/pause",
        json={"expected_version": expected_version, "trace_id": "trace-pause-stale"},
    )
    assert stale_pause_response.status_code == 409
    assert stale_pause_response.json()["error"]["code"] == "TASK_VERSION_CONFLICT"

    with Session(api_context.engine) as session:
        event_id = cast(Any, Event.id)
        audit_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(Event.event_type == "task.intervention.audit")
                .order_by(event_id.asc())
            ).all()
        )
        security_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(
                    cast(Any, Event.event_type).in_(
                        ["security.audit.allowed", "security.audit.denied"]
                    )
                )
                .order_by(event_id.asc())
            ).all()
        )
    task_audits = [event for event in audit_events if event.payload_json.get("task_id") == task_id]
    assert len(task_audits) == 2
    assert [event.payload_json["outcome"] for event in task_audits] == ["applied", "conflict"]
    conflict_payload = task_audits[1].payload_json
    assert conflict_payload["expected_version"] == expected_version
    assert conflict_payload["actual_version"] == expected_version + 1
    assert conflict_payload["error_code"] == "TASK_VERSION_CONFLICT"
    assert len(security_events) == 2
    assert [event.event_type for event in security_events] == [
        "security.audit.allowed",
        "security.audit.denied",
    ]
    assert "TASK_VERSION_CONFLICT" in str(security_events[1].payload_json["reason"])


def test_run_task_endpoint_executes_and_is_idempotent(
    api_context: ApiTestContext,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_llm = SequenceLLMClient([_success_llm_response(session_id="task-run-1")])
    monkeypatch.setattr(
        "app.api.tasks.create_llm_client",
        lambda **_: fake_llm,
    )

    agent_response = api_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": api_context.project_id,
            "name": "Run Agent",
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute tasks.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Run Me",
            "assignee_agent_id": agent_id,
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    first_run_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "执行该任务并返回一句话总结",
            "session_id": "task-run-1",
            "idempotency_key": f"task-{task_id}-run-001",
            "trace_id": "trace-task-run-1",
        },
    )
    assert first_run_response.status_code == 200
    first_payload = first_run_response.json()
    assert first_payload["task_id"] == task_id
    assert first_payload["run_status"] == "succeeded"
    assert first_payload["attempt"] == 1
    assert first_payload["token_in"] == 80
    assert first_payload["token_out"] == 20
    assert first_payload["cost_usd"] == "0.0065"
    assert fake_llm.invocation_count == 1
    assert len(fake_llm.requests) == 1
    assert fake_llm.requests[0].cwd == api_context.project_root

    duplicate_run_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "执行该任务并返回一句话总结",
            "session_id": "task-run-1",
            "idempotency_key": f"task-{task_id}-run-001",
        },
    )
    assert duplicate_run_response.status_code == 200
    duplicate_payload = duplicate_run_response.json()
    assert duplicate_payload["id"] == first_payload["id"]
    assert duplicate_payload["run_status"] == "succeeded"
    assert fake_llm.invocation_count == 1

    run_logs_response = api_context.client.get(
        "/api/v1/logs",
        params={
            "project_id": api_context.project_id,
            "run_id": first_payload["id"],
        },
    )
    assert run_logs_response.status_code == 200
    run_logs = run_logs_response.json()
    assert len(run_logs) == 1
    assert run_logs[0]["run_id"] == first_payload["id"]
    assert run_logs[0]["message"] == "任务执行完成"

    task_state_response = api_context.client.get(f"/api/v1/tasks/{task_id}")
    assert task_state_response.status_code == 200
    assert task_state_response.json()["status"] == "review"

    with Session(api_context.engine) as session:
        event_id = cast(Any, Event.id)
        task_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(Event.event_type == "task.status.changed")
                .order_by(event_id.asc())
            ).all()
        )
        run_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == api_context.project_id)
                .where(Event.event_type == "run.status.changed")
                .order_by(event_id.asc())
            ).all()
        )

    scoped_task_events = [
        event for event in task_events if event.payload_json.get("task_id") == task_id
    ]
    assert [event.payload_json["status"] for event in scoped_task_events] == [
        "todo",
        "running",
        "review",
    ]

    run_id = first_payload["id"]
    scoped_run_events = [
        event for event in run_events if event.payload_json.get("run_id") == run_id
    ]
    assert [event.payload_json["status"] for event in scoped_run_events] == [
        "queued",
        "running",
        "succeeded",
    ]


def test_run_task_endpoint_prefers_configured_project_root_for_cwd(
    api_context: ApiTestContext,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_llm = SequenceLLMClient([_success_llm_response(session_id="task-run-cwd-1")])
    monkeypatch.setattr("app.api.tasks.create_llm_client", lambda **_: fake_llm)
    configured_root = Path("E:/beebeebrain/play_ground")
    monkeypatch.setattr(
        "app.api.tasks.get_settings",
        lambda: Settings(project_root=configured_root, database_url="sqlite:///./ignored.db"),
    )

    agent_response = api_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": api_context.project_id,
            "name": "Cwd Agent",
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute tasks.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Run With Configured Cwd",
            "assignee_agent_id": agent_id,
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    run_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "执行并确认 cwd",
            "session_id": "task-run-cwd-1",
            "idempotency_key": f"task-{task_id}-run-cwd-001",
            "trace_id": "trace-task-run-cwd-1",
        },
    )
    assert run_response.status_code == 200
    assert len(fake_llm.requests) == 1
    assert fake_llm.requests[0].cwd == configured_root


def test_run_task_endpoint_creates_task_completed_inbox_item(
    api_context: ApiTestContext,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_llm = SequenceLLMClient([_success_llm_response(session_id="task-run-inbox-1")])
    monkeypatch.setattr(
        "app.api.tasks.create_llm_client",
        lambda **_: fake_llm,
    )

    agent_response = api_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": api_context.project_id,
            "name": "Inbox Agent",
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute tasks.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Inbox Completion Task",
            "assignee_agent_id": agent_id,
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    idempotency_key = f"task-{task_id}-run-inbox-001"
    run_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "执行后通知 inbox",
            "session_id": "task-run-inbox-1",
            "idempotency_key": idempotency_key,
            "trace_id": "trace-task-run-inbox-1",
        },
    )
    assert run_response.status_code == 200
    assert run_response.json()["run_status"] == "succeeded"

    inbox_response = api_context.client.get(
        "/api/v1/inbox",
        params={"project_id": api_context.project_id, "item_type": "task_completed"},
    )
    assert inbox_response.status_code == 200
    inbox_items = inbox_response.json()
    assert len(inbox_items) == 1
    assert inbox_items[0]["source_type"] == "task"
    assert inbox_items[0]["source_id"] == f"task:{task_id}"
    assert inbox_items[0]["status"] == "open"

    duplicate_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "执行后通知 inbox",
            "session_id": "task-run-inbox-1",
            "idempotency_key": idempotency_key,
        },
    )
    assert duplicate_response.status_code == 200

    duplicate_inbox_response = api_context.client.get(
        "/api/v1/inbox",
        params={"project_id": api_context.project_id, "item_type": "task_completed"},
    )
    assert duplicate_inbox_response.status_code == 200
    assert len(duplicate_inbox_response.json()) == 1


def test_run_task_endpoint_blocks_new_idempotency_when_active_run_exists(
    api_context: ApiTestContext,
    monkeypatch: MonkeyPatch,
) -> None:
    def _fail_create_llm_client(**_: Any) -> None:
        raise AssertionError("create_llm_client should not be called")

    monkeypatch.setattr(
        "app.api.tasks.create_llm_client",
        _fail_create_llm_client,
    )

    agent_response = api_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": api_context.project_id,
            "name": "Guard Agent",
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute tasks.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Guarded Task",
            "assignee_agent_id": agent_id,
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    active_key = f"task-{task_id}-active-001"
    with Session(api_context.engine) as session:
        repository = TaskRunRepository(session)
        run = repository.create_for_task(
            task_id=task_id,
            agent_id=agent_id,
            idempotency_key=active_key,
        )
        assert run.id is not None
        run = repository.mark_running(
            run_id=run.id,
            expected_version=run.version,
        )
        active_run_id = run.id

    same_key_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "重复请求",
            "idempotency_key": active_key,
        },
    )
    assert same_key_response.status_code == 200
    same_key_payload = same_key_response.json()
    assert same_key_payload["id"] == active_run_id
    assert same_key_payload["run_status"] == TaskRunStatus.RUNNING.value

    different_key_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "新启动请求",
            "idempotency_key": f"task-{task_id}-active-002",
        },
    )
    assert different_key_response.status_code == 409
    assert different_key_response.json()["error"]["code"] == "TASK_RUN_ALREADY_ACTIVE"


def test_run_task_endpoint_writes_messages_to_bound_conversation(
    api_context: ApiTestContext,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_llm = SequenceLLMClient([_success_llm_response(session_id="task-run-conversation-1")])
    monkeypatch.setattr(
        "app.api.tasks.create_llm_client",
        lambda **_: fake_llm,
    )

    agent_response = api_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": api_context.project_id,
            "name": "Conversation Bound Agent",
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute tasks.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Conversation Bound Task",
            "assignee_agent_id": agent_id,
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    conversation_response = api_context.client.post(
        "/api/v1/conversations",
        json={
            "project_id": api_context.project_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "title": f"Task #{task_id}: Conversation Bound Task",
        },
    )
    assert conversation_response.status_code == 201
    conversation_id = conversation_response.json()["id"]

    prompt_text = "执行该任务并返回一句话总结"
    run_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": prompt_text,
            "session_id": "task-run-conversation-1",
            "conversation_id": conversation_id,
            "idempotency_key": f"task-{task_id}-run-conversation-001",
            "trace_id": "trace-task-run-conversation-1",
        },
    )
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["run_status"] == "succeeded"

    messages_response = api_context.client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        params={"limit": 50},
    )
    assert messages_response.status_code == 200
    messages_payload = messages_response.json()
    items = messages_payload["items"]
    assert len(items) == 2
    assert items[0]["role"] == "user"
    assert items[0]["message_type"] == "text"
    assert items[0]["content"] == prompt_text
    assert items[0]["metadata_json"]["source"] == "task_run"
    assert items[0]["metadata_json"]["kind"] == "run_prompt"
    assert items[1]["role"] == "assistant"
    assert items[1]["message_type"] == "text"
    assert items[1]["content"] == "任务执行完成"
    assert items[1]["metadata_json"]["source"] == "task_run"
    assert items[1]["metadata_json"]["kind"] == "run_result"
    assert items[1]["metadata_json"]["run_status"] == "succeeded"
    assert fake_llm.invocation_count == 1


def test_run_task_endpoint_retryable_failure_schedules_retry(
    api_context: ApiTestContext,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_llm = SequenceLLMClient(
        [
            LLMProviderError(
                code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                provider="claude_code",
                message="temporary outage",
                retryable=True,
            )
        ]
    )
    monkeypatch.setattr(
        "app.api.tasks.create_llm_client",
        lambda **_: fake_llm,
    )

    agent_response = api_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": api_context.project_id,
            "name": "Retry Agent",
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute tasks.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    task_response = api_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": api_context.project_id,
            "title": "Retry Me",
            "assignee_agent_id": agent_id,
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    run_response = api_context.client.post(
        f"/api/v1/tasks/{task_id}/run",
        json={
            "prompt": "执行并在失败时重试",
            "idempotency_key": f"task-{task_id}-run-retry-001",
        },
    )
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["run_status"] == "retry_scheduled"
    assert payload["next_retry_at"] is not None
    assert payload["error_code"] == "LLM_PROVIDER_UNAVAILABLE"
    assert fake_llm.invocation_count == 1

    task_state_response = api_context.client.get(f"/api/v1/tasks/{task_id}")
    assert task_state_response.status_code == 200
    assert task_state_response.json()["status"] == "running"
