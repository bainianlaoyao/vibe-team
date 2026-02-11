from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Protocol, cast
from uuid import uuid4

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import select

from app.agents.persona_loader import PersonaLoader
from app.core.config import Settings, get_settings
from app.core.logging import bind_log_context, clear_log_context, get_logger
from app.db.enums import (
    ConversationStatus,
    InboxItemType,
    InboxStatus,
    MessageRole,
    MessageType,
    SessionStatus,
    SourceType,
    TaskStatus,
)
from app.db.models import (
    Agent,
    Conversation,
    ConversationSession,
    Event,
    InboxItem,
    Message,
    Project,
    Task,
    utc_now,
)
from app.db.repositories import MessageRepository, SessionRepository
from app.db.session import session_scope
from app.events.schemas import TASK_STATUS_CHANGED_EVENT_TYPE, build_task_status_payload
from app.llm.providers.claude_code import CLAUDE_PROVIDER_NAME
from app.llm.providers.claude_settings import resolve_claude_auth
from app.security import SecureFileGateway

router = APIRouter(tags=["ws_conversations"])

logger = get_logger("bbb.runtime.conversation.ws")

HEARTBEAT_TIMEOUT_S = 90
MAX_TURN_QUEUE_SIZE = 16
REPLAY_BATCH_LIMIT = 500
MAX_RAW_EVENT_JSON_CHARS = 8000

CONVERSATION_INPUT_REQUESTED_EVENT_TYPE = "conversation.input.requested"
CONVERSATION_INPUT_SUBMITTED_EVENT_TYPE = "conversation.input.submitted"
CONVERSATION_INTERRUPTED_EVENT_TYPE = "conversation.interrupted"


class WSMessageType(StrEnum):
    # Client -> Server
    USER_MESSAGE = "user.message"
    USER_INPUT_RESPONSE = "user.input_response"
    USER_INTERRUPT = "user.interrupt"
    SESSION_HEARTBEAT = "session.heartbeat"

    # Server -> Client
    SESSION_CONNECTED = "session.connected"
    SESSION_RESUMED = "session.resumed"
    SESSION_STATE = "session.state"
    SESSION_HEARTBEAT_ACK = "session.heartbeat_ack"
    SESSION_ERROR = "session.error"
    MESSAGE_REPLAY = "message.replay"
    USER_MESSAGE_ACK = "user.message.ack"
    USER_INPUT_RESPONSE_ACK = "user.input_response.ack"
    USER_INTERRUPT_ACK = "user.interrupt.ack"
    ASSISTANT_CHUNK = "assistant.chunk"
    ASSISTANT_THINKING = "assistant.thinking"
    ASSISTANT_TOOL_CALL = "assistant.tool_call"
    ASSISTANT_TOOL_RESULT = "assistant.tool_result"
    ASSISTANT_REQUEST_INPUT = "assistant.request_input"
    ASSISTANT_COMPLETE = "assistant.complete"
    SESSION_SYSTEM_EVENT = "session.system_event"


