"""
Test suite for DTN AI Routing Dataset Inspection Tool.

Tests:
- Archive listing and safe extraction
- Path traversal rejection (Zip Slip / Tar traversal prevention)
- Redundant extraction avoidance
- Supported formats (CSV, DGS, Haggle DAT, TXT)
- Graceful handling of missing folders
- Robust parsing of malformed records
- Feature classification matrix completeness and validity
"""

import os
import sys
import json
import zipfile
import tarfile
import tempfile
from pathlib import Path
import pytest

# Ensure scripts directory is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from inspect_datasets import (
    ArchiveInspector,
    DataInspector,
    FeatureClassifier,
    ReportGenerator,
    locate_project_root,
    run_pipeline,
    STATUS_DIRECTLY_OBSERVED,
    STATUS_DERIVABLE,
    STATUS_NOT_AVAILABLE,
    STATUS_NOT_YET_DETERMINED,
    VALID_FEATURE_STATUSES,
    REQUIRED_ROUTING_FEATURES,
)


# -----------------------------------------------------------------------------
# 1. Archive Inspection and Security Tests
# -----------------------------------------------------------------------------
def test_archive_inspection_zip(tmp_path: Path):
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("folder/sample.txt", "hello dtn")
        zf.writestr("data.csv", "a,b\n1,2")

    members = ArchiveInspector.list_archive(zip_path)
    assert len(members) == 2
    names = [m["name"] for m in members]
    assert "folder/sample.txt" in names
    assert "data.csv" in names

    dest_dir = tmp_path / "extracted_zip"
    extracted, files, errors = ArchiveInspector.safe_extract(zip_path, dest_dir)
    assert extracted is True
    assert len(errors) == 0
    assert (dest_dir / "folder" / "sample.txt").read_text() == "hello dtn"
    assert (dest_dir / "data.csv").read_text() == "a,b\n1,2"


def test_archive_inspection_tar(tmp_path: Path):
    tar_path = tmp_path / "test.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        data = b"node1 100 200\n"
        ti = tarfile.TarInfo("traces/test.dat")
        ti.size = len(data)
        import io
        tf.addfile(ti, io.BytesIO(data))

    members = ArchiveInspector.list_archive(tar_path)
    assert len(members) == 1
    assert members[0]["name"] == "traces/test.dat"

    dest_dir = tmp_path / "extracted_tar"
    extracted, files, errors = ArchiveInspector.safe_extract(tar_path, dest_dir)
    assert extracted is True
    assert len(errors) == 0
    assert (dest_dir / "traces" / "test.dat").read_bytes() == b"node1 100 200\n"


def test_path_traversal_prevention_zip(tmp_path: Path):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    # Test path guard function directly
    assert ArchiveInspector.is_safe_path(dest_dir, dest_dir / "valid.txt") is True
    assert ArchiveInspector.is_safe_path(dest_dir, dest_dir / "sub" / "valid.txt") is True
    assert ArchiveInspector.is_safe_path(dest_dir, dest_dir / ".." / "evil.txt") is False

    # Create a zip containing a traversal path entry
    zip_path = tmp_path / "traversal.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../escaped.txt", "attack payload")
        zf.writestr("safe.txt", "safe payload")

    extracted, files, errors = ArchiveInspector.safe_extract(zip_path, dest_dir)
    assert len(errors) > 0
    assert any("Blocked path traversal" in e for e in errors)
    assert not (tmp_path / "escaped.txt").exists()
    assert (dest_dir / "safe.txt").exists()


def test_redundant_extraction_skipping(tmp_path: Path):
    zip_path = tmp_path / "cache_test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("payload.txt", "data 123")

    dest_dir = tmp_path / "cache_dest"
    manifest_path = dest_dir / ".manifest.json"

    # First extraction
    extracted1, files1, errors1 = ArchiveInspector.safe_extract(zip_path, dest_dir, manifest_path)
    assert extracted1 is True
    assert len(files1) == 1

    # Second extraction without changes
    extracted2, files2, errors2 = ArchiveInspector.safe_extract(zip_path, dest_dir, manifest_path)
    assert extracted2 is False
    assert len(errors2) == 0


# -----------------------------------------------------------------------------
# 2. Supported Formats Inspection Tests
# -----------------------------------------------------------------------------
def test_supported_format_csv(tmp_path: Path):
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("time,lat,long,cell_id,datarate\n2020-01-01 00:00:00,47.8,13.0,123,5000000.0\n")

    profile = DataInspector.inspect_csv(csv_file)
    assert profile["status"] == "Success"
    assert profile["format"] == "CSV"
    assert profile["rows"] == 1
    assert profile["columns"] == 5
    assert "cell_id" in profile["candidate_node_ids"]
    assert "time" in profile["timestamp_fields"]
    assert "lat" in profile["position_fields"]


