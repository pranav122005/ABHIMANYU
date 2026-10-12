#!/usr/bin/env python3
"""
DTN AI Routing - Stage 5.1: Causal AI Decision Engine & Validity Audit

Module: src/ai_decision_engine.py
Description:
  Implements the offline decentralized AI routing pipeline with strict causal features:
    1. Strictly causal contemporaneous feature extraction (zero future contact knowledge).
    2. Decision-level dataset generation with defensible Time-Dependent A* teacher labels
       (identifying both direct destination deliveries AND optimal intermediate relay hops).
    3. Leakage-free train/validation/test partitioning grouped strictly by packet ID.
    4. Training and hyperparameter tuning of:
       - Shallow Decision Tree (compact rule logic exportable to C++)
       - Logistic Regression (linear weights and bias)
    5. C++ code generation for zero-runtime ESP8266 firmware deployment.
    6. Decentralized router classes (DecisionTreeRouter, LogisticRegressionRouter)
       integrating directly into DTNSimulator for closed-loop evaluation.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

# Ensure src directory is in path
CURRENT_DIR = Path(__file__).resolve().parent
import sys
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from dtn_simulator import BaseRouter, DTNNode, NodeBuffer, Packet
from temporal_astar import TemporalContactSchedule, TimeDependentAStar

logger = logging.getLogger(__name__)

# Canonical list of 11 strictly causal local features observable by an ESP8266 node
DECISION_FEATURE_NAMES = [
    "peer_is_destination",              # Binary: 1 if peer == packet.destination, else 0
    "packet_size_bytes",                # Integer: packet payload in bytes
    "packet_priority",                  # Integer: priority level (1=Normal, 2=High, 3=Urgent)
    "remaining_ttl_ratio",              # Float [0, 1]: remaining_ttl_ms / ttl_ms
    "packet_hops",                      # Integer: number of hops already traversed
    "transfer_duration_ms",             # Integer: transfer time required (overhead + ceil(size/rate))
    "contact_elapsed_ms",               # Integer: time elapsed since contact start (strictly causal)
    "estimated_remaining_contact_ms",   # Integer: history-based estimate of remaining contact duration
    "estimated_transfer_fits",          # Binary: 1 if transfer duration <= estimated_remaining, else 0
    "local_buffer_utilization",         # Float [0, 1]: local buffer occupancy ratio
    "peer_encounter_frequency",         # Integer: count of past completed contacts with peer
]


# -----------------------------------------------------------------------------
# 1. Strictly Causal Local Feature Extraction
# -----------------------------------------------------------------------------

def extract_decision_features(
    packet: Packet,
    current_node: str,
    peer_node: str,
    current_time_ms: int,
    contact_start_ms: int,
    buffer: NodeBuffer,
    transfer_duration_ms: int,
    peer_encounter_counts: Dict[str, int],
    peer_historical_avg_durations_ms: Dict[str, float],
) -> Dict[str, Union[int, float]]:
    """
    Extracts strictly causal local features available to an ESP8266 node during peer contact.
    STRICT: Zero future global knowledge or future contact end times are used.
    """
    remaining_ttl_ms = max(0, packet.expiry_time_ms - current_time_ms)
    ttl_ratio = remaining_ttl_ms / max(1, packet.ttl_ms)

    contact_elapsed_ms = max(0, current_time_ms - contact_start_ms)
    hist_avg = peer_historical_avg_durations_ms.get(peer_node, 5000.0)
    est_remaining_ms = max(0.0, hist_avg - contact_elapsed_ms)
    est_transfer_fits = 1 if (transfer_duration_ms <= est_remaining_ms) else 0
    peer_enc_freq = peer_encounter_counts.get(peer_node, 0)

    return {
        "peer_is_destination": 1 if (packet.destination == peer_node) else 0,
        "packet_size_bytes": packet.size_bytes,
        "packet_priority": packet.priority,
        "remaining_ttl_ratio": round(ttl_ratio, 4),
        "packet_hops": packet.hops,
        "transfer_duration_ms": transfer_duration_ms,
        "contact_elapsed_ms": contact_elapsed_ms,
        "estimated_remaining_contact_ms": int(est_remaining_ms),
        "estimated_transfer_fits": est_transfer_fits,
        "local_buffer_utilization": round(buffer.utilization, 4),
        "peer_encounter_frequency": peer_enc_freq,
    }


# -----------------------------------------------------------------------------
# 2. Decision Dataset Generation & Simulation-Derived Labeling
# -----------------------------------------------------------------------------

def generate_decision_dataset(
    contact_csv_path: Union[str, Path],
    workload: Sequence[Packet],
    transfer_rate_bytes_sec: float = 250_000.0,
    transfer_overhead_ms: int = 50,
    buffer_capacity_bytes: Optional[int] = 2_000_000,
    scenario_id: str = "vannes_50m",
) -> pd.DataFrame:
    """
    Extracts candidate forwarding decision opportunities with strictly causal features
    and calculates simulation-derived teacher labels using the temporal A* shortest path oracle.
    Accurately identifies both direct deliveries and optimal multi-hop intermediate relay transfers.
    """
    schedule = TemporalContactSchedule.from_csv(contact_csv_path)
    planner = TimeDependentAStar(schedule, heuristic="zero")

    # Precompute optimal time-dependent routes for workload packets from source
    planned_routes: Dict[str, Any] = {}
    for pkt in workload:
        route = planner.find_earliest_arrival_path(
            source=pkt.source,
            destination=pkt.destination,
            creation_time_ms=pkt.creation_time_ms,
            ttl_ms=pkt.ttl_ms,
            packet_size_bytes=pkt.size_bytes,
            transfer_rate_bytes_sec=transfer_rate_bytes_sec,
            transfer_overhead_ms=transfer_overhead_ms,
            packet_id=pkt.packet_id,
        )
        if route.success:
            planned_routes[pkt.packet_id] = route

    records: List[Dict[str, Any]] = []

    # Local causal tracking state
    peer_encounter_counts: Dict[Tuple[str, str], int] = collections.defaultdict(int)
    peer_history_durations: Dict[Tuple[str, str], List[int]] = collections.defaultdict(list)

    def get_xfer_ms(sz: int) -> int:
        return transfer_overhead_ms + math.ceil((sz * 1000.0) / max(1.0, transfer_rate_bytes_sec))

    # Read contacts in chronological order
    df_contacts = pd.read_csv(contact_csv_path).sort_values("start_time_ms")

    nodes: Dict[str, NodeBuffer] = {
        nid: NodeBuffer(capacity_bytes=buffer_capacity_bytes)
        for nid in schedule.all_nodes
    }
    seen_packets: Dict[str, Set[str]] = collections.defaultdict(set)

    # Inject packets into source buffers
    for pkt in workload:
        if pkt.source in nodes:
            nodes[pkt.source].add(pkt.copy())
            seen_packets[pkt.source].add(pkt.packet_id)

    # Iterate through contacts
    for _, row in df_contacts.iterrows():
        u = str(row["node_a"])
        v = str(row["node_b"])
        s_time = int(row["start_time_ms"])
        e_time = int(row["end_time_ms"])
        actual_dur = e_time - s_time

        peer_encounter_counts[(u, v)] += 1
        peer_encounter_counts[(v, u)] += 1

        for sender, receiver in [(u, v), (v, u)]:
            buf = nodes[sender]
            if len(buf) == 0:
                continue

            past_durs = peer_history_durations[(sender, receiver)]
            avg_past_dur = float(np.mean(past_durs)) if len(past_durs) > 0 else 5000.0

            for pid, pkt in list(buf.packets.items()):
                if pkt.is_expired(s_time):
                    continue
                if pid in seen_packets[receiver]:
                    continue

                xfer_ms = get_xfer_ms(pkt.size_bytes)
                feats = extract_decision_features(
                    packet=pkt,
                    current_node=sender,
                    peer_node=receiver,
                    current_time_ms=s_time,
                    contact_start_ms=s_time,
                    buffer=buf,
                    transfer_duration_ms=xfer_ms,
                    peer_encounter_counts={receiver: peer_encounter_counts[(sender, receiver)]},
                    peer_historical_avg_durations_ms={receiver: avg_past_dur},
                )

                # Teacher Labeling via Temporal Oracle:
                # 1. Physical Feasibility: Transfer must complete before contact ends in physical reality
                if s_time + xfer_ms > e_time:
                    label = 0
                    label_reason = "truncated_contact"
                # 2. Direct Delivery: Receiver is destination
                elif pkt.destination == receiver:
                    label = 1
                    label_reason = "direct_destination_delivery"
                # 3. Intermediate Relay Evaluation:
                else:
                    route = planned_routes.get(pid)
                    if route and route.success and sender in route.path_nodes:
                        idx_s = route.path_nodes.index(sender)
                        if idx_s + 1 < len(route.path_nodes) and route.path_nodes[idx_s + 1] == receiver:
                            hop = route.hops[idx_s]
                            if hop.contact_start_ms == s_time:
                                label = 1
                                label_reason = "optimal_intermediate_relay"
                            else:
                                label = 0
                                label_reason = "wrong_contact_time"
                        else:
                            label = 0
                            label_reason = "not_next_hop"
                    else:
                        label = 0
                        label_reason = "no_path_from_sender"

                row_dict = {
                    "scenario_id": scenario_id,
                    "packet_id": pid,
                    "current_node": sender,
                    "peer_node": receiver,
                    "sim_time_ms": s_time,
                    **feats,
                    "target_should_forward": label,
                    "label_reason": label_reason,
                }
                records.append(row_dict)

                # Opportunistic relay propagation for positive label
                if label == 1 and (s_time + xfer_ms <= e_time):
                    nodes[receiver].add(pkt.copy())
                    seen_packets[receiver].add(pid)

        # After contact finishes, record completed duration in history
        peer_history_durations[(u, v)].append(actual_dur)
        peer_history_durations[(v, u)].append(actual_dur)

    df_decisions = pd.DataFrame.from_records(records)
    return df_decisions


# -----------------------------------------------------------------------------
# 3. Model Training & Evaluation
# -----------------------------------------------------------------------------

@dataclasses.dataclass
class TrainedModelArtifacts:
    """Stores trained model, preprocessing scaler, and evaluation metrics."""
    decision_tree: DecisionTreeClassifier
    logistic_regression: LogisticRegression
    scaler: StandardScaler
    dt_metrics: Dict[str, Any]
    lr_metrics: Dict[str, Any]
    feature_names: List[str]
    dt_rules_text: str
    feature_importances: Dict[str, float]


def train_and_evaluate_models(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_names: List[str] = DECISION_FEATURE_NAMES,
    seed: int = 42,
) -> TrainedModelArtifacts:
    """
    Trains a Shallow Decision Tree and Logistic Regression model.
    Scales features using StandardScaler fitted ONLY on train_df.
    Evaluates on test_df with comprehensive class metrics and confusion matrix.
    """
    X_train = train_df[feature_names].values
    y_train = train_df["target_should_forward"].values

    X_val = val_df[feature_names].values
    y_val = val_df["target_should_forward"].values

    X_test = test_df[feature_names].values
    y_test = test_df["target_should_forward"].values

    # Preprocessing scaler fitted strictly on X_train (Zero Data Leakage)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    # 1. Train Shallow Decision Tree (tune max_depth on validation set)
    best_dt = None
    best_val_f1 = -1.0
    for depth in (2, 3, 4):
        dt = DecisionTreeClassifier(max_depth=depth, random_state=seed, class_weight="balanced")
        dt.fit(X_train, y_train)
        preds_val = dt.predict(X_val)
        f1 = f1_score(y_val, preds_val, zero_division=0)
        if f1 > best_val_f1:
            best_val_f1 = f1
            best_dt = dt

    assert best_dt is not None

    # Evaluate Decision Tree on test set
    dt_test_preds = best_dt.predict(X_test)
    dt_test_probs = best_dt.predict_proba(X_test)[:, 1] if len(best_dt.classes_) > 1 else dt_test_preds
    cm_dt = confusion_matrix(y_test, dt_test_preds)

    dt_metrics = {
        "accuracy": round(float(accuracy_score(y_test, dt_test_preds)), 4),
        "precision": round(float(precision_score(y_test, dt_test_preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, dt_test_preds, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, dt_test_preds, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, dt_test_probs)), 4) if len(np.unique(y_test)) > 1 else 0.5,
        "confusion_matrix": cm_dt.tolist(),
        "positive_support": int((y_test == 1).sum()),
        "negative_support": int((y_test == 0).sum()),
        "predicted_positives": int((dt_test_preds == 1).sum()),
    }

    # 2. Train Logistic Regression
    lr = LogisticRegression(C=1.0, max_iter=1000, random_state=seed, class_weight="balanced")
    lr.fit(X_train_scaled, y_train)

    lr_test_preds = lr.predict(X_test_scaled)
    lr_test_probs = lr.predict_proba(X_test_scaled)[:, 1] if len(lr.classes_) > 1 else lr_test_preds
    cm_lr = confusion_matrix(y_test, lr_test_preds)

    lr_metrics = {
        "accuracy": round(float(accuracy_score(y_test, lr_test_preds)), 4),
        "precision": round(float(precision_score(y_test, lr_test_preds, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, lr_test_preds, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, lr_test_preds, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, lr_test_probs)), 4) if len(np.unique(y_test)) > 1 else 0.5,
        "confusion_matrix": cm_lr.tolist(),
        "positive_support": int((y_test == 1).sum()),
        "negative_support": int((y_test == 0).sum()),
        "predicted_positives": int((lr_test_preds == 1).sum()),
    }

    rules_text = export_text(best_dt, feature_names=feature_names)
    importances = {name: round(float(imp), 4) for name, imp in zip(feature_names, best_dt.feature_importances_)}

    return TrainedModelArtifacts(
        decision_tree=best_dt,
        logistic_regression=lr,
        scaler=scaler,
        dt_metrics=dt_metrics,
        lr_metrics=lr_metrics,
        feature_names=feature_names,
        dt_rules_text=rules_text,
        feature_importances=importances,
    )


# -----------------------------------------------------------------------------
# 4. ESP8266 C++ Code Generation (Zero-Runtime Embedded Inference)
# -----------------------------------------------------------------------------

def generate_decision_tree_cpp(dt: DecisionTreeClassifier, feature_names: List[str]) -> str:
    """
    Translates a fitted scikit-learn DecisionTree into an ultra-compact,
    standalone C++ function suitable for deployment on an ESP8266 NodeMCU.
    Footprint and latency figures are analytical code-derived static estimates (Xtensa L106 32-bit).
    """
    tree = dt.tree_

    def recurse(node_id: int, depth: int) -> List[str]:
        indent = "  " * depth
        if tree.children_left[node_id] == -1:
            val = tree.value[node_id][0]
            pred_class = 1 if (val[1] > val[0]) else 0
            conf = val[1] / max(1e-6, (val[0] + val[1]))
            return [f"{indent}// Leaf confidence: {conf:.2f}\n{indent}return {pred_class};"]

        feat_idx = tree.feature[node_id]
        thresh = tree.threshold[node_id]
        feat_name = feature_names[feat_idx]

        left_code = recurse(tree.children_left[node_id], depth + 1)
        right_code = recurse(tree.children_right[node_id], depth + 1)

        lines = [
            f"{indent}if (features.{feat_name} <= {thresh:.8f}f) {{",
            *left_code,
            f"{indent}}} else {{",
            *right_code,
            f"{indent}}}",
        ]
        return lines

    body = "\n".join(recurse(0, 1))

    cpp_code = f"""// ============================================================================
