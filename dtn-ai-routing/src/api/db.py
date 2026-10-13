"""
Database storage layer for the shared ABHIMANYU DTN Integrated Demo.
Provides thread-safe persistence using SQLite for:
- Virtual nodes and credentials (PBKDF2-HMAC hashed)
- Messages and full routing lifecycles
- Detailed routing decisions and packet events
- Simulation engine state and contact links
"""

import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH_DEFAULT = Path(__file__).resolve().parent.parent.parent / "data" / "demo_system.db"


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Generates a secure PBKDF2 hash with a random salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    )
    return key.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verifies password against stored salt and hash."""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, expected_hash)


class DemoDatabase:
    """Thread-safe SQLite storage for the shared DTN demonstration."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH_DEFAULT
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS demo_nodes (
                    node_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    demo_password_plain TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'online', -- online, offline, unavailable
                    buffer_capacity_bytes INTEGER NOT NULL DEFAULT 2000000,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS demo_sessions (
                    token TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (node_id) REFERENCES demo_nodes(node_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS demo_messages (
                    message_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    destination_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 1,
                    ttl_ms INTEGER NOT NULL DEFAULT 14400000,
                    creation_time_ms INTEGER NOT NULL,
                    expiry_time_ms INTEGER NOT NULL,
                    status TEXT NOT NULL, -- queued, forwarding, transferred_to_next_hop, delivered, expired, failed
                    hops INTEGER NOT NULL DEFAULT 0,
                    current_holder TEXT NOT NULL,
                    route_path_json TEXT NOT NULL DEFAULT '[]',
                    created_at_utc TEXT NOT NULL,
                    delivered_at_utc TEXT,
                    delivery_delay_ms INTEGER,
                    FOREIGN KEY (source_id) REFERENCES demo_nodes(node_id),
                    FOREIGN KEY (destination_id) REFERENCES demo_nodes(node_id)
                );

                CREATE TABLE IF NOT EXISTS demo_routing_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    time_ms INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    peer_id TEXT NOT NULL,
                    decision TEXT NOT NULL, -- FORWARD, HOLD, DROP
                    policy TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    features_json TEXT,
                    model_score REAL,
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS demo_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time_ms INTEGER NOT NULL,
                    event_type TEXT NOT NULL, -- GENERATED, FORWARD_ATTEMPT, FORWARD_SUCCESS, DELIVERED, BUFFER_DROP, EXPIRY
                    message_id TEXT NOT NULL,
                    node_a TEXT NOT NULL,
                    node_b TEXT NOT NULL,
                    details TEXT,
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS demo_contacts (
                    contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_a TEXT NOT NULL,
                    node_b TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    range_m REAL NOT NULL DEFAULT 50.0,
                    last_updated TEXT NOT NULL,
                    UNIQUE(node_a, node_b)
                );
            """)

    def initialize_default_nodes(self) -> None:
        """Seeds ten virtual demonstration nodes if they do not exist."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as count FROM demo_nodes")
        if cur.fetchone()["count"] >= 10:
            return

        now_utc = datetime.now(timezone.utc).isoformat()
        default_nodes = [
            ("node-01", "Alpha Gateway", "pass-node-01"),
            ("node-02", "Bravo Field Unit", "pass-node-02"),
            ("node-03", "Charlie Relay", "pass-node-03"),
            ("node-04", "Delta Scout", "pass-node-04"),
            ("node-05", "Echo Depot", "pass-node-05"),
            ("node-06", "Foxtrot Vehicle", "pass-node-06"),
            ("node-07", "Golf Sensor Hub", "pass-node-07"),
            ("node-08", "Hotel Outpost", "pass-node-08"),
            ("node-09", "India Patrol", "pass-node-09"),
            ("node-10", "Juliet HQ Base", "pass-node-10"),
        ]

        with conn:
            for node_id, display_name, plain_pwd in default_nodes:
                p_hash, p_salt = hash_password(plain_pwd)
                conn.execute("""
                    INSERT OR IGNORE INTO demo_nodes (
                        node_id, display_name, password_hash, password_salt,
                        demo_password_plain, status, buffer_capacity_bytes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'online', 2000000, ?, ?)
                """, (node_id, display_name, p_hash, p_salt, plain_pwd, now_utc, now_utc))

            # Initialize initial mesh contacts in a ring + cross topology
            node_ids = [n[0] for n in default_nodes]
            for i in range(len(node_ids)):
                peer1 = node_ids[(i + 1) % len(node_ids)]
                a, b = sorted([node_ids[i], peer1])
                conn.execute("""
                    INSERT OR IGNORE INTO demo_contacts (node_a, node_b, is_active, range_m, last_updated)
                    VALUES (?, ?, 1, 50.0, ?)
                """, (a, b, now_utc))
                
                # Cross link
                peer2 = node_ids[(i + 3) % len(node_ids)]
                a2, b2 = sorted([node_ids[i], peer2])
                conn.execute("""
                    INSERT OR IGNORE INTO demo_contacts (node_a, node_b, is_active, range_m, last_updated)
                    VALUES (?, ?, 1, 50.0, ?)
                """, (a2, b2, now_utc))

    def get_all_nodes(self, include_plain_passwords: bool = False) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM demo_nodes ORDER BY node_id ASC")
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if not include_plain_passwords:
                d.pop("password_hash", None)
                d.pop("password_salt", None)
                d.pop("demo_password_plain", None)
            result.append(d)
        return result

    def get_node(self, node_id: str, include_auth: bool = False) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM demo_nodes WHERE node_id = ?", (node_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if not include_auth:
            d.pop("password_hash", None)
            d.pop("password_salt", None)
            d.pop("demo_password_plain", None)
        return d

    def update_node(
        self,
        node_id: str,
        display_name: Optional[str] = None,
        status: Optional[str] = None,
        demo_password_plain: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        now_utc = datetime.now(timezone.utc).isoformat()
        node = self.get_node(node_id, include_auth=True)
        if not node:
            return None

        new_name = display_name if display_name is not None else node["display_name"]
        new_status = status if status is not None else node["status"]
        if demo_password_plain is not None and demo_password_plain.strip():
            p_hash, p_salt = hash_password(demo_password_plain)
            p_plain = demo_password_plain
        else:
            p_hash = node["password_hash"]
            p_salt = node["password_salt"]
            p_plain = node["demo_password_plain"]

        with conn:
            conn.execute("""
                UPDATE demo_nodes
                SET display_name = ?, status = ?, password_hash = ?,
                    password_salt = ?, demo_password_plain = ?, updated_at = ?
                WHERE node_id = ?
            """, (new_name, new_status, p_hash, p_salt, p_plain, now_utc, node_id))

        return self.get_node(node_id)

    def authenticate_node(self, node_id: str, password: str) -> Optional[str]:
        node = self.get_node(node_id, include_auth=True)
        if not node:
            return None
        if not verify_password(password, node["password_salt"], node["password_hash"]):
            return None

        token = secrets.token_urlsafe(32)
        now_utc = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT INTO demo_sessions (token, node_id, created_at, expires_at)
                VALUES (?, ?, ?, datetime('now', '+7 days'))
            """, (token, node_id, now_utc))
        return token

    def verify_session(self, token: str) -> Optional[str]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT node_id FROM demo_sessions
            WHERE token = ? AND expires_at > datetime('now')
        """, (token,))
        row = cur.fetchone()
        return row["node_id"] if row else None

    def store_message(self, message: Dict[str, Any]) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO demo_messages (
                    message_id, source_id, destination_id, payload,
                    size_bytes, priority, ttl_ms, creation_time_ms,
                    expiry_time_ms, status, hops, current_holder,
                    route_path_json, created_at_utc, delivered_at_utc,
                    delivery_delay_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message["message_id"],
                message["source_id"],
                message["destination_id"],
                message["payload"],
                message["size_bytes"],
                message.get("priority", 1),
                message.get("ttl_ms", 14400000),
                message["creation_time_ms"],
                message["expiry_time_ms"],
                message["status"],
                message.get("hops", 0),
                message["current_holder"],
                json.dumps(message.get("route_path", [])),
                message["created_at_utc"],
                message.get("delivered_at_utc"),
                message.get("delivery_delay_ms"),
            ))

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM demo_messages WHERE message_id = ?", (message_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["route_path"] = json.loads(d["route_path_json"])
        return d

    def get_all_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM demo_messages ORDER BY creation_time_ms DESC LIMIT ?", (limit,))
        result = []
        for r in cur.fetchall():
            d = dict(r)
            d["route_path"] = json.loads(d["route_path_json"])
            result.append(d)
        return result

    def get_node_inbox(self, node_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM demo_messages
            WHERE destination_id = ? AND status = 'delivered'
            ORDER BY creation_time_ms DESC
        """, (node_id,))
        result = []
        for r in cur.fetchall():
            d = dict(r)
            d["route_path"] = json.loads(d["route_path_json"])
            result.append(d)
        return result

    def get_node_outbox(self, node_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM demo_messages
            WHERE source_id = ?
            ORDER BY creation_time_ms DESC
        """, (node_id,))
        result = []
        for r in cur.fetchall():
            d = dict(r)
            d["route_path"] = json.loads(d["route_path_json"])
            result.append(d)
        return result

    def record_decision(
        self,
        message_id: str,
        time_ms: int,
        node_id: str,
        peer_id: str,
        decision: str,
        policy: str,
        reason: str,
        features: Optional[Dict[str, Any]] = None,
        model_score: Optional[float] = None,
    ) -> None:
        conn = self._get_connection()
        now_utc = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute("""
                INSERT INTO demo_routing_decisions (
                    message_id, time_ms, node_id, peer_id, decision,
                    policy, reason, features_json, model_score, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id, time_ms, node_id, peer_id, decision,
                policy, reason, json.dumps(features) if features else None,
                model_score, now_utc
            ))

    def get_message_decisions(self, message_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM demo_routing_decisions
            WHERE message_id = ?
            ORDER BY time_ms ASC, decision_id ASC
        """, (message_id,))
        result = []
        for r in cur.fetchall():
            d = dict(r)
            if d["features_json"]:
                d["features"] = json.loads(d["features_json"])
            result.append(d)
        return result

    def record_event(
        self,
        time_ms: int,
        event_type: str,
        message_id: str,
        node_a: str,
        node_b: str,
        details: str = "",
    ) -> None:
        conn = self._get_connection()
        now_utc = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute("""
                INSERT INTO demo_events (
                    time_ms, event_type, message_id, node_a, node_b, details, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (time_ms, event_type, message_id, node_a, node_b, details, now_utc))

    def get_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM demo_events ORDER BY time_ms DESC, event_id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def get_contacts(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM demo_contacts ORDER BY node_a ASC, node_b ASC")
        return [dict(r) for r in cur.fetchall()]

    def set_contact(self, node_a: str, node_b: str, is_active: bool) -> None:
        a, b = sorted([node_a, node_b])
        now_utc = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT INTO demo_contacts (node_a, node_b, is_active, range_m, last_updated)
                VALUES (?, ?, ?, 50.0, ?)
                ON CONFLICT(node_a, node_b) DO UPDATE SET
                    is_active = excluded.is_active,
                    last_updated = excluded.last_updated
            """, (a, b, 1 if is_active else 0, now_utc))
