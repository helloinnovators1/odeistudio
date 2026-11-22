from __future__ import annotations

import base64
import ctypes
import hashlib
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import SecretStr

from odei_api.companion import ApplyChallengeManager, ApplyPatchRequest, PairingManager, create_companion_app
from odei_api.config import Settings
from odei_api.services.patch_approval import issue_patch_apply_capability
from odei_api.services.workspace_handles import WorkspaceHandleRegistry

ORIGIN = "https://studio.example.test"
BASE_URL = "http://127.0.0.1:8765"


def _build_client(tmp_path):
    selected = tmp_path / "project"
    selected.mkdir()
    (selected / "main.py").write_text("print('ODEI')", encoding="utf-8")
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected, allow_patch_apply=True)
    pairing = PairingManager()
    code = pairing.issue_pairing_code()
    app = create_companion_app(
        registry,
        workspace_id,
        allowed_origins=[ORIGIN],
        pairing_manager=pairing,
        port=8765,
    )
    return TestClient(app, base_url=BASE_URL), registry, pairing, code


def test_companion_pairs_and_reads_selected_workspace(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        response = client.post(
            "/v1/pair",
            headers={"Origin": ORIGIN},
            json={"code": code},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        assert response.json()["permissions"] == ["workspace:read"]

        files = client.get(
            "/v1/workspace/files",
            headers={"Origin": ORIGIN, "Authorization": f"Bearer {token}"},
        )
        assert files.status_code == 200
        assert files.headers["Cache-Control"] == "no-store"
        assert files.json()["files"] == [{"path": "main.py", "size": 13}]

        content = client.get(
            "/v1/workspace/file",
            params={"path": "main.py"},
            headers={"Origin": ORIGIN, "Authorization": f"Bearer {token}"},
        )
        assert content.status_code == 200
        assert content.json()["content"] == "print('ODEI')"
    finally:
        registry.close()


def test_companion_rejects_unapproved_origin(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        response = client.post(
            "/v1/pair",
            headers={"Origin": "https://attacker.example"},
            json={"code": code},
        )
        assert response.status_code == 403
    finally:
        registry.close()


def test_companion_rejects_host_header_rebinding(tmp_path) -> None:
    client, registry, _pairing, _code = _build_client(tmp_path)
    try:
        response = client.get(
            "/v1/workspace/files",
            headers={"Host": "attacker.example:8765", "Origin": ORIGIN},
        )
        assert response.status_code == 400
    finally:
        registry.close()


def test_companion_pairing_code_is_one_time_and_session_can_be_revoked(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        headers = {"Origin": ORIGIN}
        response = client.post("/v1/pair", headers=headers, json={"code": code})
        assert response.status_code == 200
        token = response.json()["access_token"]

        replay = client.post("/v1/pair", headers=headers, json={"code": code})
        assert replay.status_code == 401

        revoked = client.post(
            "/v1/session/revoke",
            headers={**headers, "Authorization": f"Bearer {token}"},
        )
        assert revoked.status_code == 204

        denied = client.get(
            "/v1/workspace/files",
            headers={**headers, "Authorization": f"Bearer {token}"},
        )
        assert denied.status_code == 401
    finally:
        registry.close()


def test_companion_standard_cors_preflight_is_scoped_to_allowed_origin(tmp_path) -> None:
    client, registry, _pairing, _code = _build_client(tmp_path)
    try:
        response = client.options(
            "/v1/workspace/files",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert response.status_code == 204
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
        assert "authorization" in response.headers["Access-Control-Allow-Headers"].casefold()
        assert "Access-Control-Allow-Private-Network" not in response.headers
    finally:
        registry.close()


def test_pairing_manager_expires_codes_and_tokens() -> None:
    now = [100.0]
    manager = PairingManager(
        pairing_ttl_seconds=10,
        token_ttl_seconds=20,
        clock=lambda: now[0],
    )
    code = manager.issue_pairing_code()
    now[0] += 11
    assert manager.exchange(code, ORIGIN) is None

    code = manager.issue_pairing_code()
    token = manager.exchange(code, ORIGIN)
    assert token is not None
    assert manager.is_valid(token)
    now[0] += 21
    assert not manager.is_valid(token)


def test_pairing_manager_rejects_non_ascii_and_rate_limits_failures() -> None:
    manager = PairingManager(max_failed_attempts=2)
    code = manager.issue_pairing_code()
    assert manager.exchange("🔐", ORIGIN) is None
    assert manager.exchange("wrong-one", ORIGIN) is None
    assert manager.exchange(code, ORIGIN) is None


def test_companion_rejects_insecure_public_origin(tmp_path) -> None:
    import pytest

    selected = tmp_path / "project"
    selected.mkdir()
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected)
    try:
        with pytest.raises(ValueError, match="must use HTTPS"):
            create_companion_app(
                registry,
                workspace_id,
                allowed_origins=["http://studio.example.test"],
            )
    finally:
        registry.close()


def test_companion_allows_loopback_http_development_origin(tmp_path) -> None:
    selected = tmp_path / "project"
    selected.mkdir()
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected)
    try:
        app = create_companion_app(
            registry,
            workspace_id,
            allowed_origins=["http://localhost:3002"],
        )
        assert app.title == "ODEI Local Workspace Companion"
    finally:
        registry.close()


def test_companion_rejects_non_origin_configuration(tmp_path) -> None:
    import pytest

    selected = tmp_path / "project"
    selected.mkdir()
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected)
    try:
        with pytest.raises(ValueError):
            create_companion_app(
                registry,
                workspace_id,
                allowed_origins=["https://studio.example.test/untrusted-path"],
            )
    finally:
        registry.close()


def test_companion_rejects_path_traversal(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        paired = client.post(
            "/v1/pair",
            headers={"Origin": ORIGIN},
            json={"code": code},
        )
        token = paired.json()["access_token"]
        response = client.get(
            "/v1/workspace/file",
            params={"path": "../outside.txt"},
            headers={"Origin": ORIGIN, "Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400
    finally:
        registry.close()


def test_companion_rejects_invalid_port(tmp_path) -> None:
    import pytest

    selected = tmp_path / "project"
    selected.mkdir()
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected)
    try:
        with pytest.raises(ValueError):
            create_companion_app(
                registry,
                workspace_id,
                allowed_origins=[ORIGIN],
                port=0,
            )
    finally:
        registry.close()


def test_companion_supports_multiple_explicitly_selected_roots(tmp_path) -> None:
    registry = WorkspaceHandleRegistry()
    first = tmp_path / "odei-studio"
    second = tmp_path / "cursor-gallery"
    first.mkdir()
    second.mkdir()
    (first / "README.md").write_text("ODEI project", encoding="utf-8")
    (second / "gallery.txt").write_text("reference gallery", encoding="utf-8")
    first_id = registry.register_selected_root(first)
    second_id = registry.register_selected_root(second)
    pairing = PairingManager()
    code = pairing.issue_pairing_code()
    app = create_companion_app(
        registry,
        [first_id, second_id],
        allowed_origins=[ORIGIN],
        pairing_manager=pairing,
        port=8765,
    )
    client = TestClient(app, base_url=BASE_URL)
    headers = {"Origin": ORIGIN}
    try:
        paired = client.post("/v1/pair", headers=headers, json={"code": code})
        token = paired.json()["access_token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}

        workspaces = client.get("/v1/workspaces", headers=auth_headers)
        assert workspaces.status_code == 200
        assert [item["workspace_id"] for item in workspaces.json()["workspaces"]] == [
            first_id,
            second_id,
        ]
        assert [item["name"] for item in workspaces.json()["workspaces"]] == [
            "odei-studio", "cursor-gallery",
        ]
        assert str(tmp_path) not in workspaces.text

        first_files = client.get(
            f"/v1/workspaces/{first_id}/files", headers=auth_headers
        )
        second_files = client.get(
            f"/v1/workspaces/{second_id}/files", headers=auth_headers
        )
        assert [item["path"] for item in first_files.json()["files"]] == ["README.md"]
        assert [item["path"] for item in second_files.json()["files"]] == ["gallery.txt"]

        ambiguous = client.get("/v1/workspace/files", headers=auth_headers)
        assert ambiguous.status_code == 409
        unknown = client.get("/v1/workspaces/not-selected/files", headers=auth_headers)
        assert unknown.status_code == 404
    finally:
        registry.close()



def test_companion_rejects_zero_origin_port(tmp_path) -> None:
    import pytest

    selected = tmp_path / "project"
    selected.mkdir()
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected)
    try:
        with pytest.raises(ValueError, match="exact scheme-and-host origins"):
            create_companion_app(
                registry,
                workspace_id,
                allowed_origins=["https://studio.example.test:0"],
            )
    finally:
        registry.close()


def _paired_headers(client, code):
    headers = {"Origin": ORIGIN}
    paired = client.post("/v1/pair", headers=headers, json={"code": code})
    assert paired.status_code == 200
    return {**headers, "Authorization": f"Bearer {paired.json()['access_token']}"}


def test_companion_builds_live_patch_preview_without_writing_files(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        headers = _paired_headers(client, code)
        original = "print('ODEI')"
        workspace_id = client.get(
            "/v1/workspaces", headers=headers
        ).json()["workspaces"][0]["workspace_id"]
        response = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"main.py": "print('NEXUS')"},
                "expected_base_hashes": {
                    "main.py": hashlib.sha256(original.encode("utf-8")).hexdigest()
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "preview_only"
        assert payload["writes_performed"] is False
        assert payload["files"][0]["operation"] == "update"
        assert "-print('ODEI')" in payload["files"][0]["unified_diff"]
        assert "+print('NEXUS')" in payload["files"][0]["unified_diff"]
        assert registry.read_text(workspace_id, "main.py") == original
    finally:
        registry.close()


def test_companion_patch_preview_supports_root_create_and_delete(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        headers = _paired_headers(client, code)
        workspace_id = client.get(
            "/v1/workspaces", headers=headers
        ).json()["workspaces"][0]["workspace_id"]
        created = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"new.py": "print('new')"},
                "expected_base_hashes": {"new.py": None},
            },
        )
        assert created.status_code == 200
        assert created.json()["files"][0]["operation"] == "create"
        assert not (tmp_path / "project" / "new.py").exists()

        original = "print('ODEI')"
        deleted = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"main.py": None},
                "expected_base_hashes": {
                    "main.py": hashlib.sha256(original.encode("utf-8")).hexdigest()
                },
            },
        )
        assert deleted.status_code == 200
        assert deleted.json()["files"][0]["operation"] == "delete"
        assert registry.read_text(workspace_id, "main.py") == original
    finally:
        registry.close()


