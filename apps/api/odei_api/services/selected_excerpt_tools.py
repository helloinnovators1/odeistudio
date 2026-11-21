"""Read-only tools scoped strictly to user-attached workspace excerpts."""
from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from odei_api.services.secret_redaction import redact_secrets

MAX_EXCERPTS = 5
MAX_PATH_CHARS = 1_024
MAX_EXCERPT_CHARS = 8_000
MAX_SEARCH_QUERY_CHARS = 200
MAX_MATCHES = 10


class SelectedExcerptToolError(ValueError):
    """Raised when a requested attached-excerpt operation is not permitted."""


class SelectedExcerptTools:
    """Expose list/read/search only over excerpts explicitly attached by the user."""

    def __init__(self, workspace_files: list[dict[str, str]]) -> None:
        if not isinstance(workspace_files, list) or not 1 <= len(workspace_files) <= MAX_EXCERPTS:
            raise SelectedExcerptToolError("Attach between one and five file excerpts before enabling inspection")
        self._files: dict[str, dict[str, str]] = {}
        seen: set[str] = set()
        total = 0
        for item in workspace_files:
            if not isinstance(item, dict) or set(item) != {"path", "content"}:
                raise SelectedExcerptToolError("Each attached excerpt must contain only path and content")
            path, content = item["path"], item["content"]
            if (
                not isinstance(path, str) or not path or len(path) > MAX_PATH_CHARS
                or "\\" in path or "\x00" in path
                or not isinstance(content, str) or len(content) > MAX_EXCERPT_CHARS
            ):
                raise SelectedExcerptToolError("An attached file path or excerpt is invalid")
            candidate = PurePosixPath(path)
            if (
                candidate.is_absolute() or not candidate.parts
                or any(part in {"", ".", ".."} for part in candidate.parts)
                or ":" in candidate.parts[0]
            ):
                raise SelectedExcerptToolError("Attached file paths must be safe workspace-relative paths")
            canonical = candidate.as_posix()
            folded = canonical.casefold()
            if folded in seen:
                raise SelectedExcerptToolError("Duplicate attached file paths are not allowed")
            seen.add(folded)
            total += len(canonical) + len(content)
            if total > 40_000:
                raise SelectedExcerptToolError("Attached excerpts exceed the combined context budget")
            self._files[canonical] = {
                "path": canonical,
                "content": redact_secrets(content),
            }

    @staticmethod
    def schemas() -> list[dict[str, Any]]:
        """Strict Responses API schemas; no workspace ID or arbitrary path root."""
        return [
            {
                "type": "function",
                "name": "list_attached_excerpts",
                "description": "List only files explicitly attached by the user to this message. Read-only.",
                "strict": True,
                "parameters": {
                    "type": "object", "properties": {}, "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "read_attached_excerpt",
                "description": "Read the bounded excerpt of one file explicitly attached by the user. Read-only.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"], "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "search_attached_excerpts",
                "description": "Search only user-attached excerpts for a literal case-insensitive phrase. Read-only.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"], "additionalProperties": False,
                },
            },
        ]

    @staticmethod
    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if not isinstance(arguments, dict):
            raise SelectedExcerptToolError("Tool arguments must be a JSON object")
        if name == "list_attached_excerpts":
            if arguments:
                raise SelectedExcerptToolError("list_attached_excerpts takes no arguments")
            return self._encode({
                "files": [
                    {"path": path, "characters": len(item["content"])}
                    for path, item in self._files.items()
                ],
                "scope": "user_attached_excerpts_only",
            })
        if name == "read_attached_excerpt":
            if set(arguments) != {"path"} or not isinstance(arguments["path"], str):
                raise SelectedExcerptToolError("read_attached_excerpt requires only a string path")
            item = self._files.get(arguments["path"])
            if item is None:
                raise SelectedExcerptToolError("The requested path was not attached by the user")
            return self._encode(item)
        if name == "search_attached_excerpts":
            if set(arguments) != {"query"} or not isinstance(arguments["query"], str):
                raise SelectedExcerptToolError("search_attached_excerpts requires only a string query")
            query = arguments["query"].strip()
            if not query or len(query) > MAX_SEARCH_QUERY_CHARS:
                raise SelectedExcerptToolError(
                    f"query must contain 1 to {MAX_SEARCH_QUERY_CHARS} characters"
                )
            matches: list[dict[str, Any]] = []
            for path, item in self._files.items():
                for line_number, line in enumerate(item["content"].splitlines(), start=1):
                    if query.casefold() in line.casefold():
                        matches.append({
                            "path": path,
                            "line": line_number,
                            "text": redact_secrets(line[:400]),
                        })
                        if len(matches) >= MAX_MATCHES:
                            return self._encode({"matches": matches, "truncated": True})
            return self._encode({"matches": matches, "truncated": False})
        raise SelectedExcerptToolError("Tool is not registered or permitted")
