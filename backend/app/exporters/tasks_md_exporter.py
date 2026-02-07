from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlmodel import Session, select

from app.core.config import get_settings
from app.db.enums import TaskStatus
from app.db.models import Project, Task

_STATUS_ORDER: tuple[TaskStatus, ...] = (
    TaskStatus.TODO,
    TaskStatus.RUNNING,
    TaskStatus.REVIEW,
    TaskStatus.BLOCKED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.DONE,
)


class TasksMarkdownExporter:
    def __init__(self, *, session: Session) -> None:
        self._session = session

    def render(self, *, project_id: int) -> str:
        project = self._session.get(Project, project_id)
        if project is None:
            raise LookupError(f"Project {project_id} does not exist.")

        tasks = self._list_tasks(project_id=project_id)
        counter = Counter(str(task.status) for task in tasks)
        generated_at = datetime.now(UTC).isoformat()

        lines = [
            "# BeeBeeBrain Tasks Snapshot",
            "",
            f"> Generated At: {generated_at}",
            "> Source: database",
            "",
            f"## Project: {project.name} (id={project.id})",
            "",
            "### Status Summary",
        ]
        for status in _STATUS_ORDER:
            lines.append(f"- `{status.value}`: {counter.get(status.value, 0)}")

        lines.extend(
            [
                "",
                "### Task List",
                "",
                "| ID | Title | Status | Priority | Assignee | Parent | Updated |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )

        if not tasks:
            lines.append("| - | (no tasks) | - | - | - | - | - |")
            return "\n".join(lines) + "\n"

        for task in tasks:
            lines.append(
                "| "
                f"{task.id} | "
                f"{_escape_markdown_cell(task.title)} | "
                f"{task.status} | "
                f"{task.priority} | "
                f"{task.assignee_agent_id or '-'} | "
                f"{task.parent_task_id or '-'} | "
                f"{task.updated_at.isoformat()} |"
            )

        return "\n".join(lines) + "\n"

    def export(self, *, project_id: int, output_path: Path) -> Path:
        markdown = self.render(project_id=project_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    def _list_tasks(self, *, project_id: int) -> list[Task]:
        statement = (
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(
                cast(Any, Task.priority).asc(),
                cast(Any, Task.updated_at).desc(),
                cast(Any, Task.id).desc(),
            )
        )
        return list(self._session.exec(statement).all())


def export_tasks_markdown(*, session: Session, project_id: int, output_path: Path) -> Path:
    exporter = TasksMarkdownExporter(session=session)
    return exporter.export(project_id=project_id, output_path=output_path)


def sync_tasks_markdown_for_project_if_enabled(
    *,
    session: Session,
    project_id: int,
) -> Path | None:
    settings = get_settings()
    if not settings.tasks_md_sync_enabled:
        return None

    output_path = Path(settings.tasks_md_output_path)
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    return export_tasks_markdown(
        session=session,
        project_id=project_id,
        output_path=output_path,
    )


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br/>")
