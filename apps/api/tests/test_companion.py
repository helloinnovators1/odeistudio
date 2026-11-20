from __future__ import annotations

from fastapi.testclient import TestClient

from odei_api.companion import PairingManager, create_companion_app
from odei_api.services.workspace_handles import WorkspaceHandleRegistry

ORIGIN = "https://studio.example.test"
BASE_URL = "http://127.0.0.1:8765"


def _build_client(tmp_path):
    selected = tmp_path / "project"
    selected.mkdir()
    (selected / "main.py").write_text("print('ODEI')", encoding="utf-8")
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected)
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
