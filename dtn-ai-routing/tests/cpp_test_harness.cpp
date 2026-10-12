
// ============================================================================
// DTN AI Routing - Stage 5.2: Host C++ Model Parity Test Harness
// File: tests/cpp_test_harness.cpp
//
// Description:
//   Loads feature vectors from a CSV file, evaluates them using the standalone
//   exported C++ inference functions for Decision Tree and Logistic Regression,
//   and outputs the predictions in CSV format for automated parity verification.
// ============================================================================

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <cstdlib>

#include "../models/stage5/decision_tree_esp8266.cpp"
#include "../models/stage5/logistic_regression_esp8266.cpp"

struct CsvRecord {
    std::string test_id;
    LocalDecisionFeatures features;
};

std::vector<CsvRecord> load_csv(const std::string& filepath) {
    std::vector<CsvRecord> records;
    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "Error: Could not open input CSV file: " << filepath << std::endl;
        std::exit(1);
    }

    std::string line;
    // Skip header
    if (!std::getline(file, line)) {
        return records;
    }

    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::stringstream ss(line);
        std::string token;
        std::vector<std::string> tokens;

        while (std::getline(ss, token, ',')) {
            tokens.push_back(token);
        }

        if (tokens.size() < 12) {
            std::cerr << "Warning: Skipping malformed line: " << line << std::endl;
            continue;
        }

        CsvRecord rec;
        rec.test_id = tokens[0];
        rec.features.peer_is_destination = static_cast<uint8_t>(std::stoi(tokens[1]));
        rec.features.packet_size_bytes = static_cast<uint32_t>(std::stoul(tokens[2]));
        rec.features.packet_priority = static_cast<uint8_t>(std::stoi(tokens[3]));
        rec.features.remaining_ttl_ratio = std::stof(tokens[4]);
        rec.features.packet_hops = static_cast<uint16_t>(std::stoi(tokens[5]));
        rec.features.transfer_duration_ms = static_cast<uint32_t>(std::stoul(tokens[6]));
        rec.features.contact_elapsed_ms = static_cast<uint32_t>(std::stoul(tokens[7]));
        rec.features.estimated_remaining_contact_ms = static_cast<uint32_t>(std::stoul(tokens[8]));
        rec.features.estimated_transfer_fits = static_cast<uint8_t>(std::stoi(tokens[9]));
        rec.features.local_buffer_utilization = std::stof(tokens[10]);
        rec.features.peer_encounter_frequency = static_cast<uint16_t>(std::stoi(tokens[11]));

        records.push_back(rec);
    }

    return records;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <input_features.csv> [output_predictions.csv]" << std::endl;
        return 1;
    }

    std::string input_path = argv[1];
    std::string output_path = (argc >= 3) ? argv[2] : "";

    auto records = load_csv(input_path);

    std::ostream* out = &std::cout;
    std::ofstream out_file;
    if (!output_path.empty()) {
        out_file.open(output_path);
        if (!out_file.is_open()) {
            std::cerr << "Error: Could not open output file: " << output_path << std::endl;
            return 1;
        }
        out = &out_file;
    }

    *out << "test_id,cpp_dt_pred,cpp_lr_pred\n";
    for (const auto& rec : records) {
        bool dt_pred = decide_forwarding_decision_tree(rec.features);
        bool lr_pred = decide_forwarding_logistic_regression(rec.features);
        *out << rec.test_id << "," << (dt_pred ? 1 : 0) << "," << (lr_pred ? 1 : 0) << "\n";
    }

    return 0;
}

