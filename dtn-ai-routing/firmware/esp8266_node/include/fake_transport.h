/**
 * @file fake_transport.h
 * @brief Test-only mock transport for unit testing without physical radio hardware.
 *
 * NOTE: STRICTLY TEST-ONLY. DOES NOT COMMUNICATE OVER AIR.
 */

#ifndef FAKE_TRANSPORT_H
#define FAKE_TRANSPORT_H

#include <string.h>
#include "transport_interface.h"

#define FAKE_QUEUE_CAPACITY 8
#define FAKE_MAX_PEERS 4

class FakeTransport : public ITransport {
public:
    FakeTransport()
        : link_status_(LINK_IDLE),
          rx_head_(0),
          rx_tail_(0),
          rx_count_(0),
          tx_count_(0),
          active_peer_count_(0)
    {
        memset(rx_senders_, 0, sizeof(rx_senders_));
        memset(last_tx_peer_, 0, sizeof(last_tx_peer_));
        memset(active_peers_, 0, sizeof(active_peers_));
    }

    virtual ~FakeTransport() = default;

    virtual bool init() override {
        link_status_ = LINK_IDLE;
        return true;
    }

    virtual bool send_packet(const char* target_peer, const Packet& pkt) override {
        if (!target_peer || !is_peer_in_range(target_peer)) {
            return false;
        }

        // Record last transmitted packet for test assertions
        dtn_safe_strcpy(last_tx_peer_, target_peer, NODE_ID_MAX_LEN);
        last_tx_packet_ = pkt;
        tx_count_++;
        return true;
    }

    virtual bool receive_packet(char* out_source_peer, Packet& out_pkt) override {
        if (rx_count_ == 0) {
            return false;
        }

        // Dequeue from circular buffer
        out_pkt = rx_queue_[rx_head_];
        if (out_source_peer) {
            dtn_safe_strcpy(out_source_peer, rx_senders_[rx_head_], NODE_ID_MAX_LEN);
        }

        rx_head_ = (rx_head_ + 1) % FAKE_QUEUE_CAPACITY;
        rx_count_--;
        return true;
    }

    virtual bool is_peer_in_range(const char* peer_id) override {
        if (!peer_id) return false;
        for (size_t i = 0; i < active_peer_count_; ++i) {
            if (strcmp(active_peers_[i], peer_id) == 0) {
                return true;
            }
        }
        return false;
    }

    virtual LinkStatus get_link_status() const override {
        return link_status_;
    }

    virtual const char* get_driver_name() const override {
        return "FakeTransport (Test-Only)";
    }

    // ------------------------------------------------------------------------
    // Test Harness Control Methods
    // ------------------------------------------------------------------------

    void set_peer_in_range(const char* peer_id, bool in_range) {
        if (!peer_id) return;
        if (in_range) {
            if (is_peer_in_range(peer_id)) return;
            if (active_peer_count_ < FAKE_MAX_PEERS) {
                dtn_safe_strcpy(active_peers_[active_peer_count_], peer_id, NODE_ID_MAX_LEN);
                active_peer_count_++;
            }
        } else {
            for (size_t i = 0; i < active_peer_count_; ++i) {
                if (strcmp(active_peers_[i], peer_id) == 0) {
                    for (size_t j = i; j < active_peer_count_ - 1; ++j) {
                        memcpy(active_peers_[j], active_peers_[j + 1], NODE_ID_MAX_LEN);
                    }
                    active_peer_count_--;
                    break;
                }
            }
        }
    }

    bool inject_incoming_packet(const char* sender_peer, const Packet& pkt) {
        if (rx_count_ >= FAKE_QUEUE_CAPACITY) {
            return false;
        }
        rx_queue_[rx_tail_] = pkt;
        if (sender_peer) {
            dtn_safe_strcpy(rx_senders_[rx_tail_], sender_peer, NODE_ID_MAX_LEN);
        } else {
            rx_senders_[rx_tail_][0] = '\0';
        }
        rx_tail_ = (rx_tail_ + 1) % FAKE_QUEUE_CAPACITY;
        rx_count_++;
        return true;
    }

    uint32_t get_tx_count() const { return tx_count_; }
    const char* get_last_tx_peer() const { return last_tx_peer_; }
    const Packet& get_last_tx_packet() const { return last_tx_packet_; }

private:
    LinkStatus link_status_;

    Packet rx_queue_[FAKE_QUEUE_CAPACITY];
    char rx_senders_[FAKE_QUEUE_CAPACITY][NODE_ID_MAX_LEN];
    size_t rx_head_;
    size_t rx_tail_;
    size_t rx_count_;

    Packet last_tx_packet_;
    char last_tx_peer_[NODE_ID_MAX_LEN];
    uint32_t tx_count_;

    char active_peers_[FAKE_MAX_PEERS][NODE_ID_MAX_LEN];
    size_t active_peer_count_;
};

#endif // FAKE_TRANSPORT_H