class ConversationRuntimeState(StrEnum):
    ACTIVE = "active"
    STREAMING = "streaming"
    WAITING_INPUT = "waiting_input"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class WSIncomingMessage(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class WSOutgoingEnvelope(BaseModel):
    type: str
    conversation_id: int
    turn_id: int | None = None
    sequence: int
    timestamp: str
    trace_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class UserMessagePayload(BaseModel):
    content: str = Field(min_length=1, max_length=40000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserInputResponsePayload(BaseModel):
    question_id: str = Field(min_length=1, max_length=200)
    answer: str = Field(max_length=40000)
    resume_task: bool = False


@dataclass(slots=True)
class TurnCommand:
    turn_id: int
    trace_id: str
    kind: Literal["user_message", "input_response"]
    content: str
    question_id: str | None = None
    resume_task: bool = False


class ClaudeSessionClient(Protocol):
    async def connect(self, prompt: str | AsyncIterable[dict[str, Any]] | None = None) -> None: ...
    async def query(
        self,
        prompt: str | AsyncIterable[dict[str, Any]],
        session_id: str = "default",
    ) -> None: ...
    def receive_response(self) -> AsyncIterator[Any]: ...
    async def interrupt(self) -> None: ...
    async def disconnect(self) -> None: ...


@dataclass
class ConnectionState:
    websocket: WebSocket
    settings: Settings
    conversation_id: int
    client_id: str
    session_id: int
    project_id: int
    agent_id: int
    task_id: int | None
    model_provider: str
    model_name: str
    system_prompt: str
    workspace_root: Path | None
    protocol: str = "v2"
    sdk_session_id: str = ""
    runtime_state: ConversationRuntimeState = ConversationRuntimeState.ACTIVE
    outgoing_sequence: int = 0
    turn_counter: int = 0
    active_turn_id: int | None = None
    turn_queue: asyncio.Queue[TurnCommand] = field(
        default_factory=lambda: asyncio.Queue(maxsize=MAX_TURN_QUEUE_SIZE)
    )
    worker_task: asyncio.Task[None] | None = None
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    input_timeout_task: asyncio.Task[None] | None = None
    pending_question_id: str | None = None
    pending_question_required: bool = True
    pending_question_deadline: datetime | None = None
    pending_question_options: list[str] = field(default_factory=list)
    pending_question_metadata: dict[str, Any] = field(default_factory=dict)
    pending_question_inbox_id: int | None = None
    sdk_client: ClaudeSessionClient | None = None
    sdk_connected: bool = False
    session_trace_id: str = field(default_factory=lambda: f"trace-conv-{uuid4().hex}")
    closed: bool = False

    def next_outgoing_sequence(self) -> int:
        self.outgoing_sequence += 1
        return self.outgoing_sequence

    def next_turn_id(self) -> int:
        self.turn_counter += 1
        return self.turn_counter


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, ConnectionState] = {}
        self._lock = asyncio.Lock()

    async def connect(self, state: ConnectionState) -> None:
        existing: ConnectionState | None = None
        async with self._lock:
            existing = self._connections.get(state.conversation_id)
            self._connections[state.conversation_id] = state
        if existing is not None:
            await _shutdown_state(existing, close_socket=True, reason="replaced by new connection")

    async def remove_if_current(self, conversation_id: int, state: ConnectionState) -> None:
        async with self._lock:
            current = self._connections.get(conversation_id)
            if current is state:
                self._connections.pop(conversation_id, None)


manager = ConnectionManager()


def _now_ts() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _normalize_trace_id(trace_id: str | None) -> str:
    candidate = (trace_id or "").strip()
    if candidate:
        return candidate
    return f"trace-conv-{uuid4().hex}"


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            return int(normalized)
    return None


def _is_supported_provider(provider: str) -> bool:
    normalized = provider.strip().lower()
    return normalized in {"anthropic", CLAUDE_PROVIDER_NAME}


def _create_claude_session_client(state: ConnectionState) -> ClaudeSessionClient:
    auth = resolve_claude_auth(settings_path_override=state.settings.claude_settings_path)
    options = ClaudeAgentOptions(
        model=state.model_name,
        system_prompt=state.system_prompt or None,
        max_turns=state.settings.claude_default_max_turns,
        cwd=state.workspace_root,
        settings=str(auth.settings_path) if auth.settings_path else None,
        env=auth.env,
        cli_path=state.settings.claude_cli_path,
        include_partial_messages=True,
    )
    return ClaudeSDKClient(options=options)


async def _send_envelope(
    state: ConnectionState,
    *,
    msg_type: WSMessageType | str,
    payload: dict[str, Any],
    trace_id: str,
    turn_id: int | None = None,
    message_sequence: int | None = None,
) -> bool:
    outgoing_payload = dict(payload)
    if message_sequence is not None:
        outgoing_payload["message_sequence"] = message_sequence

    envelope = WSOutgoingEnvelope(
        type=msg_type.value if isinstance(msg_type, WSMessageType) else msg_type,
        conversation_id=state.conversation_id,
        turn_id=turn_id,
        sequence=state.next_outgoing_sequence(),
        timestamp=_now_ts(),
        trace_id=trace_id,
        payload=outgoing_payload,
    )

    try:
        await state.websocket.send_json(envelope.model_dump(mode="json"))
        return True
    except Exception as exc:  # pragma: no cover - socket close race
        logger.warning(
            "conversation.ws.send_failed",
            conversation_id=state.conversation_id,
            turn_id=turn_id,
            error=str(exc),
        )
        return False


async def _send_direct_error(
    websocket: WebSocket,
    *,
    conversation_id: int,
    code: str,
    message: str,
) -> None:
    envelope = WSOutgoingEnvelope(
        type=WSMessageType.SESSION_ERROR.value,
        conversation_id=conversation_id,
        turn_id=None,
        sequence=1,
        timestamp=_now_ts(),
        trace_id=_normalize_trace_id(None),
        payload={"code": code, "message": message},
    )
    await websocket.send_json(envelope.model_dump(mode="json"))


async def _send_error(
    state: ConnectionState,
    *,
    code: str,
    message: str,
    trace_id: str,
    turn_id: int | None = None,
) -> None:
    await _send_envelope(
        state,
        msg_type=WSMessageType.SESSION_ERROR,
        payload={"code": code, "message": message},
        trace_id=trace_id,
        turn_id=turn_id,
    )


async def _emit_runtime_state(
    state: ConnectionState,
    *,
    next_state: ConversationRuntimeState,
    trace_id: str,
    turn_id: int | None = None,
    reason: str | None = None,
) -> None:
    state.runtime_state = next_state
    payload: dict[str, Any] = {"state": next_state.value}
    if reason:
        payload["reason"] = reason
    await _send_envelope(
        state,
        msg_type=WSMessageType.SESSION_STATE,
        payload=payload,
        trace_id=trace_id,
        turn_id=turn_id,
    )


def _persist_message(
    *,
    conversation_id: int,
    role: MessageRole,
    message_type: MessageType,
    content: str,
    metadata_json: dict[str, Any],
) -> tuple[int | None, int]:
    with session_scope() as session:
        repo = MessageRepository(session)
        sequence_num = repo.get_next_sequence_num(conversation_id)
        message = Message(
            conversation_id=conversation_id,
            role=role,
            message_type=message_type,
            content=content,
            metadata_json=metadata_json,
            sequence_num=sequence_num,
        )
        message = repo.create(message)
        return message.id, sequence_num


def _has_answered_question(*, conversation_id: int, question_id: str) -> bool:
    with session_scope() as session:
        messages = MessageRepository(session).list_by_conversation(conversation_id, limit=1000)
    for message in messages:
        if _enum_value(message.message_type) != MessageType.INPUT_RESPONSE.value:
            continue
        metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
        if str(metadata.get("question_id", "")) == question_id:
            return True
    return False


def _list_messages_after_sequence(
    *,
    conversation_id: int,
    after_sequence: int,
) -> list[Message]:
    with session_scope() as session:
        return MessageRepository(session).list_by_conversation(
            conversation_id,
            after_sequence=after_sequence,
            limit=REPLAY_BATCH_LIMIT,
        )


def _raw_event_payload(value: Any) -> dict[str, Any]:
    serialized: Any
    if is_dataclass(value) and not isinstance(value, type):
        serialized = asdict(value)
    elif isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        serialized = value
    else:
        serialized = {"repr": repr(value)}

    raw_json = json.dumps(serialized, ensure_ascii=False, default=str)
    if len(raw_json) <= MAX_RAW_EVENT_JSON_CHARS:
        return {"truncated": False, "payload": serialized}
    return {
        "truncated": True,
        "raw_size": len(raw_json),
        "payload_preview": raw_json[:MAX_RAW_EVENT_JSON_CHARS],
    }


def _usage_payload_from_result(result: ResultMessage) -> dict[str, Any]:
    usage_payload = result.usage if isinstance(result.usage, dict) else {}
    raw_in = usage_payload.get("input_tokens", 0)
    raw_cache_create = usage_payload.get("cache_creation_input_tokens", 0)
    raw_cache_read = usage_payload.get("cache_read_input_tokens", 0)
    raw_out = usage_payload.get("output_tokens", 0)

    def _to_non_negative_int(value: Any) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value if value >= 0 else 0
        if isinstance(value, float):
            return int(value) if value >= 0 else 0
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.isdigit():
                return int(normalized)
        return 0

    token_in = (
        _to_non_negative_int(raw_in)
        + _to_non_negative_int(raw_cache_create)
        + _to_non_negative_int(raw_cache_read)
    )
    token_out = _to_non_negative_int(raw_out)
    raw_cost = result.total_cost_usd if result.total_cost_usd is not None else 0.0
    try:
        cost_value = float(raw_cost)
    except Exception:
        cost_value = 0.0
    if cost_value < 0:
        cost_value = 0.0
    return {
        "token_in": token_in,
        "token_out": token_out,
        "cost_usd": f"{cost_value:.4f}",
    }


def _is_interrupt_subtype(subtype: str) -> bool:
    normalized = subtype.strip().lower()
    return "interrupt" in normalized or "cancel" in normalized


async def _single_message_stream(payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    yield payload


def _build_turn_trace_id(conversation_id: int) -> str:
    return f"trace-conv-{conversation_id}-{uuid4().hex}"


def _build_sdk_message_payload(state: ConnectionState, command: TurnCommand) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "user",
        "message": {
            "role": "user",
            "content": command.content,
        },
        "parent_tool_use_id": None,
        "tool_use_result": None,
        "session_id": state.sdk_session_id,
    }
    if command.kind == "input_response":
        payload["parent_tool_use_id"] = command.question_id
        payload["tool_use_result"] = {
            "question_id": command.question_id,
            "answer": command.content,
        }
    return payload


async def _ensure_sdk_connected(state: ConnectionState) -> None:
    if state.sdk_connected and state.sdk_client is not None:
        return
    state.sdk_client = _create_claude_session_client(state)
    await state.sdk_client.connect()
    state.sdk_connected = True


def _open_or_get_input_inbox(
    *,
    state: ConnectionState,
    question_id: str,
    question: str,
    trace_id: str,
) -> int | None:
    source_id = f"conversation:{state.conversation_id}:question:{question_id}"
    with session_scope() as session:
        existing = session.exec(
            select(InboxItem)
            .where(InboxItem.project_id == state.project_id)
            .where(InboxItem.source_id == source_id)
            .where(InboxItem.status == InboxStatus.OPEN.value)
            .order_by(cast(Any, InboxItem.id).desc())
            .limit(1)
        ).first()
        if existing is not None:
            return existing.id

        item = InboxItem(
            project_id=state.project_id,
            source_type=SourceType.TASK if state.task_id is not None else SourceType.SYSTEM,
            source_id=source_id,
            item_type=InboxItemType.AWAIT_USER_INPUT,
            title=f"Conversation question: {question_id}",
            content=question or "(empty question)",
            status=InboxStatus.OPEN,
        )
        session.add(item)
        session.flush()
        session.add(
            Event(
                project_id=state.project_id,
                event_type="inbox.item.created",
                payload_json={
                    "item_id": item.id,
                    "source_id": source_id,
                    "conversation_id": state.conversation_id,
                    "question_id": question_id,
                },
                trace_id=trace_id,
            )
        )
        session.add(
            Event(
                project_id=state.project_id,
                event_type=CONVERSATION_INPUT_REQUESTED_EVENT_TYPE,
                payload_json={
                    "conversation_id": state.conversation_id,
                    "question_id": question_id,
                    "inbox_item_id": item.id,
                },
                trace_id=trace_id,
            )
        )
        session.commit()
        session.refresh(item)
        return item.id


def _close_input_inbox(
    *,
    state: ConnectionState,
    question_id: str,
    answer: str,
    trace_id: str,
) -> None:
    with session_scope() as session:
        inbox_item_id = state.pending_question_inbox_id
        if inbox_item_id is not None:
            item = session.get(InboxItem, inbox_item_id)
            if item is not None and _enum_value(item.status) == InboxStatus.OPEN.value:
                item.status = InboxStatus.CLOSED
                item.resolved_at = utc_now()
                item.resolver = "conversation"
                item.version += 1
                session.add(item)
                session.add(
                    Event(
                        project_id=state.project_id,
                        event_type="inbox.item.closed",
                        payload_json={
                            "item_id": item.id,
                            "conversation_id": state.conversation_id,
                            "question_id": question_id,
                        },
                        trace_id=trace_id,
                    )
                )

        session.add(
            Event(
                project_id=state.project_id,
                event_type=CONVERSATION_INPUT_SUBMITTED_EVENT_TYPE,
                payload_json={
                    "conversation_id": state.conversation_id,
                    "question_id": question_id,
                    "answer_preview": answer[:200],
                },
                trace_id=trace_id,
            )
        )
        session.commit()


def _cancel_task(task: asyncio.Task[Any] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()


def _clear_pending_question(state: ConnectionState) -> None:
    _cancel_task(state.input_timeout_task)
    state.input_timeout_task = None
    state.pending_question_id = None
    state.pending_question_required = True
    state.pending_question_deadline = None
    state.pending_question_options = []
    state.pending_question_metadata = {}
    state.pending_question_inbox_id = None


def _schedule_input_timeout_watch(
    state: ConnectionState,
    *,
    question_id: str,
    trace_id: str,
    turn_id: int,
) -> None:
    _cancel_task(state.input_timeout_task)
    deadline = state.pending_question_deadline
    if deadline is None:
        return

    async def _watch() -> None:
        wait_seconds = max((deadline - utc_now()).total_seconds(), 0.0)
        await asyncio.sleep(wait_seconds)
        if state.closed:
            return
        if state.pending_question_id != question_id:
            return
        await _send_error(
            state,
            code="INPUT_TIMEOUT",
            message="Input response timed out.",
            trace_id=trace_id,
            turn_id=turn_id,
        )
        await _emit_runtime_state(
            state,
            next_state=ConversationRuntimeState.ERROR,
            trace_id=trace_id,
            turn_id=turn_id,
            reason="input_timeout",
        )

    state.input_timeout_task = asyncio.create_task(_watch())


async def _handle_request_input_tool(
    *,
    state: ConnectionState,
    block: ToolUseBlock,
    trace_id: str,
    turn_id: int,
    raw_event: dict[str, Any],
) -> None:
    raw_question = block.input.get("question", block.input.get("content", ""))
    question = str(raw_question).strip()
    raw_options = block.input.get("options")
    options = [str(item) for item in raw_options] if isinstance(raw_options, list) else []
    required = block.input.get("required", True)
    required_bool = bool(required) if isinstance(required, bool) else True
    metadata = block.input.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}

    state.pending_question_id = block.id
    state.pending_question_required = required_bool
    state.pending_question_deadline = utc_now() + timedelta(
        seconds=state.settings.chat_input_timeout_s
    )
    state.pending_question_options = options
    state.pending_question_metadata = metadata_dict
    state.pending_question_inbox_id = _open_or_get_input_inbox(
        state=state,
        question_id=block.id,
        question=question,
        trace_id=trace_id,
    )
    _schedule_input_timeout_watch(
        state,
        question_id=block.id,
        trace_id=trace_id,
        turn_id=turn_id,
    )

    _, message_sequence = _persist_message(
        conversation_id=state.conversation_id,
        role=MessageRole.ASSISTANT,
        message_type=MessageType.INPUT_REQUEST,
        content=question,
        metadata_json={
            "turn_id": turn_id,
            "trace_id": trace_id,
            "question_id": block.id,
            "options": options,
            "required": required_bool,
            "metadata": metadata_dict,
            "inbox_item_id": state.pending_question_inbox_id,
            "deadline_at": (
                state.pending_question_deadline.isoformat().replace("+00:00", "Z")
                if state.pending_question_deadline is not None
                else None
            ),
            "raw_event": raw_event,
        },
    )
    await _send_envelope(
        state,
        msg_type=WSMessageType.ASSISTANT_REQUEST_INPUT,
        payload={
            "question_id": block.id,
            "question": question,
            "options": options,
            "required": required_bool,
            "metadata": metadata_dict,
            "inbox_item_id": state.pending_question_inbox_id,
            "deadline_at": (
                state.pending_question_deadline.isoformat().replace("+00:00", "Z")
                if state.pending_question_deadline is not None
                else None
            ),
        },
        trace_id=trace_id,
        turn_id=turn_id,
        message_sequence=message_sequence,
    )


async def _process_turn(state: ConnectionState, command: TurnCommand) -> None:
    trace_id = command.trace_id
    state.active_turn_id = command.turn_id
    bind_log_context(trace_id=trace_id, task_id=state.task_id, agent_id=state.agent_id)
    turn_started_at = perf_counter()

    await _emit_runtime_state(
        state,
        next_state=ConversationRuntimeState.STREAMING,
        trace_id=trace_id,
        turn_id=command.turn_id,
    )
    await _ensure_sdk_connected(state)
    if command.kind == "input_response":
        _clear_pending_question(state)

    sdk_payload = _build_sdk_message_payload(state, command)
    assert state.sdk_client is not None
    await state.sdk_client.query(
        prompt=_single_message_stream(sdk_payload),
        session_id=state.sdk_session_id,
    )

    usage_payload: dict[str, Any] | None = None
    stop_reason: str | None = None
    interrupted = False
    tools_used: list[str] = []

    async for sdk_message in state.sdk_client.receive_response():
        raw_event = _raw_event_payload(sdk_message)

        if isinstance(sdk_message, AssistantMessage):
            if sdk_message.error is not None:
                await _send_error(
                    state,
                    code="ASSISTANT_ERROR",
                    message=f"Claude assistant returned error: {sdk_message.error}",
                    trace_id=trace_id,
                    turn_id=command.turn_id,
                )
            for block in sdk_message.content:
                if isinstance(block, TextBlock):
                    _, message_sequence = _persist_message(
                        conversation_id=state.conversation_id,
                        role=MessageRole.ASSISTANT,
                        message_type=MessageType.TEXT,
                        content=block.text,
                        metadata_json={
                            "turn_id": command.turn_id,
                            "trace_id": trace_id,
                            "stream": True,
                            "raw_event": raw_event,
                        },
                    )
                    await _send_envelope(
                        state,
                        msg_type=WSMessageType.ASSISTANT_CHUNK,
                        payload={"content": block.text},
                        trace_id=trace_id,
                        turn_id=command.turn_id,
                        message_sequence=message_sequence,
                    )
                    continue

                if isinstance(block, ThinkingBlock):
                    _, message_sequence = _persist_message(
                        conversation_id=state.conversation_id,
                        role=MessageRole.ASSISTANT,
                        message_type=MessageType.TEXT,
                        content=block.thinking,
                        metadata_json={
                            "turn_id": command.turn_id,
                            "trace_id": trace_id,
                            "thinking": True,
                            "signature": block.signature,
                            "raw_event": raw_event,
                        },
                    )
                    await _send_envelope(
                        state,
                        msg_type=WSMessageType.ASSISTANT_THINKING,
                        payload={"content": block.thinking, "signature": block.signature},
                        trace_id=trace_id,
                        turn_id=command.turn_id,
                        message_sequence=message_sequence,
                    )
                    continue

                if isinstance(block, ToolUseBlock):
                    tools_used.append(block.name)
                    _, message_sequence = _persist_message(
                        conversation_id=state.conversation_id,
                        role=MessageRole.ASSISTANT,
                        message_type=MessageType.TOOL_CALL,
                        content=block.name,
                        metadata_json={
                            "turn_id": command.turn_id,
                            "trace_id": trace_id,
                            "tool_id": block.id,
                            "arguments": block.input,
                            "raw_event": raw_event,
                        },
                    )
                    await _send_envelope(
                        state,
                        msg_type=WSMessageType.ASSISTANT_TOOL_CALL,
                        payload={
                            "id": block.id,
                            "name": block.name,
                            "arguments": block.input,
                        },
                        trace_id=trace_id,
                        turn_id=command.turn_id,
                        message_sequence=message_sequence,
                    )
                    if block.name == "request_input":
                        await _handle_request_input_tool(
                            state=state,
                            block=block,
                            trace_id=trace_id,
                            turn_id=command.turn_id,
                            raw_event=raw_event,
                        )
                    continue

                if isinstance(block, ToolResultBlock):
                    result_content = (
                        block.content
                        if isinstance(block.content, str)
                        else (
                            json.dumps(block.content, ensure_ascii=False, default=str)
                            if block.content is not None
                            else ""
                        )
                    )
                    _, message_sequence = _persist_message(
                        conversation_id=state.conversation_id,
                        role=MessageRole.ASSISTANT,
                        message_type=MessageType.TOOL_RESULT,
                        content=result_content,
                        metadata_json={
                            "turn_id": command.turn_id,
                            "trace_id": trace_id,
                            "tool_id": block.tool_use_id,
                            "is_error": bool(block.is_error),
                            "raw_event": raw_event,
                        },
                    )
                    await _send_envelope(
                        state,
                        msg_type=WSMessageType.ASSISTANT_TOOL_RESULT,
                        payload={
                            "tool_id": block.tool_use_id,
                            "result": result_content,
                            "is_error": bool(block.is_error),
                        },
                        trace_id=trace_id,
                        turn_id=command.turn_id,
                        message_sequence=message_sequence,
                    )
                    continue

        elif isinstance(sdk_message, SystemMessage):
            _, message_sequence = _persist_message(
                conversation_id=state.conversation_id,
                role=MessageRole.SYSTEM,
                message_type=MessageType.TEXT,
                content=sdk_message.subtype,
                metadata_json={
                    "turn_id": command.turn_id,
                    "trace_id": trace_id,
                    "system_data": sdk_message.data,
                    "raw_event": raw_event,
                },
            )
            await _send_envelope(
                state,
                msg_type=WSMessageType.SESSION_SYSTEM_EVENT,
                payload={
                    "subtype": sdk_message.subtype,
                    "data": sdk_message.data,
                },
                trace_id=trace_id,
                turn_id=command.turn_id,
                message_sequence=message_sequence,
            )
            continue

        elif isinstance(sdk_message, UserMessage):
            continue

        elif isinstance(sdk_message, ResultMessage):
            usage_payload = _usage_payload_from_result(sdk_message)
            stop_reason = sdk_message.subtype
            if sdk_message.is_error:
                if _is_interrupt_subtype(sdk_message.subtype):
                    interrupted = True
                else:
                    await _emit_runtime_state(
                        state,
                        next_state=ConversationRuntimeState.ERROR,
                        trace_id=trace_id,
                        turn_id=command.turn_id,
                        reason=sdk_message.subtype,
                    )
                    await _send_error(
                        state,
                        code="LLM_RESULT_ERROR",
                        message=sdk_message.result or f"Claude run failed: {sdk_message.subtype}",
                        trace_id=trace_id,
                        turn_id=command.turn_id,
                    )
            break

    if state.runtime_state != ConversationRuntimeState.ERROR:
        if state.pending_question_id is not None:
            await _emit_runtime_state(
                state,
                next_state=ConversationRuntimeState.WAITING_INPUT,
                trace_id=trace_id,
                turn_id=command.turn_id,
            )
        elif interrupted:
            await _emit_runtime_state(
                state,
                next_state=ConversationRuntimeState.INTERRUPTED,
                trace_id=trace_id,
                turn_id=command.turn_id,
                reason=stop_reason or "interrupt",
            )
        else:
            await _emit_runtime_state(
                state,
                next_state=ConversationRuntimeState.ACTIVE,
                trace_id=trace_id,
                turn_id=command.turn_id,
            )

    await _send_envelope(
        state,
        msg_type=WSMessageType.ASSISTANT_COMPLETE,
        payload={
            "usage": usage_payload,
            "stop_reason": stop_reason,
            "interrupted": interrupted,
        },
        trace_id=trace_id,
        turn_id=command.turn_id,
    )

    duration_ms = int((perf_counter() - turn_started_at) * 1000)
    logger.info(
        "conversation.turn.completed",
        conversation_id=state.conversation_id,
        turn_id=command.turn_id,
        duration_ms=duration_ms,
        queue_size=state.turn_queue.qsize(),
        stop_reason=stop_reason,
        tools=tools_used,
        interrupted=interrupted,
    )
    state.active_turn_id = None
    clear_log_context()


async def _turn_worker(state: ConnectionState) -> None:
    while not state.shutdown_event.is_set():
        try:
            command = await asyncio.wait_for(state.turn_queue.get(), timeout=1.0)
        except TimeoutError:
            continue

        try:
            await _process_turn(state, command)
        except Exception as exc:
            logger.exception(
                "conversation.turn.failed",
                conversation_id=state.conversation_id,
                turn_id=command.turn_id,
                error=str(exc),
            )
            await _emit_runtime_state(
                state,
                next_state=ConversationRuntimeState.ERROR,
                trace_id=command.trace_id,
                turn_id=command.turn_id,
                reason="runtime_exception",
            )
            await _send_error(
                state,
                code="EXECUTION_ERROR",
                message=str(exc),
                trace_id=command.trace_id,
                turn_id=command.turn_id,
            )
            state.active_turn_id = None
            clear_log_context()
        finally:
            state.turn_queue.task_done()


def _maybe_resume_blocked_task(*, conversation_id: int, task_id: int | None, trace_id: str) -> None:
    if task_id is None:
        return
    with session_scope() as session:
        task = session.get(Task, task_id)
        conversation = session.get(Conversation, conversation_id)
        if task is None or conversation is None:
            return
        if str(task.status) != TaskStatus.BLOCKED.value:
            return
        previous_status = task.status
        task.status = TaskStatus.TODO
        task.updated_at = utc_now()
        task.version += 1
        session.add(
            Event(
                project_id=conversation.project_id,
                event_type=TASK_STATUS_CHANGED_EVENT_TYPE,
                payload_json=build_task_status_payload(
                    task_id=task_id,
                    previous_status=previous_status,
                    status=TaskStatus.TODO,
                    run_id=None,
                    actor="conversation",
                ),
                trace_id=trace_id,
            )
        )
        session.commit()


def _persist_interrupt_audit(state: ConnectionState, *, trace_id: str) -> None:
    with session_scope() as session:
        session.add(
            Event(
                project_id=state.project_id,
                event_type=CONVERSATION_INTERRUPTED_EVENT_TYPE,
                payload_json={
                    "conversation_id": state.conversation_id,
                    "turn_id": state.active_turn_id,
                },
                trace_id=trace_id,
            )
        )
        session.commit()


async def _handle_heartbeat(state: ConnectionState) -> None:
    trace_id = _build_turn_trace_id(state.conversation_id)
    await _send_envelope(
        state,
        msg_type=WSMessageType.SESSION_HEARTBEAT_ACK,
        payload={"server_time": _now_ts()},
        trace_id=trace_id,
    )
    with session_scope() as session:
        SessionRepository(session).update_heartbeat(state.session_id)


async def _handle_user_message(state: ConnectionState, payload: dict[str, Any]) -> None:
    trace_id = _build_turn_trace_id(state.conversation_id)
    try:
        parsed = UserMessagePayload.model_validate(payload)
    except ValidationError as exc:
        await _send_error(
            state,
            code="INVALID_USER_MESSAGE",
            message=str(exc),
            trace_id=trace_id,
        )
        return

    if state.runtime_state == ConversationRuntimeState.WAITING_INPUT:
        await _send_error(
            state,
            code="WAITING_INPUT",
            message="Conversation is waiting for user.input_response.",
            trace_id=trace_id,
        )
        return

    turn_id = state.next_turn_id()
    message_id, message_sequence = _persist_message(
        conversation_id=state.conversation_id,
        role=MessageRole.USER,
        message_type=MessageType.TEXT,
        content=parsed.content,
        metadata_json={
            "turn_id": turn_id,
            "trace_id": trace_id,
            "metadata": parsed.metadata,
        },
    )
    if message_id is not None:
        with session_scope() as session:
            SessionRepository(session).update_last_message(state.session_id, message_id)

    try:
        state.turn_queue.put_nowait(
            TurnCommand(
                turn_id=turn_id,
                trace_id=trace_id,
                kind="user_message",
                content=parsed.content,
            )
        )
    except asyncio.QueueFull:
        await _send_error(
            state,
            code="TURN_QUEUE_FULL",
            message="Conversation queue is full.",
            trace_id=trace_id,
            turn_id=turn_id,
        )
        return

    await _send_envelope(
        state,
        msg_type=WSMessageType.USER_MESSAGE_ACK,
        payload={
            "message_id": message_id,
            "queue_size": state.turn_queue.qsize(),
        },
        trace_id=trace_id,
        turn_id=turn_id,
        message_sequence=message_sequence,
    )


async def _handle_user_input_response(state: ConnectionState, payload: dict[str, Any]) -> None:
    trace_id = _build_turn_trace_id(state.conversation_id)
    try:
        parsed = UserInputResponsePayload.model_validate(payload)
    except ValidationError as exc:
        await _send_error(
            state,
            code="INVALID_INPUT_RESPONSE",
            message=str(exc),
            trace_id=trace_id,
        )
        return

    question_id = parsed.question_id
    if state.pending_question_id is None:
        await _send_error(
            state,
            code="NO_PENDING_INPUT",
            message="No pending input request in this conversation.",
            trace_id=trace_id,
        )
        return
    if state.pending_question_id != question_id:
        await _send_error(
            state,
            code="INVALID_QUESTION_ID",
            message="question_id does not match the pending request.",
            trace_id=trace_id,
        )
        return
    if state.pending_question_deadline is not None and utc_now() > state.pending_question_deadline:
        await _send_error(
            state,
            code="INPUT_TIMEOUT",
            message="Input response arrived after deadline.",
            trace_id=trace_id,
        )
        return
    answer = parsed.answer.strip()
    if state.pending_question_required and not answer:
        await _send_error(
            state,
            code="INPUT_REQUIRED",
            message="answer is required for this question.",
            trace_id=trace_id,
        )
        return
    if _has_answered_question(conversation_id=state.conversation_id, question_id=question_id):
        await _send_error(
            state,
            code="DUPLICATE_INPUT_RESPONSE",
            message="This question already has an input response.",
            trace_id=trace_id,
        )
        return
    if state.runtime_state == ConversationRuntimeState.INTERRUPTED:
        await _send_error(
            state,
            code="CONVERSATION_INTERRUPTED",
            message="Conversation is interrupted; send a new user.message first.",
            trace_id=trace_id,
        )
        return

    turn_id = state.next_turn_id()
    message_id, message_sequence = _persist_message(
        conversation_id=state.conversation_id,
        role=MessageRole.USER,
        message_type=MessageType.INPUT_RESPONSE,
        content=answer,
        metadata_json={
            "turn_id": turn_id,
            "trace_id": trace_id,
            "question_id": question_id,
            "resume_task": parsed.resume_task,
        },
    )
    if message_id is not None:
        with session_scope() as session:
            SessionRepository(session).update_last_message(state.session_id, message_id)

    _close_input_inbox(
        state=state,
        question_id=question_id,
        answer=answer,
        trace_id=trace_id,
    )

    if parsed.resume_task:
        _maybe_resume_blocked_task(
            conversation_id=state.conversation_id,
            task_id=state.task_id,
            trace_id=trace_id,
        )

    try:
        state.turn_queue.put_nowait(
            TurnCommand(
                turn_id=turn_id,
                trace_id=trace_id,
                kind="input_response",
                content=answer,
                question_id=question_id,
                resume_task=parsed.resume_task,
            )
        )
    except asyncio.QueueFull:
        await _send_error(
            state,
            code="TURN_QUEUE_FULL",
            message="Conversation queue is full.",
            trace_id=trace_id,
            turn_id=turn_id,
        )
        return

    await _send_envelope(
        state,
        msg_type=WSMessageType.USER_INPUT_RESPONSE_ACK,
        payload={
            "message_id": message_id,
            "question_id": question_id,
            "queue_size": state.turn_queue.qsize(),
        },
        trace_id=trace_id,
        turn_id=turn_id,
        message_sequence=message_sequence,
    )


async def _handle_user_interrupt(state: ConnectionState) -> None:
    trace_id = _build_turn_trace_id(state.conversation_id)
    interrupted = False
    if state.sdk_client is not None and state.sdk_connected:
        try:
            await state.sdk_client.interrupt()
            interrupted = True
        except Exception as exc:
            await _send_error(
                state,
                code="INTERRUPT_FAILED",
                message=str(exc),
                trace_id=trace_id,
            )

    _persist_interrupt_audit(state, trace_id=trace_id)
    await _emit_runtime_state(
        state,
        next_state=ConversationRuntimeState.INTERRUPTED,
        trace_id=trace_id,
        turn_id=state.active_turn_id,
        reason="user_interrupt",
    )
    await _send_envelope(
        state,
        msg_type=WSMessageType.USER_INTERRUPT_ACK,
        payload={"interrupted": interrupted},
        trace_id=trace_id,
        turn_id=state.active_turn_id,
    )


async def _send_message_replay(state: ConnectionState, *, last_sequence: int) -> None:
    messages = _list_messages_after_sequence(
        conversation_id=state.conversation_id,
        after_sequence=last_sequence,
    )
    for message in messages:
        metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
        turn_id = _safe_int(metadata.get("turn_id"))
        trace_id = _normalize_trace_id(cast(str | None, metadata.get("trace_id")))
        await _send_envelope(
            state,
            msg_type=WSMessageType.MESSAGE_REPLAY,
            payload={
                "message_id": message.id,
                "role": _enum_value(message.role),
                "message_type": _enum_value(message.message_type),
                "content": message.content,
                "metadata_json": metadata,
                "created_at": message.created_at.isoformat().replace("+00:00", "Z"),
            },
            trace_id=trace_id,
            turn_id=turn_id,
            message_sequence=message.sequence_num,
        )


async def _shutdown_state(state: ConnectionState, *, close_socket: bool, reason: str) -> None:
    if state.closed:
        return
    state.closed = True
    state.shutdown_event.set()
    _cancel_task(state.input_timeout_task)
    if state.worker_task is not None:
        state.worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await state.worker_task
    if state.sdk_client is not None and state.sdk_connected:
        with contextlib.suppress(Exception):
            await state.sdk_client.disconnect()
    with session_scope() as session:
        SessionRepository(session).disconnect(state.session_id)
    if close_socket:
        with contextlib.suppress(Exception):
            await state.websocket.close(code=1000, reason=reason)


@router.websocket("/ws/conversations/{conversation_id}")
async def websocket_conversation(
    websocket: WebSocket,
    conversation_id: int,
    protocol: str | None = None,
    client_id: str | None = None,
    last_sequence: int | None = None,
) -> None:
    await websocket.accept()
    settings = get_settings()

    if not settings.chat_protocol_v2_enabled:
        await _send_direct_error(
            websocket,
            conversation_id=conversation_id,
            code="CHAT_PROTOCOL_DISABLED",
            message="Conversation protocol v2 is disabled.",
        )
        await websocket.close(code=4403)
        return
    if protocol != "v2":
        await _send_direct_error(
            websocket,
            conversation_id=conversation_id,
            code="PROTOCOL_VERSION_UNSUPPORTED",
            message="Query parameter protocol=v2 is required.",
        )
        await websocket.close(code=4400)
        return

    actual_client_id = client_id or uuid4().hex

    conversation_project_id: int | None = None
    conversation_agent_id: int | None = None
    conversation_task_id: int | None = None
    agent_model_provider: str | None = None
    agent_model_name: str | None = None
    agent_system_prompt: str | None = None
    project_root_path: str | None = None

    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            await _send_direct_error(
                websocket,
                conversation_id=conversation_id,
                code="CONVERSATION_NOT_FOUND",
                message="Conversation does not exist.",
            )
            await websocket.close(code=4004)
            return
        if conversation.status == ConversationStatus.CLOSED:
            await _send_direct_error(
                websocket,
                conversation_id=conversation_id,
                code="CONVERSATION_CLOSED",
                message="Conversation is closed.",
            )
            await websocket.close(code=4003)
            return

        agent = session.get(Agent, conversation.agent_id)
        project = session.get(Project, conversation.project_id)
        if agent is None:
            await _send_direct_error(
                websocket,
                conversation_id=conversation_id,
                code="AGENT_NOT_FOUND",
                message="Conversation agent does not exist.",
            )
            await websocket.close(code=4004)
            return
        if not _is_supported_provider(agent.model_provider):
            await _send_direct_error(
                websocket,
                conversation_id=conversation_id,
                code="UNSUPPORTED_PROVIDER",
                message=f"Unsupported provider for conversation runtime: {agent.model_provider}.",
            )
            await websocket.close(code=4003)
            return

        conversation_project_id = conversation.project_id
        conversation_agent_id = conversation.agent_id
        conversation_task_id = conversation.task_id
        agent_model_provider = agent.model_provider
        agent_model_name = agent.model_name

        agent_system_prompt = ""
        if project and agent.persona_path:
            try:
                gateway = SecureFileGateway(root_path=project.root_path)
                loader = PersonaLoader(gateway=gateway)
                result = loader.load_by_path(agent.persona_path)
                agent_system_prompt = result.content
            except Exception as e:
                logger.warning(
                    "ws_conversation.persona_load_failed",
                    agent_id=agent.id,
                    error=str(e),
                )

        project_root_path = project.root_path if project is not None else None

        sess_repo = SessionRepository(session)
        existing_session = sess_repo.get_by_client(conversation_id, actual_client_id)
        if existing_session is not None:
            existing_session.status = SessionStatus.CONNECTED
            existing_session.last_heartbeat_at = utc_now()
            existing_session.disconnected_at = None
            session.add(existing_session)
            session.commit()
            session.refresh(existing_session)
            db_session = existing_session
        else:
            db_session = sess_repo.create(
                ConversationSession(
                    conversation_id=conversation_id,
                    client_id=actual_client_id,
                    status=SessionStatus.CONNECTED,
                )
            )

    if db_session.id is None:
        await _send_direct_error(
            websocket,
            conversation_id=conversation_id,
            code="SESSION_CREATE_FAILED",
            message="Conversation session creation failed.",
        )
        await websocket.close(code=4500)
        return

    if (
        conversation_project_id is None
        or conversation_agent_id is None
        or agent_model_provider is None
        or agent_model_name is None
        or agent_system_prompt is None
    ):
        await _send_direct_error(
            websocket,
            conversation_id=conversation_id,
            code="SESSION_INIT_FAILED",
            message="Conversation initialization data is incomplete.",
        )
        await websocket.close(code=4500)
        return

    state = ConnectionState(
        websocket=websocket,
        settings=settings,
        conversation_id=conversation_id,
        client_id=actual_client_id,
        session_id=db_session.id,
        project_id=conversation_project_id,
        agent_id=conversation_agent_id,
        task_id=conversation_task_id,
        model_provider=agent_model_provider,
        model_name=agent_model_name,
        system_prompt=agent_system_prompt,
        workspace_root=Path(project_root_path) if project_root_path else None,
        sdk_session_id=f"conversation-{conversation_id}",
    )
    await manager.connect(state)
    state.worker_task = asyncio.create_task(_turn_worker(state))

    connected_type = (
        WSMessageType.SESSION_RESUMED
        if last_sequence is not None
        else WSMessageType.SESSION_CONNECTED
    )
    await _send_envelope(
        state,
        msg_type=connected_type,
        payload={
            "protocol": "v2",
            "client_id": actual_client_id,
            "session_id": db_session.id,
            "state": state.runtime_state.value,
        },
        trace_id=state.session_trace_id,
    )
    if last_sequence is not None:
        await _send_message_replay(
            state,
            last_sequence=max(last_sequence, 0),
        )

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_TIMEOUT_S,
                )
            except TimeoutError:
                await _send_error(
                    state,
                    code="HEARTBEAT_TIMEOUT",
                    message="WebSocket heartbeat timeout.",
                    trace_id=state.session_trace_id,
                )
                break

            try:
                incoming = WSIncomingMessage.model_validate_json(raw)
            except ValidationError:
                await _send_error(
                    state,
                    code="INVALID_FORMAT",
                    message="Invalid WebSocket message format.",
                    trace_id=state.session_trace_id,
                )
                continue

            if incoming.type == WSMessageType.SESSION_HEARTBEAT:
                await _handle_heartbeat(state)
                continue
            if incoming.type == WSMessageType.USER_MESSAGE:
                await _handle_user_message(state, incoming.payload)
                continue
            if incoming.type == WSMessageType.USER_INPUT_RESPONSE:
                await _handle_user_input_response(state, incoming.payload)
                continue
            if incoming.type == WSMessageType.USER_INTERRUPT:
                await _handle_user_interrupt(state)
                continue

            await _send_error(
                state,
                code="UNKNOWN_MESSAGE_TYPE",
                message=f"Unknown message type: {incoming.type}",
                trace_id=state.session_trace_id,
            )

    except WebSocketDisconnect:
        logger.info("conversation.ws.disconnected", conversation_id=conversation_id)
    except Exception as exc:
        logger.exception(
            "conversation.ws.failed",
            conversation_id=conversation_id,
            error=str(exc),
        )
    finally:
        await manager.remove_if_current(conversation_id, state)
        await _shutdown_state(state, close_socket=False, reason="connection closed")