def test_companion_patch_preview_rejects_stale_hash_and_nested_create(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        headers = _paired_headers(client, code)
        workspace_id = client.get(
            "/v1/workspaces", headers=headers
        ).json()["workspaces"][0]["workspace_id"]
        stale = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"main.py": "changed"},
                "expected_base_hashes": {"main.py": "0" * 64},
            },
        )
        assert stale.status_code == 409

        nested = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"src/new.py": "content"},
                "expected_base_hashes": {"src/new.py": None},
            },
        )
        assert nested.status_code == 400
    finally:
        registry.close()


def test_companion_patch_preview_requires_valid_session(tmp_path) -> None:
    client, registry, _pairing, _code = _build_client(tmp_path)
    try:
        response = client.post(
            "/v1/workspaces/not-authorized/patch-proposals",
            headers={"Origin": ORIGIN},
            json={
                "changes": {"new.py": "content"},
                "expected_base_hashes": {"new.py": None},
            },
        )
        assert response.status_code == 401
    finally:
        registry.close()


def test_companion_patch_preview_rejects_binary_and_oversized_payloads(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        headers = _paired_headers(client, code)
        workspace_id = client.get(
            "/v1/workspaces", headers=headers
        ).json()["workspaces"][0]["workspace_id"]
        binary = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"new.py": "bad\u0000content"},
                "expected_base_hashes": {"new.py": None},
            },
        )
        assert binary.status_code == 422

        too_large = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"new.py": "x" * 1_000_001},
                "expected_base_hashes": {"new.py": None},
            },
        )
        assert too_large.status_code == 422
    finally:
        registry.close()


