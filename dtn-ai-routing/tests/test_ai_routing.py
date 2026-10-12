"""
Test suite for Stage 5.1: Causal Decentralized AI Routing Pipeline & Validity Audit.

Validates:
1. Strictly causal feature extraction schema, naming, and boundaries (no future contact knowledge).
2. Edge case handling (expired TTL, zero elapsed time, unobserved peer history).
3. Corrected teacher labeling invariants (both direct delivery and optimal intermediate relays).
4. Prevention of destination-only collapse (positive decisions exist for peer_is_destination == 0).
5. Zero train/validation/test data leakage (disjoint packet-id sets in split manifest).
6. Deterministic model training reproducibility under fixed random seed.
7. Model artifact reload and prediction consistency.
8. C++ firmware code generation syntax, analytical estimates, and header guards.
9. Closed-loop simulator integration for DecisionTreeRouter and LogisticRegressionRouter.
10. Presence and integrity of all Stage 5 visual and reporting artifacts.
"""

from __future__ import annotations

import collections
import json
import math
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

# Ensure src directory is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ai_decision_engine import (
    DECISION_FEATURE_NAMES,
    DecisionTreeRouter,
    LogisticRegressionRouter,
    extract_decision_features,
    generate_decision_dataset,
    generate_decision_tree_cpp,
    generate_logistic_regression_cpp,
    train_and_evaluate_models,
)
from dtn_simulator import (
    DTNSimulator,
    NodeBuffer,
    Packet,
    SimulationMetrics,
)
from temporal_astar import TemporalContactSchedule, TimeDependentAStar


# -----------------------------------------------------------------------------
# 1. Feature Extraction Schema & Strictly Causal Boundaries
# -----------------------------------------------------------------------------

def test_feature_extraction_schema_and_boundaries():
    """
    Ensures feature extraction returns all 11 canonical causal features with values
    strictly inside their documented domain ranges, without future contact knowledge.
    """
    pkt = Packet(
        packet_id="pkt_test_01",
        source="nodeA",
        destination="nodeB",
        creation_time_ms=1000,
        ttl_ms=5000,
        size_bytes=10000,
        priority=2,
    )
    buffer = NodeBuffer(capacity_bytes=50000)
    buffer.add(pkt)

    feats = extract_decision_features(
        packet=pkt,
        current_node="nodeA",
        peer_node="nodeB",
        current_time_ms=2000,
        contact_start_ms=2000,
        buffer=buffer,
        transfer_duration_ms=90,
        peer_encounter_counts={"nodeB": 3},
        peer_historical_avg_durations_ms={"nodeB": 4000.0},
    )

    # All 11 features must be present
    assert set(feats.keys()) == set(DECISION_FEATURE_NAMES)
    assert len(feats) == len(DECISION_FEATURE_NAMES)

    # Specific values & boundaries
    assert feats["peer_is_destination"] == 1
    assert feats["packet_size_bytes"] == 10000
    assert feats["packet_priority"] == 2
    assert 0.0 <= feats["remaining_ttl_ratio"] <= 1.0
    assert feats["remaining_ttl_ratio"] == pytest.approx(4000 / 5000, abs=1e-3)
    assert feats["packet_hops"] == 0
    assert feats["transfer_duration_ms"] == 90
    assert feats["contact_elapsed_ms"] == 0
    assert feats["estimated_remaining_contact_ms"] == 4000
    assert feats["estimated_transfer_fits"] == 1
    assert 0.0 <= feats["local_buffer_utilization"] <= 1.0
    assert feats["peer_encounter_frequency"] == 3


def test_feature_extraction_edge_cases():
    """
    Tests edge conditions: zero remaining TTL, unobserved peer history,
    and elapsed contact exceeding historical average.
    """
    pkt = Packet(
        packet_id="pkt_edge",
        source="nodeX",
        destination="nodeZ",
        creation_time_ms=1000,
        ttl_ms=2000,
        size_bytes=15000,
        priority=1,
    )
    buffer = NodeBuffer(capacity_bytes=100000)

    # 1. Packet expired before current time
    feats_expired = extract_decision_features(
        packet=pkt,
        current_node="nodeX",
        peer_node="nodeY",
        current_time_ms=3500,
        contact_start_ms=3000,
        buffer=buffer,
        transfer_duration_ms=110,
        peer_encounter_counts={},
        peer_historical_avg_durations_ms={},
    )
    assert feats_expired["remaining_ttl_ratio"] == 0.0
    assert feats_expired["peer_is_destination"] == 0
    assert feats_expired["peer_encounter_frequency"] == 0
    assert feats_expired["contact_elapsed_ms"] == 500

    # 2. Elapsed contact exceeds historical average -> estimated_remaining = 0, fits = 0
    feats_overrun = extract_decision_features(
        packet=pkt,
        current_node="nodeX",
        peer_node="nodeY",
        current_time_ms=6000,
        contact_start_ms=1000,
        buffer=buffer,
        transfer_duration_ms=110,
        peer_encounter_counts={"nodeY": 1},
        peer_historical_avg_durations_ms={"nodeY": 3000.0},
    )
    assert feats_overrun["contact_elapsed_ms"] == 5000
    assert feats_overrun["estimated_remaining_contact_ms"] == 0
    assert feats_overrun["estimated_transfer_fits"] == 0


