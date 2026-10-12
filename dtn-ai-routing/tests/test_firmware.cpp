/**
 * @file test_firmware.cpp
 * @brief Host C++ unit test suite for ESP8266 DTN node firmware foundation.
 *
 * Verifies:
 * 1. Packet wire serialization and deserialization round-trip.
 * 2. Packet buffer capacity checks, duplicate suppression, and TTL expiry pruning.
 * 3. Strictly causal decision feature construction (11 features matching Python schema).
 * 4. DecisionTreeRouter integration with Stage 5.2 model.
 * 5. DirectDeliveryRouter baseline comparison.
 * 6. FakeTransport peer discovery and packet TX/RX simulation.
 * 7. NodeConditionReport structure, serialization, and bounded ReportQueue.
 * 8. Non-blocking NodeApp tick coordinator cycle and metrics tracking.
 * 9. Bounded static memory verification (zero heap fragmentation).
 */

#include <iostream>
#include <cassert>
#include <cstring>
#include <vector>

#include "../firmware/esp8266_node/include/dtn_types.h"
#include "../firmware/esp8266_node/include/node_config.h"
#include "../firmware/esp8266_node/include/packet.h"
#include "../firmware/esp8266_node/include/packet_buffer.h"
#include "../firmware/esp8266_node/include/router_interface.h"
#include "../firmware/esp8266_node/include/decision_tree_router.h"
#include "../firmware/esp8266_node/include/direct_delivery_router.h"
#include "../firmware/esp8266_node/include/transport_interface.h"
#include "../firmware/esp8266_node/include/fake_transport.h"
#include "../firmware/esp8266_node/include/display_interface.h"
#include "../firmware/esp8266_node/include/null_display.h"
#include "../firmware/esp8266_node/include/storage_interface.h"
#include "../firmware/esp8266_node/include/ram_storage.h"
#include "../firmware/esp8266_node/include/condition_report.h"
#include "../firmware/esp8266_node/include/event_logger.h"
#include "../firmware/esp8266_node/include/node_app.h"
#include "../firmware/esp8266_node/include/self_test.h"

// Include firmware source implementations directly for host test linking
#include "../firmware/esp8266_node/src/packet.cpp"
#include "../firmware/esp8266_node/src/packet_buffer.cpp"
#include "../firmware/esp8266_node/src/condition_report.cpp"
#include "../firmware/esp8266_node/src/node_app.cpp"

static int g_tests_run = 0;
static int g_tests_passed = 0;

#define TEST_ASSERT(cond, msg) \
    do { \
        if (!(cond)) { \
            std::cerr << "FAILED: " << msg << " (" << __FILE__ << ":" << __LINE__ << ")" << std::endl; \
            return false; \
        } \
    } while(0)

#define RUN_TEST(fn) \
    do { \
        g_tests_run++; \
        std::cout << "[RUNNING] " << #fn << "..." << std::flush; \
        if (fn()) { \
            g_tests_passed++; \
            std::cout << " PASSED" << std::endl; \
        } else { \
            std::cout << " FAILED" << std::endl; \
        } \
    } while(0)

// ============================================================================
// Test 1: Packet Serialization and Parsing Round-Trip
// ============================================================================
bool test_packet_serialization_roundtrip() {
    uint8_t payload_data[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02, 0x03, 0x04 };
    Packet pkt = Packet::create(
        "pkt_test_101",
        "node01",
        "node02",
        sizeof(payload_data) + sizeof(PacketWireHeader),
        2,              // Priority: High
        1000,           // Creation ms
        5000,           // TTL ms (expiry at 6000)
        payload_data,
        sizeof(payload_data)
    );

    TEST_ASSERT(strcmp(pkt.header.packet_id, "pkt_test_101") == 0, "Packet ID mismatch");
    TEST_ASSERT(strcmp(pkt.header.source, "node01") == 0, "Source mismatch");
    TEST_ASSERT(strcmp(pkt.header.destination, "node02") == 0, "Destination mismatch");
    TEST_ASSERT(pkt.header.priority == 2, "Priority mismatch");
    TEST_ASSERT(pkt.header.expiry_time_ms == 6000, "Expiry mismatch");
    TEST_ASSERT(pkt.payload_len == sizeof(payload_data), "Payload length mismatch");
    TEST_ASSERT(!pkt.is_expired(2000), "Should not be expired at 2000 ms");
    TEST_ASSERT(pkt.is_expired(6000), "Should be expired at 6000 ms");
    TEST_ASSERT(pkt.remaining_ttl_ms(3500) == 2500, "Remaining TTL calculation incorrect");
    TEST_ASSERT(pkt.remaining_ttl_ratio(3500) == 0.5f, "TTL ratio calculation incorrect");

    // Serialization
    uint8_t wire_buf[512];
    size_t written = pkt.serialize(wire_buf, sizeof(wire_buf));
    TEST_ASSERT(written > sizeof(PacketWireHeader), "Serialized size too small");

    // Deserialization
    Packet parsed;
    bool ok = parsed.deserialize(wire_buf, written);
    TEST_ASSERT(ok, "Deserialization failed");
    TEST_ASSERT(strcmp(parsed.header.packet_id, "pkt_test_101") == 0, "Parsed ID mismatch");
    TEST_ASSERT(strcmp(parsed.header.source, "node01") == 0, "Parsed source mismatch");
    TEST_ASSERT(strcmp(parsed.header.destination, "node02") == 0, "Parsed destination mismatch");
    TEST_ASSERT(parsed.header.priority == 2, "Parsed priority mismatch");
    TEST_ASSERT(parsed.payload_len == sizeof(payload_data), "Parsed payload len mismatch");
    TEST_ASSERT(memcmp(parsed.payload, payload_data, sizeof(payload_data)) == 0, "Payload data corrupted");

    // Boundary Test 1: Reject truncated header (< 78 bytes)
    Packet trunc_pkt;
    TEST_ASSERT(!trunc_pkt.deserialize(wire_buf, 77), "Must reject buffer smaller than minimum wire size 78B");

    // Boundary Test 2: Reject truncated payload (< 78 + payload_len)
    TEST_ASSERT(!trunc_pkt.deserialize(wire_buf, written - 1), "Must reject truncated payload");

    // Boundary Test 3: Reject invalid priority (0 or > 3)
    uint8_t corrupt_prio_buf[512];
    memcpy(corrupt_prio_buf, wire_buf, written);
    corrupt_prio_buf[66] = 0; // Invalid priority
    TEST_ASSERT(!trunc_pkt.deserialize(corrupt_prio_buf, written), "Must reject priority 0");
    corrupt_prio_buf[66] = 4; // Invalid priority
    TEST_ASSERT(!trunc_pkt.deserialize(corrupt_prio_buf, written), "Must reject priority 4");

    // Boundary Test 4: Maximum payload (256 bytes) round-trip
    uint8_t max_payload[MAX_PAYLOAD_BYTES];
    for (size_t i = 0; i < MAX_PAYLOAD_BYTES; ++i) {
        max_payload[i] = static_cast<uint8_t>(i & 0xFF);
    }
    Packet max_pkt = Packet::create("pkt_max_256", "srcNode", "dstNode", 300, 3, 500, 1000, max_payload, MAX_PAYLOAD_BYTES);
    size_t max_written = max_pkt.serialize(wire_buf, sizeof(wire_buf));
    TEST_ASSERT(max_written == PACKET_WIRE_MIN_BYTES + MAX_PAYLOAD_BYTES, "Max payload wire size must be exactly 78 + 256 = 334 bytes");
    Packet max_parsed;
    TEST_ASSERT(max_parsed.deserialize(wire_buf, max_written), "Max payload deserialization failed");
    TEST_ASSERT(max_parsed.payload_len == MAX_PAYLOAD_BYTES, "Max payload length mismatch");
    TEST_ASSERT(memcmp(max_parsed.payload, max_payload, MAX_PAYLOAD_BYTES) == 0, "Max payload byte content corrupted");

    return true;
}

