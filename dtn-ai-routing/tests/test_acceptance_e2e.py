"""
Complete 12-Step Cross-Component Integration and Acceptance Test
Verifies the FastAPI backend, DTN simulation engine, client API contract parity,
and message lifecycle against the live Single Source of Truth.
"""

import sys
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.server import app, db, service


@pytest.fixture(scope="module")
def client():
    # Use TestClient with live app
    return TestClient(app)


def test_12_step_messaging_lifecycle(client):
    print("\n--- BEGIN 12-STEP INTEGRATION ACCEPTANCE AUDIT ---")
    admin_headers = {"X-Admin-Token": "dev-admin-secret-token"}

    # Reset simulation state to clean slate
    reset_res = client.post("/api/simulation/reset", headers=admin_headers)
    assert reset_res.status_code == 200

    # Step 1: Node fetch
    res1 = client.get("/api/nodes")
    assert res1.status_code == 200, f"Step 1 failed: {res1.text}"
    nodes_data = res1.json()
    assert "nodes" in nodes_data and len(nodes_data["nodes"]) >= 10
    assert "demo_password_plain" not in nodes_data["nodes"][0]
    print("[PASS] Step 1: Discovered nodes fetch (GET /api/nodes)")

    # Step 2: Authenticate node-01
    bad_auth = client.post("/api/nodes/node-01/connect", json={"password": "wrong_password"})
    assert bad_auth.status_code == 401
    res2 = client.post("/api/nodes/node-01/connect", json={"password": "pass-node-01"})
    assert res2.status_code == 200, f"Step 2 failed: {res2.text}"
    auth_data = res2.json()
    assert "token" in auth_data and len(auth_data["token"]) > 0
    assert auth_data["node_id"] == "node-01"
    token = auth_data["token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    print(f"[PASS] Step 2: Authenticated node-01 with bearer token (len={len(token)})")

    # Ensure clean contact state: activate node-01 to node-02
    client.post("/api/contacts", headers=admin_headers, json={"node_a": "node-01", "node_b": "node-02", "is_active": True})

    # Step 3: Submit message from node-01 to node-02 with client message_id
    run_id = uuid.uuid4().hex[:8]
    test_msg_id = f"test-msg-step3-{run_id}"
    res3 = client.post(
        "/api/messages",
        headers=auth_headers,
        json={
            "message_id": test_msg_id,
            "source_id": "node-01",
            "destination_id": "node-02",
            "payload": f"Emergency relay test payload - Step 3 - {run_id}",
            "priority": 1,
            "ttl_ms": 3600000,
        },
    )
    assert res3.status_code in (200, 201), f"Step 3 failed: {res3.text}"
    submitted = res3.json()
    assert submitted["message_id"] == test_msg_id
    print(f"[PASS] Step 3: Message submitted with client ID parity: {test_msg_id}")

    # Step 4: Confirm message ID and queueing in backend
    res4 = client.get(f"/api/messages/{test_msg_id}", headers=auth_headers)
    assert res4.status_code == 200, f"Step 4 failed: {res4.text}"
    msg_rec = res4.json()
    assert msg_rec["message_id"] == test_msg_id
    assert msg_rec["source_id"] == "node-01"
    assert msg_rec["destination_id"] == "node-02"
    print(f"[PASS] Step 4: Confirmed backend message storage and state: {msg_rec['status']}")

    # Step 5: Check route and decisions
    res5 = client.get(f"/api/messages/{test_msg_id}/route", headers=auth_headers)
    assert res5.status_code == 200, f"Step 5 failed: {res5.text}"
    route_rec = res5.json()
    assert route_rec["message_id"] == test_msg_id
    assert "route_path" in route_rec
    assert "decisions" in route_rec
    print(f"[PASS] Step 5: Route and decisions queried. Decisions recorded: {len(route_rec['decisions'])}")

    # Step 6: Advance simulation step and check forwarding
    res6 = client.post("/api/simulation/step", headers=admin_headers, json={"step_delta_ms": 10000})
    assert res6.status_code == 200, f"Step 6 failed: {res6.text}"
    res6_route = client.get(f"/api/messages/{test_msg_id}/route", headers=auth_headers)
    route_after_step = res6_route.json()
    assert route_after_step["status"] == "delivered", f"Expected delivered, got {route_after_step['status']}"
    assert "node-02" in route_after_step["route_path"]
    print(f"[PASS] Step 6: Simulation advanced 10s. Status delivered: route={route_after_step['route_path']}")

    # Step 7: Destination inbox check
    res7 = client.get("/api/nodes/node-02/inbox", headers=admin_headers)
    assert res7.status_code == 200, f"Step 7 failed: {res7.text}"
    inbox = res7.json()
    inbox_msg_ids = [m["message_id"] for m in inbox["messages"]]
    assert test_msg_id in inbox_msg_ids, f"{test_msg_id} not found in node-02 inbox: {inbox_msg_ids}"
    print(f"[PASS] Step 7: Verified message in destination node-02 inbox (total={inbox['count']})")

    # Step 8: Deactivate contact between node-01 and node-02
    res8 = client.post("/api/contacts", headers=admin_headers, json={"node_a": "node-01", "node_b": "node-02", "is_active": False})
    assert res8.status_code == 200, f"Step 8 failed: {res8.text}"
    contacts = client.get("/api/contacts").json()["contacts"]
    c12 = next((c for c in contacts if (c["node_a"] == "node-01" and c["node_b"] == "node-02") or (c["node_a"] == "node-02" and c["node_b"] == "node-01")), None)
    assert c12 is not None and c12["is_active"] == 0
    # Also disconnect node-01's other direct contacts (like cross-link to node-04) so it cannot relay to node-02
    client.post("/api/contacts", headers=admin_headers, json={"node_a": "node-01", "node_b": "node-04", "is_active": False})
    client.post("/api/contacts", headers=admin_headers, json={"node_a": "node-01", "node_b": "node-08", "is_active": False})
    client.post("/api/contacts", headers=admin_headers, json={"node_a": "node-01", "node_b": "node-10", "is_active": False})
    print("[PASS] Step 8: Contacts for node-01 deactivated (network partition simulated)")

    # Step 9: Send another message while disconnected -> verify remains pending/queued
    test_msg_id_disc = f"test-msg-step9-{run_id}"
    res9 = client.post(
        "/api/messages",
        headers=auth_headers,
        json={
            "message_id": test_msg_id_disc,
            "source_id": "node-01",
            "destination_id": "node-02",
            "payload": f"Payload sent during network partition - Step 9 - {run_id}",
            "priority": 1,
            "ttl_ms": 3600000,
        },
    )
    assert res9.status_code in (200, 201)
    # Advance time while contact is disconnected
    client.post("/api/simulation/step", headers=admin_headers, json={"step_delta_ms": 10000})
    res9_route = client.get(f"/api/messages/{test_msg_id_disc}/route", headers=auth_headers).json()
    assert res9_route["status"] == "queued"
    assert res9_route["current_holder"] == "node-01"
    print(f"[PASS] Step 9: Disconnected message safely held in node-01 buffer. Status: {res9_route['status']}")

    # Step 10: Reactivate contact -> advance simulation -> verify forwarding resumes without duplicates
    res10_contact = client.post("/api/contacts", headers=admin_headers, json={"node_a": "node-01", "node_b": "node-02", "is_active": True})
    assert res10_contact.status_code == 200
    res10_step = client.post("/api/simulation/step", headers=admin_headers, json={"step_delta_ms": 10000})
    assert res10_step.status_code == 200
    res10_route = client.get(f"/api/messages/{test_msg_id_disc}/route", headers=auth_headers).json()
    assert res10_route["status"] == "delivered"
    assert res10_route["current_holder"] == "node-02"
    # Verify no duplicate deliveries in inbox
    inbox2 = client.get("/api/nodes/node-02/inbox", headers=admin_headers).json()
    matching_inbox = [m for m in inbox2["messages"] if m["message_id"] == test_msg_id_disc]
    assert len(matching_inbox) == 1, f"Expected exactly 1 copy, found {len(matching_inbox)}"
    print(f"[PASS] Step 10: Contact restored, bundle forwarded to node-02. Zero duplicates verified.")

    # Step 11: Client message status querying
    res11 = client.get(f"/api/messages/{test_msg_id_disc}/route", headers=auth_headers)
    assert res11.status_code == 200
    data11 = res11.json()
    assert data11["status"] == "delivered"
    assert data11["hops"] >= 1
    assert "node-01" in data11["route_path"] and "node-02" in data11["route_path"]
    print(f"[PASS] Step 11: Client status query verified (status={data11['status']}, hops={data11['hops']})")

    # Step 12: Shortest route calculation across active topology
    res12_short = client.get("/api/routes/shortest?source_id=node-01&destination_id=node-02")
    assert res12_short.status_code == 200
    short_data = res12_short.json()
    assert short_data["feasible"] is True
    assert short_data["path"] == ["node-01", "node-02"]

    # Now simulate node-02 offline
    client.patch("/api/nodes/node-02", headers=admin_headers, json={"status": "offline"})
    res12_offline = client.get("/api/routes/shortest?source_id=node-01&destination_id=node-02")
    assert res12_offline.status_code == 200
    assert res12_offline.json()["feasible"] is False
    assert res12_offline.json()["status"] == "ENDPOINT_OFFLINE"

    # Restore node-02 online
    client.patch("/api/nodes/node-02", headers=admin_headers, json={"status": "online"})
    res12_online = client.get("/api/routes/shortest?source_id=node-01&destination_id=node-02")
    assert res12_online.status_code == 200
    assert res12_online.json()["feasible"] is True
    print("[PASS] Step 12: Shortest path routing computed & offline node isolation verified")

    print("\n--- ALL 12 INTEGRATION STEPS SUCCESSFULLY PASSED (100%) ---")

