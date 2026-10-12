"""
Test suite for Stage 2: Vannes Contact-Graph Generator.

Validates:
- Known node-position distance calculations
- Contact creation within range
- No contact outside range
- Contact interval start, end, and duration semantics
- Node inactivity, deletion, and missing positions handling
- Undirected duplicate contact prevention (canonical node_a < node_b)
- Timestamp monotonicity and temporal gap handling
- Malformed DGS record diagnostics and strict error handling
- Hand-constructed DGS fixture with verified expected results
- Processed CSV output schema and invariant validation
"""

import io
import math
import sys
from pathlib import Path
import pytest
import pandas as pd

# Ensure src directory is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vannes_contact_graph import (
    ContactGraphGenerator,
    ContactInterval,
    DGSParser,
    compute_euclidean_distance,
    process_vannes_dgs,
)


# -----------------------------------------------------------------------------
# 1. Known Distance Calculations
# -----------------------------------------------------------------------------

def test_known_node_position_distance_calculations():
    """Validates exact Euclidean distance calculations against known geometric values."""
    # 3-4-5 right triangle scaled to 30-40-50 meters
    assert compute_euclidean_distance(0.0, 0.0, 30.0, 40.0) == pytest.approx(50.0, rel=1e-6)

    # Negative coordinates
    assert compute_euclidean_distance(-100.0, -200.0, -100.0, -100.0) == pytest.approx(100.0, rel=1e-6)

    # Identical coordinates (zero distance)
    assert compute_euclidean_distance(123.456, -789.012, 123.456, -789.012) == pytest.approx(0.0, abs=1e-9)

    # Symmetry: d(u, v) == d(v, u)
    d1 = compute_euclidean_distance(15.2, -42.8, -89.4, 110.1)
    d2 = compute_euclidean_distance(-89.4, 110.1, 15.2, -42.8)
    assert d1 == pytest.approx(d2, rel=1e-9)


# -----------------------------------------------------------------------------
# 2. Contact Creation Within Range
# -----------------------------------------------------------------------------

def test_contact_creation_within_range():
    """Confirms contact intervals are created when distance is within configured range."""
    generator = ContactGraphGenerator(ranges_m=[50.0, 100.0])

    # Two nodes separated by 40 meters at step 1000
    generator.process_step(
        time_ms=1000,
        node_positions={"bus_1": (0.0, 0.0), "bus_2": (40.0, 0.0)},
    )
    generator.finalize()

    contacts_50 = generator.get_contacts(50.0)
    contacts_100 = generator.get_contacts(100.0)

    assert len(contacts_50) == 1
    assert len(contacts_100) == 1

    c = contacts_50[0]
    assert c.node_a == "bus_1"
    assert c.node_b == "bus_2"
    assert c.start_time_ms == 1000
    assert c.end_time_ms == 1000
    assert c.duration_ms == 0
    assert c.minimum_distance_m == pytest.approx(40.0, rel=1e-4)

    # Boundary test: exactly on threshold (50.0 meters)
    gen_boundary = ContactGraphGenerator(ranges_m=[50.0])
    gen_boundary.process_step(
        time_ms=2000,
        node_positions={"bus_a": (0.0, 0.0), "bus_b": (30.0, 40.0)},
    )
    gen_boundary.finalize()
    assert len(gen_boundary.get_contacts(50.0)) == 1
    assert gen_boundary.get_contacts(50.0)[0].minimum_distance_m == pytest.approx(50.0, rel=1e-4)


# -----------------------------------------------------------------------------
# 3. No Contact Outside Range
# -----------------------------------------------------------------------------

def test_no_contact_outside_range():
    """Confirms nodes outside configured range threshold do not generate contacts."""
    generator = ContactGraphGenerator(ranges_m=[50.0, 100.0])

    # Distance = 50.1 meters (just outside 50m, inside 100m)
    generator.process_step(
        time_ms=1000,
        node_positions={"bus_1": (0.0, 0.0), "bus_2": (50.1, 0.0)},
    )
    generator.finalize()

    assert len(generator.get_contacts(50.0)) == 0
    assert len(generator.get_contacts(100.0)) == 1

    # Distance = 500 meters (outside all ranges)
    gen_far = ContactGraphGenerator(ranges_m=[50.0, 100.0, 200.0])
    gen_far.process_step(
        time_ms=1000,
        node_positions={"bus_1": (0.0, 0.0), "bus_2": (500.0, 0.0)},
    )
    gen_far.finalize()
    for r in [50.0, 100.0, 200.0]:
        assert len(gen_far.get_contacts(r)) == 0


