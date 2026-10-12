/**
 * @file null_display.h
 * @brief Null / RAM-cached display implementation for headless nodes and unit testing.
 */

#ifndef NULL_DISPLAY_H
#define NULL_DISPLAY_H

#include <string.h>
#include "display_interface.h"

class NullDisplay : public IDisplay {
public:
    NullDisplay() {
        memset(&last_status_, 0, sizeof(last_status_));
        update_count_ = 0;
    }

    virtual ~NullDisplay() = default;

    virtual bool init() override {
        return true;
    }

    virtual void update_status(const NodeStatus& status) override {
        last_status_ = status;
        update_count_++;
    }

    virtual const char* get_display_name() const override {
        return "NullDisplay (Headless/Test)";
    }

    const NodeStatus& get_last_status() const { return last_status_; }
    uint32_t get_update_count() const { return update_count_; }

private:
    NodeStatus last_status_;
    uint32_t update_count_;
};

#endif // NULL_DISPLAY_H