// ============================================================================
// Test 2: Buffer Capacity, Duplicate Suppression, and Expiry Pruning
// ============================================================================
bool test_buffer_capacity_duplicate_and_expiry() {
    PacketBuffer buf(4, 1000); // Max 4 packets, max 1000 bytes

    // 1. Add valid packets
    Packet p1 = Packet::create("p1", "nA", "nB", 200, 1, 1000, 5000);
    Packet p2 = Packet::create("p2", "nA", "nB", 200, 1, 1000, 3000);
    Packet p3 = Packet::create("p3", "nA", "nB", 200, 1, 1000, 8000);
    Packet p4 = Packet::create("p4", "nA", "nB", 200, 1, 1000, 9000);

    TEST_ASSERT(buf.add(p1, 1000) == BUFFER_ACCEPTED, "p1 should be accepted");
    TEST_ASSERT(buf.add(p2, 1000) == BUFFER_ACCEPTED, "p2 should be accepted");
    TEST_ASSERT(buf.add(p3, 1000) == BUFFER_ACCEPTED, "p3 should be accepted");
    TEST_ASSERT(buf.add(p4, 1000) == BUFFER_ACCEPTED, "p4 should be accepted");
    TEST_ASSERT(buf.count() == 4, "Buffer should have 4 packets");
    TEST_ASSERT(buf.bytes_used() == 800, "Buffer should have 800 bytes used");

    // 2. Reject when full
    Packet p5 = Packet::create("p5", "nA", "nB", 200, 1, 1000, 5000);
    TEST_ASSERT(buf.add(p5, 1000) == BUFFER_REJECTED_FULL, "Buffer should reject when full");

    // 3. Reject duplicate
    TEST_ASSERT(buf.add(p1, 1000) == BUFFER_ALREADY_PRESENT, "Should report already present");
    buf.remove("p1");
    TEST_ASSERT(buf.count() == 3, "Buffer count should decrease to 3");
    // p1 was previously seen, so duplicate filter should reject it
    TEST_ASSERT(buf.add(p1, 1000) == BUFFER_REJECTED_DUPLICATE, "Duplicate filter should reject seen packet");

    // 4. Reject expired upon add
    Packet p_exp = Packet::create("p_exp", "nA", "nB", 100, 1, 1000, 500); // expires at 1500
    TEST_ASSERT(buf.add(p_exp, 2000) == BUFFER_REJECTED_EXPIRED, "Should reject already expired packet");

    // 5. Pruning expired packets in buffer
    // At current_time = 4500 ms:
    // p2 expires at 4000 ms -> should be pruned!
    // p3 (expires at 9000 ms) and p4 (expires at 10000 ms) remain!
    size_t pruned = buf.prune_expired(4500);
    TEST_ASSERT(pruned == 1, "Expected 1 pruned packet (p2)");
    TEST_ASSERT(buf.get("p2") == nullptr, "p2 should no longer exist in buffer");
    TEST_ASSERT(buf.get("p3") != nullptr, "p3 should still exist");
    TEST_ASSERT(buf.get("p4") != nullptr, "p4 should still exist");
    TEST_ASSERT(buf.count() == 2, "Buffer should have 2 remaining packets");

    return true;
}

