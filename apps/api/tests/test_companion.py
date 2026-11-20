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


def test_companion_private_network_preflight_is_scoped_to_allowed_origin(tmp_path) -> None:
    client, registry, _pairing, _code = _build_client(tmp_path)
    try:
        response = client.options(
            "/v1/workspace/files",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
                "Access-Control-Request-Private-Network": "true",
            },
        )
        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
        assert response.headers["Access-Control-Allow-Private-Network"] == "true"
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
