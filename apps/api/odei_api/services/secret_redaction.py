"""Best-effort secret redaction before repository text reaches a model."""
from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    (
        re.compile(
            r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
            r"github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|"
            r"xox[baprs]-[A-Za-z0-9-]{10,})\b"
        ),
        "[REDACTED]",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED JWT]",
    ),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(r"(?i)(mongodb(?:\+srv)?://[^:/@\s]+:)[^@\s/]+(@)"),
        r"\1[REDACTED]\2",
    ),
)
_QUOTED_SECRET_ASSIGNMENT = re.compile(
    r"""(?im)(["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret)\b["']?\s*[:=]\s*)(["'])(.{8,}?)\2"""
)


def redact_secrets(text: str) -> str:
    """Redact common credential formats; this is defense-in-depth, not DLP."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return _QUOTED_SECRET_ASSIGNMENT.sub(
        lambda match: match.group(1) + match.group(2) + "[REDACTED]" + match.group(2),
        result,
    )
