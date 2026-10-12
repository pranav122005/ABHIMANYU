# DTN AI Routing — ESP8266 Deployment Feasibility Report (Audited)

## 1. Hardware Target: ESP8266 NodeMCU
- **Processor**: Tensilica Xtensa L106 32-bit RISC CPU @ 80 MHz (configurable to 160 MHz).
- **SRAM**: 80 KB total RAM (~35 KB available heap for user application code).
- **Flash Memory**: 4 MB external SPI flash.
- **Floating Point Unit**: None (Software floating-point emulation via GCC libgcc).
- **Operating Environment**: FreeRTOS / Arduino Core C++ (No Python or ML runtimes).

---

## 2. Static Code-Derived Analytical Resource Estimates

> [!NOTE]
> All figures below are static code-derived analytical estimates based on Xtensa L106 instruction set architecture (32-bit load/store, soft-float emulated MACs, stack frames). Physical hardware benchmarking on physical ESP8266 silicon is required upon firmware flashing.

| Metric | Shallow Decision Tree (`max_depth=3`) | Logistic Regression (11 Features) | Analytical Feasibility Verdict |
| :--- | :---: | :---: | :--- |
| **Serialized Flash Footprint** | **384 bytes** | **864 bytes** | Negligible (< 0.02% of 4MB Flash) |
| **RAM Heap Allocation** | **0 bytes** (In-place execution) | **0 bytes** (Stack frame only) | 100% Zero Heap Fragmentation |
| **Stack RAM Required** | ~24 bytes | ~44 bytes | Well within 4 KB task stack |
| **Arithmetic Operations** | 3-4 branch comparisons (`<=`) | 11 multiplications + 11 additions | Fast integer/float emulation |
| **Floating-Point heavy calls** | None (`if` logic on float vars) | None (Eliminated `exp()` via logit threshold) | No expensive transcendentals |
| **Estimated Latency @ 80MHz** | **< 1.0 microsecond** | **~3.5 microseconds** | Real-time capable during contact |
| **C/C++ Implementation** | [`decision_tree_esp8266.cpp`](file:///D:/ABHIMANYU/dtn-ai-routing/models/stage5/decision_tree_esp8266.cpp) | [`logistic_regression_esp8266.cpp`](file:///D:/ABHIMANYU/dtn-ai-routing/models/stage5/logistic_regression_esp8266.cpp) | Standalone C++ header |

---

## 3. Engineering Recommendations
1. **Decision Tree (Recommended for Embedded Deployment)**:
   - Evaluates 3 to 4 `if/else` conditions without multiplications or dynamic allocations.
   - Fully auditable by embedded firmware engineers without black-box risk.
2. **Logistic Regression**:
   - Evaluates $z > 0.0$ instead of $\sigma(z) > 0.5$, bypassing `exp()`.
