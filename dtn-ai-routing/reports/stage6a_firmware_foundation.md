# DTN AI Routing — Stage 6A: ESP8266 Node Firmware Foundation Report

**Document ID**: `reports/stage6a_firmware_foundation.md`  
**Date**: October 2026  
**Status**: COMPLETE / VERIFIED  
**Target Hardware Architecture**: Espressif ESP8266 NodeMCU v2 (Tensilica Xtensa L106 @ 80 MHz, 80 KB SRAM, 4 MB Flash)  
**Host Test Environment**: Windows host / GCC 15.2.0 (`x86_64-w64-mingw32-g++.exe -std=c++17`)  
**Existing Test Suite**: **61 passed in 10.20s** (Expanded from 58)  

---

## 1. Executive Summary

Stage 6A establishes the complete modular C++ firmware foundation for an autonomous Delay-Tolerant Network (DTN) node running on the ESP8266 NodeMCU. The software architecture strictly isolates network logic, packet storage, routing decisions, condition reporting, and loop orchestration from specific physical hardware choices (NRF24L01 vs. ESP-NOW; OLED model; storage media).

The validated Stage 5.2 shallow decision tree (`models/stage5/decision_tree_esp8266.cpp`) has been integrated directly without duplication. The entire firmware has been verified via a native host C++ test harness (`tests/test_firmware.cpp`) and automated pytest suite (`tests/test_firmware_parity.py`), confirming 100% test pass rate across packet serialization, bounded buffer management, duplicate suppression, causal feature construction, decision-tree execution, test transport flow, and non-blocking application loop coordination.

---

## 2. Firmware Architecture & Directory Layout

The firmware is organized according to standard PlatformIO and Arduino conventions under `firmware/esp8266_node/`:

```
firmware/esp8266_node/
├── platformio.ini              # PlatformIO project configuration (esp8266 / nodemcuv2, C++17)
├── include/
│   ├── dtn_types.h             # Common enumerations (BufferOutcome, ForwardingState, LinkStatus, EventCode)
│   ├── node_config.h           # Node identity, bounded prototype limits, timing intervals, dtn_safe_strcpy
│   ├── packet.h                # PacketWireHeader (44B), Packet class, serialization/deserialization
│   ├── packet_buffer.h         # Bounded slot pool, duplicate suppression ring, TTL expiry pruning
│   ├── router_interface.h      # IRouter interface, EncounterContext, 11-feature LocalDecisionFeatures builder
│   ├── decision_tree_router.h  # Adapter directly invoking Stage 5.2 decide_forwarding_decision_tree
│   ├── direct_delivery_router.h# Baseline non-AI comparison router (direct-destination only)
│   ├── transport_interface.h   # Abstract ITransport for peer discovery, send, receive, link status
│   ├── fake_transport.h        # Strictly test-only mock transport for unit testing (FIFO queue & loopback)
│   ├── display_interface.h     # Abstract IDisplay for status snapshots (NodeStatus)
│   ├── null_display.h          # Null/RAM status cache for headless nodes and testing
│   ├── storage_interface.h     # Abstract IStorage for non-volatile packet & event persistence
│   ├── ram_storage.h           # RAM-backed mock storage for host testing
│   ├── condition_report.h      # Versioned NodeConditionReport struct (43B), ReportQueue bounded FIFO
│   ├── event_logger.h          # Non-blocking bounded ring buffer for recent system events
│   └── node_app.h              # Autonomous non-blocking coordinator state machine
└── src/
    ├── packet.cpp              # Wire serialization & deserialization logic
    ├── packet_buffer.cpp       # Bounded slot management & duplicate suppression implementation
    ├── condition_report.cpp    # ReportQueue FIFO implementation
    ├── node_app.cpp            # Non-blocking tick() state machine implementation
    └── main.cpp                # Arduino setup() and loop() entry point (#ifdef ARDUINO)
```

---

## 3. Bounded Memory Design & Zero Dynamic Allocation Guarantee

The ESP8266 possesses ~80 KB total SRAM, of which ~35–45 KB is typically available for user heap and stack after the WiFi/radio core is loaded. Heap fragmentation caused by repeated `malloc` / `free` or `std::string` allocations is the leading cause of MCU crashes in long-running embedded nodes.

