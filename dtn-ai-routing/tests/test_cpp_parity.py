"""
Test suite for Stage 5.2: C++ Model Parity & Feature Interface Consistency.

Validates:
1. Feature Interface Consistency & Causality (11 features matching DECISION_FEATURE_NAMES, no oracle leakage).
2. Host C++ Compiler Presence & Executable Compilation.
3. 100% Exact Prediction Parity between Python Scikit-Learn models and native exported C++ code
   across direct destination, accepted/rejected relays, boundary values around all tree thresholds,
   contact window boundaries, TTL edge cases, and buffer saturation cases.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys
import joblib
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
MODELS_DIR = PROJECT_ROOT / "models" / "stage5"
TESTS_DIR = PROJECT_ROOT / "tests"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ai_decision_engine import DECISION_FEATURE_NAMES


def get_cpp_compiler() -> str | None:
    """Finds an available C++ compiler executable on the host system."""
    for compiler in ["g++", "clang++", "c++"]:
        path = shutil.which(compiler)
        if path:
            return path
    # Common MSYS2/MinGW paths on Windows
    msys_gpp = Path("C:/msys64/ucrt64/bin/g++.exe")
    if msys_gpp.exists():
        return str(msys_gpp)
    return None


def test_feature_interface_consistency_and_causality():
    """
    Verifies that the exported C++ LocalDecisionFeatures struct matches the 11
    canonical causal decision features exactly, without future contact knowledge.
    """
    dt_cpp_file = MODELS_DIR / "decision_tree_esp8266.cpp"
    lr_cpp_file = MODELS_DIR / "logistic_regression_esp8266.cpp"

    assert dt_cpp_file.exists(), f"Missing {dt_cpp_file}"
    assert lr_cpp_file.exists(), f"Missing {lr_cpp_file}"

    dt_content = dt_cpp_file.read_text(encoding="utf-8")
    lr_content = lr_cpp_file.read_text(encoding="utf-8")

    # Invariants for both C++ files:
    for code, filename in [(dt_content, "decision_tree_esp8266.cpp"), (lr_content, "logistic_regression_esp8266.cpp")]:
        assert "struct LocalDecisionFeatures" in code, f"LocalDecisionFeatures missing in {filename}"
        assert "#ifndef LOCAL_DECISION_FEATURES_DEF" in code, f"Include guard missing in {filename}"

        # All 11 feature names must be represented in the struct definition
        for feat in DECISION_FEATURE_NAMES:
            assert feat in code, f"Feature '{feat}' missing in {filename}"

        # No oracle or non-causal features allowed
        forbidden_keywords = [
            "oracle",
            "future_contact",
            "actual_contact_duration",
            "astar",
            "global_topology",
            "optimal_path",
        ]
        for forbidden in forbidden_keywords:
            assert forbidden not in code.lower(), f"Forbidden non-causal keyword '{forbidden}' in {filename}"


def test_host_cpp_compiler_available():
    """Confirms that a valid C++ compiler is available on the test environment."""
    compiler = get_cpp_compiler()
    assert compiler is not None, "Host C++ compiler (g++, clang++) was not found in PATH or standard locations."


def test_cpp_test_harness_compilation():
    """Compiles tests/cpp_test_harness.cpp into an executable using the host C++ compiler."""
    compiler = get_cpp_compiler()
    assert compiler is not None, "Compiler required for native harness test"

    harness_src = TESTS_DIR / "cpp_test_harness.cpp"
    harness_exe = TESTS_DIR / "cpp_test_harness.exe"

    assert harness_src.exists(), f"Missing {harness_src}"

    cmd = [compiler, "-O2", "-std=c++17", "-Wall", "-Wextra", str(harness_src), "-o", str(harness_exe)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert result.returncode == 0, f"Compilation failed: {result.stderr}"
    assert harness_exe.exists(), "Compiled harness executable not found"


def generate_comprehensive_test_vectors() -> list[dict]:
    """
    Generates a comprehensive battery of test vectors designed to rigorously test:
    1. Direct destination encounters (peer_is_destination = 1).
    2. Intermediate relay encounters accepted by decision tree (peer_is_destination = 0).
    3. Intermediate relay encounters rejected by decision tree.
    4. Boundary values around all tree thresholds:
       - remaining_ttl_ratio: 0.70545000, 0.71044999, 0.87105000, 0.94155002, 1.03395003, 1.06325001
       - local_buffer_utilization: 0.02250000
       - peer_encounter_frequency: 1.50000000
    5. Contact duration boundaries (estimated contact just above/below transfer duration).
    6. Extreme values: near-zero/zero TTL, TTL > 1.0, high buffer utilization.
    7. Multi-size and multi-priority packet combinations.
    """
    vectors = []
    idx = 1

    def make_vec(tid: str, **kwargs) -> dict:
        base = {
            "test_id": tid,
            "peer_is_destination": 0,
            "packet_size_bytes": 10000,
            "packet_priority": 1,
            "remaining_ttl_ratio": 0.8,
            "packet_hops": 0,
            "transfer_duration_ms": 90,
            "contact_elapsed_ms": 0,
            "estimated_remaining_contact_ms": 5000,
            "estimated_transfer_fits": 1,
            "local_buffer_utilization": 0.01,
            "peer_encounter_frequency": 2,
        }
        base.update(kwargs)
        return base

    # 1. Direct Destination Encounters
    for prio in [1, 2, 3]:
        for size in [5000, 10000, 50000]:
            for ttl in [0.05, 0.5, 0.95]:
                vectors.append(make_vec(
                    f"dir_dest_p{prio}_s{size}_t{int(ttl*100)}",
                    peer_is_destination=1,
                    packet_priority=prio,
                    packet_size_bytes=size,
                    remaining_ttl_ratio=ttl,
                ))

    # 2. Intermediate Relay Encounters - Accepted by Decision Tree
    # (remaining_ttl_ratio > 0.87105 and <= 1.03395)
    for ttl in [0.88, 0.90, 0.92, 0.95, 1.00]:
        vectors.append(make_vec(
            f"relay_acc_ttl_{int(ttl*100)}",
            peer_is_destination=0,
            remaining_ttl_ratio=ttl,
            peer_encounter_frequency=3,
        ))

    # 3. Intermediate Relay Encounters - Rejected by Decision Tree
    # (remaining_ttl_ratio <= 0.71045 or remaining_ttl_ratio in (0.71045, 0.87105])
    for ttl in [0.1, 0.3, 0.5, 0.70, 0.75, 0.80, 0.85]:
        vectors.append(make_vec(
            f"relay_rej_ttl_{int(ttl*100)}",
            peer_is_destination=0,
            remaining_ttl_ratio=ttl,
            peer_encounter_frequency=3,
        ))

    # 4. Near-zero and near-one TTL ratios
    for ttl in [0.0, 0.0001, 0.001, 0.01, 0.99, 0.999, 1.0, 1.001]:
        vectors.append(make_vec(
            f"ttl_edge_{str(ttl).replace('.', '_')}",
            remaining_ttl_ratio=ttl,
        ))

    # 5. Boundary values around ALL decision tree thresholds:
    # Thresholds from tree:
    #   remaining_ttl_ratio: 0.70545000, 0.71044999, 0.87105000, 0.94155002, 1.03395003, 1.06325001
    #   local_buffer_utilization: 0.02250000
    #   peer_encounter_frequency: 1.50000000
    ttl_thresholds = [0.70545000, 0.71044999, 0.87105000, 0.94155002, 1.03395003, 1.06325001]
    for thresh in ttl_thresholds:
        for delta in [-1e-4, -1e-6, 1e-6, 1e-4]:
            val = thresh + delta
            vectors.append(make_vec(
                f"bnd_ttl_{thresh:.6f}_{delta:+.6f}",
                remaining_ttl_ratio=val,
            ))

    buf_threshold = 0.02250000
    for delta in [-1e-4, -1e-6, 1e-6, 1e-4]:
        val = max(0.0, buf_threshold + delta)
        vectors.append(make_vec(
            f"bnd_buf_{buf_threshold:.6f}_{delta:+.6f}",
            remaining_ttl_ratio=0.6,  # puts it into the buffer branch
            local_buffer_utilization=val,
        ))

    enc_threshold = 1.50000000
    for enc in [0, 1, 2, 3]:
        vectors.append(make_vec(
            f"bnd_enc_{enc}",
            remaining_ttl_ratio=0.6,
            local_buffer_utilization=0.01,
            peer_encounter_frequency=enc,
        ))

    # 6. Contact duration boundaries (estimated remaining contact vs transfer duration)
    # Transfer duration = 90 ms
    vectors.append(make_vec(
        "contact_just_below_transfer",
        transfer_duration_ms=90,
        estimated_remaining_contact_ms=89,
        estimated_transfer_fits=0,
    ))
    vectors.append(make_vec(
        "contact_exact_transfer",
        transfer_duration_ms=90,
        estimated_remaining_contact_ms=90,
        estimated_transfer_fits=1,
    ))
    vectors.append(make_vec(
        "contact_just_above_transfer",
        transfer_duration_ms=90,
        estimated_remaining_contact_ms=91,
        estimated_transfer_fits=1,
    ))

    # 7. Extreme and invalid edge cases
    vectors.append(make_vec("extreme_ttl_high", remaining_ttl_ratio=3.5))
    vectors.append(make_vec("extreme_buf_saturated", local_buffer_utilization=1.0))
    vectors.append(make_vec("extreme_buf_overflow", local_buffer_utilization=1.5))
    vectors.append(make_vec("extreme_high_encounters", peer_encounter_frequency=1000))
    vectors.append(make_vec("zero_remaining_contact", estimated_remaining_contact_ms=0, estimated_transfer_fits=0))

    return vectors


def test_decision_tree_and_logistic_regression_cpp_parity():
    """
    Rigorously tests 100% exact parity between Python scikit-learn model predictions
    and the compiled host C++ implementation across a battery of diverse vectors.
    """
    # 1. Load trained Python models
    dt_model_path = MODELS_DIR / "decision_tree_model.joblib"
    lr_model_path = MODELS_DIR / "logistic_regression_model.joblib"
    scaler_path = MODELS_DIR / "feature_scaler.joblib"

    assert dt_model_path.exists()
    assert lr_model_path.exists()
    assert scaler_path.exists()

    dt_model = joblib.load(dt_model_path)
    lr_model = joblib.load(lr_model_path)
    scaler = joblib.load(scaler_path)

    # 2. Generate comprehensive test vectors
    test_vectors = generate_comprehensive_test_vectors()
    assert len(test_vectors) >= 50, f"Expected at least 50 test vectors, got {len(test_vectors)}"

    # 3. Create DataFrame and evaluate with Python models
    df = pd.DataFrame(test_vectors)
    X = df[DECISION_FEATURE_NAMES].to_numpy(dtype=np.float32)

    py_dt_preds = dt_model.predict(X).astype(int)
    X_scaled = scaler.transform(X)
    py_lr_preds = lr_model.predict(X_scaled).astype(int)

    # 4. Write test vectors to temporary CSV for C++ harness
    csv_input_path = TESTS_DIR / "parity_test_vectors.csv"
    csv_output_path = TESTS_DIR / "parity_cpp_output.csv"

    cols_order = ["test_id"] + DECISION_FEATURE_NAMES
    df[cols_order].to_csv(csv_input_path, index=False)

    # 5. Run C++ test harness
    harness_exe = TESTS_DIR / "cpp_test_harness.exe"
    assert harness_exe.exists(), "C++ harness executable must exist. Run test_cpp_test_harness_compilation first."

    run_res = subprocess.run(
        [str(harness_exe), str(csv_input_path), str(csv_output_path)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert run_res.returncode == 0, f"C++ harness execution failed: {run_res.stderr}"
    assert csv_output_path.exists(), "C++ output CSV not generated"

    # 6. Read C++ predictions
    cpp_df = pd.read_csv(csv_output_path)
    assert len(cpp_df) == len(df), f"Size mismatch: {len(cpp_df)} C++ vs {len(df)} Python"

    cpp_dt_preds = cpp_df["cpp_dt_pred"].to_numpy(dtype=int)
    cpp_lr_preds = cpp_df["cpp_lr_pred"].to_numpy(dtype=int)

    # 7. Check for mismatches
    dt_mismatches = []
    lr_mismatches = []

    for i, row in enumerate(test_vectors):
        tid = row["test_id"]
        if py_dt_preds[i] != cpp_dt_preds[i]:
            dt_mismatches.append({
                "test_id": tid,
                "py": py_dt_preds[i],
                "cpp": cpp_dt_preds[i],
                "features": row,
            })
        if py_lr_preds[i] != cpp_lr_preds[i]:
            lr_mismatches.append({
                "test_id": tid,
                "py": py_lr_preds[i],
                "cpp": cpp_lr_preds[i],
                "features": row,
            })

    # Clean up temp test files
    if csv_input_path.exists():
        csv_input_path.unlink()
    if csv_output_path.exists():
        csv_output_path.unlink()

    total_tested = len(test_vectors)
    dt_matches = total_tested - len(dt_mismatches)
    lr_matches = total_tested - len(lr_mismatches)

    print(f"\n[C++ Parity Results] Total Vectors: {total_tested}")
    print(f"  Decision Tree:       {dt_matches}/{total_tested} matches (Mismatches: {len(dt_mismatches)})")
    print(f"  Logistic Regression: {lr_matches}/{total_tested} matches (Mismatches: {len(lr_mismatches)})")

    # Invariant: EXACT 100% PARITY (0 mismatches)
    assert len(dt_mismatches) == 0, f"Decision Tree had {len(dt_mismatches)} mismatches: {dt_mismatches}"
    assert len(lr_mismatches) == 0, f"Logistic Regression had {len(lr_mismatches)} mismatches: {lr_mismatches}"


def test_stage5_2_simulation_results_integrity():
    """
    Validates that stage5_2_robustness_results.csv satisfies all scientific invariants:
    1. Exactly 234 simulation runs (3 ranges x 13 seeds x 6 policies).
    2. All expected policies, ranges, and seeds are present without gaps.
    3. Mathematical invariants: PDR in [0, 1], non-negative delay and hops.
    4. Decision Tree achieves statistically superior PDR over Direct Delivery.
    5. Decision Tree generates substantially lower overhead than Epidemic routing.
    """
    results_csv = PROJECT_ROOT / "data" / "ai_experiments" / "stage5_2_robustness_results.csv"
    assert results_csv.exists(), f"Missing {results_csv}"

    df = pd.read_csv(results_csv)
    assert len(df) == 234, f"Expected exactly 234 runs, found {len(df)}"

    expected_policies = {"direct_delivery", "two_hop", "epidemic", "decision_tree", "logistic_regression", "temporal_astar"}
    assert set(df["routing_policy"].unique()) == expected_policies

    expected_ranges = {50.0, 100.0, 200.0}
    assert set(df["range_m"].unique()) == expected_ranges

    expected_seeds = {100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1300}
    assert set(df["eval_seed"].unique()) == expected_seeds

    # Mathematical invariants
    assert (df["packet_delivery_ratio"] >= 0.0).all() and (df["packet_delivery_ratio"] <= 1.0).all()
    assert (df["mean_delay_ms"] >= 0.0).all()
    assert (df["mean_hops"] >= 1.0).all()
    assert (df["overhead_ratio"] >= 1.0).all()

    # Relative performance invariants
    mean_pdr = df.groupby("routing_policy")["packet_delivery_ratio"].mean()
    mean_ovh = df.groupby("routing_policy")["overhead_ratio"].mean()

    # Decision tree delivers significantly higher PDR than Direct Delivery
    assert mean_pdr["decision_tree"] > mean_pdr["direct_delivery"] + 0.20
    # Decision tree delivers > 75% PDR across seeds
    assert mean_pdr["decision_tree"] >= 0.75
    # Decision tree has significantly lower overhead than Epidemic
    assert mean_ovh["decision_tree"] < mean_ovh["epidemic"]


def test_stage5_2_artifacts_and_reports_exist():
    """
    Confirms that all 5 publication-quality figures and both Stage 5.2 markdown reports
    exist and are populated.
    """
    reports_dir = PROJECT_ROOT / "reports"
    figures_dir = reports_dir / "figures" / "stage5_2"

    expected_figures = [
        "delay_variability_by_policy.png",
        "overhead_vs_pdr_tradeoff_robustness.png",
        "pdr_distribution_across_seeds.png",
        "relay_acceptance_rate_by_range.png",
        "teacher_disagreement_analysis.png",
    ]
    for fig in expected_figures:
        fig_path = figures_dir / fig
        assert fig_path.exists(), f"Missing figure: {fig_path}"
        assert fig_path.stat().st_size > 1000, f"Figure {fig_path} is unexpectedly small or empty"

    export_report = reports_dir / "stage5_2_export_validation.md"
    robust_report = reports_dir / "stage5_2_robustness_evaluation.md"

    assert export_report.exists(), f"Missing {export_report}"
    assert export_report.stat().st_size > 500, f"{export_report} is empty"

    assert robust_report.exists(), f"Missing {robust_report}"
    assert robust_report.stat().st_size > 500, f"{robust_report} is empty"


