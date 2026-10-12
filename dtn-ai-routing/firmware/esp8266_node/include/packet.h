/**
 * @file packet.h
 * @brief DTN Packet structures, metadata, and byte serialization.
 */

#ifndef PACKET_H
#define PACKET_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "dtn_types.h"
#include "node_config.h"

#define PACKET_WIRE_HEADER_BYTES    76U     ///< Wire header size without payload_len
#define PACKET_WIRE_MIN_BYTES       78U     ///< Minimum wire frame size (76 header + 2 payload_len)

#pragma pack(push, 1)
/**
 * @brief Compact packed header for network wire serialization.
 * Fixed layout: 32 (ID) + 16 (Src) + 16 (Dst) + 2 (size) + 1 (prio) + 1 (hops) + 4 (creation) + 4 (expiry) = 76 bytes.
 */
struct PacketWireHeader {
    char packet_id[PACKET_ID_MAX_LEN];      ///< Unique packet ID (32 bytes)
    char source[NODE_ID_MAX_LEN];           ///< Originating node ID (16 bytes)
    char destination[NODE_ID_MAX_LEN];      ///< Destination node ID (16 bytes)
    uint16_t size_bytes;                    ///< Packet logical size (bytes, little-endian)
    uint8_t priority;                       ///< Priority: 1=Normal, 2=High, 3=Urgent
    uint8_t hops;                           ///< Hops traversed
    uint32_t creation_time_ms;              ///< Creation time ms (little-endian)
    uint32_t expiry_time_ms;                ///< Absolute expiration timestamp ms (little-endian)
};
#pragma pack(pop)

/**
 * @brief In-memory packet representation.
 */
struct Packet {
    PacketWireHeader header;
    uint8_t payload[MAX_PAYLOAD_BYTES];     ///< Raw payload buffer
    uint16_t payload_len;                   ///< Actual payload length in bytes
    ForwardingState state;                  ///< Lifecycle state

    Packet();

    /**
     * @brief Factory constructor for initializing a new packet.
     */
    static Packet create(
        const char* id,
        const char* src,
        const char* dst,
        uint16_t size,
        uint8_t prio,
        uint32_t creation_ms,
        uint32_t ttl_ms,
        const uint8_t* p_data = nullptr,
        uint16_t p_len = 0
    );

    /**
     * @brief Checks if packet has expired at the given timestamp.
     */
    bool is_expired(uint32_t current_time_ms) const;

    /**
     * @brief Computes remaining TTL in milliseconds.
     */
    uint32_t remaining_ttl_ms(uint32_t current_time_ms) const;

    /**
     * @brief Computes normalized remaining TTL ratio [0.0 - 1.0].
     */
    float remaining_ttl_ratio(uint32_t current_time_ms) const;

    /**
     * @brief Serializes packet into a compact binary wire format.
     * @return Number of bytes written, or 0 on error / buffer overflow.
     */
    size_t serialize(uint8_t* out_buf, size_t max_len) const;

    /**
     * @brief Deserializes a binary wire payload into this packet instance.
     * @return true if successfully deserialized, false if corrupted or truncated.
     */
    bool deserialize(const uint8_t* in_buf, size_t len);
};

#endif // PACKET_H

