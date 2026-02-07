from __future__ import annotations

from app.security import redact_sensitive_text


def test_redact_sensitive_assignments_and_bearer_tokens() -> None:
    raw = (
        "api_key=abc123 access_token:xyz789 refresh_token=qwe123 "
        "secret=topsecret password=hunter2 Authorization: Bearer token-value"
    )
    redacted = redact_sensitive_text(raw)

    assert "abc123" not in redacted
    assert "xyz789" not in redacted
    assert "qwe123" not in redacted
    assert "topsecret" not in redacted
    assert "hunter2" not in redacted
    assert "token-value" not in redacted
    assert "***REDACTED***" in redacted
