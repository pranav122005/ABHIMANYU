/**
 * @file dtn_types.h
 * @brief Common types, enumerations, and return codes for ESP8266 DTN node.
 */

#ifndef DTN_TYPES_H
#define DTN_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Outcome of attempting to add a packet to the local node buffer.
 */
typedef enum {
    BUFFER_ACCEPTED = 0,           ///< Successfully stored in buffer
    BUFFER_REJECTED_FULL,          ///< Buffer full; cannot accommodate packet size/count
    BUFFER_REJECTED_DUPLICATE,     ///< Packet was previously received and processed
    BUFFER_REJECTED_EXPIRED,       ///< Packet TTL has already expired
    BUFFER_ALREADY_PRESENT         ///< Packet is already currently sitting in buffer
} BufferOutcome;

/**
 * @brief Forwarding lifecycle state of a buffered packet.
 */
typedef enum {
    STATE_PENDING = 0,             ///< In buffer, waiting for a suitable forwarding encounter
    STATE_TRANSMITTING,            ///< Transmission initiated over radio transport
    STATE_FORWARDED,               ///< Successfully transferred to relay peer (acknowledged)
    STATE_DELIVERED,               ///< Handed directly to destination node
    STATE_EXPIRED,                 ///< TTL expired before successful forwarding
    STATE_FAILED                   ///< Transmission failed or unacknowledged after max retries
} ForwardingState;

/**
 * @brief Physical radio link status abstraction.
 */
typedef enum {
    LINK_UNAVAILABLE = 0,          ///< Radio hardware uninitialized or no link
    LINK_IDLE,                     ///< Radio ready, listening / idle
    LINK_DISCOVERING,              ///< Scanning or broadcasting beacon
    LINK_TRANSMITTING,             ///< Packet transfer in flight
    LINK_RECEIVING,                ///< Inbound packet receiving
    LINK_ERROR                     ///< Hardware or transmission timeout error
} LinkStatus;

/**
 * @brief System event codes for the local circular event logger.
 */
typedef enum {
    EVT_BOOT = 0,                  ///< System booted
    EVT_PACKET_GENERATED,          ///< Locally generated packet
    EVT_PACKET_ACCEPTED,           ///< Received packet accepted into buffer
    EVT_PACKET_FORWARDED,          ///< Packet forwarded to relay
    EVT_PACKET_DELIVERED,          ///< Packet delivered to final destination
    EVT_PACKET_DROPPED,            ///< Packet dropped due to buffer capacity
    EVT_PACKET_EXPIRED,            ///< Expired packet pruned from buffer
    EVT_PEER_DISCOVERED,           ///< New peer encounter started
    EVT_PEER_LOST,                 ///< Peer contact ended
    EVT_REPORT_QUEUED              ///< Condition report queued
} EventCode;

#ifdef __cplusplus
}
#endif

#endif // DTN_TYPES_H

