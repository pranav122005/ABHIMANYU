# DTN AI ROUTING — STAGE 5.1: MODEL VALIDITY AUDIT AND CAUSAL FEATURE CORRECTION

## Executive Summary

This audit investigates the empirical finding that the Stage 5 decentralized AI routing policies (**Shallow Decision Tree** and **Logistic Regression**) exhibited identical closed-loop simulation metrics to **Direct Delivery** across all 54 evaluated runs (e.g., exactly 49.3% PDR and 49 forwarding attempts at 50 m range).

Through rigorous source code inspection, mathematical derivation, feature causality verification, and simulation profiling, this audit identifies:
1. **The Exact Cause of Direct Delivery Equivalence**: An algorithmic bug in the simulation-derived teacher label ($T_v < T_u$) that mathematically guaranteed $100\%$ rejection of all intermediate relay encounters, collapsing the training target to `peer_is_destination`.
2. **Feature-Causality Violations**: The inclusion of `contact_duration_ms` and `transfer_fits_contact`, which leaked future contact termination times ($t_{\text{end}}$) into contemporaneous encounter decisions.
3. **Causal & Algorithmic Corrections**: Implementation of strictly causal features (`contact_elapsed_ms`, `estimated_remaining_contact_ms`, `estimated_transfer_fits`) and a corrected teacher label recognizing both direct deliveries and optimal time-dependent multi-hop relays.
4. **Post-Correction Evaluation**: In closed-loop simulation across 54 runs on held-out seeds (100, 200, 300), the corrected Decision Tree achieves **79.0% to 80.3% PDR** (a +30% absolute improvement over Direct Delivery) while cutting forwarding attempts by **36% to 42%** compared to Epidemic routing. The corrected Logistic Regression achieves **59.3% to 63.7% PDR** with an ultra-conservative **90% reduction in forwarding transmissions**.

---

## Part A — Audit of Preliminary Stage 5 Model Behavior

### 1. Label Distribution & 100% Metric Collapse
In the initial Stage 5 dataset (`data/ai_experiments/decision_features.csv`, 168,348 rows):
- **Positive Labels (`target_should_forward == 1`)**: exactly **400** instances ($0.2376\%$).
- **Negative Labels (`target_should_forward == 0`)**: exactly **167,948** instances ($99.7624\%$).
- **Cross-Tabulation (`peer_is_destination` vs `target_should_forward`)**:

| `peer_is_destination` | `target == 0` | `target == 1` | Total |
| :---: | :---: | :---: | :---: |
| **0** (Intermediate Relay) | **167,948** | **0** | **167,948** |
| **1** (Destination Node) | **0** | **400** | **400** |
| **Total** | **167,948** | **400** | **168,348** |

**Empirical Finding**: `target_should_forward` was **100.00% identical** to `peer_is_destination`. Not a single intermediate relay opportunity was labeled positive across the entire dataset.

### 2. Breakdown of Teacher Label Reasons
The label generator recorded three categorical reasons:
- `inferior_or_redundant_path`: 166,830 instances ($99.09\%$)
- `truncated_contact`: 1,118 instances ($0.66\%$)
- `direct_destination_delivery`: 400 instances ($0.24\%$)
- `earlier_arrival_path`: **0 instances ($0.00\%$)**

### 3. Root-Cause Analysis: The Strict Inequality Fallacy
In `src/ai_decision_engine.py` (lines 198–228):
```python
route_hold = planner.find_earliest_arrival_path(
    source=sender, destination=pkt.destination, creation_time_ms=s_time, ...
)
route_fwd = planner.find_earliest_arrival_path(
    source=receiver, destination=pkt.destination, creation_time_ms=s_time + xfer_ms, ...
)
arr_hold = route_hold.arrival_time_ms if route_hold.success else float("inf")
arr_fwd = route_fwd.arrival_time_ms if route_fwd.success else float("inf")

if arr_fwd < arr_hold:
    label = 1
    label_reason = "earlier_arrival_path"
else:
    label = 0
    label_reason = "inferior_or_redundant_path"
```

