"""Policy-controlled, read-only tools for NEXUS workspace context.

These tools never write files, execute commands, access arbitrary roots, or
perform deployment/network side effects. The workspace ID is injected by the
trusted caller and is never accepted from model-generated arguments.
"""
from __future__ import annotations

import json
from typing import Any

from odei_api.services.project_files import ProjectFile
from odei_api.services.secret_redaction import redact_secrets
from odei_api.services.workspace_handles import WorkspaceHandleRegistry

MAX_LIST_FILES = 40
MAX_SEARCH_FILES = 100
MAX_READ_BYTES = 128_000
MAX_READ_CHARS = 8_000
MAX_SEARCH_QUERY_CHARS = 200
MAX_SEARCH_RESULTS = 10


class ToolExecutionError(ValueError):
    """Raised when a tool call is invalid or not permitted."""


class ReadOnlyWorkspaceTools:
    """Expose bounded list/read/search operations for one approved workspace."""

    def __init__(self, registry: WorkspaceHandleRegistry, workspace_id: str) -> None:
        if not workspace_id.strip():
            raise ValueError("workspace_id must not be empty")
        self._registry = registry
        self._workspace_id = workspace_id

    @staticmethod
    def schemas() -> list[dict[str, Any]]:
        """Return strict Responses API function-tool schemas."""
        return [
            {
                "type": "function",
                "name": "list_project_files",
                "description": "List up to 40 eligible files in the already-approved workspace. Read-only.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "read_project_file",
                "description": "Read one bounded UTF-8 text file by workspace-relative path. Read-only.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "search_project_files",
                "description": "Search eligible UTF-8 text files for a literal case-insensitive phrase. Read-only.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Validate and execute one approved read-only tool call."""
        if not isinstance(arguments, dict):
            raise ToolExecutionError("Tool arguments must be a JSON object")
        if name == "list_project_files":
            if arguments:
                raise ToolExecutionError("list_project_files takes no arguments")
            return self._list_files()
        if name == "read_project_file":
            if set(arguments) != {"path"} or not isinstance(arguments["path"], str):
                raise ToolExecutionError("read_project_file requires only a string path")
            return self._read_file(arguments["path"])
        if name == "search_project_files":
            if set(arguments) != {"query"} or not isinstance(arguments["query"], str):
                raise ToolExecutionError("search_project_files requires only a string query")
            return self._search(arguments["query"])
        raise ToolExecutionError("Tool is not registered or permitted")

    def _encode(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _list_files(self) -> str:
        files = self._registry.list_files(
            self._workspace_id,
            max_files=MAX_LIST_FILES + 1,
            max_total_bytes=25_000_000,
        )
        visible = files[:MAX_LIST_FILES]
        return self._encode({
            "files": [{"path": item.path, "size": item.size} for item in visible],
            "truncated": len(files) > MAX_LIST_FILES,
        })

    def _read_file(self, path: str) -> str:
        if not path or len(path) > 1024:
            raise ToolExecutionError("path must contain 1 to 1024 characters")
        content = redact_secrets(self._registry.read_text(
            self._workspace_id, path, max_bytes=MAX_READ_BYTES
        ))
        truncated = len(content) > MAX_READ_CHARS
        return self._encode({
            "path": path,
            "content": content[:MAX_READ_CHARS],
            "truncated": truncated,
        })

    def _search(self, query: str) -> str:
        clean_query = query.strip()
        if not clean_query or len(clean_query) > MAX_SEARCH_QUERY_CHARS:
            raise ToolExecutionError(
                f"query must contain 1 to {MAX_SEARCH_QUERY_CHARS} characters"
            )
        files: list[ProjectFile] = self._registry.list_files(
            self._workspace_id,
            max_files=MAX_SEARCH_FILES,
            max_total_bytes=25_000_000,
        )
        matches: list[dict[str, str | int]] = []
        total_read = 0
        for item in files:
            if item.size > MAX_READ_BYTES:
                continue
            try:
                content = self._registry.read_text(
                    self._workspace_id, item.path, max_bytes=MAX_READ_BYTES
                )
            except (OSError, ValueError):
                continue
            total_read += item.size
            if total_read > 5_000_000:
                break
            for line_number, line in enumerate(content.splitlines(), start=1):
                if clean_query.casefold() in line.casefold():
                    matches.append({
                        "path": item.path,
                        "line": line_number,
                        "text": redact_secrets(line[:400]),
                    })
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        return self._encode({"matches": matches, "truncated": True})
        return self._encode({"matches": matches, "truncated": len(files) >= MAX_SEARCH_FILES})
