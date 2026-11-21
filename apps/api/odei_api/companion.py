"""Read-only loopback companion for explicitly selected local workspaces."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import secrets
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator
from starlette.concurrency import run_in_threadpool

from odei_api.services.patch_proposals import (
    MAX_FILE_BYTES,
    MAX_PATCH_FILES,
    MAX_TOTAL_BYTES,
    PatchProposalError,
    build_patch_proposal,
)
from odei_api.services.workspace_handles import WorkspaceHandleRegistry

DEFAULT_PORT = 8765
DEFAULT_PAIRING_TTL_SECONDS = 300
DEFAULT_TOKEN_TTL_SECONDS = 3600


class PairRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class PatchProposalRequest(BaseModel):
    """Bounded text changes for a read-only, live-workspace diff preview."""

    model_config = ConfigDict(extra="forbid")

    changes: dict[str, StrictStr | None] = Field(min_length=1, max_length=MAX_PATCH_FILES)
    expected_base_hashes: dict[str, StrictStr | None]

    @model_validator(mode="after")
    def validate_budgets(self):
        if set(self.expected_base_hashes) != set(self.changes):
            raise ValueError("Every changed path requires exactly one expected base hash")
        total_bytes = 0
        for content in self.changes.values():
            if content is None:
                continue
            if "\x00" in content:
                raise ValueError("Binary content is not supported")
            try:
                encoded = content.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError("New content must be valid UTF-8 text") from exc
            size = len(encoded)
            if size > MAX_FILE_BYTES:
                raise ValueError("A changed file exceeds the 1 MB limit")
            total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValueError("Aggregate replacement content exceeds the 5 MB limit")
        return self


class PairingManager:
    """One-time pairing codes and short-lived read-only bearer sessions."""

    def __init__(
        self,
        *,
        pairing_ttl_seconds: int = DEFAULT_PAIRING_TTL_SECONDS,
        token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        max_failed_attempts: int = 5,
        failure_window_seconds: int = 60,
    ) -> None:
        if pairing_ttl_seconds < 1 or token_ttl_seconds < 1:
            raise ValueError("Pairing and token TTLs must be positive")
        self.pairing_ttl_seconds = pairing_ttl_seconds
        self.token_ttl_seconds = token_ttl_seconds
        self._clock = clock
        self._max_failed_attempts = max_failed_attempts
        self._failure_window_seconds = failure_window_seconds
        self._pairing_code: str | None = None
        self._pairing_expires_at = 0.0
        self._tokens: dict[str, float] = {}
        self._failed_attempts: dict[str, deque[float]] = {}

    def issue_pairing_code(self) -> str:
        self._pairing_code = secrets.token_urlsafe(18)
        self._pairing_expires_at = self._clock() + self.pairing_ttl_seconds
        self._failed_attempts.clear()
        return self._pairing_code

    def exchange(self, code: str, origin: str) -> str | None:
        now = self._clock()
        attempts = self._failed_attempts.setdefault(origin, deque())
        while attempts and now - attempts[0] >= self._failure_window_seconds:
            attempts.popleft()
        if len(attempts) >= self._max_failed_attempts:
            return None

        valid = (
            self._pairing_code is not None
            and now < self._pairing_expires_at
            and code.isascii()
            and 1 <= len(code) <= 128
            and hmac.compare_digest(code, self._pairing_code)
        )
        if not valid:
            attempts.append(now)
            if now >= self._pairing_expires_at:
                self._pairing_code = None
            return None

        self._pairing_code = None
        self._failed_attempts.clear()
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self._tokens[digest] = now + self.token_ttl_seconds
        return token

    def is_valid(self, token: str) -> bool:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expiry = self._tokens.get(digest)
        if expiry is None:
            return False
        if self._clock() >= expiry:
            self._tokens.pop(digest, None)
            return False
        return True

    def revoke(self, token: str) -> bool:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return self._tokens.pop(digest, None) is not None


def _validate_origins(origins: Iterable[str]) -> set[str]:
    allowed: set[str] = set()
    for origin in origins:
        parsed = urlsplit(origin)
        try:
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Companion origins must contain a valid host and port") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or hostname is None
            or port == 0
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or origin != f"{parsed.scheme}://{parsed.netloc}"
        ):
            raise ValueError("Companion origins must be exact scheme-and-host origins")
        # A public web application must use HTTPS. Permit plain HTTP only for
        # loopback development origins, which browsers treat as secure contexts.
        if parsed.scheme == "http" and hostname.casefold() not in {
            "localhost", "127.0.0.1", "::1"
        }:
            raise ValueError("Non-loopback companion origins must use HTTPS")
        allowed.add(origin)
    if not allowed:
        raise ValueError("At least one explicit companion browser origin is required")
    return allowed


def create_companion_app(
    registry: WorkspaceHandleRegistry,
    workspace_ids: str | Iterable[str],
    *,
    allowed_origins: Iterable[str],
    pairing_manager: PairingManager | None = None,
    port: int = DEFAULT_PORT,
) -> FastAPI:
    """Create a loopback-only companion API with exact Origin and Host checks."""
    if not 1 <= port <= 65535:
        raise ValueError("Companion port must be between 1 and 65535")
    origins = _validate_origins(allowed_origins)
    selected_workspace_ids = (
        (workspace_ids,) if isinstance(workspace_ids, str)
        else tuple(dict.fromkeys(workspace_ids))
    )
    if not selected_workspace_ids:
        raise ValueError("At least one selected workspace is required")
    allowed_workspace_ids = frozenset(selected_workspace_ids)
    pairing = pairing_manager or PairingManager()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    app = FastAPI(
        title="ODEI Local Workspace Companion",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def enforce_loopback_browser_boundary(request: Request, call_next):
        host = request.headers.get("host", "").casefold()
        if host not in allowed_hosts:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid local companion host"},
            )

        origin = request.headers.get("origin")
        if request.url.path == "/health" and origin is None:
            response = await call_next(request)
        else:
            if origin not in origins:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Browser origin is not authorized"},
                )

            if request.method == "OPTIONS":
                response = Response(status_code=204)
            else:
                response = await call_next(request)

            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Vary"] = "Origin"

        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def require_bearer(request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="A valid companion session is required")
        if not pairing.is_valid(token):
            raise HTTPException(status_code=401, detail="A valid companion session is required")
        return token

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "odei-local-companion"}

    @app.post("/v1/pair")
    async def pair(payload: PairRequest, request: Request):
        origin = request.headers.get("origin", "")
        token = pairing.exchange(payload.code, origin)
        if token is None:
            raise HTTPException(status_code=401, detail="Pairing code is invalid or expired")
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": pairing.token_ttl_seconds,
            "permissions": ["workspace:read"],
        }

    def require_selected_workspace(workspace_id: str) -> None:
        if workspace_id not in allowed_workspace_ids:
            raise HTTPException(status_code=404, detail="Workspace is unavailable")

    def require_single_workspace() -> str:
        if len(selected_workspace_ids) != 1:
            raise HTTPException(
                status_code=409,
                detail="Use the multi-workspace routes for this companion session",
            )
        return selected_workspace_ids[0]

    @app.get("/v1/workspaces")
    async def list_workspaces(request: Request):
        require_bearer(request)
        return {
            "workspaces": [
                {"workspace_id": item, "name": registry.display_name(item), "access": "read-only"}
                for item in selected_workspace_ids
            ]
        }

    @app.get("/v1/workspaces/{workspace_id}/files")
    async def list_workspace_files(workspace_id: str, request: Request):
        require_bearer(request)
        require_selected_workspace(workspace_id)
        files = await run_in_threadpool(registry.list_files, workspace_id)
        return {"workspace_id": workspace_id, "files": [
            {"path": item.path, "size": item.size} for item in files
        ]}

    @app.get("/v1/workspaces/{workspace_id}/file")
    async def read_workspace_file(
        workspace_id: str,
        request: Request,
        path: str = Query(min_length=1, max_length=1024),
    ):
        require_bearer(request)
        require_selected_workspace(workspace_id)
        try:
            content = await run_in_threadpool(registry.read_text, workspace_id, path)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail="File is unavailable for safe reading") from exc
        return {"workspace_id": workspace_id, "path": path, "content": content}

    @app.post("/v1/workspaces/{workspace_id}/patch-proposals")
    async def preview_workspace_patch(
        workspace_id: str, payload: PatchProposalRequest, request: Request
    ):
        """Build a bounded diff from fresh local files; this route never writes files."""
        require_bearer(request)
        require_selected_workspace(workspace_id)
        try:
            indexed_files = await run_in_threadpool(registry.list_files, workspace_id)
            base_files = {item.path: "" for item in indexed_files}
            paths_by_casefold = {item.path.casefold(): item.path for item in indexed_files}

            for path in payload.changes:
                expected_hash = payload.expected_base_hashes[path]
                if expected_hash is None:
                    # Root-level creates only: nested directory creation is not part of
                    # this read-only preview contract and must not be guessed.
                    if "/" in path:
                        raise HTTPException(
                            status_code=400,
                            detail="New files can only be previewed at the workspace root",
                        )
                    if path.casefold() in paths_by_casefold:
                        raise HTTPException(
                            status_code=409,
                            detail="A file with this path already exists; refresh the workspace",
                        )
                    try:
                        await run_in_threadpool(registry.read_text, workspace_id, path)
                    except FileNotFoundError:
                        pass
                    except (ValueError, OSError) as exc:
                        raise HTTPException(
                            status_code=409,
                            detail="The new path exists or cannot be safely inspected",
                        ) from exc
                    else:
                        raise HTTPException(
                            status_code=409,
                            detail="A file with this path already exists; refresh the workspace",
                        )
                    continue

                actual_path = paths_by_casefold.get(path.casefold())
                if actual_path is None:
                    raise HTTPException(
                        status_code=409,
                        detail="The base file no longer exists; refresh the workspace",
                    )
                try:
                    current_content = await run_in_threadpool(
                        registry.read_text, workspace_id, actual_path
                    )
                except (ValueError, OSError) as exc:
                    raise HTTPException(
                        status_code=409,
                        detail="The base file is no longer safely readable",
                    ) from exc
                base_files[actual_path] = current_content

            proposal = build_patch_proposal(
                base_files, payload.changes, payload.expected_base_hashes
            )
        except PatchProposalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except (ValueError, OSError) as exc:
            raise HTTPException(
                status_code=400, detail="Workspace snapshot is unavailable for safe preview"
            ) from exc

        return {
            "workspace_id": workspace_id,
            "mode": "preview_only",
            "writes_performed": False,
            "files": [
                {
                    "path": item.path,
                    "operation": item.operation,
                    "base_sha256": item.base_sha256,
                    "result_sha256": item.result_sha256,
                    "content": item.content,
                    "unified_diff": item.unified_diff,
                }
                for item in proposal.files
            ],
            "total_content_bytes": proposal.total_content_bytes,
            "total_diff_bytes": proposal.total_diff_bytes,
        }

    @app.get("/v1/workspace")
    async def workspace(request: Request):
        require_bearer(request)
        workspace_id = require_single_workspace()
        return {"workspace_id": workspace_id, "access": "read-only"}

    @app.get("/v1/workspace/files")
    async def list_files(request: Request):
        require_bearer(request)
        workspace_id = require_single_workspace()
        files = await run_in_threadpool(registry.list_files, workspace_id)
        return {"files": [{"path": item.path, "size": item.size} for item in files]}

    @app.get("/v1/workspace/file")
    async def read_file(
        request: Request,
        path: str = Query(min_length=1, max_length=1024),
    ):
        require_bearer(request)
        workspace_id = require_single_workspace()
        try:
            content = await run_in_threadpool(registry.read_text, workspace_id, path)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail="File is unavailable for safe reading") from exc
        return {"workspace_id": workspace_id, "path": path, "content": content}

    @app.post("/v1/session/revoke", status_code=204)
    async def revoke_session(request: Request):
        token = require_bearer(request)
        pairing.revoke(token)
        return Response(status_code=204)

    return app


def select_directory_native() -> str | None:
    """Display an OS folder picker; return the user's explicit selection."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("This Python installation does not include Tk support") from exc

    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root,
            title="Select a project folder for ODEI Studio",
            mustexist=True,
        )
        return selected or None
    finally:
        root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ODEI read-only local workspace companion")
    parser.add_argument("--port", type=int, default=int(os.getenv("ODEI_COMPANION_PORT", DEFAULT_PORT)))
    args = parser.parse_args()

    origins = [
        item.strip()
        for item in os.getenv("ODEI_COMPANION_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    ]
    if not origins:
        print(
            "Set ODEI_COMPANION_ALLOWED_ORIGINS to the exact ODEI Studio web-app origin(s).",
            file=sys.stderr,
        )
        return 2
    if not 1 <= args.port <= 65535:
        print("ODEI_COMPANION_PORT must be between 1 and 65535.", file=sys.stderr)
        return 2
    try:
        _validate_origins(origins)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    selected_paths: list[str] = []
    while True:
        try:
            selected = select_directory_native()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if not selected:
            break
        if selected not in selected_paths:
            selected_paths.append(selected)
        answer = input("Select another project folder? [y/N]: ").strip().casefold()
        if answer not in {"y", "yes"}:
            break
    if not selected_paths:
        print("No project folders selected.")
        return 1

    registry = WorkspaceHandleRegistry()
    workspace_ids: list[str] = []
    pairing = PairingManager()
    code = pairing.issue_pairing_code()
    try:
        for selected_path in selected_paths:
            workspace_ids.append(registry.register_selected_root(selected_path))
        import uvicorn

        app = create_companion_app(
            registry,
            workspace_ids,
            allowed_origins=origins,
            pairing_manager=pairing,
            port=args.port,
        )
        print("ODEI Local Workspace Companion is starting on 127.0.0.1.")
        print(f"{len(workspace_ids)} selected folder(s) are held by OS handles; access is read-only.")
        print("Enter this one-time pairing code in the ODEI Studio web app:")
        print(code)
        print("The code expires in five minutes. Do not share it with anyone.")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
            access_log=False,
        )
    finally:
        registry.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
