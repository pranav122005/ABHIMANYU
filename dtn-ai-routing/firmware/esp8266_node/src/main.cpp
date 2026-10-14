/**
 * @file main.cpp
 * @brief Autonomous ESP8266 NodeMCU DTN Node firmware entry point.
 *
 * Implements bidirectional ESP-NOW communication, Stage 5.2 embedded AI decision-tree
 * Store-Carry-Forward routing, SSD1306 OLED visualization for Node A, headless operation
 * for Node B, and an interactive Serial CLI for hardware acceptance testing.
 */

#ifdef ARDUINO
#include <Arduino.h>
#include "node_config.h"
#include "packet_buffer.h"
#include "decision_tree_router.h"
#include "esp_now_transport.h"
#include "ram_storage.h"
#include "condition_report.h"
#include "event_logger.h"
#include "node_app.h"
#include "self_test.h"

// Compile-time configuration for Node ID and OLED availability
#ifndef DTN_NODE_ID
#if defined(DTN_NODE_B)
#define DTN_NODE_ID "node_b"
#else
#define DTN_NODE_ID "node_a"
#endif
#endif

#ifndef DTN_PEER_NODE_ID
#if defined(DTN_NODE_B)
#define DTN_PEER_NODE_ID "node_a"
#else
#define DTN_PEER_NODE_ID "node_b"
#endif
#endif

#ifndef DTN_HAS_OLED
#if defined(DTN_NODE_B)
#define DTN_HAS_OLED 0
#else
#define DTN_HAS_OLED 1
#endif
#endif

#if DTN_HAS_OLED
#include "oled_display.h"
static OledDisplay g_display;
#else
#include "null_display.h"
static NullDisplay g_display;
#endif

static NodeConfig g_config;
static PacketBuffer g_buffer(MAX_BUFFER_PACKETS, MAX_BUFFER_BYTES);
static DecisionTreeRouter g_router;
static EspNowTransport g_transport;
static RamStorage g_storage;
static ReportQueue g_report_queue;
static EventLogger g_logger;

static NodeApp g_app(
    g_config,
    g_buffer,
    g_router,
    g_transport,
    g_display,
    g_storage,
    g_report_queue,
    g_logger
);

static uint32_t g_msg_seq = 0;
static const char* g_local_node_id = DTN_NODE_ID;
static const char* g_peer_node_id = DTN_PEER_NODE_ID;

static void print_help() {
    Serial.println("\n========================================================");
    Serial.printf(" ABHIMANYU DTN NODE [%s] — COMMAND MENU\n", g_local_node_id);
    Serial.println("========================================================");
    Serial.println(" [M] Send Test Message to peer node");
    Serial.println(" [R] Send Relay Message (tests AI Decision Tree)");
    Serial.println(" [P] Send Discovery Ping / Beacon");
    Serial.println(" [S] Print Detailed System & Buffer Status");
    Serial.println(" [B] Print Local and Peer MAC Addresses");
    Serial.println(" [T] Run Deterministic AI & Parity Self-Tests");
    Serial.println(" [H] Show this Help Menu");
    Serial.println("========================================================\n");
}

static void send_test_message() {
    g_msg_seq++;
    char pkt_id[PACKET_ID_MAX_LEN];
    snprintf(pkt_id, sizeof(pkt_id), "msg_%.5s_%04u", g_local_node_id, static_cast<unsigned>(g_msg_seq));

    char payload[64];
    snprintf(payload, sizeof(payload), "Hello from %s [#%u]", g_local_node_id, static_cast<unsigned>(g_msg_seq));

    uint32_t now = millis();
    BufferOutcome outcome = g_app.generate_packet(
        pkt_id,
        g_peer_node_id,
        static_cast<uint16_t>(strlen(payload)),
        1,       // Priority: Normal
        3600000, // TTL: 1 hour (3600s)
        now,
        reinterpret_cast<const uint8_t*>(payload),
        static_cast<uint16_t>(strlen(payload))
    );

    if (outcome == BUFFER_ACCEPTED) {
        Serial.printf("[USER-CMD] Generated bundle '%s' to '%s': \"%s\"\n", pkt_id, g_peer_node_id, payload);
    } else {
        Serial.printf("[USER-CMD] Failed to generate bundle '%s' (outcome code: %d)\n", pkt_id, outcome);
    }
}