### 3.1 Static Footprint Budget

| Component | Prototype Configuration | Static RAM Allocation | Notes |
| :--- | :---: | :---: | :--- |
| **Packet Buffer** | `MAX_BUFFER_PACKETS = 16` | ~4,736 B (~4.6 KB) | Fixed slot pool; 0 bytes dynamic allocation |
| **Duplicate Seen Filter** | `MAX_SEEN_PACKETS = 64` | 2,048 B (~2.0 KB) | Circular ring buffer of 32-byte packet IDs |
| **Condition Report Queue** | `MAX_QUEUED_REPORTS = 8` | ~344 B | Compact 43-byte versioned telemetry records |
| **Event Log** | `MAX_EVENT_LOG_ENTRIES = 16` | ~384 B | Circular ring buffer of system events |
| **Peer Encounter History** | `MAX_TRACKED_PEERS = 8` | ~256 B | Causal contact duration and encounter counters |
| **Total Runtime RAM** | — | **~7.7 KB** | **Leaves > 30 KB free SRAM on ESP8266** |

**Zero Heap Allocation Rule**: No dynamic memory allocations (`new`, `malloc`, `std::vector`, or `std::string`) are invoked in any packet buffering, forwarding, or logging routine. All memory is statically allocated or allocated on the execution stack.

---

## 4. Stage 5.2 Decision Tree Integration (Part B)

### 4.1 Safe Direct Code Reuse
Rather than duplicating or transcribing the decision tree logic, `decision_tree_router.h` directly `#include`s the verified Stage 5.2 model file:
```cpp
#include "../../../models/stage5/decision_tree_esp8266.cpp"
```
Because `decision_tree_esp8266.cpp` is protected by include guards (`#ifndef DECENTRALIZED_DTN_ROUTER_H` and `#ifndef LOCAL_DECISION_FEATURES_DEF`), it compiles cleanly into both the firmware and host test harnesses without multiple definition conflicts.

### 4.2 Strictly Causal Feature Construction
The firmware constructs `LocalDecisionFeatures` inside `router_interface.h` via `build_decision_features()`:

```cpp
LocalDecisionFeatures feats;
feats.peer_is_destination = (strcmp(ctx.peer_id, pkt.header.destination) == 0) ? 1 : 0;
feats.packet_size_bytes = pkt.header.size_bytes;
feats.packet_priority = pkt.header.priority;
feats.remaining_ttl_ratio = pkt.remaining_ttl_ratio(ctx.current_time_ms);
feats.packet_hops = pkt.header.hops;
feats.transfer_duration_ms = ctx.transfer_overhead_ms + ceilf((pkt.header.size_bytes * 1000.0f) / ctx.transfer_rate_bytes_sec);
feats.contact_elapsed_ms = (ctx.current_time_ms >= ctx.contact_start_ms) ? (ctx.current_time_ms - ctx.contact_start_ms) : 0;
feats.estimated_remaining_contact_ms = (ctx.avg_historical_contact_ms > elapsed_ms) ? (ctx.avg_historical_contact_ms - elapsed_ms) : 0;
feats.estimated_transfer_fits = (feats.transfer_duration_ms <= feats.estimated_remaining_contact_ms) ? 1 : 0;
feats.local_buffer_utilization = ctx.buffer_utilization;
feats.peer_encounter_frequency = ctx.peer_encounter_count;
```

**Causality Audit**:
- Zero knowledge of future contact end times or future contact counts.
- Zero offline oracle path scores or global topology metrics.
- Uses strictly local encounter history running averages and local buffer occupancy.

---

## 5. Non-Blocking Loop & Interface Abstractions

### 5.1 Main Coordinator Loop (`NodeApp::tick()`)
The `NodeApp::tick(uint32_t current_time_ms)` loop executes five non-blocking phases:
1. **Receive Phase** (`step_receive_packets`): Polls non-blocking `transport_.receive_packet()`. Directly delivers inbound packets destined for this node; buffers inbound transit packets.
2. **Routing & Forwarding Phase** (`step_route_and_forward`): Polls in-range peers, builds causal `EncounterContext`, evaluates `router_.should_forward(pkt, ctx)`, and transmits at most one packet per peer per tick to keep radio channel access responsive.
3. **Buffer Maintenance Phase** (`step_buffer_maintenance`): Prunes expired packets every `PRUNE_INTERVAL_MS` (1,000 ms).
4. **Condition Reporting Phase** (`step_condition_reporting`): Generates and queues a versioned `NodeConditionReport` every `report_interval_ms` (30,000 ms).
5. **Display Refresh Phase** (`step_display_update`): Refreshes `NodeStatus` snapshot every `DISPLAY_UPDATE_INTERVAL_MS` (500 ms).

