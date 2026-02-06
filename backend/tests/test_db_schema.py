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
        assert {
            "projects",
            "agents",
            "tasks",
            "task_dependencies",
            "task_runs",
            "inbox_items",
            "documents",
            "comments",
            "events",
            "api_usage_daily",
        }.issubset(table_names)

        projects_columns = {column["name"] for column in inspector.get_columns("projects")}
        assert projects_columns == {
            "id",
            "name",
            "root_path",
            "created_at",
            "updated_at",
            "version",
        }

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
            "version",
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
            "version",
        }

        task_dependency_columns = {
            column["name"] for column in inspector.get_columns("task_dependencies")
        }
        assert task_dependency_columns == {
            "id",
            "task_id",
            "depends_on_task_id",
            "dependency_type",
        }

        task_run_columns = {column["name"] for column in inspector.get_columns("task_runs")}
        assert task_run_columns == {
            "id",
            "task_id",
            "agent_id",
            "run_status",
            "attempt",
            "started_at",
            "ended_at",
            "error_code",
            "error_message",
            "token_in",
            "token_out",
            "cost_usd",
            "version",
        }

        inbox_columns = {column["name"] for column in inspector.get_columns("inbox_items")}
        assert inbox_columns == {
            "id",
            "project_id",
            "source_type",
            "source_id",
            "category",
            "title",
            "content",
            "status",
            "created_at",
            "resolved_at",
            "resolver",
            "version",
        }

        documents_columns = {column["name"] for column in inspector.get_columns("documents")}
        assert documents_columns == {
            "id",
            "project_id",
            "path",
            "title",
            "doc_type",
            "is_mandatory",
            "tags_json",
            "version",
            "updated_at",
        }

        comments_columns = {column["name"] for column in inspector.get_columns("comments")}
        assert comments_columns == {
            "id",
            "document_id",
            "task_id",
            "anchor",
            "comment_text",
            "author",
            "status",
            "created_at",
            "version",
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

        api_usage_columns = {column["name"] for column in inspector.get_columns("api_usage_daily")}
        assert api_usage_columns == {
            "id",
            "provider",
            "model_name",
            "date",
            "request_count",
            "token_in",
            "token_out",
            "cost_usd",
        }

        task_foreign_keys = {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in inspector.get_foreign_keys("tasks")
        }
        assert ("project_id", "projects") in task_foreign_keys
        assert ("assignee_agent_id", "agents") in task_foreign_keys
        assert ("parent_task_id", "tasks") in task_foreign_keys

        dependency_foreign_keys = {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in inspector.get_foreign_keys("task_dependencies")
        }
        assert ("task_id", "tasks") in dependency_foreign_keys
        assert ("depends_on_task_id", "tasks") in dependency_foreign_keys

        task_run_foreign_keys = {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in inspector.get_foreign_keys("task_runs")
        }
        assert ("task_id", "tasks") in task_run_foreign_keys
        assert ("agent_id", "agents") in task_run_foreign_keys

        comment_foreign_keys = {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in inspector.get_foreign_keys("comments")
        }
        assert ("document_id", "documents") in comment_foreign_keys
        assert ("task_id", "tasks") in comment_foreign_keys
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
            assert persisted_project.version == 1
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