def test_supported_format_dgs(tmp_path: Path):
    dgs_file = tmp_path / "sample.dgs"
    dgs_file.write_text(
        "DGS004\n"
        "SIMUL 0 0\n"
        'cg ref_time="19500000"\n'
        'cg area="car:0,0,10,10:47.6,-2.7"\n'
        "st 0\n"
        "an line01-01 x=100.0 y=200.0\n"
        "st 1000\n"
        "cn line01-01 x=105.0 y=202.0\n"
        "dn line01-01\n"
    )

    profile = DataInspector.inspect_dgs(dgs_file)
    assert profile["status"] == "Success"
    assert profile["format"] == "DGS (Dynamic Graph Stream)"
    assert profile["unique_nodes"] == 1
    assert "line01-01" in profile["sample_nodes"]
    assert profile["ref_time_ms"] == "19500000"
    assert profile["events_breakdown"]["st"] == 2
    assert profile["events_breakdown"]["cn"] == 1


def test_supported_format_haggle_dat(tmp_path: Path):
    haggle_dir = tmp_path / "haggle_data"
    sub_dir = haggle_dir / "SR-10mins-Students"
    sub_dir.mkdir(parents=True)

    dat_file = sub_dir / "1.dat"
    dat_file.write_text("10 1130000000 1130000600\n20 1130001000 1130001600\n")

    profile = DataInspector.inspect_haggle_directory(haggle_dir)
    assert profile["status"] == "Success"
    assert profile["rows"] == 2
    assert profile["columns"] == 3
    assert profile["unique_observer_nodes"] == 1
    assert profile["unique_seen_nodes"] == 2


def test_generic_and_unknown_formats(tmp_path: Path):
    txt_file = tmp_path / "README.txt"
    txt_file.write_text("Dataset documentation guidelines\nLine 2")
    txt_prof = DataInspector.inspect_generic_file(txt_file)
    assert txt_prof["format"] == "Text Documentation"
    assert txt_prof["rows"] == 2

    bin_file = tmp_path / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03")
    bin_prof = DataInspector.inspect_generic_file(bin_file)
    assert bin_prof["status"] == "Unsupported"
    assert "recommendation" in bin_prof


# -----------------------------------------------------------------------------
# 3. Robustness Tests (Malformed Records & Missing Folders)
# -----------------------------------------------------------------------------
def test_missing_folders_handling(tmp_path: Path):
    # Empty workspace with no data/raw folders
    empty_root = tmp_path / "empty_project"
    empty_root.mkdir()

    res = run_pipeline(empty_root)
    assert res["raw_status"]["vannes"]["present"] is False
    assert res["raw_status"]["haggle"]["present"] is False
    assert res["raw_status"]["salzburg"]["present"] is False
    assert len(res["archives"]) == 0


def test_malformed_records_handling(tmp_path: Path):
    # DGS with garbage lines
    bad_dgs = tmp_path / "malformed.dgs"
    bad_dgs.write_text("st NOT_A_NUMBER\nan\n\n\ncn\n")
    prof_dgs = DataInspector.inspect_dgs(bad_dgs)
    assert prof_dgs["status"] == "Success"
    assert prof_dgs["malformed_lines"] > 0

    # Haggle with incomplete records
    bad_haggle = tmp_path / "bad_haggle"
    bad_haggle.mkdir()
    (bad_haggle / "99.dat").write_text("single_column\nonly two columns\n100 NOT_INT NOT_INT\n")
    prof_haggle = DataInspector.inspect_haggle_directory(bad_haggle)
    assert prof_haggle["status"] == "Success"
    assert prof_haggle["malformed_lines"] == 3


# -----------------------------------------------------------------------------
# 4. Feature Classification Tests
# -----------------------------------------------------------------------------
def test_feature_classification():
    matrix = FeatureClassifier.get_feature_matrix()
    assert len(matrix) == len(REQUIRED_ROUTING_FEATURES)

    for item in matrix:
        assert item["Feature"] in REQUIRED_ROUTING_FEATURES
        assert item["Vannes_Bus"] in VALID_FEATURE_STATUSES
        assert item["Haggle_Cambridge"] in VALID_FEATURE_STATUSES
        assert item["Salzburg_LTE"] in VALID_FEATURE_STATUSES
        assert len(item["Rationale_and_Source_Fields"]) > 0

    # Check specific ground truths
    node_id_item = next(i for i in matrix if i["Feature"] == "Node identity")
    assert node_id_item["Vannes_Bus"] == STATUS_DIRECTLY_OBSERVED
    assert node_id_item["Haggle_Cambridge"] == STATUS_DIRECTLY_OBSERVED
    assert node_id_item["Salzburg_LTE"] == STATUS_DIRECTLY_OBSERVED

    pos_item = next(i for i in matrix if i["Feature"] == "Node positions")
    assert pos_item["Haggle_Cambridge"] == STATUS_NOT_AVAILABLE
    assert pos_item["Vannes_Bus"] == STATUS_DIRECTLY_OBSERVED

    sig_item = next(i for i in matrix if i["Feature"] == "Signal quality")
    assert sig_item["Salzburg_LTE"] == STATUS_DIRECTLY_OBSERVED
    assert sig_item["Vannes_Bus"] == STATUS_NOT_AVAILABLE
    assert sig_item["Haggle_Cambridge"] == STATUS_NOT_AVAILABLE
