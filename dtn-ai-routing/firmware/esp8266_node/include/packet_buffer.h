/**
 * @file packet_buffer.h
 * @brief Bounded local packet buffer and duplicate suppression for ESP8266.
 */

#ifndef PACKET_BUFFER_H
#define PACKET_BUFFER_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "dtn_types.h"
#include "node_config.h"
#include "packet.h"

/**
 * @brief Manages a fixed-size slot pool of packets and duplicate suppression.
 */
class PacketBuffer {
public:
    PacketBuffer(uint16_t max_packets = MAX_BUFFER_PACKETS, uint32_t max_bytes = MAX_BUFFER_BYTES);

    /**
     * @brief Attempts to insert a packet into the buffer.
     * Checks for expiration, duplicates, already-present status, and capacity.
     */
    BufferOutcome add(const Packet& pkt, uint32_t current_time_ms);

    /**
     * @brief Finds a packet slot by its packet ID.
     * @return Pointer to packet, or nullptr if not found.
     */
    Packet* get(const char* packet_id);
    const Packet* get(const char* packet_id) const;

    /**
     * @brief Removes a packet from the buffer by ID.
     * @return true if found and removed, false otherwise.
     */
    bool remove(const char* packet_id);

    /**
     * @brief Updates the forwarding state of a buffered packet.
     */
    bool set_state(const char* packet_id, ForwardingState state);

    /**
     * @brief Prunes all expired packets based on the current timestamp.
     * @return Number of expired packets removed.
     */
    size_t prune_expired(uint32_t current_time_ms);

    /**
     * @brief Returns the number of currently occupied packet slots.
     */
    size_t count() const { return occupied_count_; }

    /**
     * @brief Returns the maximum packet slot capacity.
     */
    size_t capacity_slots() const { return max_packets_; }

    /**
     * @brief Returns total logical bytes occupied by stored packets.
     */
    uint32_t bytes_used() const { return total_bytes_; }

    /**
     * @brief Returns maximum byte capacity.
     */
    uint32_t capacity_bytes() const { return max_bytes_; }

    /**
     * @brief Computes buffer utilization ratio [0.0 - 1.0].
     */
    float utilization() const;

    /**
     * @brief Checks if a packet has already been seen/processed.
     */
    bool is_seen(const char* packet_id) const;

    /**
     * @brief Marks a packet ID as seen in the duplicate suppression ring.
     */
    void mark_seen(const char* packet_id);

    /**
     * @brief Access slot by index [0, max_packets_ - 1] (for iteration).
     * @return Pointer to packet, or nullptr if slot is empty.
     */
    Packet* get_slot(size_t index);
    const Packet* get_slot(size_t index) const;

    /**
     * @brief Clears all packets from buffer and resets counters.
     */
    void clear();

private:
    uint16_t max_packets_;
    uint32_t max_bytes_;
    uint16_t occupied_count_;
    uint32_t total_bytes_;

    // Statically bounded storage pool
    Packet slots_[MAX_BUFFER_PACKETS];
    bool slot_active_[MAX_BUFFER_PACKETS];

    // Seen packets circular ring buffer for duplicate suppression
    char seen_ids_[MAX_SEEN_PACKETS][PACKET_ID_MAX_LEN];
    size_t seen_count_;
    size_t seen_head_;
};

#endif // PACKET_BUFFER_H

