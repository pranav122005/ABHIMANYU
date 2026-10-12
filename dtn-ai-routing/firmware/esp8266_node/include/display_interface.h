/**
 * @file display_interface.h
 * @brief Abstract display interface for node status visualization.
 *
 * Designed to later support I2C OLED (e.g. SSD1306 128x64) without assuming hardware now.
 */

#ifndef DISPLAY_INTERFACE_H
#define DISPLAY_INTERFACE_H

#include <stdint.h>
#include <stddef.h>
#include "dtn_types.h"
#include "node_config.h"

/**
 * @brief Current operational snapshot for status display.
 */
struct NodeStatus {
    char node_id[NODE_ID_MAX_LEN];          ///< Local node identifier
    size_t buffer_packet_count;             ///< Number of queued packets in buffer
    size_t buffer_capacity;                 ///< Total buffer slot capacity
    float buffer_utilization;               ///< Buffer occupancy ratio [0.0 - 1.0]
    uint32_t successful_transfers;          ///< Total successful forwarding events
    uint32_t failed_transfers;              ///< Total failed / rejected attempts
    LinkStatus link_status;                 ///< Current radio status
    char current_action[24];                ///< Short string of current action (e.g. "IDLE", "FWD:nodeB")
};

class IDisplay {
public:
    virtual ~IDisplay() = default;

    /**
     * @brief Initializes display hardware (e.g. I2C bus, pins).
     * @return true on success.
     */
    virtual bool init() = 0;

    /**
     * @brief Refreshes the display with current node status.
     */
    virtual void update_status(const NodeStatus& status) = 0;

    /**
     * @brief Returns display hardware name or model string.
     */
    virtual const char* get_display_name() const = 0;
};

#endif // DISPLAY_INTERFACE_H

