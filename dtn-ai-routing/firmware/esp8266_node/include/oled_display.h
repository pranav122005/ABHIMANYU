/**
 * @file oled_display.h
 * @brief SSD1306 128x64 I2C OLED display driver for Node A.
 *
 * Implements IDisplay using standard Arduino Wire.h (I2C) on NodeMCU:
 *   SDA -> D2 (GPIO4)
 *   SCL -> D1 (GPIO5)
 *
 * Zero external library dependencies, page-streamed font rendering,
 * and graceful fallback if display hardware is detached.
 */

#ifndef OLED_DISPLAY_H
#define OLED_DISPLAY_H

#include "display_interface.h"

#define OLED_I2C_ADDR_PRIMARY   0x3C
#define OLED_I2C_ADDR_SECONDARY 0x3D
#define OLED_SDA_PIN               4    ///< NodeMCU D2 (GPIO4)
#define OLED_SCL_PIN               5    ///< NodeMCU D1 (GPIO5)

class OledDisplay : public IDisplay {
public:
    OledDisplay();
    virtual ~OledDisplay() = default;

    virtual bool init() override;
    virtual void update_status(const NodeStatus& status) override;
    virtual const char* get_display_name() const override;

    void clear();
    void print_line(uint8_t line_idx, const char* text);

    bool is_present() const { return is_present_; }

    // Diagnostic readouts for tests
    const char* get_line_buffer(uint8_t line) const {
        return (line < 4) ? line_buffers_[line] : "";
    }

private:
    void send_command(uint8_t cmd);
    void send_data(const uint8_t* data, size_t len);

    bool is_present_;
    uint8_t i2c_addr_;
    uint32_t last_update_ms_;
    char line_buffers_[4][32];
};

#endif // OLED_DISPLAY_H

