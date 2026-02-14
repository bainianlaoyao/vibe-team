from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import AsyncIterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolUseBlock
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.core.config import Settings, get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import TaskStatus
from app.db.models import Agent, Conversation, Event, Project, Task
from app.events.schemas import TASK_STATUS_CHANGED_EVENT_TYPE
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _result_message(*, subtype: str = "success", is_error: bool = False) -> ResultMessage:
    return ResultMessage(
        subtype=subtype,
        duration_ms=10,
        duration_api_ms=8,
        is_error=is_error,
        num_turns=1,
        session_id="conv-session",
        total_cost_usd=0.0001,
        usage={"input_tokens": 1, "output_tokens": 1},
        result="ok",
    )


class FakeClaudeSessionClient:
    def __init__(self) -> None:
        self.connected = False
        self.interrupt_count = 0
        self.sent_payloads: list[dict[str, Any]] = []
        self._responses: list[list[Any]] = []
        self.connect_thread_id: int | None = None
        self.connect_loop_name: str | None = None
        self.query_thread_id: int | None = None

    def push_turn(self, messages: list[Any]) -> None:
        self._responses.append(messages)

    async def connect(self, prompt: str | AsyncIterable[dict[str, Any]] | None = None) -> None:
        _ = prompt
        self.connect_thread_id = threading.get_ident()
        self.connect_loop_name = asyncio.get_running_loop().__class__.__name__
        self.connected = True

    async def query(
        self,
        prompt: str | AsyncIterable[dict[str, Any]],
        session_id: str = "default",
    ) -> None:
        _ = session_id
        self.query_thread_id = threading.get_ident()
        if isinstance(prompt, str):
            self.sent_payloads.append(
                {
                    "type": "user",
                    "message": {"role": "user", "content": prompt},
                    "parent_tool_use_id": None,
                    "tool_use_result": None,
                }
            )
            return

        captured: dict[str, Any] | None = None
        async for item in prompt:
            captured = dict(item)
            break
        self.sent_payloads.append(captured or {})

    def receive_response(self) -> Any:
        messages = self._responses.pop(0) if self._responses else [_result_message()]

        async def _iter() -> Any:
            for message in messages:
                yield message

        return _iter()

    async def interrupt(self) -> None:
        self.interrupt_count += 1

    async def disconnect(self) -> None:
        self.connected = False


@dataclass
class WSTestContext:
    client: TestClient
    engine: Engine
    project_id: int
    agent_id: int
    conversation_id: int
    fake_client: FakeClaudeSessionClient


def _receive_until(websocket: Any, event_type: str, *, limit: int = 20) -> dict[str, Any]:
    for _ in range(limit):
        data = websocket.receive_json()
        if data["type"] == event_type:
            return data
    raise AssertionError(f"Did not receive event {event_type} within {limit} messages")