def test_companion_patch_preview_rejects_existing_empty_directory_as_new_file(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    (tmp_path / "project" / "empty-dir").mkdir()
    try:
        headers = _paired_headers(client, code)
        workspace_id = client.get(
            "/v1/workspaces", headers=headers
        ).json()["workspaces"][0]["workspace_id"]
        response = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"empty-dir": "not a file"},
                "expected_base_hashes": {"empty-dir": None},
            },
        )
        assert response.status_code == 409
    finally:
        registry.close()


def test_companion_patch_preview_validates_paths_and_hashes_before_io(tmp_path) -> None:
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        headers = _paired_headers(client, code)
        workspace_id = client.get(
            "/v1/workspaces", headers=headers
        ).json()["workspaces"][0]["workspace_id"]
        traversal = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"../outside.txt": "content"},
                "expected_base_hashes": {"../outside.txt": None},
            },
        )
        assert traversal.status_code == 422

        malformed_hash = client.post(
            f"/v1/workspaces/{workspace_id}/patch-proposals",
            headers=headers,
            json={
                "changes": {"main.py": "changed"},
                "expected_base_hashes": {"main.py": "not-a-hash"},
            },
        )
        assert malformed_hash.status_code == 422
    finally:
        registry.close()


def _build_apply_client(tmp_path):
    selected = tmp_path / "project"
    selected.mkdir()
    original = "print('ODEI')"
    (selected / "main.py").write_text(original, encoding="utf-8")
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected, allow_patch_apply=True)
    pairing = PairingManager()
    code = pairing.issue_pairing_code()
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
    private_encoded = base64.urlsafe_b64encode(private_raw).decode("ascii").rstrip("=")
    public_encoded = base64.urlsafe_b64encode(public_raw).decode("ascii").rstrip("=")
    settings = Settings(
        patch_approval_issuer="https://api.odei.example",
        patch_approval_key_id="companion-test",
        patch_approval_private_key_b64=SecretStr(private_encoded),
        patch_approval_ttl_seconds=60,
    )
    app = create_companion_app(
        registry,
        workspace_id,
        allowed_origins=[ORIGIN],
        pairing_manager=pairing,
        port=8765,
        patch_approval_issuer="https://api.odei.example",
        patch_approval_public_keys={"companion-test": public_encoded},
    )
    return TestClient(app, base_url=BASE_URL), registry, pairing, code, workspace_id, settings, original