# -----------------------------------------------------------------------------
# 4. Contact Interval Start, End, and Duration Semantics
# -----------------------------------------------------------------------------

def test_contact_interval_start_and_end():
    """Validates start_time_ms, end_time_ms, duration_ms, and minimum_distance tracking."""
    generator = ContactGraphGenerator(ranges_m=[50.0])

    # Step 1000: Out of range (60m)
    generator.process_step(1000, {"bus_1": (0.0, 0.0), "bus_2": (60.0, 0.0)})
    # Step 2000: Enters range (40m) -> contact starts
    generator.process_step(2000, {"bus_1": (0.0, 0.0), "bus_2": (40.0, 0.0)})
    # Step 3000: Closer (20m) -> contact continues
    generator.process_step(3000, {"bus_1": (0.0, 0.0), "bus_2": (20.0, 0.0)})
    # Step 4000: Moves further but still in range (35m) -> contact continues
    generator.process_step(4000, {"bus_1": (0.0, 0.0), "bus_2": (35.0, 0.0)})
    # Step 5000: Out of range (70m) -> contact ends at step 4000
    generator.process_step(5000, {"bus_1": (0.0, 0.0), "bus_2": (70.0, 0.0)})
    generator.finalize()

    contacts = generator.get_contacts(50.0)
    assert len(contacts) == 1
    c = contacts[0]
    assert c.start_time_ms == 2000
    assert c.end_time_ms == 4000
    assert c.duration_ms == 2000
    assert c.duration_ms == c.end_time_ms - c.start_time_ms
    assert c.minimum_distance_m == pytest.approx(20.0, rel=1e-4)


# -----------------------------------------------------------------------------
# 5. Node Inactivity, Missing Positions, and Node Deletion
# -----------------------------------------------------------------------------

def test_node_inactivity_and_missing_positions():
    """Verifies unpositioned nodes (like line01-09) and deleted nodes are handled safely."""
    generator = ContactGraphGenerator(ranges_m=[50.0])

    # Step 1000: bus_1 and bus_2 in contact
    generator.process_step(
        1000,
        {"bus_1": (0.0, 0.0), "bus_2": (30.0, 0.0)},
    )
    # Step 2000: bus_2 is deleted/inactive (only bus_1 present)
    generator.process_step(
        2000,
        {"bus_1": (0.0, 0.0)},
    )
    generator.finalize()

    contacts = generator.get_contacts(50.0)
    assert len(contacts) == 1
    assert contacts[0].start_time_ms == 1000
    assert contacts[0].end_time_ms == 1000
    assert contacts[0].duration_ms == 0

    # Unpositioned node handling in DGS parser
    sample_dgs = io.StringIO(
        "DGS004\n"
        "SIMUL 0 0\n"
        "st 0\n"
        "an bus_with_pos x=10.0 y=20.0\n"
        "an bus_no_pos\n"
        "st 1000\n"
        "cn bus_with_pos x=10.5 y=20.5\n"
        "st 2000\n"
        "dn bus_no_pos\n"
    )
    parser = DGSParser()
    steps = list(parser.parse_stream(sample_dgs))

    assert "bus_no_pos" in parser.diagnostics.nodes_with_missing_positions
    assert "bus_no_pos" not in steps[0][1]  # Not in valid coordinates dict
    assert "bus_with_pos" in steps[0][1]


# -----------------------------------------------------------------------------
# 6. Duplicate Contact Prevention
# -----------------------------------------------------------------------------

def test_duplicate_contact_prevention():
    """Verifies contacts are strictly undirected and canonical (node_a < node_b)."""
    generator = ContactGraphGenerator(ranges_m=[50.0])

    generator.process_step(
        1000,
        {"zeta_bus": (0.0, 0.0), "alpha_bus": (10.0, 0.0)},
    )
    generator.finalize()

    contacts = generator.get_contacts(50.0)
    assert len(contacts) == 1
    # Lexicographically sorted: alpha_bus < zeta_bus
    assert contacts[0].node_a == "alpha_bus"
    assert contacts[0].node_b == "zeta_bus"


