/**
 * @file ram_storage.h
 * @brief RAM-backed mock storage for unit testing without hardware storage media.
 */

#ifndef RAM_STORAGE_H
#define RAM_STORAGE_H

#include <string.h>
#include "storage_interface.h"

#define RAM_STORAGE_MAX_SLOTS 8
#define RAM_STORAGE_MAX_EVENTS 16

class RamStorage : public IStorage {
public:
    RamStorage()
        : slot_count_(0),
          event_count_(0)
    {
        for (size_t i = 0; i < RAM_STORAGE_MAX_SLOTS; ++i) {
            slot_used_[i] = false;
        }
    }

    virtual ~RamStorage() = default;

    virtual bool init() override {
        return true;
    }

    virtual bool save_packet(const Packet& pkt) override {
        // Update existing if present
        for (size_t i = 0; i < RAM_STORAGE_MAX_SLOTS; ++i) {
            if (slot_used_[i] && strcmp(stored_packets_[i].header.packet_id, pkt.header.packet_id) == 0) {
                stored_packets_[i] = pkt;
                return true;
            }
        }
        // Insert into free slot
        for (size_t i = 0; i < RAM_STORAGE_MAX_SLOTS; ++i) {
            if (!slot_used_[i]) {
                stored_packets_[i] = pkt;
                slot_used_[i] = true;
                slot_count_++;
                return true;
            }
        }
        return false;
    }

    virtual bool load_packet(const char* packet_id, Packet& out_pkt) override {
        if (!packet_id) return false;
        for (size_t i = 0; i < RAM_STORAGE_MAX_SLOTS; ++i) {
            if (slot_used_[i] && strcmp(stored_packets_[i].header.packet_id, packet_id) == 0) {
                out_pkt = stored_packets_[i];
                return true;
            }
        }
        return false;
    }

    virtual bool delete_packet(const char* packet_id) override {
        if (!packet_id) return false;
        for (size_t i = 0; i < RAM_STORAGE_MAX_SLOTS; ++i) {
            if (slot_used_[i] && strcmp(stored_packets_[i].header.packet_id, packet_id) == 0) {
                slot_used_[i] = false;
                slot_count_--;
                return true;
            }
        }
        return false;
    }

    virtual bool append_event(const SystemEvent& evt) override {
        if (event_count_ < RAM_STORAGE_MAX_EVENTS) {
            events_[event_count_++] = evt;
        } else {
            // Ring overwrite
            for (size_t i = 0; i < RAM_STORAGE_MAX_EVENTS - 1; ++i) {
                events_[i] = events_[i + 1];
            }
            events_[RAM_STORAGE_MAX_EVENTS - 1] = evt;
        }
        return true;
    }

    virtual const char* get_storage_name() const override {
        return "RamStorage (RAM-Backed/Test)";
    }

    size_t get_stored_packet_count() const { return slot_count_; }
    size_t get_logged_event_count() const { return event_count_; }

private:
    Packet stored_packets_[RAM_STORAGE_MAX_SLOTS];
    bool slot_used_[RAM_STORAGE_MAX_SLOTS];
    size_t slot_count_;

    SystemEvent events_[RAM_STORAGE_MAX_EVENTS];
    size_t event_count_;
};

#endif // RAM_STORAGE_H