def test_companion_apply_challenge_is_short_lived_session_bound_and_one_use():
    now = [100.0]
    manager = ApplyChallengeManager(ttl_seconds=60, clock=lambda: now[0])
    challenge = manager.issue("workspace_1234567890123456", "session-one")
    assert manager.consume(challenge, "workspace_1234567890123456", "session-two") is False
    assert manager.consume(challenge, "workspace_1234567890123456", "session-one") is True
    assert manager.consume(challenge, "workspace_1234567890123456", "session-one") is False
    expired = manager.issue("workspace_1234567890123456", "session-one")
    now[0] += 61
    assert manager.consume(expired, "workspace_1234567890123456", "session-one") is False


def test_companion_applies_only_a_signed_one_use_approved_patch(tmp_path):
    client, registry, _pairing, code, workspace_id, settings, original = _build_apply_client(tmp_path)
    try:
        pair_response = client.post(
            "/v1/pair", headers={"Origin": ORIGIN}, json={"code": code},
        )
        assert pair_response.status_code == 200
        assert "patch:apply" in pair_response.json()["permissions"]
        headers = {"Origin": ORIGIN, "Authorization": f"Bearer {pair_response.json()['access_token']}"}
        paired = client.get("/v1/workspaces", headers=headers)
        assert paired.status_code == 200
        assert paired.json()["workspaces"][0]["workspace_id"] == workspace_id

        challenge_response = client.post(
            f"/v1/workspaces/{workspace_id}/apply-challenge", headers=headers,
        )
        assert challenge_response.status_code == 200
        challenge = challenge_response.json()["challenge"]
        replacement = "print('NEXUS')"
        file_item = {
            "path": "main.py",
            "operation": "update",
            "base_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "result_sha256": hashlib.sha256(replacement.encode("utf-8")).hexdigest(),
            "content": replacement,
        }
        token, _, _ = issue_patch_apply_capability(
            settings=settings,
            principal_issuer="https://identity.odei.example",
            principal_subject="owner-1",
            organization_id="org-1",
            project_id="project-1",
            workspace_id=workspace_id,
            proposal_id="proposal-1",
            proposal_version=1,
            files=[file_item],
            challenge=challenge,
        )
        request = {
            "organization_id": "org-1",
            "project_id": "project-1",
            "proposal_id": "proposal-1",
            "proposal_version": 1,
            "companion_challenge": challenge,
            "capability": token,
            "files": [file_item],
        }
        response = client.post(
            f"/v1/workspaces/{workspace_id}/apply-patch",
            headers=headers,
            json=request,
        )
        assert response.status_code == 200, response.text
        assert response.json()["applied"] is True
        assert isinstance(response.json()["files"][0]["durability_confirmed"], bool)
        assert registry.read_text(workspace_id, "main.py") == replacement
        replay = client.post(
            f"/v1/workspaces/{workspace_id}/apply-patch",
            headers=headers,
            json=request,
        )
        assert replay.status_code == 401
    finally:
        registry.close()


