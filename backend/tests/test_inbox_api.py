from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, select

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import InboxItemType, SourceType
from app.db.models import Event, InboxItem, Project
from app.db.repositories import InboxRepository
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class InboxApiContext:
    client: TestClient
    engine: Engine
    project_id: int


def _create_inbox_item(
    engine: Engine,
    *,
    project_id: int,
    item_type: InboxItemType,
    source_id: str,
    title: str,
) -> int:
    with Session(engine) as session:
        repository = InboxRepository(session)
        created = repository.create(
            InboxItem(
                project_id=project_id,
                source_type=SourceType.TASK,
                source_id=source_id,
                item_type=item_type,
                title=title,
                content=f"Context for {title}",
            ),
            trace_id=f"trace-create-{source_id}",
        )
        assert created.id is not None
        return created.id


@pytest.fixture
def inbox_api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[InboxApiContext]:
    db_url = _to_sqlite_url(tmp_path / "inbox-api.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(
            name="Inbox API Project", root_path=str((tmp_path / "workspace").resolve())
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

    with TestClient(create_app()) as client:
        yield InboxApiContext(client=client, engine=engine, project_id=project_id)

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_await_user_input_flow_requires_input_and_records_events(
    inbox_api_context: InboxApiContext,
) -> None:
    item_id = _create_inbox_item(
        inbox_api_context.engine,
        project_id=inbox_api_context.project_id,
        item_type=InboxItemType.AWAIT_USER_INPUT,
        source_id="task:await-1",
        title="Need user release decision",
    )

    list_response = inbox_api_context.client.get(
        "/api/v1/inbox",
        params={
            "project_id": inbox_api_context.project_id,
            "item_type": InboxItemType.AWAIT_USER_INPUT.value,
            "status": "open",
        },
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["id"] == item_id
    assert listed[0]["item_type"] == InboxItemType.AWAIT_USER_INPUT.value

    missing_input_response = inbox_api_context.client.post(
        f"/api/v1/inbox/{item_id}/close", json={}
    )
    assert missing_input_response.status_code == 422
    assert missing_input_response.json()["error"]["code"] == "USER_INPUT_REQUIRED"

    close_response = inbox_api_context.client.post(
        f"/api/v1/inbox/{item_id}/close",
        json={
            "user_input": "Use release/2026.02 and continue deployment.",
            "resolver": "alice",
            "trace_id": "trace-close-await-1",
        },
    )
    assert close_response.status_code == 200
    closed_item = close_response.json()
    assert closed_item["status"] == "closed"
    assert closed_item["resolver"] == "alice"
    assert closed_item["version"] == 2

    closed_list_response = inbox_api_context.client.get(
        "/api/v1/inbox",
        params={
            "project_id": inbox_api_context.project_id,
            "status": "closed",
        },
    )
    assert closed_list_response.status_code == 200
    closed_ids = {row["id"] for row in closed_list_response.json()}
    assert item_id in closed_ids

    with Session(inbox_api_context.engine) as session:
        events = list(session.exec(select(Event)).all())
        events.sort(key=lambda event: event.id or 0)
        event_types = [event.event_type for event in events]
        assert event_types == [
            "inbox.item.created",
            "inbox.item.closed",
            "user.input.submitted",
        ]

        created_payload = events[0].payload_json
        assert created_payload["item_id"] == item_id
        assert created_payload["item_type"] == InboxItemType.AWAIT_USER_INPUT.value

        closed_payload = events[1].payload_json
        assert closed_payload["item_id"] == item_id
        assert closed_payload["user_input_submitted"] is True

        user_input_payload = events[2].payload_json
        assert user_input_payload["item_id"] == item_id
        assert user_input_payload["user_input"] == "Use release/2026.02 and continue deployment."


def test_task_completed_flow_closes_without_user_input(
    inbox_api_context: InboxApiContext,
) -> None:
    item_id = _create_inbox_item(
        inbox_api_context.engine,
        project_id=inbox_api_context.project_id,
        item_type=InboxItemType.TASK_COMPLETED,
        source_id="task:done-1",
        title="Task completed confirmation",
    )

    close_response = inbox_api_context.client.post(
        f"/api/v1/inbox/{item_id}/close",
        json={"resolver": "system", "trace_id": "trace-close-done-1"},
    )
    assert close_response.status_code == 200
    closed_item = close_response.json()
    assert closed_item["item_type"] == InboxItemType.TASK_COMPLETED.value
    assert closed_item["status"] == "closed"
    assert closed_item["resolver"] == "system"

    with Session(inbox_api_context.engine) as session:
        events = list(session.exec(select(Event)).all())
        events.sort(key=lambda event: event.id or 0)
        event_types = [event.event_type for event in events]
        assert event_types == ["inbox.item.created", "inbox.item.closed"]
        assert "user.input.submitted" not in event_types
