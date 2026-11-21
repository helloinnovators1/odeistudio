import base64
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr

from odei_api.config import Settings
from odei_api.services.patch_approval import (
    CapabilityReplayCache,
    InvalidPatchCapability,
    PatchApprovalNotConfigured,
    PatchCapabilityReplay,
    canonical_patch_digest,
    issue_patch_apply_capability,
    verify_patch_apply_capability,
)
from odei_api.services.patch_proposals import sha256_text


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _fixture():
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    settings = Settings(
        patch_approval_issuer="https://api.odei.example",
        patch_approval_key_id="test-key-1",
        patch_approval_private_key_b64=SecretStr(_b64(private_raw)),
        patch_approval_ttl_seconds=60,
    )
    content = "print('updated')"
    files = [{
        "path": "src/main.py",
        "operation": "update",
        "base_sha256": "a" * 64,
        "result_sha256": sha256_text(content),
        "content": content,
    }]
    return settings, {"test-key-1": _b64(public_raw)}, files


def test_capability_binds_exact_workspace_proposal_version_and_patch_and_is_one_use():
    settings, public_keys, files = _fixture()
    now = int(time.time())
    token, expires_at, digest = issue_patch_apply_capability(
        settings=settings,
        principal_issuer="https://identity.odei.example",
        principal_subject="user-123",
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace_1234567890123456",
        proposal_id="proposal-1",
        proposal_version=2,
        files=files,
        now=now,
    )
    assert expires_at == now + 60
    assert digest == canonical_patch_digest(
        workspace_id="workspace_1234567890123456",
        proposal_id="proposal-1", proposal_version=2, files=files,
    )
    replay = CapabilityReplayCache()
    claims = verify_patch_apply_capability(
        token,
        public_keys=public_keys,
        issuer="https://api.odei.example",
        organization_id="org-1", project_id="project-1",
        workspace_id="workspace_1234567890123456",
        proposal_id="proposal-1", proposal_version=2, files=files,
        replay_cache=replay,
    )
    assert claims["sub"] == "user-123"
    with pytest.raises(PatchCapabilityReplay):
        verify_patch_apply_capability(
            token,
            public_keys=public_keys,
            issuer="https://api.odei.example",
            organization_id="org-1", project_id="project-1",
            workspace_id="workspace_1234567890123456",
            proposal_id="proposal-1", proposal_version=2, files=files,
            replay_cache=replay,
        )


def test_capability_rejects_changed_content_and_wrong_workspace():
    settings, public_keys, files = _fixture()
    token, _, _ = issue_patch_apply_capability(
        settings=settings,
        principal_issuer="https://identity.odei.example",
        principal_subject="user-123",
        organization_id="org-1", project_id="project-1",
        workspace_id="workspace_1234567890123456",
        proposal_id="proposal-1", proposal_version=2, files=files,
    )
    replay = CapabilityReplayCache()
    changed = [dict(files[0], content="different")]
    with pytest.raises(InvalidPatchCapability):
        verify_patch_apply_capability(
            token, public_keys=public_keys, issuer="https://api.odei.example",
            organization_id="org-1", project_id="project-1",
            workspace_id="workspace_1234567890123456",
            proposal_id="proposal-1", proposal_version=2, files=changed,
            replay_cache=replay,
        )
    with pytest.raises(InvalidPatchCapability):
        verify_patch_apply_capability(
            token, public_keys=public_keys, issuer="https://api.odei.example",
            organization_id="org-1", project_id="project-1",
            workspace_id="workspace_different123456",
            proposal_id="proposal-1", proposal_version=2, files=files,
            replay_cache=replay,
        )


def test_capability_rejects_untrusted_keys_and_invalid_workspace_or_file_hash():
    settings, public_keys, files = _fixture()
    with pytest.raises(PatchApprovalNotConfigured):
        verify_patch_apply_capability(
            "x", public_keys={}, issuer="https://api.odei.example",
            organization_id="org-1", project_id="project-1",
            workspace_id="workspace_1234567890123456",
            proposal_id="proposal-1", proposal_version=2, files=files,
            replay_cache=CapabilityReplayCache(),
        )
    with pytest.raises(Exception):
        canonical_patch_digest(
            workspace_id="../escape", proposal_id="proposal-1",
            proposal_version=2, files=files,
        )
    with pytest.raises(Exception):
        canonical_patch_digest(
            workspace_id="workspace_1234567890123456", proposal_id="proposal-1",
            proposal_version=2, files=[dict(files[0], result_sha256="0" * 64)],
        )


def test_patch_approval_settings_must_be_configured_as_a_complete_keyset():
    with pytest.raises(ValueError, match="must be configured together"):
        Settings(patch_approval_issuer="https://api.odei.example")