def test_companion_rejects_stale_or_mismatched_signed_patch_without_writing(tmp_path):
    client, registry, _pairing, code, workspace_id, settings, original = _build_apply_client(tmp_path)
    try:
        headers = _paired_headers(client, code)
        challenge = client.post(
            f"/v1/workspaces/{workspace_id}/apply-challenge", headers=headers,
        ).json()["challenge"]
        replacement = "print('NEXUS')"
        file_item = {
            "path": "main.py",
            "operation": "update",
            "base_sha256": "0" * 64,
            "result_sha256": hashlib.sha256(replacement.encode("utf-8")).hexdigest(),
            "content": replacement,
        }
        token, _, _ = issue_patch_apply_capability(
            settings=settings,
            principal_issuer="https://identity.odei.example",
            principal_subject="owner-1",
            organization_id="org-1",
            project_id="project-1",
            workspace_id=workspace_id,
            proposal_id="proposal-stale",
            proposal_version=1,
            files=[file_item],
            challenge=challenge,
        )
        response = client.post(
            f"/v1/workspaces/{workspace_id}/apply-patch",
            headers=headers,
            json={
                "organization_id": "org-1",
                "project_id": "project-1",
                "proposal_id": "proposal-stale",
                "proposal_version": 1,
                "companion_challenge": challenge,
                "capability": token,
                "files": [file_item],
            },
        )
        assert response.status_code == 409
        assert registry.read_text(workspace_id, "main.py") == original
    finally:
        registry.close()


