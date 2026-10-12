# DTN AI ROUTING — STAGE 5: DECENTRALIZED AI EVALUATION REPORT (AUDITED)

## Executive Summary
This report presents the audited, causally corrected evaluation of decentralized AI routing policies for urban Delay-Tolerant Networks. 

Using strictly causal local features and simulation-derived teacher labels, a **Shallow Decision Tree** and **Logistic Regression** model were trained and benchmarked against Direct Delivery, Two-Hop Relay, Epidemic Routing, and the offline Time-Dependent A* oracle across 54 independent closed-loop simulation runs.

---

## 1. Decision-Level Model Performance (Test Split)

Evaluated on held-out test packets (zero packet leakage from training):

| Candidate Model | Accuracy | Precision | Recall | F1-Score | ROC-AUC | Embedded C++ Artifact |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Shallow Decision Tree** | **91.3%** | 0.054 | 0.943 | **0.103** | **0.962** | [`decision_tree_esp8266.cpp`](file:///D:/ABHIMANYU/dtn-ai-routing/models/stage5/decision_tree_esp8266.cpp) |
| **Logistic Regression** | **83.8%** | 0.013 | 0.409 | **0.026** | **0.746** | [`logistic_regression_esp8266.cpp`](file:///D:/ABHIMANYU/dtn-ai-routing/models/stage5/logistic_regression_esp8266.cpp) |

### Test Split Confusion Matrices & Class-Specific Support
- **Decision Tree**: Support: 247 positive, 46230 negative. Confusion Matrix: `[[42187, 4043], [14, 233]]`.
- **Logistic Regression**: Support: 247 positive, 46230 negative. Confusion Matrix: `[[38861, 7369], [146, 101]]`.

---

## 2. In-Simulator Closed-Loop Results Across Held-Out Seeds

Evaluated across held-out seeds (100, 200, 300) under full simulator constraints (half-duplex contention, 2 MB buffer, 250 KB/s transfer rate):

| Range | Policy | Classification | PDR (%) | Delivered / Gen | Mean Delay (s) | Median Delay (s) | Fwd Attempts | Overhead Ratio |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **50 m** | `direct_delivery` | Decentralized Rule | **49.3%** | 49.3 / 100 | 5368.7 s | 3923.3 s | 49 | 1.0x |
| **50 m** | `two_hop` | Decentralized Rule | **83.7%** | 83.7 / 100 | 3110.5 s | 2143.8 s | 3,128 | 37.4x |
| **50 m** | `epidemic` | Decentralized Rule | **84.7%** | 84.7 / 100 | 2514.6 s | 1708.9 s | 5,079 | 60.0x |
| **50 m** | `decision_tree` | Decentralized AI | **79.0%** | 79.0 / 100 | 2550.9 s | 1587.7 s | 2,948 | 37.3x |
| **50 m** | `logistic_regression` | Decentralized AI | **59.3%** | 59.3 / 100 | 4477.7 s | 2667.1 s | 473 | 8.0x |
| **50 m** | `temporal_astar` | Offline Oracle | **70.7%** | 70.7 / 100 | 3581.2 s | 2329.2 s | 246 | 3.5x |
| **100 m** | `direct_delivery` | Decentralized Rule | **54.7%** | 54.7 / 100 | 5140.9 s | 3792.3 s | 54 | 1.0x |
| **100 m** | `two_hop` | Decentralized Rule | **83.7%** | 83.7 / 100 | 2891.0 s | 1929.8 s | 3,379 | 40.4x |
| **100 m** | `epidemic` | Decentralized Rule | **84.7%** | 84.7 / 100 | 2395.2 s | 1560.5 s | 5,080 | 60.0x |
| **100 m** | `decision_tree` | Decentralized AI | **80.3%** | 80.3 / 100 | 2394.0 s | 1524.4 s | 3,139 | 39.1x |
| **100 m** | `logistic_regression` | Decentralized AI | **62.7%** | 62.7 / 100 | 4325.9 s | 2608.2 s | 516 | 8.2x |
| **100 m** | `temporal_astar` | Offline Oracle | **64.0%** | 64.0 / 100 | 3568.2 s | 2185.9 s | 236 | 3.7x |
| **200 m** | `direct_delivery` | Decentralized Rule | **57.7%** | 57.7 / 100 | 4905.0 s | 3469.2 s | 57 | 1.0x |
| **200 m** | `two_hop` | Decentralized Rule | **83.7%** | 83.7 / 100 | 2745.0 s | 1733.5 s | 3,516 | 42.0x |
| **200 m** | `epidemic` | Decentralized Rule | **85.0%** | 85.0 / 100 | 2344.0 s | 1505.5 s | 5,088 | 59.9x |
| **200 m** | `decision_tree` | Decentralized AI | **80.3%** | 80.3 / 100 | 2296.8 s | 1417.5 s | 3,257 | 40.5x |
| **200 m** | `logistic_regression` | Decentralized AI | **63.7%** | 63.7 / 100 | 3939.4 s | 2384.3 s | 503 | 7.9x |
| **200 m** | `temporal_astar` | Offline Oracle | **54.0%** | 54.0 / 100 | 4119.9 s | 2616.8 s | 242 | 4.5x |

---

## 3. Scientific Analysis & Key Takeaways

1. **Resolution of Direct Delivery Equivalence**:
   - The Stage 5 audit revealed that the preliminary teacher label suffered from an inequality bug that marked 100% of intermediate relay opportunities as negative, causing the models to learn destination-only forwarding.
   - With the corrected teacher labeling, the models learn to accept productive intermediate relays while pruning unpromising contacts.
2. **Zero Information Leakage & Strictly Causal Features**:
   - Replaced future-dependent contact durations with strictly causal elapsed and history-based estimates.
   - Evaluated on completely held-out random seeds (100, 200, 300) with disjoint packet groups.
3. **ESP8266 Feasibility**:
   - Analytical estimates confirm static code footprints under 512 bytes flash and 0 bytes dynamic heap allocation.
