/**
 * @file node_config.h
 * @brief Node configuration, identity, memory limits, and prototype parameters.
 *
 * Designed for ESP8266 NodeMCU (Tensilica Xtensa L106 @ 80 MHz, ~80 KB SRAM).
 * All memory allocations are bounded and statically determinable.
 */

#ifndef NODE_CONFIG_H
#define NODE_CONFIG_H

#include <stdint.h>
#include <stddef.h>

// ============================================================================
// Node Identity & Protocol Dimensions
// ============================================================================

#define NODE_ID_MAX_LEN             16      ///< Max length for node string identifiers (e.g. "nodeRelay\0")
#define PACKET_ID_MAX_LEN           32      ///< Max length for packet identifiers (e.g. "pkt_00100\0")
#define MAX_PAYLOAD_BYTES          256      ///< Max payload capacity per packet (fits ESP-NOW 250B / NRF fragments)
#define FIRMWARE_VERSION        0x0100      ///< Firmware version 1.0.0 (high byte = major, low byte = minor)

/**
 * @brief Bounded string copy utility preventing buffer overruns.
 */
inline void dtn_safe_strcpy(char* dest, const char* src, size_t max_len) {
    if (!dest || max_len == 0) return;
    size_t i = 0;
    if (src) {
        while (src[i] != '\0' && i < max_len - 1) {
            dest[i] = src[i];
            i++;
        }
    }
    dest[i] = '\0';
}

// ============================================================================
// Bounded Buffer Prototype Parameters
// ============================================================================

/**
 * @brief Configurable prototype maximum buffered packet slots.
 *
 * Memory Footprint Calculation:
 *   16 slots * ~296 bytes/packet = ~4,736 bytes (~4.6 KB).
 *   Leaves ~35 KB+ SRAM completely free for WiFi/radio buffers and stack.
 */
#ifndef MAX_BUFFER_PACKETS
#define MAX_BUFFER_PACKETS          16
#endif

/**
 * @brief Total byte capacity for packet payloads in the buffer.
 */
#ifndef MAX_BUFFER_BYTES
#define MAX_BUFFER_BYTES          4096
#endif

/**
 * @brief Maximum remembered packet IDs for duplicate suppression.
 * 64 entries * 16 bytes = 1,024 bytes.
 */
#ifndef MAX_SEEN_PACKETS
#define MAX_SEEN_PACKETS            64
#endif

/**
 * @brief Maximum entries in the local circular event log.
 */
#define MAX_EVENT_LOG_ENTRIES       16

/**
 * @brief Maximum queued condition reports waiting for dashboard telemetry.
 */
#define MAX_QUEUED_REPORTS           8

// ============================================================================
// Timing & Radio Modeling Defaults (Non-blocking loop intervals)
// ============================================================================

#define PRUNE_INTERVAL_MS         1000      ///< Buffer maintenance & expired packet purge interval
#define REPORT_INTERVAL_MS       30000      ///< Local condition-report queueing interval
#define DISPLAY_UPDATE_INTERVAL_MS 500      ///< UI/display status update interval
#define CONTACT_POLL_INTERVAL_MS   100      ///< Peer discovery polling interval

#define DEFAULT_TRANSFER_RATE_BPS 250000.0f ///< Radio transfer rate: 250 KB/sec
#define DEFAULT_TRANSFER_OVERHEAD_MS 50     ///< Radio connection establishment overhead (ms)

#define MAX_PACKET_RETRIES           3      ///< Max immediate transmission attempts before backoff
#define RETRY_BACKOFF_MS           500      ///< Minimum backoff between failed transmission retries (ms)

// ============================================================================
// Node Configuration Struct
// ============================================================================

struct NodeConfig {
    char node_id[NODE_ID_MAX_LEN];          ///< Local node identifier
    uint16_t max_buffer_packets;            ///< Maximum packet slots
    uint32_t max_buffer_bytes;              ///< Maximum payload capacity in bytes
    float transfer_rate_bytes_sec;          ///< Simulated/configured radio rate
    uint32_t transfer_overhead_ms;          ///< Connection establishment overhead (ms)
    uint32_t report_interval_ms;            ///< Condition report generation cadence (ms)

    /**
     * @brief Creates a default configuration with the specified node identity.
     */
    static NodeConfig create_default(const char* id = "node01") {
        NodeConfig cfg;
        size_t i = 0;
        if (id) {
            while (id[i] != '\0' && i < NODE_ID_MAX_LEN - 1) {
                cfg.node_id[i] = id[i];
                i++;
            }
        }
        cfg.node_id[i] = '\0';
        cfg.max_buffer_packets = MAX_BUFFER_PACKETS;
        cfg.max_buffer_bytes = MAX_BUFFER_BYTES;
        cfg.transfer_rate_bytes_sec = DEFAULT_TRANSFER_RATE_BPS;
        cfg.transfer_overhead_ms = DEFAULT_TRANSFER_OVERHEAD_MS;
        cfg.report_interval_ms = REPORT_INTERVAL_MS;
        return cfg;
    }
};

#endif // NODE_CONFIG_H
