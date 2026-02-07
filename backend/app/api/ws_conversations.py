from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.db.enums import ConversationStatus, MessageRole, MessageType, SessionStatus
from app.db.models import Conversation, ConversationSession, Message, utc_now
from app.db.repositories import MessageRepository, SessionRepository
from app.db.session import session_scope

router = APIRouter(tags=["ws_conversations"])

logger = logging.getLogger("bbb.api.ws")

HEARTBEAT_INTERVAL_S = 30
HEARTBEAT_TIMEOUT_S = 90


class WSMessageType(StrEnum):
    """WebSocket message types for bidirectional communication."""

    # Client -> Server
    USER_MESSAGE = "user.message"
    USER_INTERRUPT = "user.interrupt"
    USER_INPUT_RESPONSE = "user.input_response"
    SESSION_HEARTBEAT = "session.heartbeat"

    # Server -> Client
    ASSISTANT_CHUNK = "assistant.chunk"
    ASSISTANT_TOOL_CALL = "assistant.tool_call"
    ASSISTANT_TOOL_RESULT = "assistant.tool_result"
    ASSISTANT_THINKING = "assistant.thinking"
    ASSISTANT_REQUEST_INPUT = "assistant.request_input"
    ASSISTANT_COMPLETE = "assistant.complete"
    SESSION_CONNECTED = "session.connected"
    SESSION_RESUMED = "session.resumed"
    SESSION_ERROR = "session.error"
    SESSION_HEARTBEAT_ACK = "session.heartbeat_ack"


class WSIncomingMessage(BaseModel):
    """Base model for incoming WebSocket messages."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


class WSOutgoingMessage(BaseModel):
    """Base model for outgoing WebSocket messages."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    sequence: int = 0

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


@dataclass
class ConnectionState:
    """Tracks the state of a WebSocket connection."""

    websocket: WebSocket
    conversation_id: int
    client_id: str
    session_id: int | None = None
    last_message_id: int | None = None
    message_sequence: int = 0
    is_processing: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def next_sequence(self) -> int:
        self.message_sequence += 1
        return self.message_sequence


class ConnectionManager:
    """Manages active WebSocket connections for conversations."""

    def __init__(self) -> None:
        self._connections: dict[int, ConnectionState] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        conversation_id: int,
        client_id: str,
        last_message_id: int | None = None,
    ) -> ConnectionState:
        async with self._lock:
            if conversation_id in self._connections:
                existing = self._connections[conversation_id]
                await self._disconnect_state(existing, "replaced by new connection")

            state = ConnectionState(
                websocket=websocket,
                conversation_id=conversation_id,
                client_id=client_id,
                last_message_id=last_message_id,
            )
            self._connections[conversation_id] = state
            return state

    async def disconnect(self, conversation_id: int) -> None:
        async with self._lock:
            if conversation_id in self._connections:
                state = self._connections.pop(conversation_id)
                state.cancel_event.set()

    async def _disconnect_state(self, state: ConnectionState, reason: str) -> None:
        state.cancel_event.set()
        try:
            await state.websocket.close(code=1000, reason=reason)
        except Exception:
            pass

    def get(self, conversation_id: int) -> ConnectionState | None:
        return self._connections.get(conversation_id)

    async def send_message(
        self, conversation_id: int, msg_type: WSMessageType, payload: dict[str, Any]
    ) -> bool:
        state = self._connections.get(conversation_id)
        if state is None:
            return False

        message = WSOutgoingMessage(
            type=msg_type.value,
            payload=payload,
            sequence=state.next_sequence(),
        )
        try:
            await state.websocket.send_json(message.model_dump())
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to conversation {conversation_id}: {e}")
            return False


manager = ConnectionManager()


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    """Send an error message to the client."""
    error_msg = WSOutgoingMessage(
        type=WSMessageType.SESSION_ERROR.value,
        payload={"code": code, "message": message},
    )
    await websocket.send_json(error_msg.model_dump())


async def _handle_heartbeat(state: ConnectionState) -> None:
    """Handle heartbeat from client."""
    ack = WSOutgoingMessage(
        type=WSMessageType.SESSION_HEARTBEAT_ACK.value,
        payload={"server_time": datetime.utcnow().isoformat() + "Z"},
        sequence=state.next_sequence(),
    )
    await state.websocket.send_json(ack.model_dump())

    with session_scope() as session:
        repo = SessionRepository(session)
        if state.session_id:
            repo.update_heartbeat(state.session_id)


async def _handle_user_message(state: ConnectionState, payload: dict[str, Any]) -> None:
    """Handle user message - store and prepare for LLM processing."""
    content = payload.get("content", "")
    if not content:
        await _send_error(state.websocket, "INVALID_MESSAGE", "Message content is required")
        return

    with session_scope() as session:
        msg_repo = MessageRepository(session)
        sequence_num = msg_repo.get_next_sequence_num(state.conversation_id)

        message = Message(
            conversation_id=state.conversation_id,
            role=MessageRole.USER,
            message_type=MessageType.TEXT,
            content=content,
            metadata_json=payload.get("metadata", {}),
            sequence_num=sequence_num,
        )
        message = msg_repo.create(message)
        state.last_message_id = message.id

        if state.session_id and message.id is not None:
            sess_repo = SessionRepository(session)
            sess_repo.update_last_message(state.session_id, message.id)

    ack = WSOutgoingMessage(
        type="user.message.ack",
        payload={"message_id": message.id, "sequence_num": sequence_num},
        sequence=state.next_sequence(),
    )
    await state.websocket.send_json(ack.model_dump())