def test_workspace_handle_applies_root_create_and_delete_atomically(tmp_path):
    selected = tmp_path / "project"
    selected.mkdir()
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected, allow_patch_apply=True)
    try:
        created_content = "print('created')"
        created_hash = hashlib.sha256(created_content.encode("utf-8")).hexdigest()
        created = registry.apply_patch(workspace_id, {
            "path": "created.py",
            "operation": "create",
            "base_sha256": None,
            "result_sha256": created_hash,
            "content": created_content,
        })
        assert created["applied"] is True
        assert isinstance(created["durability_confirmed"], bool)
        assert registry.read_text(workspace_id, "created.py") == created_content

        deleted = registry.apply_patch(workspace_id, {
            "path": "created.py",
            "operation": "delete",
            "base_sha256": created_hash,
            "result_sha256": None,
            "content": None,
        })
        assert deleted["operation"] == "delete"
        assert not (selected / "created.py").exists()
    finally:
        registry.close()


def test_unconfigured_companion_stays_read_only_and_cannot_issue_apply_challenges(tmp_path):
    client, registry, _pairing, code = _build_client(tmp_path)
    try:
        pair_response = client.post(
            "/v1/pair", headers={"Origin": ORIGIN}, json={"code": code},
        )
        assert pair_response.status_code == 200
        assert pair_response.json()["permissions"] == ["workspace:read"]
        headers = {
            "Origin": ORIGIN,
            "Authorization": f"Bearer {pair_response.json()['access_token']}",
        }
        workspace = client.get("/v1/workspaces", headers=headers).json()["workspaces"][0]
        assert workspace["access"] == "read-only"
        response = client.post(
            f"/v1/workspaces/{workspace['workspace_id']}/apply-challenge",
            headers=headers,
        )
        assert response.status_code == 503
    finally:
        registry.close()


def test_companion_rejects_invalid_pinned_public_keys_at_startup(tmp_path):
    selected = tmp_path / "project"
    selected.mkdir()
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected, allow_patch_apply=True)
    try:
        with pytest.raises(ValueError, match="public keys are invalid"):
            create_companion_app(
                registry,
                workspace_id,
                allowed_origins=[ORIGIN],
                pairing_manager=PairingManager(),
                port=8765,
                patch_approval_issuer="https://api.odei.example",
                patch_approval_public_keys={"bad-key": "not-a-valid-key"},
            )
    finally:
        registry.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows native file API regression")
