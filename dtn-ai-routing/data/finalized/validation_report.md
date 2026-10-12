# DTN AI Routing — Finalized Dataset Validation & Integrity Report

**Validation Date**: `2026-10-11T17:36:05.157880+00:00`  
**Dataset Directory**: `data/finalized/`  
**Schema Version**: `1.0.0`

---

## 1. File Inventory and Cryptographic Checksums

| File Name | SHA-256 Checksum | File Size (Bytes) | Row Count | Integrity Status |
| :--- | :--- | :---: | :---: | :---: |
| `packet_outcomes.csv` | `ca4b2b4011b89c8f...bc265ce5` | 287,794 | 2,400 | Verified Passed |
| `simulation_summary.csv` | `86bdc10c1a8b8f1f...df6f38c2` | 2,222 | 12 | Verified Passed |
| `temporal_routes.csv` | `45ca61963a5fb0e3...06905de3` | 92,325 | 600 | Verified Passed |
| `vannes_contacts_100m.csv` | `15881aa801c3ab21...9c1a16d3` | 517,414 | 8,036 | Verified Passed |
| `vannes_contacts_200m.csv` | `81614ce6eb55a988...e382a755` | 575,900 | 8,892 | Verified Passed |
| `vannes_contacts_50m.csv` | `c4c69cfbb4d04588...38358da4` | 458,727 | 7,275 | Verified Passed |

---

## 2. Mathematical Invariant Verification

| Invariant Verification Check | Expected Condition | Observed Result | Status |
| :--- | :--- | :---: | :---: |
| **Delivery Ratio Bounds** | $0.0 \le \text{PDR} \le 1.0$ for all runs | Min: 0.4450, Max: 0.8900 | **PASSED** |
| **Delivery Ceiling Consistency** | $\text{Delivered} \le \text{Generated}$ ($D \le 200$) | Max delivered: 178 | **PASSED** |
| **Complete Accounting Invariant** | $D + P + E = N_{\text{gen}}$ across all 12 runs | Verified on 12 runs | **PASSED** |
| **Non-Negative Delay Invariant** | $\text{Delay} > 0$ for all delivered bundles | Min delivered delay: 33481 ms | **PASSED** |
| **Canonical Node Ordering** | `node_a < node_b` across all contact tables | 100% strictly enforced | **PASSED** |
| **Deterministic Workload Consistency** | Workload identical across all 12 policy evaluations | 200 identical (src, dst, creation_t) tuples | **PASSED** |

---

## 3. Label Integrity & Derivation Definitions

> [!IMPORTANT]
> **Scientific Target Definitions**:
> - `delivered`: Binary flag indicating whether the packet reached its intended destination node under the specific simulated resource constraints (buffer, half-duplex contention, TTL).
> - `delivery_delay_ms`: Elapsed physical latency from creation to delivery ($t_{\text{deliv}} - t_{\text{creat}}$). Recorded as `-1` for undelivered packets.
> - `theoretical_delay_ms`: Offline theoretical lower bound computed by time-dependent A*. Represents the earliest achievable delivery time assuming infinite buffer and zero contention.
> - **No Artificial Radio Measurements**: These targets are derived strictly from discrete-event simulation over geometry-filtered contact schedules. They must **not** be presented as measured physical radio RSSI, SNR, or LoRa/NRF hardware performance.

---

## 4. Zero Data Leakage Certification

- **No Train/Test Split Leakage**: No machine learning training, validation, or test partitions have been created yet.
- **Independence of Benchmark**: The offline Time-Dependent A* oracle computes routes independently and does not leak future contact knowledge into the decentralized routing policies (`direct_delivery`, `epidemic`, `two_hop`).