static void send_ai_relay_test_message() {
    g_msg_seq++;
    char pkt_id[PACKET_ID_MAX_LEN];
    snprintf(pkt_id, sizeof(pkt_id), "relay_%.5s_%04u", g_local_node_id, static_cast<unsigned>(g_msg_seq));

    // Target a destination beyond the immediate peer to test relay routing decisions
    const char* distant_dest = "node_hq";
    char payload[64];
    snprintf(payload, sizeof(payload), "AI Relay Test via %s [#%u]", g_peer_node_id, static_cast<unsigned>(g_msg_seq));

    uint32_t now = millis();
    BufferOutcome outcome = g_app.generate_packet(
        pkt_id,
        distant_dest,
        static_cast<uint16_t>(strlen(payload)),
        2,       // Priority: High
        1800000, // TTL: 30 minutes
        now,
        reinterpret_cast<const uint8_t*>(payload),
        static_cast<uint16_t>(strlen(payload))
    );

    Serial.printf("\n--- AI RELAY ROUTING TEST --- \n");
    Serial.printf("[USER-CMD] Created bundle '%s' for distant destination '%s'\n", pkt_id, distant_dest);
    Serial.printf("[USER-CMD] Immediate peer '%s' is NOT final destination (peer_is_destination = 0)\n", g_peer_node_id);
    Serial.printf("[USER-CMD] Evaluating Stage 5.2 Decision Tree on contact encounter...\n");
    if (outcome != BUFFER_ACCEPTED) {
        Serial.printf("[USER-CMD] Buffer rejected packet (code: %d)\n", outcome);
    }
}

static void print_status() {
    char local_mac[20], peer_mac[20];
    g_transport.get_local_mac_str(local_mac, sizeof(local_mac));
    g_transport.get_peer_mac_str(peer_mac, sizeof(peer_mac));

    Serial.println("\n--------------------------------------------------------");
    Serial.printf(" NODE IDENTITY:        %s\n", g_local_node_id);
    Serial.printf(" DESIGNATED PEER:      %s\n", g_peer_node_id);
    Serial.printf(" LOCAL MAC:            %s\n", local_mac);
    Serial.printf(" PEER MAC:             %s (%s)\n", peer_mac, g_transport.has_peer_mac() ? "Configured" : "Broadcast / Auto-discovery");
    Serial.printf(" OLED DISPLAY:         %s\n", g_display.get_display_name());
    Serial.printf(" RADIO DRIVER:         %s\n", g_transport.get_driver_name());
    Serial.printf(" PEER IN RANGE:        %s\n", g_transport.is_peer_in_range(g_peer_node_id) ? "YES (Contact Active)" : "NO (Contact Lost / Timeout)");
    Serial.printf(" BUFFER SLOTS USED:    %u / %u (Utilization: %.1f%%)\n",
        static_cast<unsigned>(g_buffer.count()),
        static_cast<unsigned>(g_buffer.capacity_slots()),
        g_buffer.utilization() * 100.0f);
    Serial.printf(" BUFFER BYTES USED:    %u / %u bytes\n",
        static_cast<unsigned>(g_buffer.bytes_used()),
        static_cast<unsigned>(g_buffer.capacity_bytes()));
    Serial.printf(" PACKETS GENERATED:    %u\n", g_app.get_packets_generated());
    Serial.printf(" PACKETS RECEIVED:     %u\n", g_app.get_packets_received());
    Serial.printf(" PACKETS FORWARDED:    %u\n", g_app.get_packets_forwarded());
    Serial.printf(" PACKETS DELIVERED:    %u\n", g_app.get_packets_delivered());
    Serial.printf(" PACKETS DROPPED:      %u\n", g_app.get_packets_dropped());
    Serial.printf(" PACKETS EXPIRED:      %u\n", g_app.get_packets_expired());
    Serial.printf(" SYSTEM UPTIME:        %lu ms\n", static_cast<unsigned long>(millis()));
    Serial.println("--------------------------------------------------------\n");
}

