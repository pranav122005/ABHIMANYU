"""
FastAPI application serving the single source of truth for DTN nodes,
messages, routing events, and simulation state.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure src in sys.path
import sys
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.db import DemoDatabase
from api.service import DTNIntegratedService

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dtn.api")

app = FastAPI(
    title="ABHIMANYU DTN Integrated Demo API",
    description="Single Source of Truth connecting Streamlit Monitoring Dashboard and Flutter Messenger Client to the Real DTN AI Routing Simulator",
    version="2.0.0",
)

# Enable CORS for Flutter web / desktop / local dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize storage and integrated service
db = DemoDatabase()
service = DTNIntegratedService(db)


# -----------------------------------------------------------------------------
# Pydantic Request/Response Models
# -----------------------------------------------------------------------------

class NodeUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    status: Optional[str] = Field(None, description="online, offline, or unavailable")
    demo_password: Optional[str] = None

class NodeLoginRequest(BaseModel):
    password: str

class NodeLoginResponse(BaseModel):
    token: str
    node_id: str
    display_name: str
    status: str

class MessageCreateRequest(BaseModel):
    source_id: str
    destination_id: str
    payload: str
    priority: int = 1
    ttl_ms: int = 14400000

class SimulationStepRequest(BaseModel):
    step_delta_ms: int = 10000

class PolicyChangeRequest(BaseModel):
    policy: str = Field(..., description="decision_tree, epidemic, two_hop, direct_delivery")

class ContactUpdateRequest(BaseModel):
    node_a: str
    node_b: str
    is_active: bool


# -----------------------------------------------------------------------------
# Authentication Dependency
# -----------------------------------------------------------------------------

def get_current_node_id(authorization: Optional[str] = Header(None)) -> str:
    """Validates bearer token against demo session store."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing.",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format. Expected 'Bearer <token>'.",
        )
    token = parts[1]
    node_id = db.verify_session(token)
    if not node_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired demonstration session token.",
        )
    return node_id


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "ABHIMANYU DTN Integrated Demo API",
        "active_policy": service.active_policy,
        "virtual_time_ms": service.current_time_ms,
        "nodes_loaded": len(service.live_nodes),
        "ai_model_loaded": service.dt_model is not None,
    }

@app.get("/api/nodes")
def get_nodes(include_admin: bool = Query(False, description="Include plain demonstration passwords for admin")):
    nodes = db.get_all_nodes(include_plain_passwords=include_admin)
    # Augment with live buffer telemetry from DTNNodes
    for n in nodes:
        live = service.live_nodes.get(n["node_id"])
        if live:
            n["buffer_utilization"] = live.buffer_utilization
            n["stored_packet_count"] = live.stored_packet_count
            n["stored_bytes"] = live.stored_bytes
            n["available_buffer_bytes"] = live.available_buffer_bytes
    return {"nodes": nodes}

@app.get("/api/nodes/{node_id}")
def get_single_node(node_id: str, include_admin: bool = Query(False)):
    node = db.get_node(node_id, include_auth=include_admin)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    live = service.live_nodes.get(node_id)
    if live:
        node["buffer_utilization"] = live.buffer_utilization
        node["stored_packet_count"] = live.stored_packet_count
        node["stored_bytes"] = live.stored_bytes
        node["available_buffer_bytes"] = live.available_buffer_bytes
    return node

@app.patch("/api/nodes/{node_id}")
def update_node(node_id: str, req: NodeUpdateRequest):
    updated = db.update_node(
        node_id=node_id,
        display_name=req.display_name,
        status=req.status,
        demo_password_plain=req.demo_password,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    service._sync_live_nodes_from_db()
    return updated

@app.post("/api/nodes/{node_id}/connect", response_model=NodeLoginResponse)
def connect_node(node_id: str, req: NodeLoginRequest):
    token = db.authenticate_node(node_id, req.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node ID or demonstration password.",
        )
    node_data = db.get_node(node_id)
    return {
        "token": token,
        "node_id": node_id,
        "display_name": node_data["display_name"],
        "status": node_data["status"],
    }

@app.get("/api/nodes/{node_id}/inbox")
def get_node_inbox(node_id: str):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    inbox = db.get_node_inbox(node_id)
    return {"node_id": node_id, "messages": inbox, "count": len(inbox)}

@app.get("/api/nodes/{node_id}/outbox")
def get_node_outbox(node_id: str):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    outbox = db.get_node_outbox(node_id)
    return {"node_id": node_id, "messages": outbox, "count": len(outbox)}

@app.post("/api/messages")
def create_message(req: MessageCreateRequest):
    try:
        msg = service.send_message(
            source_id=req.source_id,
            destination_id=req.destination_id,
            payload=req.payload,
            priority=req.priority,
            ttl_ms=req.ttl_ms,
        )
        return msg
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/messages")
def list_messages(limit: int = Query(100, ge=1, le=1000)):
    return {"messages": db.get_all_messages(limit=limit)}

@app.get("/api/messages/{message_id}")
def get_message(message_id: str):
    msg = db.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail=f"Message '{message_id}' not found.")
    return msg

@app.get("/api/messages/{message_id}/route")
def get_message_route(message_id: str):
    msg = db.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail=f"Message '{message_id}' not found.")
    decisions = db.get_message_decisions(message_id)
    return {
        "message_id": message_id,
        "source": msg["source_id"],
        "destination": msg["destination_id"],
        "status": msg["status"],
        "hops": msg["hops"],
        "current_holder": msg["current_holder"],
        "route_path": msg["route_path"],
        "delivery_delay_ms": msg.get("delivery_delay_ms"),
        "decisions": decisions,
    }

@app.get("/api/events")
def list_events(limit: int = Query(100, ge=1, le=1000)):
    return {"events": db.get_events(limit=limit)}

@app.get("/api/metrics")
def get_metrics():
    return service.get_metrics_summary()

@app.get("/api/contacts")
def get_contacts():
    return {"contacts": db.get_contacts()}

@app.post("/api/contacts")
def update_contact(req: ContactUpdateRequest):
    db.set_contact(req.node_a, req.node_b, req.is_active)
    # Trigger an immediate step to evaluate any newly opened contacts
    res = service.step_simulation(step_delta_ms=0)
    return {"status": "updated", "contact": req.dict(), "step_result": res}

@app.get("/api/simulation/state")
def get_simulation_state():
    return {
        "current_time_ms": service.current_time_ms,
        "is_running": service.is_running,
        "active_policy": service.active_policy,
        "step_delta_ms": service.time_step_ms,
        "node_count": len(service.live_nodes),
    }

@app.post("/api/simulation/step")
def step_simulation(req: SimulationStepRequest = SimulationStepRequest()):
    result = service.step_simulation(step_delta_ms=req.step_delta_ms)
    return result

@app.post("/api/simulation/policy")
def set_policy(req: PolicyChangeRequest):
    try:
        service.set_routing_policy(req.policy)
        return {"status": "updated", "active_policy": service.active_policy}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/simulation/reset")
def reset_simulation():
    # Safely resets queues and messages in the demo database without deleting datasets or code
    with service.lock:
        conn = db._get_connection()
        with conn:
            conn.execute("DELETE FROM demo_messages")
            conn.execute("DELETE FROM demo_routing_decisions")
            conn.execute("DELETE FROM demo_events")
        # Clear live node buffers
        for n in service.live_nodes.values():
            n.buffer = NodeBuffer(capacity_bytes=2_000_000)
            n.seen_packet_ids.clear()
            n.delivered_packets.clear()
        service.current_time_ms = 1_000_000
    return {"status": "reset_completed", "current_time_ms": service.current_time_ms}
