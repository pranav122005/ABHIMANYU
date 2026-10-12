/**
 * @file router_interface.h
 * @brief Routing policy abstraction and strictly causal local feature construction.
 */

#ifndef ROUTER_INTERFACE_H
#define ROUTER_INTERFACE_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>

#include "node_config.h"
#include "packet.h"

// Bring in canonical LocalDecisionFeatures struct definition
#ifndef LOCAL_DECISION_FEATURES_DEF
#define LOCAL_DECISION_FEATURES_DEF
struct LocalDecisionFeatures {
    uint8_t  peer_is_destination;           // 1 if peer == packet destination, else 0
    uint32_t packet_size_bytes;             // Packet size in bytes
    uint8_t  packet_priority;               // Priority (1=Normal, 2=High, 3=Urgent)
    float    remaining_ttl_ratio;           // Normalized remaining TTL [0.0 - 1.0]
    uint16_t packet_hops;                   // Number of hops traversed
    uint32_t transfer_duration_ms;          // Required transfer duration in ms
    uint32_t contact_elapsed_ms;            // Elapsed time since contact establish (causal)
    uint32_t estimated_remaining_contact_ms;// Causal estimate from past encounter history
    uint8_t  estimated_transfer_fits;       // 1 if transfer fits in estimated remaining window
    float    local_buffer_utilization;      // Buffer occupancy ratio [0.0 - 1.0]
    uint16_t peer_encounter_frequency;      // Historical completed encounters with peer
};
#endif // LOCAL_DECISION_FEATURES_DEF

/**
 * @brief Contextual local information available to the node during a peer encounter.
 * Strictly causal: contains only local measurements and past history, no future oracle knowledge.
 */
struct EncounterContext {
    char peer_id[NODE_ID_MAX_LEN];          ///< ID of currently encountered peer
    uint32_t current_time_ms;               ///< Current node uptime / clock in ms
    uint32_t contact_start_ms;              ///< When current contact with peer was detected (ms)
    uint32_t avg_historical_contact_ms;     ///< Local running average of past contact durations with peer
    uint16_t peer_encounter_count;          ///< Completed past encounters with this peer
    float buffer_utilization;               ///< Current local buffer occupancy ratio [0.0 - 1.0]
    float transfer_rate_bytes_sec;          ///< Local radio transmission speed (bytes/sec)
    uint32_t transfer_overhead_ms;          ///< Radio setup / preamble overhead (ms)
};

/**
 * @brief Constructs strictly causal decision features matching the 11 Python schema features.
 */
inline LocalDecisionFeatures build_decision_features(const Packet& pkt, const EncounterContext& ctx) {
    LocalDecisionFeatures feats;

    // 1. peer_is_destination
    feats.peer_is_destination = (strcmp(ctx.peer_id, pkt.header.destination) == 0) ? 1 : 0;

    // 2. packet_size_bytes
    feats.packet_size_bytes = pkt.header.size_bytes;

    // 3. packet_priority
    feats.packet_priority = pkt.header.priority;

    // 4. remaining_ttl_ratio
    feats.remaining_ttl_ratio = pkt.remaining_ttl_ratio(ctx.current_time_ms);

    // 5. packet_hops
    feats.packet_hops = pkt.header.hops;

    // 6. transfer_duration_ms
    float rate = (ctx.transfer_rate_bytes_sec > 0.0f) ? ctx.transfer_rate_bytes_sec : DEFAULT_TRANSFER_RATE_BPS;
    uint32_t xfer_ms = ctx.transfer_overhead_ms + static_cast<uint32_t>(ceilf((pkt.header.size_bytes * 1000.0f) / rate));
    feats.transfer_duration_ms = xfer_ms;

    // 7. contact_elapsed_ms
    uint32_t elapsed_ms = (ctx.current_time_ms >= ctx.contact_start_ms) ? (ctx.current_time_ms - ctx.contact_start_ms) : 0;
    feats.contact_elapsed_ms = elapsed_ms;

    // 8. estimated_remaining_contact_ms
    uint32_t est_rem_ms = 0;
    if (ctx.avg_historical_contact_ms > elapsed_ms) {
        est_rem_ms = ctx.avg_historical_contact_ms - elapsed_ms;
    }
    feats.estimated_remaining_contact_ms = est_rem_ms;

    // 9. estimated_transfer_fits
    feats.estimated_transfer_fits = (xfer_ms <= est_rem_ms) ? 1 : 0;

    // 10. local_buffer_utilization
    feats.local_buffer_utilization = ctx.buffer_utilization;

    // 11. peer_encounter_frequency
    feats.peer_encounter_frequency = ctx.peer_encounter_count;

    return feats;
}

/**
 * @brief Abstract router interface enabling pluggable forwarding policies.
 */
class IRouter {
public:
    virtual ~IRouter() = default;

    /**
     * @brief Decides whether the buffered packet should be forwarded to the peer.
     * @return true to forward, false to hold/wait.
     */
    virtual bool should_forward(const Packet& pkt, const EncounterContext& ctx) = 0;

    /**
     * @brief Returns human-readable policy identifier.
     */
    virtual const char* get_policy_name() const = 0;
};

#endif // ROUTER_INTERFACE_H

