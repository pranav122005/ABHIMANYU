/**
 * @file esp_now_transport.cpp
 * @brief Implementation of ESP-NOW transport layer for autonomous DTN nodes.
 */

#include "esp_now_transport.h"
#include <string.h>
#include <stdio.h>

#ifdef ARDUINO
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <espnow.h>
#endif

// Static members
EspNowTransport* EspNowTransport::s_instance = nullptr;
volatile bool EspNowTransport::s_tx_complete = false;
volatile uint8_t EspNowTransport::s_tx_status = 0;

static const uint8_t BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

EspNowTransport::EspNowTransport()
    : link_status_(LINK_UNAVAILABLE),
      peer_mac_configured_(false),
      wifi_channel_(1),
      last_peer_seen_ms_(0),
      last_beacon_time_ms_(0),
      tx_success_count_(0),
      tx_fail_count_(0),
      rx_count_(0),
      rx_head_(0),
      rx_tail_(0),
      rx_occupancy_(0)
{
    memset(target_peer_id_, 0, sizeof(target_peer_id_));
    memset(local_mac_, 0, sizeof(local_mac_));
    memset(peer_mac_, 0, sizeof(peer_mac_));
    memset(rx_queue_, 0, sizeof(rx_queue_));
    s_instance = this;
}

bool EspNowTransport::register_espnow_peer(const uint8_t* mac) {
#ifdef ARDUINO
    if (!mac) return false;
    uint8_t zero_mac[6] = {0};
    if (memcmp(mac, zero_mac, 6) == 0) return false;

    // Check if peer already registered
    uint8_t mac_copy[6];
    memcpy(mac_copy, mac, 6);

    if (esp_now_is_peer_exist(mac_copy)) {
        return true;
    }

    int res = esp_now_add_peer(mac_copy, ESP_NOW_ROLE_COMBO, wifi_channel_, nullptr, 0);
    if (res == 0) {
        Serial.printf("[ESP-NOW] Peer registered: %02X:%02X:%02X:%02X:%02X:%02X (CH %d)\n",
            mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], wifi_channel_);
        return true;
    } else {
        Serial.printf("[ESP-NOW] Failed to register peer, error code: %d\n", res);
        return false;
    }
#else
    (void)mac;
    return true;
#endif
}

bool EspNowTransport::init() {
#ifdef ARDUINO
    link_status_ = LINK_DISCOVERING;
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    WiFi.macAddress(local_mac_);
    Serial.printf("[ESP-NOW] Initializing on WiFi Channel %d...\n", wifi_channel_);
    Serial.printf("[ESP-NOW] Local MAC Address: %02X:%02X:%02X:%02X:%02X:%02X\n",
        local_mac_[0], local_mac_[1], local_mac_[2], local_mac_[3], local_mac_[4], local_mac_[5]);

    if (esp_now_init() != 0) {
        Serial.println("[ESP-NOW] Critical: esp_now_init() failed!");
        link_status_ = LINK_ERROR;
        return false;
    }

    esp_now_set_self_role(ESP_NOW_ROLE_COMBO);
    esp_now_register_send_cb(EspNowTransport::on_data_sent_cb);
    esp_now_register_recv_cb(EspNowTransport::on_data_recv_cb);

    // Register broadcast address for peer discovery beaconing
    register_espnow_peer(BROADCAST_MAC);

    // Register designated peer MAC if already provided
    if (peer_mac_configured_) {
        register_espnow_peer(peer_mac_);
    }

    link_status_ = LINK_IDLE;
    Serial.println("[ESP-NOW] Driver ready (COMBO role, broadcast fallback active).");
    return true;
#else
    link_status_ = LINK_IDLE;
    local_mac_[0] = 0xAA; local_mac_[1] = 0xBB; local_mac_[2] = 0xCC;
    local_mac_[3] = 0x11; local_mac_[4] = 0x22; local_mac_[5] = 0x33;
    return true;
#endif
}

void EspNowTransport::set_peer_mac(const uint8_t* mac_addr) {
    if (!mac_addr) return;
    memcpy(peer_mac_, mac_addr, 6);
    peer_mac_configured_ = true;
    register_espnow_peer(peer_mac_);
}

void EspNowTransport::set_target_peer_id(const char* peer_id) {
    if (peer_id) {
        dtn_safe_strcpy(target_peer_id_, peer_id, NODE_ID_MAX_LEN);
    }
}

