"""
Integration Service linking FastAPI with the real DTN simulator and AI models.
Executes genuine store-carry-and-forward routing evaluations without mock algorithms.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import logging
import math
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import joblib
import numpy as np

# Ensure parent and src directories are in Python path
API_DIR = Path(__file__).resolve().parent
SRC_DIR = API_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dtn_simulator import (
    BaseRouter,
    DirectDeliveryRouter,
    DTNNode,
    EpidemicRouter,
    NodeBuffer,
    Packet,
    SimulationMetrics,
    TwoHopRelayRouter,
)

from ai_decision_engine import (
    DECISION_FEATURE_NAMES,
    DecisionTreeRouter,
    LogisticRegressionRouter,
    extract_decision_features,
)

from api.db import DemoDatabase

logger = logging.getLogger("dtn.service")


class DTNIntegratedService:
    """
    Central controller managing virtual nodes, contact schedule, and routing executions.
    Reuses the real DTNNode, Packet, and BaseRouter classes from dtn-ai-routing.
    """

    def __init__(self, db: DemoDatabase):
        self.db = db
        self.lock = threading.RLock()
        self.current_time_ms: int = 1_000_000  # Virtual clock starting at 1000s
        self.time_step_ms: int = 10_000        # 10s per simulation step
        self.is_running: bool = False
        self.active_policy: str = "decision_tree"  # decision_tree, epidemic, two_hop, direct_delivery

        # In-memory DTNNodes wrapping real buffers
        self.live_nodes: Dict[str, DTNNode] = {}
        
        # Load AI models if present
        self.dt_model = None
        self.dt_scaler = None
        self._load_ai_models()

        # Initialize nodes from DB
        self.db.initialize_default_nodes()
        self._sync_live_nodes_from_db()

    def _load_ai_models(self) -> None:
        model_path = PROJECT_ROOT / "models" / "stage5" / "decision_tree_model.joblib"
        scaler_path = PROJECT_ROOT / "models" / "stage5" / "feature_scaler.joblib"
        if model_path.exists():
            try:
                self.dt_model = joblib.load(model_path)
                logger.info(f"Loaded Stage 5.2 Decision Tree model from {model_path}")
            except Exception as e:
                logger.warning(f"Could not load decision tree model: {e}")
        if scaler_path.exists():
            try:
                self.dt_scaler = joblib.load(scaler_path)
                logger.info(f"Loaded Stage 5.2 Scaler from {scaler_path}")
            except Exception as e:
                logger.warning(f"Could not load scaler: {e}")

    def _get_router_class(self, policy_name: str) -> type:
        if policy_name == "decision_tree":
            return DecisionTreeRouter
        elif policy_name == "two_hop":
            return TwoHopRelayRouter
        elif policy_name == "direct_delivery":
            return DirectDeliveryRouter
        return EpidemicRouter

    def _sync_live_nodes_from_db(self) -> None:
        with self.lock:
            db_nodes = self.db.get_all_nodes(include_plain_passwords=True)
            router_cls = self._get_router_class(self.active_policy)
            for n in db_nodes:
                nid = n["node_id"]
                if nid not in self.live_nodes:
                    node = DTNNode(
                        node_id=nid,
                        buffer_capacity_bytes=n["buffer_capacity_bytes"],
                        router_class=router_cls,
                    )
                    if hasattr(node.router, "model") and self.dt_model is not None:
                        node.router.model = self.dt_model
                    if hasattr(node.router, "scaler") and self.dt_scaler is not None:
                        node.router.scaler = self.dt_scaler
                    self.live_nodes[nid] = node

    def set_routing_policy(self, policy: str) -> None:
        valid_policies = ["decision_tree", "epidemic", "two_hop", "direct_delivery"]
        if policy not in valid_policies:
            raise ValueError(f"Invalid policy {policy}. Must be one of {valid_policies}")
        with self.lock:
            self.active_policy = policy
            router_cls = self._get_router_class(policy)
            for node in self.live_nodes.values():
                node.router = router_cls(node.node_id)
                if hasattr(node.router, "model") and self.dt_model is not None:
                    node.router.model = self.dt_model
                if hasattr(node.router, "scaler") and self.dt_scaler is not None:
                    node.router.scaler = self.dt_scaler

    def send_message(
        self,
        source_id: str,
        destination_id: str,
        payload: str,
        priority: int = 1,
        ttl_ms: int = 14_400_000,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingests a user message, packs it into a real Packet, stores it in the source DTNNode buffer,
        and logs the creation event in the shared database.
        """
        if source_id == destination_id:
            raise ValueError("Source and destination nodes must be distinct.")

        with self.lock:
            self._sync_live_nodes_from_db()
            src_node = self.live_nodes.get(source_id)
            dst_node = self.live_nodes.get(destination_id)
            if not src_node:
                raise ValueError(f"Source node '{source_id}' does not exist.")
            if not dst_node:
                raise ValueError(f"Destination node '{destination_id}' does not exist.")

            now_utc = datetime.now(timezone.utc).isoformat()
            payload_bytes = payload.encode("utf-8")
            size_bytes = len(payload_bytes) + 78  # 78 bytes wire frame min
            msg_id = message_id.strip() if (message_id and message_id.strip()) else f"msg_{int(time.time() * 1000)}_{source_id}_{destination_id}"

            # Check for existing message to prevent duplicate creation
            existing = self.db.get_message(msg_id)
            if existing:
                return existing

            packet = Packet(
                packet_id=msg_id,
                source=source_id,
                destination=destination_id,
                size_bytes=size_bytes,
                priority=priority,
                creation_time_ms=self.current_time_ms,
                ttl_ms=ttl_ms,
            )

            # Insert packet into source node buffer
            stored, reason = src_node.receive_packet(packet, self.current_time_ms)
            status = "queued" if stored else "failed"

            msg_record = {
                "message_id": msg_id,
                "source_id": source_id,
                "destination_id": destination_id,
                "payload": payload,
                "size_bytes": size_bytes,
                "priority": priority,
                "ttl_ms": ttl_ms,
                "creation_time_ms": self.current_time_ms,
                "expiry_time_ms": packet.expiry_time_ms,
                "status": status,
                "hops": 0,
                "current_holder": source_id,
                "route_path": [source_id],
                "created_at_utc": now_utc,
                "delivered_at_utc": None,
                "delivery_delay_ms": None,
            }
            self.db.store_message(msg_record)

            self.db.record_event(
                time_ms=self.current_time_ms,
                event_type="GENERATED",
                message_id=msg_id,
                node_a=source_id,
                node_b=destination_id,
                details=f"Packet generated at source {source_id} (size: {size_bytes}B, status: {status})",
            )

            # Trigger an immediate forwarding evaluation across available contacts
            self.step_simulation(step_delta_ms=0)

            return self.db.get_message(msg_id) or msg_record

    def step_simulation(self, step_delta_ms: int = 10_000) -> Dict[str, Any]:
        """
        Advances the virtual clock and executes genuine decentralized routing evaluations
        across all active node contact links.
        """
        with self.lock:
            self.current_time_ms += step_delta_ms
            curr_t = self.current_time_ms

            # 1. Purge expired packets in all node buffers
            for node in self.live_nodes.values():
                expired = node.purge_expired_packets(curr_t)
                for exp_pkt in expired:
                    msg = self.db.get_message(exp_pkt.packet_id)
                    if msg and msg["status"] not in ["delivered", "expired"]:
                        msg["status"] = "expired"
                        self.db.store_message(msg)
                    self.db.record_event(
                        time_ms=curr_t,
                        event_type="EXPIRY",
                        message_id=exp_pkt.packet_id,
                        node_a=node.node_id,
                        node_b="",
                        details=f"Packet expired in buffer of {node.node_id} (TTL exceeded)",
                    )

            # 2. Query active contacts and online nodes
            active_contacts = [c for c in self.db.get_contacts() if c["is_active"] == 1]
            db_nodes = {n["node_id"]: n for n in self.db.get_all_nodes(include_plain_passwords=True)}

            transfers_completed = 0
            decisions_evaluated = 0

            # 3. For each active contact link, perform mutual routing evaluation
            for contact in active_contacts:
                na_id = contact["node_a"]
                nb_id = contact["node_b"]

                # Ensure both nodes are online
                node_a_info = db_nodes.get(na_id)
                node_b_info = db_nodes.get(nb_id)
                if not node_a_info or node_a_info["status"] != "online":
                    continue
                if not node_b_info or node_b_info["status"] != "online":
                    continue

                node_a = self.live_nodes.get(na_id)
                node_b = self.live_nodes.get(nb_id)
                if not node_a or not node_b:
                    continue

                # Record encounter
                node_a.record_encounter(nb_id, curr_t)
                node_b.record_encounter(na_id, curr_t)

                # Transfer A -> B
                xfer1, dec1 = self._evaluate_and_transfer_peer_pair(node_a, node_b, curr_t)
                # Transfer B -> A
                xfer2, dec2 = self._evaluate_and_transfer_peer_pair(node_b, node_a, curr_t)

                transfers_completed += (xfer1 + xfer2)
                decisions_evaluated += (dec1 + dec2)

            return {
                "current_time_ms": self.current_time_ms,
                "active_contacts": len(active_contacts),
                "decisions_evaluated": decisions_evaluated,
                "transfers_completed": transfers_completed,
            }

    def _evaluate_and_transfer_peer_pair(
        self,
        sender: DTNNode,
        receiver: DTNNode,
        current_time_ms: int,
    ) -> Tuple[int, int]:
        """
        Executes routing decisions from sender to receiver.
        Uses the sender's configured router to inspect its buffer packets.
        """
        transfers = 0
        decisions_count = 0

        # Snapshot of packets currently in sender's buffer
        candidate_packets = sender.buffer.packets_list
        if not candidate_packets:
            return 0, 0

        # Run router selection
        router = sender.router
        selected_for_forwarding = router.select_packets_to_forward(
            current_time_ms=current_time_ms,
            peer_id=receiver.node_id,
            peer_seen_packet_ids=receiver.seen_packet_ids,
            buffer=sender.buffer,
        )

        selected_pids = {p.packet_id for p in selected_for_forwarding}

        for pkt in candidate_packets:
            decisions_count += 1
            is_selected = pkt.packet_id in selected_pids

            # Log decision details
            reason = ""
            decision_type = "FORWARD" if is_selected else "HOLD"
            features = None
            score = None

            if pkt.destination == receiver.node_id:
                reason = "Direct destination encounter prioritized"
            elif receiver.node_id in pkt.path or pkt.packet_id in receiver.seen_packet_ids:
                reason = "Receiver already holds or has seen packet"
                decision_type = "HOLD"
            elif self.active_policy == "decision_tree" and self.dt_model is not None:
                # Extract features for record
                xfer_ms = 50 + math.ceil((pkt.size_bytes * 1000.0) / 250_000.0)
                feats = extract_decision_features(
                    packet=pkt,
                    current_node=sender.node_id,
                    peer_node=receiver.node_id,
                    current_time_ms=current_time_ms,
                    contact_start_ms=current_time_ms,
                    buffer=sender.buffer,
                    transfer_duration_ms=xfer_ms,
                    peer_encounter_counts=getattr(sender, "encounter_counts", {}),
                    peer_historical_avg_durations_ms={},
                )
                features = feats
                if is_selected:
                    reason = "Decision Tree approved relay (causal features satisfied)"
                    score = 1.0
                else:
                    reason = "Decision Tree rejected relay (policy threshold not met)"
                    score = 0.0
            elif self.active_policy == "two_hop":
                if is_selected:
                    reason = "Two-Hop source replication permitted"
                else:
                    reason = "Two-Hop relay forwarding restricted to direct destination"
            elif self.active_policy == "direct_delivery":
                reason = "Direct Delivery only permits final destination transfer"
            else:
                reason = "Epidemic multi-copy replication" if is_selected else "Epidemic duplicate suppression"

            self.db.record_decision(
                message_id=pkt.packet_id,
                time_ms=current_time_ms,
                node_id=sender.node_id,
                peer_id=receiver.node_id,
                decision=decision_type,
                policy=self.active_policy,
                reason=reason,
                features=features,
                model_score=score,
            )

            if is_selected:
                # Execute packet transfer
                replica = pkt.copy()
                replica.hops += 1
                replica.path.append(receiver.node_id)

                self.db.record_event(
                    time_ms=current_time_ms,
                    event_type="FORWARD_ATTEMPT",
                    message_id=pkt.packet_id,
                    node_a=sender.node_id,
                    node_b=receiver.node_id,
                    details=f"Forwarding bundle from {sender.node_id} to {receiver.node_id} ({self.active_policy})",
                )

                success, outcome = receiver.receive_packet(replica, current_time_ms)
                if success:
                    transfers += 1
                    msg = self.db.get_message(pkt.packet_id)
                    if msg:
                        msg["hops"] = replica.hops
                        msg["current_holder"] = receiver.node_id
                        path = msg.get("route_path", [])
                        if receiver.node_id not in path:
                            path.append(receiver.node_id)
                        msg["route_path"] = path

                        if outcome == "DELIVERED":
                            msg["status"] = "delivered"
                            msg["delivered_at_utc"] = datetime.now(timezone.utc).isoformat()
                            msg["delivery_delay_ms"] = current_time_ms - pkt.creation_time_ms
                            self.db.record_event(
                                time_ms=current_time_ms,
                                event_type="DELIVERED",
                                message_id=pkt.packet_id,
                                node_a=sender.node_id,
                                node_b=receiver.node_id,
                                details=f"Bundle successfully delivered to destination {receiver.node_id}! Delay: {msg['delivery_delay_ms']}ms",
                            )
                        else:
                            msg["status"] = "transferred_to_next_hop"
                            self.db.record_event(
                                time_ms=current_time_ms,
                                event_type="FORWARD_SUCCESS",
                                message_id=pkt.packet_id,
                                node_a=sender.node_id,
                                node_b=receiver.node_id,
                                details=f"Bundle received and buffered at relay {receiver.node_id}",
                            )
                        self.db.store_message(msg)

        return transfers, decisions_count

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Calculates live metrics from the shared database."""
        all_msgs = self.db.get_all_messages(limit=1000)
        total = len(all_msgs)
        delivered = sum(1 for m in all_msgs if m["status"] == "delivered")
        pending = sum(1 for m in all_msgs if m["status"] in ["queued", "transferred_to_next_hop", "forwarding"])
        expired = sum(1 for m in all_msgs if m["status"] == "expired")
        failed = sum(1 for m in all_msgs if m["status"] == "failed")

        delays = [m["delivery_delay_ms"] for m in all_msgs if m.get("delivery_delay_ms") is not None]
        avg_delay = round(sum(delays) / len(delays), 1) if delays else 0.0

        events = self.db.get_events(limit=1000)
        fwd_attempts = sum(1 for e in events if e["event_type"] == "FORWARD_ATTEMPT")
        fwd_success = sum(1 for e in events if e["event_type"] in ["FORWARD_SUCCESS", "DELIVERED"])

        pdr = round(delivered / total, 4) if total > 0 else 0.0
        overhead = round((fwd_success - delivered) / delivered, 4) if delivered > 0 else 0.0

        return {
            "total_messages": total,
            "delivered": delivered,
            "pending": pending,
            "expired": expired,
            "failed": failed,
            "packet_delivery_ratio": pdr,
            "overhead_ratio": overhead,
            "average_delay_ms": avg_delay,
            "forwarding_attempts": fwd_attempts,
            "successful_transfers": fwd_success,
            "active_policy": self.active_policy,
            "current_time_ms": self.current_time_ms,
        }

    def calculate_shortest_path(self, source_id: str, destination_id: str) -> Dict[str, Any]:
        """
        Calculates the shortest valid path (fewest hops) across currently active contacts
        and online nodes using Breadth-First Search (BFS).
        """
        if source_id == destination_id:
            return {
                "source": source_id,
                "destination": destination_id,
                "path": [source_id],
                "hops": 0,
                "status": "SAME_NODE",
                "feasible": True,
            }

        with self.lock:
            # Query active contacts and online nodes
            active_contacts = [c for c in self.db.get_contacts() if c["is_active"] == 1]
            db_nodes = {n["node_id"]: n for n in self.db.get_all_nodes(include_plain_passwords=True)}

            # Build adjacency list considering ONLY online nodes
            adj: Dict[str, List[str]] = collections.defaultdict(list)
            for c in active_contacts:
                u, v = c["node_a"], c["node_b"]
                u_online = (u in db_nodes and db_nodes[u]["status"] == "online")
                v_online = (v in db_nodes and db_nodes[v]["status"] == "online")
                if u_online and v_online:
                    adj[u].append(v)
                    adj[v].append(u)

            # Check endpoints availability
            src_online = (source_id in db_nodes and db_nodes[source_id]["status"] == "online")
            dst_online = (destination_id in db_nodes and db_nodes[destination_id]["status"] == "online")

            if not src_online or not dst_online:
                return {
                    "source": source_id,
                    "destination": destination_id,
                    "path": [],
                    "hops": 0,
                    "status": "ENDPOINT_OFFLINE",
                    "feasible": False,
                }

            # BFS traversal
            queue = collections.deque([[source_id]])
            visited = {source_id}

            while queue:
                current_path = queue.popleft()
                node = current_path[-1]

                if node == destination_id:
                    hops = len(current_path) - 1
                    return {
                        "source": source_id,
                        "destination": destination_id,
                        "path": current_path,
                        "hops": hops,
                        "status": "VALID_ROUTE",
                        "feasible": True,
                    }

                for neighbor in adj.get(node, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(current_path + [neighbor])

            return {
                "source": source_id,
                "destination": destination_id,
                "path": [],
                "hops": 0,
                "status": "NO_VALID_ROUTE",
                "feasible": False,
            }

