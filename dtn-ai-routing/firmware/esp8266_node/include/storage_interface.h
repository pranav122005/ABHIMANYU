/**
 * @file storage_interface.h
 * @brief Abstract persistent storage interface for packets and event logging.
 *
 * Can later be implemented using LittleFS, SPIFFS, or external SPI SD/EEPROM.
 */

#ifndef STORAGE_INTERFACE_H
#define STORAGE_INTERFACE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "dtn_types.h"
#include "packet.h"

/**
 * @brief Compact system event record for local event logging.
 */
struct SystemEvent {
    uint32_t timestamp_ms;                  ///< Time event occurred
    EventCode code;                         ///< Event type
    char detail[16];                        ///< Short detail (e.g. packet_id or peer_id)
};

class IStorage {
public:
    virtual ~IStorage() = default;

    /**
     * @brief Mounts / initializes storage filesystem or media.
     * @return true on success.
     */
    virtual bool init() = 0;

    /**
     * @brief Persists a packet to non-volatile storage.
     */
    virtual bool save_packet(const Packet& pkt) = 0;

    /**
     * @brief Loads a packet by ID from non-volatile storage.
     */
    virtual bool load_packet(const char* packet_id, Packet& out_pkt) = 0;

    /**
     * @brief Deletes a packet from non-volatile storage.
     */
    virtual bool delete_packet(const char* packet_id) = 0;

    /**
     * @brief Appends an event record to non-volatile audit log.
     */
    virtual bool append_event(const SystemEvent& evt) = 0;

    /**
     * @brief Returns storage driver / media description.
     */
    virtual const char* get_storage_name() const = 0;
};

#endif // STORAGE_INTERFACE_H

