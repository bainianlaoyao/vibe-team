from __future__ import annotations

from .conftest import E2EContext


def test_conversation_http_flow(e2e_context: E2EContext) -> None:
    agent_response = e2e_context.client.post(
        "/api/v1/agents",
        json={
            "project_id": e2e_context.project_id,
            "name": "Conversation Agent",
            "role": "assistant",
            "model_provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
            "initial_persona_prompt": "Chat with user.",
            "enabled_tools_json": [],
            "status": "active",
        },
    )
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["id"]

    conversation_response = e2e_context.client.post(
        "/api/v1/conversations",
        json={
            "project_id": e2e_context.project_id,
            "agent_id": agent_id,
            "title": "E2E Conversation",
        },
    )
    assert conversation_response.status_code == 201
    conversation_id = conversation_response.json()["id"]

    message_response = e2e_context.client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={
            "role": "user",
            "message_type": "text",
            "content": "Hello from e2e",
        },
    )
    assert message_response.status_code == 201

    list_response = e2e_context.client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) >= 1
