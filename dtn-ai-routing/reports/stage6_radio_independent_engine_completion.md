# DTN AI Routing — Radio-Independent DTN Engine Completion Report

**Project Root**: `D:\ABHIMANYU\dtn-ai-routing`  
**Target Architecture**: ESP8266 NodeMCU (`nodemcuv2` / Tensilica Xtensa L106 @ 80 MHz)  
**Compiler Suite**: Host g++ 14 (UCRT64) / PlatformIO Cross-Compiler (GCC 10.3.0 Xtensa)  
**Test Suite Status**: 63 / 63 pytest tests passed (100%), 22 / 22 native C++ host tests passed (100%), PlatformIO target build SUCCESS (0 errors, 0 warnings).

---

## 1. Executive Summary

This milestone completes and validates the radio-independent Delay-Tolerant Networking (DTN) packet engine on the ESP8266 firmware architecture. Building directly upon the Stage 6B foundation and the Stage 5.2 validated C++ shallow decision-tree inference engine, the firmware now implements a complete, leak-free, non-blocking store-carry-and-forward packet lifecycle.

All physical wireless communication is strictly abstracted behind the `ITransport` interface, allowing complete offline mathematical and lifecycle verification prior to selecting physical radio hardware (NRF24L01+ vs. ESP-NOW).

---

## 2. Packet Lifecycle Implementation Details

The packet lifecycle spans generation, transit reception, duplicate checking, queue admission, forwarding decision, transmission, acknowledgement, retry backoff, and TTL-based pruning.

```
       [ Packet Ingestion / Local Generation ]
                         |
            +------------+------------+
            |                         |
    [ Direct Delivery ]       [ Transit Packet ]
    (pkt.dst == node_id)      (pkt.dst != node_id)
            |                         |
     Seen in History?          Seen in History?
      /           \             /           \
   [Yes]         [No]        [Yes]         [No]
     |             |           |             |
 (Suppress)    (Deliver)   (Suppress)   Buffer Full?
                   |                      /       \
            [STATE_DELIVERED]          [Yes]     [No]
                                         |         |
                                      (Drop)    (Enforce Quota)
                                                   |
                                            [STATE_PENDING]
                                                   |
                                         Peer In Range?
                                          /          \
                                       [No]         [Yes]
                                         |            |
                                      (Hold)   Calculate 11 Causal Features
                                                      |
                                               Decision Tree: FORWARD?
                                                /                \
                                             [No]               [Yes]
                                               |                  |
                                            (Hold)         [STATE_TRANSMITTING]
                                                                  |
                                                           ITransport::send()
                                                            /            \
                                                        [Success]       [Fail]
                                                           |               |
                                                  [STATE_FORWARDED]  retry < MAX_RETRIES?
                                                           |             /           \
                                                    (Purge from Buf)  [Yes]         [No]
                                                                        |             |
                                                                   (Backoff)   [STATE_FAILED]
                                                                        |             |
                                                                 [STATE_PENDING] (Retain in Buf)
```

### Core Invariants Maintained:
1. **Direct Destination Delivery**: Incoming packets addressed to the local node (`pkt.header.dest_id == local_node_id`) bypass the forwarding queue and are processed immediately. The deduplication filter (`seen_packets_`) prevents redundant local processing if the packet is re-received.
2. **Transit Buffering**: Inbound transit packets destined for another node are admitted to `PacketBuffer` only if both slot capacity (`count < max_buffer_packets`) and byte quota (`bytes_used + payload_size <= max_buffer_bytes`) are satisfied.
3. **No Oracle Future Knowledge**: Packets are routed strictly using local state, current contact features, and current buffer statistics.
4. **Zero Heap Allocation**: All packet allocations and buffers are pre-allocated with bounded fixed arrays. No `malloc`, `free`, `new`, or STL dynamic containers are used in the packet path.

---

## 3. Forwarding States and Bounded Retry Logic

### Forwarding States (`ForwardingState` Enum)
- `STATE_PENDING` (0): Packet is queued, waiting for a suitable peer contact or backoff timer expiration.
- `STATE_TRANSMITTING` (1): Packet is currently in-flight across the radio link. In-flight isolation prevents concurrent duplicate transmission.
- `STATE_FORWARDED` (2): Packet was successfully transferred and acknowledged by the relay peer; removed from local buffer.
- `STATE_DELIVERED` (3): Packet reached its final destination (either locally or confirmed delivery to destination node).
- `STATE_EXPIRED` (4): Packet TTL expired before delivery; pruned during buffer maintenance.
- `STATE_FAILED` (5): Packet exhausted maximum allowable transmission attempts (`MAX_PACKET_RETRIES = 3`) to the current peer. Retained safely in buffer without silent data loss.

### Bounded Exponential Retry Backoff
When `ITransport::send_packet()` fails or delivery acknowledgement is missing:
1. `retry_count` is incremented.
2. `next_retry_time_ms = current_time_ms + RETRY_BACKOFF_MS` (500 ms nominal backoff).
3. The packet transitions back to `STATE_PENDING` if `retry_count < MAX_PACKET_RETRIES`.
4. While `current_time_ms < next_retry_time_ms`, the non-blocking coordinator skips this packet, eliminating tight busy-wait polling loops.
5. If `retry_count >= MAX_PACKET_RETRIES`, the state transitions to `STATE_FAILED`.
6. When a new contact is established (`notify_peer_contact(peer, true)`), `reset_failed_packets()` clears the failure counter and restores eligibility for routing against the newly discovered peer.

