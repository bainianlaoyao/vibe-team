from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
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
from app.db.enums import CommentStatus, TaskStatus
from app.db.models import Agent, Comment, Project, Task
from app.llm.contracts import (
    LLMRequest,
    LLMResponse,
    LLMUsage,
    StreamCallback,
    StreamEvent,
    StreamEventType,
)
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


class _FakeStreamingClient:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        async def _noop(_: StreamEvent) -> None:
            return None

        return await self.generate_stream(request, cast(StreamCallback, _noop))

    async def generate_stream(self, request: LLMRequest, callback: StreamCallback) -> LLMResponse:
        await callback(
            StreamEvent(
                event_type=StreamEventType.TEXT_CHUNK,
                content="comment addressed",
            )
        )
        usage = LLMUsage(request_count=1, token_in=5, token_out=7, cost_usd=Decimal("0.0001"))
        await callback(StreamEvent(event_type=StreamEventType.COMPLETE, usage=usage))
        return LLMResponse(
            provider=request.provider,
            model=request.model,
            session_id=request.session_id,
            text="comment addressed",
            tool_calls=[],
            usage=usage,
        )


@dataclass
class CommentReplyContext:
    client: TestClient
    engine: Engine
    comment_id: int
    project_id: int
    agent_id: int


@pytest.fixture
def comment_reply_context(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> Iterator[CommentReplyContext]:
    db_url = _to_sqlite_url(tmp_path / "comments-reply.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(name="Comment Project", root_path=str((tmp_path / "workspace").resolve()))
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

        agent = Agent(
            project_id=project.id,
            name="Reply Agent",
            role="assistant",
            model_provider="anthropic",
            model_name="claude-sonnet-4-5",
            initial_persona_prompt="Reply comments",
            enabled_tools_json=[],
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)
        assert agent.id is not None
        agent_id = agent.id

        task = Task(
            project_id=project.id,
            title="Task with comment",
            status=TaskStatus.BLOCKED,
            priority=2,
            assignee_agent_id=agent.id,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        assert task.id is not None

        comment = Comment(
            task_id=task.id,
            comment_text="Please improve error handling.",
            author="reviewer",
            status=CommentStatus.OPEN,
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)
        assert comment.id is not None
        comment_id = comment.id

    from app.api import comments as comments_api

    monkeypatch.setattr(comments_api, "create_llm_client", lambda **_: _FakeStreamingClient())

    with TestClient(create_app()) as client:
        yield CommentReplyContext(
            client=client,
            engine=engine,
            comment_id=comment_id,
            project_id=project_id,
            agent_id=agent_id,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_reply_comment_creates_conversation_and_addresses_comment(
    comment_reply_context: CommentReplyContext,
) -> None:
    resp = comment_reply_context.client.post(
        f"/api/v1/comments/{comment_reply_context.comment_id}/reply",
        json={"prompt": "请回复并给出修改建议。"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["comment_id"] == comment_reply_context.comment_id
    assert payload["conversation_id"] > 0
    assert payload["status"] == "addressed"
    assert payload["assistant_message_id"] is not None

    with Session(comment_reply_context.engine) as session:
        stored = session.get(Comment, comment_reply_context.comment_id)
        assert stored is not None
        assert str(stored.status) == "addressed"
        assert stored.conversation_id == payload["conversation_id"]