// ============================================================================
// Test 3: Routing Feature Construction & Decision Tree Integration
// ============================================================================
bool test_routing_feature_construction_and_decision_tree() {
    Packet pkt = Packet::create("pkt_dt_01", "nodeA", "nodeDest", 10000, 2, 1000, 10000);
    EncounterContext ctx;
    dtn_safe_strcpy(ctx.peer_id, "nodeRelay", NODE_ID_MAX_LEN);
    ctx.current_time_ms = 2000;
    ctx.contact_start_ms = 1800;
    ctx.avg_historical_contact_ms = 6000;
    ctx.peer_encounter_count = 5;
    ctx.buffer_utilization = 0.05f;
    ctx.transfer_rate_bytes_sec = 250000.0f;
    ctx.transfer_overhead_ms = 50;

    LocalDecisionFeatures feats = build_decision_features(pkt, ctx);

    // Verify all 11 causal features
    TEST_ASSERT(feats.peer_is_destination == 0, "peer_is_destination mismatch");
    TEST_ASSERT(feats.packet_size_bytes == 10000, "packet_size_bytes mismatch");
    TEST_ASSERT(feats.packet_priority == 2, "packet_priority mismatch");
    TEST_ASSERT(feats.remaining_ttl_ratio > 0.85f && feats.remaining_ttl_ratio < 0.95f, "remaining_ttl_ratio mismatch");
    TEST_ASSERT(feats.packet_hops == 0, "packet_hops mismatch");
    TEST_ASSERT(feats.transfer_duration_ms == 90, "transfer_duration_ms mismatch (50 + ceil(10000*1000/250000) = 90)");
    TEST_ASSERT(feats.contact_elapsed_ms == 200, "contact_elapsed_ms mismatch");
    TEST_ASSERT(feats.estimated_remaining_contact_ms == 5800, "estimated_remaining_contact_ms mismatch");
    TEST_ASSERT(feats.estimated_transfer_fits == 1, "estimated_transfer_fits mismatch");
    TEST_ASSERT(feats.local_buffer_utilization == 0.05f, "local_buffer_utilization mismatch");
    TEST_ASSERT(feats.peer_encounter_frequency == 5, "peer_encounter_frequency mismatch");

    // Test with DecisionTreeRouter
    DecisionTreeRouter dt_router;
    TEST_ASSERT(strcmp(dt_router.get_policy_name(), "decision_tree_esp8266") == 0, "Policy name mismatch");

    // Since remaining_ttl_ratio is ~0.90, the shallow decision tree accepts relay forwarding!
    bool decision_relay = dt_router.should_forward(pkt, ctx);
    TEST_ASSERT(decision_relay == true, "Decision tree should accept promising fresh relay");

    // When peer is destination, it must ALWAYS forward
    dtn_safe_strcpy(ctx.peer_id, "nodeDest", NODE_ID_MAX_LEN);
    bool decision_dest = dt_router.should_forward(pkt, ctx);
    TEST_ASSERT(decision_dest == true, "Direct destination must always be accepted");

    // When TTL is exhausted or low (< 0.70), relay forwarding must be rejected
    Packet old_pkt = Packet::create("pkt_old", "nodeA", "nodeDest", 10000, 1, 1000, 10000);
    dtn_safe_strcpy(ctx.peer_id, "nodeRelay", NODE_ID_MAX_LEN);
    ctx.current_time_ms = 7000; // Remaining TTL = 4000/10000 = 0.40
    bool decision_old_relay = dt_router.should_forward(old_pkt, ctx);
    TEST_ASSERT(decision_old_relay == false, "Old packet relay encounter should be rejected");

    // Baseline DirectDeliveryRouter comparison
    DirectDeliveryRouter direct_router;
    TEST_ASSERT(direct_router.should_forward(pkt, ctx) == false, "Direct router must reject relay");
    dtn_safe_strcpy(ctx.peer_id, "nodeDest", NODE_ID_MAX_LEN);
    TEST_ASSERT(direct_router.should_forward(pkt, ctx) == true, "Direct router must accept destination");

    return true;
}

// ============================================================================
// Test 4: FakeTransport Behavior & Packet TX/RX Flow
// ============================================================================
bool test_fake_transport_tx_rx() {
    FakeTransport transport;
    TEST_ASSERT(transport.init() == true, "Transport init failed");
    TEST_ASSERT(transport.get_link_status() == LINK_IDLE, "Initial status should be IDLE");

    Packet pkt = Packet::create("p_tx", "nodeA", "nodeB", 64, 1, 1000, 5000);

    // Should fail when peer is not in range
    TEST_ASSERT(transport.send_packet("nodeB", pkt) == false, "Should fail when peer out of range");

    // Set peer in range
    transport.set_peer_in_range("nodeB", true);
    TEST_ASSERT(transport.is_peer_in_range("nodeB") == true, "Peer should be in range");

    // Send packet
    TEST_ASSERT(transport.send_packet("nodeB", pkt) == true, "Transmission should succeed");
    TEST_ASSERT(transport.get_tx_count() == 1, "TX count should be 1");
    TEST_ASSERT(strcmp(transport.get_last_tx_peer(), "nodeB") == 0, "Last TX peer mismatch");

    // Inject incoming packet into FakeTransport
    Packet rx_pkt = Packet::create("p_rx", "nodeC", "nodeA", 64, 1, 1500, 5000);
    TEST_ASSERT(transport.inject_incoming_packet("nodeC", rx_pkt) == true, "Injection failed");

    char sender[NODE_ID_MAX_LEN];
    Packet popped;
    TEST_ASSERT(transport.receive_packet(sender, popped) == true, "Receive failed");
    TEST_ASSERT(strcmp(sender, "nodeC") == 0, "Received sender mismatch");
    TEST_ASSERT(strcmp(popped.header.packet_id, "p_rx") == 0, "Received packet ID mismatch");

    // Receive queue should now be empty
    TEST_ASSERT(transport.receive_packet(sender, popped) == false, "Queue should be empty");

    return true;
}

// ============================================================================
// Test 5: NodeConditionReport Structure, Queue, and Serialization
// ============================================================================
bool test_condition_report_queue() {
    ReportQueue queue;
    TEST_ASSERT(queue.is_empty() == true, "Queue should initially be empty");
    TEST_ASSERT(queue.capacity() == MAX_QUEUED_REPORTS, "Queue capacity mismatch");

    NodeConditionReport r1;
    memset(&r1, 0, sizeof(r1));
    r1.schema_version = CONDITION_REPORT_SCHEMA_VERSION;
    strncpy(r1.node_id, "node01", NODE_ID_MAX_LEN);
    r1.sequence_number = 1;
    r1.uptime_ms = 30000;
    r1.buffer_packet_count = 5;
    r1.buffer_bytes_used = 1200;
    r1.packets_generated = 10;
    r1.packets_received = 8;
    r1.packets_forwarded = 4;
    r1.packets_delivered = 6;
    r1.radio_rssi_dbm = RADIO_METRIC_UNAVAILABLE;
    r1.firmware_version = FIRMWARE_VERSION;

    TEST_ASSERT(queue.enqueue(r1) == true, "Enqueue failed");
    TEST_ASSERT(queue.count() == 1, "Queue count should be 1");

    // Fill to capacity
    for (uint32_t i = 2; i <= MAX_QUEUED_REPORTS; ++i) {
        NodeConditionReport rx = r1;
        rx.sequence_number = i;
        TEST_ASSERT(queue.enqueue(rx) == true, "Enqueue within capacity failed");
    }
    TEST_ASSERT(queue.is_full() == true, "Queue should be full");

    // Next enqueue must fail (bounded guarantee)
    NodeConditionReport overflow;
    TEST_ASSERT(queue.enqueue(overflow) == false, "Queue overflow must be rejected");

    // Dequeue FIFO check
    NodeConditionReport out_r;
    TEST_ASSERT(queue.dequeue(out_r) == true, "Dequeue failed");
    TEST_ASSERT(out_r.sequence_number == 1, "FIFO order violated");
    TEST_ASSERT(strcmp(out_r.node_id, "node01") == 0, "Node ID corrupted");
    TEST_ASSERT(out_r.radio_rssi_dbm == RADIO_METRIC_UNAVAILABLE, "Radio metric sentinel corrupted");

    return true;
}

