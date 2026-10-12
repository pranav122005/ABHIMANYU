# DTN AI Routing — Finalized Dataset Data Dictionary

**Schema Version**: `1.0.0`  
**Location**: `data/finalized/`

This document defines the schema, data types, physical units, nullability, and semantic definitions for all finalized tables.

---

## 1. Table: `vannes_contacts_{50,100,200}m.csv`
Derived geometric proximity contact intervals between municipal buses.

| Column Name | Data Type | Physical Unit | Nullable | Semantic Description |
| :--- | :--- | :--- | :---: | :--- |
| `dataset_id` | `string` | — | No | Identifier string (`vannes`). |
| `range_m` | `float` | meters | No | Configured geometric communication range horizon (50.0, 100.0, 200.0). |
| `node_a` | `string` | — | No | Canonical first bus identifier (`node_a < node_b`). |
| `node_b` | `string` | — | No | Canonical second bus identifier. |
| `start_time_ms` | `integer` | milliseconds | No | First discrete simulation step where Euclidean distance $d \le R$. |
| `end_time_ms` | `integer` | milliseconds | No | Last consecutive simulation step where Euclidean distance $d \le R$. |
| `duration_ms` | `integer` | milliseconds | No | Contact duration (`end_time_ms - start_time_ms`). |
| `minimum_distance_m` | `float` | meters | No | Minimum 2D Euclidean distance observed during the contact window. |

---

## 2. Table: `packet_outcomes.csv`
Per-packet ground truth records comparing decentralized routing policies with the offline A* temporal oracle.

| Column Name | Data Type | Physical Unit | Nullable | Semantic Description |
| :--- | :--- | :--- | :---: | :--- |
| `packet_id` | `string` | — | No | Unique deterministic bundle identifier (`pkt_XXXX_src_dst`). |
| `range_m` | `float` | meters | No | Evaluated contact-range assumption (50.0, 100.0, 200.0). |
| `policy` | `string` | — | No | Routing policy (`direct_delivery`, `two_hop`, `epidemic`, `temporal_astar`). |
| `source` | `string` | — | No | Bus identifier originating the bundle. |
| `destination` | `string` | — | No | Target bus identifier intended to receive the bundle. |
| `size_bytes` | `integer` | bytes | No | Bundle payload size (default 10,000 bytes). |
| `priority` | `integer` | — | No | User priority level (1=Normal, 2=High, 3=Urgent). |
| `creation_time_ms` | `integer` | milliseconds | No | Simulation clock time when the bundle was injected into source buffer. |
| `ttl_ms` | `integer` | milliseconds | No | Time-to-live threshold (14,400,000 ms = 4 hours). |
| `delivered` | `integer` | binary flag | No | `1` if bundle successfully reached destination; `0` otherwise. |
| `delivery_delay_ms` | `integer` | milliseconds | No | Latency from creation to delivery ($t_{\text{deliv}} - t_{\text{creat}}$); `-1` if undelivered. |
| `hops` | `integer` | count | No | Number of network hops traversed by delivered bundle; `-1` if undelivered. |
| `pending` | `integer` | binary flag | No | `1` if bundle was still held in an active buffer at simulation end; `0` otherwise. |
| `expired` | `integer` | binary flag | No | `1` if bundle reached TTL without being delivered; `0` otherwise. |
| `theoretical_feasible` | `integer` | binary flag | No | `1` if offline time-dependent A* found a valid temporal path within TTL; `0` otherwise. |
| `theoretical_delay_ms` | `integer` | milliseconds | No | Theoretical earliest possible delivery latency under A* oracle; `-1` if unreachable. |
| `theoretical_hops` | `integer` | count | No | Hop count along theoretical earliest arrival path; `-1` if unreachable. |

---

## 3. Table: `simulation_summary.csv`
Macro-level network performance metrics across all 12 benchmark evaluations.

