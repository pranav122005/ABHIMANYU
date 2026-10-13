"""
Test suite for Stage 3: Discrete-Event DTN Simulator.

Validates:
- Contact-window boundaries
- Transfers that fit or do not fit within a contact
- Buffer exhaustion and drop handling
- Packet expiry and TTL enforcement
- Duplicate suppression
- Delivery accounting and metric consistency
- Deterministic reproducibility with a fixed seed
- Malformed input and empty contact graphs
- Routing policy differentiation (Epidemic vs Direct Delivery)
- Output CSV schemas and report generation
"""

import io
import math
import sys
import tempfile
from pathlib import Path
import pytest
import pandas as pd

# Ensure src directory is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dtn_simulator import (
    ContactRecord,
    DirectDeliveryRouter,
    DTNNode,
    DTNSimulator,
    EpidemicRouter,
    NodeBuffer,
    Packet,
    SimulationMetrics,
    TwoHopRelayRouter,
)


# -----------------------------------------------------------------------------
# 1. Contact-Window Boundaries & Fitting
# -----------------------------------------------------------------------------

def test_contact_window_boundaries_and_fit(tmp_path: Path):
    """
    Tests that transfers fit if within contact window and fail/truncate if
    transfer duration exceeds available contact window.
    """
    # Create contact CSV with one contact between A and B from 1000 to 1100 ms (duration 100 ms)
    contact_csv = tmp_path / "contact_boundary.csv"
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "vannes,50.0,nodeA,nodeB,1000,1100,100,10.0\n"
    )

    # 1. Packet transfer time = 50 ms overhead + ceil(10,000 * 1000 / 250,000) = 50 + 40 = 90 ms
    # 90 ms <= 100 ms -> Fits!
    sim_fits = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        routing_policy="epidemic",
        transfer_rate_bytes_sec=250_000.0,
        transfer_overhead_ms=50,
    )
    workload_fits = [
        Packet(
            packet_id="pkt_fit",
            source="nodeA",
            destination="nodeB",
            size_bytes=10_000,
            priority=1,
            creation_time_ms=500,
            ttl_ms=10_000,
        )
    ]
    metrics_fits = sim_fits.run(traffic_workload=workload_fits)
    assert metrics_fits.total_delivered == 1
    assert metrics_fits.packet_delivery_ratio == 1.0
    assert metrics_fits.truncated_contact_attempts == 0

    # 2. Packet of size 20,000 bytes:
    # 50 ms overhead + ceil(20,000 * 1000 / 250,000) = 50 + 80 = 130 ms.
    # 130 ms > 100 ms -> Does NOT fit within contact!
    sim_overflow = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        routing_policy="epidemic",
        transfer_rate_bytes_sec=250_000.0,
        transfer_overhead_ms=50,
    )
    workload_overflow = [
        Packet(
            packet_id="pkt_too_large",
            source="nodeA",
            destination="nodeB",
            size_bytes=20_000,
            priority=1,
            creation_time_ms=500,
            ttl_ms=10_000,
        )
    ]
    metrics_overflow = sim_overflow.run(traffic_workload=workload_overflow)
    assert metrics_overflow.total_delivered == 0
    assert metrics_overflow.packet_delivery_ratio == 0.0
    assert metrics_overflow.truncated_contact_attempts == 1
    assert metrics_overflow.failed_transfers == 1


# -----------------------------------------------------------------------------
# 2. Buffer Exhaustion and Dropped Packets
# -----------------------------------------------------------------------------

def test_buffer_exhaustion_and_drop_handling(tmp_path: Path):
    """
    Validates finite buffer constraints: packets exceeding buffer capacity
    are rejected upon generation or transfer attempt.
    """
    # Buffer unit test
    buf = NodeBuffer(capacity_bytes=15_000)
    p1 = Packet("p1", "s", "d", 10_000, 1, 0, 5000)
    p2 = Packet("p2", "s", "d", 10_000, 1, 0, 5000)

    assert buf.can_fit(p1.size_bytes) is True
    assert buf.add(p1) is True
    assert buf.current_bytes == 10_000
    assert buf.available_bytes == 5_000
    assert buf.utilization == pytest.approx(10_000 / 15_000)

    # p2 needs 10_000 bytes, only 5_000 available
    assert buf.can_fit(p2.size_bytes) is False
    assert buf.add(p2) is False
    assert buf.current_bytes == 10_000  # Unchanged

    # Simulator integration test: receiver buffer full
    contact_csv = tmp_path / "contact_buffer.csv"
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "vannes,50.0,nodeS,nodeR,1000,5000,4000,10.0\n"
    )

    sim = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        buffer_capacity_bytes=15_000,  # 15 KB
        routing_policy="epidemic",
        transfer_rate_bytes_sec=1_000_000.0,
        transfer_overhead_ms=10,
    )
    # Workload: 2 packets of 10 KB intended for nodeD through relay nodeR
    workload = [
        Packet("pkt_1", "nodeS", "nodeD", 10_000, 1, 100, 10_000),
        Packet("pkt_2", "nodeS", "nodeD", 10_000, 1, 100, 10_000),
    ]
    metrics = sim.run(traffic_workload=workload)
    # First packet stored in nodeR, second rejected due to BUFFER_FULL
    assert metrics.successful_transfers == 1
    assert metrics.buffer_dropped_packets == 1


