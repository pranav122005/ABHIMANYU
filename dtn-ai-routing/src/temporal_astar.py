#!/usr/bin/env python3
"""
DTN AI Routing - Stage 4: Time-Dependent A* Benchmark

Module: src/temporal_astar.py
Description:
  Implements an offline time-dependent A* (and Dijkstra-equivalent) path planning
  benchmark for Delay-Tolerant Networks over Contact Graphs / Time-Varying Graphs (TVG).

Decentralization Boundary & Scientific Labeling:
  IMPORTANT: This is an OFFLINE TEMPORAL ROUTING BENCHMARK / ORACLE.
  It computes the theoretical lower bound on packet delivery delay using complete
  global knowledge of future contact schedules. It is NOT a decentralized routing
  algorithm suitable for direct ad-hoc deployment on embedded vehicular nodes.
  
  To build a genuinely decentralized A*-inspired algorithm in future work, nodes would
  require either distributed link-state summary announcements, encounter-probability
  exchange (e.g. PRoPHET), or geographic mobility trajectory beacons.

Algorithm Details:
  - Optimizes: Earliest Arrival Time at destination (or minimum latency).
  - Graph model: Contacts are time intervals [start_time_ms, end_time_ms].
  - Waiting: Nodes can buffer/wait at an intermediate node until a future contact starts.
  - Transfer constraints: A transfer succeeds only if transmission duration
    (transfer_overhead_ms + ceil(size_bytes * 1000 / rate_bps)) completes before contact_end_ms
    and within packet TTL / expiry.
  - Heuristic: Admissible zero heuristic h(u) = 0 (reducing to exact time-dependent label-setting
    Dijkstra, guaranteed optimal without overestimating remaining cost), with optional
    spatial distance / transfer time lower bounds.
"""

from __future__ import annotations

import collections
import dataclasses
import heapq
import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import pandas as pd


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 1. Data Models
# -----------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class TemporalHop:
    """Represents an individual hop in a time-dependent route."""
    from_node: str
    to_node: str
    contact_start_ms: int
    contact_end_ms: int
    tx_start_ms: int
    tx_end_ms: int
    wait_duration_ms: int
    transfer_duration_ms: int

    def to_dict(self) -> Dict[str, Union[str, int]]:
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "contact_start_ms": self.contact_start_ms,
            "contact_end_ms": self.contact_end_ms,
            "tx_start_ms": self.tx_start_ms,
            "tx_end_ms": self.tx_end_ms,
            "wait_duration_ms": self.wait_duration_ms,
            "transfer_duration_ms": self.transfer_duration_ms,
        }


@dataclasses.dataclass
class TemporalRoute:
    """Represents a planned time-dependent route from source to destination."""
    packet_id: str
    source: str
    destination: str
    success: bool
    creation_time_ms: int
    arrival_time_ms: int
    delay_ms: int
    path_nodes: List[str] = dataclasses.field(default_factory=list)
    hops: List[TemporalHop] = dataclasses.field(default_factory=list)
    nodes_expanded: int = 0
    search_time_ms: float = 0.0
    failure_reason: Optional[str] = None

    @property
    def hop_count(self) -> int:
        return len(self.hops)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "source": self.source,
            "destination": self.destination,
            "success": self.success,
            "creation_time_ms": self.creation_time_ms,
            "arrival_time_ms": self.arrival_time_ms,
            "delay_ms": self.delay_ms,
            "hop_count": self.hop_count,
            "path": " -> ".join(self.path_nodes) if self.path_nodes else "None",
            "nodes_expanded": self.nodes_expanded,
            "search_time_ms": round(self.search_time_ms, 3),
            "failure_reason": self.failure_reason or "",
        }


# -----------------------------------------------------------------------------
# 2. Time-Dependent Contact Graph Representation
# -----------------------------------------------------------------------------