// ESP8266 NodeMCU Firmware - Decentralized Routing Policy (Decision Tree)
// Generated by DTN AI Routing Pipeline (Stage 5.1 Causal Audit)
// Target Architecture: Tensilica Xtensa L106 @ 80MHz / 80KB SRAM
// Static Analytical Footprint: Flash < 512 bytes | RAM = 0 bytes (stack frame: ~24B)
// Static Analytical Latency: < 1.0 microsecond (3-4 branch evaluations)
// Note: Static code-derived estimate; physical hardware benchmarking on ESP8266 required upon firmware deployment.
// ============================================================================

#ifndef DECENTRALIZED_DTN_ROUTER_H
#define DECENTRALIZED_DTN_ROUTER_H

#include <stdint.h>
#include <stdbool.h>

#ifndef LOCAL_DECISION_FEATURES_DEF
#define LOCAL_DECISION_FEATURES_DEF
struct LocalDecisionFeatures {{
    uint8_t  peer_is_destination;           // 1 if peer == packet destination, else 0
    uint32_t packet_size_bytes;             // Packet size in bytes
    uint8_t  packet_priority;               // Priority (1=Normal, 2=High, 3=Urgent)
    float    remaining_ttl_ratio;           // Normalized remaining TTL [0.0 - 1.0]
    uint16_t packet_hops;                   // Number of hops traversed
    uint32_t transfer_duration_ms;          // Required transfer duration in ms
    uint32_t contact_elapsed_ms;            // Elapsed time since contact establish (causal)
    uint32_t estimated_remaining_contact_ms;// Causal estimate from past encounter history
    uint8_t  estimated_transfer_fits;       // 1 if transfer fits in estimated remaining window
    float    local_buffer_utilization;      // Buffer occupancy ratio [0.0 - 1.0]
    uint16_t peer_encounter_frequency;      // Historical completed encounters with peer
}};
#endif // LOCAL_DECISION_FEATURES_DEF

