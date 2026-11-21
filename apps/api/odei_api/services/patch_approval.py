"""Ed25519 one-use capabilities bound to an approved local patch."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from odei_api.config import Settings
from odei_api.services.patch_proposals import (
    MAX_FILE_BYTES,
    MAX_PATCH_FILES,
    MAX_TOTAL_BYTES,
    PatchProposalError,
    sha256_text,
    validate_patch_path,
)

CAPABILITY_AUDIENCE = "odei-local-companion"
MAX_CAPABILITY_TTL_SECONDS = 300
MAX_CAPABILITY_BYTES = 8_192
_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PatchApprovalError(ValueError):
    """Base error for capability failures."""


class PatchApprovalNotConfigured(PatchApprovalError):
    """Signing or verification keys are not configured."""


class InvalidPatchCapability(PatchApprovalError):
    """A capability is invalid or bound to different patch data."""


class PatchCapabilityReplay(InvalidPatchCapability):
    """A capability has already been consumed."""


def _decode_key(value: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise PatchApprovalError("Key material is invalid")
    try:
        return base64.b64decode((value + "=" * (-len(value) % 4)).encode("ascii"), altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise PatchApprovalError("Key material is invalid") from exc


def validate_patch_approval_public_keys(public_keys: Mapping[str, str]) -> None:
    """Validate the pinned Ed25519 public-key map before enabling companion writes."""
    if not isinstance(public_keys, Mapping) or not 1 <= len(public_keys) <= 16:
        raise PatchApprovalNotConfigured("Pinned patch approval public keys are missing or invalid")
    for key_id, encoded_key in public_keys.items():
        if not isinstance(key_id, str) or not key_id or len(key_id) > 64:
            raise PatchApprovalNotConfigured("Pinned patch approval key ID is invalid")
        try:
            Ed25519PublicKey.from_public_bytes(_decode_key(encoded_key))
        except (PatchApprovalError, ValueError, TypeError) as exc:
            raise PatchApprovalNotConfigured("Pinned patch approval public key is invalid") from exc


def canonical_patch_digest(*, workspace_id: str, proposal_id: str, proposal_version: int, files: list[dict[str, Any]]) -> str:
    """Digest the exact file operations and replacement bytes authorized for apply."""
    if not isinstance(workspace_id, str) or not _WORKSPACE_ID.fullmatch(workspace_id):
        raise PatchApprovalError("Workspace identifier is invalid")
    if not isinstance(proposal_id, str) or not proposal_id or len(proposal_id) > 128:
        raise PatchApprovalError("Proposal identifier is invalid")
    if not isinstance(proposal_version, int) or isinstance(proposal_version, bool) or proposal_version < 0:
        raise PatchApprovalError("Proposal version is invalid")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_PATCH_FILES:
        raise PatchApprovalError("A capability must bind one to twenty files")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_bytes = 0
    for item in files:
        if not isinstance(item, dict) or not {"path", "operation", "base_sha256", "result_sha256", "content"}.issubset(item):
            raise PatchApprovalError("Patch file entry is incomplete")
        path = item["path"]
        try:
            validate_patch_path(path)
        except PatchProposalError as exc:
            raise PatchApprovalError("Patch path is not permitted") from exc
        folded = path.casefold()
        if folded in seen:
            raise PatchApprovalError("Duplicate patch paths are not allowed")
        seen.add(folded)
        operation, base_hash, result_hash, content = (
            item["operation"], item["base_sha256"], item["result_sha256"], item["content"]
        )
        if operation == "create":
            valid_shape = base_hash is None and isinstance(content, str)
        elif operation == "update":
            valid_shape = isinstance(base_hash, str) and _SHA256.fullmatch(base_hash) and isinstance(content, str)
        elif operation == "delete":
            valid_shape = isinstance(base_hash, str) and _SHA256.fullmatch(base_hash) and content is None and result_hash is None
        else:
            valid_shape = False
        if not valid_shape:
            raise PatchApprovalError("Patch operation fields are inconsistent")
        if operation != "delete":
            if "\x00" in content:
                raise PatchApprovalError("Binary patch content is not supported")
            try:
                encoded = content.encode("utf-8", errors="strict")
                actual_hash = sha256_text(content)
            except (UnicodeEncodeError, PatchProposalError) as exc:
                raise PatchApprovalError("Patch content must be valid UTF-8 text") from exc
            if len(encoded) > MAX_FILE_BYTES:
                raise PatchApprovalError("A patch file exceeds the per-file size limit")
            total_bytes += len(encoded)
            if total_bytes > MAX_TOTAL_BYTES:
                raise PatchApprovalError("Patch content exceeds the aggregate size limit")
            if not isinstance(result_hash, str) or not _SHA256.fullmatch(result_hash) or actual_hash != result_hash:
                raise PatchApprovalError("Patch result hash does not match replacement content")
        normalized.append({
            "path": path, "operation": operation, "base_sha256": base_hash,
            "result_sha256": result_hash, "content": content,
        })
    normalized.sort(key=lambda item: item["path"].casefold())
    encoded = json.dumps({
        "workspace_id": workspace_id, "proposal_id": proposal_id,
        "proposal_version": proposal_version, "files": normalized,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def issue_patch_apply_capability(
    *, settings: Settings, principal_issuer: str, principal_subject: str,
    organization_id: str, project_id: str, workspace_id: str, proposal_id: str,
    proposal_version: int, files: list[dict[str, Any]], challenge: str,
    now: int | None = None,
) -> tuple[str, int, str]:
    """Sign a short-lived capability; no token is persisted."""
    if not settings.patch_approval_issuer or not settings.patch_approval_key_id or not settings.patch_approval_private_key_b64:
        raise PatchApprovalNotConfigured("Patch approval signing is not configured")
    if not isinstance(challenge, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", challenge):
        raise PatchApprovalError("A fresh companion challenge is required")
    digest = canonical_patch_digest(
        workspace_id=workspace_id, proposal_id=proposal_id,
        proposal_version=proposal_version, files=files,
    )
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(
            _decode_key(settings.patch_approval_private_key_b64.get_secret_value())
        )
    except (ValueError, TypeError) as exc:
        raise PatchApprovalNotConfigured("Patch approval signing key is invalid") from exc
    issued_at = int(time.time()) if now is None else int(now)
    expires_at = issued_at + settings.patch_approval_ttl_seconds
    claims = {
        "iss": settings.patch_approval_issuer, "aud": CAPABILITY_AUDIENCE,
        "sub": principal_subject, "actor_issuer": principal_issuer,
        "organization_id": organization_id, "project_id": project_id,
        "workspace_id": workspace_id, "proposal_id": proposal_id,
        "proposal_version": proposal_version, "patch_sha256": digest,
        "companion_challenge": challenge,
        "jti": uuid4().hex, "iat": issued_at, "exp": expires_at,
    }
    token = jwt.encode(
        claims, private_key, algorithm="EdDSA",
        headers={"kid": settings.patch_approval_key_id, "typ": "JWT"},
    )
    return token, expires_at, digest


class CapabilityReplayCache:
    """Process-local one-use jti cache; restart invalidates outstanding capabilities."""

    def __init__(self, *, clock=time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._used: dict[str, int] = {}

    def consume(self, jti: str, expires_at: int) -> bool:
        now = int(self._clock())
        if not isinstance(jti, str) or not jti or len(jti) > 128 or expires_at <= now:
            return False
        with self._lock:
            for key, expiry in list(self._used.items()):
                if expiry <= now:
                    self._used.pop(key, None)
            if jti in self._used:
                return False
            self._used[jti] = expires_at
            return True


def verify_patch_apply_capability(
    token: str, *, public_keys: Mapping[str, str], issuer: str,
    organization_id: str, project_id: str, workspace_id: str,
    proposal_id: str, proposal_version: int, files: list[dict[str, Any]],
    challenge: str, replay_cache: CapabilityReplayCache, now: int | None = None,
) -> dict[str, Any]:
    """Verify signature, issuer, audience, expiry, payload binding and replay."""
    if not isinstance(token, str) or not token or len(token.encode("utf-8")) > MAX_CAPABILITY_BYTES:
        raise InvalidPatchCapability("Capability is missing or oversized")
    if not isinstance(public_keys, Mapping) or not public_keys:
        raise PatchApprovalNotConfigured("No pinned patch approval public keys are configured")
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "EdDSA" or header.get("typ") != "JWT" or not isinstance(kid, str):
            raise InvalidPatchCapability("Capability header is invalid")
        encoded_key = public_keys.get(kid)
        if encoded_key is None:
            raise InvalidPatchCapability("Capability key is not trusted")
        public_key = Ed25519PublicKey.from_public_bytes(_decode_key(encoded_key))
        current = int(time.time()) if now is None else int(now)
        claims = jwt.decode(
            token, public_key, algorithms=["EdDSA"],
            audience=CAPABILITY_AUDIENCE, issuer=issuer, leeway=5,
            options={"require": [
                "iss", "aud", "sub", "actor_issuer", "organization_id",
                "project_id", "workspace_id", "proposal_id", "proposal_version",
                "patch_sha256", "companion_challenge", "jti", "iat", "exp",
            ]},
        )
    except InvalidPatchCapability:
        raise
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidPatchCapability("Capability signature or claims are invalid") from exc
    if (
        claims.get("organization_id") != organization_id
        or claims.get("project_id") != project_id
        or claims.get("workspace_id") != workspace_id
        or claims.get("proposal_id") != proposal_id
        or claims.get("proposal_version") != proposal_version
        or claims.get("companion_challenge") != challenge
        or not isinstance(challenge, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", challenge)
        or not isinstance(claims.get("sub"), str) or not claims.get("sub")
        or not isinstance(claims.get("actor_issuer"), str) or not claims.get("actor_issuer")
        or claims.get("exp", 0) <= claims.get("iat", 0)
        or claims.get("exp", 0) - claims.get("iat", 0) > MAX_CAPABILITY_TTL_SECONDS
        or claims.get("iat", current + 1) > current + 5
    ):
        raise InvalidPatchCapability("Capability is bound to a different or invalid request")
    try:
        digest = canonical_patch_digest(
            workspace_id=workspace_id, proposal_id=proposal_id,
            proposal_version=proposal_version, files=files,
        )
    except PatchApprovalError as exc:
        raise InvalidPatchCapability("Patch payload is invalid") from exc
    if not isinstance(claims.get("patch_sha256"), str) or not hmac.compare_digest(claims["patch_sha256"], digest):
        raise InvalidPatchCapability("Capability does not authorize this patch payload")
    if not replay_cache.consume(claims.get("jti", ""), int(claims.get("exp", 0))):
        raise PatchCapabilityReplay("Capability has expired or has already been used")
    return claims
