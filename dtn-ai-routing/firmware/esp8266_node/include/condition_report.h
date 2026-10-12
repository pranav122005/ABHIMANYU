/**
 * @file condition_report.h
 * @brief Versioned node condition-report structure and bounded queue for telemetry.
 */

#ifndef CONDITION_REPORT_H
#define CONDITION_REPORT_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "dtn_types.h"
#include "node_config.h"

#define CONDITION_REPORT_SCHEMA_VERSION 1
#define RADIO_METRIC_UNAVAILABLE       (-999)  ///< Explicit sentinel for unequipped/unavailable radio reading

#pragma pack(push, 1)
/**
 * @brief Compact binary wire format for node telemetry condition reports.
 * Size: 1 + 8 + 4 + 4 + 2 + 4 + 2*6 + 2 + 4 + 2 = 43 bytes.
 */
struct NodeConditionReport {
    uint8_t schema_version;                 ///< Schema format version (1)
    char node_id[NODE_ID_MAX_LEN];          ///< Local node identifier
    uint32_t sequence_number;               ///< Monotonically increasing report counter
    uint32_t uptime_ms;                     ///< System uptime in milliseconds
    uint16_t buffer_packet_count;           ///< Number of packets in buffer
    uint32_t buffer_bytes_used;             ///< Current payload bytes in buffer
    uint16_t packets_generated;             ///< Packets locally generated
    uint16_t packets_received;              ///< Inbound packets received from peers
    uint16_t packets_forwarded;             ///< Packets relayed to peers
    uint16_t packets_delivered;             ///< Packets successfully delivered to destination
    uint16_t packets_dropped;               ///< Packets dropped due to buffer exhaustion
    uint16_t packets_expired;               ///< Packets pruned due to TTL expiration
    int16_t  radio_rssi_dbm;                ///< Last link RSSI in dBm, or RADIO_METRIC_UNAVAILABLE
    uint32_t last_transfer_time_ms;         ///< Timestamp of last successful transfer (0 if none)
    uint16_t firmware_version;              ///< Firmware version (e.g. 0x0100)
};
#pragma pack(pop)

/**
 * @brief Bounded FIFO queue for storing reports until transmitted.
 */
class ReportQueue {
public:
    ReportQueue();

    /**
     * @brief Enqueues a condition report.
     * @return true if enqueued, false if queue is full.
     */
    bool enqueue(const NodeConditionReport& report);

    /**
     * @brief Dequeues the oldest condition report.
     * @return true if dequeued, false if queue was empty.
     */
    bool dequeue(NodeConditionReport& out_report);

    /**
     * @brief Peeks at the front report without removing it.
     */
    const NodeConditionReport* peek() const;

    size_t count() const { return count_; }
    size_t capacity() const { return MAX_QUEUED_REPORTS; }
    bool is_empty() const { return count_ == 0; }
    bool is_full() const { return count_ >= MAX_QUEUED_REPORTS; }
    void clear();

private:
    NodeConditionReport queue_[MAX_QUEUED_REPORTS];
    size_t head_;
    size_t tail_;
    size_t count_;
};

#endif // CONDITION_REPORT_H