| Column Name | Data Type | Physical Unit | Nullable | Semantic Description |
| :--- | :--- | :--- | :---: | :--- |
| `dataset_id` | `string` | — | No | Dataset name (`vannes`). |
| `range_m` | `float` | meters | No | Contact range (50.0, 100.0, 200.0). |
| `routing_policy` | `string` | — | No | Evaluated policy (`direct_delivery`, `two_hop`, `epidemic`, `temporal_astar`). |
| `num_nodes` | `integer` | count | No | Number of active participating nodes (59 municipal buses). |
| `total_contacts` | `integer` | count | No | Number of available contact windows in input contact graph. |
| `total_generated` | `integer` | count | No | Total bundle workload size ($N_{\text{gen}} = 200$). |
| `total_delivered` | `integer` | count | No | Unique bundles delivered to destination ($D$). |
| `pending_in_buffers` | `integer` | count | No | Bundles pending in transit buffers at simulation termination ($P$). |
| `expired_undelivered` | `integer` | count | No | Bundles expired before reaching destination ($E$). |
| `buffer_dropped_packets`| `integer` | count | No | Transmission attempts rejected due to receiver buffer exhaustion. |
| `packet_delivery_ratio` | `float` | ratio [0, 1] | No | Packet delivery ratio: $\text{PDR} = \frac{D}{N_{\text{gen}}}$. |
| `mean_delay_ms` | `float` | milliseconds | No | Arithmetic mean delivery delay for delivered bundles. |
| `median_delay_ms` | `float` | milliseconds | No | Median delivery delay for delivered bundles. |
| `mean_hops` | `float` | count | No | Average hops traversed by delivered bundles. |
| `forwarding_attempts` | `integer` | count | No | Total transmission attempts across contact links. |
| `successful_transfers` | `integer` | count | No | Completed transmissions received by peer nodes. |
| `theoretical_pdr` | `float` | ratio [0, 1] | Yes | Theoretical maximum PDR from offline A* planner (populated for A*). |
| `theoretical_mean_delay_ms` | `float` | milliseconds | Yes | Theoretical mean delay from offline A* planner (populated for A*). |
| `mean_search_time_ms` | `float` | milliseconds | Yes | Average CPU search time per packet for A* path finding. |
| `mean_nodes_expanded` | `float` | count | Yes | Average search states expanded per packet by A*. |

---

## 4. Table: `temporal_routes.csv`
Offline optimal time-dependent paths computed by the A* benchmark oracle.

| Column Name | Data Type | Physical Unit | Nullable | Semantic Description |
| :--- | :--- | :--- | :---: | :--- |
| `packet_id` | `string` | — | No | Target bundle identifier. |
| `range_m` | `float` | meters | No | Contact range (50.0, 100.0, 200.0). |
| `source` | `string` | — | No | Source bus identifier. |
| `destination` | `string` | — | No | Destination bus identifier. |
| `success` | `boolean` | — | No | `True` if feasible temporal path exists within TTL; `False` otherwise. |
| `creation_time_ms` | `integer` | milliseconds | No | Injection timestamp. |
| `arrival_time_ms` | `integer` | milliseconds | No | Optimal earliest arrival timestamp at destination (`-1` if unreachable). |
| `delay_ms` | `integer` | milliseconds | No | Optimal latency ($t_{\text{arr}} - t_{\text{creat}}$); `-1` if unreachable. |
| `hop_count` | `integer` | count | No | Number of temporal hops along the optimal path. |
| `path` | `string` | — | No | Ordered sequence of nodes (e.g. `nodeA -> nodeB -> nodeC`). |
| `nodes_expanded` | `integer` | count | No | Number of priority-queue state expansions. |
| `search_time_ms` | `float` | milliseconds | No | CPU wall-clock execution time for the A* search. |
| `failure_reason` | `string` | — | Yes | Reason for path planning failure (e.g. unreachable, TTL expired). |
