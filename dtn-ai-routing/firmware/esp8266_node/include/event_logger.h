/**
 * @file event_logger.h
 * @brief Non-blocking bounded ring buffer for local event logging.
 */

#ifndef EVENT_LOGGER_H
#define EVENT_LOGGER_H

#include <stdint.h>
#include <string.h>
#include "dtn_types.h"
#include "node_config.h"

struct LogEntry {
    uint32_t timestamp_ms;
    EventCode code;
    char detail[16];
};

class EventLogger {
public:
    EventLogger() : head_(0), count_(0) {
        memset(entries_, 0, sizeof(entries_));
    }

    void log(uint32_t timestamp_ms, EventCode code, const char* detail = nullptr) {
        entries_[head_].timestamp_ms = timestamp_ms;
        entries_[head_].code = code;
        if (detail) {
            dtn_safe_strcpy(entries_[head_].detail, detail, sizeof(entries_[head_].detail));
        } else {
            entries_[head_].detail[0] = '\0';
        }
        head_ = (head_ + 1) % MAX_EVENT_LOG_ENTRIES;
        if (count_ < MAX_EVENT_LOG_ENTRIES) {
            count_++;
        }
    }

    size_t count() const { return count_; }

    const LogEntry* get(size_t index) const {
        if (index >= count_) return nullptr;
        // Return chronologically from oldest
        size_t start = (count_ == MAX_EVENT_LOG_ENTRIES) ? head_ : 0;
        size_t actual_idx = (start + index) % MAX_EVENT_LOG_ENTRIES;
        return &entries_[actual_idx];
    }

private:
    LogEntry entries_[MAX_EVENT_LOG_ENTRIES];
    size_t head_;
    size_t count_;
};

#endif // EVENT_LOGGER_H
