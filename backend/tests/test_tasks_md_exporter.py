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
from app.db.enums import TaskStatus
from app.db.models import Project, Task
from app.exporters import TasksMarkdownExporter
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_tasks_markdown_exporter_renders_db_snapshot(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "tasks-export.db")
    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            project = Project(
                name="Export Project",
                root_path=str((tmp_path / "workspace").resolve()),
            )
            session.add(project)
            session.flush()

            session.add(
                Task(
                    project_id=project.id,
                    title="Todo item",
                    status=TaskStatus.TODO,
                    priority=2,
                )
            )
            session.add(
                Task(
                    project_id=project.id,
                    title="Running item",
                    status=TaskStatus.RUNNING,
                    priority=1,
                )
            )
            session.commit()
            assert project.id is not None

            markdown = TasksMarkdownExporter(session=session).render(project_id=project.id)
    finally:
        engine.dispose()

    assert "# BeeBeeBrain Tasks Snapshot" in markdown
    assert "## Project: Export Project" in markdown
    assert "`todo`: 1" in markdown
    assert "`running`: 1" in markdown
    assert "Todo item" in markdown
    assert "Running item" in markdown


@dataclass(slots=True)
class SyncTestContext:
    client: TestClient
    engine: Engine
    export_path: Path
    task_id: int


@pytest.fixture
def sync_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[SyncTestContext]:
    db_url = _to_sqlite_url(tmp_path / "tasks-sync.db")
    export_path = tmp_path / "tasks.md"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("TASKS_MD_SYNC_ENABLED", "true")
    monkeypatch.setenv("TASKS_MD_OUTPUT_PATH", str(export_path))
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(name="Sync Project", root_path=str((tmp_path / "workspace").resolve()))
        session.add(project)
        session.flush()
        task = Task(
            project_id=project.id,
            title="Sync me",
            status=TaskStatus.TODO,
            priority=2,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        assert task.id is not None
        task_id = task.id

    with TestClient(create_app()) as client:
        yield SyncTestContext(
            client=client,
            engine=engine,
            export_path=export_path,
            task_id=task_id,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_task_status_change_triggers_tasks_md_sync(sync_context: SyncTestContext) -> None:
    response = sync_context.client.patch(
        f"/api/v1/tasks/{sync_context.task_id}",
        json={"status": "running"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"

    assert sync_context.export_path.exists()
    exported = sync_context.export_path.read_text(encoding="utf-8")
    assert "Sync me" in exported
    assert "| running |" in exported
