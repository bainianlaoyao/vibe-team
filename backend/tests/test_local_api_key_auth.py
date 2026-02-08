from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class AuthApiContext:
    client: TestClient
    engine: Engine
    api_key: str


@pytest.fixture
def auth_api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[AuthApiContext]:
    api_key = "local-debug-api-key"
    db_url = _to_sqlite_url(tmp_path / "auth-api.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("LOCAL_API_KEY", api_key)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with TestClient(create_app()) as client:
        yield AuthApiContext(client=client, engine=engine, api_key=api_key)

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_healthz_not_blocked_by_local_api_key(auth_api_context: AuthApiContext) -> None:
    response = auth_api_context.client.get("/healthz")
    assert response.status_code == 200


def test_api_requires_local_api_key(auth_api_context: AuthApiContext) -> None:
    response = auth_api_context.client.get("/api/v1/agents")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_api_accepts_x_api_key_and_bearer(auth_api_context: AuthApiContext) -> None:
    x_api_key_response = auth_api_context.client.get(
        "/api/v1/agents",
        headers={"X-API-Key": auth_api_context.api_key},
    )
    assert x_api_key_response.status_code == 200

    bearer_response = auth_api_context.client.get(
        "/api/v1/agents",
        headers={"Authorization": f"Bearer {auth_api_context.api_key}"},
    )
    assert bearer_response.status_code == 200


def test_debug_panel_route_is_accessible(auth_api_context: AuthApiContext) -> None:
    response = auth_api_context.client.get("/debug/panel")
    assert response.status_code == 200
    assert "BeeBeeBrain Debug Panel" in response.text