### 5.2 Transport Abstraction (`ITransport` & `FakeTransport`)
Exposes `init()`, `send_packet()`, `receive_packet()`, `is_peer_in_range()`, and `get_link_status()`.
The `FakeTransport` implementation provides in-memory packet injection and transmission logging for automated host verification without hardware drivers.

### 5.3 Display & Storage Abstractions (`IDisplay`, `IStorage`)
- `NullDisplay`: Caches `NodeStatus` without requiring I2C OLED hardware.
- `RamStorage`: In-memory storage of packets and system audit events without requiring LittleFS / SD card hardware.

---

## 6. Host Unit Test Suite & Build Validation Results

### 6.1 Native C++ Test Suite (`tests/test_firmware.cpp`)
Compiled and executed via `g++ -O2 -std=c++17 -Wall -Wextra`:

| Test Name | Validated Property | Status |
| :--- | :--- | :---: |
| `test_packet_serialization_roundtrip` | Byte packing wire format, priority, TTL calculation, unpack verification | **PASSED** |
| `test_buffer_capacity_duplicate_and_expiry` | Slot limits, byte limits, duplicate rejection, already-present status, TTL pruning | **PASSED** |
| `test_routing_feature_construction_and_decision_tree` | 11 causal features, tree execution (relay accepted for $TTL > 0.87$, rejected for old packets), baseline comparison | **PASSED** |
| `test_fake_transport_tx_rx` | Out-of-range rejection, in-range TX, RX queue pop, transmitter accounting | **PASSED** |
| `test_condition_report_queue` | 43-byte report structure, sequence counter, sentinel handling (`-999` dBm RSSI), FIFO dequeue | **PASSED** |
| `test_node_app_coordinator_cycle` | Full coordinator lifecycle: packet generation, peer discovery, decision forwarding, buffer removal, direct delivery, condition reporting | **PASSED** |

**Summary**: **6 / 6 passed (100.0%)**.

### 6.2 Full Pytest Integration Suite
- Total Test Items: **61** (58 existing tests + 3 firmware integration tests in `test_firmware_parity.py`).
- Full Suite Execution: **61 passed in 10.20s** with **zero regressions**.

### 6.3 Toolchain Availability Notice
- Target Cross-Compiler (`xtensa-lx106-elf-g++` / PlatformIO CLI): **Not installed on host PATH**.
- Host C++ Compiler: **MSYS2 UCRT64 GCC 15.2.0** (`x86_64-w64-mingw32-g++.exe`) available and validated.
- All code complies with C++17 and Arduino core standards; PlatformIO configuration provided in `platformio.ini`.

---

## 7. Remaining Hardware Decisions for Subsequent Stages

1. **Radio Transport Selection**:
   - Option A: **NRF24L01+** (SPI bus: MOSI/MISO/SCK, CE, CSN; 32-byte hardware payload limit requiring packet fragmentation).
   - Option B: **ESP-NOW** (Internal WiFi MAC layer; 250-byte payload per frame, eliminates SPI pins and external RF module).
2. **Display Module**:
   - Target: I2C 0.96" SSD1306 OLED (128x64 pixels, SDA on D2/GPIO4, SCL on D1/GPIO5).
3. **Storage Module**:
   - Internal SPI Flash using LittleFS (built into ESP8266 4MB flash, 1–2 MB partition) vs. External MicroSD over SPI.
4. **Pin Assignment Confirmation**:
   - Pin layout will be mapped once physical radio and display modules are confirmed.
"""
    (PROJECT_ROOT / "reports" / "stage6a_firmware_foundation.md").write_text(CodeContent, encoding="utf-8")
    print("Created stage6a_firmware_foundation.md")