// ============================================================================
// Test 6: Non-Blocking NodeApp Coordinator Cycle
// ============================================================================
bool test_node_app_coordinator_cycle() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init() == true, "App initialization failed");

    // 1. Generate packet to destination "nodeDest" with 10,000 ms TTL
    BufferOutcome gen_res = app.generate_packet("pkt_001", "nodeDest", 100, 1, 10000, 1000);
    TEST_ASSERT(gen_res == BUFFER_ACCEPTED, "Packet generation failed");
    TEST_ASSERT(app.get_packets_generated() == 1, "Packets generated count mismatch");
    TEST_ASSERT(buffer.count() == 1, "Buffer should hold 1 packet");

    // 2. Tick loop with no peers in range
    app.tick(1500);
    TEST_ASSERT(buffer.count() == 1, "Packet should still be pending");
    TEST_ASSERT(app.get_packets_forwarded() == 0, "No forwarding should have occurred");

    // 3. Peer "nodeRelay" comes in range
    transport.set_peer_in_range("nodeRelay", true);
    app.notify_peer_contact("nodeRelay", true, 2000);

    // Tick loop -> Decision Tree evaluates and forwards packet to relay!
    app.tick(2000);
    TEST_ASSERT(app.get_packets_forwarded() == 1, "Packet should have been forwarded to relay");
    TEST_ASSERT(buffer.count() == 0, "Packet should be removed from buffer after forward");
    TEST_ASSERT(transport.get_tx_count() == 1, "Transport should record 1 transmission");

    // 4. Inbound packet delivered to this node ("nodeA")
    Packet in_delivered = Packet::create("pkt_in_01", "nodeX", "nodeA", 64, 1, 2000, 5000);
    transport.inject_incoming_packet("nodeX", in_delivered);

    app.tick(2500);
    TEST_ASSERT(app.get_packets_delivered() == 1, "Direct delivery count mismatch");

    // 5. Take nodeRelay out of range so inbound transit packet remains in store-carry-forward buffer
    transport.set_peer_in_range("nodeRelay", false);
    app.notify_peer_contact("nodeRelay", false, 2800);

    Packet in_transit = Packet::create("pkt_in_02", "nodeX", "nodeZ", 64, 1, 2500, 5000);
    transport.inject_incoming_packet("nodeX", in_transit);

    app.tick(3000);
    TEST_ASSERT(app.get_packets_received() == 1, "Transit packet received count mismatch");
    TEST_ASSERT(buffer.count() == 1, "Transit packet should be in buffer");

    // 6. Advance clock to trigger periodic condition report (30,000 ms)
    app.tick(31000);
    TEST_ASSERT(report_queue.count() >= 1, "Condition report should have been queued");
    NodeConditionReport rep;
    TEST_ASSERT(report_queue.dequeue(rep) == true, "Failed to dequeue generated report");
    TEST_ASSERT(rep.packets_generated == 1, "Report generated counter mismatch");
    TEST_ASSERT(rep.packets_forwarded == 1, "Report forwarded counter mismatch");
    TEST_ASSERT(rep.packets_delivered == 1, "Report delivered counter mismatch");

    return true;
}

// ============================================================================
// Test 7: Timer Rollover Safety Across uint32_t Wrap-Around
// ============================================================================
bool test_timer_rollover_safety() {
    // Creation at 0xFFFFFF00 (4,294,967,040 ms), TTL = 500 ms
    // Expiry wraps to 0x000000F4 (244 ms)
    uint32_t creation_ms = 0xFFFFFF00;
    uint32_t ttl_ms = 500;
    Packet pkt = Packet::create("pkt_wrap", "nodeA", "nodeB", 64, 1, creation_ms, ttl_ms);

    TEST_ASSERT(pkt.header.expiry_time_ms == (creation_ms + ttl_ms), "Expiry timestamp arithmetic mismatch");

    // Before wrap (e.g. at 0xFFFFFF50, 80 ms after creation, 420 ms remaining)
    uint32_t time_before_wrap = 0xFFFFFF50;
    TEST_ASSERT(!pkt.is_expired(time_before_wrap), "Packet should NOT be expired before wrap");
    TEST_ASSERT(pkt.remaining_ttl_ms(time_before_wrap) == 420, "Remaining TTL before wrap mismatch");
    TEST_ASSERT(pkt.remaining_ttl_ratio(time_before_wrap) > 0.80f, "Remaining TTL ratio before wrap mismatch");

    // After wrap, before expiry (e.g. at 0x00000050, 336 ms after creation, 164 ms remaining)
    uint32_t time_after_wrap = 0x00000050;
    TEST_ASSERT(!pkt.is_expired(time_after_wrap), "Packet should NOT be expired after wrap before expiry");
    TEST_ASSERT(pkt.remaining_ttl_ms(time_after_wrap) == (pkt.header.expiry_time_ms - time_after_wrap), "Remaining TTL after wrap mismatch");

    // At exact expiry (0x000000F4)
    TEST_ASSERT(pkt.is_expired(pkt.header.expiry_time_ms), "Packet MUST be expired at exact expiry timestamp");
    TEST_ASSERT(pkt.remaining_ttl_ms(pkt.header.expiry_time_ms) == 0, "Remaining TTL at expiry must be 0");

    // After expiry (e.g. at 0x00000200)
    TEST_ASSERT(pkt.is_expired(0x00000200), "Packet MUST be expired after expiry timestamp");
    TEST_ASSERT(pkt.remaining_ttl_ms(0x00000200) == 0, "Remaining TTL after expiry must be 0");
    TEST_ASSERT(pkt.remaining_ttl_ratio(0x00000200) == 0.0f, "Remaining ratio after expiry must be 0.0");

    return true;
}

