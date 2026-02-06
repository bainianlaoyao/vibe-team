from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.models import Project
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _normalize_line(raw_line: str | bytes) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8")
    return raw_line


def _collect_sse_events(response: Any, expected_count: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_id: int | None = None
    current_event_type: str | None = None
    data_lines: list[str] = []

    for raw_line in response.iter_lines():
        line = _normalize_line(raw_line)
        if line.startswith(":"):
            continue
        if line.startswith("id:"):
            current_id = int(line.split(":", maxsplit=1)[1].strip())
            continue
        if line.startswith("event:"):
            current_event_type = line.split(":", maxsplit=1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", maxsplit=1)[1].strip())
            continue
        if line != "":
            continue

        if current_id is not None and data_lines:
            data = json.loads("\n".join(data_lines))
            events.append(
                {
                    "id": current_id,
                    "event_type": current_event_type,
                    "data": data,
                }
            )
            if len(events) >= expected_count:
                break

        current_id = None
        current_event_type = None
        data_lines = []

    return events


@dataclass
class EventsApiContext:
    client: TestClient
    engine: Engine
    project_id: int


@pytest.fixture
def events_api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[EventsApiContext]:
    db_url = _to_sqlite_url(tmp_path / "events-api.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(
            name="Events API Project",
            root_path=str((tmp_path / "workspace").resolve()),
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

    with TestClient(create_app()) as client:
        yield EventsApiContext(client=client, engine=engine, project_id=project_id)

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_create_typed_events_and_stream_replay(events_api_context: EventsApiContext) -> None:
    task_status_response = events_api_context.client.post(
        "/api/v1/events",
        json={
            "project_id": events_api_context.project_id,
            "event_type": "task.status.changed",
            "payload": {
                "task_id": 22,
                "previous_status": "todo",
                "status": "running",
                "run_id": 99,
                "actor": "scheduler",
            },
            "trace_id": "trace-task-22-run-99",
        },
    )
    assert task_status_response.status_code == 201
    assert task_status_response.json()["category"] == "task_status"

    run_status_response = events_api_context.client.post(
        "/api/v1/events",
        json={
            "project_id": events_api_context.project_id,
            "event_type": "run.status.changed",
            "payload": {
                "run_id": 99,
                "task_id": 22,
                "previous_status": "running",
                "status": "retry_scheduled",
                "attempt": 1,
                "idempotency_key": "task-22-request-99",
                "next_retry_at": "2026-02-06T19:00:00Z",
                "error_code": "TIMEOUT",
                "actor": "runtime",
            },
            "trace_id": "trace-run-99-retry",
        },
    )
    assert run_status_response.status_code == 201
    assert run_status_response.json()["category"] == "run_status"

    run_log_response = events_api_context.client.post(
        "/api/v1/events",
        json={
            "project_id": events_api_context.project_id,
            "event_type": "run.log",
            "payload": {
                "run_id": 99,
                "task_id": 22,
                "level": "info",
                "message": "Run heartbeat emitted.",
                "sequence": 2,
            },
            "trace_id": "trace-run-99",
        },
    )
    assert run_log_response.status_code == 201
    assert run_log_response.json()["category"] == "run_log"

    alert_response = events_api_context.client.post(
        "/api/v1/events",
        json={
            "project_id": events_api_context.project_id,
            "event_type": "alert.raised",
            "payload": {
                "code": "RUN_SLOW",
                "severity": "warning",
                "title": "Run is slower than target",
                "message": "Run exceeded the latency budget for 5 consecutive checks.",
                "task_id": 22,
                "run_id": 99,
            },
            "trace_id": "trace-alert-99",
        },
    )
    assert alert_response.status_code == 201
    assert alert_response.json()["category"] == "alert"

    with events_api_context.client.stream(
        "GET",
        "/api/v1/events/stream",
        params={
            "project_id": events_api_context.project_id,
            "replay_last": 4,
            "max_events": 4,
            "batch_size": 10,
            "poll_interval_ms": 100,
        },
    ) as stream_response:
        assert stream_response.status_code == 200
        streamed_events = _collect_sse_events(stream_response, expected_count=4)

    assert [event["event_type"] for event in streamed_events] == [
        "task.status.changed",
        "run.status.changed",
        "run.log",
        "alert.raised",
    ]
    assert streamed_events[-1]["data"]["payload"]["code"] == "RUN_SLOW"


def test_stream_reconnect_uses_last_event_id(events_api_context: EventsApiContext) -> None:
    created_ids: list[int] = []
    for index in range(3):
        response = events_api_context.client.post(
            "/api/v1/events",
            json={
                "project_id": events_api_context.project_id,
                "event_type": "run.log",
                "payload": {
                    "run_id": 120,
                    "task_id": 45,
                    "level": "info",
                    "message": f"log-{index}",
                    "sequence": index + 1,
                },
            },
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    with events_api_context.client.stream(
        "GET",
        "/api/v1/events/stream",
        params={
            "project_id": events_api_context.project_id,
            "max_events": 2,
            "batch_size": 10,
            "poll_interval_ms": 100,
        },
        headers={"Last-Event-ID": str(created_ids[0])},
    ) as stream_response:
        assert stream_response.status_code == 200
        replayed_events = _collect_sse_events(stream_response, expected_count=2)

    assert [event["id"] for event in replayed_events] == created_ids[1:]


def test_stream_rejects_conflicting_last_event_ids(events_api_context: EventsApiContext) -> None:
    response = events_api_context.client.get(
        "/api/v1/events/stream",
        params={"last_event_id": 1},
        headers={"Last-Event-ID": "2"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_LAST_EVENT_ID"
