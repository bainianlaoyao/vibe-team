from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import Agent
from tests.shared import ApiTestContext


def test_agent_creation_creates_persona_file(api_context: ApiTestContext) -> None:
    """Test that creating an agent with persona creates a file."""
    payload = {
        "project_id": api_context.project_id,
        "name": "File Agent",
        "role": "executor",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        "initial_persona_prompt": "This is a file-based persona.",
        "enabled_tools_json": [],
        "status": "active",
    }

    response = api_context.client.post("/api/v1/agents", json=payload)
    assert response.status_code == 201
    data = response.json()

    # Check API response
    assert data["name"] == "File Agent"
    assert "initial_persona_prompt" not in data  # Should be removed from schema or None
    assert data["persona_path"] == "docs/agents/file_agent.md"

    # Check File System
    expected_path = api_context.project_root / "docs" / "agents" / "file_agent.md"
    assert expected_path.exists()
    assert expected_path.read_text(encoding="utf-8") == "This is a file-based persona."

    # Check DB
    with Session(api_context.engine) as session:
        agent = session.exec(select(Agent).where(Agent.id == data["id"])).one()
        assert agent.persona_path == "docs/agents/file_agent.md"


def test_agent_update_updates_persona_file(api_context: ApiTestContext) -> None:
    """Test that updating an agent's persona updates the file."""
    # Create agent
    create_payload = {
        "project_id": api_context.project_id,
        "name": "Update Agent",
        "role": "executor",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        "initial_persona_prompt": "Original persona.",
        "enabled_tools_json": [],
        "status": "active",
    }
    create_res = api_context.client.post("/api/v1/agents", json=create_payload)
    agent_id = create_res.json()["id"]

    # Update persona
    update_payload = {
        "initial_persona_prompt": "Updated persona content."
    }
    update_res = api_context.client.patch(f"/api/v1/agents/{agent_id}", json=update_payload)
    assert update_res.status_code == 200

    # Check file
    expected_path = api_context.project_root / "docs" / "agents" / "update_agent.md"
    assert expected_path.read_text(encoding="utf-8") == "Updated persona content."


def test_agent_renaming_renames_persona_file(api_context: ApiTestContext) -> None:
    """Test that renaming an agent renames the persona file."""
    # Create agent
    create_payload = {
        "project_id": api_context.project_id,
        "name": "Old Name Agent",
        "role": "executor",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        "initial_persona_prompt": "Persona content.",
        "enabled_tools_json": [],
        "status": "active",
    }
    create_res = api_context.client.post("/api/v1/agents", json=create_payload)
    agent_id = create_res.json()["id"]

    old_path = api_context.project_root / "docs" / "agents" / "old_name_agent.md"
    assert old_path.exists()

    # Rename agent
    update_payload = {
        "name": "New Name Agent"
    }
    update_res = api_context.client.patch(f"/api/v1/agents/{agent_id}", json=update_payload)
    assert update_res.status_code == 200

    # Check files
    new_path = api_context.project_root / "docs" / "agents" / "new_name_agent.md"
    assert new_path.exists()
    assert not old_path.exists()
    assert new_path.read_text(encoding="utf-8") == "Persona content."


def test_agent_deletion_deletes_persona_file(api_context: ApiTestContext) -> None:
    """Test that deleting an agent deletes the persona file."""
    # Create agent
    create_payload = {
        "project_id": api_context.project_id,
        "name": "Delete Agent",
        "role": "executor",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        "initial_persona_prompt": "To be deleted.",
        "enabled_tools_json": [],
        "status": "active",
    }
    create_res = api_context.client.post("/api/v1/agents", json=create_payload)
    agent_id = create_res.json()["id"]

    path = api_context.project_root / "docs" / "agents" / "delete_agent.md"
    assert path.exists()

    # Delete agent
    delete_res = api_context.client.delete(f"/api/v1/agents/{agent_id}")
    assert delete_res.status_code == 204

    # Check file
    assert not path.exists()


def test_get_agent_persona_endpoint(api_context: ApiTestContext) -> None:
    """Test the GET /agents/{id}/persona endpoint."""
    # Create agent
    create_payload = {
        "project_id": api_context.project_id,
        "name": "Get Persona Agent",
        "role": "executor",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        "initial_persona_prompt": "Content to fetch.",
        "enabled_tools_json": [],
        "status": "active",
    }
    create_res = api_context.client.post("/api/v1/agents", json=create_payload)
    agent_id = create_res.json()["id"]

    # Get persona
    get_res = api_context.client.get(f"/api/v1/agents/{agent_id}/persona")
    assert get_res.status_code == 200
    assert get_res.json()["content"] == "Content to fetch."


def test_update_agent_persona_endpoint(api_context: ApiTestContext) -> None:
    """Test the PUT /agents/{id}/persona endpoint."""
    # Create agent
    create_payload = {
        "project_id": api_context.project_id,
        "name": "Put Persona Agent",
        "role": "executor",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        "initial_persona_prompt": "Initial content.",
        "enabled_tools_json": [],
        "status": "active",
    }
    create_res = api_context.client.post("/api/v1/agents", json=create_payload)
    agent_id = create_res.json()["id"]

    # Update persona direct endpoint
    put_payload = {"content": "Directly updated content."}
    put_res = api_context.client.put(f"/api/v1/agents/{agent_id}/persona", json=put_payload)
    assert put_res.status_code == 200
    # Response is AgentRead, so it doesn't contain "content"
    assert put_res.json()["id"] == agent_id
    assert put_res.json()["persona_path"] is not None

    # Check file system
    path = api_context.project_root / "docs" / "agents" / "put_persona_agent.md"
    assert path.read_text(encoding="utf-8") == "Directly updated content."


def test_create_agent_without_persona(api_context: ApiTestContext) -> None:
    """Test creating an agent without a persona prompt."""
    payload = {
        "project_id": api_context.project_id,
        "name": "No Persona Agent",
        "role": "executor",
        "model_provider": "openai",
        "model_name": "gpt-4.1-mini",
        # initial_persona_prompt omitted
        "enabled_tools_json": [],
        "status": "active",
    }

    response = api_context.client.post("/api/v1/agents", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["persona_path"] is not None

    # Check DB
    with Session(api_context.engine) as session:
        agent = session.exec(select(Agent).where(Agent.id == data["id"])).one()
        assert agent.persona_path is not None
        assert agent.persona_path.endswith(".md")

