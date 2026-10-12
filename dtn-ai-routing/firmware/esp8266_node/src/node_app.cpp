/**
 * @file node_app.cpp
 * @brief Implementation of autonomous non-blocking DTN node coordinator.
 */

#include "node_app.h"
#include <string.h>

NodeApp::NodeApp(
    const NodeConfig& config,
    PacketBuffer& buffer,
    IRouter& router,
    ITransport& transport,
    IDisplay& display,
    IStorage& storage,
    ReportQueue& report_queue,
    EventLogger& logger
)
    : config_(config),
      buffer_(buffer),
      router_(router),
      transport_(transport),
      display_(display),
      storage_(storage),
      report_queue_(report_queue),
      logger_(logger),
      packets_generated_(0),
      packets_received_(0),
      packets_forwarded_(0),
      packets_delivered_(0),
      packets_dropped_(0),
      packets_expired_(0),
      report_seq_(0),
      last_transfer_time_ms_(0),
      last_prune_time_ms_(0),
      last_report_time_ms_(0),
      last_display_time_ms_(0),
      peer_count_(0)
{
    memset(peer_history_, 0, sizeof(peer_history_));
}

bool NodeApp::init() {
    bool t_ok = transport_.init();
    bool d_ok = display_.init();
    bool s_ok = storage_.init();
    logger_.log(0, EVT_BOOT, config_.node_id);
    return (t_ok && d_ok && s_ok);
}

PeerHistoryRecord* NodeApp::get_or_create_peer_record(const char* peer_id) {
    if (!peer_id) return nullptr;
    for (size_t i = 0; i < peer_count_; ++i) {
        if (strcmp(peer_history_[i].peer_id, peer_id) == 0) {
            return &peer_history_[i];
        }
    }
    if (peer_count_ < MAX_TRACKED_PEERS) {
        PeerHistoryRecord* rec = &peer_history_[peer_count_++];
        dtn_safe_strcpy(rec->peer_id, peer_id, NODE_ID_MAX_LEN);
        rec->encounter_count = 0;
        rec->total_duration_ms = 0;
        rec->last_seen_ms = 0;
        rec->current_contact_start_ms = 0;
        rec->is_in_contact = false;
        return rec;
    }
    return nullptr;
}

void NodeApp::notify_peer_contact(const char* peer_id, bool in_contact, uint32_t current_time_ms) {
    PeerHistoryRecord* rec = get_or_create_peer_record(peer_id);
    if (!rec) return;

    if (in_contact && !rec->is_in_contact) {
        // Contact established
        rec->is_in_contact = true;
        rec->current_contact_start_ms = current_time_ms;
        rec->encounter_count++;
        logger_.log(current_time_ms, EVT_PEER_DISCOVERED, peer_id);

        // Reset failed packets to PENDING so new encounter can retry them
        reset_failed_packets();
    } else if (!in_contact && rec->is_in_contact) {
        // Contact lost
        rec->is_in_contact = false;
        if (current_time_ms >= rec->current_contact_start_ms) {
            rec->total_duration_ms += (current_time_ms - rec->current_contact_start_ms);
        }
        rec->last_seen_ms = current_time_ms;
        logger_.log(current_time_ms, EVT_PEER_LOST, peer_id);
    }
}

BufferOutcome NodeApp::generate_packet(
    const char* packet_id,
    const char* destination,
    uint16_t size_bytes,
    uint8_t priority,
    uint32_t ttl_ms,
    uint32_t current_time_ms,
    const uint8_t* payload,
    uint16_t payload_len
) {
    Packet pkt = Packet::create(
        packet_id,
        config_.node_id,
        destination,
        size_bytes,
        priority,
        current_time_ms,
        ttl_ms,
        payload,
        payload_len
    );

    BufferOutcome outcome = buffer_.add(pkt, current_time_ms);
    if (outcome == BUFFER_ACCEPTED) {
        packets_generated_++;
        logger_.log(current_time_ms, EVT_PACKET_GENERATED, packet_id);
    } else if (outcome == BUFFER_REJECTED_FULL) {
        packets_dropped_++;
        logger_.log(current_time_ms, EVT_PACKET_DROPPED, packet_id);
    }
    return outcome;
}

