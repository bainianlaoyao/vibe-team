from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from app.agents.persona_loader import PersonaLoader
from app.core.logging import get_logger
from app.db.enums import MessageRole, MessageType
from app.db.models import Agent, Conversation, Message, Project, Task
from app.db.repositories import MessageRepository
from app.db.session import session_scope
from app.llm.contracts import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMRole,
    LLMToolCall,
    LLMUsage,
    StreamCallback,
    StreamEvent,
    StreamEventType,
    StreamingLLMClient,
)
from app.llm.errors import LLMProviderError
from app.security import SecureFileGateway

logger = get_logger("bbb.runtime.conversation")


class WebSocketPusher(Protocol):
    """Protocol for pushing messages to WebSocket clients."""

    async def send_chunk(self, content: str) -> bool: ...
    async def send_tool_call(self, tool_call: LLMToolCall) -> bool: ...
    async def send_tool_result(self, tool_id: str, result: str) -> bool: ...
    async def send_thinking(self, content: str) -> bool: ...
    async def send_request_input(self, content: str) -> bool: ...
    async def send_complete(self, usage: LLMUsage | None) -> bool: ...
    async def send_error(self, code: str, message: str) -> bool: ...


@dataclass
class ExecutionContext:
    """Context for a conversation execution."""

    conversation_id: int
    agent_id: int
    session_id: str
    user_message_id: int
    user_content: str
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    trace_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class ExecutionResult:
    """Result of a conversation execution."""

    success: bool
    response: LLMResponse | None = None
    assistant_message_id: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancelled: bool = False