**Mathematical Proof of Collapse**:
Let $u$ be the sender, $v$ the receiver, and $d$ the destination. At simulation time $s$, contact $(u, v)$ is active.
- `route_hold` searched for the optimal path from $u$ starting at $s$.
- Because contact $(u, v)$ is available at $s$, one feasible path for $u$ is to transfer to $v$ (completing at $s + \text{xfer\_ms}$) and then follow any valid path from $v$.
- Therefore, the search space for `route_hold` **contains** the entire search space for `route_fwd`.
- By Bellman's principle of optimality:
  $$\text{Arrival}(P^*(u, s)) \le \text{Arrival}(P^*(v, s + \text{xfer\_ms})) \implies \text{arr\_hold} \le \text{arr\_fwd}$$
- Whenever transferring to $v$ at time $s$ was on the globally optimal path, $\text{arr\_hold} == \text{arr\_fwd}$.
- Because the code tested strict inequality `arr_fwd < arr_hold`, it evaluated $\text{arr\_fwd} < \text{arr\_hold}$ as **False** on every optimal hop!
- Whenever transferring to $v$ was suboptimal, $\text{arr\_hold} < \text{arr\_fwd}$, which was also **False**.
- **Result**: `arr_fwd < arr_hold` was mathematically incapable of evaluating to True for any contact in the trace.

### 4. Consequence for Trained Models & Simulation
- **Decision Tree**: Learned `if peer_is_destination <= 0.5: return 0; else: return 1;`.
- **Logistic Regression**: Assigned huge positive weight to `peer_is_destination` and negative bias, predicting 1 iff `peer_is_destination == 1`.
- **Test Metrics**: Both models achieved 100% test accuracy, precision, recall, F1, and ROC-AUC because the test target was an exact copy of the binary input feature.
- **Closed-Loop Simulator**: Routers never forwarded to any intermediate relay. Packets were only transferred when `peer == destination`. As a result, the models executed the exact same actions as `DirectDeliveryRouter`.

---

## Part B — Feature Causality Audit

### 1. Causality Violations Identified

| Feature Name | Preliminary Definition | Future Information Leaked | Physical Violation on ESP8266 |
|---|---|---|---|
| `contact_duration_ms` | `contact_end_ms - contact_start_ms` | Requires knowing exact future time when nodes move out of radio range. | Node cannot anticipate future radio cutoff upon initial RF beacon handshake. |
| `transfer_fits_contact` | $1 \text{ if } T_{\text{xfer}} \le (t_{\text{end}} - t_{\text{curr}})$ | Uses future contact termination clock $t_{\text{end}}$. | Evaluates physical channel drop before transmission begins. |

### 2. Causally Valid Replacements

To eliminate future-oracle leakage, the feature schema was revised to use strictly contemporaneous observations and local rolling history:

1. **`contact_elapsed_ms`**:
   $$\Delta t_{\text{elapsed}} = \max(0, t_{\text{curr}} - t_{\text{contact\_start}})$$
   - *Physical Semantics*: Recorded by local node timer upon establishing radio link. Strictly causal.
2. **`estimated_remaining_contact_ms`**:
   $$\hat{T}_{\text{remaining}} = \max\left(0, \bar{T}_{\text{hist}}(v) - \Delta t_{\text{elapsed}}\right)$$
   - *Physical Semantics*: $\bar{T}_{\text{hist}}(v)$ is the arithmetic mean of past *completed* encounters with peer $v$. If the peer is newly encountered, a network-wide prior (5,000 ms) is used.
3. **`estimated_transfer_fits`**:
   $$\hat{F}_{\text{transfer}} = \begin{cases} 1 & \text{if } T_{\text{xfer}} \le \hat{T}_{\text{remaining}} \\ 0 & \text{otherwise} \end{cases}$$
   - *Physical Semantics*: Conservative contemporaneous check based solely on historical duration estimates.

### 3. Simulation Boundary Preservation
In the revised discrete-event simulator:
- The router extracts features and makes forwarding decisions using strictly causal features ($\hat{T}_{\text{remaining}}, \hat{F}_{\text{transfer}}$).
- The simulator engine enforces physical transmission physics: if the contact terminates prematurely in reality ($t_{\text{curr}} + T_{\text{xfer}} > t_{\text{end}}$), the transfer is aborted and logged as `CONTACT_EXPIRED` / `truncated_contact_attempts`.
- This strictly segregates online decision-making from offline ground-truth simulation physics.

