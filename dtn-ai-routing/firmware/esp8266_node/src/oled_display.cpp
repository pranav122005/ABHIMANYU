/**
 * @file oled_display.cpp
 * @brief SSD1306 128x64 I2C OLED display driver implementation.
 */

#include "oled_display.h"
#include <string.h>
#include <stdio.h>

#ifdef ARDUINO
#include <Arduino.h>
#include <Wire.h>
#endif

// Compact 5x7 ASCII font table (ASCII 32 ' ' to 126 '~')
static const uint8_t FONT_5X7[][5] = {
    {0x00, 0x00, 0x00, 0x00, 0x00}, // 32 ' '
    {0x00, 0x00, 0x5F, 0x00, 0x00}, // 33 '!'
    {0x00, 0x07, 0x00, 0x07, 0x00}, // 34 '"'
    {0x14, 0x7F, 0x14, 0x7F, 0x14}, // 35 '#'
    {0x24, 0x2A, 0x7F, 0x2A, 0x12}, // 36 '$'
    {0x23, 0x13, 0x08, 0x64, 0x62}, // 37 '%'
    {0x36, 0x49, 0x55, 0x22, 0x50}, // 38 '&'
    {0x00, 0x05, 0x03, 0x00, 0x00}, // 39 '''
    {0x00, 0x1C, 0x22, 0x41, 0x00}, // 40 '('
    {0x00, 0x41, 0x22, 0x1C, 0x00}, // 41 ')'
    {0x14, 0x08, 0x3E, 0x08, 0x14}, // 42 '*'
    {0x08, 0x08, 0x3E, 0x08, 0x08}, // 43 '+'
    {0x00, 0x50, 0x30, 0x00, 0x00}, // 44 ','
    {0x08, 0x08, 0x08, 0x08, 0x08}, // 45 '-'
    {0x00, 0x60, 0x60, 0x00, 0x00}, // 46 '.'
    {0x20, 0x10, 0x08, 0x04, 0x02}, // 47 '/'
    {0x3E, 0x51, 0x49, 0x45, 0x3E}, // 48 '0'
    {0x00, 0x42, 0x7F, 0x40, 0x00}, // 49 '1'
    {0x42, 0x61, 0x51, 0x49, 0x46}, // 50 '2'
    {0x21, 0x41, 0x45, 0x4B, 0x31}, // 51 '3'
    {0x18, 0x14, 0x12, 0x7F, 0x10}, // 52 '4'
    {0x27, 0x45, 0x45, 0x45, 0x39}, // 53 '5'
    {0x3C, 0x4A, 0x49, 0x49, 0x30}, // 54 '6'
    {0x01, 0x71, 0x09, 0x05, 0x03}, // 55 '7'
    {0x36, 0x49, 0x49, 0x49, 0x36}, // 56 '8'
    {0x06, 0x49, 0x49, 0x29, 0x1E}, // 57 '9'
    {0x00, 0x36, 0x36, 0x00, 0x00}, // 58 ':'
    {0x00, 0x56, 0x36, 0x00, 0x00}, // 59 ';'
    {0x08, 0x14, 0x22, 0x41, 0x00}, // 60 '<'
    {0x14, 0x14, 0x14, 0x14, 0x14}, // 61 '='
    {0x00, 0x41, 0x22, 0x14, 0x08}, // 62 '>'
    {0x02, 0x01, 0x51, 0x09, 0x06}, // 63 '?'
    {0x32, 0x49, 0x79, 0x41, 0x3E}, // 64 '@'
    {0x7E, 0x11, 0x11, 0x11, 0x7E}, // 65 'A'
    {0x7F, 0x49, 0x49, 0x49, 0x36}, // 66 'B'
    {0x3E, 0x41, 0x41, 0x41, 0x22}, // 67 'C'
    {0x7F, 0x41, 0x41, 0x22, 0x1C}, // 68 'D'
    {0x7F, 0x49, 0x49, 0x49, 0x41}, // 69 'E'
    {0x7F, 0x09, 0x09, 0x09, 0x01}, // 70 'F'
    {0x3E, 0x41, 0x49, 0x49, 0x7A}, // 71 'G'
    {0x7F, 0x08, 0x08, 0x08, 0x7F}, // 72 'H'
    {0x00, 0x41, 0x7F, 0x41, 0x00}, // 73 'I'
    {0x20, 0x40, 0x41, 0x3F, 0x01}, // 74 'J'
    {0x7F, 0x08, 0x14, 0x22, 0x41}, // 75 'K'
    {0x7F, 0x40, 0x40, 0x40, 0x40}, // 76 'L'
    {0x7F, 0x02, 0x0C, 0x02, 0x7F}, // 77 'M'
    {0x7F, 0x04, 0x08, 0x10, 0x7F}, // 78 'N'
    {0x3E, 0x41, 0x41, 0x41, 0x3E}, // 79 'O'
    {0x7F, 0x09, 0x09, 0x09, 0x06}, // 80 'P'
    {0x3E, 0x41, 0x51, 0x21, 0x5E}, // 81 'Q'
    {0x7F, 0x09, 0x19, 0x29, 0x46}, // 82 'R'
    {0x46, 0x49, 0x49, 0x49, 0x31}, // 83 'S'
    {0x01, 0x01, 0x7F, 0x01, 0x01}, // 84 'T'
    {0x3F, 0x40, 0x40, 0x40, 0x3F}, // 85 'U'
    {0x1F, 0x20, 0x40, 0x20, 0x1F}, // 86 'V'
    {0x3F, 0x40, 0x38, 0x40, 0x3F}, // 87 'W'
    {0x63, 0x14, 0x08, 0x14, 0x63}, // 88 'X'
    {0x07, 0x08, 0x70, 0x08, 0x07}, // 89 'Y'
    {0x61, 0x51, 0x49, 0x45, 0x43}, // 90 'Z'
    {0x00, 0x7F, 0x41, 0x41, 0x00}, // 91 '['
    {0x02, 0x04, 0x08, 0x10, 0x20}, // 92 '\'
    {0x00, 0x41, 0x41, 0x7F, 0x00}, // 93 ']'
    {0x04, 0x02, 0x01, 0x02, 0x04}, // 94 '^'
    {0x40, 0x40, 0x40, 0x40, 0x40}, // 95 '_'
    {0x00, 0x01, 0x02, 0x04, 0x00}, // 96 '`'
    {0x20, 0x54, 0x54, 0x54, 0x78}, // 97 'a'
    {0x7F, 0x48, 0x44, 0x44, 0x38}, // 98 'b'
    {0x38, 0x44, 0x44, 0x44, 0x20}, // 99 'c'
    {0x38, 0x44, 0x44, 0x48, 0x7F}, // 100 'd'
    {0x38, 0x54, 0x54, 0x54, 0x18}, // 101 'e'
    {0x08, 0x7E, 0x09, 0x01, 0x02}, // 102 'f'
    {0x0C, 0x52, 0x52, 0x52, 0x3E}, // 103 'g'
    {0x7F, 0x08, 0x04, 0x04, 0x78}, // 104 'h'
    {0x00, 0x44, 0x7D, 0x40, 0x00}, // 105 'i'
    {0x20, 0x40, 0x44, 0x3D, 0x00}, // 106 'j'
    {0x7F, 0x10, 0x28, 0x44, 0x00}, // 107 'k'
    {0x00, 0x41, 0x7F, 0x40, 0x00}, // 108 'l'
    {0x7C, 0x04, 0x18, 0x04, 0x78}, // 109 'm'
    {0x7C, 0x08, 0x04, 0x04, 0x78}, // 110 'n'
    {0x38, 0x44, 0x44, 0x44, 0x38}, // 111 'o'
    {0x7C, 0x14, 0x14, 0x14, 0x08}, // 112 'p'
    {0x08, 0x14, 0x14, 0x18, 0x7C}, // 113 'q'
    {0x7C, 0x08, 0x04, 0x04, 0x08}, // 114 'r'
    {0x48, 0x54, 0x54, 0x54, 0x20}, // 115 's'
    {0x04, 0x3F, 0x44, 0x40, 0x20}, // 116 't'
    {0x3C, 0x40, 0x40, 0x20, 0x7C}, // 117 'u'
    {0x1C, 0x20, 0x40, 0x20, 0x1C}, // 118 'v'
    {0x3C, 0x40, 0x30, 0x40, 0x3C}, // 119 'w'
    {0x44, 0x28, 0x10, 0x28, 0x44}, // 120 'x'
    {0x0C, 0x50, 0x50, 0x50, 0x3C}, // 121 'y'
    {0x44, 0x64, 0x54, 0x4C, 0x44}, // 122 'z'
    {0x00, 0x08, 0x36, 0x41, 0x00}, // 123 '{'
    {0x00, 0x00, 0x7F, 0x00, 0x00}, // 124 '|'
    {0x00, 0x41, 0x36, 0x08, 0x00}, // 125 '}'
    {0x08, 0x08, 0x2A, 0x1C, 0x08}  // 126 '~'
};

