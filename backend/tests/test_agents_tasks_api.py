from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.models import Project
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class ApiTestContext:
    client: TestClient
    project_id: int
    other_project_id: int


@pytest.fixture
def api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[ApiTestContext]:
    db_url = _to_sqlite_url(tmp_path / "api-integration.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(name="API Project", root_path=str((tmp_path / "workspace").resolve()))
        other_project = Project(
            name="API Project 2",
            root_path=str((tmp_path / "workspace-2").resolve()),
        )
        session.add(project)
        session.add(other_project)
        session.commit()
        session.refresh(project)
        session.refresh(other_project)
        assert project.id is not None
        assert other_project.id is not None
        project_id = project.id
        other_project_id = other_project.id

    with TestClient(create_app()) as client:
        yield ApiTestContext(
            client=client,
            project_id=project_id,
            other_project_id=other_project_id,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


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
