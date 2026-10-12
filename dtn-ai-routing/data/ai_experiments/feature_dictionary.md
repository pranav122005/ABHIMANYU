# DTN AI Routing — Stage 5 Decision Feature Dictionary (Causal Audit)

**Target Device**: ESP8266 NodeMCU (Tensilica Xtensa L106 @ 80MHz)  
**Scope**: Strictly Local, Contemporaneous Encounter Features (Decentralized Inference)

| Feature Name | Data Type | Physical Unit | Source & Availability | Category | Semantics & Causal Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `peer_is_destination` | `uint8_t` | binary (0/1) | Peer discovery beacon | Observed | `1` if peer matches packet destination. Essential for immediate direct delivery. |
| `packet_size_bytes` | `uint32_t` | bytes | Stored packet header | Observed | Packet payload length (default 10,000 bytes). Determines required transmission time. |
| `packet_priority` | `uint8_t` | level (1-3) | Stored packet header | Observed | User priority class (1=Normal, 2=High, 3=Urgent). |
| `remaining_ttl_ratio` | `float` | ratio [0, 1] | Local RTC & packet header | Derived | $(t_{\text{expiry}} - t_{\text{curr}}) / \text{TTL}$. Distinguishes fresh vs expiring packets. |
| `packet_hops` | `uint16_t` | hop count | Stored packet header | Observed | Number of relay transfers traversed so far. Prunes excessive relay loops. |
| `transfer_duration_ms`| `uint32_t` | milliseconds | Local transfer model | Derived | $\text{overhead} + \lceil S \cdot 1000 / \text{rate} \rceil$. Expected transfer time at radio rate. |
| `contact_elapsed_ms` | `uint32_t` | milliseconds | Local contact clock | Observed | Time elapsed since peer was first detected ($t_{\text{curr}} - t_{\text{start}}$). Strictly causal. |
| `estimated_remaining_contact_ms`| `uint32_t` | milliseconds | Local encounter history | Derived | History-based estimate: $\max(0, \bar{T}_{\text{hist}} - \Delta t_{\text{elapsed}})$. Does NOT use future contact end. |
| `estimated_transfer_fits`| `uint8_t` | binary (0/1) | Local comparator | Derived | `1` if $\text{transfer\_duration} \le \text{estimated\_remaining}$; `0` otherwise. Strictly causal. |
| `local_buffer_utilization`| `float` | ratio [0, 1] | Local buffer manager | Observed | Current queue byte occupancy / total capacity (2 MB). |
| `peer_encounter_frequency`| `uint16_t` | count | Local rolling neighbor log | Observed | Number of past completed encounters with this peer node. |

> [!IMPORTANT]
> **Strict Feature Causality Safeguards**:
> None of the features use future contact end times, future contact schedules, offline A* routes, or central telemetry. All features are strictly contemporaneous or derived from local past completed encounter history.
