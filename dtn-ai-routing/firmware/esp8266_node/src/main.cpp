/**
 * @file main.cpp
 * @brief Autonomous ESP8266 NodeMCU DTN Node firmware entry point.
 *
 * Provides Arduino setup() and loop() hooks when compiled for ESP8266.
 */

#ifdef ARDUINO
#include <Arduino.h>
#include "node_config.h"
#include "packet_buffer.h"
#include "decision_tree_router.h"
#include "null_display.h"
#include "ram_storage.h"
#include "condition_report.h"
#include "event_logger.h"
#include "node_app.h"
#include "self_test.h"

// Note: Transport is injected at build time. Default is uninitialized/null placeholder
// until physical radio driver (NRF24L01 / ESP-NOW) is confirmed.
#include "fake_transport.h"

static NodeConfig g_config;
static PacketBuffer g_buffer(MAX_BUFFER_PACKETS, MAX_BUFFER_BYTES);
static DecisionTreeRouter g_router;
static FakeTransport g_transport; // Replaced once hardware transport is selected
static NullDisplay g_display;     // Replaced once OLED display is selected
static RamStorage g_storage;       // Replaced once storage module is selected
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

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("\n[DTN NODE] Booting Autonomous NodeMCU Firmware v1.0...");

    g_config = NodeConfig::create_default("node01");
    if (g_app.init()) {
        Serial.println("[DTN NODE] Subsystems initialized successfully.");
    } else {
        Serial.println("[DTN NODE] Warning: One or more subsystems failed initialization.");
    }

#ifdef DTN_SELF_TEST_ON_BOOT
    run_firmware_self_tests();
#else
    Serial.println("[DTN NODE] Press 'T' in Serial Monitor to run deterministic AI self-tests.");
#endif
}

void loop() {
    // Non-blocking serial command listener for deterministic AI self-test mode
    if (Serial.available()) {
        char cmd = static_cast<char>(Serial.read());
        if (cmd == 't' || cmd == 'T') {
            run_firmware_self_tests();
        }
    }

    uint32_t now = millis();
    g_app.tick(now);
    // Yield to allow ESP8266 background WiFi/system watchdog routines to run
    yield();
}
#endif // ARDUINO