class ConversationExecutor:
    """Executes LLM requests for conversations with streaming support."""

    def __init__(
        self,
        *,
        llm_client: StreamingLLMClient,
        default_max_turns: int = 10,
        default_timeout_seconds: float = 300.0,
    ) -> None:
        self._llm_client = llm_client
        self._default_max_turns = default_max_turns
        self._default_timeout_seconds = default_timeout_seconds

    async def execute(
        self,
        *,
        context: ExecutionContext,
        pusher: WebSocketPusher,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult:
        """Execute an LLM request with streaming output."""
        timeout = timeout_seconds or self._default_timeout_seconds

        # Load conversation and agent context
        with session_scope() as session:
            conversation = session.get(Conversation, context.conversation_id)
            if conversation is None:
                return ExecutionResult(
                    success=False,
                    error_code="CONVERSATION_NOT_FOUND",
                    error_message="Conversation does not exist",
                )

            agent = session.get(Agent, context.agent_id)
            if agent is None:
                return ExecutionResult(
                    success=False,
                    error_code="AGENT_NOT_FOUND",
                    error_message="Agent does not exist",
                )

            # Build message history
            msg_repo = MessageRepository(session)
            history = msg_repo.list_by_conversation(
                context.conversation_id,
                limit=50,
            )
            project = session.get(Project, conversation.project_id)
            task = (
                session.get(Task, conversation.task_id)
                if conversation.task_id is not None
                else None
            )

            messages = self._build_llm_messages(history)

            base_prompt = ""
            if project and agent.persona_path:
                try:
                    gateway = SecureFileGateway(root_path=project.root_path)
                    loader = PersonaLoader(gateway=gateway)
                    result = loader.load_by_path(agent.persona_path)
                    base_prompt = result.content
                except Exception as e:
                    logger.warning(
                        "conversation.persona_load_failed",
                        agent_id=agent.id,
                        error=str(e),
                    )

            system_prompt = self._build_system_prompt(
                base_prompt=base_prompt,
                conversation=conversation,
                task=task,
            )
            cwd = Path(project.root_path) if project is not None else None

        request = LLMRequest(
            provider=agent.model_provider,
            model=agent.model_name,
            messages=messages,
            session_id=context.session_id,
            system_prompt=system_prompt,
            max_turns=self._default_max_turns,
            cwd=cwd,
            trace_id=context.trace_id,
        )

        # Create streaming callback that pushes to WebSocket and accumulates response
        accumulated_text: list[str] = []
        accumulated_tool_calls: list[LLMToolCall] = []

        async def stream_callback(event: StreamEvent) -> None:
            if context.cancel_event.is_set():
                return

            if event.event_type == StreamEventType.TEXT_CHUNK:
                accumulated_text.append(event.content)
                await pusher.send_chunk(event.content)
                await self._persist_message(
                    conversation_id=context.conversation_id,
                    role=MessageRole.ASSISTANT,
                    message_type=MessageType.TEXT,
                    content=event.content,
                    metadata_json={"stream": True},
                )

            elif event.event_type == StreamEventType.TOOL_CALL_START:
                if event.tool_call:
                    accumulated_tool_calls.append(event.tool_call)
                    await pusher.send_tool_call(event.tool_call)
                    await self._persist_message(
                        conversation_id=context.conversation_id,
                        role=MessageRole.ASSISTANT,
                        message_type=MessageType.TOOL_CALL,
                        content=event.tool_call.name,
                        metadata_json={
                            "tool_id": event.tool_call.id,
                            "arguments": event.tool_call.arguments,
                        },
                    )
                    if event.tool_call.name == "request_input":
                        request_content = str(event.tool_call.arguments.get("content", "")).strip()
                        if request_content:
                            await pusher.send_request_input(request_content)
                            await self._persist_message(
                                conversation_id=context.conversation_id,
                                role=MessageRole.ASSISTANT,
                                message_type=MessageType.INPUT_REQUEST,
                                content=request_content,
                                metadata_json={"tool_id": event.tool_call.id},
                            )

            elif event.event_type == StreamEventType.THINKING:
                await pusher.send_thinking(event.content)

            elif event.event_type == StreamEventType.COMPLETE:
                await pusher.send_complete(event.usage)

            elif event.event_type == StreamEventType.ERROR:
                await pusher.send_error("LLM_ERROR", event.error or "Unknown error")

        try:
            # Execute with timeout and cancellation support
            response = await self._execute_with_cancellation(
                request=request,
                callback=stream_callback,
                cancel_event=context.cancel_event,
                timeout=timeout,
            )

            # Persist assistant response
            assistant_message_id = await self._persist_assistant_message(
                conversation_id=context.conversation_id,
                content="".join(accumulated_text),
                tool_calls=accumulated_tool_calls,
                usage=response.usage if response else None,
            )
            for tool_call in accumulated_tool_calls:
                await pusher.send_tool_result(tool_call.id, "ok")
                await self._persist_message(
                    conversation_id=context.conversation_id,
                    role=MessageRole.ASSISTANT,
                    message_type=MessageType.TOOL_RESULT,
                    content="ok",
                    metadata_json={"tool_id": tool_call.id, "tool_name": tool_call.name},
                )

            if response is None:
                return ExecutionResult(
                    success=False,
                    cancelled=True,
                    assistant_message_id=assistant_message_id,
                )

            return ExecutionResult(
                success=True,
                response=response,
                assistant_message_id=assistant_message_id,
            )

        except TimeoutError:
            logger.warning(
                "conversation.execute.timeout",
                conversation_id=context.conversation_id,
                timeout=timeout,
            )
            await pusher.send_error("TIMEOUT", "Request timed out")
            return ExecutionResult(
                success=False,
                error_code="TIMEOUT",
                error_message="Request timed out",
            )

        except LLMProviderError as exc:
            logger.warning(
                "conversation.execute.provider_error",
                conversation_id=context.conversation_id,
                code=exc.code.value,
                message=exc.message,
            )
            await pusher.send_error(exc.code.value, exc.message)
            return ExecutionResult(
                success=False,
                error_code=exc.code.value,
                error_message=exc.message,
            )

        except Exception as exc:
            logger.exception(
                "conversation.execute.unexpected_error",
                conversation_id=context.conversation_id,
            )
            await pusher.send_error("INTERNAL_ERROR", str(exc))
            return ExecutionResult(
                success=False,
                error_code="INTERNAL_ERROR",
                error_message=str(exc),
            )

    async def _execute_with_cancellation(
        self,
        *,
        request: LLMRequest,
        callback: StreamCallback,
        cancel_event: asyncio.Event,
        timeout: float,
    ) -> LLMResponse | None:
        """Execute LLM request with cancellation and timeout support."""
        llm_task = asyncio.create_task(self._llm_client.generate_stream(request, callback))
        cancel_task = asyncio.create_task(cancel_event.wait())

        try:
            done, pending = await asyncio.wait(
                {llm_task, cancel_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if llm_task in done:
                return llm_task.result()

            # Cancelled or timed out
            return None

        except Exception:
            llm_task.cancel()
            cancel_task.cancel()
            raise

    def _build_llm_messages(self, history: list[Message]) -> list[LLMMessage]:
        """Build LLM messages from conversation history."""
        messages: list[LLMMessage] = []
        for msg in history:
            role = self._map_message_role(msg.role)
            if role and msg.content:
                messages.append(LLMMessage(role=role, content=msg.content))
        return messages

    def _map_message_role(self, role: MessageRole | str) -> LLMRole | None:
        """Map database message role to LLM role."""
        role_str = role.value if isinstance(role, MessageRole) else str(role)
        mapping = {
            "user": LLMRole.USER,
            "assistant": LLMRole.ASSISTANT,
            "system": LLMRole.SYSTEM,
            "tool": LLMRole.TOOL,
        }
        return mapping.get(role_str)

    async def _persist_assistant_message(
        self,
        *,
        conversation_id: int,
        content: str,
        tool_calls: list[LLMToolCall],
        usage: LLMUsage | None,
    ) -> int | None:
        """Persist the assistant's response to the database."""
        if not content and not tool_calls:
            return None

        metadata: dict[str, Any] = {}
        if tool_calls:
            metadata["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in tool_calls
            ]
        if usage:
            metadata["usage"] = {
                "token_in": usage.token_in,
                "token_out": usage.token_out,
                "cost_usd": str(usage.cost_usd),
            }

        with session_scope() as session:
            msg_repo = MessageRepository(session)
            sequence_num = msg_repo.get_next_sequence_num(conversation_id)

            message = Message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                message_type=MessageType.TEXT,
                content=content,
                metadata_json=metadata,
                sequence_num=sequence_num,
            )
            message = msg_repo.create(message)
            return message.id

    async def _persist_message(
        self,
        *,
        conversation_id: int,
        role: MessageRole,
        message_type: MessageType,
        content: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> int | None:
        normalized_content = content.strip()
        if not normalized_content:
            return None
        with session_scope() as session:
            repo = MessageRepository(session)
            sequence_num = repo.get_next_sequence_num(conversation_id)
            message = Message(
                conversation_id=conversation_id,
                role=role,
                message_type=message_type,
                content=normalized_content,
                metadata_json=metadata_json or {},
                sequence_num=sequence_num,
            )
            message = repo.create(message)
            return message.id

    def _build_system_prompt(
        self,
        *,
        base_prompt: str,
        conversation: Conversation,
        task: Task | None,
    ) -> str:
        task_context = conversation.context_json.get("task_context")
        if task_context is None and task is None:
            return base_prompt

        parts = [base_prompt.strip()]
        if task is not None:
            parts.append(f"[Task]\nid={task.id}\ntitle={task.title}\nstatus={task.status}")
        if isinstance(task_context, dict):
            parts.append(f"[InheritedContext]\n{task_context}")
        return "\n\n".join(part for part in parts if part)
