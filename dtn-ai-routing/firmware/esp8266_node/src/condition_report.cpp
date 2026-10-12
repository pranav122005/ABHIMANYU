/**
 * @file condition_report.cpp
 * @brief Implementation of ReportQueue bounded FIFO.
 */

#include "condition_report.h"
#include <string.h>

ReportQueue::ReportQueue()
    : head_(0),
      tail_(0),
      count_(0)
{
    clear();
}

void ReportQueue::clear() {
    head_ = 0;
    tail_ = 0;
    count_ = 0;
    memset(queue_, 0, sizeof(queue_));
}

bool ReportQueue::enqueue(const NodeConditionReport& report) {
    if (is_full()) {
        return false;
    }
    queue_[tail_] = report;
    tail_ = (tail_ + 1) % MAX_QUEUED_REPORTS;
    count_++;
    return true;
}

bool ReportQueue::dequeue(NodeConditionReport& out_report) {
    if (is_empty()) {
        return false;
    }
    out_report = queue_[head_];
    head_ = (head_ + 1) % MAX_QUEUED_REPORTS;
    count_--;
    return true;
}

const NodeConditionReport* ReportQueue::peek() const {
    if (is_empty()) {
        return nullptr;
    }
    return &queue_[head_];
}