# -----------------------------------------------------------------------------
# 3. Packet Expiry (TTL Enforcement)
# -----------------------------------------------------------------------------

def test_packet_expiry_and_pruning(tmp_path: Path):
    """
    Validates that expired packets are purged from buffers and not forwarded.
    """
    contact_csv = tmp_path / "contact_expiry.csv"
    # Contact occurs at 5000 ms
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "vannes,50.0,nodeA,nodeB,5000,6000,1000,10.0\n"
    )

    sim = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        routing_policy="epidemic",
    )
    # Packet created at 1000 ms with TTL of 2000 ms (expires at 3000 ms)
    # By contact time 5000 ms, packet is already expired!
    workload = [
        Packet("pkt_exp", "nodeA", "nodeB", 1000, 1, 1000, 2000)
    ]
    metrics = sim.run(traffic_workload=workload)
    assert metrics.total_delivered == 0
    assert metrics.expired_undelivered == 1
    assert metrics.total_expired_copies >= 1
    assert metrics.forwarding_attempts == 0


# -----------------------------------------------------------------------------
# 4. Duplicate Forwarding Suppression
# -----------------------------------------------------------------------------

def test_duplicate_forwarding_suppression(tmp_path: Path):
    """
    Confirms that once a node receives or delivers a packet, subsequent
    contacts do not re-transfer the identical packet.
    """
    contact_csv = tmp_path / "contact_duplicate.csv"
    # Two sequential contacts between nodeA and nodeB
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "vannes,50.0,nodeA,nodeB,1000,2000,1000,10.0\n"
        "vannes,50.0,nodeA,nodeB,5000,6000,1000,10.0\n"
    )

    sim = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        routing_policy="epidemic",
    )
    workload = [
        Packet("pkt_dup", "nodeA", "nodeB", 1000, 1, 500, 10_000)
    ]
    metrics = sim.run(traffic_workload=workload)

    # Transferred and delivered during contact 1
    assert metrics.total_delivered == 1
    # Must NOT be transferred again during contact 2!
    assert metrics.forwarding_attempts == 1
    assert metrics.successful_transfers == 1


# -----------------------------------------------------------------------------
# 5. Delivery Accounting and Metrics Consistency
# -----------------------------------------------------------------------------

def test_delivery_accounting_and_metrics_consistency(tmp_path: Path):
    """
    Verifies metric formulas:
      PDR = delivered / generated
      delay = delivery_time - creation_time
      delay distribution statistics
    """
    contact_csv = tmp_path / "contact_accounting.csv"
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "vannes,50.0,nodeA,nodeB,1000,3000,2000,10.0\n"
    )

    sim = DTNSimulator(
        contact_csv_path=contact_csv,
        range_m=50.0,
        transfer_rate_bytes_sec=1_000_000.0,
        transfer_overhead_ms=0,
    )
    # Packet size 1000 B at 1 MB/s -> 1 ms transfer time
    # Creation time: 800 ms. Delivery time: 1000 + 1 = 1001 ms.
    # Delay = 1001 - 800 = 201 ms.
    workload = [
        Packet("pkt_acc", "nodeA", "nodeB", 1000, 1, 800, 10_000)
    ]
    metrics = sim.run(traffic_workload=workload)

    assert metrics.total_generated == 1
    assert metrics.total_delivered == 1
    assert metrics.packet_delivery_ratio == 1.0
    assert metrics.delivery_delays_ms == [201]
    assert metrics.mean_delay_ms == 201.0
    assert metrics.median_delay_ms == 201.0
    assert metrics.min_delay_ms == 201
    assert metrics.max_delay_ms == 201
    assert metrics.mean_hops == 1.0


# -----------------------------------------------------------------------------
# 6. Deterministic Reproducibility With Fixed Seed
# -----------------------------------------------------------------------------

