from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.models import Event

SECURITY_AUDIT_ALLOWED_EVENT_TYPE = "security.audit.allowed"
SECURITY_AUDIT_DENIED_EVENT_TYPE = "security.audit.denied"


class SecurityAuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class SecurityAuditPayload(BaseModel):
    actor: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=120)
    resource: str = Field(min_length=1, max_length=240)
    outcome: SecurityAuditOutcome
    reason: str | None = Field(default=None, max_length=512)
    ip: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


def append_security_audit_event(
    session: Session,
    *,
    project_id: int,
    actor: str,
    action: str,
    resource: str,
    outcome: SecurityAuditOutcome,
    reason: str | None = None,
    ip: str | None = None,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    event_type = (
        SECURITY_AUDIT_ALLOWED_EVENT_TYPE
        if outcome == SecurityAuditOutcome.ALLOWED
        else SECURITY_AUDIT_DENIED_EVENT_TYPE
    )
    payload = SecurityAuditPayload(
        actor=actor,
        action=action,
        resource=resource,
        outcome=outcome,
        reason=reason,
        ip=ip,
        metadata=metadata or {},
    ).model_dump(mode="json")
    session.add(
        Event(
            project_id=project_id,
            event_type=event_type,
            payload_json=payload,
            trace_id=trace_id,
        )
    )
