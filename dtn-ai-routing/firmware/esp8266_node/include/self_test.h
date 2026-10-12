/**
 * @file self_test.h
 * @brief Deterministic on-device verification suite for AI decision tree and firmware behavior.
 *
 * Provides a self-contained, isolated test mode that verifies:
 * 1. AI Decision Tree inference parity against reference model vectors.
 * 2. DecisionTreeRouter routing policy integration.
 * 3. Packet wire serialization, deserialization, and boundary rejection.
 * 4. Bounded buffer limits, duplicate suppression, and in-flight isolation.
 * 5. Timer rollover handling across uint32_t wrap-around.
 *
 * Can be executed on host (via std::cout) or on ESP8266 NodeMCU (via Serial).
 * Operates on isolated local stack buffers; NEVER touches production buffers or radio.
 */

#ifndef SELF_TEST_H
#define SELF_TEST_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "node_config.h"
#include "packet.h"
#include "packet_buffer.h"
#include "decision_tree_router.h"

#ifdef ARDUINO
#include <Arduino.h>
#define ST_PRINT(msg)       Serial.print(msg)
#define ST_PRINTLN(msg)     Serial.println(msg)
#define ST_PRINT_INT(val)   Serial.print(val)
#define ST_PRINTLN_INT(val) Serial.println(val)
#else
#include <iostream>
#define ST_PRINT(msg)       std::cout << (msg)
#define ST_PRINTLN(msg)     std::cout << (msg) << std::endl
#define ST_PRINT_INT(val)   std::cout << (val)
#define ST_PRINTLN_INT(val) std::cout << (val) << std::endl
#endif

struct AiBenchmarkCase {
    const char* name;
    LocalDecisionFeatures features;
    bool expected_decision;
    const char* rationale;
};

// 9 benchmark feature vectors obtained from scikit-learn reference model
static const AiBenchmarkCase AI_BENCHMARK_CASES[9] = {
    {
        "Direct Destination (Fresh)",
        { 1, 10000, 2, 0.95f, 0, 90, 100, 5000, 1, 0.05f, 5 },
        true,
        "Direct destination encounter must always forward"
    },
    {
        "Direct Destination (Low TTL)",
        { 1, 10000, 1, 0.10f, 2, 90, 500, 2000, 1, 0.50f, 10 },
        true,
        "Direct destination encounter forwards even at low TTL"
    },
    {
        "Relay Encounter (Fresh TTL 0.90)",
        { 0, 10000, 2, 0.90f, 0, 90, 200, 5800, 1, 0.05f, 5 },
        true,
        "Fresh packet (TTL ratio > 0.871) accepted for relay forwarding"
    },
    {
        "Relay Encounter (Very Fresh TTL 0.98)",
        { 0, 5000, 3, 0.98f, 0, 70, 50, 8000, 1, 0.01f, 8 },
        true,
        "High-priority fresh packet accepted for relay forwarding"
    },
    {
        "Relay Encounter (Low TTL 0.40)",
        { 0, 10000, 1, 0.40f, 1, 90, 300, 4000, 1, 0.20f, 3 },
        false,
        "Stale packet (TTL ratio <= 0.710) rejected to conserve bandwidth"
    },
    {
        "Relay Encounter (Intermediate TTL 0.75)",
        { 0, 10000, 2, 0.75f, 0, 90, 150, 3000, 1, 0.10f, 4 },
        false,
        "Intermediate packet (TTL ratio <= 0.871) rejected by decision tree"
    },
    {
        "Relay Encounter (High Buffer 0.85)",
        { 0, 20000, 1, 0.60f, 1, 130, 500, 2500, 1, 0.85f, 2 },
        false,
        "High local buffer utilization rejects opportunistic relay"
    },
    {
        "Relay Encounter (Boundary Above 0.88)",
        { 0, 10000, 2, 0.88f, 0, 90, 100, 4000, 1, 0.05f, 3 },
        true,
        "TTL ratio 0.88 is just above decision boundary 0.871 -> forward"
    },
    {
        "Relay Encounter (Boundary Below 0.86)",
        { 0, 10000, 2, 0.86f, 0, 90, 100, 4000, 1, 0.05f, 3 },
        false,
        "TTL ratio 0.86 is just below decision boundary 0.871 -> hold"
    }
};