def test_windows_relative_rename_uses_nt_set_information_file(monkeypatch):
    from types import SimpleNamespace

    from odei_api.services import windows_file_handles as windows

    captured = {}

    def fake_duplicate_handle(source_process, source_handle, target_process, target_handle, desired_access, inherit, options):
        ctypes.cast(target_handle, ctypes.POINTER(windows.wintypes.HANDLE)).contents.value = 0x9876
        captured["desired_access"] = desired_access
        return 1

    fake_kernel32 = SimpleNamespace(
        GetCurrentProcess=lambda: 0x1111,
        DuplicateHandle=fake_duplicate_handle,
        CloseHandle=lambda handle: captured.setdefault("closed_root", handle.value),
    )

    def fake_nt_set_information_file(handle, io_status, buffer, length, info_class):
        info = ctypes.cast(buffer, ctypes.POINTER(windows._FileRenameInfoEx)).contents
        name = ctypes.string_at(
            ctypes.addressof(buffer) + windows._FileRenameInfoEx.FileName.offset,
            info.FileNameLength,
        ).decode("utf-16-le")
        captured.update({
            "handle": handle,
            "root": info.RootDirectory,
            "name": name,
            "flags": info.Flags,
            "length": length,
            "info_class": info_class,
        })
        return 0

    monkeypatch.setattr(
        windows, "_apis",
        lambda: (fake_kernel32, SimpleNamespace(NtSetInformationFile=fake_nt_set_information_file)),
    )
    windows._rename_relative(fake_kernel32, 0x1234, 0x5678, "created.py", replace=True)

    assert captured == {
        "handle": 0x1234,
        "root": 0x9876,
        "name": "created.py",
        "flags": windows.FILE_RENAME_POSIX_SEMANTICS | windows.FILE_RENAME_REPLACE_IF_EXISTS,
        "length": ctypes.sizeof(windows._FileRenameInfoEx) + len("created.py".encode("utf-16-le")),
        "info_class": windows.FILE_RENAME_INFORMATION_EX,
        "desired_access": windows.FILE_TRAVERSE | windows.FILE_READ_ATTRIBUTES | windows.SYNCHRONIZE,
        "closed_root": 0x9876,
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows native file API regression")
def test_windows_patch_directory_access_does_not_require_delete_child(monkeypatch):
    from types import SimpleNamespace

    from odei_api.services import windows_file_handles as windows

    captured = {}

    def fake_create_file(path, desired_access, *args):
        captured["root_access"] = desired_access
        return 0x1234

    fake_kernel32 = SimpleNamespace(
        CreateFileW=fake_create_file,
        CloseHandle=lambda handle: 1,
    )
    monkeypatch.setattr(windows, "_apis", lambda: (fake_kernel32, SimpleNamespace()))
    monkeypatch.setattr(windows, "_check_type", lambda kernel32, handle, *, directory: None)

    _kernel32, root_handle = windows.open_directory_handle(
        "C:\\selected-workspace", allow_patch_apply=True
    )
    assert root_handle == 0x1234
    assert captured["root_access"] == (
        windows.FILE_LIST_DIRECTORY | windows.FILE_TRAVERSE
        | windows.FILE_READ_ATTRIBUTES | windows.SYNCHRONIZE | windows.FILE_ADD_FILE
    )
    assert not captured["root_access"] & windows.FILE_DELETE_CHILD

    child_capture = {}

    def fake_nt_create_file(child_ptr, desired_access, *args):
        ctypes.cast(
            child_ptr, ctypes.POINTER(windows.wintypes.HANDLE)
        ).contents.value = 0x5678
        child_capture["access"] = desired_access
        return 0

    fake_ntdll = SimpleNamespace(NtCreateFile=fake_nt_create_file)
    child = windows._open_child(
        fake_kernel32, fake_ntdll, root_handle, "nested",
        directory=True, allow_write=True,
    )
    assert child.value == 0x5678
    assert child_capture["access"] == (
        windows.FILE_READ_ATTRIBUTES | windows.SYNCHRONIZE
        | windows.FILE_LIST_DIRECTORY | windows.FILE_TRAVERSE | windows.FILE_ADD_FILE
    )
    assert not child_capture["access"] & windows.FILE_DELETE_CHILD


def test_companion_environment_diagnostics_report_prerequisites_without_opening_workspace():
    from odei_api.companion import diagnose_companion_environment

    report = diagnose_companion_environment(port=0, allowed_origins=[ORIGIN])
    assert report["ready"] is False
    assert report["checks"]["python"]["ok"] is True
    assert report["checks"]["port"]["ok"] is False
    assert report["checks"]["browser_origins"] == {"ok": True, "configured_count": 1}
    assert "studio.example.test" not in repr(report)
    assert any("No workspace is opened" in item for item in report["limitations"])


def test_companion_environment_diagnostics_reject_invalid_public_http_origin():
    from odei_api.companion import diagnose_companion_environment

    report = diagnose_companion_environment(port=8765, allowed_origins=["http://studio.example.test"])
    assert report["checks"]["browser_origins"]["ok"] is False



def test_apply_request_rejects_boolean_proposal_version() -> None:
    replacement = "print('NEXUS')"
    file_item = {
        "path": "main.py",
        "operation": "create",
        "base_sha256": None,
        "result_sha256": hashlib.sha256(replacement.encode("utf-8")).hexdigest(),
        "content": replacement,
    }
    with pytest.raises(ValueError):
        ApplyPatchRequest.model_validate({
            "organization_id": "org-1",
            "project_id": "project-1",
            "proposal_id": "proposal-1",
            "proposal_version": True,
            "companion_challenge": "c" * 32,
            "capability": "placeholder",
            "files": [file_item],
        })
