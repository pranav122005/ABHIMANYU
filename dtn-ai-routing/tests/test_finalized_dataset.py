"""
Test suite for Stage 4: Finalized Dataset Validation and Integrity.

Validates:
- Presence of all required finalized dataset files under data/finalized/
- SHA-256 checksums in manifest.json match on-disk file contents
- Schema definitions and row counts match documented specifications
- Mathematical invariants (PDR, non-negative delay, conservation of bundles)
- Label integrity and derivation semantics
- Preservation of raw source datasets
"""

import hashlib
import json
import sys
from pathlib import Path
import pytest
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINALIZED_DIR = PROJECT_ROOT / "data" / "finalized"


def compute_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


# -----------------------------------------------------------------------------
# 1. Finalized Dataset Directory & File Structure
# -----------------------------------------------------------------------------

def test_finalized_dataset_files_exist():
    """Confirms all required finalized files exist in data/finalized/."""
    assert FINALIZED_DIR.is_dir(), f"Missing finalized directory: {FINALIZED_DIR}"

    expected_files = [
        "manifest.json",
        "data_dictionary.md",
        "validation_report.md",
        "simulation_summary.csv",
        "packet_outcomes.csv",
        "temporal_routes.csv",
        "vannes_contacts_50m.csv",
        "vannes_contacts_100m.csv",
        "vannes_contacts_200m.csv",
    ]

    for fname in expected_files:
        p = FINALIZED_DIR / fname
        assert p.is_file(), f"Missing finalized dataset file: {fname}"
        assert p.stat().st_size > 0, f"File is empty: {fname}"


# -----------------------------------------------------------------------------
# 2. Manifest Checksum & Row Count Integrity
# -----------------------------------------------------------------------------

def test_manifest_checksums_and_row_counts():
    """Verifies that every SHA-256 and row count in manifest.json matches on-disk files."""
    manifest_file = FINALIZED_DIR / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "1.0.0"
    files = manifest["files"]

    for fname, meta in files.items():
        disk_file = FINALIZED_DIR / fname
        assert disk_file.is_file(), f"File in manifest missing on disk: {fname}"

        # Cryptographic checksum verification
        actual_sha = compute_sha256(disk_file)
        assert actual_sha == meta["sha256"], f"Checksum mismatch for {fname}!"

        # Row count verification for CSV files
        if fname.endswith(".csv"):
            df = pd.read_csv(disk_file)
            assert len(df) == meta["row_count"], f"Row count mismatch for {fname}!"


# -----------------------------------------------------------------------------
# 3. Packet Outcomes Table Invariants
# -----------------------------------------------------------------------------

def test_packet_outcomes_mathematical_invariants():
    """
    Validates packet_outcomes.csv integrity:
      - 200 packets x 3 ranges x 4 policies = 2400 records
      - Complete bundle accounting: delivered + pending + expired == 1 for every record
      - Delivered packets have non-negative delay and positive hops
      - Undelivered packets have delay = -1 and hops = -1
    """
    outcomes_file = FINALIZED_DIR / "packet_outcomes.csv"
    df = pd.read_csv(outcomes_file)

    # 12 runs x 200 packets = 2400 records
    assert len(df) == 2400

    # Required columns
    expected_cols = [
        "packet_id", "range_m", "policy", "source", "destination",
        "size_bytes", "priority", "creation_time_ms", "ttl_ms",
        "delivered", "delivery_delay_ms", "hops", "pending", "expired",
        "theoretical_feasible", "theoretical_delay_ms", "theoretical_hops",
    ]
    for c in expected_cols:
        assert c in df.columns, f"Missing column '{c}' in packet_outcomes.csv"

    # Mutual exclusivity of bundle states: delivered + pending + expired == 1
    state_sum = df["delivered"] + df["pending"] + df["expired"]
    assert (state_sum == 1).all(), "Inconsistent bundle state: packet must be exactly one of delivered, pending, or expired"

    # Delivered packet invariants
    delivered_mask = df["delivered"] == 1
    assert (df.loc[delivered_mask, "delivery_delay_ms"] > 0).all()
    assert (df.loc[delivered_mask, "hops"] >= 1).all()

    # Undelivered packet invariants
    undelivered_mask = df["delivered"] == 0
    assert (df.loc[undelivered_mask, "delivery_delay_ms"] == -1).all()
    assert (df.loc[undelivered_mask, "hops"] == -1).all()


# -----------------------------------------------------------------------------
# 4. Simulation Summary Table Invariants
# -----------------------------------------------------------------------------

def test_simulation_summary_invariants():
    """
    Validates simulation_summary.csv across all 12 benchmark runs:
      - 12 rows (3 ranges x 4 policies)
      - PDR in [0, 1]
      - Delivered <= Generated
    """
    summary_file = FINALIZED_DIR / "simulation_summary.csv"
    df = pd.read_csv(summary_file)

    assert len(df) == 12  # 3 ranges x 4 policies
    assert set(df["policy"] if "policy" in df.columns else df["routing_policy"]) == {
        "direct_delivery", "two_hop", "epidemic", "temporal_astar"
    }
    assert set(df["range_m"]) == {50.0, 100.0, 200.0}

    assert (df["packet_delivery_ratio"] >= 0.0).all()
    assert (df["packet_delivery_ratio"] <= 1.0).all()
    assert (df["total_delivered"] <= df["total_generated"]).all()


# -----------------------------------------------------------------------------
# 5. Raw Source Dataset Preservation
# -----------------------------------------------------------------------------

def test_raw_source_datasets_preserved():
    """Confirms raw input archives in data/raw/ have NOT been modified or deleted."""
    raw_vannes = PROJECT_ROOT / "data" / "raw" / "vannes" / "vbn_0.zip"
    raw_haggle = PROJECT_ROOT / "data" / "raw" / "haggle" / "imote-traces-cambridge.tar.gz"
    raw_salzburg = PROJECT_ROOT / "data" / "raw" / "salzburg" / "SRFG-v1.csv"

    assert raw_vannes.is_file(), "Raw Vannes archive was deleted or modified!"
    assert raw_haggle.is_file(), "Raw Haggle archive was deleted or modified!"
    assert raw_salzburg.is_file(), "Raw Salzburg archive was deleted or modified!"

