from __future__ import annotations

from .conftest import E2EContext


def test_task_lifecycle_create_assign_transition_complete(e2e_context: E2EContext) -> None:
    agent_response = e2e_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": e2e_context.project_id,
            "name": "E2E Agent",
            "role": "executor",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Execute e2e tasks.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    create_task_response = e2e_context.client.post(
        "/api/v1/tasks",
        json={
            "project_id": e2e_context.project_id,
            "title": "E2E Task",
            "description": "Lifecycle smoke",
            "assignee_agent_id": agent_id,
        },
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    start_response = e2e_context.client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "running"},
    )
    assert start_response.status_code == 200

    review_response = e2e_context.client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "review"},
    )
    assert review_response.status_code == 200

    done_response = e2e_context.client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
    )
    assert done_response.status_code == 200
    assert done_response.json()["status"] == "done"