def test_shutdown_state_disconnects_sdk_client_even_when_not_connected(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.api import ws_conversations as ws_api

    class DisconnectProbeClient:
        def __init__(self) -> None:
            self.disconnect_calls = 0

        async def disconnect(self) -> None:
            self.disconnect_calls += 1

    probe = DisconnectProbeClient()
    monkeypatch.setattr(ws_api.SessionRepository, "disconnect", lambda self, session_id: None)

    state = ws_api.ConnectionState(
        websocket=cast(Any, MagicMock()),
        settings=Settings(),
        conversation_id=1,
        client_id="client",
        session_id=1,
        project_id=1,
        agent_id=1,
        task_id=None,
        model_provider="anthropic",
        model_name="claude-sonnet-4-5",
        system_prompt="system",
        workspace_root=None,
    )
    state.sdk_client = cast(Any, probe)
    state.sdk_connected = False

    async def _run() -> None:
        await ws_api._shutdown_state(state, close_socket=False, reason="unit-test")

    asyncio.run(_run())

    assert probe.disconnect_calls == 1
    assert state.sdk_connected is False


def test_ensure_sdk_connected_cleans_up_failed_connect(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.api import ws_conversations as ws_api

    class FailingConnectClient:
        def __init__(self) -> None:
            self.disconnect_calls = 0

        async def connect(self, prompt: str | AsyncIterable[dict[str, Any]] | None = None) -> None:
            _ = prompt
            raise RuntimeError("connect failed")

        async def query(
            self,
            prompt: str | AsyncIterable[dict[str, Any]],
            session_id: str = "default",
        ) -> None:
            _ = prompt
            _ = session_id
            raise AssertionError("query should not be called")

        def receive_response(self) -> Any:
            raise AssertionError("receive_response should not be called")

        async def interrupt(self) -> None:
            return None

        async def disconnect(self) -> None:
            self.disconnect_calls += 1

    failing_client = FailingConnectClient()
    monkeypatch.setattr(
        ws_api,
        "_create_claude_session_client",
        lambda _state: cast(Any, failing_client),
    )

    state = ws_api.ConnectionState(
        websocket=cast(Any, MagicMock()),
        settings=Settings(),
        conversation_id=1,
        client_id="client",
        session_id=1,
        project_id=1,
        agent_id=1,
        task_id=None,
        model_provider="anthropic",
        model_name="claude-sonnet-4-5",
        system_prompt="system",
        workspace_root=None,
    )

    async def _run() -> None:
        await ws_api._ensure_sdk_connected(state)

    with pytest.raises(RuntimeError, match="connect failed"):
        asyncio.run(_run())

    assert failing_client.disconnect_calls == 1
    assert state.sdk_client is None
    assert state.sdk_connected is False


def test_create_claude_session_client_uses_windows_default_cli_path(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    from app.api import ws_conversations as ws_api

    def fake_sdk_client(*, options: Any) -> Any:
        captured["cli_path"] = options.cli_path
        captured["permission_mode"] = options.permission_mode
        captured["cwd"] = options.cwd
        return object()

    monkeypatch.setattr("app.llm.providers.claude_settings.sys.platform", "win32")
    monkeypatch.setattr(ws_api, "ClaudeSDKClient", fake_sdk_client)
    monkeypatch.setattr(
        ws_api,
        "resolve_claude_auth",
        lambda settings_path_override=None: MagicMock(settings_path=None, env={}),
    )

    state = ws_api.ConnectionState(
        websocket=cast(Any, MagicMock()),
        settings=Settings(),
        conversation_id=1,
        client_id="client",
        session_id=1,
        project_id=1,
        agent_id=1,
        task_id=None,
        model_provider="anthropic",
        model_name="claude-sonnet-4-5",
        system_prompt="",
        workspace_root=None,
    )

    _ = ws_api._create_claude_session_client(state)
    assert captured["cli_path"] == "claude.cmd"
    assert captured["permission_mode"] == "bypassPermissions"
    assert captured["cwd"] is None


def test_create_claude_session_client_prefers_settings_project_root(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    from app.api import ws_conversations as ws_api

    def fake_sdk_client(*, options: Any) -> Any:
        captured["cwd"] = options.cwd
        return object()

    monkeypatch.setattr(ws_api, "ClaudeSDKClient", fake_sdk_client)
    monkeypatch.setattr(
        ws_api,
        "resolve_claude_auth",
        lambda settings_path_override=None: MagicMock(settings_path=None, env={}),
    )

    configured_root = Path("E:/beebeebrain/play_ground")
    state = ws_api.ConnectionState(
        websocket=cast(Any, MagicMock()),
        settings=Settings(project_root=configured_root, database_url="sqlite:///./ignored.db"),
        conversation_id=1,
        client_id="client",
        session_id=1,
        project_id=1,
        agent_id=1,
        task_id=None,
        model_provider="anthropic",
        model_name="claude-sonnet-4-5",
        system_prompt="",
        workspace_root=Path("E:/beebeebrain"),
    )

    _ = ws_api._create_claude_session_client(state)
    assert captured["cwd"] == configured_root


def test_threaded_claude_session_client_supports_selector_loop() -> None:
    from app.api import ws_conversations as ws_api

    selector_loop_factory = getattr(asyncio, "SelectorEventLoop", None)
    if selector_loop_factory is None:
        pytest.skip("SelectorEventLoop is unavailable on this platform.")

    fake_client = FakeClaudeSessionClient()
    fake_client.push_turn(
        [
            AssistantMessage(
                content=[TextBlock(text="hello from threaded client")],
                model="claude-sonnet-4-5",
            ),
            _result_message(),
        ]
    )
    client = ws_api.ThreadedClaudeSessionClient(
        options=MagicMock(),
        client_factory=lambda _options: fake_client,
    )

    loop = selector_loop_factory()
    asyncio.set_event_loop(loop)
    try:

        async def _run() -> list[Any]:
            main_thread_id = threading.get_ident()
            await client.connect()
            await client.query("hello", session_id="selector-loop")
            messages: list[Any] = []
            async for message in client.receive_response():
                messages.append(message)
            await client.disconnect()
            assert fake_client.connect_thread_id is not None
            assert fake_client.query_thread_id is not None
            assert fake_client.connect_thread_id != main_thread_id
            assert fake_client.query_thread_id != main_thread_id
            return messages

        messages = loop.run_until_complete(_run())
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    assert fake_client.connect_loop_name is not None
    if sys.platform == "win32":
        assert fake_client.connect_loop_name == "ProactorEventLoop"
    assert any(isinstance(message, ResultMessage) for message in messages)


@pytest.fixture
def ws_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[WSTestContext]:
    db_url = _to_sqlite_url(tmp_path / "ws-test.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CHAT_PROTOCOL_V2_ENABLED", "true")
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
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        assert conversation.id is not None
        conversation_id = conversation.id

    fake_client = FakeClaudeSessionClient()
    from app.api import ws_conversations as ws_api

    monkeypatch.setattr(ws_api, "_create_claude_session_client", lambda _state: fake_client)

    with TestClient(create_app()) as client:
        yield WSTestContext(
            client=client,
            engine=engine,
            project_id=project_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            fake_client=fake_client,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


class TestWebSocketConnection:
    def test_connect_to_conversation_v2(self, ws_context: WSTestContext) -> None:
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?protocol=v2"
        ) as websocket:
            data = websocket.receive_json()
            assert data["type"] == "session.connected"
            assert data["conversation_id"] == ws_context.conversation_id
            assert data["payload"]["protocol"] == "v2"
            assert "trace_id" in data
            assert "sequence" in data


class TestWebSocketMessaging:
    def test_send_user_message_ack(self, ws_context: WSTestContext) -> None:
        ws_context.fake_client.push_turn([_result_message()])
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?protocol=v2"
        ) as websocket:
            websocket.receive_json()

            websocket.send_json(
                {
                    "type": "user.message",
                    "payload": {"content": "Hello, Agent!"},
                }
            )

            ack = _receive_until(websocket, "user.message.ack")
            assert ack["turn_id"] == 1
            assert ack["payload"]["message_id"] is not None
            assert ack["payload"]["message_sequence"] == 1

    def test_heartbeat(self, ws_context: WSTestContext) -> None:
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?protocol=v2"
        ) as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "session.heartbeat", "payload": {}})
            ack = websocket.receive_json()
            assert ack["type"] == "session.heartbeat_ack"
            assert "server_time" in ack["payload"]

    def test_filters_init_system_message(self, ws_context: WSTestContext) -> None:
        ws_context.fake_client.push_turn(
            [
                SystemMessage(subtype="init", data={"type": "system", "subtype": "init"}),
                AssistantMessage(
                    content=[TextBlock(text="Hello after init")],
                    model="claude-sonnet-4-5",
                ),
                _result_message(),
            ]
        )
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?protocol=v2"
        ) as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "user.message",
                    "payload": {"content": "trigger init system message"},
                }
            )

            received_events: list[dict[str, Any]] = []
            for _ in range(30):
                message = websocket.receive_json()
                received_events.append(message)
                if message["type"] == "assistant.complete":
                    break

            assert any(event["type"] == "assistant.chunk" for event in received_events)
            assert not any(
                event["type"] == "session.system_event"
                and event["payload"].get("subtype", "").strip().lower() == "init"
                for event in received_events
            )

    def test_user_interrupt(self, ws_context: WSTestContext) -> None:
        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?protocol=v2"
        ) as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "user.interrupt", "payload": {}})
            ack = _receive_until(websocket, "user.interrupt.ack")
            assert ack["payload"]["interrupted"] is False

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

        ws_context.fake_client.push_turn(
            [
                AssistantMessage(
                    content=[
                        ToolUseBlock(
                            id="question-1",
                            name="request_input",
                            input={"question": "Need confirm", "required": True},
                        )
                    ],
                    model="claude-sonnet-4-5",
                ),
                _result_message(subtype="awaiting_input"),
            ]
        )
        ws_context.fake_client.push_turn(
            [
                AssistantMessage(
                    content=[TextBlock(text="confirmed")],
                    model="claude-sonnet-4-5",
                ),
                _result_message(),
            ]
        )

        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?protocol=v2"
        ) as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "user.message",
                    "payload": {"content": "please ask"},
                }
            )
            _receive_until(websocket, "user.message.ack")
            request_input = _receive_until(websocket, "assistant.request_input")
            question_id = request_input["payload"]["question_id"]
            assert question_id == "question-1"

            websocket.send_json(
                {
                    "type": "user.input_response",
                    "payload": {
                        "question_id": question_id,
                        "answer": "confirmed",
                        "resume_task": True,
                    },
                }
            )
            ack = _receive_until(websocket, "user.input_response.ack")
            assert ack["payload"]["question_id"] == question_id

        assert len(ws_context.fake_client.sent_payloads) >= 2
        assert ws_context.fake_client.sent_payloads[1]["parent_tool_use_id"] == "question-1"
        assert ws_context.fake_client.sent_payloads[1]["tool_use_result"]["answer"] == "confirmed"

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

    def test_invalid_question_id_returns_error(self, ws_context: WSTestContext) -> None:
        ws_context.fake_client.push_turn(
            [
                AssistantMessage(
                    content=[
                        ToolUseBlock(
                            id="question-2",
                            name="request_input",
                            input={"question": "Need option", "required": True},
                        )
                    ],
                    model="claude-sonnet-4-5",
                ),
                _result_message(subtype="awaiting_input"),
            ]
        )

        with ws_context.client.websocket_connect(
            f"/ws/conversations/{ws_context.conversation_id}?protocol=v2"
        ) as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "user.message",
                    "payload": {"content": "trigger question"},
                }
            )
            _receive_until(websocket, "assistant.request_input")
            websocket.send_json(
                {
                    "type": "user.input_response",
                    "payload": {"question_id": "wrong-qid", "answer": "x"},
                }
            )
            error = _receive_until(websocket, "session.error")
            assert error["payload"]["code"] == "INVALID_QUESTION_ID"