void EspNowTransport::get_local_mac(uint8_t* out_mac) const {
    if (out_mac) {
        memcpy(out_mac, local_mac_, 6);
    }
}

void EspNowTransport::get_local_mac_str(char* out_str, size_t max_len) const {
    if (!out_str || max_len < 18) return;
    snprintf(out_str, max_len, "%02X:%02X:%02X:%02X:%02X:%02X",
        local_mac_[0], local_mac_[1], local_mac_[2],
        local_mac_[3], local_mac_[4], local_mac_[5]);
}

void EspNowTransport::get_peer_mac(uint8_t* out_mac) const {
    if (out_mac) {
        memcpy(out_mac, peer_mac_, 6);
    }
}

void EspNowTransport::get_peer_mac_str(char* out_str, size_t max_len) const {
    if (!out_str || max_len < 18) return;
    if (peer_mac_configured_) {
        snprintf(out_str, max_len, "%02X:%02X:%02X:%02X:%02X:%02X",
            peer_mac_[0], peer_mac_[1], peer_mac_[2],
            peer_mac_[3], peer_mac_[4], peer_mac_[5]);
    } else {
        dtn_safe_strcpy(out_str, "AUTO_DISCOVER", max_len);
    }
}

bool EspNowTransport::send_packet(const char* target_peer, const Packet& pkt) {
#ifdef ARDUINO
    uint8_t wire_buf[ESPNOW_MAX_FRAME_BYTES];
    size_t wire_len = pkt.serialize(wire_buf, sizeof(wire_buf));

    if (wire_len == 0 || wire_len > ESPNOW_MAX_FRAME_BYTES) {
        Serial.printf("[ESP-NOW] Send rejected: wire length %u exceeds ESP-NOW max frame (%d)\n",
            static_cast<unsigned>(wire_len), ESPNOW_MAX_FRAME_BYTES);
        tx_fail_count_++;
        return false;
    }

    // Determine target MAC address: prefer explicit peer MAC, fallback to broadcast
    uint8_t send_mac[6];
    if (peer_mac_configured_) {
        memcpy(send_mac, peer_mac_, 6);
    } else {
        memcpy(send_mac, BROADCAST_MAC, 6);
    }

    link_status_ = LINK_TRANSMITTING;
    s_tx_complete = false;
    s_tx_status = 1;

    int ret = esp_now_send(send_mac, wire_buf, wire_len);
    if (ret != 0) {
        Serial.printf("[ESP-NOW] esp_now_send error: %d\n", ret);
        tx_fail_count_++;
        link_status_ = LINK_IDLE;
        return false;
    }

    // Wait for hardware MAC transmission confirmation (typically completes in 1-3 ms)
    uint32_t t0 = millis();
    while (!s_tx_complete && (millis() - t0 < 35)) {
        delay(1);
    }

    link_status_ = LINK_IDLE;

    if (s_tx_complete && s_tx_status == 0) {
        tx_success_count_++;
        last_peer_seen_ms_ = millis(); // Positive ACK confirms peer is in active contact
        Serial.printf("[ESP-NOW-TX] Packet '%s' to '%s' delivered & acknowledged (size: %u bytes)\n",
            pkt.header.packet_id, target_peer ? target_peer : "peer", static_cast<unsigned>(wire_len));
        return true;
    } else {
        tx_fail_count_++;
        Serial.printf("[ESP-NOW-TX] Packet '%s' to '%s' unacknowledged / timeout (status=%d)\n",
            pkt.header.packet_id, target_peer ? target_peer : "peer", s_tx_status);
        return false;
    }
#else
    // Host mock behavior
    (void)target_peer;
    uint8_t wire_buf[ESPNOW_MAX_FRAME_BYTES];
    size_t wire_len = pkt.serialize(wire_buf, sizeof(wire_buf));
    if (wire_len == 0 || wire_len > ESPNOW_MAX_FRAME_BYTES) {
        tx_fail_count_++;
        return false;
    }
    tx_success_count_++;
    return true;
#endif
}

