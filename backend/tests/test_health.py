from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import inspect

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def health_client(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[TestClient]:
    db_url = _to_sqlite_url(tmp_path / "health.db")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("DB_AUTO_INIT", raising=False)
    monkeypatch.delenv("DB_AUTO_SEED", raising=False)
    get_settings.cache_clear()
    dispose_engine()

    with TestClient(create_app()) as client:
        yield client

    dispose_engine()
    get_settings.cache_clear()


def test_healthz(health_client: TestClient) -> None:
    response = health_client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "BeeBeeBrain Backend"
    assert payload["env"] in {"development", "test", "production"}


def test_readyz(health_client: TestClient) -> None:
    response = health_client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ready", "checks": {"configuration": "ok"}}


def test_startup_auto_initializes_database_in_development(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    db_path = tmp_path / "auto-init.db"
    db_url = _to_sqlite_url(db_path)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.delenv("DB_AUTO_INIT", raising=False)
    monkeypatch.delenv("DB_AUTO_SEED", raising=False)
    get_settings.cache_clear()
    dispose_engine()

    with TestClient(create_app()) as client:
        response = client.get("/readyz")
        assert response.status_code == 200

    engine = create_engine_from_url(db_url)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert "projects" in table_names
        assert "alembic_version" in table_names
    finally:
        engine.dispose()
        dispose_engine()
        get_settings.cache_clear()