### Timer Rollover Safety
All timer comparisons utilize standard unsigned 32-bit modulo arithmetic:
```cpp
if (pkt->next_retry_time_ms != 0 && static_cast<int32_t>(current_time_ms - pkt->next_retry_time_ms) < 0) {
    continue; // Backoff still active across 49.7-day rollover
}
```
This guarantees flawless behavior before, during, and after a `uint32_t` overflow.

---

## 4. AI Decision Integration & Local Feature Extraction

Each routing evaluation invokes `decision_tree_predict_esp8266(features)` with exactly the 11 strictly causal features verified in Stage 5.2:

| Index | Feature Name | Computation Formula / Source | Causal Property |
|---|---|---|---|
| 0 | `peer_is_destination` | `strcmp(peer_id, pkt.dest_id) == 0 ? 1 : 0` | Local encounter state |
| 1 | `remaining_ttl_ratio` | `remaining_ttl_ms / total_ttl_ms` | Packet header decay |
| 2 | `hop_count` | `pkt.header.hop_count` | Wire header accumulator |
| 3 | `peer_contact_duration` | Contact start to current elapsed seconds | Local peer contact timer |
| 4 | `peer_historical_contacts` | Local peer contact frequency counter | Local observation history |
| 5 | `peer_intercontact_time` | Seconds since last contact with this peer | Local observation history |
| 6 | `buffer_occupancy_ratio`| `buffer.count() / max_buffer_packets` | Local queue state |
| 7 | `buffer_bytes_ratio` | `buffer.bytes_used() / max_buffer_bytes` | Local queue state |
| 8 | `peer_buffer_occupancy` | Zero-knowledge default (0.50f) | Local assumption |
| 9 | `relative_distance` | Signal / RSSI / range estimate (default 1.0f)| Radio link metric |
| 10 | `packet_size_ratio` | `pkt.header.payload_size / max_buffer_bytes` | Packet header size |

### Inference Behavior:
- **Direct Encounter**: If `peer_is_destination == 1`, the tree immediately yields `FORWARD (1)`.
- **Relay Encounter**: If `peer_is_destination == 0`, the tree inspects `remaining_ttl_ratio`. If `remaining_ttl_ratio > 0.87105`, the relay is approved for store-carry-and-forward. If degraded below 0.87105 or buffer pressure is elevated, the packet is held (`HOLD (0)`).

---

## 5. Host Test Results Across All 12 Realistic Scenarios

All 12 realistic host scenarios were implemented and executed in `tests/test_firmware.cpp` and validated via `tests/test_firmware_parity.py`:

```
==============================================================
 ESP8266 DTN NODE FIRMWARE AUDIT - HOST TEST SUITE
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
[RUNNING] test_deterministic_ai_and_firmware_self_test... PASSED
  --> 17 / 17 self-test assertions passed.
[RUNNING] test_scenario_1_buffered_for_later_forwarding... PASSED
[RUNNING] test_scenario_2_no_peer_available_packet_remains_queued... PASSED
[RUNNING] test_scenario_3_send_fails_eligible_for_later_retry... PASSED
[RUNNING] test_scenario_4_duplicate_packet_suppression... PASSED
[RUNNING] test_scenario_5_packet_expires_while_buffered... PASSED
[RUNNING] test_scenario_6_destination_reachable_delivery_completes... PASSED
[RUNNING] test_scenario_7_relayed_through_intermediate_node... PASSED
[RUNNING] test_scenario_8_buffer_slot_limit_enforced... PASSED
[RUNNING] test_scenario_9_buffer_byte_limit_enforced... PASSED
[RUNNING] test_scenario_10_concurrent_transmission_protection... PASSED
[RUNNING] test_scenario_11_missing_acknowledgement_handling... PASSED
[RUNNING] test_scenario_12_timer_rollover_lifecycle... PASSED
==============================================================
 Results: 22 / 22 passed (100%).
==============================================================
```

