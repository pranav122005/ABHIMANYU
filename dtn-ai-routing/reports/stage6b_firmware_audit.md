# DTN AI Routing — Stage 6B: Firmware Audit and Target Build Validation Report

**Date**: October 2026  
**Repository**: `D:\ABHIMANYU\dtn-ai-routing`  
**Target Architecture**: ESP8266 NodeMCU v2 (Tensilica Xtensa L106 @ 80 MHz, ~80 KB SRAM, 4 MB Flash)  
**Status**: All audits completed, defects corrected, 9/9 host unit tests passed, target cross-compilation verified with zero warnings, 62/62 regression tests passed.

---

## 1. Executive Summary & Audit Baseline

Stage 6B performed a rigorous, defensive audit of the modular C++ firmware foundation constructed in Stage 6A (`firmware/esp8266_node/`). The audit verified AI model compatibility, memory constraints, packet serialization safety, forwarding lifecycle invariants, timer rollover handling, and actual target compilation with the ESP8266 toolchain.

### Audit Baseline
- **Initial Test Suite**: 61 passed in 11.13s (Stages 1 through 6A).
- **Final Test Suite**: 62 passed in 14.00s (added target PlatformIO cross-compilation test).
- **Host Unit Test Harness**: Expanded from 6 to 9 unit tests in `tests/test_firmware.cpp` (100% pass rate).
- **Target Cross-Compilation**: Verified on PlatformIO Core 6.2.0 with Espressif 8266 platform 4.2.1 and GCC 10.3.0 for `nodemcuv2`. Built with `-std=c++17 -Wall -Wextra -Os` yielding **zero warnings**.

---

## 2. AI Model Compatibility Audit

The decision-tree inference routine (`models/stage5/decision_tree_esp8266.cpp`) and the feature construction bridge (`firmware/esp8266_node/include/router_interface.h`) were audited against the Python reference implementation (`src/ai_decision_engine.py`) and feature dictionary (`data/ai_experiments/feature_dictionary.md`).

### Feature Schema & Causality Alignment (11 Features)

| Feature # | Feature Name in Python | C++ Field in `LocalDecisionFeatures` | Type | Calculation / Source | Causal Verification |
|---|---|---|---|---|---|
| 1 | `peer_is_destination` | `peer_is_destination` | `uint8_t` | `strcmp(ctx.peer_id, pkt.header.destination) == 0 ? 1 : 0` | Strictly local |
| 2 | `packet_size_bytes` | `packet_size_bytes` | `uint32_t` | `pkt.header.size_bytes` | Local packet header |
| 3 | `packet_priority` | `packet_priority` | `uint8_t` | `pkt.header.priority` (1, 2, or 3) | Local packet header |
| 4 | `remaining_ttl_ratio` | `remaining_ttl_ratio` | `float` | `(expiry - now) / (expiry - creation)` clamped to `[0.0, 1.0]` | Local clock + header |
| 5 | `packet_hops` | `packet_hops` | `uint8_t` | `pkt.header.hops` | Local packet header |
| 6 | `transfer_duration_ms` | `transfer_duration_ms` | `uint32_t` | `overhead_ms + ceil(size * 1000.0 / rate_bps)` | Local radio model |
| 7 | `contact_elapsed_ms` | `contact_elapsed_ms` | `uint32_t` | `now - contact_start_ms` | Local encounter clock |
| 8 | `estimated_remaining_contact_ms` | `estimated_remaining_contact_ms` | `uint32_t` | `max(0, avg_hist_duration - contact_elapsed)` | Local history heuristic |
| 9 | `estimated_transfer_fits` | `estimated_transfer_fits` | `uint8_t` | `transfer_duration <= est_remaining ? 1 : 0` | Local comparison |
| 10 | `local_buffer_utilization` | `local_buffer_utilization` | `float` | `buffer_bytes / max_buffer_bytes` clamped to `[0.0, 1.0]` | Local buffer state |
| 11 | `peer_encounter_frequency` | `peer_encounter_frequency` | `uint16_t` | `peer_encounter_count` | Local encounter history |

### Audit Findings:
1. **Zero Future Oracle Leakage**: The firmware relies solely on local historical averages (`avg_historical_contact_ms`), local buffer state, and packet metadata. No simulated ground-truth future contact end times or oracle scores are accessed.
2. **Threshold & Decision Integrity**: When `peer_is_destination == 1`, forwarding is guaranteed immediately. When evaluating intermediate relay opportunities, the exported decision tree faithfully replicates the Python tree's decision boundaries (e.g. `remaining_ttl_ratio > 0.85`, `estimated_transfer_fits == 1`).

---

## 3. Packet Serialization & Wire Protocol Audit

### Identified Defect in Baseline Implementation
The baseline Stage 6A implementation relied on `memcpy(out_buf, &header, sizeof(PacketWireHeader))`. While functional under a single host compiler, this pattern is brittle in embedded deployments because:
- Compiler struct padding/alignment rules may differ between host x86_64 and Xtensa 32-bit architectures.
- Host endianness is assumed without explicit byte-order encoding.
- Wire buffers could not safely validate truncated or corrupted payloads.

