/**
 * @file decision_tree_router.h
 * @brief Decentralized AI router integrating Stage 5.2 exported shallow decision tree.
 */

#ifndef DECISION_TREE_ROUTER_H
#define DECISION_TREE_ROUTER_H

#include "router_interface.h"

// Safely reuse the validated Stage 5.2 C++ export directly without duplication
#include "../../../models/stage5/decision_tree_esp8266.cpp"

class DecisionTreeRouter : public IRouter {
public:
    DecisionTreeRouter() = default;
    virtual ~DecisionTreeRouter() = default;

    virtual bool should_forward(const Packet& pkt, const EncounterContext& ctx) override {
        // Build strictly causal feature vector
        LocalDecisionFeatures feats = build_decision_features(pkt, ctx);

        // Direct destination encounters are always prioritized
        if (feats.peer_is_destination == 1) {
            return true;
        }

        // Evaluate Stage 5.2 shallow decision tree
        return decide_forwarding_decision_tree(feats);
    }

    virtual const char* get_policy_name() const override {
        return "decision_tree_esp8266";
    }
};

#endif // DECISION_TREE_ROUTER_H