bool EspNowTransport::receive_packet(char* out_source_peer, Packet& out_pkt) {
    if (rx_occupancy_ == 0) {
        return false;
    }

    RxQueueEntry entry = rx_queue_[rx_head_];
    rx_head_ = (rx_head_ + 1) % ESPNOW_RX_QUEUE_CAPACITY;
    rx_occupancy_--;

    // Validate and deserialize in main thread context
    bool ok = out_pkt.deserialize(entry.data, entry.len);
    if (!ok) {
        return false;
    }

    // Check if this is an internal discovery beacon frame
    if (strcmp(out_pkt.header.packet_id, "__beacon__") == 0) {
        return false; // Beacon handled internally; not passed up as a user packet
    }

    if (out_source_peer) {
        dtn_safe_strcpy(out_source_peer, out_pkt.header.source, NODE_ID_MAX_LEN);
    }

    rx_count_++;
    return true;
}

bool EspNowTransport::is_peer_in_range(const char* peer_id) {
    if (!peer_id) return false;
    // If target peer ID is set, check match
    if (target_peer_id_[0] != '\0' && strcmp(target_peer_id_, peer_id) != 0) {
        return false;
    }
#ifdef ARDUINO
    uint32_t now = millis();
    if (last_peer_seen_ms_ == 0) {
        return false; // No contact established yet
    }
    return (static_cast<int32_t>(now - last_peer_seen_ms_) < static_cast<int32_t>(PEER_CONTACT_TIMEOUT_MS));
#else
    return (last_peer_seen_ms_ != 0);
#endif
}

LinkStatus EspNowTransport::get_link_status() const {
    return link_status_;
}

const char* EspNowTransport::get_driver_name() const {
    return "ESP-NOW (2.4GHz Wi-Fi MAC)";
}

bool EspNowTransport::send_ping(uint32_t current_time_ms) {
    Packet beacon = Packet::create(
        "__beacon__",
        "dtn_node",
        "peer_node",
        0,
        1,
        current_time_ms,
        5000,
        nullptr,
        0
    );
    return send_packet(target_peer_id_, beacon);
}

void EspNowTransport::tick(uint32_t current_time_ms) {
#ifdef ARDUINO
    // Periodic beaconing to maintain contact awareness
    if (current_time_ms - last_beacon_time_ms_ >= BEACON_INTERVAL_MS) {
        send_ping(current_time_ms);
        last_beacon_time_ms_ = current_time_ms;
    }
#else
    (void)current_time_ms;
#endif
}

void EspNowTransport::on_data_sent_cb(uint8_t *mac_addr, uint8_t status) {
    (void)mac_addr;
    s_tx_status = status;
    s_tx_complete = true;
}

void EspNowTransport::on_data_recv_cb(uint8_t *mac_addr, uint8_t *data, uint8_t data_len) {
    if (!s_instance || !data || data_len < PACKET_WIRE_MIN_BYTES || data_len > ESPNOW_MAX_FRAME_BYTES) {
        return; // Validation failure or malformed payload
    }

#ifdef ARDUINO
    s_instance->last_peer_seen_ms_ = millis();

    // Auto-discover / verify peer MAC address
    if (!s_instance->peer_mac_configured_ && mac_addr) {
        memcpy(s_instance->peer_mac_, mac_addr, 6);
        s_instance->peer_mac_configured_ = true;
        s_instance->register_espnow_peer(s_instance->peer_mac_);
        Serial.printf("[ESP-NOW] Auto-discovered peer MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
            mac_addr[0], mac_addr[1], mac_addr[2], mac_addr[3], mac_addr[4], mac_addr[5]);
    }
#endif

    // Enqueue for processing in main loop (ring buffer)
    if (s_instance->rx_occupancy_ < ESPNOW_RX_QUEUE_CAPACITY) {
        RxQueueEntry& entry = s_instance->rx_queue_[s_instance->rx_tail_];
        memcpy(entry.data, data, data_len);
        entry.len = static_cast<uint16_t>(data_len);
        if (mac_addr) {
            memcpy(entry.sender_mac, mac_addr, 6);
        }
        s_instance->rx_tail_ = (s_instance->rx_tail_ + 1) % ESPNOW_RX_QUEUE_CAPACITY;
        s_instance->rx_occupancy_++;
    }
}

void EspNowTransport::mock_inject_rx(const uint8_t* mac, const uint8_t* data, uint8_t len) {
    on_data_recv_cb(const_cast<uint8_t*>(mac), const_cast<uint8_t*>(data), len);
}

void EspNowTransport::mock_set_peer_in_range(bool in_range) {
    last_peer_seen_ms_ = in_range ? 1000 : 0;
}

