from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, dispose_engine
from app.db.enums import TaskRunStatus, TaskStatus
from app.db.models import ApiUsageDaily, Project, Task, TaskRun
from app.main import create_app


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@dataclass
class MetricsApiContext:
    client: TestClient
    engine: Engine
    project_id: int


@pytest.fixture
def metrics_api_context(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterator[MetricsApiContext]:
    db_url = _to_sqlite_url(tmp_path / "metrics-api.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    dispose_engine()

    engine = create_engine_from_url(db_url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project = Project(
            name="Metrics API Project",
            root_path=str((tmp_path / "workspace").resolve()),
        )
        session.add(project)
        session.flush()
        assert project.id is not None

        task = Task(
            project_id=project.id,
            title="Metrics Task",
            status=TaskStatus.RUNNING,
            priority=2,
        )
        session.add(task)
        session.flush()
        assert task.id is not None

        started_at = datetime(2026, 2, 7, 8, 0, 0, tzinfo=UTC)
        session.add(
            TaskRun(
                task_id=task.id,
                run_status=TaskRunStatus.SUCCEEDED,
                attempt=1,
                started_at=started_at,
                ended_at=started_at + timedelta(seconds=10),
                token_in=100,
                token_out=30,
                cost_usd=Decimal("0.0100"),
            )
        )
        session.add(
            TaskRun(
                task_id=task.id,
                run_status=TaskRunStatus.FAILED,
                attempt=2,
                started_at=started_at + timedelta(minutes=1),
                ended_at=started_at + timedelta(minutes=1, seconds=20),
                token_in=40,
                token_out=10,
                cost_usd=Decimal("0.0040"),
            )
        )
        session.add(
            TaskRun(
                task_id=task.id,
                run_status=TaskRunStatus.RUNNING,
                attempt=3,
                started_at=started_at + timedelta(minutes=2),
                token_in=20,
                token_out=5,
                cost_usd=Decimal("0.0020"),
            )
        )

        session.add(
            ApiUsageDaily(
                provider="claude_code",
                model_name="claude-sonnet-4-5",
                date=date(2026, 2, 7),
                request_count=3,
                token_in=160,
                token_out=45,
                cost_usd=Decimal("0.0160"),
            )
        )
        session.add(
            ApiUsageDaily(
                provider="claude_code",
                model_name="claude-sonnet-4-5",
                date=date(2026, 2, 8),
                request_count=2,
                token_in=90,
                token_out=25,
                cost_usd=Decimal("0.0095"),
            )
        )
        session.add(
            ApiUsageDaily(
                provider="openai",
                model_name="gpt-4.1-mini",
                date=date(2026, 2, 7),
                request_count=1,
                token_in=20,
                token_out=6,
                cost_usd=Decimal("0.0018"),
            )
        )
        session.commit()
        project_id = project.id

    with TestClient(create_app()) as client:
        yield MetricsApiContext(client=client, engine=engine, project_id=project_id)

    engine.dispose()
    dispose_engine()
    get_settings.cache_clear()


def test_usage_daily_metrics_support_filtering(metrics_api_context: MetricsApiContext) -> None:
    response = metrics_api_context.client.get(
        "/api/v1/metrics/usage-daily",
        params={
            "provider": "claude_code",
            "model_name": "claude-sonnet-4-5",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["date"] == "2026-02-08"
    assert payload[0]["request_count"] == 2
    assert payload[1]["date"] == "2026-02-07"
    assert payload[1]["cost_usd"] == "0.0160"


def test_runs_summary_metrics_contains_duration_and_cost(
    metrics_api_context: MetricsApiContext,
) -> None:
    response = metrics_api_context.client.get(
        "/api/v1/metrics/runs-summary",
        params={"project_id": metrics_api_context.project_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_runs"] == 3
    assert payload["succeeded_runs"] == 1
    assert payload["failed_runs"] == 1
    assert payload["running_runs"] == 1
    assert payload["total_token_in"] == 160
    assert payload["total_token_out"] == 45
    assert payload["total_cost_usd"] == "0.0160"
    assert payload["avg_duration_seconds"] == 15.0
    assert payload["max_duration_seconds"] == 20.0