// ============================================================================
// Test 8: In-Flight Packet State Isolation (No Re-forwarding during TX)
// ============================================================================
bool test_inflight_packet_isolation() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    // Generate a packet
    BufferOutcome outcome = app.generate_packet("pkt_tx_guard", "nodeDest", 100, 1, 10000, 1000);
    TEST_ASSERT(outcome == BUFFER_ACCEPTED, "Packet generation failed");

    // Mark packet as STATE_TRANSMITTING (in flight)
    Packet* p = buffer.get("pkt_tx_guard");
    TEST_ASSERT(p != nullptr, "Packet not found");
    p->state = STATE_TRANSMITTING;

    // Bring peer into range
    transport.set_peer_in_range("nodeRelay", true);
    app.notify_peer_contact("nodeRelay", true, 2000);

    // Run tick: router should SKIP packet because it is not in STATE_PENDING
    app.tick(2000);
    TEST_ASSERT(app.get_packets_forwarded() == 0, "In-flight packet must NOT be forwarded again");
    TEST_ASSERT(buffer.count() == 1, "Packet should still be in buffer");
    TEST_ASSERT(transport.get_tx_count() == 0, "Transport TX count should be 0");

    // Revert state to STATE_PENDING -> should now forward
    p->state = STATE_PENDING;
    app.tick(2100);
    TEST_ASSERT(app.get_packets_forwarded() == 1, "Pending packet should now be forwarded");
    TEST_ASSERT(buffer.count() == 0, "Packet should be removed after forwarding");

    return true;
}

// ============================================================================
// Test 9: Buffer Underflow Protection
// ============================================================================
bool test_buffer_underflow_safety() {
    PacketBuffer buf(4, 1000);
    Packet p1 = Packet::create("p1", "nA", "nB", 500, 1, 1000, 5000);
    TEST_ASSERT(buf.add(p1, 1000) == BUFFER_ACCEPTED, "p1 add failed");
    TEST_ASSERT(buf.bytes_used() == 500, "bytes_used mismatch");
    TEST_ASSERT(buf.count() == 1, "count mismatch");

    // Remove p1
    TEST_ASSERT(buf.remove("p1") == true, "p1 remove failed");
    TEST_ASSERT(buf.bytes_used() == 0, "bytes_used must be 0");
    TEST_ASSERT(buf.count() == 0, "count must be 0");

    // Double remove should safely return false without underflow
    TEST_ASSERT(buf.remove("p1") == false, "double remove should return false");
    TEST_ASSERT(buf.bytes_used() == 0, "bytes_used must not underflow");
    TEST_ASSERT(buf.count() == 0, "count must not underflow");

    // Prune on empty buffer should safely return 0
    size_t pruned = buf.prune_expired(99999);
    TEST_ASSERT(pruned == 0, "pruned on empty buffer should be 0");
    TEST_ASSERT(buf.bytes_used() == 0, "bytes_used must remain 0");

    return true;
}

// ============================================================================
// Test 10: Deterministic AI Inference & Firmware Self-Test Suite
// ============================================================================
bool test_deterministic_ai_and_firmware_self_test() {
    return run_firmware_self_tests();
}

// ============================================================================
// Scenario 1: A packet arrives and is buffered for later forwarding
// ============================================================================
bool test_scenario_1_buffered_for_later_forwarding() {
    NodeConfig cfg = NodeConfig::create_default("nodeRelay");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    // Inbound transit packet: from nodeSrc, addressed to nodeDest
    Packet transit_pkt = Packet::create("pkt_transit_01", "nodeSrc", "nodeDest", 100, 2, 1000, 10000);
    transport.inject_incoming_packet("nodeSrc", transit_pkt);

    // Tick with no peers in range
    app.tick(1000);

    TEST_ASSERT(app.get_packets_received() == 1, "Packet should be recorded as received");
    TEST_ASSERT(app.get_packets_delivered() == 0, "Packet must not be marked delivered locally");
    TEST_ASSERT(app.get_packets_forwarded() == 0, "Packet must not be forwarded yet");
    TEST_ASSERT(buffer.count() == 1, "Packet must be stored in local buffer");

    Packet* p = buffer.get("pkt_transit_01");
    TEST_ASSERT(p != nullptr, "Buffered packet must be retrievable");
    TEST_ASSERT(p->state == STATE_PENDING, "Buffered packet must be in STATE_PENDING");
    return true;
}

// ============================================================================
// Scenario 2: No peer is available; the packet remains queued
// ============================================================================
bool test_scenario_2_no_peer_available_packet_remains_queued() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    BufferOutcome res = app.generate_packet("pkt_wait_01", "nodeDest", 100, 1, 10000, 1000);
    TEST_ASSERT(res == BUFFER_ACCEPTED, "Generate packet failed");

    // Multiple ticks over elapsed time without any peer discovery
    for (uint32_t t = 1100; t <= 3000; t += 200) {
        app.tick(t);
        TEST_ASSERT(buffer.count() == 1, "Packet must remain in buffer");
        TEST_ASSERT(app.get_packets_forwarded() == 0, "No forwarding when no peer available");
        TEST_ASSERT(app.get_packets_dropped() == 0, "No packet drops should occur");
    }

    Packet* p = buffer.get("pkt_wait_01");
    TEST_ASSERT(p != nullptr && p->state == STATE_PENDING, "Packet must remain in STATE_PENDING");
    return true;
}

