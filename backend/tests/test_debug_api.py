from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

import app.api.debug as debug_api
from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import TaskStatus
from app.db.models import Agent, Project, Task
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class DebugApiContext:
    client: TestClient
    engine: Engine
    project_id: int
    workspace_root: Path


@pytest.fixture
def debug_api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[DebugApiContext]:
    db_url = _to_sqlite_url(tmp_path / "debug-api.db")
    project_root = (tmp_path / "project-root").resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(name="Debug API Project", root_path=str(project_root))
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

    monkeypatch.setattr(debug_api, "_WORKSPACE_ROOT", tmp_path.resolve())
    with TestClient(create_app()) as client:
        yield DebugApiContext(
            client=client,
            engine=engine,
            project_id=project_id,
            workspace_root=tmp_path.resolve(),
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_setup_agent_playground_creates_file_agent_and_task(
    debug_api_context: DebugApiContext,
) -> None:
    response = debug_api_context.client.post(
        "/debug/agent-playground/setup",
        json={"project_id": debug_api_context.project_id},
    )
    assert response.status_code == 201
    payload = response.json()

    workspace_readme = debug_api_context.workspace_root / "play_ground" / "README.md"
    assert workspace_readme.exists()
    assert workspace_readme.read_text(encoding="utf-8") == "114514\n"

    with Session(debug_api_context.engine) as session:
        agent = session.get(Agent, payload["agent_id"])
        task = session.get(Task, payload["task_id"])
        assert agent is not None
        assert task is not None
        assert agent.model_provider == "claude_code"
        assert task.assignee_agent_id == agent.id
        assert task.status == TaskStatus.TODO
        assert task.title.startswith("Debug Playground Task-")

    assert payload["workspace_playground_path"].endswith("play_ground\\README.md") or payload[
        "workspace_playground_path"
    ].endswith("play_ground/README.md")
    assert "114514" in Path(payload["workspace_playground_path"]).read_text(encoding="utf-8")
    assert "仅返回文件内容本身" in payload["run_prompt"]


def test_setup_agent_playground_returns_project_not_found(
    debug_api_context: DebugApiContext,
) -> None:
    response = debug_api_context.client.post(
        "/debug/agent-playground/setup",
        json={"project_id": 999999},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
