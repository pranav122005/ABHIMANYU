"""
Unit tests validating the FastAPI and SQLite integration layer for the DTN demo.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure src in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.db import DemoDatabase, hash_password, verify_password
from api.service import DTNIntegratedService
from api.server import app, db as global_db, service as global_service


def test_password_hashing():
    p_hash, p_salt = hash_password("secret123")
    assert verify_password("secret123", p_salt, p_hash) is True
    assert verify_password("wrongpass", p_salt, p_hash) is False


def test_db_init_and_nodes(tmp_path: Path):
    test_db = DemoDatabase(db_path=tmp_path / "test_demo.db")
    test_db.initialize_default_nodes()
    nodes = test_db.get_all_nodes(include_plain_passwords=True)
    assert len(nodes) == 10
    assert nodes[0]["node_id"] == "node-01"

    # Verify authentication
    token = test_db.authenticate_node("node-01", "pass-node-01")
    assert token is not None
    assert test_db.verify_session(token) == "node-01"

    # Wrong password rejected
    bad_token = test_db.authenticate_node("node-01", "wrong_password")
    assert bad_token is None


def test_api_endpoints():
    client = TestClient(app)

    # 1. Health check
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["nodes_loaded"] == 10

    # 2. Get nodes
    res = client.get("/api/nodes")
    assert res.status_code == 200
    nodes = res.json()["nodes"]
    assert len(nodes) == 10
    # Passwords excluded by default
    assert "demo_password_plain" not in nodes[0]

    # 3. Connect node
    res = client.post("/api/nodes/node-01/connect", json={"password": "pass-node-01"})
    assert res.status_code == 200
    token = res.json()["token"]
    assert token != ""

    # 4. Send message
    res = client.post("/api/messages", json={
        "source_id": "node-01",
        "destination_id": "node-02",
        "payload": "Hello DTN mesh!",
        "priority": 1,
    })
    assert res.status_code == 200
    msg = res.json()
    assert msg["source_id"] == "node-01"
    assert msg["destination_id"] == "node-02"
    msg_id = msg["message_id"]

    # 5. Check route and decisions
    res = client.get(f"/api/messages/{msg_id}/route")
    assert res.status_code == 200
    route_info = res.json()
    assert route_info["message_id"] == msg_id
    assert "decisions" in route_info

    # 6. Query inbox
    res = client.get("/api/nodes/node-02/inbox")
    assert res.status_code == 200

    # 7. Step simulation
    res = client.post("/api/simulation/step", json={"step_delta_ms": 10000})
    assert res.status_code == 200

    # 8. Query metrics
    res = client.get("/api/metrics")
    assert res.status_code == 200
    metrics = res.json()
    assert metrics["total_messages"] >= 1
