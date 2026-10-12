/**
 * @file direct_delivery_router.h
 * @brief Non-AI baseline router that only forwards directly to the destination.
 */

#ifndef DIRECT_DELIVERY_ROUTER_H
#define DIRECT_DELIVERY_ROUTER_H

#include "router_interface.h"

class DirectDeliveryRouter : public IRouter {
public:
    DirectDeliveryRouter() = default;
    virtual ~DirectDeliveryRouter() = default;

    virtual bool should_forward(const Packet& pkt, const EncounterContext& ctx) override {
        return (strcmp(ctx.peer_id, pkt.header.destination) == 0);
    }

    virtual const char* get_policy_name() const override {
        return "direct_delivery";
    }
};

#endif // DIRECT_DELIVERY_ROUTER_H

