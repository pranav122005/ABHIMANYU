# DTN AI Routing — Vannes Contact-Graph Generation Report

## Executive Summary
This report documents the extraction of proximity-derived node-contact events from the Vannes municipal bus mobility trace (`vbn_0.dgs`) for communication range thresholds of 50 m, 100 m, and 200 m.

> [!IMPORTANT]
> **Proximity vs. Radio Transmission**: These contact intervals represent spatial proximity within configured Euclidean geometric thresholds. They **do not assume or simulate radio propagation, channel contention, wireless fading, or packet-delivery outcomes**.

---

## 1. Trace Overview & Ingestion Metrics

| Metric | Observed Value | Documented Specification | Alignment |
| :--- | :--- | :--- | :--- |
| **Format** | `DGS004` | GraphStream DGS004 | Verified |
| **Total File Lines** | `1,964,512` | ~1.96M lines | Verified |
| **Simulation Timesteps** | `51,080` | ~51,080 steps | Verified |
| **Scenario Duration** | `51,240,000 ms` (~14h 14m) | 51,240,000 ms (05:25 to 19:39) | Exact Match |
| **Reference Time** | `19500000` ms (05:25 AM) | `ref_time=19500000` | Exact Match |
| **Coordinate System** | Cartesian meters relative to area reference | Cartesian relative to GPS ref point | Exact Match |
| **Discovered Buses** | `60` nodes | 60 total buses | Exact Match |
| **Max Simultaneous Active** | `56` nodes | 56 max active simultaneously | Exact Match |
| **Nodes Missing Positions** | `1` (`line01-09`) | Handled safely without interpolation | Verified |

---

## 2. Contact Graph Summary Across Configurable Ranges

| Range Threshold | Total Contacts | Unique Node Pairs | Mean Duration | Median Duration | Max Duration | Min Dist (Avg) | Instantaneous Contacts (0s) | Output CSV |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **50 m** | 7,275 | 1288 | 68.94 s (68936 ms) | 20.0 s | 17667.0 s | 10.59 m | 56 (0.8%) | `vannes_contacts_50m.csv` |
| **100 m** | 8,036 | 1347 | 82.20 s (82203 ms) | 37.0 s | 17677.0 s | 19.00 m | 25 (0.3%) | `vannes_contacts_100m.csv` |
| **200 m** | 8,892 | 1395 | 105.89 s (105889 ms) | 68.0 s | 17696.0 s | 35.93 m | 77 (0.9%) | `vannes_contacts_200m.csv` |

---

## 3. Duration & Proximity Distribution Metrics

| Metric | 50 m Range | 100 m Range | 200 m Range |
| :--- | :---: | :---: | :---: |
| **Minimum Duration** | 0 ms | 0 ms | 0 ms |
| **25th Percentile Duration** | 6000.0 ms | 13000.0 ms | 28000.0 ms |
| **Median (50th %) Duration** | 20000.0 ms | 37000.0 ms | 68000.0 ms |
| **75th Percentile Duration** | 111000.0 ms | 123000.0 ms | 146000.0 ms |
| **Mean Duration** | 68936.2 ms | 82202.8 ms | 105889.1 ms |
| **Std Dev Duration** | 323508.5 ms | 367552.5 ms | 355030.3 ms |
| **Maximum Duration** | 17,667,000 ms | 17,677,000 ms | 17,696,000 ms |
| **Minimum Distance Observed** | 0.00 m | 0.00 m | 0.00 m |

---

## 4. Methodology, Algorithms & Exact Definitions

### 4.1 Incremental DGS Streaming Parser
- **Memory Efficiency**: The parser streams DGS lines sequentially without loading the 64.8 MB file into memory.
- **Event Lifecycle**: Handles `an` (node creation), `cn` (coordinate updates), and `dn` (node removal).
- **Coordinate Tracking**: Retains latest Cartesian coordinates $(x, y)$ in meters. Inactive nodes and unpositioned nodes are tracked separately.
- **Safeguards**: Node `line01-09` is created without coordinates (`an line01-09`) and deleted (`dn line01-09`) without updates. It is explicitly identified and safely bypassed from distance calculations without throwing errors or interpolating artificial positions.

### 4.2 Proximity & Contact Intervals
- **Distance Calculation**: $d(u, v) = \sqrt{(x_u - x_v)^2 + (y_u - y_v)^2}$ in meters.
- **Contact Condition**: $d(u, v) \le R$, where $R \in \{50, 100, 200\}$ meters.
- **Undirected Contacts**: Canonical ordering `node_a < node_b` guarantees that edge $(u, v)$ is identical to $(v, u)$, avoiding double-counting.
- **Contact Interval Boundary Semantics**:
  - `start_time_ms`: The first discrete simulation step $t_1$ at which $d(u, v) \le R$.
  - `end_time_ms`: The final consecutive simulation step $t_k$ at which $d(u, v) \le R$.
  - `duration_ms`: Defined as `end_time_ms - start_time_ms`. For instantaneous encounters observed at a single discrete step ($k=1$), `start == end` and `duration == 0 ms`.
  - `minimum_distance_m`: $\min_{t \in [t_1, t_k]} d_t(u, v)$.
- **Interruption & Observation Gap Handling**: If consecutive timesteps exhibit a temporal gap exceeding `max_gap_ms` (default 5,000 ms), or if either node is removed (`dn`), the active contact is closed immediately at the last observed step rather than artificially bridging across unobserved periods.
- **Spatial Acceleration**: 2D grid hashing partitions the $18\times 12$ km bounding area into square cells of dimension $\max(R) = 200$ m, reducing pairwise checks to $O(N)$ expected time per step.

---

## 5. Parser Diagnostics, Warnings & Trace Anomalies

- **Malformed Records**: `0` malformed records encountered.
- **Parser Warnings**: `0` warnings logged.
- **Identified Temporal Gaps in Trace**:
  - From `96,000 ms` to `140,000 ms` (duration `44,000 ms` = 44.0 s)
  - From `140,000 ms` to `177,000 ms` (duration `37,000 ms` = 37.0 s)
  - From `320,000 ms` to `322,000 ms` (duration `2,000 ms` = 2.0 s)
  - From `51,137,000 ms` to `51,139,000 ms` (duration `2,000 ms` = 2.0 s)
  - From `51,159,000 ms` to `51,240,000 ms` (duration `81,000 ms` = 81.0 s)

- **Missing Position Observations**:
  - Bus `line01-09`: Active between `36,420,000 ms` and `46,080,000 ms` (9,660 seconds) without any spatial coordinate attributes.
  - Safely omitted from contact evaluations without synthetic data hallucination.

---

## 6. Assumptions and Limitations

1. **Proximity-Derived Contact vs. Actual Radio Channel**: Contacts indicate geometric distance $\le R$. Real vehicular radio propagation is subject to urban building occlusion, multipath fading, antenna orientation, and Doppler shift.
2. **No Transmission Success Guarantee**: DTN routing algorithms must not treat contact intervals as guaranteed packet delivery windows. Bandwidth, contention, and queue buffer constraints must be evaluated in routing simulation.
3. **No Velocity Interpolation**: When buses remain stationary or between temporal gaps, coordinates are not interpolated with synthetic curves.
4. **Synthetic Realistic Nature**: Bus routes and schedules originate from OpenStreetMap and Kicéo 2017 timetables generated via the LEPTON platform, reflecting municipal transit behavior with moderate churn.
