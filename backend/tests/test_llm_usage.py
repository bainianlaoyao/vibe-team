from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db.bootstrap import initialize_database
from app.db.engine import create_engine_from_url
from app.db.enums import AgentStatus, TaskRunStatus, TaskStatus
from app.db.models import Agent, ApiUsageDaily, Project, Task, TaskRun
from app.llm.contracts import LLMUsage
from app.llm.usage import record_usage_for_run


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _create_run(session: Session, root: Path) -> TaskRun:
    project = Project(name="LLM Usage Project", root_path=str(root / "workspace"))
    session.add(project)
    session.flush()

    agent = Agent(
        project_id=project.id,
        name="Usage Agent",
        role="executor",
        model_provider="claude_code",
        model_name="claude-sonnet-4-5",
        initial_persona_prompt="Track usage",
        enabled_tools_json=[],
        status=AgentStatus.ACTIVE,
    )
    session.add(agent)
    session.flush()

    task = Task(
        project_id=project.id,
        title="Usage Task",
        status=TaskStatus.RUNNING,
        priority=2,
        assignee_agent_id=agent.id,
    )
    session.add(task)
    session.flush()

    run = TaskRun(
        task_id=task.id,
        agent_id=agent.id,
        run_status=TaskRunStatus.RUNNING,
        attempt=1,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_record_usage_for_run_updates_task_run_and_daily_stats(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "llm-usage.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            run = _create_run(session, tmp_path)
            assert run.id is not None

            record_usage_for_run(
                session,
                run_id=run.id,
                provider="claude_code",
                model_name="claude-sonnet-4-5",
                usage=LLMUsage(
                    request_count=1,
                    token_in=120,
                    token_out=40,
                    cost_usd=Decimal("0.0123"),
                ),
                occurred_at=datetime(2026, 2, 7, 8, 0, 0, tzinfo=UTC),
            )
            record_usage_for_run(
                session,
                run_id=run.id,
                provider="claude_code",
                model_name="claude-sonnet-4-5",
                usage=LLMUsage(
                    request_count=1,
                    token_in=30,
                    token_out=10,
                    cost_usd=Decimal("0.0056"),
                ),
                occurred_at=datetime(2026, 2, 7, 9, 0, 0, tzinfo=UTC),
            )

            persisted_run = session.get(TaskRun, run.id)
            assert persisted_run is not None
            assert persisted_run.token_in == 150
            assert persisted_run.token_out == 50
            assert persisted_run.cost_usd == Decimal("0.0179")

            usage_rows = session.exec(
                select(ApiUsageDaily).where(
                    ApiUsageDaily.provider == "claude_code",
                    ApiUsageDaily.model_name == "claude-sonnet-4-5",
                )
            ).all()
            assert len(usage_rows) == 1
            usage_row = usage_rows[0]
            assert usage_row.date.isoformat() == "2026-02-07"
            assert usage_row.request_count == 2
            assert usage_row.token_in == 150
            assert usage_row.token_out == 50
            assert usage_row.cost_usd == Decimal("0.0179")
    finally:
        engine.dispose()


def test_record_usage_for_run_validates_inputs(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "llm-usage-invalid.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            run = _create_run(session, tmp_path)
            assert run.id is not None

            with pytest.raises(ValueError, match="token_in"):
                record_usage_for_run(
                    session,
                    run_id=run.id,
                    provider="claude_code",
                    model_name="claude-sonnet-4-5",
                    usage=LLMUsage(
                        request_count=1,
                        token_in=-1,
                        token_out=0,
                        cost_usd=Decimal("0.0000"),
                    ),
                )

            with pytest.raises(ValueError, match="does not exist"):
                record_usage_for_run(
                    session,
                    run_id=9999,
                    provider="claude_code",
                    model_name="claude-sonnet-4-5",
                    usage=LLMUsage(),
                )
    finally:
        engine.dispose()