OledDisplay::OledDisplay()
    : is_present_(false),
      i2c_addr_(OLED_I2C_ADDR_PRIMARY),
      last_update_ms_(0)
{
    memset(line_buffers_, 0, sizeof(line_buffers_));
}

void OledDisplay::send_command(uint8_t cmd) {
#ifdef ARDUINO
    if (!is_present_) return;
    Wire.beginTransmission(i2c_addr_);
    Wire.write(0x00); // Co = 0, D/C# = 0
    Wire.write(cmd);
    Wire.endTransmission();
#else
    (void)cmd;
#endif
}

void OledDisplay::send_data(const uint8_t* data, size_t len) {
#ifdef ARDUINO
    if (!is_present_ || !data || len == 0) return;
    // Transmit in 16-byte chunks to fit Arduino Wire buffer
    size_t offset = 0;
    while (offset < len) {
        size_t chunk = (len - offset > 16) ? 16 : (len - offset);
        Wire.beginTransmission(i2c_addr_);
        Wire.write(0x40); // Co = 0, D/C# = 1 (Data)
        for (size_t i = 0; i < chunk; ++i) {
            Wire.write(data[offset + i]);
        }
        Wire.endTransmission();
        offset += chunk;
    }
#else
    (void)data;
    (void)len;
#endif
}

