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
    RETRY_SCHEDULED = "retry_scheduled"
    INTERRUPTED = "interrupted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceType(StrEnum):
    TASK = "task"
    RUN = "run"
    SYSTEM = "system"
    DOCUMENT = "document"


class InboxItemType(StrEnum):
    AWAIT_USER_INPUT = "await_user_input"
    TASK_COMPLETED = "task_completed"


class InboxStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class DocumentType(StrEnum):
    SPEC = "spec"
    TASK = "task"
    NOTE = "note"
    OTHER = "other"


class CommentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"


TASK_TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.DONE,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
)


TASK_RUN_TERMINAL_STATUSES: frozenset[TaskRunStatus] = frozenset(
    {
        TaskRunStatus.SUCCEEDED,
        TaskRunStatus.FAILED,
        TaskRunStatus.CANCELLED,
    }
)
