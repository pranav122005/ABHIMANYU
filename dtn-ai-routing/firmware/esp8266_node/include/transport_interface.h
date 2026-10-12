/**
 * @file transport_interface.h
 * @brief Abstract radio transport interface for peer discovery and packet transfer.
 *
 * Designed to later support NRF24L01 (SPI) or ESP-NOW (WiFi MAC layer).
 * For Stage 6A, no hardware drivers or pin layouts are assumed.
 */

#ifndef TRANSPORT_INTERFACE_H
#define TRANSPORT_INTERFACE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "dtn_types.h"
#include "node_config.h"
#include "packet.h"

class ITransport {
public:
    virtual ~ITransport() = default;

    /**
     * @brief Initializes the underlying radio hardware / stack.
     * @return true on success, false on initialization failure.
     */
    virtual bool init() = 0;

    /**
     * @brief Sends a packet over the radio to the specified peer.
     * @param target_peer Identifier of encountered peer.
     * @param pkt Packet to transmit.
     * @return true if transmission initiated and positively acknowledged by peer, false otherwise.
     */
    virtual bool send_packet(const char* target_peer, const Packet& pkt) = 0;

    /**
     * @brief Polls for an incoming packet received from a peer.
     * @param out_source_peer Buffer to receive sender node ID (min NODE_ID_MAX_LEN).
     * @param out_pkt Packet struct to populate with received data.
     * @return true if a valid packet was received, false if no packet available.
     */
    virtual bool receive_packet(char* out_source_peer, Packet& out_pkt) = 0;

    /**
     * @brief Checks if a specific peer is currently within radio contact range.
     */
    virtual bool is_peer_in_range(const char* peer_id) = 0;

    /**
     * @brief Returns current radio/link operational status.
     */
    virtual LinkStatus get_link_status() const = 0;

    /**
     * @brief Returns human-readable transport driver name.
     */
    virtual const char* get_driver_name() const = 0;
};

#endif // TRANSPORT_INTERFACE_H

