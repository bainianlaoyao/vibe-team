from __future__ import annotations

import re

_REPLACEMENT = "***REDACTED***"

# Match common token/key assignment formats while keeping the key name visible.
_ASSIGNMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(api[_-]?key)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(access[_-]?token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(refresh[_-]?token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(secret(?:[_-]?key)?)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\b(password)\s*[:=]\s*([^\s,;]+)"),
)

# Basic bearer token redaction.
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9\-_\.=]+)")


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in _ASSIGNMENT_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}={_REPLACEMENT}", redacted)
    redacted = _BEARER_PATTERN.sub(lambda match: f"{match.group(1)} {_REPLACEMENT}", redacted)
    return redacted
