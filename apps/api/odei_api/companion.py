"""Loopback companion for selected workspaces; writes require signed owner approval."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator
from starlette.concurrency import run_in_threadpool

from odei_api.services.patch_approval import (
    CapabilityReplayCache,
    PatchApprovalError,
    PatchApprovalNotConfigured,
    PatchCapabilityReplay,
    verify_patch_apply_capability,
)
from odei_api.services.patch_proposals import (
    MAX_FILE_BYTES,
    MAX_PATCH_FILES,
    MAX_TOTAL_BYTES,
    PatchProposalError,
    build_patch_proposal,
    validate_patch_path,
)
from odei_api.services.workspace_handles import WorkspaceHandleError, WorkspaceHandleRegistry, WorkspaceNotFound

DEFAULT_PORT = 8765
DEFAULT_PAIRING_TTL_SECONDS = 300
DEFAULT_TOKEN_TTL_SECONDS = 3600


class PairRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class PatchProposalRequest(BaseModel):
    """Bounded text changes for a read-only, live-workspace diff preview."""

    model_config = ConfigDict(extra="forbid")

    changes: dict[StrictStr, StrictStr | None] = Field(min_length=1, max_length=MAX_PATCH_FILES)
    expected_base_hashes: dict[StrictStr, StrictStr | None] = Field(max_length=MAX_PATCH_FILES)

    @model_validator(mode="after")
    def validate_budgets(self):
        if not self.changes or len(self.changes) > MAX_PATCH_FILES:
            raise ValueError("A proposal must contain between 1 and 20 file changes")
        if set(self.expected_base_hashes) != set(self.changes):
            raise ValueError("Every changed path requires exactly one expected base hash")
        for path, expected_hash in self.expected_base_hashes.items():
            validate_patch_path(path)
            if expected_hash is not None and (
                len(expected_hash) != 64
                or any(character not in "0123456789abcdef" for character in expected_hash)
            ):
                raise ValueError("Existing files require a valid SHA-256 base hash")
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


class ApplyPatchFile(BaseModel):
    """Exact one-file operation authorized by a signed patch capability."""

    model_config = ConfigDict(extra="forbid")

    path: StrictStr = Field(min_length=1, max_length=1024)
    operation: StrictStr = Field(pattern="^(create|update|delete)$")
    base_sha256: StrictStr | None = None
    result_sha256: StrictStr | None = None
    content: StrictStr | None = Field(default=None, max_length=1_000_000)


class ApplyPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: StrictStr = Field(min_length=1, max_length=128)
    project_id: StrictStr = Field(min_length=1, max_length=128)
    proposal_id: StrictStr = Field(min_length=1, max_length=128)
    proposal_version: int = Field(ge=0)
    companion_challenge: StrictStr = Field(min_length=32, max_length=128)
    capability: StrictStr = Field(min_length=1, max_length=8192)
    files: list[ApplyPatchFile] = Field(min_length=1, max_length=1)


class ApplyChallengeManager:
    """Short-lived, session-bound challenges invalidated on companion restart."""

    def __init__(self, *, ttl_seconds: int = 60, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._challenges: dict[str, tuple[float, str, str]] = {}

    def issue(self, workspace_id: str, session_token: str) -> str:
        challenge = secrets.token_urlsafe(32)
        digest = hashlib.sha256(challenge.encode("utf-8")).hexdigest()
        session_digest = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        with self._lock:
            now = self._clock()
            for key, value in list(self._challenges.items()):
                if value[0] <= now:
                    self._challenges.pop(key, None)
            if len(self._challenges) >= 128:
                oldest = next(iter(self._challenges))
                self._challenges.pop(oldest, None)
            self._challenges[digest] = (
                now + self.ttl_seconds, workspace_id, session_digest,
            )
        return challenge

    def consume(self, challenge: str, workspace_id: str, session_token: str) -> bool:
        if not isinstance(challenge, str) or not 32 <= len(challenge) <= 128:
            return False
        digest = hashlib.sha256(challenge.encode("utf-8")).hexdigest()
        session_digest = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        with self._lock:
            record = self._challenges.get(digest)
            if record is None:
                return False
            expires_at, expected_workspace, expected_session = record
            if self._clock() >= expires_at:
                self._challenges.pop(digest, None)
                return False
            if (
                not hmac.compare_digest(expected_workspace, workspace_id)
                or not hmac.compare_digest(expected_session, session_digest)
            ):
                return False
            self._challenges.pop(digest, None)
            return True


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
    patch_approval_issuer: str | None = None,
    patch_approval_public_keys: Mapping[str, str] | None = None,
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
    if (patch_approval_issuer is None) != (patch_approval_public_keys is None):
        raise ValueError("Patch approval issuer and pinned public keys must be configured together")
    if patch_approval_issuer is not None:
        issuer_parts = urlsplit(patch_approval_issuer)
        if (
            issuer_parts.scheme != "https" or not issuer_parts.netloc
            or issuer_parts.username or issuer_parts.password
            or issuer_parts.query or issuer_parts.fragment
            or issuer_parts.path not in {"", "/"}
            or not patch_approval_public_keys
            or len(patch_approval_public_keys) > 16
            or any(
                not isinstance(key_id, str) or not key_id or len(key_id) > 64
                or not isinstance(value, str) or not value or len(value) > 256
                for key_id, value in patch_approval_public_keys.items()
            )
        ):
            raise ValueError("Patch approval issuer or pinned public keys are invalid")
    apply_challenges = ApplyChallengeManager()
    capability_replays = CapabilityReplayCache()
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
            "permissions": ["workspace:read"] + (["patch:apply"] if patch_approval_issuer else []),
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
                {"workspace_id": item, "name": registry.display_name(item), "access": "approval-gated" if patch_approval_issuer and registry.can_apply_patch(item) else "read-only"}
                for item in selected_workspace_ids
            ]
        }

    @app.post("/v1/workspaces/{workspace_id}/apply-challenge")
    async def issue_apply_challenge(workspace_id: str, request: Request):
        session_token = require_bearer(request)
        require_selected_workspace(workspace_id)
        if patch_approval_issuer is None or patch_approval_public_keys is None:
            raise HTTPException(status_code=503, detail="Signed patch application is not configured")
        challenge = apply_challenges.issue(workspace_id, session_token)
        return {
            "workspace_id": workspace_id,
            "challenge": challenge,
            "expires_in": apply_challenges.ttl_seconds,
        }

    @app.post("/v1/workspaces/{workspace_id}/apply-patch")
    async def apply_approved_workspace_patch(
        workspace_id: str, payload: ApplyPatchRequest, request: Request
    ):
        session_token = require_bearer(request)
        require_selected_workspace(workspace_id)
        if patch_approval_issuer is None or patch_approval_public_keys is None:
            raise HTTPException(status_code=503, detail="Signed patch application is not configured")
        if not apply_challenges.consume(
            payload.companion_challenge, workspace_id, session_token
        ):
            raise HTTPException(status_code=401, detail="Companion apply challenge is invalid, expired or already used")
        file_item = payload.files[0].model_dump()
        try:
            verify_patch_apply_capability(
                payload.capability,
                public_keys=patch_approval_public_keys,
                issuer=patch_approval_issuer,
                organization_id=payload.organization_id,
                project_id=payload.project_id,
                workspace_id=workspace_id,
                proposal_id=payload.proposal_id,
                proposal_version=payload.proposal_version,
                files=[file_item],
                challenge=payload.companion_challenge,
                replay_cache=capability_replays,
            )
        except PatchApprovalNotConfigured as exc:
            raise HTTPException(status_code=503, detail="Patch approval verification is not configured") from exc
        except PatchCapabilityReplay as exc:
            raise HTTPException(status_code=409, detail="Patch approval capability has expired or was already used") from exc
        except PatchApprovalError as exc:
            raise HTTPException(status_code=403, detail="Patch approval capability is invalid") from exc
        try:
            applied = await run_in_threadpool(
                registry.apply_patch, workspace_id, file_item
            )
        except WorkspaceNotFound as exc:
            raise HTTPException(status_code=404, detail="The selected workspace is no longer available") from exc
        except WorkspaceHandleError as exc:
            raise HTTPException(status_code=409, detail="The selected workspace is not enabled for patch application") from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=409, detail="The approved patch could not be applied to the current workspace state") from exc
        return {
            "workspace_id": workspace_id,
            "proposal_id": payload.proposal_id,
            "proposal_version": payload.proposal_version,
            "applied": True,
            "files": [applied],
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

    approval_issuer = os.getenv("ODEI_PATCH_APPROVAL_ISSUER", "").strip() or None
    public_keys_value = os.getenv("ODEI_PATCH_APPROVAL_PUBLIC_KEYS", "").strip()
    approval_public_keys = None
    if bool(approval_issuer) != bool(public_keys_value):
        print(
            "Set both ODEI_PATCH_APPROVAL_ISSUER and ODEI_PATCH_APPROVAL_PUBLIC_KEYS, or leave both unset.",
            file=sys.stderr,
        )
        return 2
    if public_keys_value:
        try:
            parsed_keys = json.loads(public_keys_value)
            if (
                not isinstance(parsed_keys, dict)
                or not parsed_keys
                or any(
                    not isinstance(key_id, str) or not key_id
                    or not isinstance(value, str) or not value
                    for key_id, value in parsed_keys.items()
                )
            ):
                raise ValueError("Pinned public keys must be a non-empty JSON object of key IDs and base64 values")
            approval_public_keys = parsed_keys
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"Invalid ODEI_PATCH_APPROVAL_PUBLIC_KEYS: {exc}", file=sys.stderr)
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
            patch_approval_issuer=approval_issuer,
            patch_approval_public_keys=approval_public_keys,
        )
        print("ODEI Local Workspace Companion is starting on 127.0.0.1.")
        print(f"{len(workspace_ids)} selected folder(s) are held by OS handles.")
        print(
            "Signed one-file patch application is enabled."
            if approval_issuer else
            "Access is read-only; signed patch application is not configured."
        )
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
