/**
 * @file esp_now_transport.h
 * @brief ESP-NOW radio transport driver for bidirectional communication between NodeMCU nodes.
 *
 * Implements ITransport over ESP8266 ESP-NOW. Supports 250-byte single-frame transfers,
 * hardware MAC-level acknowledgements, peer auto-discovery and pairing, and contact timeout tracking.
 */

#ifndef ESP_NOW_TRANSPORT_H
#define ESP_NOW_TRANSPORT_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "transport_interface.h"
#include "node_config.h"
#include "packet.h"

#define ESPNOW_MAX_FRAME_BYTES      250     ///< Physical maximum packet size for ESP-NOW
#define ESPNOW_RX_QUEUE_CAPACITY      4     ///< Queued received frames awaiting coordinator pickup
#define PEER_CONTACT_TIMEOUT_MS   12000     ///< Inactive duration before peer contact considered lost
#define BEACON_INTERVAL_MS         3000     ///< Discovery heartbeat broadcast cadence (ms)

class EspNowTransport : public ITransport {
public:
    EspNowTransport();
    virtual ~EspNowTransport() = default;

    /**
     * @brief Initializes Wi-Fi in Station mode and configures ESP-NOW combo role.
     */
    virtual bool init() override;

    /**
     * @brief Transmits a DTN packet to the target peer via ESP-NOW.
     * Validates frame length, initiates transmission, and waits for MAC delivery confirmation.
     * @return true if successfully delivered and acknowledged at MAC layer, false otherwise.
     */
    virtual bool send_packet(const char* target_peer, const Packet& pkt) override;

    /**
     * @brief Polls received queue populated by the ESP-NOW receive callback.
     */
    virtual bool receive_packet(char* out_source_peer, Packet& out_pkt) override;

    /**
     * @brief Evaluates whether peer is currently within radio contact range.
     */
    virtual bool is_peer_in_range(const char* peer_id) override;

    virtual LinkStatus get_link_status() const override;
    virtual const char* get_driver_name() const override;

    /**
     * @brief Non-blocking housekeeping: sends periodic discovery beacons and checks timeouts.
     */
    void tick(uint32_t current_time_ms);

    /**
     * @brief Sets explicit 6-byte MAC address for the designated peer node.
     */
    void set_peer_mac(const uint8_t* mac_addr);

    /**
     * @brief Registers designated peer ID (e.g. "node_b" or "node_a").
     */
    void set_target_peer_id(const char* peer_id);

    /**
     * @brief Retrieves local board's 6-byte Wi-Fi Station MAC address.
     */
    void get_local_mac(uint8_t* out_mac) const;

    /**
     * @brief Formats local MAC address as standard string (e.g. "AA:BB:CC:DD:EE:FF").
     */
    void get_local_mac_str(char* out_str, size_t max_len) const;

    /**
     * @brief Retrieves currently configured or auto-discovered peer MAC address.
     */
    void get_peer_mac(uint8_t* out_mac) const;
    void get_peer_mac_str(char* out_str, size_t max_len) const;

    bool has_peer_mac() const { return peer_mac_configured_; }
    const char* get_target_peer_id() const { return target_peer_id_; }

    /**
     * @brief Manually triggers a discovery/ping beacon transmission to the peer.
     */
    bool send_ping(uint32_t current_time_ms);

    // Callbacks registered with ESP-NOW core (static)
    static void on_data_sent_cb(uint8_t *mac_addr, uint8_t status);
    static void on_data_recv_cb(uint8_t *mac_addr, uint8_t *data, uint8_t data_len);

    // Host test mock helpers
    void mock_inject_rx(const uint8_t* mac, const uint8_t* data, uint8_t len);
    void mock_set_peer_in_range(bool in_range);

private:
    struct RxQueueEntry {
        uint8_t data[ESPNOW_MAX_FRAME_BYTES];
        uint16_t len;
        uint8_t sender_mac[6];
    };

    bool register_espnow_peer(const uint8_t* mac);

    LinkStatus link_status_;
    char target_peer_id_[NODE_ID_MAX_LEN];
    uint8_t local_mac_[6];
    uint8_t peer_mac_[6];
    bool peer_mac_configured_;
    uint8_t wifi_channel_;

    uint32_t last_peer_seen_ms_;
    uint32_t last_beacon_time_ms_;
    uint32_t tx_success_count_;
    uint32_t tx_fail_count_;
    uint32_t rx_count_;

    // Thread-safe / callback-safe ring buffer
    RxQueueEntry rx_queue_[ESPNOW_RX_QUEUE_CAPACITY];
    volatile size_t rx_head_;
    volatile size_t rx_tail_;
    volatile size_t rx_occupancy_;

    // Static pointer for C callback dispatch
    static EspNowTransport* s_instance;
    static volatile bool s_tx_complete;
    static volatile uint8_t s_tx_status;
};

#endif // ESP_NOW_TRANSPORT_H