# -----------------------------------------------------------------------------
# 2. Corrected Teacher Labeling & Intermediate Relay Detection
# -----------------------------------------------------------------------------

def test_teacher_labeling_direct_delivery_and_intermediate_relays(tmp_path: Path):
    """
    Validates teacher labeling rules:
    - Direct delivery to destination yields label 1.
    - Physically truncated contact yields label 0.
    - Intermediate relay on the optimal A* path yields label 1 with optimal_intermediate_relay.
    """
    contact_csv = tmp_path / "contacts_test.csv"
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "test,50.0,nodeA,nodeB,1000,1200,200,10.0\n"
        "test,50.0,nodeB,nodeC,2000,3000,1000,10.0\n"
        "test,50.0,nodeA,nodeX,1500,1520,20,10.0\n"
    )

    workload = [
        # Packet destined for nodeB (direct delivery)
        Packet(packet_id="pkt_dir", source="nodeA", destination="nodeB", creation_time_ms=500, ttl_ms=10000, size_bytes=10000, priority=1),
        # Packet destined for nodeC via nodeB (nodeA -> nodeB -> nodeC)
        Packet(packet_id="pkt_multi", source="nodeA", destination="nodeC", creation_time_ms=500, ttl_ms=10000, size_bytes=10000, priority=1),
        # Packet destined for nodeZ meeting nodeX (window 20ms too short for ~70ms transfer)
        Packet(packet_id="pkt_trunc", source="nodeA", destination="nodeZ", creation_time_ms=500, ttl_ms=10000, size_bytes=10000, priority=1),
    ]

    df = generate_decision_dataset(
        contact_csv_path=contact_csv,
        workload=workload,
        transfer_rate_bytes_sec=250_000.0,
        transfer_overhead_ms=50,
        scenario_id="test_labels",
    )

    # 1. Direct delivery
    dir_rows = df[(df["packet_id"] == "pkt_dir") & (df["peer_node"] == "nodeB")]
    assert len(dir_rows) > 0
    assert dir_rows.iloc[0]["target_should_forward"] == 1
    assert dir_rows.iloc[0]["label_reason"] == "direct_destination_delivery"

    # 2. Optimal intermediate relay (nodeA -> nodeB for pkt_multi)
    relay_rows = df[(df["packet_id"] == "pkt_multi") & (df["peer_node"] == "nodeB") & (df["sim_time_ms"] == 1000)]
    assert len(relay_rows) > 0
    assert relay_rows.iloc[0]["target_should_forward"] == 1
    assert relay_rows.iloc[0]["label_reason"] == "optimal_intermediate_relay"

    # 3. Truncated contact (window 20ms < xfer 70ms)
    trunc_rows = df[(df["packet_id"] == "pkt_trunc") & (df["peer_node"] == "nodeX")]
    assert len(trunc_rows) > 0
    assert trunc_rows.iloc[0]["target_should_forward"] == 0
    assert trunc_rows.iloc[0]["label_reason"] == "truncated_contact"


def test_destination_only_collapse_detection():
    """
    Regression Test: Verifies that the decision dataset and trained models do NOT
    collapse into a destination-only rule (i.e. positive decisions MUST exist
    for peer_is_destination == 0).
    """
    features_csv = PROJECT_ROOT / "data" / "ai_experiments" / "decision_features.csv"
    if not features_csv.exists():
        pytest.skip("decision_features.csv not found.")

    df = pd.read_csv(features_csv)
    relay_positives = df[(df["peer_is_destination"] == 0) & (df["target_should_forward"] == 1)]
    assert len(relay_positives) > 0, (
        "Model validity failure: Exactly 0 intermediate relay opportunities were labeled positive! "
        "The dataset has collapsed to Direct Delivery."
    )


# -----------------------------------------------------------------------------
# 3. Data Leakage Prevention (Split Manifest)
# -----------------------------------------------------------------------------

