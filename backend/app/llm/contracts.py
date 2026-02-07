from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol


class LLMRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: LLMRole
    content: str


@dataclass(frozen=True, slots=True)
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMUsage:
    request_count: int = 1
    token_in: int = 0
    token_out: int = 0
    cost_usd: Decimal = Decimal("0.0000")


@dataclass(frozen=True, slots=True)
class LLMRequest:
    provider: str
    model: str | None
    messages: list[LLMMessage]
    session_id: str = "default"
    system_prompt: str | None = None
    max_turns: int | None = None
    cwd: Path | None = None
    trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class LLMResponse:
    provider: str
    model: str | None
    session_id: str
    text: str
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    stop_reason: str | None = None
    raw_result: str | None = None


class LLMClient(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