def test_deterministic_reproducibility(tmp_path: Path):
    """
    Confirms identical workload and metrics when running with identical seed,
    and divergent workload when running with different seeds.
    """
    contact_csv = PROJECT_ROOT / "data" / "processed" / "vannes_contacts_50m.csv"
    if not contact_csv.is_file():
        pytest.skip("vannes_contacts_50m.csv not present")

    sim1 = DTNSimulator(contact_csv, seed=42)
    m1 = sim1.run(num_packets=50)

    sim2 = DTNSimulator(contact_csv, seed=42)
    m2 = sim2.run(num_packets=50)

    assert m1.total_generated == m2.total_generated
    assert m1.total_delivered == m2.total_delivered
    assert m1.packet_delivery_ratio == m2.packet_delivery_ratio
    assert m1.mean_delay_ms == m2.mean_delay_ms
    assert m1.forwarding_attempts == m2.forwarding_attempts

    # Different seed produces different packet set
    sim3 = DTNSimulator(contact_csv, seed=999)
    traffic1 = sim1.generate_traffic(num_packets=10)
    traffic3 = sim3.generate_traffic(num_packets=10)
    assert [p.packet_id for p in traffic1] != [p.packet_id for p in traffic3]


# -----------------------------------------------------------------------------
# 7. Malformed Input and Empty Contact Graphs
# -----------------------------------------------------------------------------

def test_malformed_input_and_empty_contact_graphs(tmp_path: Path):
    """
    Tests graceful degradation on empty contact CSV, missing file,
    and missing schema columns.
    """
    # 1. Non-existent file
    sim_missing = DTNSimulator(tmp_path / "non_existent.csv")
    with pytest.raises(FileNotFoundError):
        sim_missing.load_contacts()

    # 2. Empty CSV
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("")
    sim_empty = DTNSimulator(empty_csv)
    contacts = sim_empty.load_contacts()
    assert contacts == []
    m_empty = sim_empty.run(traffic_workload=[])
    assert m_empty.total_contacts == 0
    assert m_empty.total_delivered == 0

    # 3. Malformed columns
    malformed_csv = tmp_path / "malformed.csv"
    malformed_csv.write_text("dataset_id,range_m,only_some_cols\nvannes,50,bad\n")
    sim_malformed = DTNSimulator(malformed_csv)
    with pytest.raises(ValueError, match="Missing required columns"):
        sim_malformed.load_contacts()


# -----------------------------------------------------------------------------
# 8. Routing Policy Differentiation: Epidemic vs Direct Delivery
# -----------------------------------------------------------------------------

def test_routing_policy_differentiation(tmp_path: Path):
    """
    Verifies that DirectDelivery only forwards directly to destination,
    while Epidemic utilizes intermediate relay nodes.
    
    Topology:
      - nodeS -> nodeR at 1000 ms
      - nodeR -> nodeD at 3000 ms
      (nodeS never directly meets nodeD)
    """
    contact_csv = tmp_path / "two_hop_contact.csv"
    contact_csv.write_text(
        "dataset_id,range_m,node_a,node_b,start_time_ms,end_time_ms,duration_ms,minimum_distance_m\n"
        "vannes,50.0,nodeR,nodeS,1000,2000,1000,10.0\n"
        "vannes,50.0,nodeD,nodeR,3000,4000,1000,10.0\n"
    )

    workload = [
        Packet("pkt_relay", "nodeS", "nodeD", 1000, 1, 500, 10_000)
    ]

    # Direct Delivery: nodeS meets nodeR -> nodeR is NOT destination, so NOT forwarded!
    sim_dd = DTNSimulator(contact_csv, routing_policy="direct_delivery")
    m_dd = sim_dd.run(traffic_workload=[p.copy() for p in workload])
    assert m_dd.total_delivered == 0
    assert m_dd.forwarding_attempts == 0

    # Epidemic: nodeS meets nodeR -> forwards to nodeR; nodeR meets nodeD -> delivers!
    sim_epi = DTNSimulator(contact_csv, routing_policy="epidemic")
    m_epi = sim_epi.run(traffic_workload=[p.copy() for p in workload])
    assert m_epi.total_delivered == 1
    assert m_epi.packet_delivery_ratio == 1.0
    assert m_epi.mean_hops == 2.0


# -----------------------------------------------------------------------------
# 9. Output Summary CSV Schema & Report File Verification
# -----------------------------------------------------------------------------

