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
_SECRET_NAME = r"""["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?access[_-]?key|aws[_-]?secret[_-]?access[_-]?key|db[_-]?password|password|passwd|secret|credential)\b["']?\s*[:=]\s*"""
_QUOTED_SECRET_ASSIGNMENT = re.compile(
    r"(?im)(" + _SECRET_NAME + r")([\"'])(.{8,}?)\2"
)
_UNQUOTED_SECRET_ASSIGNMENT = re.compile(
    r"(?im)(" + _SECRET_NAME + r")([A-Za-z0-9_./+=:-]{12,})(?=\s|[,;}#]|$)"
)

def redact_secrets(text: str) -> str:
    """Redact common credential formats; this is defense-in-depth, not DLP."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    result = _QUOTED_SECRET_ASSIGNMENT.sub(
        lambda match: match.group(1) + match.group(2) + "[REDACTED]" + match.group(2),
        result,
    )
    return _UNQUOTED_SECRET_ASSIGNMENT.sub(
        lambda match: match.group(1) + "[REDACTED]",
        result,
    )



class StreamingSecretRedactor:
    """Redact known credential formats without releasing incomplete secret tokens."""

    _PRIVATE_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
    _PRIVATE_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY-----")
    _ASSIGNMENT = re.compile(
        r"(?i)[\"']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"client[_-]?secret|secret[_-]?access[_-]?key|aws[_-]?secret[_-]?access[_-]?key|"
        r"db[_-]?password|password|passwd|secret|credential)\b[\"']?\s*[:=]\s*"
    )
    _BEARER = re.compile(r"(?i)\bBearer\s+")
    _MONGO = re.compile(r"(?i)mongodb(?:\+srv)?://")
    _TOKENS = (
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}"),
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
        re.compile(r"\bAKIA[0-9A-Z]{16}"),
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    )
    _TOKEN_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-+/=")
    _LOOKBEHIND = 160

    def __init__(self) -> None:
        self._buffer = ""

    @staticmethod
    def _token_end(value: str, start: int, allowed: frozenset[str]) -> int:
        index = start
        while index < len(value) and value[index] in allowed:
            index += 1
        return index

    def _earliest_start(self):
        matches = []
        patterns = [self._PRIVATE_BEGIN, self._ASSIGNMENT, self._BEARER, self._MONGO, *self._TOKENS]
        for pattern in patterns:
            match = pattern.search(self._buffer)
            if match:
                matches.append(match)
        return min(matches, key=lambda match: match.start()) if matches else None

    def _drain(self, *, final: bool) -> str:
        output: list[str] = []
        while self._buffer:
            match = self._earliest_start()
            if match is None:
                if final:
                    output.append(redact_secrets(self._buffer))
                    self._buffer = ""
                elif len(self._buffer) > self._LOOKBEHIND:
                    safe = len(self._buffer) - self._LOOKBEHIND
                    output.append(self._buffer[:safe])
                    self._buffer = self._buffer[safe:]
                break

            if match.start() > 0:
                output.append(self._buffer[:match.start()])
                self._buffer = self._buffer[match.start():]
                match = self._earliest_start()
                if match is None:
                    continue

            marker = match.group(0)
            start = match.start()
            end = match.end()
            secret_end: int | None = None

            if marker.startswith("-----BEGIN "):
                ending = self._PRIVATE_END.search(self._buffer, end)
                if ending:
                    secret_end = ending.end()
            elif marker.casefold().startswith("mongodb"):
                authority_end = min(
                    (position for position in (self._buffer.find("/", end), self._buffer.find("?", end),
                     self._buffer.find(" ", end), self._buffer.find("\t", end), self._buffer.find("\r", end),
                     self._buffer.find("\n", end)) if position >= 0),
                    default=-1,
                )
                authority_limit = authority_end if authority_end >= 0 else len(self._buffer)
                at = self._buffer.find("@", end, authority_limit)
                if at >= 0 and ":" in self._buffer[end:at]:
                    secret_end = at + 1
                elif authority_end >= 0:
                    output.append(self._buffer[:authority_end])
                    self._buffer = self._buffer[authority_end:]
                    continue
                elif final:
                    output.append(self._buffer)
                    self._buffer = ""
                    break
            elif marker.casefold().startswith("bearer"):
                token_end = self._token_end(self._buffer, end, self._TOKEN_CHARS)
                if token_end < len(self._buffer):
                    secret_end = token_end
            elif self._ASSIGNMENT.match(self._buffer):
                value_start = end
                if value_start < len(self._buffer) and self._buffer[value_start] in {"'", '"'}:
                    quote = self._buffer[value_start]
                    quote_end = self._buffer.find(quote, value_start + 1)
                    if quote_end >= 0:
                        secret_end = quote_end + 1
                else:
                    token_end = self._token_end(self._buffer, value_start, self._TOKEN_CHARS)
                    if token_end < len(self._buffer):
                        secret_end = token_end
            else:
                token_end = self._token_end(self._buffer, end, self._TOKEN_CHARS)
                if token_end < len(self._buffer):
                    secret_end = token_end

            if secret_end is None:
                if not final:
                    break
                secret_end = len(self._buffer)

            candidate = self._buffer[start:secret_end]
            redacted = redact_secrets(candidate)
            if redacted == candidate:
                # Do not leak a detected credential prefix if a provider ends
                # unexpectedly before a normal delimiter is received.
                redacted = "[REDACTED]"
            output.append(redacted)
            self._buffer = self._buffer[secret_end:]

        return "".join(output)

    def feed(self, chunk: str) -> str:
        if not isinstance(chunk, str):
            raise TypeError("stream chunk must be a string")
        self._buffer += chunk
        return self._drain(final=False)

    def finish(self) -> str:
        return self._drain(final=True)