bool OledDisplay::init() {
#ifdef ARDUINO
    // SDA -> D2 (GPIO4), SCL -> D1 (GPIO5)
    Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
    Wire.setClock(400000); // 400 kHz Fast I2C

    // Probe primary I2C address 0x3C
    Wire.beginTransmission(OLED_I2C_ADDR_PRIMARY);
    if (Wire.endTransmission() == 0) {
        i2c_addr_ = OLED_I2C_ADDR_PRIMARY;
        is_present_ = true;
    } else {
        // Probe secondary address 0x3D
        Wire.beginTransmission(OLED_I2C_ADDR_SECONDARY);
        if (Wire.endTransmission() == 0) {
            i2c_addr_ = OLED_I2C_ADDR_SECONDARY;
            is_present_ = true;
        } else {
            is_present_ = false;
            Serial.println("[OLED] Warning: SSD1306 display not detected on I2C (SDA=D2, SCL=D1). Continuing headless.");
            return true; // Graceful degradation: do not abort firmware boot
        }
    }

    Serial.printf("[OLED] SSD1306 128x64 display detected at I2C address 0x%02X\n", i2c_addr_);

    // SSD1306 128x64 Initialization Sequence
    send_command(0xAE); // Display OFF
    send_command(0xD5); send_command(0x80); // Set Display Clock Divide Ratio
    send_command(0xA8); send_command(0x3F); // Set Multiplex Ratio (64 lines)
    send_command(0xD3); send_command(0x00); // Set Display Offset = 0
    send_command(0x40); // Set Start Line = 0
    send_command(0x8D); send_command(0x14); // Enable Charge Pump
    send_command(0x20); send_command(0x02); // Set Page Addressing Mode
    send_command(0xA1); // Set Segment Re-map (A0/A1)
    send_command(0xC8); // Set COM Output Scan Direction
    send_command(0xDA); send_command(0x12); // Set COM Pins Hardware Config
    send_command(0x81); send_command(0xCF); // Set Contrast Control
    send_command(0xD9); send_command(0xF1); // Set Pre-charge Period
    send_command(0xDB); send_command(0x40); // Set VCOMH Deselect Level
    send_command(0xA4); // Entire Display ON resume
    send_command(0xA6); // Set Normal Display (A6=Normal, A7=Inverse)
    send_command(0x2E); // Deactivate Scroll
    send_command(0xAF); // Display ON

    clear();
    print_line(0, "ABHIMANYU DTN NODE");
    print_line(1, "Booting...");
    return true;
#else
    is_present_ = true;
    return true;
#endif
}

