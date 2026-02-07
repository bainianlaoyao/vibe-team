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
from app.db.models import Event, Project
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class LogsApiContext:
    client: TestClient
    engine: Engine
    project_id: int


@pytest.fixture
def logs_api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[LogsApiContext]:
    db_url = _to_sqlite_url(tmp_path / "logs-api.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("LOG_FORMAT", "json")
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(
            name="Logs API Project",
            root_path=str((tmp_path / "workspace").resolve()),
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

    with TestClient(create_app()) as client:
        yield LogsApiContext(client=client, engine=engine, project_id=project_id)

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_logs_query_supports_task_run_level_filters(logs_api_context: LogsApiContext) -> None:
    response_ok = logs_api_context.client.post(
        "/api/v1/events",
        json={
            "project_id": logs_api_context.project_id,
            "event_type": "run.log",
            "payload": {
                "run_id": 12,
                "task_id": 5,
                "level": "info",
                "message": "run started",
                "sequence": 1,
            },
            "trace_id": "trace-run-12",
        },
    )
    assert response_ok.status_code == 201

    response_other = logs_api_context.client.post(
        "/api/v1/events",
        json={
            "project_id": logs_api_context.project_id,
            "event_type": "run.log",
            "payload": {
                "run_id": 18,
                "task_id": 9,
                "level": "error",
                "message": "run failed",
                "sequence": 1,
            },
            "trace_id": "trace-run-18",
        },
    )
    assert response_other.status_code == 201

    list_response = logs_api_context.client.get(
        "/api/v1/logs",
        params={
            "project_id": logs_api_context.project_id,
            "task_id": 5,
            "run_id": 12,
            "level": "info",
        },
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 1
    assert payload[0]["task_id"] == 5
    assert payload[0]["run_id"] == 12
    assert payload[0]["level"] == "info"
    assert payload[0]["trace_id"] == "trace-run-12"


def test_trace_header_is_preserved_and_generated(logs_api_context: LogsApiContext) -> None:
    traced = logs_api_context.client.get("/healthz", headers={"X-Trace-ID": "trace-client-001"})
    assert traced.status_code == 200
    assert traced.headers["X-Trace-ID"] == "trace-client-001"

    generated = logs_api_context.client.get("/readyz")
    assert generated.status_code == 200
    assert generated.headers["X-Trace-ID"].startswith("trace-http-")


def test_logs_query_skips_invalid_run_log_payload(logs_api_context: LogsApiContext) -> None:
    with Session(logs_api_context.engine) as session:
        session.add(
            Event(
                project_id=logs_api_context.project_id,
                event_type="run.log",
                payload_json={"task_id": 5, "message": "invalid"},
                trace_id="trace-invalid",
            )
        )
        session.commit()

    response = logs_api_context.client.get(
        "/api/v1/logs",
        params={"project_id": logs_api_context.project_id},
    )
    assert response.status_code == 200
    assert response.json() == []
