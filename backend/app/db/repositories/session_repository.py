from __future__ import annotations

from sqlalchemy import update
from sqlmodel import Session, select

from app.db.enums import SessionStatus
from app.db.models import ConversationSession, utc_now


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, conv_session: ConversationSession) -> ConversationSession:
        self.session.add(conv_session)
        self.session.commit()
        self.session.refresh(conv_session)
        return conv_session

    def get(self, session_id: int) -> ConversationSession | None:
        return self.session.get(ConversationSession, session_id)

    def get_by_client(self, conversation_id: int, client_id: str) -> ConversationSession | None:
        statement = select(ConversationSession).where(
            ConversationSession.conversation_id == conversation_id,
            ConversationSession.client_id == client_id,
        )
        return self.session.exec(statement).first()

    def list_active_by_conversation(self, conversation_id: int) -> list[ConversationSession]:
        statement = select(ConversationSession).where(
            ConversationSession.conversation_id == conversation_id,
            ConversationSession.status == SessionStatus.CONNECTED.value,
        )
        return list(self.session.exec(statement).all())

    def update_heartbeat(self, session_id: int) -> ConversationSession | None:
        statement = (
            update(ConversationSession)
            .where(ConversationSession.id == session_id)  # type: ignore[arg-type]
            .values(last_heartbeat_at=utc_now())
        )
        self.session.exec(statement)
        self.session.commit()
        return self.session.get(ConversationSession, session_id)

    def update_last_message(self, session_id: int, message_id: int) -> ConversationSession | None:
        statement = (
            update(ConversationSession)
            .where(ConversationSession.id == session_id)  # type: ignore[arg-type]
            .values(
                last_message_id=message_id,
                last_heartbeat_at=utc_now(),
            )
        )
        self.session.exec(statement)
        self.session.commit()
        return self.session.get(ConversationSession, session_id)

    def disconnect(self, session_id: int) -> ConversationSession | None:
        now = utc_now()
        statement = (
            update(ConversationSession)
            .where(ConversationSession.id == session_id)  # type: ignore[arg-type]
            .values(
                status=SessionStatus.DISCONNECTED.value,
                disconnected_at=now,
            )
        )
        self.session.exec(statement)
        self.session.commit()
        return self.session.get(ConversationSession, session_id)

    def disconnect_stale_sessions(self, timeout_seconds: int = 90) -> int:
        """Disconnect sessions that haven't sent a heartbeat in timeout_seconds."""
        import datetime

        cutoff = utc_now() - datetime.timedelta(seconds=timeout_seconds)
        statement = (
            update(ConversationSession)
            .where(ConversationSession.status == SessionStatus.CONNECTED.value)  # type: ignore[arg-type]
            .where(ConversationSession.last_heartbeat_at < cutoff)  # type: ignore[arg-type]
            .values(
                status=SessionStatus.DISCONNECTED.value,
                disconnected_at=utc_now(),
            )
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount
