from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import Session, select

from app.db.bootstrap import initialize_database
from app.db.cli import main as db_cli_main
from app.db.engine import create_engine_from_url
from app.db.migrations import upgrade_to_head
from app.db.models import Agent, Event, Project, Task


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_migrations_create_expected_schema(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "schema.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert {"projects", "agents", "tasks", "events"}.issubset(table_names)

        projects_columns = {column["name"] for column in inspector.get_columns("projects")}
        assert projects_columns == {"id", "name", "root_path", "created_at", "updated_at"}

        agents_columns = {column["name"] for column in inspector.get_columns("agents")}
        assert agents_columns == {
            "id",
            "project_id",
            "name",
            "role",
            "model_provider",
            "model_name",
            "initial_persona_prompt",
            "enabled_tools_json",
            "status",
        }

        tasks_columns = {column["name"] for column in inspector.get_columns("tasks")}
        assert tasks_columns == {
            "id",
            "project_id",
            "title",
            "description",
            "status",
            "priority",
            "assignee_agent_id",
            "parent_task_id",
            "created_at",
            "updated_at",
            "due_at",
        }

        events_columns = {column["name"] for column in inspector.get_columns("events")}
        assert events_columns == {
            "id",
            "project_id",
            "event_type",
            "payload_json",
            "created_at",
            "trace_id",
        }

        task_foreign_keys = {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in inspector.get_foreign_keys("tasks")
        }
        assert ("project_id", "projects") in task_foreign_keys
        assert ("assignee_agent_id", "agents") in task_foreign_keys
        assert ("parent_task_id", "tasks") in task_foreign_keys
    finally:
        engine.dispose()


def test_migrations_are_repeatable_and_preserve_data(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "repeatable.db")
    initialize_database(database_url=db_url, seed=False)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            project = Project(name="Regression Project", root_path=str(tmp_path / "workspace"))
            session.add(project)
            session.commit()

        upgrade_to_head(db_url)

        with Session(engine) as session:
            persisted_project = session.exec(
                select(Project).where(Project.name == "Regression Project")
            ).first()
            assert persisted_project is not None
    finally:
        engine.dispose()


def test_seed_data_is_idempotent(tmp_path: Path) -> None:
    db_url = _to_sqlite_url(tmp_path / "seed.db")
    project_root = tmp_path / "workspace"
    project_root.mkdir(parents=True, exist_ok=True)

    initialize_database(database_url=db_url, seed=True, project_root=project_root)
    initialize_database(database_url=db_url, seed=True, project_root=project_root)

    engine = create_engine_from_url(db_url)
    try:
        with Session(engine) as session:
            assert len(session.exec(select(Project)).all()) == 1
            assert len(session.exec(select(Agent)).all()) == 1
            assert len(session.exec(select(Task)).all()) == 1
            seeded_events = session.exec(
                select(Event).where(Event.event_type == "system.seeded")
            ).all()
            assert len(seeded_events) == 1
    finally:
        engine.dispose()


def test_cli_init_command_creates_database(tmp_path: Path) -> None:
    db_path = tmp_path / "cli-init.db"
    db_url = _to_sqlite_url(db_path)

    exit_code = db_cli_main(["init", "--database-url", db_url])

    assert exit_code == 0
    assert db_path.exists()