---

## Part C — Corrected Teacher Label Formulation

The offline teacher label must reward productive intermediate forwarding without falling into the strict-inequality fallacy or rewarding unpromising floods.

### Audited Teacher Target Specification
For sender $u$ encountering peer $v$ holding packet $P$ destined for $d$ at simulation time $t$:

$$\text{target\_should\_forward} = \begin{cases} 
0, & \text{if } t + T_{\text{xfer}} > t_{\text{end}} \quad \text{(physically truncated transfer)} \\
1, & \text{if } v == d \quad \text{(direct destination delivery)} \\
1, & \text{if } (u \to v)_t \text{ is the scheduled first hop on } P\text{'s optimal temporal A* path} \\
0, & \text{otherwise (inferior or redundant forwarding opportunity)}
\end{cases}$$

### Physical Justification
- **Direct Delivery**: Delivering directly to destination guarantees packet termination without additional hops.
- **Optimal Time-Dependent Hop**: The Time-Dependent A* oracle plans the global earliest-arrival route $R^*(P) = [h_0, h_1, \dots, h_{k-1}]$. If $h_0$ starts at contact time $t$ from $u$ to $v$, transferring to $v$ is globally optimal.
- **Redundant / Inferior Contact Suppression**: If $v$ is not the next hop on the optimal path (or encounters $u$ at the wrong time), transferring to $v$ would represent uncoordinated flooding. Labeling these encounters $0$ trains the model to withhold packets until a promising relay or destination arrives.

---

## Part D — Re-evaluation of the Learning Problem & Trade-offs

### Decision-Level Objectives
In decentralized opportunistic networks, routing optimizes multiple competing objectives:
1. **Delivery Ratio (PDR)**: Maximizing arrival probability before packet TTL expiry.
2. **Delivery Latency**: Minimizing end-to-end delay.
3. **Transmission Overhead**: Minimizing duplicate packets, channel contention, and radio energy consumption.

### The Trade-off Spectrum
- **Epidemic Routing (Flooding Upper Bound)**: Replicates bundles to every encountered peer. Achieves high PDR (~84.7%) and low delay (~2,500 s), but incurs extreme transmission overhead (~5,080 forwarding attempts per 100 packets, overhead ratio > 60x).
- **Direct Delivery (Single-Hop Lower Bound)**: Eliminates all multi-hop transmissions (overhead ratio 1.0x), but suffers poor PDR (49.3% to 57.7%) and high delay (~5,300 s).
- **Decentralized AI Policies**: Strike an intelligent balance by identifying productive intermediate relays while rejecting unproductive flooding encounters.

---

## Part E — Retrained Model Performance & Simulation Results

### 1. Decision Dataset Generation Summary
- **Total Generated Decision Instances**: **274,338** across 50 m, 100 m, and 200 m contact horizons (seeds 42, 43).
- **Class Distribution**: Negative (0): 272,740 ($99.42\%$) | Positive (1): 1,598 ($0.58\%$).
- **Partitioning (Grouped Strictly by `packet_id`)**:
  - Train (70%): 192,036 instances (positive support: 1,114)
  - Validation (15%): 35,825 instances (positive support: 237)
  - Test (15%): 46,477 instances (positive support: 247)
  - Zero packet overlap: $\text{Train} \cap \text{Val} \cap \text{Test} = \emptyset$.

### 2. Offline Test Set Classification Metrics

| Candidate Model | Accuracy | Precision | Recall | F1-Score | ROC-AUC | Positive Support | Predicted Positives |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Shallow Decision Tree** | **91.27%** | 0.0545 | **0.9433** | **0.1030** | **0.9615** | 247 | 4,276 (9.2% rate) |
| **Logistic Regression** | **83.83%** | 0.0135 | **0.4089** | **0.0262** | **0.7456** | 247 | 7,470 (16.1% rate) |

#### Confusion Matrices (Test Set, $N = 46,477$)
- **Shallow Decision Tree**:
  $$\begin{pmatrix} \text{TN} & \text{FP} \\ \text{FN} & \text{TP} \end{pmatrix} = \begin{pmatrix} 42,187 & 4,043 \\ 14 & 233 \end{pmatrix}$$
  - *Analysis*: The decision tree captures **94.33%** of all productive forwarding opportunities (233 out of 247), while filtering out **91.25%** of unpromising flooding opportunities (42,187 true negatives).
- **Logistic Regression**:
  $$\begin{pmatrix} \text{TN} & \text{FP} \\ \text{FN} & \text{TP} \end{pmatrix} = \begin{pmatrix} 38,861 & 7,369 \\ 146 & 101 \end{pmatrix}$$

#### Exported Decision Tree Rules
```
|--- peer_is_destination <= 0.50
|   |--- remaining_ttl_ratio <= 0.78
|   |   |--- class: 0  (Hold aged packets; do not flood)
|   |--- remaining_ttl_ratio >  0.78
|   |   |--- estimated_remaining_contact_ms <= 4200.00
|   |   |   |--- class: 0  (Hold if estimated window too short)
|   |   |--- estimated_remaining_contact_ms >  4200.00
|   |   |   |--- class: 1  (Forward to promising intermediate relay!)
|--- peer_is_destination >  0.50
|   |--- class: 1  (Direct delivery to destination!)
```

### 3. Closed-Loop In-Simulator Results (54 Runs Across Held-Out Seeds 100, 200, 300)

Evaluated under physical half-duplex contention, 2 MB buffer capacity, 250 KB/s transfer rate, and 50 ms connection setup overhead:

| Horizon | Policy | Classification | PDR (%) | Delivered / Gen | Mean Delay (s) | Median Delay (s) | Forwarding Attempts | Overhead Ratio |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **50 m** | `direct_delivery` | Decentralized Rule | **49.3%** | 49.3 / 100 | 5,368.7 s | 3,923.3 s | 49 | 1.0x |
| **50 m** | `two_hop` | Decentralized Rule | **83.7%** | 83.7 / 100 | 3,110.5 s | 2,143.8 s | 3,128 | 37.4x |
| **50 m** | `epidemic` | Decentralized Rule | **84.7%** | 84.7 / 100 | 2,514.6 s | 1,708.9 s | 5,079 | 60.0x |
| **50 m** | `decision_tree` | Decentralized AI | **79.0%** | 79.0 / 100 | 2,987.4 s | 1,984.2 s | **2,949** | **37.3x** |
| **50 m** | `logistic_regression` | Decentralized AI | **59.3%** | 59.3 / 100 | 4,682.1 s | 3,310.5 s | **473** | **8.0x** |
| **50 m** | `temporal_astar` | Offline Oracle | **70.7%** | 70.7 / 100 | 3,581.2 s | 2,329.2 s | 246 | 3.5x |
| **100 m** | `direct_delivery` | Decentralized Rule | **54.7%** | 54.7 / 100 | 5,140.9 s | 3,792.3 s | 55 | 1.0x |
| **100 m** | `two_hop` | Decentralized Rule | **83.7%** | 83.7 / 100 | 2,891.0 s | 1,929.8 s | 3,379 | 40.4x |
| **100 m** | `epidemic` | Decentralized Rule | **84.7%** | 84.7 / 100 | 2,395.2 s | 1,560.5 s | 5,081 | 60.0x |
| **100 m** | `decision_tree` | Decentralized AI | **80.3%** | 80.3 / 100 | 2,752.1 s | 1,811.4 s | **3,139** | **39.1x** |
| **100 m** | `logistic_regression` | Decentralized AI | **62.7%** | 62.7 / 100 | 4,411.3 s | 3,124.7 s | **517** | **8.2x** |
| **100 m** | `temporal_astar` | Offline Oracle | **64.0%** | 64.0 / 100 | 3,568.2 s | 2,185.9 s | 236 | 3.7x |
| **200 m** | `direct_delivery` | Decentralized Rule | **57.7%** | 57.7 / 100 | 4,905.0 s | 3,469.2 s | 58 | 1.0x |
| **200 m** | `two_hop` | Decentralized Rule | **83.7%** | 83.7 / 100 | 2,745.0 s | 1,733.5 s | 3,516 | 42.0x |
| **200 m** | `epidemic` | Decentralized Rule | **85.0%** | 85.0 / 100 | 2,344.0 s | 1,505.5 s | 5,088 | 59.9x |
| **200 m** | `decision_tree` | Decentralized AI | **80.3%** | 80.3 / 100 | 2,610.4 s | 1,675.2 s | **3,257** | **40.6x** |
| **200 m** | `logistic_regression` | Decentralized AI | **63.7%** | 63.7 / 100 | 4,198.6 s | 2,941.8 s | **503** | **7.9x** |
| **200 m** | `temporal_astar` | Offline Oracle | **54.0%** | 54.0 / 100 | 4,119.9 s | 2,616.8 s | 243 | 4.5x |

### 4. Key Scientific Observations
1. **Resolution of Direct Delivery Equivalence**:
   - The corrected Decision Tree achieves **79.0% to 80.3% PDR**, compared to Direct Delivery's 49.3% to 57.7% PDR.
   - Forwarding attempts average ~3,100 (clearly engaging intermediate relays), while cutting over **1,800 to 2,100 redundant forwarding attempts** relative to Epidemic routing.
2. **Logistic Regression as an Energy-Efficient Relay Policy**:
   - Logistic Regression achieves a balanced operating point: **59.3% to 63.7% PDR** with only ~500 forwarding attempts.
   - It delivers an overhead ratio of only **8.0x** (compared to Epidemic's 60.0x), making it attractive for battery-constrained IoT sensor nodes.
3. **Robustness Across Held-Out Seeds**:
   - Both AI policies demonstrated stable performance across held-out seeds (100, 200, 300) without significant variance or degradation.

---

## Part F — ESP8266 Deployment Feasibility Claims Audit

### 1. Distinction Between Code-Derived Estimates vs Hardware Profiling
All resource metrics in this stage are **static code-derived analytical estimates** based on the Xtensa L106 instruction set architecture and C++ data structures. No physical ESP8266 silicon was flashed, and no live radio measurements were taken.

| Metric | Source of Value | Physical Meaning |
|---|---|---|
| Flash Size (< 512 B) | GCC Xtensa opcode analysis | Byte count of the compiled instruction stream for `decide_forwarding_decision_tree`. |
| RAM Overhead (0 B) | Static C++ code inspection | Function uses only stack frame variables (`LocalDecisionFeatures`); zero heap allocations (`malloc`/`new`). |
| Stack Frame (~24–44 B) | Xtensa 32-bit calling convention | Storage for function arguments and local registers on stack. |
| Latency (< 1.0 $\mu$s) | Analytical cycle count calculation | 3–4 conditional branch instructions executed at 80 MHz clock speed ($80 \text{ cycles} \implies 1.0\,\mu\text{s}$). |

### 2. Standalone C++ Firmware Exports
Both models were exported as self-contained C++ header files in [`models/stage5/`](file:///D:/ABHIMANYU/dtn-ai-routing/models/stage5/):
- [`decision_tree_esp8266.cpp`](file:///D:/ABHIMANYU/dtn-ai-routing/models/stage5/decision_tree_esp8266.cpp)
- [`logistic_regression_esp8266.cpp`](file:///D:/ABHIMANYU/dtn-ai-routing/models/stage5/logistic_regression_esp8266.cpp)

Each header includes the `LocalDecisionFeatures` struct with the 11 strictly causal features and inline evaluation functions.

---

## Part G — Visual Artifacts & Deliverables

All 7 publication plots have been regenerated and verified in [`reports/figures/stage5/`](file:///D:/ABHIMANYU/dtn-ai-routing/reports/figures/stage5/):
1. `pdr_by_policy_and_range.png`: PDR comparison across policies and horizons.
2. `delay_by_policy_and_range.png`: Mean delivery latency across policies and horizons.
3. `forwarding_overhead_by_policy.png`: Forwarding attempts and overhead transmission ratios.
4. `pdr_vs_delay_tradeoff.png`: Multi-objective Pareto frontier showing PDR vs delay tradeoff.
5. `model_roc_pr_curves.png`: Test set ROC and Precision-Recall curves.
6. `model_footprint_comparison.png`: Static analytical flash, RAM, and operation counts for ESP8266.
7. `seed_variability_comparison.png`: Performance consistency across held-out seeds (100, 200, 300).

