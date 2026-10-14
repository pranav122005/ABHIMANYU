"""
Comprehensive Security and Authorization Hardening Tests for ABHIMANYU DTN API.
Validates authentication, actor authorization boundaries, spoofing prevention,
admin override capabilities, and production credential protection.
"""

import os
import sys
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.db import DemoDatabase, get_default_db_path
from api.server import app, db, service


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_tokens(client):
    # Authenticate node-01
    res1 = client.post("/api/nodes/node-01/connect", json={"password": "pass-node-01"})
    assert res1.status_code == 200
    token1 = res1.json()["token"]

    # Authenticate node-02
    res2 = client.post("/api/nodes/node-02/connect", json={"password": "pass-node-02"})
    assert res2.status_code == 200
    token2 = res2.json()["token"]

    # Authenticate node-03
    res3 = client.post("/api/nodes/node-03/connect", json={"password": "pass-node-03"})
    assert res3.status_code == 200
    token3 = res3.json()["token"]

    return {
        "node-01": token1,
        "node-02": token2,
        "node-03": token3,
        "admin": "dev-admin-secret-token",
    }


def test_admin_routes_unauthorized_without_token(client):
    """Admin endpoints must reject requests lacking administrative authentication."""
    # 1. Contacts modification
    r1 = client.post("/api/contacts", json={"node_a": "node-01", "node_b": "node-02", "is_active": True})
    assert r1.status_code == 401

    # 2. Simulation step
    r2 = client.post("/api/simulation/step", json={"step_delta_ms": 1000})
    assert r2.status_code == 401

    # 3. Simulation policy
    r3 = client.post("/api/simulation/policy", json={"policy": "epidemic"})
    assert r3.status_code == 401

    # 4. Simulation reset
    r4 = client.post("/api/simulation/reset")
    assert r4.status_code == 401

    # 5. Global messages inspection
    r5 = client.get("/api/messages")
    assert r5.status_code == 401

    # 6. Global event logs
    r6 = client.get("/api/events")
    assert r6.status_code == 401

    # 7. Node administrative patch
    r7 = client.patch("/api/nodes/node-01", json={"status": "offline"})
    assert r7.status_code == 401


def test_admin_routes_forbidden_with_invalid_token(client):
    """Admin endpoints must reject requests with an incorrect admin token."""
    bad_headers = {"X-Admin-Token": "completely-invalid-admin-secret"}
    r = client.post("/api/simulation/step", headers=bad_headers, json={"step_delta_ms": 1000})
    assert r.status_code == 403


def test_identity_spoofing_prevention(client, auth_tokens):
    """An authenticated node cannot forge the source_id of another node."""
    token_node1 = auth_tokens["node-01"]
    spoofed_req = {
        "source_id": "node-02",  # Attempting to forge node-02 while logged in as node-01
        "destination_id": "node-03",
        "payload": "Spoofed bundle attempting fraud",
    }
    res = client.post(
        "/api/messages",
        headers={"Authorization": f"Bearer {token_node1}"},
        json=spoofed_req,
    )
    assert res.status_code == 403
    assert "cannot send messages as source" in res.json()["detail"]


def test_mailbox_access_control(client, auth_tokens):
    """A node cannot access the inbox or outbox of other nodes."""
    token_node1 = auth_tokens["node-01"]

    # node-01 tries to access node-02's inbox
    r_inbox = client.get(
        "/api/nodes/node-02/inbox",
        headers={"Authorization": f"Bearer {token_node1}"},
    )
    assert r_inbox.status_code == 403

    # node-01 tries to access node-02's outbox
    r_outbox = client.get(
        "/api/nodes/node-02/outbox",
        headers={"Authorization": f"Bearer {token_node1}"},
    )
    assert r_outbox.status_code == 403


def test_message_telemetry_isolation(client, auth_tokens):
    """A third party node cannot inspect messages or routing decisions of others."""
    token_node1 = auth_tokens["node-01"]
    token_node3 = auth_tokens["node-03"]
    msg_id = f"sec-isolation-{uuid.uuid4().hex[:6]}"

    # Send message from node-01 to node-02
    send_res = client.post(
        "/api/messages",
        headers={"Authorization": f"Bearer {token_node1}"},
        json={
            "message_id": msg_id,
            "source_id": "node-01",
            "destination_id": "node-02",
            "payload": "Confidential routing telemetry test",
        },
    )
    assert send_res.status_code == 200

    # node-03 (not sender, not recipient) attempts to view message details
    r_detail = client.get(
        f"/api/messages/{msg_id}",
        headers={"Authorization": f"Bearer {token_node3}"},
    )
    assert r_detail.status_code == 403

    # node-03 attempts to view message route telemetry
    r_route = client.get(
        f"/api/messages/{msg_id}/route",
        headers={"Authorization": f"Bearer {token_node3}"},
    )
    assert r_route.status_code == 403

    # Sender (node-01) can view both
    assert client.get(f"/api/messages/{msg_id}", headers={"Authorization": f"Bearer {token_node1}"}).status_code == 200
    assert client.get(f"/api/messages/{msg_id}/route", headers={"Authorization": f"Bearer {token_node1}"}).status_code == 200


def test_admin_override_capabilities(client, auth_tokens):
    """Administrators can dispatch messages on behalf of any node and inspect any telemetry."""
    admin_headers = {"X-Admin-Token": auth_tokens["admin"]}
    admin_msg_id = f"sec-admin-{uuid.uuid4().hex[:6]}"

    # Admin dispatches bundle from node-02
    r_dispatch = client.post(
        "/api/messages",
        headers=admin_headers,
        json={
            "message_id": admin_msg_id,
            "source_id": "node-02",
            "destination_id": "node-03",
            "payload": "Administrative broadcast",
        },
    )
    assert r_dispatch.status_code == 200

    # Admin can inspect message and route
    assert client.get(f"/api/messages/{admin_msg_id}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/messages/{admin_msg_id}/route", headers=admin_headers).status_code == 200

    # Admin can view node-02 inbox
    assert client.get("/api/nodes/node-02/inbox", headers=admin_headers).status_code == 200


def test_production_mode_credential_suppression(tmp_path: Path, monkeypatch):
    """In production mode (DTN_ENV=production), plain passwords are never saved or returned."""
    monkeypatch.setenv("DTN_ENV", "production")
    prod_db_file = tmp_path / "prod_test.db"
    prod_db = DemoDatabase(db_path=prod_db_file)
    prod_db.initialize_default_nodes()

    # Query all nodes with include_plain_passwords=True (should still be stripped)
    nodes = prod_db.get_all_nodes(include_plain_passwords=True)
    assert len(nodes) == 10
    for n in nodes:
        assert "password_hash" not in n
        assert "password_salt" not in n
        assert "demo_password_plain" not in n

    # Single node query
    n1 = prod_db.get_node("node-01", include_auth=True)
    assert "password_hash" not in n1
    assert "demo_password_plain" not in n1


def test_custom_db_path_environment(tmp_path: Path, monkeypatch):
    """Validates that DTN_DB_PATH environment variable correctly configures storage location."""
    custom_loc = tmp_path / "custom_data" / "app.db"
    monkeypatch.setenv("DTN_DB_PATH", str(custom_loc))
    resolved = get_default_db_path()
    assert resolved == custom_loc.resolve()

    custom_db = DemoDatabase()
    assert custom_db.db_path == custom_loc.resolve()
    assert custom_loc.parent.exists()
