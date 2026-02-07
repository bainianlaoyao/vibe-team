from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import ConversationStatus, MessageRole
from app.db.models import Agent, Conversation, Message, Project
from app.db.repositories import MessageRepository
from app.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMUsage,
    StreamCallback,
    StreamEvent,
    StreamEventType,
)
from app.runtime import ConversationExecutor, ExecutionContext


class _Pusher:
    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.tool_calls: list[str] = []
        self.tool_results: list[str] = []
        self.request_inputs: list[str] = []

    async def send_chunk(self, content: str) -> bool:
        self.chunks.append(content)
        return True

    async def send_tool_call(self, tool_call: LLMToolCall) -> bool:
        self.tool_calls.append(tool_call.name)
        return True

    async def send_tool_result(self, tool_id: str, result: str) -> bool:
        self.tool_results.append(f"{tool_id}:{result}")
        return True

    async def send_thinking(self, content: str) -> bool:
        return True

    async def send_request_input(self, content: str) -> bool:
        self.request_inputs.append(content)
        return True

    async def send_complete(self, usage: LLMUsage | None) -> bool:
        return True

    async def send_error(self, code: str, message: str) -> bool:
        return True


class _StreamingClient:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        async def _noop(_: StreamEvent) -> None:
            return None

        return await self.generate_stream(request, cast(StreamCallback, _noop))

    async def generate_stream(self, request: LLMRequest, callback: StreamCallback) -> LLMResponse:
        tool = LLMToolCall(id="tool-1", name="request_input", arguments={"content": "need confirm"})
        await callback(StreamEvent(event_type=StreamEventType.TOOL_CALL_START, tool_call=tool))
        await callback(StreamEvent(event_type=StreamEventType.TEXT_CHUNK, content="hello "))
        await callback(StreamEvent(event_type=StreamEventType.TEXT_CHUNK, content="world"))
        usage = LLMUsage(request_count=1, token_in=10, token_out=8, cost_usd=Decimal("0.0002"))
        await callback(StreamEvent(event_type=StreamEventType.COMPLETE, usage=usage))
        return LLMResponse(
            provider=request.provider,
            model=request.model,
            session_id=request.session_id,
            text="hello world",
            tool_calls=[tool],
            usage=usage,
        )


class _SlowStreamingClient:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        async def _noop(_: StreamEvent) -> None:
            return None

        return await self.generate_stream(request, cast(StreamCallback, _noop))

    async def generate_stream(self, request: LLMRequest, callback: StreamCallback) -> LLMResponse:
        await asyncio.sleep(5)
        usage = LLMUsage(request_count=1, token_in=0, token_out=0, cost_usd=Decimal("0.0000"))
        return LLMResponse(
            provider=request.provider,
            model=request.model,
            session_id=request.session_id,
            text="",
            usage=usage,
        )


@dataclass
class _Fixture:
    engine: Any
    conversation_id: int
    agent_id: int


def _setup(tmp_path: Path) -> _Fixture:
    db_url = f"sqlite:///{(tmp_path / 'executor.db').as_posix()}"
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = db_url
    get_settings.cache_clear()
    dispose_engine()
    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(name="p", root_path=str((tmp_path / "workspace").resolve()))
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        agent = Agent(
            project_id=project.id,
            name="a",
            role="assistant",
            model_provider="anthropic",
            model_name="claude-sonnet-4-5",
            initial_persona_prompt="You are helper",
            enabled_tools_json=[],
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)
        assert agent.id is not None
        conversation = Conversation(
            project_id=project.id,
            agent_id=agent.id,
            title="conv",
            status=ConversationStatus.ACTIVE,
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        assert conversation.id is not None
        seed = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="hi",
            sequence_num=1,
            metadata_json={},
        )
        session.add(seed)
        session.commit()
        return _Fixture(
            engine=engine,
            conversation_id=conversation.id,
            agent_id=agent.id,
        )


def test_conversation_executor_streams_and_persists(tmp_path: Path) -> None:
    fx = _setup(tmp_path)
    pusher = _Pusher()
    executor = ConversationExecutor(llm_client=_StreamingClient())
    result = asyncio.run(
        executor.execute(
            context=ExecutionContext(
                conversation_id=fx.conversation_id,
                agent_id=fx.agent_id,
                session_id="s1",
                user_message_id=1,
                user_content="hi",
            ),
            pusher=pusher,
        )
    )
    assert result.success is True
    assert pusher.chunks == ["hello ", "world"]
    assert pusher.tool_calls == ["request_input"]
    assert pusher.request_inputs == ["need confirm"]
    assert pusher.tool_results == ["tool-1:ok"]

    with Session(fx.engine) as session:
        messages = MessageRepository(session).list_by_conversation(fx.conversation_id, limit=50)
        kinds = [
            m.message_type.value if hasattr(m.message_type, "value") else str(m.message_type)
            for m in messages
        ]
        assert "tool_call" in kinds
        assert "tool_result" in kinds
        assert "input_request" in kinds


def test_conversation_executor_can_be_interrupted(tmp_path: Path) -> None:
    fx = _setup(tmp_path)
    pusher = _Pusher()
    cancel_event = asyncio.Event()
    context = ExecutionContext(
        conversation_id=fx.conversation_id,
        agent_id=fx.agent_id,
        session_id="s2",
        user_message_id=1,
        user_content="hi",
        cancel_event=cancel_event,
    )
    executor = ConversationExecutor(llm_client=_SlowStreamingClient())

    async def run_and_interrupt() -> Any:
        task = asyncio.create_task(executor.execute(context=context, pusher=pusher))
        await asyncio.sleep(0.1)
        cancel_event.set()
        return await task

    result = asyncio.run(run_and_interrupt())
    assert result.cancelled is True
    assert result.success is False
