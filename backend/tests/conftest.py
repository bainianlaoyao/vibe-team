from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.models import Project
from app.main import create_app
from tests.shared import ApiTestContext


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[ApiTestContext]:
    """
    Creates a temporary SQLite database and a test client.
    Seeds two projects for testing isolation and cross-project checks.
    """
    db_url = _to_sqlite_url(tmp_path / "api-integration.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Create workspace directories
        workspace_1 = tmp_path / "workspace"
        workspace_1.mkdir(parents=True, exist_ok=True)
        workspace_2 = tmp_path / "workspace-2"
        workspace_2.mkdir(parents=True, exist_ok=True)

        project = Project(name="API Project", root_path=str(workspace_1.resolve()))
        other_project = Project(
            name="API Project 2",
            root_path=str(workspace_2.resolve()),
        )
        session.add(project)
        session.add(other_project)
        session.commit()
        session.refresh(project)
        session.refresh(other_project)
        assert project.id is not None
        assert other_project.id is not None
        project_id = project.id
        other_project_id = other_project.id

    with TestClient(create_app()) as client:
        yield ApiTestContext(
            client=client,
            engine=engine,
            project_id=project_id,
            project_root=workspace_1.resolve(),
            other_project_id=other_project_id,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()