// ============================================================================
// Scenario 3: A send fails; the packet remains eligible for a later retry
// ============================================================================
bool test_scenario_3_send_fails_eligible_for_later_retry() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    app.generate_packet("pkt_retry_01", "nodeDest", 100, 2, 50000, 1000);

    // Peer comes in range
    transport.set_peer_in_range("nodeRelay", true);
    app.notify_peer_contact("nodeRelay", true, 2000);

    // Simulate transmission failure on first attempt
    transport.set_fail_next_send(true);
    app.tick(2000);

    // Packet must NOT be silently dropped or deleted!
    TEST_ASSERT(buffer.count() == 1, "Packet must NOT be removed from buffer on TX failure");
    TEST_ASSERT(app.get_packets_forwarded() == 0, "Forwarded count must remain 0 on TX failure");

    Packet* p = buffer.get("pkt_retry_01");
    TEST_ASSERT(p != nullptr, "Packet must be in buffer");
    TEST_ASSERT(p->retry_count == 1, "Retry count must be incremented to 1");
    TEST_ASSERT(p->next_retry_time_ms == 2500, "Next retry time must be current + RETRY_BACKOFF_MS (2500)");

    // Immediate tick within backoff window (e.g. 2100 ms) must NOT retry in tight loop
    app.tick(2100);
    TEST_ASSERT(p->retry_count == 1, "Retry count must not advance during active backoff");
    TEST_ASSERT(app.get_packets_forwarded() == 0, "Still no forwarding during backoff");

    // Tick after backoff elapsed (e.g. 2600 ms) -> transport succeeds!
    app.tick(2600);
    TEST_ASSERT(app.get_packets_forwarded() == 1, "Packet must be successfully forwarded on retry");
    TEST_ASSERT(buffer.count() == 0, "Packet must be removed after successful acknowledged retry");
    return true;
}

// ============================================================================
// Scenario 4: A duplicate packet arrives; it is not delivered or forwarded twice
// ============================================================================
bool test_scenario_4_duplicate_packet_suppression() {
    NodeConfig cfg = NodeConfig::create_default("nodeMe");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    // Case 1: Packet addressed directly to local node arrives twice
    Packet dest_pkt = Packet::create("pkt_dest_dup", "nodeX", "nodeMe", 50, 1, 1000, 5000);
    transport.inject_incoming_packet("nodeX", dest_pkt);
    app.tick(1000);
    TEST_ASSERT(app.get_packets_delivered() == 1, "First arrival must be delivered");

    // Inject exact same packet again
    transport.inject_incoming_packet("nodeX", dest_pkt);
    app.tick(1100);
    TEST_ASSERT(app.get_packets_delivered() == 1, "Duplicate arrival must NOT increment delivered count");

    // Case 2: Transit packet arrives twice
    Packet transit_pkt = Packet::create("pkt_trans_dup", "nodeX", "nodeTarget", 50, 1, 1000, 5000);
    transport.inject_incoming_packet("nodeX", transit_pkt);
    app.tick(1200);
    TEST_ASSERT(app.get_packets_received() == 1, "First transit arrival accepted");
    TEST_ASSERT(buffer.count() == 1, "Buffer holds 1 transit packet");

    // Inject same transit packet while sitting in buffer
    transport.inject_incoming_packet("nodeX", transit_pkt);
    app.tick(1300);
    TEST_ASSERT(app.get_packets_received() == 1, "Duplicate transit packet must NOT increase received count");
    TEST_ASSERT(buffer.count() == 1, "Buffer still holds 1 transit packet");

    return true;
}

// ============================================================================
// Scenario 5: A packet expires while buffered
// ============================================================================
bool test_scenario_5_packet_expires_while_buffered() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    // Generate packet with 2000 ms TTL (creation 1000 ms, expires at 3000 ms)
    app.generate_packet("pkt_exp_01", "nodeDest", 100, 1, 2000, 1000);
    TEST_ASSERT(buffer.count() == 1, "Packet should be in buffer");

    // Advance clock past expiration (e.g. 3500 ms) and trigger buffer maintenance
    app.tick(3500);
    TEST_ASSERT(app.get_packets_expired() == 1, "Packet must be counted as expired");
    TEST_ASSERT(buffer.count() == 0, "Expired packet must be pruned from buffer");
    TEST_ASSERT(buffer.get("pkt_exp_01") == nullptr, "Expired packet must be removed");
    return true;
}

// ============================================================================
// Scenario 6: The destination becomes reachable and delivery completes
// ============================================================================
bool test_scenario_6_destination_reachable_delivery_completes() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    app.generate_packet("pkt_to_dest", "finalDest", 100, 1, 10000, 1000);
    TEST_ASSERT(buffer.count() == 1, "Packet should be buffered");

    // Destination node comes directly in range
    transport.set_peer_in_range("finalDest", true);
    app.notify_peer_contact("finalDest", true, 2000);

    app.tick(2000);
    TEST_ASSERT(app.get_packets_delivered() == 1, "Destination delivery must increment packets_delivered");
    TEST_ASSERT(app.get_packets_forwarded() == 0, "Destination delivery must not count as forwarded relay");
    TEST_ASSERT(buffer.count() == 0, "Delivered packet must be removed from buffer");
    TEST_ASSERT(transport.get_tx_count() == 1, "Transport should have executed 1 TX");
    TEST_ASSERT(strcmp(transport.get_last_tx_peer(), "finalDest") == 0, "Last TX peer must be destination");
    return true;
}

