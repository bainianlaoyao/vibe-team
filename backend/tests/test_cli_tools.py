from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import TaskStatus
from app.db.models import Event, InboxItem, Project, Task
from app.main import create_app
from app.tools import CliDomainTools


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass(slots=True)
class CliToolsTestContext:
    app: Any
    engine: Engine
    project_id: int
    review_task_id: int
    running_task_id: int
    todo_task_id: int


@pytest.fixture
def cli_tools_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[CliToolsTestContext]:
    db_url = _to_sqlite_url(tmp_path / "cli-tools.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(
            name="CLI Tool Project",
            root_path=str((tmp_path / "workspace").resolve()),
        )
        session.add(project)
        session.flush()

        review_task = Task(
            project_id=project.id,
            title="Review task",
            status=TaskStatus.REVIEW,
            priority=2,
        )
        running_task = Task(
            project_id=project.id,
            title="Running task",
            status=TaskStatus.RUNNING,
            priority=2,
        )
        todo_task = Task(
            project_id=project.id,
            title="Todo task",
            status=TaskStatus.TODO,
            priority=3,
        )
        session.add(review_task)
        session.add(running_task)
        session.add(todo_task)
        session.commit()
        session.refresh(project)
        session.refresh(review_task)
        session.refresh(running_task)
        session.refresh(todo_task)
        assert project.id is not None
        assert review_task.id is not None
        assert running_task.id is not None
        assert todo_task.id is not None
        context = CliToolsTestContext(
            app=create_app(),
            engine=engine,
            project_id=project.id,
            review_task_id=review_task.id,
            running_task_id=running_task.id,
            todo_task_id=todo_task.id,
        )

    yield context

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_cli_tools_call_backend_command_api_and_write_audit(
    cli_tools_context: CliToolsTestContext,
) -> None:
    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=cli_tools_context.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            tools = CliDomainTools(base_url="http://testserver", client=http_client)

            finish_result = await tools.finish_task(
                task_id=cli_tools_context.review_task_id,
                idempotency_key=f"finish-{cli_tools_context.review_task_id}-001",
            )
            assert finish_result.task_status == "done"
            assert finish_result.idempotency_hit is False

            duplicated = await tools.finish_task(
                task_id=cli_tools_context.review_task_id,
                idempotency_key=f"finish-{cli_tools_context.review_task_id}-001",
            )
            assert duplicated.idempotency_hit is True
            assert duplicated.task_version == finish_result.task_version

            block_result = await tools.block_task(
                task_id=cli_tools_context.running_task_id,
                reason="wait for dependency",
                idempotency_key=f"block-{cli_tools_context.running_task_id}-001",
            )
            assert block_result.task_status == "blocked"
            assert block_result.idempotency_hit is False

            input_result = await tools.request_input(
                task_id=cli_tools_context.todo_task_id,
                title="Need user confirmation",
                content="Please confirm whether to proceed.",
                idempotency_key=f"request-input-{cli_tools_context.todo_task_id}-001",
            )
            assert input_result.task_status == "blocked"
            assert input_result.inbox_item_id is not None
            assert input_result.idempotency_hit is False

    asyncio.run(run_scenario())

    with Session(cli_tools_context.engine) as session:
        review_task = session.get(Task, cli_tools_context.review_task_id)
        running_task = session.get(Task, cli_tools_context.running_task_id)
        todo_task = session.get(Task, cli_tools_context.todo_task_id)
        assert review_task is not None
        assert running_task is not None
        assert todo_task is not None
        assert review_task.status == TaskStatus.DONE
        assert running_task.status == TaskStatus.BLOCKED
        assert todo_task.status == TaskStatus.BLOCKED

        inbox_items = list(
            session.exec(
                select(InboxItem).where(InboxItem.project_id == cli_tools_context.project_id)
            ).all()
        )
        assert len(inbox_items) == 1
        assert inbox_items[0].item_type == "await_user_input"

        event_id = cast(Any, Event.id)
        audit_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == cli_tools_context.project_id)
                .where(Event.event_type == "tool.command.audit")
                .order_by(event_id.asc())
            ).all()
        )
        security_events = list(
            session.exec(
                select(Event)
                .where(Event.project_id == cli_tools_context.project_id)
                .where(
                    cast(Any, Event.event_type).in_(
                        ["security.audit.allowed", "security.audit.denied"]
                    )
                )
                .order_by(event_id.asc())
            ).all()
        )

    assert len(audit_events) == 3
    assert {event.payload_json["tool"] for event in audit_events} == {
        "finish_task",
        "block_task",
        "request_input",
    }
    assert {event.payload_json["outcome"] for event in audit_events} == {"applied"}
    assert len(security_events) == 4
    assert {event.event_type for event in security_events} == {"security.audit.allowed"}
    for event in security_events:
        payload = event.payload_json
        assert payload["actor"] == "cli_tool"
        assert payload["outcome"] == "allowed"
        assert payload["action"] in {"finish_task", "block_task", "request_input"}
        assert str(payload["resource"]).startswith("task:")