def test_simulation_summary_csv_and_report_artifacts():
    """
    Validates that data/processed/simulation_summary.csv and
    reports/dtn_simulation_results.md exist, have valid schemas,
    and report consistent numbers.
    """
    summary_csv = PROJECT_ROOT / "data" / "processed" / "simulation_summary.csv"
    report_file = PROJECT_ROOT / "reports" / "dtn_simulation_results.md"

    assert summary_csv.is_file(), f"Missing summary CSV: {summary_csv}"
    assert report_file.is_file(), f"Missing simulation report: {report_file}"

    df = pd.read_csv(summary_csv)
    expected_cols = [
        "dataset_id", "range_m", "routing_policy", "num_nodes", "total_contacts",
        "total_generated", "total_delivered", "pending_in_buffers", "expired_undelivered",
        "total_expired_copies", "buffer_dropped_packets", "packet_delivery_ratio",
        "mean_delay_ms", "median_delay_ms", "min_delay_ms", "max_delay_ms",
        "std_delay_ms", "mean_hops", "forwarding_attempts", "successful_transfers",
        "failed_transfers", "truncated_contact_attempts", "peak_buffer_bytes_network",
        "mean_buffer_utilization"
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing column '{col}' in summary CSV"

    assert len(df) >= 6  # At least 3 ranges x 2 policies
    assert (df["packet_delivery_ratio"] >= 0.0).all()
    assert (df["packet_delivery_ratio"] <= 1.0).all()
    assert (df["total_delivered"] <= df["total_generated"]).all()


def test_packet_remaining_ttl_bounded():
    """
    Validates that Packet.remaining_ttl_ms correctly reports remaining lifetime
    and cleanly clamps to 0 once expired.
    """
    pkt = Packet(
        packet_id="pkt_test_ttl",
        source="nodeA",
        destination="nodeB",
        size_bytes=1000,
        priority=1,
        creation_time_ms=1000,
        ttl_ms=5000,
    )
    assert pkt.expiry_time_ms == 6000
    assert pkt.remaining_ttl_ms(1000) == 5000
    assert pkt.remaining_ttl_ms(3000) == 3000
    assert pkt.remaining_ttl_ms(6000) == 0
    assert pkt.remaining_ttl_ms(8000) == 0
    assert pkt.is_expired(6000) is True
    assert pkt.is_expired(5999) is False


def test_node_buffer_membership_and_snapshot():
    """
    Validates that NodeBuffer supports membership checks via `in` and
    provides an immutable/isolated snapshot list of current packets.
    """
    buf = NodeBuffer(capacity_bytes=5000)
    pkt1 = Packet("pkt_1", "nodeA", "nodeB", 1000, 1, 0, 10000)
    pkt2 = Packet("pkt_2", "nodeA", "nodeC", 2000, 1, 0, 10000)

    assert "pkt_1" not in buf
    buf.add(pkt1)
    buf.add(pkt2)

    assert "pkt_1" in buf
    assert "pkt_2" in buf
    assert "pkt_3" not in buf

    snapshot = buf.packets_list
    assert len(snapshot) == 2
    assert {p.packet_id for p in snapshot} == {"pkt_1", "pkt_2"}

    # Modifying the returned list does not affect the internal buffer
    snapshot.pop()
    assert len(buf) == 2


def test_simulation_metrics_overhead_ratio():
    """
    Validates that SimulationMetrics.overhead_ratio calculates the standard
    DTN overhead ratio (transfers - deliveries) / deliveries cleanly, and
    safely yields 0.0 when deliveries is 0.
    """
    m = SimulationMetrics(
        dataset_id="vannes",
        range_m=50.0,
        routing_policy="epidemic",
        num_nodes=5,
        total_contacts=20,
    )
    # Zero deliveries: overhead ratio should be 0.0 safely
    assert m.overhead_ratio == 0.0
    assert m.to_dict()["overhead_ratio"] == 0.0

    # 10 successful transfers for 2 deliveries: (10 - 2) / 2 = 4.0
    m.total_delivered = 2
    m.successful_transfers = 10
    assert m.overhead_ratio == 4.0
    assert m.to_dict()["overhead_ratio"] == 4.0

    # Direct delivery: 2 successful transfers for 2 deliveries: (2 - 2) / 2 = 0.0
    m.successful_transfers = 2
    assert m.overhead_ratio == 0.0


def test_dtn_node_buffer_status_properties():
    """
    Validates DTNNode buffer convenience properties: buffer_utilization,
    stored_packet_count, and stored_bytes.
    """
    node = DTNNode(node_id="nodeA", buffer_capacity_bytes=1000)
    assert node.buffer_utilization == 0.0
    assert node.stored_packet_count == 0
    assert node.stored_bytes == 0

    pkt = Packet("pkt_1", "nodeA", "nodeB", size_bytes=250, priority=1, creation_time_ms=0, ttl_ms=10000)
    success, reason = node.receive_packet(pkt, current_time_ms=100)
    assert success is True
    assert reason == "BUFFER_STORED"

    assert node.stored_packet_count == 1
    assert node.stored_bytes == 250
    assert node.buffer_utilization == 0.25

