from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import ConversationStatus, TaskStatus
from app.db.models import Agent, Conversation, Event, Project, Task
from app.events.schemas import TASK_STATUS_CHANGED_EVENT_TYPE
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class WSTestContext:
    client: TestClient
    engine: Engine
    project_id: int
    agent_id: int
    conversation_id: int


@pytest.fixture
def ws_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[WSTestContext]:
    db_url = _to_sqlite_url(tmp_path / "ws-test.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(name="WS Project", root_path=str((tmp_path / "workspace").resolve()))
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

        agent = Agent(
            project_id=project_id,
            name="WS Agent",
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

        conversation = Conversation(
            project_id=project_id,
            agent_id=agent_id,
            title="WS Test Conversation",
            status=ConversationStatus.ACTIVE,
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        assert conversation.id is not None
        conversation_id = conversation.id

    with TestClient(create_app()) as client:
        yield WSTestContext(
            client=client,
            engine=engine,
            project_id=project_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


class TestWebSocketConnection:
    def test_connect_to_conversation(self, ws_context: WSTestContext) -> None:
        """Test basic WebSocket connection to a conversation."""
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}"
        ) as websocket:
            data = websocket.receive_json()
            assert data["type"] == "session.connected"
            assert data["payload"]["conversation_id"] == ws_context.conversation_id
            assert "client_id" in data["payload"]
            assert "session_id" in data["payload"]

    def test_connect_with_client_id(self, ws_context: WSTestContext) -> None:
        """Test connection with custom client ID."""
        client_id = "test-client-123"
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?client_id={client_id}"
        ) as websocket:
            data = websocket.receive_json()
            assert data["type"] == "session.connected"
            assert data["payload"]["client_id"] == client_id


class TestWebSocketMessaging:
    def test_send_user_message(self, ws_context: WSTestContext) -> None:
        """Test sending a user message and receiving acknowledgment."""
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}"
        ) as websocket:
            # Receive connection confirmation
            websocket.receive_json()

            # Send user message
            websocket.send_json(
                {
                    "type": "user.message",
                    "payload": {"content": "Hello, Agent!"},
                }
            )

            # Receive acknowledgment
            ack = websocket.receive_json()
            assert ack["type"] == "user.message.ack"
            assert "message_id" in ack["payload"]
            assert ack["payload"]["sequence_num"] == 1

    def test_heartbeat(self, ws_context: WSTestContext) -> None:
        """Test heartbeat mechanism."""
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}"
        ) as websocket:
            websocket.receive_json()

            websocket.send_json({"type": "session.heartbeat", "payload": {}})

            ack = websocket.receive_json()
            assert ack["type"] == "session.heartbeat_ack"
            assert "server_time" in ack["payload"]

    def test_user_interrupt(self, ws_context: WSTestContext) -> None:
        """Test user interrupt signal."""
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}"
        ) as websocket:
            websocket.receive_json()

            websocket.send_json({"type": "user.interrupt", "payload": {}})

            ack = websocket.receive_json()
            assert ack["type"] == "user.interrupt.ack"
            assert ack["payload"]["interrupted"] is True

    def test_user_input_response_can_resume_blocked_task(self, ws_context: WSTestContext) -> None:
        with Session(ws_context.engine) as session:
            task = Task(
                project_id=ws_context.project_id,
                title="Need input",
                status=TaskStatus.BLOCKED,
                priority=2,
                assignee_agent_id=ws_context.agent_id,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.id is not None
            task_id = task.id
            conversation = session.get(Conversation, ws_context.conversation_id)
            assert conversation is not None
            conversation.task_id = task_id
            session.add(conversation)
            session.commit()

        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}"
        ) as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "user.input_response",
                    "payload": {"content": "confirmed", "resume_task": True},
                }
            )

        with Session(ws_context.engine) as session:
            task_after = session.get(Task, task_id)
            assert task_after is not None
            assert str(task_after.status) == "todo"
            resume_event = session.exec(
                select(Event)
                .where(Event.event_type == TASK_STATUS_CHANGED_EVENT_TYPE)
                .order_by(cast(Any, Event.id).desc())
            ).first()
            assert resume_event is not None
