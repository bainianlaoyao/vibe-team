from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import (
    AgentStatus,
    InboxItemType,
    InboxStatus,
    SourceType,
    TaskRunStatus,
    TaskStatus,
)
from app.db.models import Agent, ApiUsageDaily, Event, InboxItem, Project, Task, TaskRun
from app.events.schemas import (
    RUN_LOG_EVENT_TYPE,
    RUN_STATUS_CHANGED_EVENT_TYPE,
    TASK_STATUS_CHANGED_EVENT_TYPE,
    build_run_status_payload,
    build_task_status_payload,
)
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class Phase8Context:
    client: TestClient
    engine: Engine
    project_id: int
    agent_id: int
    task_id: int
    inbox_id: int
    workspace_root: Path


@pytest.fixture
def phase8_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[Phase8Context]:
    db_url = _to_sqlite_url(tmp_path / "phase8-api.db")
    workspace_root = (tmp_path / "workspace").resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "README.md").write_text(
        "# Phase 8\n\nIntegration target.\n",
        encoding="utf-8",
    )
    (workspace_root / "docs").mkdir(parents=True, exist_ok=True)
    (workspace_root / "docs" / "overview.md").write_text("Overview\n", encoding="utf-8")
    (workspace_root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:5173")
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(name="Phase8 Project", root_path=str(workspace_root))
        session.add(project)
        session.flush()
        assert project.id is not None

        agent = Agent(
            project_id=project.id,
            name="Phase8 Agent",
            role="executor",
            model_provider="claude_code",
            model_name="claude-sonnet-4-5",
            initial_persona_prompt="Execute integration tasks.",
            enabled_tools_json=["read_file_tool"],
            status=AgentStatus.ACTIVE,
        )
        session.add(agent)
        session.flush()
        assert agent.id is not None

        task = Task(
            project_id=project.id,
            title="Phase8 Task",
            description="Integration task.",
            status=TaskStatus.RUNNING,
            priority=2,
            assignee_agent_id=agent.id,
        )
        blocked_task = Task(
            project_id=project.id,
            title="Blocked Task",
            description="Needs input.",
            status=TaskStatus.BLOCKED,
            priority=3,
            assignee_agent_id=agent.id,
        )
        session.add(task)
        session.add(blocked_task)
        session.flush()
        assert task.id is not None

        run = TaskRun(
            task_id=task.id,
            agent_id=agent.id,
            run_status=TaskRunStatus.FAILED,
            attempt=1,
            token_in=120,
            token_out=30,
            cost_usd=Decimal("0.0142"),
            error_code="LLM_TIMEOUT",
        )
        session.add(run)
        session.flush()
        assert run.id is not None

        inbox_item = InboxItem(
            project_id=project.id,
            source_type=SourceType.TASK,
            source_id=f"task:{blocked_task.id}",
            item_type=InboxItemType.AWAIT_USER_INPUT,
            title="Need release decision",
            content="Choose release branch.",
            status=InboxStatus.OPEN,
        )
        session.add(inbox_item)
        session.flush()
        assert inbox_item.id is not None

        session.add(
            Event(
                project_id=project.id,
                event_type=TASK_STATUS_CHANGED_EVENT_TYPE,
                payload_json=build_task_status_payload(
                    task_id=task.id,
                    previous_status=TaskStatus.TODO,
                    status=TaskStatus.RUNNING,
                    run_id=run.id,
                    actor="scheduler",
                ),
                trace_id="trace-phase8-task",
            )
        )
        session.add(
            Event(
                project_id=project.id,
                event_type=RUN_STATUS_CHANGED_EVENT_TYPE,
                payload_json=build_run_status_payload(
                    run_id=run.id,
                    task_id=task.id,
                    previous_status=TaskRunStatus.RUNNING,
                    status=TaskRunStatus.FAILED,
                    attempt=run.attempt,
                    idempotency_key=run.idempotency_key,
                    error_code=run.error_code,
                    actor="runtime",
                ),
                trace_id="trace-phase8-run",
            )
        )
        session.add(
            Event(
                project_id=project.id,
                event_type=RUN_LOG_EVENT_TYPE,
                payload_json={
                    "run_id": run.id,
                    "task_id": task.id,
                    "level": "error",
                    "message": "Request timeout while waiting for provider response.",
                    "sequence": 1,
                },
                trace_id="trace-phase8-log",
            )
        )
        session.add(
            Event(
                project_id=project.id,
                event_type="inbox.item.created",
                payload_json={"item_id": inbox_item.id, "project_id": project.id},
                trace_id="trace-phase8-inbox-create",
            )
        )

        session.add(
            ApiUsageDaily(
                provider="claude_code",
                model_name="claude-sonnet-4-5",
                date=date(2026, 2, 7),
                request_count=4,
                token_in=220,
                token_out=70,
                cost_usd=Decimal("0.0420"),
            )
        )
        session.add(
            ApiUsageDaily(
                provider="openai",
                model_name="gpt-4.1-mini",
                date=date(2026, 2, 7),
                request_count=2,
                token_in=80,
                token_out=20,
                cost_usd=Decimal("0.0060"),
            )
        )
        session.commit()
        project_id = project.id
        agent_id = agent.id
        task_id = task.id
        inbox_id = inbox_item.id

    with TestClient(create_app()) as client:
        yield Phase8Context(
            client=client,
            engine=engine,
            project_id=project_id,
            agent_id=agent_id,
            task_id=task_id,
            inbox_id=inbox_id,
            workspace_root=workspace_root,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_dashboard_stats_and_updates(phase8_context: Phase8Context) -> None:
    stats_response = phase8_context.client.get(
        "/api/v1/tasks/stats",
        params={"project_id": phase8_context.project_id},
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["running"] == 1
    assert stats["blocked"] == 1
    assert stats["total"] == 2

    updates_response = phase8_context.client.get(
        "/api/v1/updates",
        params={"project_id": phase8_context.project_id, "limit": 10},
    )
    assert updates_response.status_code == 200
    updates = updates_response.json()
    assert len(updates) >= 2
    assert any(update["event_type"] == RUN_LOG_EVENT_TYPE for update in updates)


def test_agent_health_endpoint(phase8_context: Phase8Context) -> None:
    response = phase8_context.client.get(f"/api/v1/agents/{phase8_context.agent_id}/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == phase8_context.agent_id
    assert 0 <= payload["health"] <= 100
    assert payload["blocked_task_count"] == 1


def test_mark_inbox_read_and_list_flag(phase8_context: Phase8Context) -> None:
    read_response = phase8_context.client.patch(
        f"/api/v1/inbox/{phase8_context.inbox_id}/read",
        json={"reader": "tester", "trace_id": "trace-read-1"},
    )
    assert read_response.status_code == 200
    assert read_response.json()["is_read"] is True

    list_response = phase8_context.client.get(
        "/api/v1/inbox",
        params={"project_id": phase8_context.project_id},
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    inbox_row = next(item for item in listed if item["id"] == phase8_context.inbox_id)
    assert inbox_row["is_read"] is True


def test_files_tree_content_and_permissions(phase8_context: Phase8Context) -> None:
    tree_response = phase8_context.client.get(
        "/api/v1/files",
        params={"project_id": phase8_context.project_id, "path": ".", "max_depth": 2},
    )
    assert tree_response.status_code == 200
    root = tree_response.json()["root"]
    readme_node = next(child for child in root["children"] if child["name"] == "README.md")
    readme_id = readme_node["id"]

    content_response = phase8_context.client.get(
        f"/api/v1/files/{readme_id}/content",
        params={"project_id": phase8_context.project_id},
    )
    assert content_response.status_code == 200
    content_payload = content_response.json()
    assert "Phase 8" in cast(str, content_payload["content"])

    permission_response = phase8_context.client.patch(
        f"/api/v1/files/{readme_id}/permissions",
        json={
            "project_id": phase8_context.project_id,
            "permission": "none",
        },
    )
    assert permission_response.status_code == 200
    assert permission_response.json()["permission"] == "none"

    denied_response = phase8_context.client.get(
        f"/api/v1/files/{readme_id}/content",
        params={"project_id": phase8_context.project_id},
    )
    assert denied_response.status_code == 403
    assert denied_response.json()["error"]["code"] == "FILE_ACCESS_DENIED"


def test_roles_crud(phase8_context: Phase8Context) -> None:
    create_response = phase8_context.client.post(
        "/api/v1/roles",
        json={
            "project_id": phase8_context.project_id,
            "name": "Frontend Specialist",
            "description": "UI focused role.",
            "checkpoint_preference": "Ask before final polish.",
            "tags": ["vue", "ux"],
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    role_id = created["id"]

    list_response = phase8_context.client.get(
        "/api/v1/roles",
        params={"project_id": phase8_context.project_id},
    )
    assert list_response.status_code == 200
    assert any(item["id"] == role_id for item in list_response.json())

    update_response = phase8_context.client.put(
        f"/api/v1/roles/{role_id}",
        json={
            "project_id": phase8_context.project_id,
            "name": "Frontend Lead",
            "description": "Owns UI quality.",
            "checkpoint_preference": "Check in before release.",
            "tags": ["vue", "a11y"],
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Frontend Lead"

    delete_response = phase8_context.client.delete(
        f"/api/v1/roles/{role_id}",
        params={"project_id": phase8_context.project_id},
    )
    assert delete_response.status_code == 204


def test_usage_endpoints(phase8_context: Phase8Context) -> None:
    budget_response = phase8_context.client.get("/api/v1/usage/budget")
    assert budget_response.status_code == 200
    budget_payload = budget_response.json()
    assert Decimal(budget_payload["used_usd"]) >= Decimal("0")

    timeline_response = phase8_context.client.get("/api/v1/usage/timeline", params={"days": 30})
    assert timeline_response.status_code == 200
    assert len(timeline_response.json()) >= 1

    errors_response = phase8_context.client.get(
        "/api/v1/usage/errors",
        params={"project_id": phase8_context.project_id},
    )
    assert errors_response.status_code == 200
    errors = errors_response.json()
    assert len(errors) >= 1
    assert any(item["error_type"] in {"RunLogError", "RunFailed"} for item in errors)


def test_cors_preflight_allowed(phase8_context: Phase8Context) -> None:
    response = phase8_context.client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_new_routes_present_in_openapi(phase8_context: Phase8Context) -> None:
    response = phase8_context.client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    paths = payload["paths"]
    for required_path in [
        "/api/v1/tasks/stats",
        "/api/v1/updates",
        "/api/v1/usage/budget",
        "/api/v1/files",
        "/api/v1/roles",
        "/api/v1/inbox/{item_id}/read",
        "/api/v1/agents/{agent_id}/health",
    ]:
        assert required_path in paths
