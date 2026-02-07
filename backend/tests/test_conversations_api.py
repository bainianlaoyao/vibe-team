from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import TaskRunStatus, TaskStatus
from app.db.models import Agent, Project, Task, TaskRun
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class ConversationTestContext:
    client: TestClient
    engine: Engine
    project_id: int
    agent_id: int


@pytest.fixture
def conv_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[ConversationTestContext]:
    db_url = _to_sqlite_url(tmp_path / "conversation-test.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(
            name="Conversation Project",
            root_path=str((tmp_path / "workspace").resolve()),
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

        agent = Agent(
            project_id=project_id,
            name="Test Agent",
            role="assistant",
            model_provider="anthropic",
            model_name="claude-sonnet-4-5",
            initial_persona_prompt="You are a helpful assistant.",
            enabled_tools_json=[],
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)
        assert agent.id is not None
        agent_id = agent.id

    with TestClient(create_app()) as client:
        yield ConversationTestContext(
            client=client,
            engine=engine,
            project_id=project_id,
            agent_id=agent_id,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


class TestConversationCRUD:
    def test_create_conversation(self, conv_context: ConversationTestContext) -> None:
        resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Test Conversation",
                "context_json": {"topic": "testing"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Conversation"
        assert data["status"] == "active"
        assert data["project_id"] == conv_context.project_id
        assert data["agent_id"] == conv_context.agent_id
        assert data["context_json"] == {"topic": "testing"}
        assert data["id"] is not None

    def test_create_conversation_invalid_project(
        self, conv_context: ConversationTestContext
    ) -> None:
        resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": 9999,
                "agent_id": conv_context.agent_id,
                "title": "Test Conversation",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PROJECT_NOT_FOUND"

    def test_create_conversation_invalid_agent(self, conv_context: ConversationTestContext) -> None:
        resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": 9999,
                "title": "Test Conversation",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"

    def test_create_conversation_inherits_task_context(
        self,
        conv_context: ConversationTestContext,
    ) -> None:
        with Session(conv_context.engine) as session:
            task = Task(
                project_id=conv_context.project_id,
                title="Task Context Source",
                description="Task for conversation inheritance",
                status=TaskStatus.BLOCKED,
                priority=2,
                assignee_agent_id=conv_context.agent_id,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.id is not None
            task_id = task.id

            run = TaskRun(
                task_id=task_id,
                agent_id=conv_context.agent_id,
                run_status=TaskRunStatus.INTERRUPTED,
                attempt=1,
                idempotency_key="conv-inherit-run-1",
            )
            session.add(run)
            session.commit()

            child = Task(
                project_id=conv_context.project_id,
                title="Child Dependency",
                status=TaskStatus.TODO,
                priority=3,
                parent_task_id=task.id,
            )
            session.add(child)
            session.commit()

        resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "task_id": task_id,
                "title": "Context Inheritance",
                "context_json": {"entry": "base"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        task_context = data["context_json"]["task_context"]
        assert task_context["task_id"] == task_id
        assert task_context["title"] == "Task Context Source"
        assert task_context["enabled_tools"] == []
        assert len(task_context["dependencies"]) == 1
        assert task_context["dependencies"][0]["title"] == "Child Dependency"
        assert len(task_context["recent_runs"]) == 1
        assert task_context["recent_runs"][0]["run_status"] == "interrupted"

    def test_get_conversation(self, conv_context: ConversationTestContext) -> None:
        create_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Get Test",
            },
        )
        assert create_resp.status_code == 201
        conv_id = create_resp.json()["id"]

        get_resp = conv_context.client.get(f"/api/v1/conversations/{conv_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Get Test"

    def test_get_conversation_not_found(self, conv_context: ConversationTestContext) -> None:
        resp = conv_context.client.get("/api/v1/conversations/9999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    def test_list_conversations(self, conv_context: ConversationTestContext) -> None:
        for i in range(3):
            conv_context.client.post(
                "/api/v1/conversations",
                json={
                    "project_id": conv_context.project_id,
                    "agent_id": conv_context.agent_id,
                    "title": f"Conversation {i}",
                },
            )

        resp = conv_context.client.get("/api/v1/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_list_conversations_with_filters(self, conv_context: ConversationTestContext) -> None:
        conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Active Conversation",
            },
        )

        resp = conv_context.client.get(
            "/api/v1/conversations",
            params={"project_id": conv_context.project_id, "status": "active"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert all(c["status"] == "active" for c in data["items"])

    def test_update_conversation_title(self, conv_context: ConversationTestContext) -> None:
        create_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Original Title",
            },
        )
        conv_id = create_resp.json()["id"]

        update_resp = conv_context.client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": "Updated Title"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["title"] == "Updated Title"

    def test_update_conversation_status(self, conv_context: ConversationTestContext) -> None:
        create_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "To Close",
            },
        )
        conv_id = create_resp.json()["id"]

        update_resp = conv_context.client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"status": "closed"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "closed"
        assert update_resp.json()["closed_at"] is not None

    def test_delete_conversation(self, conv_context: ConversationTestContext) -> None:
        create_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "To Delete",
            },
        )
        conv_id = create_resp.json()["id"]

        delete_resp = conv_context.client.delete(f"/api/v1/conversations/{conv_id}")
        assert delete_resp.status_code == 204

        get_resp = conv_context.client.get(f"/api/v1/conversations/{conv_id}")
        assert get_resp.status_code == 404