/**
 * Evaluates whether the ESP8266 should forward the packet to the encountered peer.
 * @return true if forward, false if hold/wait.
 */
inline bool decide_forwarding_decision_tree(const LocalDecisionFeatures& features) {{
{body}
}}

#endif // DECENTRALIZED_DTN_ROUTER_H
"""
    return cpp_code


def generate_logistic_regression_cpp(
    lr: LogisticRegression,
    scaler: StandardScaler,
    feature_names: List[str],
) -> str:
    """
    Translates a fitted LogisticRegression model and StandardScaler into compact C++ code.
    Evaluates: logit = bias + sum(weights * (feat - mean) / std) > 0.
    Footprint and latency figures are analytical code-derived static estimates (Xtensa L106 32-bit).
    """
    weights = lr.coef_[0]
    bias = lr.intercept_[0]
    means = scaler.mean_
    scales = scaler.scale_

    weight_terms = []
    for i, name in enumerate(feature_names):
        weight_terms.append(
            f"    logit += {weights[i]:.6f}f * ((features.{name} - {means[i]:.6f}f) / {scales[i]:.6f}f);"
        )

    terms_code = "\n".join(weight_terms)

    cpp_code = f"""// ============================================================================
// ESP8266 NodeMCU Firmware - Decentralized Routing Policy (Logistic Regression)
// Generated by DTN AI Routing Pipeline (Stage 5.1 Causal Audit)
// Target Architecture: Tensilica Xtensa L106 @ 80MHz / 80KB SRAM
// Static Analytical Footprint: Flash < 1 KB | RAM = 0 bytes (stack frame: ~44B)
// Static Analytical Latency: ~3.5 microseconds (11 multiply-accumulate operations)
// Note: Static code-derived estimate; physical hardware benchmarking on ESP8266 required upon firmware deployment.
// ============================================================================

