from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    Date,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from app.db.enums import (
    AgentStatus,
    CommentStatus,
    DependencyType,
    DocumentType,
    InboxCategory,
    InboxStatus,
    SourceType,
    TaskRunStatus,
    TaskStatus,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Project(SQLModel, table=True):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_projects_version_positive"),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(length=120), nullable=False, index=True))
    root_path: str = Field(sa_column=Column(String(length=512), nullable=False, unique=True))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
    version: int = Field(default=1, nullable=False)


class Agent(SQLModel, table=True):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_agents_project_name"),
        CheckConstraint("version >= 1", name="ck_agents_version_positive"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False, index=True)
    name: str = Field(sa_column=Column(String(length=120), nullable=False, index=True))
    role: str = Field(sa_column=Column(String(length=80), nullable=False))
    model_provider: str = Field(sa_column=Column(String(length=80), nullable=False))
    model_name: str = Field(sa_column=Column(String(length=120), nullable=False))
    initial_persona_prompt: str = Field(sa_column=Column(Text(), nullable=False))
    enabled_tools_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON(), nullable=False),
    )
    status: AgentStatus = Field(
        default=AgentStatus.ACTIVE,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    version: int = Field(default=1, nullable=False)


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_tasks_priority_range"),
        CheckConstraint("version >= 1", name="ck_tasks_version_positive"),
        Index("ix_tasks_project_status_priority", "project_id", "status", "priority"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False, index=True)
    title: str = Field(sa_column=Column(String(length=160), nullable=False, index=True))
    description: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    status: TaskStatus = Field(
        default=TaskStatus.TODO,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    priority: int = Field(default=3, nullable=False)
    assignee_agent_id: int | None = Field(default=None, foreign_key="agents.id", index=True)
    parent_task_id: int | None = Field(default=None, foreign_key="tasks.id", index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
    due_at: datetime | None = Field(default=None, nullable=True)
    version: int = Field(default=1, nullable=False)


class TaskDependency(SQLModel, table=True):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
        CheckConstraint("task_id <> depends_on_task_id", name="ck_task_dependencies_not_self"),
    )

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", nullable=False, index=True)
    depends_on_task_id: int = Field(foreign_key="tasks.id", nullable=False, index=True)
    dependency_type: DependencyType = Field(
        default=DependencyType.FINISH_TO_START,
        sa_column=Column(String(length=32), nullable=False),
    )


class TaskRun(SQLModel, table=True):
    __tablename__ = "task_runs"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt", name="uq_task_runs_task_attempt"),
        CheckConstraint("attempt >= 1", name="ck_task_runs_attempt_positive"),
        CheckConstraint("token_in >= 0", name="ck_task_runs_token_in_non_negative"),
        CheckConstraint("token_out >= 0", name="ck_task_runs_token_out_non_negative"),
        CheckConstraint("cost_usd >= 0", name="ck_task_runs_cost_non_negative"),
        CheckConstraint("version >= 1", name="ck_task_runs_version_positive"),
        Index("ix_task_runs_task_status_started", "task_id", "run_status", "started_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", nullable=False, index=True)
    agent_id: int | None = Field(default=None, foreign_key="agents.id", index=True)
    run_status: TaskRunStatus = Field(
        default=TaskRunStatus.QUEUED,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    attempt: int = Field(default=1, nullable=False)
    started_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    ended_at: datetime | None = Field(default=None, nullable=True)
    error_code: str | None = Field(default=None, sa_column=Column(String(length=64), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    token_in: int = Field(default=0, nullable=False)
    token_out: int = Field(default=0, nullable=False)
    cost_usd: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(12, 4), nullable=False),
    )
    version: int = Field(default=1, nullable=False)


class InboxItem(SQLModel, table=True):
    __tablename__ = "inbox_items"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_inbox_items_version_positive"),
        Index("ix_inbox_items_project_status", "project_id", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False, index=True)
    source_type: SourceType = Field(
        default=SourceType.SYSTEM,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    source_id: str = Field(sa_column=Column(String(length=64), nullable=False, index=True))
    category: InboxCategory = Field(
        default=InboxCategory.NEEDS_REVIEW,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    title: str = Field(sa_column=Column(String(length=160), nullable=False, index=True))
    content: str = Field(sa_column=Column(Text(), nullable=False))
    status: InboxStatus = Field(
        default=InboxStatus.OPEN,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    resolved_at: datetime | None = Field(default=None, nullable=True)
    resolver: str | None = Field(default=None, sa_column=Column(String(length=120), nullable=True))
    version: int = Field(default=1, nullable=False)


class Document(SQLModel, table=True):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "path", name="uq_documents_project_path"),
        CheckConstraint("version >= 1", name="ck_documents_version_positive"),
        Index("ix_documents_project_doc_type", "project_id", "doc_type"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False, index=True)
    path: str = Field(sa_column=Column(String(length=512), nullable=False))
    title: str = Field(sa_column=Column(String(length=200), nullable=False, index=True))
    doc_type: DocumentType = Field(
        default=DocumentType.OTHER,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    is_mandatory: bool = Field(default=False, nullable=False)
    tags_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON(), nullable=False),
    )
    version: int = Field(default=1, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


class Comment(SQLModel, table=True):
    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint(
            "(document_id IS NOT NULL) OR (task_id IS NOT NULL)",
            name="ck_comments_target_present",
        ),
        CheckConstraint("version >= 1", name="ck_comments_version_positive"),
    )

    id: int | None = Field(default=None, primary_key=True)
    document_id: int | None = Field(default=None, foreign_key="documents.id", index=True)
    task_id: int | None = Field(default=None, foreign_key="tasks.id", index=True)
    anchor: str | None = Field(default=None, sa_column=Column(String(length=240), nullable=True))
    comment_text: str = Field(sa_column=Column(Text(), nullable=False))
    author: str = Field(sa_column=Column(String(length=120), nullable=False, index=True))
    status: CommentStatus = Field(
        default=CommentStatus.OPEN,
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    version: int = Field(default=1, nullable=False)


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False, index=True)
    event_type: str = Field(sa_column=Column(String(length=120), nullable=False, index=True))
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON(), nullable=False),
    )
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    trace_id: str | None = Field(default=None, sa_column=Column(String(length=64), nullable=True))


class ApiUsageDaily(SQLModel, table=True):
    __tablename__ = "api_usage_daily"
    __table_args__ = (
        UniqueConstraint("provider", "model_name", "date", name="uq_api_usage_daily_dim"),
        CheckConstraint("request_count >= 0", name="ck_api_usage_daily_request_count_non_negative"),
        CheckConstraint("token_in >= 0", name="ck_api_usage_daily_token_in_non_negative"),
        CheckConstraint("token_out >= 0", name="ck_api_usage_daily_token_out_non_negative"),
        CheckConstraint("cost_usd >= 0", name="ck_api_usage_daily_cost_non_negative"),
    )

    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(sa_column=Column(String(length=80), nullable=False, index=True))
    model_name: str = Field(sa_column=Column(String(length=120), nullable=False, index=True))
    date: date_type = Field(sa_column=Column(Date(), nullable=False, index=True))
    request_count: int = Field(default=0, nullable=False)
    token_in: int = Field(default=0, nullable=False)
    token_out: int = Field(default=0, nullable=False)
    cost_usd: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(12, 4), nullable=False),
    )