class TemporalContactSchedule:
    """
    Indexed time-dependent contact schedule.
    Provides chronologically ordered contact lookups per node.
    """

    def __init__(self):
        # node -> list of (peer_node, start_time_ms, end_time_ms)
        self.adjacency: Dict[str, List[Tuple[str, int, int]]] = collections.defaultdict(list)
        self.all_nodes: Set[str] = set()
        self.total_contacts: int = 0

    @classmethod
    def from_csv(cls, csv_path: Union[str, Path]) -> TemporalContactSchedule:
        """Loads and indexes contacts from a Vannes contact CSV."""
        schedule = cls()
        path = Path(csv_path)
        if not path.is_file():
            raise FileNotFoundError(f"Contact CSV not found: {path}")

        try:
            df = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return schedule

        required = ["node_a", "node_b", "start_time_ms", "end_time_ms"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column '{col}' in contact CSV: {path}")

        for _, row in df.iterrows():
            u = str(row["node_a"])
            v = str(row["node_b"])
            s = int(row["start_time_ms"])
            e = int(row["end_time_ms"])
            schedule.adjacency[u].append((v, s, e))
            schedule.adjacency[v].append((u, s, e))
            schedule.all_nodes.add(u)
            schedule.all_nodes.add(v)
            schedule.total_contacts += 1

        # Sort contacts per node chronologically by start_time_ms
        for node in schedule.adjacency:
            schedule.adjacency[node].sort(key=lambda c: (c[1], c[2]))

        return schedule

    @classmethod
    def from_tuples(
        cls, contacts: Sequence[Tuple[str, str, int, int]]
    ) -> TemporalContactSchedule:
        """Constructs schedule directly from (node_a, node_b, start_ms, end_ms) tuples."""
        schedule = cls()
        for u, v, s, e in contacts:
            schedule.adjacency[u].append((v, s, e))
            schedule.adjacency[v].append((u, s, e))
            schedule.all_nodes.add(u)
            schedule.all_nodes.add(v)
            schedule.total_contacts += 1

        for node in schedule.adjacency:
            schedule.adjacency[node].sort(key=lambda c: (c[1], c[2]))
        return schedule


# -----------------------------------------------------------------------------
# 3. Time-Dependent A* Search Engine
# -----------------------------------------------------------------------------

class TimeDependentAStar:
    """
    Offline Time-Dependent A* Benchmark for DTN Contact Graphs.
    
    WARNING / DECENTRALIZATION BOUNDARY:
      This is an OFFLINE TEMPORAL ROUTING BENCHMARK / ORACLE.
      It computes optimal earliest-arrival paths using complete offline knowledge
      of future contact schedules. It is an evaluation benchmark, NOT a decentralized
      ad-hoc routing protocol suitable for embedded deployment.
    
    Computes earliest arrival time paths taking into account:
      - Departure availability at source
      - Waiting time at intermediate carrier nodes
      - Contact duration constraints vs required packet transfer time
      - Packet TTL / expiry deadline
    
    Heuristic:
      Default is h(u) = 0 (zero heuristic).
      Because contact graphs are time-dependent and discrete, h(u)=0 guarantees
      admissibility and consistency, reducing to an exact label-setting Dijkstra search.
    """

    is_offline_oracle: bool = True  # Explicit scientific labeling flag

    def __init__(
        self,
        contact_schedule: TemporalContactSchedule,
        heuristic: str = "zero",
    ):
        """
        Args:
            contact_schedule: Indexed temporal contact schedule.
            heuristic: Heuristic mode ('zero' for Dijkstra-equivalent admissible search).
        """
        self.schedule = contact_schedule
        self.heuristic_mode = heuristic.lower()
        if self.heuristic_mode not in ("zero", "transfer_bound"):
            raise ValueError(f"Unsupported heuristic '{heuristic}'. Supported: 'zero', 'transfer_bound'")

    def calculate_transfer_time_ms(
        self,
        size_bytes: int,
        transfer_rate_bytes_sec: float,
        transfer_overhead_ms: int,
    ) -> int:
        """Calculates transmission duration in ms."""
        raw_xfer_ms = (size_bytes * 1000.0) / max(1.0, transfer_rate_bytes_sec)
        return transfer_overhead_ms + math.ceil(raw_xfer_ms)

    def heuristic(self, current_node: str, destination: str, min_transfer_ms: int) -> int:
        """Admissible lower bound on remaining duration to destination."""
        if current_node == destination:
            return 0
        if self.heuristic_mode == "transfer_bound":
            # At least one transfer duration is required if not at destination
            return min_transfer_ms
        # Default: guaranteed admissible zero heuristic
        return 0

    def find_earliest_arrival_path(
        self,
        source: str,
        destination: str,
        creation_time_ms: int,
        ttl_ms: int,
        packet_size_bytes: int = 10_000,
        transfer_rate_bytes_sec: float = 250_000.0,
        transfer_overhead_ms: int = 50,
        packet_id: str = "benchmark_pkt",
    ) -> TemporalRoute:
        """
        Plans the earliest arrival time-dependent path from source to destination.

        Returns:
            TemporalRoute instance with optimal hops, delay, and computational cost.
        """
        start_search_time = time.perf_counter()

        # Input validation
        if source not in self.schedule.all_nodes and source != destination:
            return TemporalRoute(
                packet_id=packet_id,
                source=source,
                destination=destination,
                success=False,
                creation_time_ms=creation_time_ms,
                arrival_time_ms=-1,
                delay_ms=-1,
                failure_reason=f"Source '{source}' not in contact schedule",
            )

        if destination not in self.schedule.all_nodes and source != destination:
            return TemporalRoute(
                packet_id=packet_id,
                source=source,
                destination=destination,
                success=False,
                creation_time_ms=creation_time_ms,
                arrival_time_ms=-1,
                delay_ms=-1,
                failure_reason=f"Destination '{destination}' not in contact schedule",
            )

        # Trivial path: source is destination
        if source == destination:
            return TemporalRoute(
                packet_id=packet_id,
                source=source,
                destination=destination,
                success=True,
                creation_time_ms=creation_time_ms,
                arrival_time_ms=creation_time_ms,
                delay_ms=0,
                path_nodes=[source],
                hops=[],
                nodes_expanded=0,
                search_time_ms=(time.perf_counter() - start_search_time) * 1000.0,
            )

        expiry_time_ms = creation_time_ms + ttl_ms
        xfer_duration_ms = self.calculate_transfer_time_ms(
            size_bytes=packet_size_bytes,
            transfer_rate_bytes_sec=transfer_rate_bytes_sec,
            transfer_overhead_ms=transfer_overhead_ms,
        )

        # Priority Queue: (f_score, arrival_time_ms, current_node, path_nodes, list_of_hops)
        # Ties broken by arrival_time_ms, then hop count
        min_xfer = xfer_duration_ms
        h0 = self.heuristic(source, destination, min_xfer)
        pq: List[Tuple[int, int, str, List[str], List[TemporalHop]]] = [
            (creation_time_ms + h0, creation_time_ms, source, [source], [])
        ]

        # best_arrival[node] = earliest known arrival time at node
        best_arrival: Dict[str, int] = {source: creation_time_ms}
        nodes_expanded = 0

        while pq:
            f_score, curr_arrival_ms, u, path_nodes, hops = heapq.heappop(pq)
            nodes_expanded += 1

            # Prune if we have already found a strictly earlier arrival at u
            if curr_arrival_ms > best_arrival.get(u, float("inf")):
                continue

            # Goal check
            if u == destination:
                elapsed_ms = (time.perf_counter() - start_search_time) * 1000.0
                delay_ms = curr_arrival_ms - creation_time_ms
                return TemporalRoute(
                    packet_id=packet_id,
                    source=source,
                    destination=destination,
                    success=True,
                    creation_time_ms=creation_time_ms,
                    arrival_time_ms=curr_arrival_ms,
                    delay_ms=delay_ms,
                    path_nodes=path_nodes,
                    hops=hops,
                    nodes_expanded=nodes_expanded,
                    search_time_ms=elapsed_ms,
                )

            # Explore outgoing contacts from u
            for v, contact_start, contact_end in self.schedule.adjacency.get(u, []):
                # Contact already ended before packet arrived at u
                if contact_end < curr_arrival_ms:
                    continue

                # Transmission can start at max(arrival_at_u, contact_start)
                # (Models waiting at node u until contact opens)
                tx_start = max(curr_arrival_ms, contact_start)
                tx_end = tx_start + xfer_duration_ms

                # Check 1: Does transfer finish before contact window ends?
                if tx_end > contact_end:
                    continue

                # Check 2: Does transfer complete before packet TTL expires?
                if tx_end > expiry_time_ms:
                    continue

                # Check 3: Is this an improvement over the earliest known arrival at v?
                if tx_end < best_arrival.get(v, float("inf")):
                    best_arrival[v] = tx_end
                    h_val = self.heuristic(v, destination, min_xfer)
                    hop = TemporalHop(
                        from_node=u,
                        to_node=v,
                        contact_start_ms=contact_start,
                        contact_end_ms=contact_end,
                        tx_start_ms=tx_start,
                        tx_end_ms=tx_end,
                        wait_duration_ms=tx_start - curr_arrival_ms,
                        transfer_duration_ms=xfer_duration_ms,
                    )
                    heapq.heappush(
                        pq,
                        (
                            tx_end + h_val,
                            tx_end,
                            v,
                            path_nodes + [v],
                            hops + [hop],
                        ),
                    )

        elapsed_ms = (time.perf_counter() - start_search_time) * 1000.0
        return TemporalRoute(
            packet_id=packet_id,
            source=source,
            destination=destination,
            success=False,
            creation_time_ms=creation_time_ms,
            arrival_time_ms=-1,
            delay_ms=-1,
            nodes_expanded=nodes_expanded,
            search_time_ms=elapsed_ms,
            failure_reason="No feasible temporal path found within TTL",
        )


# -----------------------------------------------------------------------------
# 4. Batch Benchmark Evaluator
# -----------------------------------------------------------------------------

def evaluate_temporal_astar_benchmark(
    contact_csv_path: Union[str, Path],
    workload: Sequence[Any],  # Sequence of Packet objects
    transfer_rate_bytes_sec: float = 250_000.0,
    transfer_overhead_ms: int = 50,
    heuristic: str = "zero",
) -> Tuple[List[TemporalRoute], Dict[str, Any]]:
    """
    Evaluates the offline Time-Dependent A* benchmark over a packet workload.

    Returns:
        (routes_list, summary_metrics_dict)
    """
    schedule = TemporalContactSchedule.from_csv(contact_csv_path)
    planner = TimeDependentAStar(schedule, heuristic=heuristic)

    routes: List[TemporalRoute] = []
    delays: List[int] = []
    hop_counts: List[int] = []
    search_times: List[float] = []
    nodes_exp: List[int] = []

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
        routes.append(route)
        search_times.append(route.search_time_ms)
        nodes_exp.append(route.nodes_expanded)

        if route.success:
            delays.append(route.delay_ms)
            hop_counts.append(route.hop_count)

    n_total = len(workload)
    n_delivered = len(delays)
    pdr = (n_delivered / n_total) if n_total > 0 else 0.0

    summary = {
        "total_packets": n_total,
        "delivered_packets": n_delivered,
        "theoretical_pdr": round(pdr, 4),
        "mean_delay_ms": round(sum(delays) / n_delivered, 1) if n_delivered > 0 else 0.0,
        "median_delay_ms": round(float(pd.Series(delays).median()), 1) if n_delivered > 0 else 0.0,
        "min_delay_ms": min(delays) if n_delivered > 0 else 0,
        "max_delay_ms": max(delays) if n_delivered > 0 else 0,
        "mean_hops": round(sum(hop_counts) / n_delivered, 2) if n_delivered > 0 else 0.0,
        "mean_nodes_expanded": round(sum(nodes_exp) / n_total, 1) if n_total > 0 else 0.0,
        "mean_search_time_ms": round(sum(search_times) / n_total, 3) if n_total > 0 else 0.0,
    }

    return routes, summary