void OledDisplay::clear() {
#ifdef ARDUINO
    if (!is_present_) return;
    uint8_t zero_chunk[16] = {0};
    for (uint8_t page = 0; page < 8; ++page) {
        send_command(0xB0 + page); // Set page start address
        send_command(0x00);        // Set lower column address
        send_command(0x10);        // Set higher column address
        for (uint8_t c = 0; c < 8; ++c) {
            send_data(zero_chunk, 16);
        }
    }
#endif
}

void OledDisplay::print_line(uint8_t line_idx, const char* text) {
    if (line_idx > 3 || !text) return;
    dtn_safe_strcpy(line_buffers_[line_idx], text, sizeof(line_buffers_[line_idx]));

#ifdef ARDUINO
    if (!is_present_) return;

    // Line 0 -> Page 0, Line 1 -> Page 2, Line 2 -> Page 4, Line 3 -> Page 6
    uint8_t page = line_idx * 2;
    send_command(0xB0 + page);
    send_command(0x00);
    send_command(0x10);

    size_t len = strlen(text);
    if (len > 21) len = 21; // Max 21 chars in 128 pixels (6 pixels per char)

    uint8_t char_buf[6];
    size_t col = 0;
    for (size_t i = 0; i < len; ++i) {
        char c = text[i];
        if (c >= 32 && c <= 126) {
            memcpy(char_buf, FONT_5X7[c - 32], 5);
        } else {
            memset(char_buf, 0, 5);
        }
        char_buf[5] = 0x00; // 1-pixel horizontal spacing
        send_data(char_buf, 6);
        col += 6;
    }

    // Fill remaining columns with blank space
    uint8_t blank[16] = {0};
    while (col < 128) {
        size_t step = (128 - col > 16) ? 16 : (128 - col);
        send_data(blank, step);
        col += step;
    }
#endif
}

void OledDisplay::update_status(const NodeStatus& status) {
    char l0[32], l1[32], l2[32], l3[32];

    // Line 0: Node ID and Link State
    const char* link_str = (status.link_status == LINK_IDLE) ? "ON" :
                           (status.link_status == LINK_TRANSMITTING) ? "TX" :
                           (status.link_status == LINK_RECEIVING) ? "RX" : "DISC";
    snprintf(l0, sizeof(l0), "[%.10s] Link:%.4s", status.node_id, link_str);

    // Line 1: Latest Transmit Info
    if (status.last_tx_id[0] != '\0') {
        snprintf(l1, sizeof(l1), "Tx:%.10s (%.4s)", status.last_tx_id, status.last_tx_status);
    } else {
        snprintf(l1, sizeof(l1), "Tx: None");
    }

    // Line 2: Latest Receive Info
    if (status.last_rx_id[0] != '\0') {
        if (status.last_rx_payload[0] != '\0') {
            snprintf(l2, sizeof(l2), "Rx:%.16s", status.last_rx_payload);
        } else {
            snprintf(l2, sizeof(l2), "Rx:%.16s", status.last_rx_id);
        }
    } else {
        snprintf(l2, sizeof(l2), "Rx: None");
    }

    // Line 3: DTN Buffer & AI Status
    snprintf(l3, sizeof(l3), "Buf:%u/%u AI:%.7s",
        static_cast<unsigned>(status.buffer_packet_count),
        static_cast<unsigned>(status.buffer_capacity),
        status.ai_decision_str[0] != '\0' ? status.ai_decision_str : status.current_action);

    print_line(0, l0);
    print_line(1, l1);
    print_line(2, l2);
    print_line(3, l3);
}

const char* OledDisplay::get_display_name() const {
    return is_present_ ? "SSD1306 OLED (128x64 I2C D1/D2)" : "SSD1306 (Not Detected / Headless)";
}

