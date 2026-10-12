/**
 * @file packet.cpp
 * @brief Implementation of DTN packet constructors and serialization.
 */

#include "packet.h"
#include <string.h>

Packet::Packet() {
    memset(&header, 0, sizeof(header));
    memset(payload, 0, sizeof(payload));
    payload_len = 0;
    state = STATE_PENDING;
}

Packet Packet::create(
    const char* id,
    const char* src,
    const char* dst,
    uint16_t size,
    uint8_t prio,
    uint32_t creation_ms,
    uint32_t ttl_ms,
    const uint8_t* p_data,
    uint16_t p_len
) {
    Packet pkt;
    dtn_safe_strcpy(pkt.header.packet_id, id, PACKET_ID_MAX_LEN);
    dtn_safe_strcpy(pkt.header.source, src, NODE_ID_MAX_LEN);
    dtn_safe_strcpy(pkt.header.destination, dst, NODE_ID_MAX_LEN);
    pkt.header.size_bytes = size;
    pkt.header.priority = prio;
    pkt.header.hops = 0;
    pkt.header.creation_time_ms = creation_ms;
    pkt.header.expiry_time_ms = creation_ms + ttl_ms;
    pkt.state = STATE_PENDING;

    if (p_data && p_len > 0) {
        uint16_t copy_len = (p_len > MAX_PAYLOAD_BYTES) ? MAX_PAYLOAD_BYTES : p_len;
        memcpy(pkt.payload, p_data, copy_len);
        pkt.payload_len = copy_len;
    } else {
        pkt.payload_len = 0;
    }

    return pkt;
}

bool Packet::is_expired(uint32_t current_time_ms) const {
    // Timer rollover safe: signed difference handles uint32_t wrap-around (Linux time_after pattern)
    return static_cast<int32_t>(current_time_ms - header.expiry_time_ms) >= 0;
}

uint32_t Packet::remaining_ttl_ms(uint32_t current_time_ms) const {
    if (is_expired(current_time_ms)) {
        return 0;
    }
    return header.expiry_time_ms - current_time_ms;
}

float Packet::remaining_ttl_ratio(uint32_t current_time_ms) const {
    if (is_expired(current_time_ms)) {
        return 0.0f;
    }
    int32_t total_ttl = static_cast<int32_t>(header.expiry_time_ms - header.creation_time_ms);
    if (total_ttl <= 0) return 0.0f;
    int32_t rem = static_cast<int32_t>(header.expiry_time_ms - current_time_ms);
    if (rem <= 0) return 0.0f;
    float ratio = static_cast<float>(rem) / static_cast<float>(total_ttl);
    if (ratio > 1.0f) return 1.0f;
    if (ratio < 0.0f) return 0.0f;
    return ratio;
}

static inline void write_le16(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v & 0xFF);
    p[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
}

static inline void write_le32(uint8_t* p, uint32_t v) {
    p[0] = static_cast<uint8_t>(v & 0xFF);
    p[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
    p[2] = static_cast<uint8_t>((v >> 16) & 0xFF);
    p[3] = static_cast<uint8_t>((v >> 24) & 0xFF);
}

static inline uint16_t read_le16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

static inline uint32_t read_le32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0])
         | (static_cast<uint32_t>(p[1]) << 8)
         | (static_cast<uint32_t>(p[2]) << 16)
         | (static_cast<uint32_t>(p[3]) << 24);
}

size_t Packet::serialize(uint8_t* out_buf, size_t max_len) const {
    if (!out_buf) return 0;
    size_t required = PACKET_WIRE_MIN_BYTES + payload_len;
    if (max_len < required) return 0;

    // Explicit field-by-field little-endian serialization
    // 0..31: packet_id (32 bytes)
    memset(out_buf, 0, PACKET_WIRE_MIN_BYTES);
    dtn_safe_strcpy(reinterpret_cast<char*>(out_buf), header.packet_id, PACKET_ID_MAX_LEN);

    // 32..47: source (16 bytes)
    dtn_safe_strcpy(reinterpret_cast<char*>(out_buf + 32), header.source, NODE_ID_MAX_LEN);

    // 48..63: destination (16 bytes)
    dtn_safe_strcpy(reinterpret_cast<char*>(out_buf + 48), header.destination, NODE_ID_MAX_LEN);

    // 64..65: size_bytes (2 bytes, LE)
    write_le16(out_buf + 64, header.size_bytes);

    // 66: priority (1 byte)
    out_buf[66] = header.priority;

    // 67: hops (1 byte)
    out_buf[67] = header.hops;

    // 68..71: creation_time_ms (4 bytes, LE)
    write_le32(out_buf + 68, header.creation_time_ms);

    // 72..75: expiry_time_ms (4 bytes, LE)
    write_le32(out_buf + 72, header.expiry_time_ms);

    // 76..77: payload_len (2 bytes, LE)
    write_le16(out_buf + 76, payload_len);

    // 78..: payload bytes
    if (payload_len > 0) {
        memcpy(out_buf + PACKET_WIRE_MIN_BYTES, payload, payload_len);
    }

    return required;
}

bool Packet::deserialize(const uint8_t* in_buf, size_t len) {
    if (!in_buf || len < PACKET_WIRE_MIN_BYTES) {
        return false;
    }

    // 1. Extract IDs with strict bounding
    dtn_safe_strcpy(header.packet_id, reinterpret_cast<const char*>(in_buf), PACKET_ID_MAX_LEN);
    dtn_safe_strcpy(header.source, reinterpret_cast<const char*>(in_buf + 32), NODE_ID_MAX_LEN);
    dtn_safe_strcpy(header.destination, reinterpret_cast<const char*>(in_buf + 48), NODE_ID_MAX_LEN);

    // Reject empty identifiers
    if (header.packet_id[0] == '\0' || header.source[0] == '\0' || header.destination[0] == '\0') {
        return false;
    }

    // 2. Extract numeric fields
    header.size_bytes = read_le16(in_buf + 64);
    header.priority = in_buf[66];
    header.hops = in_buf[67];
    header.creation_time_ms = read_le32(in_buf + 68);
    header.expiry_time_ms = read_le32(in_buf + 72);

    // Reject invalid priority (1=Normal, 2=High, 3=Urgent)
    if (header.priority < 1 || header.priority > 3) {
        return false;
    }

    // Reject inverted TTL (expiry before creation in signed modular difference)
    if (static_cast<int32_t>(header.expiry_time_ms - header.creation_time_ms) < 0) {
        return false;
    }

    // 3. Extract and validate payload
    uint16_t p_len = read_le16(in_buf + 76);
    if (p_len > MAX_PAYLOAD_BYTES) {
        return false;
    }
    if (len < static_cast<size_t>(PACKET_WIRE_MIN_BYTES) + static_cast<size_t>(p_len)) {
        return false; // Truncated packet
    }

    payload_len = p_len;
    if (payload_len > 0) {
        memcpy(payload, in_buf + PACKET_WIRE_MIN_BYTES, payload_len);
    }
    state = STATE_PENDING;
    return true;
}