### Scenario Breakdown:
1. **Scenario 1 (Buffered for later forwarding)**: Inbound transit packet stored in `STATE_PENDING` while waiting for peer encounters.
2. **Scenario 2 (No peer available)**: Packet held across multiple ticks with 0 drops and 0 erroneous forwardings.
3. **Scenario 3 (Send fails, eligible for retry)**: Transport send error triggers `retry_count = 1` and 500 ms backoff; successfully retried and forwarded at $t = 2600\text{ ms}$.
4. **Scenario 4 (Duplicate packet suppression)**: Verified for both direct destination delivery and intermediate transit buffering.
5. **Scenario 5 (Packet expires while buffered)**: TTL expiration safely prunes packet, increments dropped counter, and recovers byte buffer capacity without memory corruption.
6. **Scenario 6 (Destination reachable)**: Node encounters target destination; priority direct delivery successfully completes.
7. **Scenario 7 (Multi-hop relay)**: End-to-end pipeline $A \rightarrow B \rightarrow C$ passes: Node A creates packet for Node C, relays to Node B; Node B later encounters Node C and completes delivery.
8. **Scenario 8 (Buffer slot limit)**: Rejection on buffer slot capacity ($N = 3$), cleanly rejecting subsequent generation.
9. **Scenario 9 (Buffer byte limit)**: 300 B packet accepted, second 300 B packet rejected (exceeds 500 B capacity), 150 B packet accepted.
10. **Scenario 10 (Concurrent transmission protection)**: `STATE_TRANSMITTING` packets are skipped by the forwarding cycle, preventing duplicate concurrent transmission.
11. **Scenario 11 (Missing ACK handling)**: Repeated ACK failures increment `retry_count` up to 3, transition packet to `STATE_FAILED`, and prevent tight-loop CPU spinning.
12. **Scenario 12 (Timer rollover lifecycle)**: Unsigned 32-bit wrap around verified for packet expiration, remaining TTL calculations, and backoff timer expiration.

---

## 6. PlatformIO Build Verification & Memory Footprint

The firmware was compiled for target `nodemcuv2` (Tensilica Xtensa L106 @ 80 MHz, 4MB Flash, 80KB RAM) using PlatformIO.

### Target Build Summary:
- **Status**: SUCCESS (Exit code 0, 0 compiler warnings)
- **Toolchain**: `toolchain-xtensa @ 2.100300.220621 (10.3.0)`
- **Arduino Framework**: `framework-arduinoespressif8266 @ 3.30102.0`
- **Build Duration**: 1.62 seconds

### Memory Footprint:
| Memory Segment | Used | Total Available | Percentage | Margin Remaining |
|---|---|---|---|---|
| **RAM (Heap / BSS / Data)** | **47,004 bytes** | 81,920 bytes | **57.4%** | **34,916 bytes (42.6%)** |
| **Flash (ROM / Program Text)** | **277,099 bytes** | 1,044,464 bytes | **26.5%** | **767,365 bytes (73.5%)** |

### Memory Sizing Invariants:
- `sizeof(PacketWireHeader)`: exactly 48 bytes (wire packed, no compiler padding).
- `sizeof(Packet)`: exactly 340 bytes (32-bit aligned).
- `sizeof(NodeConditionReport)`: exactly 48 bytes.
- Buffer capacity: 16 packets $\times$ 340 bytes $\approx$ 5.4 KB static BSS memory.

---

## 7. Radio-Readiness Assessment

The completed firmware defines a clean boundary between the DTN routing engine and physical layer hardware via `ITransport`:

```cpp
class ITransport {
public:
    virtual ~ITransport() = default;
    virtual bool init() = 0;
    virtual void tick(uint32_t current_time_ms) = 0;
    virtual bool send_packet(const char* peer_id, const Packet& packet) = 0;
    virtual bool receive_packet(Packet& out_packet, char* out_sender_id) = 0;
    virtual bool is_peer_in_range(const char* peer_id) = 0;
    virtual size_t get_active_peers(char out_peer_ids[][NODE_ID_MAX_LEN], size_t max_peers) = 0;
};
```

### Expectations for Future Physical Drivers:
1. **Packet Serialization**: Use `Packet::serialize_wire()` and `Packet::deserialize_wire()` (48-byte header + payload $\le 256$ bytes).
2. **Payload Splitting (for NRF24L01+)**:
   - NRF24L01+ hardware packets have a maximum payload of 32 bytes.
   - An NRF24 driver will implement fragmentation / reassembly (e.g. 10 frames of 32 bytes) within `send_packet()` / `receive_packet()`, presenting whole DTN packets to `NodeApp`.
3. **ESP-NOW Alternative**:
   - ESP-NOW supports 250-byte frames natively. With a 48-byte header and small payloads, single-frame transmissions are possible; payloads $> 200$ bytes require 2-fragment delivery.
4. **Link-Layer Discovery / ACK**:
   - Peer discovery feeds `node_app.notify_peer_contact(peer_id, in_range)`.
   - `send_packet()` returning `false` triggers standard DTN backoff and retry handling without engine modification.

---

## 8. Exact Next Steps for Hardware Integration

1. **Radio Module Finalization**:
   - Decide between NRF24L01+ (SPI, external antenna) and ESP-NOW (native Wi-Fi frame injection, zero additional pins/hardware).
2. **Implement Physical Radio Driver**:
   - Create `Nrf24Transport` or `EspNowTransport` implementing `ITransport`.
3. **Display Driver**:
   - Implement `I2cOledDisplay` (SSD1306 128x64) replacing `NullDisplay` to render buffer occupancy and active neighbor IDs.
4. **Storage Driver**:
   - Implement `LittleFsStorage` replacing `RamStorage` for persistent non-volatile bundle storage across hardware reboots.
5. **Physical Multi-Node Testbed**:
   - Deploy firmware to 3 physical NodeMCU boards and observe multi-hop store-carry-and-forward relaying over physical radio links.
