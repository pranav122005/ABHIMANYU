"""
Test suite for Stage 4: Time-Dependent A* Benchmark.

Validates:
- A* finding an available time-dependent route across multi-hop contacts.
- Waiting for future contacts (carrier store-and-carry).
- Choosing lower-cost / earlier arrival route over later routes.
- Rejecting contacts too short to complete packet transmission.
- Handling expired packets and unreachable destinations gracefully.
- Deterministic search behavior under fixed configuration.
- Correct labeling and documentation of the offline benchmark oracle.
"""

import sys
from pathlib import Path
import pytest

# Ensure src directory is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dtn_simulator import TemporalAStarRouter
from temporal_astar import (
    TemporalContactSchedule,
    TemporalHop,
    TemporalRoute,
    TimeDependentAStar,
)


# -----------------------------------------------------------------------------
# 1. Available Temporal Route Finding
# -----------------------------------------------------------------------------

def test_astar_finds_available_temporal_route():
    """
    Verifies that Time-Dependent A* discovers the multi-hop path:
      S -> R1 -> R2 -> D
    with scheduled contacts.
    """
    contacts = [
        ("nodeS", "nodeR1", 1000, 2000),
        ("nodeR1", "nodeR2", 3000, 4000),
        ("nodeR2", "nodeD", 5000, 6000),
    ]
    schedule = TemporalContactSchedule.from_tuples(contacts)
    planner = TimeDependentAStar(schedule, heuristic="zero")

    # Packet created at 500 ms with 10s TTL, 10 KB size at 250 KB/s (90 ms xfer)
    route = planner.find_earliest_arrival_path(
        source="nodeS",
        destination="nodeD",
        creation_time_ms=500,
        ttl_ms=10_000,
        packet_size_bytes=10_000,
        transfer_rate_bytes_sec=250_000.0,
        transfer_overhead_ms=50,
    )

    assert route.success is True
    assert route.path_nodes == ["nodeS", "nodeR1", "nodeR2", "nodeD"]
    assert route.hop_count == 3
    assert route.creation_time_ms == 500
    assert route.arrival_time_ms == 5000 + 90  # Arrives at nodeD at 5090 ms
    assert route.delay_ms == 5090 - 500


# -----------------------------------------------------------------------------
# 2. Waiting for Future Contact
# -----------------------------------------------------------------------------

def test_astar_waiting_for_future_contact():
    """
    Verifies that when a packet arrives at an intermediate node before the
    next outgoing contact starts, the search explicitly accounts for carrier wait duration.
    """
    contacts = [
        ("nodeA", "nodeB", 1000, 2000),   # S -> B transfers at 1000..1090
        ("nodeB", "nodeC", 10000, 12000), # B waits until 10000 before transferring to C
    ]
    schedule = TemporalContactSchedule.from_tuples(contacts)
    planner = TimeDependentAStar(schedule)

    route = planner.find_earliest_arrival_path(
        source="nodeA",
        destination="nodeC",
        creation_time_ms=500,
        ttl_ms=20_000,
        packet_size_bytes=10_000,
        transfer_rate_bytes_sec=250_000.0,
        transfer_overhead_ms=50,
    )

    assert route.success is True
    assert len(route.hops) == 2

    hop1 = route.hops[0]
    assert hop1.from_node == "nodeA"
    assert hop1.to_node == "nodeB"
    assert hop1.tx_start_ms == 1000
    assert hop1.tx_end_ms == 1090
    assert hop1.wait_duration_ms == 500  # Waited 500..1000 at nodeA

    hop2 = route.hops[1]
    assert hop2.from_node == "nodeB"
    assert hop2.to_node == "nodeC"
    assert hop2.tx_start_ms == 10000
    assert hop2.tx_end_ms == 10090
    assert hop2.wait_duration_ms == 10000 - 1090  # Waited 8910 ms at nodeB!


# -----------------------------------------------------------------------------
# 3. Choosing Lower-Cost / Earlier Arrival Route
# -----------------------------------------------------------------------------

def test_astar_choosing_earlier_arrival_route():
    """
    Tests that A* chooses the route that arrives earliest, even if an
    alternative route departs earlier.
    
    Path 1 (Early departure, late arrival):
      S -> A at [1000, 2000], A -> D at [15000, 16000] -> Arrival: 15090 ms
    Path 2 (Later departure, early arrival):
      S -> B at [3000, 4000], B -> D at [5000, 6000]   -> Arrival: 5090 ms
    """
    contacts = [
        ("nodeS", "nodeA", 1000, 2000),
        ("nodeA", "nodeD", 15000, 16000),
        ("nodeS", "nodeB", 3000, 4000),
        ("nodeB", "nodeD", 5000, 6000),
    ]
    schedule = TemporalContactSchedule.from_tuples(contacts)
    planner = TimeDependentAStar(schedule)

    route = planner.find_earliest_arrival_path(
        source="nodeS",
        destination="nodeD",
        creation_time_ms=0,
        ttl_ms=30_000,
        packet_size_bytes=10_000,
        transfer_rate_bytes_sec=250_000.0,
        transfer_overhead_ms=50,
    )

    assert route.success is True
    # Must choose Path 2 through nodeB!
    assert route.path_nodes == ["nodeS", "nodeB", "nodeD"]
    assert route.arrival_time_ms == 5090


