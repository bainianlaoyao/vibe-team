from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.agents import ContextBuildRequest, PromptContextBuilder
from app.db.bootstrap import initialize_database
from app.db.engine import create_engine_from_url
from app.db.enums import DocumentType, TaskStatus
from app.db.models import Document, Project, Task, TaskDependency


def _to_sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _create_project_and_task(
    session: Session,
    *,
    root_path: Path,
    priority: int,
    title: str,
) -> tuple[Project, Task]:
    project = Project(name="Context Project", root_path=str(root_path))
    session.add(project)
    session.flush()
    task = Task(
        project_id=project.id,
        title=title,
        description="Implement phase 4 context and tool flow.",
        status=TaskStatus.TODO,
        priority=priority,
    )
    session.add(task)
    session.flush()
    return project, task


def test_context_builder_includes_rules_docs_and_tasks_snapshot(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "docs" / "rules.md").write_text(
        "Rule 1: never read .env directly.\nRule 2: always use command API.",
        encoding="utf-8",
    )
    (workspace / "docs" / "spec.md").write_text(
        "Acceptance: CLI tools must write back task status via HTTP.",
        encoding="utf-8",
    )
    (workspace / "tasks.md").write_text("- [ ] Phase 4\n", encoding="utf-8")

    db_url = _to_sqlite_url(tmp_path / "context-builder.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            project, parent_task = _create_project_and_task(
                session,
                root_path=workspace,
                priority=2,
                title="Parent task",
            )
            task = Task(
                project_id=project.id,
                title="Build context layer",
                description="Assemble task + docs + rules.",
                status=TaskStatus.TODO,
                priority=2,
                parent_task_id=parent_task.id,
            )
            session.add(task)
            session.flush()

            dependency = Task(
                project_id=project.id,
                title="Dependency task",
                description="Must complete first",
                status=TaskStatus.RUNNING,
                priority=1,
            )
            session.add(dependency)
            session.flush()
            session.add(
                TaskDependency(
                    task_id=task.id,
                    depends_on_task_id=dependency.id,
                )
            )
            session.add(
                Document(
                    project_id=project.id,
                    path="docs/spec.md",
                    title="Phase4 Spec",
                    doc_type=DocumentType.SPEC,
                    is_mandatory=True,
                    tags_json=["phase4"],
                )
            )
            session.commit()
            session.refresh(task)
            assert task.id is not None

            builder = PromptContextBuilder(session=session)
            result = builder.build(
                ContextBuildRequest(
                    task_id=task.id,
                    phase="phase4",
                    task_type="backend_api",
                )
            )

            assert result.template_name == "phase4__default.tmpl"
            assert "Rule 1: never read .env directly." in result.prompt
            assert "CLI tools must write back task status via HTTP." in result.prompt
            assert "- [ ] Phase 4" in result.prompt
            assert "depends_on" in result.prompt
            assert result.estimated_tokens <= result.token_budget
    finally:
        engine.dispose()


def test_context_builder_enforces_token_budget_with_trimming(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    large_text = "phase4-constraint " * 400
    (workspace / "docs" / "rules.md").write_text(large_text, encoding="utf-8")
    (workspace / "docs" / "spec.md").write_text(large_text, encoding="utf-8")
    (workspace / "tasks.md").write_text(large_text, encoding="utf-8")

    db_url = _to_sqlite_url(tmp_path / "context-builder-budget.db")
    initialize_database(database_url=db_url, seed=False)
    engine = create_engine_from_url(db_url)

    try:
        with Session(engine) as session:
            project, task = _create_project_and_task(
                session,
                root_path=workspace,
                priority=5,
                title="Budget task",
            )
            session.add(
                Document(
                    project_id=project.id,
                    path="docs/spec.md",
                    title="Large Spec",
                    doc_type=DocumentType.SPEC,
                    is_mandatory=True,
                    tags_json=["large"],
                )
            )
            session.commit()
            session.refresh(task)
            assert task.id is not None

            builder = PromptContextBuilder(session=session)
            result = builder.build(
                ContextBuildRequest(
                    task_id=task.id,
                    phase="phase4",
                    task_type="context",
                    token_budget=120,
                )
            )

            assert result.estimated_tokens <= 120
            assert result.trimmed_sections
            assert "...[truncated]" in result.prompt
    finally:
        engine.dispose()
