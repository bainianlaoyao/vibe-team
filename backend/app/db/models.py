from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, String, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(length=120), nullable=False, index=True))
    root_path: str = Field(sa_column=Column(String(length=512), nullable=False, unique=True))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class Agent(SQLModel, table=True):
    __tablename__ = "agents"

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
    status: str = Field(
        default="active",
        sa_column=Column(String(length=32), nullable=False, index=True),
    )


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", nullable=False, index=True)
    title: str = Field(sa_column=Column(String(length=160), nullable=False, index=True))
    description: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    status: str = Field(
        default="todo",
        sa_column=Column(String(length=32), nullable=False, index=True),
    )
    priority: int = Field(default=3, nullable=False)
    assignee_agent_id: int | None = Field(default=None, foreign_key="agents.id", index=True)
    parent_task_id: int | None = Field(default=None, foreign_key="tasks.id", index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
    due_at: datetime | None = Field(default=None, nullable=True)


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