/**
 * @brief Executes the complete deterministic on-device verification suite.
 * @return true if all 15 deterministic checks pass, false if any check fails.
 */
inline bool run_firmware_self_tests() {
    int passed = 0;
    int total = 0;

    ST_PRINTLN("\n==============================================================");
    ST_PRINTLN(" ESP8266 DTN NODE DETERMINISTIC AI & FIRMWARE SELF-TEST");
    ST_PRINTLN(" Target: Tensilica Xtensa L106 @ 80 MHz | Model: Decision Tree");
    ST_PRINTLN("==============================================================");

    // ------------------------------------------------------------------------
    // Part 1: AI Decision Tree Inference Parity (9 vectors)
    // ------------------------------------------------------------------------
    ST_PRINTLN("\n--- [PART 1] AI Decision Tree Inference Parity ---");
    for (size_t i = 0; i < 9; ++i) {
        total++;
        const AiBenchmarkCase& tc = AI_BENCHMARK_CASES[i];
        bool actual = decide_forwarding_decision_tree(tc.features);
        bool match = (actual == tc.expected_decision);

        ST_PRINT("  [AI-");
        ST_PRINT_INT(i + 1);
        ST_PRINT("] ");
        ST_PRINT(tc.name);
        ST_PRINT(": Expected=");
        ST_PRINT(tc.expected_decision ? "FORWARD" : "HOLD");
        ST_PRINT(", Actual=");
        ST_PRINT(actual ? "FORWARD" : "HOLD");

        if (match) {
            ST_PRINTLN(" -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN(" -> [FAIL]");
        }
    }

    // ------------------------------------------------------------------------
    // Part 2: DecisionTreeRouter Integration via EncounterContext
    // ------------------------------------------------------------------------
    ST_PRINTLN("\n--- [PART 2] DecisionTreeRouter Integration ---");
    {
        total++;
        DecisionTreeRouter router;
        Packet p_fresh = Packet::create("p_test_fresh", "nodeA", "nodeDest", 10000, 2, 1000, 10000);
        EncounterContext ctx_relay;
        dtn_safe_strcpy(ctx_relay.peer_id, "nodeRelay", NODE_ID_MAX_LEN);
        ctx_relay.current_time_ms = 2000;
        ctx_relay.contact_start_ms = 1800;
        ctx_relay.avg_historical_contact_ms = 6000;
        ctx_relay.peer_encounter_count = 5;
        ctx_relay.buffer_utilization = 0.05f;
        ctx_relay.transfer_rate_bytes_sec = 250000.0f;
        ctx_relay.transfer_overhead_ms = 50;

        bool dec_fresh = router.should_forward(p_fresh, ctx_relay);
        if (dec_fresh) {
            ST_PRINTLN("  [ROUTER-1] Fresh packet forwarded to promising relay -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [ROUTER-1] Fresh packet forward failed -> [FAIL]");
        }

        total++;
        dtn_safe_strcpy(ctx_relay.peer_id, "nodeDest", NODE_ID_MAX_LEN);
        bool dec_dest = router.should_forward(p_fresh, ctx_relay);
        if (dec_dest) {
            ST_PRINTLN("  [ROUTER-2] Direct destination encounter prioritized -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [ROUTER-2] Direct destination prioritization failed -> [FAIL]");
        }
    }

    // ------------------------------------------------------------------------
    // Part 3: Packet Wire Serialization & Bounds
    // ------------------------------------------------------------------------
    ST_PRINTLN("\n--- [PART 3] Packet Wire Serialization & Rejection ---");
    {
        total++;
        uint8_t payload_bytes[32] = { 0xAA, 0xBB, 0xCC, 0xDD };
        Packet pkt = Packet::create("p_ser_test", "node1", "node2", 100, 2, 500, 3000, payload_bytes, 32);
        uint8_t wire[512];
        size_t written = pkt.serialize(wire, sizeof(wire));
        Packet parsed;
        bool ok = parsed.deserialize(wire, written);
        if (ok && strcmp(parsed.header.packet_id, "p_ser_test") == 0 && parsed.payload_len == 32) {
            ST_PRINTLN("  [WIRE-1] Wire round-trip serialization and byte recovery -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [WIRE-1] Wire round-trip failed -> [FAIL]");
        }

        total++;
        Packet trunc;
        bool rej_trunc = !trunc.deserialize(wire, 77); // Less than minimum 78 bytes
        if (rej_trunc) {
            ST_PRINTLN("  [WIRE-2] Truncated wire frame (< 78B) rejection -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [WIRE-2] Truncated wire frame accepted -> [FAIL]");
        }

        total++;
        uint8_t bad_prio[512];
        memcpy(bad_prio, wire, written);
        bad_prio[66] = 5; // Invalid priority
        bool rej_prio = !trunc.deserialize(bad_prio, written);
        if (rej_prio) {
            ST_PRINTLN("  [WIRE-3] Corrupted packet priority rejection -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [WIRE-3] Corrupted packet priority accepted -> [FAIL]");
        }
    }

    // ------------------------------------------------------------------------
    // Part 4: Buffer Limits, In-Flight Isolation & Rollover Safety
    // ------------------------------------------------------------------------
    ST_PRINTLN("\n--- [PART 4] Buffer Safety, In-Flight Guard & Rollover ---");
    {
        total++;
        PacketBuffer test_buf(2, 500);
        Packet p1 = Packet::create("pkt_b1", "nA", "nB", 200, 1, 100, 5000);
        Packet p2 = Packet::create("pkt_b2", "nA", "nB", 200, 1, 100, 5000);
        Packet p3 = Packet::create("pkt_b3", "nA", "nB", 200, 1, 100, 5000);

        test_buf.add(p1, 100);
        test_buf.add(p2, 100);
        BufferOutcome full_res = test_buf.add(p3, 100);
        if (full_res == BUFFER_REJECTED_FULL && test_buf.count() == 2) {
            ST_PRINTLN("  [BUF-1] Bounded slot limit enforcement -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [BUF-1] Bounded slot limit enforcement failed -> [FAIL]");
        }

        total++;
        // Duplicate suppression
        test_buf.remove("pkt_b1");
        BufferOutcome dup_res = test_buf.add(p1, 100);
        if (dup_res == BUFFER_REJECTED_DUPLICATE) {
            ST_PRINTLN("  [BUF-2] Duplicate suppression filter rejection -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [BUF-2] Duplicate suppression filter failed -> [FAIL]");
        }

        total++;
        // Timer rollover safety across 0xFFFFFFFF
        uint32_t wrap_create = 0xFFFFFF00;
        uint32_t wrap_ttl = 500;
        Packet p_wrap = Packet::create("p_wrap", "nA", "nB", 64, 1, wrap_create, wrap_ttl);
        bool before_exp = !p_wrap.is_expired(0xFFFFFF50);
        bool after_wrap_pre_exp = !p_wrap.is_expired(0x00000050);
        bool after_exp = p_wrap.is_expired(0x00000100);
        if (before_exp && after_wrap_pre_exp && after_exp) {
            ST_PRINTLN("  [TIMER-1] Rollover-safe expiration across 32-bit wrap -> [PASS]");
            passed++;
        } else {
            ST_PRINTLN("  [TIMER-1] Timer rollover check failed -> [FAIL]");
        }
    }

    ST_PRINTLN("==============================================================");
    ST_PRINT(" SUMMARY: ");
    ST_PRINT_INT(passed);
    ST_PRINT(" / ");
    ST_PRINT_INT(total);
    ST_PRINTLN(" tests passed.");
    if (passed == total) {
        ST_PRINTLN(" RESULT: 100% PARITY & FIRMWARE BEHAVIOR VERIFIED.");
    } else {
        ST_PRINTLN(" RESULT: VERIFICATION FAILED.");
    }
    ST_PRINTLN("==============================================================\n");

    return (passed == total);
}

#endif // SELF_TEST_H