async def _handle_user_interrupt(state: ConnectionState) -> None:
    """Handle user interrupt request."""
    state.cancel_event.set()
    ack = WSOutgoingMessage(
        type="user.interrupt.ack",
        payload={"interrupted": True},
        sequence=state.next_sequence(),
    )
    await state.websocket.send_json(ack.model_dump())


async def _send_missed_messages(state: ConnectionState) -> None:
    """Send messages that were missed during disconnection."""
    if state.last_message_id is None:
        return

    with session_scope() as session:
        msg_repo = MessageRepository(session)
        missed = msg_repo.list_by_conversation(
            state.conversation_id,
            after_sequence=0,
            limit=100,
        )

        last_seq = 0
        if state.last_message_id:
            for msg in missed:
                if msg.id == state.last_message_id:
                    last_seq = msg.sequence_num
                    break

        messages_to_send = [m for m in missed if m.sequence_num > last_seq]

    for msg in messages_to_send:
        replay_msg = WSOutgoingMessage(
            type="message.replay",
            payload={
                "id": msg.id,
                "role": msg.role,
                "message_type": msg.message_type,
                "content": msg.content,
                "metadata_json": msg.metadata_json,
                "sequence_num": msg.sequence_num,
                "created_at": msg.created_at.isoformat() + "Z",
            },
            sequence=state.next_sequence(),
        )
        await state.websocket.send_json(replay_msg.model_dump())


@router.websocket("/ws/conversations/{conversation_id}")
async def websocket_conversation(
    websocket: WebSocket,
    conversation_id: int,
    client_id: str | None = None,
    last_message_id: int | None = None,
) -> None:
    """WebSocket endpoint for real-time conversation."""
    await websocket.accept()

    actual_client_id = client_id or uuid4().hex

    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            await _send_error(websocket, "CONVERSATION_NOT_FOUND", "Conversation does not exist")
            await websocket.close(code=4004)
            return

        if conversation.status == ConversationStatus.CLOSED:
            await _send_error(websocket, "CONVERSATION_CLOSED", "Conversation is closed")
            await websocket.close(code=4003)
            return

        sess_repo = SessionRepository(session)
        existing_session = sess_repo.get_by_client(conversation_id, actual_client_id)

        if existing_session:
            existing_session.status = SessionStatus.CONNECTED
            existing_session.last_heartbeat_at = utc_now()
            existing_session.disconnected_at = None
            session.add(existing_session)
            session.commit()
            session.refresh(existing_session)
            db_session_id = existing_session.id
        else:
            new_session = ConversationSession(
                conversation_id=conversation_id,
                client_id=actual_client_id,
                status=SessionStatus.CONNECTED,
            )
            new_session = sess_repo.create(new_session)
            db_session_id = new_session.id

    state = await manager.connect(
        websocket=websocket,
        conversation_id=conversation_id,
        client_id=actual_client_id,
        last_message_id=last_message_id,
    )
    state.session_id = db_session_id

    is_resume = last_message_id is not None
    msg_type = WSMessageType.SESSION_RESUMED if is_resume else WSMessageType.SESSION_CONNECTED
    connect_msg = WSOutgoingMessage(
        type=msg_type.value,
        payload={
            "conversation_id": conversation_id,
            "client_id": actual_client_id,
            "session_id": db_session_id,
        },
        sequence=state.next_sequence(),
    )
    await websocket.send_json(connect_msg.model_dump())

    if is_resume:
        await _send_missed_messages(state)

    try:
        while True:
            try:
                raw_data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_TIMEOUT_S,
                )
            except TimeoutError:
                logger.info(f"Connection timeout for conversation {conversation_id}")
                break

            try:
                data = json.loads(raw_data)
                incoming = WSIncomingMessage(**data)
            except (json.JSONDecodeError, ValidationError) as e:
                await _send_error(websocket, "INVALID_FORMAT", str(e))
                continue

            if incoming.type == WSMessageType.SESSION_HEARTBEAT:
                await _handle_heartbeat(state)
            elif incoming.type == WSMessageType.USER_MESSAGE:
                await _handle_user_message(state, incoming.payload)
            elif incoming.type == WSMessageType.USER_INTERRUPT:
                await _handle_user_interrupt(state)
            elif incoming.type == WSMessageType.USER_INPUT_RESPONSE:
                with session_scope() as session:
                    msg_repo = MessageRepository(session)
                    sequence_num = msg_repo.get_next_sequence_num(state.conversation_id)
                    message = Message(
                        conversation_id=state.conversation_id,
                        role=MessageRole.USER,
                        message_type=MessageType.INPUT_RESPONSE,
                        content=incoming.payload.get("content", ""),
                        metadata_json=incoming.payload.get("metadata", {}),
                        sequence_num=sequence_num,
                    )
                    msg_repo.create(message)
            else:
                await _send_error(
                    websocket, "UNKNOWN_MESSAGE_TYPE", f"Unknown message type: {incoming.type}"
                )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for conversation {conversation_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for conversation {conversation_id}: {e}")
    finally:
        await manager.disconnect(conversation_id)

        with session_scope() as session:
            sess_repo = SessionRepository(session)
            if state.session_id:
                sess_repo.disconnect(state.session_id)