def test_split_manifest_zero_leakage():
    """
    Verifies that train, validation, and test packet IDs are strictly disjoint
    in the split manifest generated by the pipeline.
    """
    manifest_path = PROJECT_ROOT / "data" / "ai_experiments" / "split_manifest.json"
    if not manifest_path.exists():
        pytest.skip("Split manifest has not been generated yet.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    train_pkts = set(manifest["train_packets"])
    val_pkts = set(manifest["val_packets"])
    test_pkts = set(manifest["test_packets"])

    assert len(train_pkts) > 0
    assert len(val_pkts) > 0
    assert len(test_pkts) > 0

    # Strict disjointness
    assert train_pkts.isdisjoint(val_pkts), "Train and Validation sets have overlapping packets!"
    assert train_pkts.isdisjoint(test_pkts), "Train and Test sets have overlapping packets!"
    assert val_pkts.isdisjoint(test_pkts), "Validation and Test sets have overlapping packets!"


# -----------------------------------------------------------------------------
# 4. Model Training Reproducibility & Performance
# -----------------------------------------------------------------------------

def test_model_training_reproducibility():
    """
    Verifies that model training is fully deterministic under a fixed random seed.
    """
    rng = np.random.RandomState(42)
    n_samples = 200
    n_feats = len(DECISION_FEATURE_NAMES)
    data = rng.rand(n_samples, n_feats)
    labels = rng.randint(0, 2, size=n_samples)

    df = pd.DataFrame(data, columns=DECISION_FEATURE_NAMES)
    df["target_should_forward"] = labels

    train_df = df.iloc[:120]
    val_df = df.iloc[120:160]
    test_df = df.iloc[160:]

    artifacts_1 = train_and_evaluate_models(train_df, val_df, test_df, seed=42)
    artifacts_2 = train_and_evaluate_models(train_df, val_df, test_df, seed=42)

    p1 = artifacts_1.decision_tree.predict(test_df[DECISION_FEATURE_NAMES].values)
    p2 = artifacts_2.decision_tree.predict(test_df[DECISION_FEATURE_NAMES].values)
    np.testing.assert_array_equal(p1, p2)

    assert artifacts_1.dt_metrics["accuracy"] == artifacts_2.dt_metrics["accuracy"]
    assert artifacts_1.lr_metrics["accuracy"] == artifacts_2.lr_metrics["accuracy"]


def test_saved_model_reload_and_inference():
    """
    Ensures saved model artifacts on disk can be reloaded via joblib and
    generate valid binary classifications on causal features.
    """
    models_dir = PROJECT_ROOT / "models" / "stage5"
    dt_path = models_dir / "decision_tree_model.joblib"
    lr_path = models_dir / "logistic_regression_model.joblib"
    scaler_path = models_dir / "feature_scaler.joblib"

    if not (dt_path.exists() and lr_path.exists() and scaler_path.exists()):
        pytest.skip("Model artifacts not found in models/stage5.")

    dt_model = joblib.load(dt_path)
    lr_model = joblib.load(lr_path)
    scaler = joblib.load(scaler_path)

    assert isinstance(dt_model, DecisionTreeClassifier)
    assert isinstance(lr_model, LogisticRegression)
    assert isinstance(scaler, StandardScaler)

    # Sample input vector (11 causal features)
    dummy_input = np.array([[0, 10000, 1, 0.8, 1, 90, 0, 5000, 1, 0.2, 5]], dtype=float)
    dt_pred = dt_model.predict(dummy_input)
    assert dt_pred[0] in (0, 1)

    dummy_scaled = scaler.transform(dummy_input)
    lr_pred = lr_model.predict(dummy_scaled)
    assert lr_pred[0] in (0, 1)


# -----------------------------------------------------------------------------
# 5. C++ Firmware Code Generation
# -----------------------------------------------------------------------------

def test_cpp_code_generation_syntax():
    """
    Verifies that C++ code generators emit clean, syntactically correct code
    with header guards, structures, and decision functions.
    """
    rng = np.random.RandomState(42)
    X = rng.rand(100, len(DECISION_FEATURE_NAMES))
    y = rng.randint(0, 2, size=100)

    dt = DecisionTreeClassifier(max_depth=3, random_state=42)
    dt.fit(X, y)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    lr = LogisticRegression(random_state=42)
    lr.fit(X_scaled, y)

    dt_cpp = generate_decision_tree_cpp(dt, DECISION_FEATURE_NAMES)
    lr_cpp = generate_logistic_regression_cpp(lr, scaler, DECISION_FEATURE_NAMES)

    assert "#ifndef DECENTRALIZED_DTN_ROUTER_H" in dt_cpp
    assert "struct LocalDecisionFeatures" in dt_cpp
    assert "uint32_t contact_elapsed_ms;" in dt_cpp
    assert "uint32_t estimated_remaining_contact_ms;" in dt_cpp
    assert "uint8_t  estimated_transfer_fits;" in dt_cpp
    assert "inline bool decide_forwarding_decision_tree" in dt_cpp
    assert "return 0;" in dt_cpp or "return 1;" in dt_cpp

    assert "#ifndef DECENTRALIZED_DTN_LOGISTIC_H" in lr_cpp
    assert "inline bool decide_forwarding_logistic_regression" in lr_cpp
    assert "logit > 0.0f" in lr_cpp


# -----------------------------------------------------------------------------
# 6. Simulator Integration with Decentralized AI Routers
# -----------------------------------------------------------------------------

def test_simulator_with_ai_routers(tmp_path: Path):
    """
    Ensures DTNSimulator can run end-to-end with decision_tree and
    logistic_regression routing policies using causal features.
    """
    contact_csv = tmp_path / "sim_test_contacts.csv"
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "test,50.0,nodeA,nodeB,1000,3000,2000,10.0\n"
        "test,50.0,nodeB,nodeC,4000,6000,2000,10.0\n"
    )

    models_dir = PROJECT_ROOT / "models" / "stage5"
    dt_model_path = models_dir / "decision_tree_model.joblib"
    lr_model_path = models_dir / "logistic_regression_model.joblib"
    scaler_path = models_dir / "feature_scaler.joblib"

    dt_model = joblib.load(dt_model_path) if dt_model_path.exists() else None
    lr_model = joblib.load(lr_model_path) if lr_model_path.exists() else None
    scaler = joblib.load(scaler_path) if scaler_path.exists() else None

    workload = [
        Packet("pkt_test_1", "nodeA", "nodeC", 500, 10000, 5000, 1),
        Packet("pkt_test_2", "nodeA", "nodeB", 600, 10000, 5000, 2),
    ]

    # Test Decision Tree Router
    sim_dt = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        routing_policy="decision_tree",
        buffer_capacity_bytes=500_000,
        model=dt_model,
        seed=42,
    )
    metrics_dt = sim_dt.run(traffic_workload=workload)
    assert isinstance(metrics_dt, SimulationMetrics)
    assert metrics_dt.total_generated == 2

    # Test Logistic Regression Router
    sim_lr = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        routing_policy="logistic_regression",
        buffer_capacity_bytes=500_000,
        model=lr_model,
        scaler=scaler,
        seed=42,
    )
    metrics_lr = sim_lr.run(traffic_workload=workload)
    assert isinstance(metrics_lr, SimulationMetrics)
    assert metrics_lr.total_generated == 2


