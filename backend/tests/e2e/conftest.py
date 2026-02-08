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
from app.db.models import Project
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class E2EContext:
    client: TestClient
    engine: Engine
    project_id: int
    workspace_root: Path


@pytest.fixture
def e2e_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[E2EContext]:
    db_url = _to_sqlite_url(tmp_path / "e2e.db")
    workspace_root = (tmp_path / "workspace").resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "README.md").write_text("E2E workspace\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(name="E2E Project", root_path=str(workspace_root))
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        project_id = project.id

    with TestClient(create_app()) as client:
        yield E2EContext(
            client=client,
            engine=engine,
            project_id=project_id,
            workspace_root=workspace_root,
        )

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()