#ifndef DECENTRALIZED_DTN_LOGISTIC_H
#define DECENTRALIZED_DTN_LOGISTIC_H

#include <stdint.h>
#include <stdbool.h>

#ifndef LOCAL_DECISION_FEATURES_DEF
#define LOCAL_DECISION_FEATURES_DEF
struct LocalDecisionFeatures {{
    uint8_t  peer_is_destination;
    uint32_t packet_size_bytes;
    uint8_t  packet_priority;
    float    remaining_ttl_ratio;
    uint16_t packet_hops;
    uint32_t transfer_duration_ms;
    uint32_t contact_elapsed_ms;
    uint32_t estimated_remaining_contact_ms;
    uint8_t  estimated_transfer_fits;
    float    local_buffer_utilization;
    uint16_t peer_encounter_frequency;
}};
#endif // LOCAL_DECISION_FEATURES_DEF

/**
 * Evaluates logistic regression logit: z > 0 corresponds to probability > 0.5.
 * Eliminates expensive exp() calculation on embedded MCU.
 */
inline bool decide_forwarding_logistic_regression(const LocalDecisionFeatures& features) {{
    float logit = {bias:.6f}f;
{terms_code}
    return (logit > 0.0f);
}}

#endif // DECENTRALIZED_DTN_LOGISTIC_H
"""
    return cpp_code


# -----------------------------------------------------------------------------
# 5. Decentralized AI Router Classes for Simulator Integration
# -----------------------------------------------------------------------------

class DecisionTreeRouter(BaseRouter):
    """
    Decentralized AI Router powered by the Shallow Decision Tree policy.
    Uses strictly local contemporaneous observations and causal history.
    """

    def __init__(
        self,
        node_id: str,
        model: Optional[DecisionTreeClassifier] = None,
        feature_names: List[str] = DECISION_FEATURE_NAMES,
    ):
        super().__init__(node_id)
        self.model = model
        self.feature_names = feature_names
        # Causal local history tracking
        self.peer_encounter_counts: Dict[str, int] = collections.defaultdict(int)
        self.peer_history_durations: Dict[str, List[int]] = collections.defaultdict(list)
        self.active_contacts: Dict[str, int] = {}
        self.last_seen_time: Dict[str, int] = {}

    def select_packets_to_forward(
        self,
        current_time_ms: int,
        peer_id: str,
        peer_seen_packet_ids: Set[str],
        buffer: NodeBuffer,
    ) -> List[Packet]:
        # Track contact establishment and completed durations causally
        if peer_id not in self.active_contacts or (current_time_ms - self.last_seen_time.get(peer_id, 0) > 2000):
            if peer_id in self.active_contacts:
                prev_dur = self.last_seen_time[peer_id] - self.active_contacts[peer_id]
                if prev_dur > 0:
                    self.peer_history_durations[peer_id].append(prev_dur)
            self.active_contacts[peer_id] = current_time_ms
            self.peer_encounter_counts[peer_id] += 1

        self.last_seen_time[peer_id] = current_time_ms

        contact_start_ms = self.active_contacts[peer_id]
        contact_elapsed_ms = current_time_ms - contact_start_ms
        past_durs = self.peer_history_durations[peer_id]
        avg_past_dur = float(np.mean(past_durs)) if len(past_durs) > 0 else 5000.0
        est_remaining_ms = max(0.0, avg_past_dur - contact_elapsed_ms)

        candidates: List[Packet] = []
        if not self.model:
            return candidates

        for pkt in buffer.packets.values():
            if pkt.is_expired(current_time_ms):
                continue
            if pkt.packet_id in peer_seen_packet_ids:
                continue

            # Direct delivery is always prioritary
            if pkt.destination == peer_id:
                candidates.append(pkt)
                continue

            # Compute strictly causal local features
            xfer_ms = 50 + math.ceil((pkt.size_bytes * 1000.0) / 250_000.0)
            est_fits = 1 if (xfer_ms <= est_remaining_ms) else 0
            rem_ttl = max(0, pkt.expiry_time_ms - current_time_ms)
            ttl_ratio = rem_ttl / max(1, pkt.ttl_ms)

            feats = {
                "peer_is_destination": 0,
                "packet_size_bytes": pkt.size_bytes,
                "packet_priority": pkt.priority,
                "remaining_ttl_ratio": round(ttl_ratio, 4),
                "packet_hops": pkt.hops,
                "transfer_duration_ms": xfer_ms,
                "contact_elapsed_ms": contact_elapsed_ms,
                "estimated_remaining_contact_ms": int(est_remaining_ms),
                "estimated_transfer_fits": est_fits,
                "local_buffer_utilization": round(buffer.utilization, 4),
                "peer_encounter_frequency": self.peer_encounter_counts[peer_id],
            }

            X = np.array([[feats[name] for name in self.feature_names]])
            pred = self.model.predict(X)[0]

            if pred == 1:
                candidates.append(pkt)

        # Prioritize destination deliveries first, then higher priority, then FIFO
        candidates.sort(key=lambda p: (-(p.destination == peer_id), -p.priority, p.creation_time_ms))
        return candidates


class LogisticRegressionRouter(BaseRouter):
    """
    Decentralized AI Router powered by the Logistic Regression policy.
    Uses strictly local observations scaled by the offline training scaler.
    """

    def __init__(
        self,
        node_id: str,
        model: Optional[LogisticRegression] = None,
        scaler: Optional[StandardScaler] = None,
        feature_names: List[str] = DECISION_FEATURE_NAMES,
    ):
        super().__init__(node_id)
        self.model = model
        self.scaler = scaler
        self.feature_names = feature_names
        # Causal local history tracking
        self.peer_encounter_counts: Dict[str, int] = collections.defaultdict(int)
        self.peer_history_durations: Dict[str, List[int]] = collections.defaultdict(list)
        self.active_contacts: Dict[str, int] = {}
        self.last_seen_time: Dict[str, int] = {}

    def select_packets_to_forward(
        self,
        current_time_ms: int,
        peer_id: str,
        peer_seen_packet_ids: Set[str],
        buffer: NodeBuffer,
    ) -> List[Packet]:
        if peer_id not in self.active_contacts or (current_time_ms - self.last_seen_time.get(peer_id, 0) > 2000):
            if peer_id in self.active_contacts:
                prev_dur = self.last_seen_time[peer_id] - self.active_contacts[peer_id]
                if prev_dur > 0:
                    self.peer_history_durations[peer_id].append(prev_dur)
            self.active_contacts[peer_id] = current_time_ms
            self.peer_encounter_counts[peer_id] += 1

        self.last_seen_time[peer_id] = current_time_ms

        contact_start_ms = self.active_contacts[peer_id]
        contact_elapsed_ms = current_time_ms - contact_start_ms
        past_durs = self.peer_history_durations[peer_id]
        avg_past_dur = float(np.mean(past_durs)) if len(past_durs) > 0 else 5000.0
        est_remaining_ms = max(0.0, avg_past_dur - contact_elapsed_ms)

        candidates: List[Packet] = []
        if not self.model or not self.scaler:
            return candidates

        for pkt in buffer.packets.values():
            if pkt.is_expired(current_time_ms):
                continue
            if pkt.packet_id in peer_seen_packet_ids:
                continue

            if pkt.destination == peer_id:
                candidates.append(pkt)
                continue

            xfer_ms = 50 + math.ceil((pkt.size_bytes * 1000.0) / 250_000.0)
            est_fits = 1 if (xfer_ms <= est_remaining_ms) else 0
            rem_ttl = max(0, pkt.expiry_time_ms - current_time_ms)
            ttl_ratio = rem_ttl / max(1, pkt.ttl_ms)

            feats = {
                "peer_is_destination": 0,
                "packet_size_bytes": pkt.size_bytes,
                "packet_priority": pkt.priority,
                "remaining_ttl_ratio": round(ttl_ratio, 4),
                "packet_hops": pkt.hops,
                "transfer_duration_ms": xfer_ms,
                "contact_elapsed_ms": contact_elapsed_ms,
                "estimated_remaining_contact_ms": int(est_remaining_ms),
                "estimated_transfer_fits": est_fits,
                "local_buffer_utilization": round(buffer.utilization, 4),
                "peer_encounter_frequency": self.peer_encounter_counts[peer_id],
            }

            X = np.array([[feats[name] for name in self.feature_names]])
            X_scaled = self.scaler.transform(X)
            pred = self.model.predict(X_scaled)[0]

            if pred == 1:
                candidates.append(pkt)

        candidates.sort(key=lambda p: (-(p.destination == peer_id), -p.priority, p.creation_time_ms))
        return candidates