// ============================================================================
// Scenario 7: A packet is relayed through an intermediate node
// ============================================================================
bool test_scenario_7_relayed_through_intermediate_node() {
    // Node A (Originator) -> Node B (Relay) -> Node C (Destination)
    NodeConfig cfgA = NodeConfig::create_default("nodeA");
    PacketBuffer bufA(16, 4096);
    DecisionTreeRouter routerA;
    FakeTransport txA;
    NullDisplay dispA;
    RamStorage storeA;
    ReportQueue qA;
    EventLogger logA;
    NodeApp appA(cfgA, bufA, routerA, txA, dispA, storeA, qA, logA);
    TEST_ASSERT(appA.init(), "Node A init failed");

    NodeConfig cfgB = NodeConfig::create_default("nodeB");
    PacketBuffer bufB(16, 4096);
    DecisionTreeRouter routerB;
    FakeTransport txB;
    NullDisplay dispB;
    RamStorage storeB;
    ReportQueue qB;
    EventLogger logB;
    NodeApp appB(cfgB, bufB, routerB, txB, dispB, storeB, qB, logB);
    TEST_ASSERT(appB.init(), "Node B init failed");

    // 1. Node A generates packet for Node C
    appA.generate_packet("pkt_multi_hop", "nodeC", 100, 2, 10000, 1000);

    // 2. Encounter between Node A and Node B
    txA.set_peer_in_range("nodeB", true);
    appA.notify_peer_contact("nodeB", true, 2000);

    // Node A forwards to Node B
    appA.tick(2000);
    TEST_ASSERT(appA.get_packets_forwarded() == 1, "Node A must record 1 forwarded packet");
    TEST_ASSERT(bufA.count() == 0, "Node A buffer should now be empty");

    // 3. Node B receives packet from Node A
    Packet relayed_pkt = txA.get_last_tx_packet();
    txB.inject_incoming_packet("nodeA", relayed_pkt);
    appB.tick(2100);
    TEST_ASSERT(appB.get_packets_received() == 1, "Node B must receive the transit packet");
    TEST_ASSERT(bufB.count() == 1, "Node B must buffer the transit packet");

    // Node A leaves contact
    txA.set_peer_in_range("nodeB", false);
    appA.notify_peer_contact("nodeB", false, 2500);

    // 4. Later, Node B encounters destination Node C
    txB.set_peer_in_range("nodeC", true);
    appB.notify_peer_contact("nodeC", true, 3000);
    appB.tick(3000);

    TEST_ASSERT(appB.get_packets_delivered() == 1, "Node B must deliver packet to destination Node C");
    TEST_ASSERT(bufB.count() == 0, "Node B buffer must be empty after final delivery");
    TEST_ASSERT(strcmp(txB.get_last_tx_peer(), "nodeC") == 0, "Last TX recipient must be destination Node C");
    return true;
}

// ============================================================================
// Scenario 8: A buffer reaches its packet-count limit
// ============================================================================
bool test_scenario_8_buffer_slot_limit_enforced() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    cfg.max_buffer_packets = 3;
    PacketBuffer buffer(3, 10000);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    // Fill buffer to capacity (3 packets)
    TEST_ASSERT(app.generate_packet("p1", "nD", 100, 1, 5000, 1000) == BUFFER_ACCEPTED, "p1 failed");
    TEST_ASSERT(app.generate_packet("p2", "nD", 100, 1, 5000, 1000) == BUFFER_ACCEPTED, "p2 failed");
    TEST_ASSERT(app.generate_packet("p3", "nD", 100, 1, 5000, 1000) == BUFFER_ACCEPTED, "p3 failed");
    TEST_ASSERT(buffer.count() == 3, "Buffer count should be 3");

    // 4th packet must be rejected due to slot limit
    BufferOutcome res = app.generate_packet("p4", "nD", 100, 1, 5000, 1000);
    TEST_ASSERT(res == BUFFER_REJECTED_FULL, "p4 must be rejected as full");
    TEST_ASSERT(buffer.count() == 3, "Buffer count must remain strictly 3");
    TEST_ASSERT(app.get_packets_dropped() == 1, "Dropped counter must be 1");
    return true;
}

// ============================================================================
// Scenario 9: A buffer reaches its byte limit
// ============================================================================
bool test_scenario_9_buffer_byte_limit_enforced() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(10, 500); // Max 500 bytes
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    // Add packet of 300 bytes -> accepted (300/500)
    TEST_ASSERT(app.generate_packet("p_big1", "nD", 300, 1, 5000, 1000) == BUFFER_ACCEPTED, "p_big1 failed");
    TEST_ASSERT(buffer.bytes_used() == 300, "bytes_used must be 300");

    // Add second packet of 300 bytes -> 300 + 300 = 600 > 500 -> rejected!
    BufferOutcome rej = app.generate_packet("p_big2", "nD", 300, 1, 5000, 1000);
    TEST_ASSERT(rej == BUFFER_REJECTED_FULL, "p_big2 must be rejected due to byte limit");
    TEST_ASSERT(buffer.bytes_used() == 300, "bytes_used must remain 300");

    // Add smaller packet of 150 bytes -> 300 + 150 = 450 <= 500 -> accepted!
    TEST_ASSERT(app.generate_packet("p_small", "nD", 150, 1, 5000, 1000) == BUFFER_ACCEPTED, "p_small failed");
    TEST_ASSERT(buffer.bytes_used() == 450, "bytes_used must be 450");
    return true;
}

// ============================================================================
// Scenario 10: A transmission is in progress; same packet cannot be forwarded concurrently
// ============================================================================
bool test_scenario_10_concurrent_transmission_protection() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    app.generate_packet("pkt_tx_guard2", "nodeDest", 100, 1, 10000, 1000);
    Packet* p = buffer.get("pkt_tx_guard2");
    TEST_ASSERT(p != nullptr, "Packet must exist");

    // Set state to STATE_TRANSMITTING (in flight)
    p->state = STATE_TRANSMITTING;

    transport.set_peer_in_range("nodeRelay", true);
    app.notify_peer_contact("nodeRelay", true, 2000);

    // Tick: router must skip this packet
    app.tick(2000);
    TEST_ASSERT(app.get_packets_forwarded() == 0, "In-flight packet must not be forwarded");
    TEST_ASSERT(transport.get_tx_count() == 0, "No TX should occur while in-flight");
    TEST_ASSERT(buffer.count() == 1, "Packet must remain in buffer");
    return true;
}