# -----------------------------------------------------------------------------
# 7. Timestamp Handling: Monotonicity and Gaps
# -----------------------------------------------------------------------------

def test_timestamp_handling():
    """Validates monotonicity checks, temporal gap tracking, and contact closure on gap."""
    # Test gap interruption closes active contact
    generator = ContactGraphGenerator(ranges_m=[50.0], max_gap_ms=3000)

    # Step 1000: In contact
    generator.process_step(1000, {"b1": (0.0, 0.0), "b2": (20.0, 0.0)})
    # Step 2000: Still in contact
    generator.process_step(2000, {"b1": (0.0, 0.0), "b2": (20.0, 0.0)})
    # Gap of 40,000 ms to step 42000 (> max_gap_ms 3000)
    generator.process_step(42000, {"b1": (0.0, 0.0), "b2": (20.0, 0.0)})
    generator.finalize()

    contacts = generator.get_contacts(50.0)
    # Must be 2 separate intervals because the gap was unobserved
    assert len(contacts) == 2
    assert contacts[0].start_time_ms == 1000
    assert contacts[0].end_time_ms == 2000
    assert contacts[0].duration_ms == 1000

    assert contacts[1].start_time_ms == 42000
    assert contacts[1].end_time_ms == 42000

    # Non-monotonic timestamp in parser
    non_monotonic_dgs = io.StringIO(
        "DGS004\n"
        "SIMUL 0 0\n"
        "st 2000\n"
        "an b1 x=0 y=0\n"
        "st 1000\n"  # Decreasing!
        "cn b1 x=1 y=1\n"
    )
    # Non-strict mode records diagnostic
    parser = DGSParser(strict=False)
    list(parser.parse_stream(non_monotonic_dgs))
    assert len(parser.diagnostics.malformed_records) > 0

    # Strict mode raises ValueError
    non_monotonic_dgs.seek(0)
    strict_parser = DGSParser(strict=True)
    with pytest.raises(ValueError, match="Non-monotonic timestamp"):
        list(strict_parser.parse_stream(non_monotonic_dgs))


# -----------------------------------------------------------------------------
# 8. Malformed DGS Records
# -----------------------------------------------------------------------------

def test_malformed_dgs_records():
    """Validates parser resilience against corrupted DGS commands and values."""
    corrupted_dgs = io.StringIO(
        "DGS004\n"
        "SIMUL 0 0\n"
        "st 0\n"
        "an b1 x=invalid_float y=10.0\n"
        "st 1000\n"
        "unknown_cmd b1 123\n"
        "an\n"  # missing node ID
        "cn b1 x=20.0 y=30.0\n"
    )
    parser = DGSParser(strict=False)
    steps = list(parser.parse_stream(corrupted_dgs))

    assert len(parser.diagnostics.malformed_records) >= 3
    # Valid step at 1000 still processed
    assert len(steps) == 2
    assert "b1" in steps[1][1]
    assert steps[1][1]["b1"] == (20.0, 30.0)


# -----------------------------------------------------------------------------
# 9. Hand-Constructed DGS Fixture With Known Expected Results
# -----------------------------------------------------------------------------