void NodeApp::step_receive_packets(uint32_t current_time_ms) {
    char sender[NODE_ID_MAX_LEN];
    Packet in_pkt;

    while (transport_.receive_packet(sender, in_pkt)) {
        // Check if destination is this node
        if (strcmp(in_pkt.header.destination, config_.node_id) == 0) {
            // Check duplicate suppression filter to prevent repeated destination delivery
            if (buffer_.is_seen(in_pkt.header.packet_id)) {
                continue;
            }
            in_pkt.state = STATE_DELIVERED;
            packets_delivered_++;
            buffer_.mark_seen(in_pkt.header.packet_id);
            logger_.log(current_time_ms, EVT_PACKET_DELIVERED, in_pkt.header.packet_id);
            continue;
        }

        // Try adding to local buffer for store-carry-forward
        BufferOutcome outcome = buffer_.add(in_pkt, current_time_ms);
        if (outcome == BUFFER_ACCEPTED) {
            packets_received_++;
            logger_.log(current_time_ms, EVT_PACKET_ACCEPTED, in_pkt.header.packet_id);
        } else if (outcome == BUFFER_REJECTED_FULL) {
            packets_dropped_++;
            logger_.log(current_time_ms, EVT_PACKET_DROPPED, in_pkt.header.packet_id);
        } else if (outcome == BUFFER_REJECTED_EXPIRED) {
            packets_expired_++;
            logger_.log(current_time_ms, EVT_PACKET_EXPIRED, in_pkt.header.packet_id);
        }
    }
}

void NodeApp::step_route_and_forward(uint32_t current_time_ms) {
    for (size_t p = 0; p < peer_count_; ++p) {
        PeerHistoryRecord& peer = peer_history_[p];
        bool in_range = transport_.is_peer_in_range(peer.peer_id);
        notify_peer_contact(peer.peer_id, in_range, current_time_ms);

        if (!peer.is_in_contact) {
            continue;
        }

        // Build strictly causal EncounterContext
        EncounterContext ctx;
        dtn_safe_strcpy(ctx.peer_id, peer.peer_id, NODE_ID_MAX_LEN);
        ctx.current_time_ms = current_time_ms;
        ctx.contact_start_ms = peer.current_contact_start_ms;
        ctx.avg_historical_contact_ms = (peer.encounter_count > 0 && peer.total_duration_ms > 0)
            ? (peer.total_duration_ms / peer.encounter_count)
            : 5000;
        ctx.peer_encounter_count = peer.encounter_count;
        ctx.buffer_utilization = buffer_.utilization();
        ctx.transfer_rate_bytes_sec = config_.transfer_rate_bytes_sec;
        ctx.transfer_overhead_ms = config_.transfer_overhead_ms;

        // Evaluate buffered packets (only packets in STATE_PENDING are eligible)
        for (size_t s = 0; s < buffer_.capacity_slots(); ++s) {
            Packet* pkt = buffer_.get_slot(s);
            if (!pkt || pkt->is_expired(current_time_ms) || pkt->state != STATE_PENDING) {
                continue;
            }

            // Check retry backoff (rollover-safe signed comparison)
            if (pkt->next_retry_time_ms != 0 &&
                static_cast<int32_t>(current_time_ms - pkt->next_retry_time_ms) < 0) {
                continue; // Backoff active: avoid infinite tight retry loop
            }

            // Ask pluggable routing engine (Stage 5.2 Decision Tree)
            if (router_.should_forward(*pkt, ctx)) {
                // Initiation of transmission
                pkt->state = STATE_TRANSMITTING;
                bool tx_ok = transport_.send_packet(peer.peer_id, *pkt);

                if (tx_ok) {
                    last_transfer_time_ms_ = current_time_ms;
                    char pkt_id[PACKET_ID_MAX_LEN];
                    dtn_safe_strcpy(pkt_id, pkt->header.packet_id, PACKET_ID_MAX_LEN);

                    if (strcmp(peer.peer_id, pkt->header.destination) == 0) {
                        pkt->state = STATE_DELIVERED;
                        packets_delivered_++;
                        buffer_.mark_seen(pkt_id);
                        logger_.log(current_time_ms, EVT_PACKET_DELIVERED, pkt_id);
                    } else {
                        pkt->state = STATE_FORWARDED;
                        packets_forwarded_++;
                        buffer_.mark_seen(pkt_id);
                        logger_.log(current_time_ms, EVT_PACKET_FORWARDED, pkt_id);
                    }

                    // Remove from local buffer after positively acknowledged forwarding
                    buffer_.remove(pkt_id);
                    // Transmit at most one packet per peer per tick to keep loop responsive
                    break;
                } else {
                    // Transmission failed or unacknowledged: bound retry attempts
                    pkt->retry_count++;
                    pkt->next_retry_time_ms = current_time_ms + RETRY_BACKOFF_MS;
                    if (pkt->retry_count >= MAX_PACKET_RETRIES) {
                        pkt->state = STATE_FAILED;
                    } else {
                        pkt->state = STATE_PENDING;
                    }
                }
            }
        }
    }
}