static void print_mac_addresses() {
    char local_mac[20], peer_mac[20];
    g_transport.get_local_mac_str(local_mac, sizeof(local_mac));
    g_transport.get_peer_mac_str(peer_mac, sizeof(peer_mac));

    Serial.println("\n>>> HARDWARE MAC ADDRESS CONFIGURATION <<<");
    Serial.printf("This Node (%s) MAC: %s\n", g_local_node_id, local_mac);
    Serial.printf("Current Target Peer MAC:   %s\n", peer_mac);
    Serial.println("To pair with explicit MAC addresses, use set_peer_mac() or enter peer MAC into platformio.ini.\n");
}

void setup() {
    Serial.begin(115200);
    delay(200);

    Serial.println("\n\n========================================================");
    Serial.println("    ABHIMANYU — DTN AI ROUTING EMBEDDED NODE");
    Serial.printf("    Node Identity: %s | Target Architecture: ESP8266\n", g_local_node_id);
    Serial.println("========================================================");

    g_config = NodeConfig::create_default(g_local_node_id);
    g_transport.set_target_peer_id(g_peer_node_id);

    // If explicit peer MAC addresses are configured via compile flags
#if defined(DTN_PEER_A_MAC) && defined(DTN_NODE_B)
    const uint8_t peer_mac[] = DTN_PEER_A_MAC;
    g_transport.set_peer_mac(peer_mac);
#elif defined(DTN_PEER_B_MAC) && defined(DTN_NODE_A)
    const uint8_t peer_mac[] = DTN_PEER_B_MAC;
    g_transport.set_peer_mac(peer_mac);
#endif

    if (g_app.init()) {
        Serial.println("[BOOT] All subsystems (Transport, Display, Storage, Router) initialized.");
    } else {
        Serial.println("[BOOT] Warning: One or more subsystems failed initialization.");
    }

    print_status();
    print_help();

#ifdef DTN_SELF_TEST_ON_BOOT
    run_firmware_self_tests();
#endif
}

void loop() {
    uint32_t now = millis();

    // Interactive Serial Monitor command listener
    if (Serial.available()) {
        char cmd = static_cast<char>(Serial.read());
        // Echo and filter newlines
        if (cmd == 'm' || cmd == 'M') {
            send_test_message();
        } else if (cmd == 'r' || cmd == 'R') {
            send_ai_relay_test_message();
        } else if (cmd == 'p' || cmd == 'P') {
            Serial.println("[USER-CMD] Sending discovery beacon / ping to peer...");
            bool ok = g_transport.send_ping(now);
            Serial.printf("[USER-CMD] Ping outcome: %s\n", ok ? "ACKED by peer" : "UNACKED / Timeout");
        } else if (cmd == 's' || cmd == 'S') {
            print_status();
        } else if (cmd == 'b' || cmd == 'B') {
            print_mac_addresses();
        } else if (cmd == 't' || cmd == 'T') {
            run_firmware_self_tests();
        } else if (cmd == 'h' || cmd == 'H' || cmd == '?') {
            print_help();
        }
    }

    // Transport housekeeping (beaconing and peer range expiration)
    g_transport.tick(now);

    // Non-blocking DTN engine tick
    g_app.tick(now);

    // Yield to allow ESP8266 background WiFi/system watchdog routines to run
    yield();
}
#endif // ARDUINO