def test_hand_constructed_dgs_fixture():
    """
    Constructs a controlled DGS trace fixture with known trajectories:
      - nodeA: moves progressively away from nodeB
      - nodeB: stationary at (30, 40)
      - nodeC: stationary far away at (1000, 1000)
      - nodeD: added without coordinates (missing position)
    
    Verifies exact expected contact start, end, duration, and min distance across ranges.
    """
    fixture_dgs = io.StringIO(
        "DGS004\n"
        "TEST_GRAPH 0 0\n"
        "cg area=\"car:-1000,-1000,2000,2000:47.0,-2.0\"\n"
        "cg ref_time=\"1000000\"\n"
        "st 0\n"
        "an nodeA x=0.0 y=0.0\n"
        "an nodeB x=30.0 y=40.0\n"
        "an nodeC x=1000.0 y=1000.0\n"
        "an nodeD\n"
        "st 1000\n"
        "cn nodeA x=0.0 y=20.0\n"
        "st 2000\n"
        "cn nodeA x=0.0 y=50.0\n"
        "st 3000\n"
        "cn nodeA x=0.0 y=100.0\n"
        "st 4000\n"
        "cn nodeA x=0.0 y=300.0\n"
        "st 5000\n"
        "dn nodeC\n"
    )

    parser = DGSParser(strict=True)
    generator = ContactGraphGenerator(ranges_m=[50.0, 100.0, 200.0])

    for time_ms, positions in parser.parse_stream(fixture_dgs):
        generator.process_step(time_ms, positions)
    generator.finalize()

    # Distances between nodeA and nodeB over time:
    # t=0:    (0, 0)   to (30, 40)  -> d = sqrt(30^2 + 40^2) = 50.0 m
    # t=1000: (0, 20)  to (30, 40)  -> d = sqrt(30^2 + 20^2) = sqrt(1300) = 36.0555 m
    # t=2000: (0, 50)  to (30, 40)  -> d = sqrt(30^2 + 10^2) = sqrt(1000) = 31.6228 m (min!)
    # t=3000: (0, 100) to (30, 40)  -> d = sqrt(30^2 + 60^2) = sqrt(4500) = 67.0820 m
    # t=4000: (0, 300) to (30, 40)  -> d = sqrt(30^2 + 260^2) = 261.725 m (out of all ranges)
    # t=5000: nodeC deleted

    # Range 50m: in range at t=0, 1000, 2000 (d <= 50m). Out of range at 3000.
    c_50 = generator.get_contacts(50.0)
    assert len(c_50) == 1
    assert c_50[0].node_a == "nodeA"
    assert c_50[0].node_b == "nodeB"
    assert c_50[0].start_time_ms == 0
    assert c_50[0].end_time_ms == 2000
    assert c_50[0].duration_ms == 2000
    assert c_50[0].minimum_distance_m == pytest.approx(math.sqrt(1000), rel=1e-4)

    # Range 100m: in range at t=0, 1000, 2000, 3000 (d <= 100m). Out of range at 4000.
    c_100 = generator.get_contacts(100.0)
    assert len(c_100) == 1
    assert c_100[0].start_time_ms == 0
    assert c_100[0].end_time_ms == 3000
    assert c_100[0].duration_ms == 3000
    assert c_100[0].minimum_distance_m == pytest.approx(math.sqrt(1000), rel=1e-4)

    # Range 200m: in range at t=0, 1000, 2000, 3000 (d <= 200m). Out of range at 4000 (261.7m).
    c_200 = generator.get_contacts(200.0)
    assert len(c_200) == 1
    assert c_200[0].start_time_ms == 0
    assert c_200[0].end_time_ms == 3000
    assert c_200[0].duration_ms == 3000
    assert c_200[0].minimum_distance_m == pytest.approx(math.sqrt(1000), rel=1e-4)

    # Verify nodeD generated 0 contacts
    for r in [50.0, 100.0, 200.0]:
        for c in generator.get_contacts(r):
            assert c.node_a != "nodeD"
            assert c.node_b != "nodeD"


# -----------------------------------------------------------------------------
# 10. Processed Real Output CSV Validation
# -----------------------------------------------------------------------------

def test_vannes_processed_csv_integrity():
    """Validates the schema, mathematical invariants, and consistency of generated CSVs."""
    expected_cols = [
        "dataset_id",
        "range_m",
        "node_a",
        "node_b",
        "start_time_ms",
        "end_time_ms",
        "duration_ms",
        "minimum_distance_m",
    ]

    for r in [50, 100, 200]:
        csv_file = PROJECT_ROOT / "data" / "processed" / f"vannes_contacts_{r}m.csv"
        assert csv_file.is_file(), f"Output file missing: {csv_file}"

        df = pd.read_csv(csv_file)
        assert list(df.columns) == expected_cols
        assert len(df) > 0

        # Mathematical invariants
        assert (df["duration_ms"] == df["end_time_ms"] - df["start_time_ms"]).all()
        assert (df["start_time_ms"] <= df["end_time_ms"]).all()
        assert (df["minimum_distance_m"] <= float(r)).all()
        assert (df["node_a"] < df["node_b"]).all()
        assert (df["range_m"] == float(r)).all()
        assert (df["dataset_id"] == "vannes").all()

    # Monotonicity checks across ranges
    df_50 = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "vannes_contacts_50m.csv")
    df_100 = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "vannes_contacts_100m.csv")
    df_200 = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "vannes_contacts_200m.csv")

    assert len(df_50) <= len(df_100) <= len(df_200)
    assert df_50["duration_ms"].mean() <= df_100["duration_ms"].mean() <= df_200["duration_ms"].mean()

