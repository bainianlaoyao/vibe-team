from __future__ import annotations

from enum import StrEnum


class AgentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TaskStatus(StrEnum):
    TODO = "todo"
    RUNNING = "running"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DependencyType(StrEnum):
    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"
    FINISH_TO_FINISH = "finish_to_finish"
    START_TO_FINISH = "start_to_finish"


class TaskRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceType(StrEnum):
    TASK = "task"
    RUN = "run"
    SYSTEM = "system"
    DOCUMENT = "document"


class InboxCategory(StrEnum):
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    RISK = "risk"


class InboxStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class DocumentType(StrEnum):
    SPEC = "spec"
    TASK = "task"
    NOTE = "note"
    OTHER = "other"


class CommentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


TASK_TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.DONE,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
)