### Corrected Wire Protocol Specification
A fixed, explicit little-endian binary layout was implemented with manual field serialization and deserialization:

```
+-----------------------------------------------------------------------------+
| Byte Offset | Field Name         | Width (Bytes) | Encoding                 |
+-------------+--------------------+---------------+--------------------------+
| 0..31       | packet_id          | 32            | ASCII string (null-term) |
| 32..47      | source             | 16            | ASCII string (null-term) |
| 48..63      | destination        | 16            | ASCII string (null-term) |
| 64..65      | size_bytes         | 2             | uint16_t, Little-Endian  |
| 66          | priority           | 1             | uint8_t (1=Norm,2=Hi,3=U)|
| 67          | hops               | 1             | uint8_t                  |
| 68..71      | creation_time_ms   | 4             | uint32_t, Little-Endian  |
| 72..75      | expiry_time_ms     | 4             | uint32_t, Little-Endian  |
| 76..77      | payload_len        | 2             | uint16_t, Little-Endian  |
| 78..333     | payload            | 0..256        | Raw binary data bytes    |
+-----------------------------------------------------------------------------+
```

- **Minimum Wire Frame Size (`PACKET_WIRE_MIN_BYTES`)**: `78` bytes (76B header + 2B payload_len).
- **Maximum Wire Frame Size**: `334` bytes (78B + 256B max payload). Fits comfortably in single or double MTU fragments across standard micro-radios.

### Strict Deserialization Validation Guards Added
`Packet::deserialize(const uint8_t* in_buf, size_t len)` now strictly enforces:
1. `len >= PACKET_WIRE_MIN_BYTES` (rejects truncated frames < 78 bytes).
2. Non-empty identifiers: `packet_id[0] != '\0'`, `source[0] != '\0'`, `destination[0] != '\0'`.
3. Priority bounds: `1 <= priority <= 3`. Invalid priority values immediately reject the packet.
4. Non-inverted TTL: `int32_t(expiry_time_ms - creation_time_ms) >= 0`.
5. Payload bounds: `payload_len <= MAX_PAYLOAD_BYTES` (256).
6. Payload truncation check: `len >= PACKET_WIRE_MIN_BYTES + payload_len`.

---

## 4. Buffer Lifecycle & Forwarding Guard Audit

### 1. In-Flight Transmission Isolation Guard
- **Defect Found**: In `NodeApp::step_route_and_forward()`, the packet iteration evaluated all packets in the buffer. If a packet was in `STATE_TRANSMITTING` (e.g. non-blocking radio transmission in progress), a subsequent tick could re-evaluate and re-transmit the same packet.
- **Correction Applied**:
  ```cpp
  for (size_t s = 0; s < buffer_.capacity_slots(); ++s) {
      Packet* pkt = buffer_.get_slot(s);
      if (!pkt || pkt->is_expired(current_time_ms) || pkt->state != STATE_PENDING) {
          continue; // Skip expired, empty, or currently transmitting packets
      }
      ...
  ```
  Verified via dedicated unit test `test_inflight_packet_isolation()`.

### 2. Timer Rollover Safety Across uint32_t Wrap-Around
- **Defect Found**: `Packet::is_expired(now)` used `now >= expiry_time_ms`. When `now` rolls over modulo $2^{32}$ (after ~49.7 days of continuous ESP8266 operation), comparison against pre-rollover timestamps yields incorrect truth values.
- **Correction Applied**:
  Adopted the standard Linux kernel `time_after()` pattern using signed 32-bit differences:
  ```cpp
  bool Packet::is_expired(uint32_t current_time_ms) const {
      return static_cast<int32_t>(current_time_ms - header.expiry_time_ms) >= 0;
  }
  ```
  Correspondingly updated `remaining_ttl_ms()` and `remaining_ttl_ratio()` to protect arithmetic during clock wrapping. Verified via unit test `test_timer_rollover_safety()`.

### 3. Buffer Size Underflow Protection
- **Defect Found**: `PacketBuffer::remove()` and `PacketBuffer::prune_expired()` subtracted packet sizes from `total_bytes_` directly: `total_bytes_ -= size`.
- **Correction Applied**: Added defensive underflow clamps:
  ```cpp
  if (slots_[i].header.size_bytes >= total_bytes_) {
      total_bytes_ = 0;
  } else {
      total_bytes_ -= slots_[i].header.size_bytes;
  }
  if (occupied_count_ > 0) {
      occupied_count_--;
  }
  ```

---

## 5. Static Memory Footprint & Portability Measurements

### Exact Host Compiler `sizeof` Measurements (x86_64 GCC 15.2.0)
The compiler's concrete struct measurements were extracted directly via C++ harness:

```
[Size Audit] sizeof(PacketWireHeader)     =  76 bytes
[Size Audit] sizeof(Packet)               = 340 bytes  (76B header + 256B payload + 2B len + state + padding)
[Size Audit] sizeof(LocalDecisionFeatures)=  44 bytes  (11 features)
[Size Audit] sizeof(NodeConditionReport)  =  51 bytes  (Telemetry record)
[Size Audit] sizeof(PacketBuffer)         = 7536 bytes (~7.36 KB: 16 slots * 340B + 64 seen IDs + flags)
[Size Audit] sizeof(DecisionTreeRouter)   =   8 bytes  (Virtual table pointer only)
[Size Audit] sizeof(EventLogger)          = 400 bytes  (Circular buffer of 16 events)
[Size Audit] sizeof(ReportQueue)          = 432 bytes  (8 queued reports + indices)
[Size Audit] sizeof(NodeApp)              = 424 bytes  (Peer histories + metrics counters + timers)
--------------------------------------------------------------------------------
[Size Audit] Total Static Node Object     = 8792 bytes (~8.58 KB)
```

### ESP8266 Target Cross-Compilation Measurements (PlatformIO / Xtensa GCC 10.3.0)
The entire firmware stack—including Arduino core, memory allocators, C++17 runtime, decision tree router, packet buffer, and coordinator—was compiled for the physical ESP8266 NodeMCU v2 target:

```
Target Board:      nodemcuv2 (ESP-12E Module)
Processor:         Tensilica Xtensa L106 @ 80 MHz
Operating Voltage: 3.3V
Physical RAM:      80 KB total SRAM (~40 KB available for application heap/bss)
Physical Flash:    4 MB SPI Flash (1 MB mapped for application firmware)

PlatformIO Build Results:
--------------------------------------------------------------------------------
RAM:   [=====     ]  53.3%  (used 43,640 bytes from 81,920 bytes)
Flash: [===       ]  25.9%  (used 270,679 bytes from 1,044,464 bytes)
--------------------------------------------------------------------------------
Free RAM Headroom:   38,280 bytes (~37.4 KB) available for stack, buffers, and radio driver
Free Flash Headroom: 773,785 bytes (~755 KB) available for radio stacks and OTA updates
Build Status:        SUCCESS (Zero compiler warnings under -Wall -Wextra)
```

---

## 6. Host Unit Test Execution (Stage 6B Test Harness)

The host unit test suite in `tests/test_firmware.cpp` was compiled using host GCC and executed with 9/9 passing tests:

```
==============================================================
 ESP8266 DTN NODE FIRMWARE AUDIT - HOST TEST SUITE (Stage 6B)
==============================================================
[RUNNING] test_packet_serialization_roundtrip... PASSED
[RUNNING] test_buffer_capacity_duplicate_and_expiry... PASSED
[RUNNING] test_routing_feature_construction_and_decision_tree... PASSED
[RUNNING] test_fake_transport_tx_rx... PASSED
[RUNNING] test_condition_report_queue... PASSED
[RUNNING] test_node_app_coordinator_cycle... PASSED
[RUNNING] test_timer_rollover_safety... PASSED
[RUNNING] test_inflight_packet_isolation... PASSED
[RUNNING] test_buffer_underflow_safety... PASSED
==============================================================
 Results: 9 / 9 passed.
==============================================================
```

### Full Repository Regression Test Suite
All 62 tests across the complete DTN project passed:
- `test_ai_routing.py`: 10 tests passed
- `test_cpp_parity.py`: 6 tests passed
- `test_dtn_simulator.py`: 9 tests passed
- `test_finalized_dataset.py`: 5 tests passed
- `test_firmware_parity.py`: 4 tests passed (including automated target PlatformIO build verification)
- `test_inspect_datasets.py`: 11 tests passed
- `test_temporal_astar.py`: 7 tests passed
- `test_vannes_contact_graph.py`: 10 tests passed
- **Total: 62 passed in 14.00s.**

---

## 7. Hardware Abstraction Status & Unconfirmed Choices

To maintain architectural integrity before physical hardware integration, no physical radio or display drivers were hardcoded:

1. **Radio Transport (`ITransport`)**:
   - `FakeTransport` remains the reference implementation for tests and simulation.
   - The choice between **NRF24L01** (SPI interface, 32-byte hardware packets requiring fragmentation) and **ESP-NOW** (native 802.11 vendor action frames, 250-byte MTU matching our 256-byte payload) remains decoupled.
2. **Display (`IDisplay`)**:
   - `NullDisplay` serves as the headless default. Supports clean replacement by `SSD1306Wire` (I2C) once the physical OLED module is selected.
3. **Storage (`IStorage`)**:
   - `RamStorage` provides bounded in-memory buffer logging. An SPI Flash / LittleFS driver can be plugged in without modifying routing or buffer logic.

---

## 8. Conclusion & Sign-Off

The Stage 6B audit confirmed that:
1. The exported Stage 5.2 shallow decision tree integrates with zero semantic distortion and strictly causal inputs.
2. Packet wire serialization is deterministic, endian-safe, and bounds-checked against malformed inputs.
3. In-flight transmission isolation, timer rollover safety, and buffer capacity accounting are thoroughly tested and verified.
4. Target ESP8266 cross-compilation builds cleanly with 53.3% RAM and 25.9% Flash utilization, leaving ample headroom for physical radio drivers.
5. All 62 project regression tests pass cleanly.

The firmware architecture is verified, stable, and ready for physical communication hardware integration.

