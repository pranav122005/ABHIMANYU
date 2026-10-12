/**
 * @file packet_buffer.cpp
 * @brief Implementation of bounded packet buffer and duplicate suppression.
 */

#include "packet_buffer.h"
#include <string.h>

PacketBuffer::PacketBuffer(uint16_t max_packets, uint32_t max_bytes)
    : max_packets_(max_packets > MAX_BUFFER_PACKETS ? MAX_BUFFER_PACKETS : max_packets),
      max_bytes_(max_bytes > MAX_BUFFER_BYTES ? MAX_BUFFER_BYTES : max_bytes),
      occupied_count_(0),
      total_bytes_(0),
      seen_count_(0),
      seen_head_(0)
{
    clear();
}

void PacketBuffer::clear() {
    occupied_count_ = 0;
    total_bytes_ = 0;
    for (size_t i = 0; i < MAX_BUFFER_PACKETS; ++i) {
        slot_active_[i] = false;
    }
}

BufferOutcome PacketBuffer::add(const Packet& pkt, uint32_t current_time_ms) {
    // 1. Check if expired
    if (pkt.is_expired(current_time_ms)) {
        return BUFFER_REJECTED_EXPIRED;
    }

    // 2. Check if already present in buffer
    if (get(pkt.header.packet_id) != nullptr) {
        return BUFFER_ALREADY_PRESENT;
    }

    // 3. Check duplicate suppression filter
    if (is_seen(pkt.header.packet_id)) {
        return BUFFER_REJECTED_DUPLICATE;
    }

    // 4. Check capacity limits
    if (occupied_count_ >= max_packets_) {
        return BUFFER_REJECTED_FULL;
    }
    if (total_bytes_ + pkt.header.size_bytes > max_bytes_) {
        return BUFFER_REJECTED_FULL;
    }

    // 5. Find free slot
    for (size_t i = 0; i < max_packets_; ++i) {
        if (!slot_active_[i]) {
            slots_[i] = pkt;
            slots_[i].state = STATE_PENDING;
            slot_active_[i] = true;
            occupied_count_++;
            total_bytes_ += pkt.header.size_bytes;
            mark_seen(pkt.header.packet_id);
            return BUFFER_ACCEPTED;
        }
    }

    return BUFFER_REJECTED_FULL;
}

Packet* PacketBuffer::get(const char* packet_id) {
    if (!packet_id) return nullptr;
    for (size_t i = 0; i < max_packets_; ++i) {
        if (slot_active_[i] && strcmp(slots_[i].header.packet_id, packet_id) == 0) {
            return &slots_[i];
        }
    }
    return nullptr;
}

const Packet* PacketBuffer::get(const char* packet_id) const {
    if (!packet_id) return nullptr;
    for (size_t i = 0; i < max_packets_; ++i) {
        if (slot_active_[i] && strcmp(slots_[i].header.packet_id, packet_id) == 0) {
            return &slots_[i];
        }
    }
    return nullptr;
}

bool PacketBuffer::remove(const char* packet_id) {
    if (!packet_id) return false;
    for (size_t i = 0; i < max_packets_; ++i) {
        if (slot_active_[i] && strcmp(slots_[i].header.packet_id, packet_id) == 0) {
            if (slots_[i].header.size_bytes >= total_bytes_) {
                total_bytes_ = 0;
            } else {
                total_bytes_ -= slots_[i].header.size_bytes;
            }
            slot_active_[i] = false;
            if (occupied_count_ > 0) {
                occupied_count_--;
            }
            return true;
        }
    }
    return false;
}

bool PacketBuffer::set_state(const char* packet_id, ForwardingState state) {
    Packet* p = get(packet_id);
    if (!p) return false;
    p->state = state;
    return true;
}

size_t PacketBuffer::prune_expired(uint32_t current_time_ms) {
    size_t pruned = 0;
    for (size_t i = 0; i < max_packets_; ++i) {
        if (slot_active_[i] && slots_[i].is_expired(current_time_ms)) {
            if (slots_[i].header.size_bytes >= total_bytes_) {
                total_bytes_ = 0;
            } else {
                total_bytes_ -= slots_[i].header.size_bytes;
            }
            slot_active_[i] = false;
            if (occupied_count_ > 0) {
                occupied_count_--;
            }
            pruned++;
        }
    }
    return pruned;
}

float PacketBuffer::utilization() const {
    if (max_bytes_ == 0) return 0.0f;
    float util = static_cast<float>(total_bytes_) / static_cast<float>(max_bytes_);
    if (util > 1.0f) return 1.0f;
    return util;
}

bool PacketBuffer::is_seen(const char* packet_id) const {
    if (!packet_id) return false;
    for (size_t i = 0; i < seen_count_; ++i) {
        if (strcmp(seen_ids_[i], packet_id) == 0) {
            return true;
        }
    }
    return false;
}

void PacketBuffer::mark_seen(const char* packet_id) {
    if (!packet_id) return;
    if (is_seen(packet_id)) return;

    dtn_safe_strcpy(seen_ids_[seen_head_], packet_id, PACKET_ID_MAX_LEN);
    seen_head_ = (seen_head_ + 1) % MAX_SEEN_PACKETS;
    if (seen_count_ < MAX_SEEN_PACKETS) {
        seen_count_++;
    }
}

Packet* PacketBuffer::get_slot(size_t index) {
    if (index >= max_packets_ || !slot_active_[index]) {
        return nullptr;
    }
    return &slots_[index];
}

const Packet* PacketBuffer::get_slot(size_t index) const {
    if (index >= max_packets_ || !slot_active_[index]) {
        return nullptr;
    }
    return &slots_[index];
}
