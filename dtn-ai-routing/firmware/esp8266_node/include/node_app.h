/**
 * @file node_app.h
 * @brief Non-blocking autonomous DTN node application coordinator.
 */

#ifndef NODE_APP_H
#define NODE_APP_H

#include <stdint.h>
#include <stddef.h>

#include "dtn_types.h"
#include "node_config.h"
#include "packet.h"
#include "packet_buffer.h"
#include "router_interface.h"
#include "transport_interface.h"
#include "display_interface.h"
#include "storage_interface.h"
#include "condition_report.h"
#include "event_logger.h"

#define MAX_TRACKED_PEERS 8

struct PeerHistoryRecord {
    char peer_id[NODE_ID_MAX_LEN];
    uint16_t encounter_count;
    uint32_t total_duration_ms;
    uint32_t last_seen_ms;
    uint32_t current_contact_start_ms;
    bool is_in_contact;
};

class NodeApp {
public:
    NodeApp(
        const NodeConfig& config,
        PacketBuffer& buffer,
        IRouter& router,
        ITransport& transport,
        IDisplay& display,
        IStorage& storage,
        ReportQueue& report_queue,
        EventLogger& logger
    );

    /**
     * @brief Initializes all subsystems.
     */
    bool init();

    /**
     * @brief Non-blocking tick executed every iteration of loop().
     * @param current_time_ms Current monotonic millisecond timestamp.
     */
    void tick(uint32_t current_time_ms);

    /**
     * @brief Generates and buffers a locally originated packet.
     */
    BufferOutcome generate_packet(
        const char* packet_id,
        const char* destination,
        uint16_t size_bytes,
        uint8_t priority,
        uint32_t ttl_ms,
        uint32_t current_time_ms,
        const uint8_t* payload = nullptr,
        uint16_t payload_len = 0
    );

    /**
     * @brief Manually notifies an encounter change (e.g. from beacon discovery).
     */
    void notify_peer_contact(const char* peer_id, bool in_contact, uint32_t current_time_ms);

    // Getters for telemetry / metrics
    const NodeConfig& get_config() const { return config_; }
    uint16_t get_packets_generated() const { return packets_generated_; }
    uint16_t get_packets_received() const { return packets_received_; }
    uint16_t get_packets_forwarded() const { return packets_forwarded_; }
    uint16_t get_packets_delivered() const { return packets_delivered_; }
    uint16_t get_packets_dropped() const { return packets_dropped_; }
    uint16_t get_packets_expired() const { return packets_expired_; }

    /**
     * @brief Resets any STATE_FAILED packets in buffer to STATE_PENDING for retry.
     */
    void reset_failed_packets();

private:
    void step_receive_packets(uint32_t current_time_ms);
    void step_route_and_forward(uint32_t current_time_ms);
    void step_buffer_maintenance(uint32_t current_time_ms);
    void step_condition_reporting(uint32_t current_time_ms);
    void step_display_update(uint32_t current_time_ms);

    PeerHistoryRecord* get_or_create_peer_record(const char* peer_id);

    NodeConfig config_;
    PacketBuffer& buffer_;
    IRouter& router_;
    ITransport& transport_;
    IDisplay& display_;
    IStorage& storage_;
    ReportQueue& report_queue_;
    EventLogger& logger_;

    // Telemetry counters
    uint16_t packets_generated_;
    uint16_t packets_received_;
    uint16_t packets_forwarded_;
    uint16_t packets_delivered_;
    uint16_t packets_dropped_;
    uint16_t packets_expired_;
    uint32_t report_seq_;
    uint32_t last_transfer_time_ms_;

    // Non-blocking timer markers
    uint32_t last_prune_time_ms_;
    uint32_t last_report_time_ms_;
    uint32_t last_display_time_ms_;

    // Historical encounter tracking
    PeerHistoryRecord peer_history_[MAX_TRACKED_PEERS];
    size_t peer_count_;
};

#endif // NODE_APP_H