# -----------------------------------------------------------------------------
# 4. Rejecting Contacts Too Short for Transfer
# -----------------------------------------------------------------------------

def test_astar_rejecting_contacts_too_short():
    """
    Tests that contacts whose duration is shorter than required transfer time
    are strictly rejected.
    """
    # Required transfer time = 50 + 40 = 90 ms
    # Contact 1: duration 50 ms (1000 to 1050) -> Too short!
    # Contact 2: duration 200 ms (5000 to 5200) -> Fits!
    contacts = [
        ("nodeA", "nodeB", 1000, 1050),
        ("nodeA", "nodeB", 5000, 5200),
    ]
    schedule = TemporalContactSchedule.from_tuples(contacts)
    planner = TimeDependentAStar(schedule)

    route = planner.find_earliest_arrival_path(
        source="nodeA",
        destination="nodeB",
        creation_time_ms=0,
        ttl_ms=10_000,
        packet_size_bytes=10_000,
        transfer_rate_bytes_sec=250_000.0,
        transfer_overhead_ms=50,
    )

    assert route.success is True
    # Must bypass contact 1 and use contact 2 at 5000 ms
    assert route.hops[0].contact_start_ms == 5000


# -----------------------------------------------------------------------------
# 5. Handling Expired Packets and Unreachable Destinations
# -----------------------------------------------------------------------------

def test_astar_handling_expired_packets_and_unreachable():
    """
    Tests graceful handling of expired TTL and unreachable topologies.
    """
    contacts = [
        ("nodeA", "nodeB", 10000, 11000),  # Contact at 10000 ms
    ]
    schedule = TemporalContactSchedule.from_tuples(contacts)
    planner = TimeDependentAStar(schedule)

    # 1. Packet expires before contact opens (creation 0, TTL 5000 ms -> expires at 5000)
    route_exp = planner.find_earliest_arrival_path(
        source="nodeA",
        destination="nodeB",
        creation_time_ms=0,
        ttl_ms=5000,
    )
    assert route_exp.success is False
    assert route_exp.arrival_time_ms == -1
    assert "TTL" in (route_exp.failure_reason or "")

    # 2. Completely disconnected destination
    route_unreach = planner.find_earliest_arrival_path(
        source="nodeA",
        destination="nodeZ_isolated",
        creation_time_ms=0,
        ttl_ms=20_000,
    )
    assert route_unreach.success is False
    assert route_unreach.arrival_time_ms == -1

    # 3. Source equals destination (trivial path)
    route_same = planner.find_earliest_arrival_path(
        source="nodeA",
        destination="nodeA",
        creation_time_ms=1234,
        ttl_ms=5000,
    )
    assert route_same.success is True
    assert route_same.delay_ms == 0
    assert route_same.path_nodes == ["nodeA"]


# -----------------------------------------------------------------------------
# 6. Deterministic Behavior With Fixed Configuration
# -----------------------------------------------------------------------------

def test_astar_deterministic_behavior():
    """Confirms multiple runs produce byte-for-byte identical temporal paths."""
    contacts = [
        ("nodeA", "nodeB", 1000, 2000),
        ("nodeB", "nodeC", 3000, 4000),
        ("nodeA", "nodeC", 5000, 6000),
    ]
    schedule = TemporalContactSchedule.from_tuples(contacts)
    planner = TimeDependentAStar(schedule)

    r1 = planner.find_earliest_arrival_path("nodeA", "nodeC", 0, 10_000)
    r2 = planner.find_earliest_arrival_path("nodeA", "nodeC", 0, 10_000)

    assert r1.success == r2.success
    assert r1.arrival_time_ms == r2.arrival_time_ms
    assert r1.delay_ms == r2.delay_ms
    assert r1.path_nodes == r2.path_nodes
    assert r1.nodes_expanded == r2.nodes_expanded


# -----------------------------------------------------------------------------
# 7. Correct Labeling of Offline Benchmark
# -----------------------------------------------------------------------------

def test_offline_benchmark_scientific_labeling():
    """
    Verifies that the offline temporal benchmark is explicitly labeled
    as an oracle, distinguishing it from decentralized ad-hoc policies.
    """
    assert TimeDependentAStar.is_offline_oracle is True
    assert TemporalAStarRouter.is_offline_oracle is True

    # Confirm docstrings clearly document the decentralization boundary
    assert "OFFLINE TEMPORAL ROUTING BENCHMARK" in TimeDependentAStar.__doc__
    assert "OFFLINE TEMPORAL ROUTING BENCHMARK" in TemporalAStarRouter.__doc__

