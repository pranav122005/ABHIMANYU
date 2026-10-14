"""
FastAPI application serving the single source of truth for DTN nodes,
messages, routing events, and simulation state.
Hardened with role-based authentication, admin token enforcement,
and production-ready configuration.
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure src in sys.path
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dtn_simulator import NodeBuffer
from api.db import DemoDatabase, get_default_db_path
from api.service import DTNIntegratedService

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dtn.api")

# -----------------------------------------------------------------------------
# Environment & Security Configuration
# -----------------------------------------------------------------------------
DTN_ENV = os.environ.get("DTN_ENV", "development").strip().lower()
DTN_ADMIN_TOKEN = os.environ.get("DTN_ADMIN_TOKEN", "").strip()

if DTN_ENV == "production":
    if not DTN_ADMIN_TOKEN or len(DTN_ADMIN_TOKEN) < 16:
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: "
            "In production mode (DTN_ENV=production), DTN_ADMIN_TOKEN must be set to a secure secret "
            "of at least 16 characters. Refusing to start with insecure credentials."
        )
    logger.info("ABHIMANYU DTN API starting in PRODUCTION mode with strict authorization.")
else:
    if not DTN_ADMIN_TOKEN:
        DTN_ADMIN_TOKEN = "dev-admin-secret-token"
        logger.warning(
            "DTN_ADMIN_TOKEN not set; using development fallback 'dev-admin-secret-token'. "
            "Configure DTN_ADMIN_TOKEN and DTN_ENV=production before deploying publicly."
        )
    else:
        logger.info("ABHIMANYU DTN API starting in DEVELOPMENT mode with configured DTN_ADMIN_TOKEN.")

app = FastAPI(
    title="ABHIMANYU DTN Integrated API",
    description="Single Source of Truth connecting Monitoring Dashboard and Flutter Messenger to the Real DTN AI Routing Simulator",
    version="2.1.0",
)

# -----------------------------------------------------------------------------
# Explicit CORS Configuration
# -----------------------------------------------------------------------------
cors_origins_env = os.environ.get("DTN_CORS_ORIGINS")
if cors_origins_env and cors_origins_env.strip():
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
elif DTN_ENV == "production":
    # In production, require explicit browser origins
    allowed_origins = []
else:
    allowed_origins = [
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True if allowed_origins else False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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
    message_id: Optional[str] = None
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
# Authentication & Authorization Dependencies
# -----------------------------------------------------------------------------

def extract_token_from_request(
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> Optional[str]:
    """Extracts bearer token from Authorization header or X-Admin-Token."""
    if x_admin_token and x_admin_token.strip():
        return x_admin_token.strip()
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def require_admin(
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> bool:
    """Enforces administrator credentials on protected endpoints."""
    token = extract_token_from_request(authorization, x_admin_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator authorization required. Provide 'Authorization: Bearer <admin_token>' or 'X-Admin-Token'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not secrets.compare_digest(token, DTN_ADMIN_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid administrator credentials.",
        )
    return True


def get_auth_actor(
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> Dict[str, Any]:
    """
    Identifies the authenticated caller as either:
    - Administrator: {"is_admin": True, "node_id": None}
    - Authenticated Node: {"is_admin": False, "node_id": "<node_id>"}
    Raises 401 if missing, invalid, or expired.
    """
    token = extract_token_from_request(authorization, x_admin_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide 'Authorization: Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if admin token
    if secrets.compare_digest(token, DTN_ADMIN_TOKEN):
        return {"is_admin": True, "node_id": None}

    # Check if valid node session
    node_id = db.verify_session(token)
    if node_id:
        return {"is_admin": False, "node_id": node_id}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# -----------------------------------------------------------------------------
# Public & Node Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """Public health verification."""
    return {
        "status": "healthy",
        "service": "ABHIMANYU DTN Integrated API",
        "environment": DTN_ENV,
        "active_policy": service.active_policy,
        "virtual_time_ms": service.current_time_ms,
        "nodes_loaded": len(service.live_nodes),
        "ai_model_loaded": service.dt_model is not None,
    }

@app.get("/api/nodes")
def get_nodes(
    include_admin: bool = Query(False, description="Include administrative information (requires admin token)"),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    """
    Returns public node listings without credentials.
    In development, include_admin requires admin token.
    In production, credentials are never exposed regardless of role.
    """
    if include_admin:
        token = extract_token_from_request(authorization, x_admin_token)
        if not token or not secrets.compare_digest(token, DTN_ADMIN_TOKEN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin token required to query administrative node details.",
            )
        nodes = db.get_all_nodes(include_plain_passwords=True)
    else:
        nodes = db.get_all_nodes(include_plain_passwords=False)

    for n in nodes:
        live = service.live_nodes.get(n["node_id"])
        if live:
            n["buffer_utilization"] = live.buffer_utilization
            n["stored_packet_count"] = live.stored_packet_count
            n["stored_bytes"] = live.stored_bytes
            n["available_buffer_bytes"] = live.available_buffer_bytes
    return {"nodes": nodes}

@app.get("/api/nodes/{node_id}")
def get_single_node(
    node_id: str,
    include_admin: bool = Query(False),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    """Returns safe single node telemetry."""
    if include_admin:
        token = extract_token_from_request(authorization, x_admin_token)
        if not token or not secrets.compare_digest(token, DTN_ADMIN_TOKEN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin token required to query administrative node details.",
            )
        node = db.get_node(node_id, include_auth=True)
    else:
        node = db.get_node(node_id, include_auth=False)

    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    live = service.live_nodes.get(node_id)
    if live:
        node["buffer_utilization"] = live.buffer_utilization
        node["stored_packet_count"] = live.stored_packet_count
        node["stored_bytes"] = live.stored_bytes
        node["available_buffer_bytes"] = live.available_buffer_bytes
    return node

@app.post("/api/nodes/{node_id}/connect", response_model=NodeLoginResponse)
def connect_node(node_id: str, req: NodeLoginRequest):
    """Authenticates node credentials and returns bearer session token."""
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
def get_node_inbox(
    node_id: str,
    actor: Dict[str, Any] = Depends(get_auth_actor),
):
    """Retrieves node inbox. Restricted to node owner or administrator."""
    if not actor["is_admin"] and actor["node_id"] != node_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Authenticated node '{actor['node_id']}' cannot access inbox of '{node_id}'.",
        )
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    inbox = db.get_node_inbox(node_id)
    return {"node_id": node_id, "messages": inbox, "count": len(inbox)}

@app.get("/api/nodes/{node_id}/outbox")
def get_node_outbox(
    node_id: str,
    actor: Dict[str, Any] = Depends(get_auth_actor),
):
    """Retrieves node outbox. Restricted to node owner or administrator."""
    if not actor["is_admin"] and actor["node_id"] != node_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Authenticated node '{actor['node_id']}' cannot access outbox of '{node_id}'.",
        )
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    outbox = db.get_node_outbox(node_id)
    return {"node_id": node_id, "messages": outbox, "count": len(outbox)}

@app.post("/api/messages")
def create_message(
    req: MessageCreateRequest,
    actor: Dict[str, Any] = Depends(get_auth_actor),
):
    """
    Submits a new DTN bundle.
    A node session may submit messages only where source_id equals its authenticated identity.
    Administrators may dispatch messages on behalf of any node.
    """
    if not actor["is_admin"] and actor["node_id"] != req.source_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Authenticated node '{actor['node_id']}' cannot send messages as source '{req.source_id}'.",
        )
    try:
        msg = service.send_message(
            source_id=req.source_id,
            destination_id=req.destination_id,
            payload=req.payload,
            priority=req.priority,
            ttl_ms=req.ttl_ms,
            message_id=req.message_id,
        )
        return msg
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/messages/{message_id}")
def get_message(
    message_id: str,
    actor: Dict[str, Any] = Depends(get_auth_actor),
):
    """Access to message details is restricted to sender, recipient, or administrator."""
    msg = db.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail=f"Message '{message_id}' not found.")
    if not actor["is_admin"] and actor["node_id"] not in (msg["source_id"], msg["destination_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only message participants or administrators can view message details.",
        )
    return msg

@app.get("/api/messages/{message_id}/route")
def get_message_route(
    message_id: str,
    actor: Dict[str, Any] = Depends(get_auth_actor),
):
    """Access to route trajectory and decisions is restricted to sender, recipient, or administrator."""
    msg = db.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail=f"Message '{message_id}' not found.")
    if not actor["is_admin"] and actor["node_id"] not in (msg["source_id"], msg["destination_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only message participants or administrators can view route telemetry.",
        )
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

@app.get("/api/routes/shortest")
def get_shortest_route(source_id: str = Query(...), destination_id: str = Query(...)):
    """Calculates the shortest valid path between source and destination using active contacts and online nodes."""
    return service.calculate_shortest_path(source_id=source_id, destination_id=destination_id)

@app.get("/api/contacts")
def get_contacts():
    """Read-only view of active geometric and demonstration contact links."""
    return {"contacts": db.get_contacts()}

@app.get("/api/metrics")
def get_metrics():
    """Public KPI metrics summary."""
    return service.get_metrics_summary()

@app.get("/api/simulation/state")
def get_simulation_state():
    """Public read-only simulation clock state."""
    return {
        "current_time_ms": service.current_time_ms,
        "is_running": service.is_running,
        "active_policy": service.active_policy,
        "step_delta_ms": service.time_step_ms,
        "node_count": len(service.live_nodes),
    }


# -----------------------------------------------------------------------------
# Protected Administrative Endpoints (Admin Token Required)
# -----------------------------------------------------------------------------

@app.patch("/api/nodes/{node_id}")
def update_node(
    node_id: str,
    req: NodeUpdateRequest,
    _admin: bool = Depends(require_admin),
):
    """Administrative node update (name, status, or password)."""
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

@app.get("/api/messages")
def list_messages(
    limit: int = Query(100, ge=1, le=1000),
    _admin: bool = Depends(require_admin),
):
    """Network-wide bundle inspection (admin only)."""
    return {"messages": db.get_all_messages(limit=limit)}

@app.get("/api/events")
def list_events(
    limit: int = Query(100, ge=1, le=1000),
    _admin: bool = Depends(require_admin),
):
    """Routing event log inspection (admin only)."""
    return {"events": db.get_events(limit=limit)}

@app.post("/api/contacts")
def update_contact(
    req: ContactUpdateRequest,
    _admin: bool = Depends(require_admin),
):
    """Administrative contact link toggle."""
    db.set_contact(req.node_a, req.node_b, req.is_active)
    res = service.step_simulation(step_delta_ms=0)
    return {"status": "updated", "contact": req.model_dump(), "step_result": res}

@app.post("/api/simulation/step")
def step_simulation(
    req: SimulationStepRequest = SimulationStepRequest(),
    _admin: bool = Depends(require_admin),
):
    """Advances virtual clock and triggers decentralized forwarding (admin only)."""
    result = service.step_simulation(step_delta_ms=req.step_delta_ms)
    return result

@app.post("/api/simulation/policy")
def set_policy(
    req: PolicyChangeRequest,
    _admin: bool = Depends(require_admin),
):
    """Changes active decentralized routing policy (admin only)."""
    try:
        service.set_routing_policy(req.policy)
        return {"status": "updated", "active_policy": service.active_policy}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/simulation/reset")
def reset_simulation(
    _admin: bool = Depends(require_admin),
):
    """Resets message queues and event logs without deleting models or code (admin only)."""
    with service.lock:
        conn = db._get_connection()
        with conn:
            conn.execute("DELETE FROM demo_messages")
            conn.execute("DELETE FROM demo_routing_decisions")
            conn.execute("DELETE FROM demo_events")
        for n in service.live_nodes.values():
            n.buffer = NodeBuffer(capacity_bytes=2_000_000)
            n.seen_packet_ids.clear()
            n.delivered_packets.clear()
        service.current_time_ms = 1_000_000
    return {"status": "reset_completed", "current_time_ms": service.current_time_ms}