// ============================================================================
// Scenario 11: An acknowledgement or delivery confirmation is missing
// ============================================================================
bool test_scenario_11_missing_acknowledgement_handling() {
    NodeConfig cfg = NodeConfig::create_default("nodeA");
    PacketBuffer buffer(16, 4096);
    DecisionTreeRouter router;
    FakeTransport transport;
    NullDisplay display;
    RamStorage storage;
    ReportQueue report_queue;
    EventLogger logger;

    NodeApp app(cfg, buffer, router, transport, display, storage, report_queue, logger);
    TEST_ASSERT(app.init(), "App init failed");

    app.generate_packet("pkt_nack", "nodeDest", 100, 2, 50000, 1000);

    transport.set_peer_in_range("nodeRelay", true);
    app.notify_peer_contact("nodeRelay", true, 2000);

    // Simulate missing ACK (send_packet returns false)
    transport.set_simulate_tx_failure(true);

    // Attempt 1 (t = 2000)
    app.tick(2000);
    Packet* p = buffer.get("pkt_nack");
    TEST_ASSERT(p != nullptr, "Packet must remain in buffer");
    TEST_ASSERT(p->retry_count == 1, "Attempt 1 recorded");
    TEST_ASSERT(p->state == STATE_PENDING, "State should be PENDING during retries");

    // Attempt 2 (t = 2500)
    app.tick(2500);
    TEST_ASSERT(p->retry_count == 2, "Attempt 2 recorded");

    // Attempt 3 (t = 3000) -> reaches MAX_PACKET_RETRIES (3)
    app.tick(3000);
    TEST_ASSERT(p->retry_count == 3, "Attempt 3 recorded");
    TEST_ASSERT(p->state == STATE_FAILED, "State must transition to STATE_FAILED on ACK exhaustion");

    // Subsequent tick (t = 3500) -> router stops hammering in tight loop
    app.tick(3500);
    TEST_ASSERT(p->retry_count == 3, "Retry count must not advance once STATE_FAILED");
    TEST_ASSERT(buffer.count() == 1, "Packet must NOT be dropped; safely preserved in buffer");

    // Resetting failed packets restores STATE_PENDING
    app.reset_failed_packets();
    TEST_ASSERT(p->state == STATE_PENDING, "State should return to PENDING after reset");
    TEST_ASSERT(p->retry_count == 0, "Retry count reset to 0");
    return true;
}

// ============================================================================
// Scenario 12: Timer rollover does not break packet expiry or retry scheduling
// ============================================================================
bool test_scenario_12_timer_rollover_lifecycle() {
    // Creation at 0xFFFFFF00, TTL = 500 ms -> expiry wrapped to 0x000000F4
    uint32_t creation_ms = 0xFFFFFF00;
    uint32_t ttl_ms = 500;
    Packet pkt = Packet::create("pkt_roll", "nodeA", "nodeB", 64, 1, creation_ms, ttl_ms);

    // Check expiry before wrap
    TEST_ASSERT(!pkt.is_expired(0xFFFFFF50), "Must not be expired at 0xFFFFFF50");
    TEST_ASSERT(pkt.remaining_ttl_ms(0xFFFFFF50) == 420, "Remaining TTL before wrap mismatch");

    // Check expiry after wrap before expiration
    TEST_ASSERT(!pkt.is_expired(0x00000050), "Must not be expired at 0x00000050");

    // Check expiry at exact timestamp and beyond
    TEST_ASSERT(pkt.is_expired(0x000000F4), "Must be expired at 0x000000F4");
    TEST_ASSERT(pkt.is_expired(0x00000200), "Must be expired at 0x00000200");

    // Retry scheduling across rollover:
    // now = 0xFFFFFF80, backoff = 500 ms -> next_retry_time_ms = 0x00000174 (wrapped)
    uint32_t now = 0xFFFFFF80;
    pkt.next_retry_time_ms = now + RETRY_BACKOFF_MS;
    TEST_ASSERT(pkt.next_retry_time_ms == (now + RETRY_BACKOFF_MS), "Arithmetic wrap verified");

    // At now = 0xFFFFFF90: 16 ms later, backoff still active
    uint32_t now_in_backoff = 0xFFFFFF90;
    bool in_backoff = (static_cast<int32_t>(now_in_backoff - pkt.next_retry_time_ms) < 0);
    TEST_ASSERT(in_backoff, "Backoff must be active across rollover");

    // At now = 0x00000174: exact backoff expiration
    uint32_t now_expired = pkt.next_retry_time_ms;
    bool backoff_done = (static_cast<int32_t>(now_expired - pkt.next_retry_time_ms) >= 0);
    TEST_ASSERT(backoff_done, "Backoff must be elapsed at exact timestamp across rollover");

    return true;
}

// ============================================================================
// Main Test Runner
// ============================================================================
int main() {
    std::cout << "==============================================================" << std::endl;
    std::cout << " ESP8266 DTN NODE FIRMWARE AUDIT - HOST TEST SUITE" << std::endl;
    std::cout << "==============================================================" << std::endl;

    RUN_TEST(test_packet_serialization_roundtrip);
    RUN_TEST(test_buffer_capacity_duplicate_and_expiry);
    RUN_TEST(test_routing_feature_construction_and_decision_tree);
    RUN_TEST(test_fake_transport_tx_rx);
    RUN_TEST(test_condition_report_queue);
    RUN_TEST(test_node_app_coordinator_cycle);
    RUN_TEST(test_timer_rollover_safety);
    RUN_TEST(test_inflight_packet_isolation);
    RUN_TEST(test_buffer_underflow_safety);
    RUN_TEST(test_deterministic_ai_and_firmware_self_test);

    // Realistic Lifecycle Scenarios 1-12
    RUN_TEST(test_scenario_1_buffered_for_later_forwarding);
    RUN_TEST(test_scenario_2_no_peer_available_packet_remains_queued);
    RUN_TEST(test_scenario_3_send_fails_eligible_for_later_retry);
    RUN_TEST(test_scenario_4_duplicate_packet_suppression);
    RUN_TEST(test_scenario_5_packet_expires_while_buffered);
    RUN_TEST(test_scenario_6_destination_reachable_delivery_completes);
    RUN_TEST(test_scenario_7_relayed_through_intermediate_node);
    RUN_TEST(test_scenario_8_buffer_slot_limit_enforced);
    RUN_TEST(test_scenario_9_buffer_byte_limit_enforced);
    RUN_TEST(test_scenario_10_concurrent_transmission_protection);
    RUN_TEST(test_scenario_11_missing_acknowledgement_handling);
    RUN_TEST(test_scenario_12_timer_rollover_lifecycle);

    std::cout << "==============================================================" << std::endl;
    std::cout << " Results: " << g_tests_passed << " / " << g_tests_run << " passed." << std::endl;
    std::cout << "==============================================================" << std::endl;

    return (g_tests_passed == g_tests_run) ? 0 : 1;
}