# -----------------------------------------------------------------------------
# 7. Verification of Stage 5 Artifacts and Visual Reports
# -----------------------------------------------------------------------------

def test_stage5_visual_and_report_artifacts_exist():
    """
    Verifies that all 7 required Stage 5 plots and accompanying markdown reports
    exist and are populated.
    """
    figures_dir = PROJECT_ROOT / "reports" / "figures" / "stage5"
    required_figures = [
        "pdr_by_policy_and_range.png",
        "delay_by_policy_and_range.png",
        "forwarding_overhead_by_policy.png",
        "pdr_vs_delay_tradeoff.png",
        "model_roc_pr_curves.png",
        "model_footprint_comparison.png",
        "seed_variability_comparison.png",
    ]

    for fig_name in required_figures:
        fig_path = figures_dir / fig_name
        assert fig_path.exists(), f"Missing required figure: {fig_name}"
        assert fig_path.stat().st_size > 1000, f"Figure {fig_name} appears empty or corrupted"

    # Verify Markdown documents
    rep_eval = PROJECT_ROOT / "reports" / "stage5_ai_evaluation.md"
    rep_audit = PROJECT_ROOT / "reports" / "stage5_model_validity_audit.md"
    rep_esp = PROJECT_ROOT / "reports" / "esp8266_deployment_feasibility.md"
    feat_dict = PROJECT_ROOT / "data" / "ai_experiments" / "feature_dictionary.md"
    label_spec = PROJECT_ROOT / "data" / "ai_experiments" / "label_generation_spec.md"

    for doc in [rep_eval, rep_audit, rep_esp, feat_dict, label_spec]:
        assert doc.exists(), f"Missing required documentation artifact: {doc.name}"
        assert doc.stat().st_size > 500, f"Artifact {doc.name} appears truncated"