void NodeApp::step_buffer_maintenance(uint32_t current_time_ms) {
    if (current_time_ms - last_prune_time_ms_ >= PRUNE_INTERVAL_MS) {
        size_t pruned = buffer_.prune_expired(current_time_ms);
        packets_expired_ += pruned;
        last_prune_time_ms_ = current_time_ms;
    }
}

void NodeApp::step_condition_reporting(uint32_t current_time_ms) {
    if (current_time_ms - last_report_time_ms_ >= config_.report_interval_ms) {
        NodeConditionReport report;
        report.schema_version = CONDITION_REPORT_SCHEMA_VERSION;
        dtn_safe_strcpy(report.node_id, config_.node_id, NODE_ID_MAX_LEN);
        report.sequence_number = ++report_seq_;
        report.uptime_ms = current_time_ms;
        report.buffer_packet_count = static_cast<uint16_t>(buffer_.count());
        report.buffer_bytes_used = buffer_.bytes_used();
        report.packets_generated = packets_generated_;
        report.packets_received = packets_received_;
        report.packets_forwarded = packets_forwarded_;
        report.packets_delivered = packets_delivered_;
        report.packets_dropped = packets_dropped_;
        report.packets_expired = packets_expired_;
        report.radio_rssi_dbm = RADIO_METRIC_UNAVAILABLE; // Explicitly marked unavailable
        report.last_transfer_time_ms = last_transfer_time_ms_;
        report.firmware_version = FIRMWARE_VERSION;

        report_queue_.enqueue(report);
        logger_.log(current_time_ms, EVT_REPORT_QUEUED, nullptr);
        last_report_time_ms_ = current_time_ms;
    }
}

void NodeApp::step_display_update(uint32_t current_time_ms) {
    if (current_time_ms - last_display_time_ms_ >= DISPLAY_UPDATE_INTERVAL_MS) {
        NodeStatus status;
        dtn_safe_strcpy(status.node_id, config_.node_id, NODE_ID_MAX_LEN);
        status.buffer_packet_count = buffer_.count();
        status.buffer_capacity = buffer_.capacity_slots();
        status.buffer_utilization = buffer_.utilization();
        status.successful_transfers = packets_forwarded_ + packets_delivered_;
        status.failed_transfers = packets_dropped_;
        status.link_status = transport_.get_link_status();
        dtn_safe_strcpy(status.current_action, router_.get_policy_name(), sizeof(status.current_action));

        display_.update_status(status);
        last_display_time_ms_ = current_time_ms;
    }
}

void NodeApp::tick(uint32_t current_time_ms) {
    step_receive_packets(current_time_ms);
    step_route_and_forward(current_time_ms);
    step_buffer_maintenance(current_time_ms);
    step_condition_reporting(current_time_ms);
    step_display_update(current_time_ms);
}

void NodeApp::reset_failed_packets() {
    for (size_t s = 0; s < buffer_.capacity_slots(); ++s) {
        Packet* p = buffer_.get_slot(s);
        if (p && p->state == STATE_FAILED) {
            p->state = STATE_PENDING;
            p->retry_count = 0;
            p->next_retry_time_ms = 0;
        }
    }
}