class TestMessageCRUD:
    def test_create_message(self, conv_context: ConversationTestContext) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Message Test",
            },
        )
        conv_id = conv_resp.json()["id"]

        msg_resp = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={
                "role": "user",
                "message_type": "text",
                "content": "Hello, Agent!",
            },
        )
        assert msg_resp.status_code == 201
        data = msg_resp.json()
        assert data["role"] == "user"
        assert data["content"] == "Hello, Agent!"
        assert data["sequence_num"] == 1
        assert data["conversation_id"] == conv_id

    def test_create_multiple_messages_sequence(self, conv_context: ConversationTestContext) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Sequence Test",
            },
        )
        conv_id = conv_resp.json()["id"]

        msg1 = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "user", "content": "First message"},
        )
        msg2 = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "assistant", "content": "Second message"},
        )
        msg3 = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Third message"},
        )

        assert msg1.json()["sequence_num"] == 1
        assert msg2.json()["sequence_num"] == 2
        assert msg3.json()["sequence_num"] == 3

    def test_cannot_add_message_to_closed_conversation(
        self,
        conv_context: ConversationTestContext,
    ) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Closed Conv",
            },
        )
        conv_id = conv_resp.json()["id"]

        conv_context.client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"status": "closed"},
        )

        msg_resp = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Late message"},
        )
        assert msg_resp.status_code == 409
        assert msg_resp.json()["error"]["code"] == "CONVERSATION_CLOSED"

    def test_list_messages(self, conv_context: ConversationTestContext) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "List Messages Test",
            },
        )
        conv_id = conv_resp.json()["id"]

        for i in range(5):
            conv_context.client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"role": "user", "content": f"Message {i}"},
            )

        list_resp = conv_context.client.get(f"/api/v1/conversations/{conv_id}/messages")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5
        assert data["items"][0]["sequence_num"] == 1
        assert data["items"][4]["sequence_num"] == 5

    def test_list_messages_after_sequence(self, conv_context: ConversationTestContext) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "After Sequence Test",
            },
        )
        conv_id = conv_resp.json()["id"]

        for i in range(5):
            conv_context.client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"role": "user", "content": f"Message {i}"},
            )

        list_resp = conv_context.client.get(
            f"/api/v1/conversations/{conv_id}/messages",
            params={"after_sequence": 2},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 3
        assert all(m["sequence_num"] > 2 for m in data["items"])

    def test_get_message(self, conv_context: ConversationTestContext) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Get Message Test",
            },
        )
        conv_id = conv_resp.json()["id"]

        msg_resp = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Test content"},
        )
        msg_id = msg_resp.json()["id"]

        get_resp = conv_context.client.get(f"/api/v1/conversations/{conv_id}/messages/{msg_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["content"] == "Test content"

    def test_get_message_not_found(self, conv_context: ConversationTestContext) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Not Found Test",
            },
        )
        conv_id = conv_resp.json()["id"]

        get_resp = conv_context.client.get(f"/api/v1/conversations/{conv_id}/messages/9999")
        assert get_resp.status_code == 404
        assert get_resp.json()["error"]["code"] == "MESSAGE_NOT_FOUND"

    def test_message_types(self, conv_context: ConversationTestContext) -> None:
        conv_resp = conv_context.client.post(
            "/api/v1/conversations",
            json={
                "project_id": conv_context.project_id,
                "agent_id": conv_context.agent_id,
                "title": "Message Types Test",
            },
        )
        conv_id = conv_resp.json()["id"]

        tool_call_resp = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={
                "role": "assistant",
                "message_type": "tool_call",
                "content": "read_file",
                "metadata_json": {"tool_name": "read_file", "args": {"path": "/tmp/test.txt"}},
            },
        )
        assert tool_call_resp.status_code == 201
        assert tool_call_resp.json()["message_type"] == "tool_call"

        tool_result_resp = conv_context.client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={
                "role": "assistant",
                "message_type": "tool_result",
                "content": "File contents here",
                "metadata_json": {"tool_name": "read_file", "success": True},
            },
        )
        assert tool_result_resp.status_code == 201
        assert tool_result_resp.json()["message_type"] == "tool_result"
