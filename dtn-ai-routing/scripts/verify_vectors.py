import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ai_decision_engine import DECISION_FEATURE_NAMES

model = joblib.load('models/stage5/decision_tree_model.joblib')

vectors = [
    # 1. Direct destination (peer_is_destination=1)
    {'name': 'Direct Destination (Fresh)', 'peer_is_destination': 1, 'packet_size_bytes': 10000, 'packet_priority': 2, 'remaining_ttl_ratio': 0.95, 'packet_hops': 0, 'transfer_duration_ms': 90, 'contact_elapsed_ms': 100, 'estimated_remaining_contact_ms': 5000, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.05, 'peer_encounter_frequency': 5},
    # 2. Direct destination (Low TTL)
    {'name': 'Direct Destination (Low TTL)', 'peer_is_destination': 1, 'packet_size_bytes': 10000, 'packet_priority': 1, 'remaining_ttl_ratio': 0.10, 'packet_hops': 2, 'transfer_duration_ms': 90, 'contact_elapsed_ms': 500, 'estimated_remaining_contact_ms': 2000, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.50, 'peer_encounter_frequency': 10},
    # 3. Promising relay: Fresh TTL ratio = 0.90, fits in contact
    {'name': 'Relay Encounter (Fresh TTL 0.90)', 'peer_is_destination': 0, 'packet_size_bytes': 10000, 'packet_priority': 2, 'remaining_ttl_ratio': 0.90, 'packet_hops': 0, 'transfer_duration_ms': 90, 'contact_elapsed_ms': 200, 'estimated_remaining_contact_ms': 5800, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.05, 'peer_encounter_frequency': 5},
    # 4. Promising relay: Very fresh TTL ratio = 0.98
    {'name': 'Relay Encounter (Very Fresh TTL 0.98)', 'peer_is_destination': 0, 'packet_size_bytes': 5000, 'packet_priority': 3, 'remaining_ttl_ratio': 0.98, 'packet_hops': 0, 'transfer_duration_ms': 70, 'contact_elapsed_ms': 50, 'estimated_remaining_contact_ms': 8000, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.01, 'peer_encounter_frequency': 8},
    # 5. Expired / Low TTL relay: ratio = 0.40 (should reject)
    {'name': 'Relay Encounter (Low TTL 0.40)', 'peer_is_destination': 0, 'packet_size_bytes': 10000, 'packet_priority': 1, 'remaining_ttl_ratio': 0.40, 'packet_hops': 1, 'transfer_duration_ms': 90, 'contact_elapsed_ms': 300, 'estimated_remaining_contact_ms': 4000, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.20, 'peer_encounter_frequency': 3},
    # 6. Intermediate TTL relay: ratio = 0.75 (should reject: tree requires > 0.87105 for relay forwarding)
    {'name': 'Relay Encounter (Intermediate TTL 0.75)', 'peer_is_destination': 0, 'packet_size_bytes': 10000, 'packet_priority': 2, 'remaining_ttl_ratio': 0.75, 'packet_hops': 0, 'transfer_duration_ms': 90, 'contact_elapsed_ms': 150, 'estimated_remaining_contact_ms': 3000, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.10, 'peer_encounter_frequency': 4},
    # 7. High buffer utilization relay: ratio = 0.60, buffer = 0.85
    {'name': 'Relay Encounter (High Buffer 0.85)', 'peer_is_destination': 0, 'packet_size_bytes': 20000, 'packet_priority': 1, 'remaining_ttl_ratio': 0.60, 'packet_hops': 1, 'transfer_duration_ms': 130, 'contact_elapsed_ms': 500, 'estimated_remaining_contact_ms': 2500, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.85, 'peer_encounter_frequency': 2},
    # 8. Boundary test: ratio = 0.88 (just above 0.87105 threshold -> forward)
    {'name': 'Relay Encounter (Boundary Above 0.88)', 'peer_is_destination': 0, 'packet_size_bytes': 10000, 'packet_priority': 2, 'remaining_ttl_ratio': 0.88, 'packet_hops': 0, 'transfer_duration_ms': 90, 'contact_elapsed_ms': 100, 'estimated_remaining_contact_ms': 4000, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.05, 'peer_encounter_frequency': 3},
    # 9. Boundary test: ratio = 0.86 (just below 0.87105 threshold -> reject)
    {'name': 'Relay Encounter (Boundary Below 0.86)', 'peer_is_destination': 0, 'packet_size_bytes': 10000, 'packet_priority': 2, 'remaining_ttl_ratio': 0.86, 'packet_hops': 0, 'transfer_duration_ms': 90, 'contact_elapsed_ms': 100, 'estimated_remaining_contact_ms': 4000, 'estimated_transfer_fits': 1, 'local_buffer_utilization': 0.05, 'peer_encounter_frequency': 3},
]

df = pd.DataFrame(vectors)
X = df[DECISION_FEATURE_NAMES].to_numpy(dtype=np.float32)
preds = model.predict(X).astype(int)

for i, row in enumerate(vectors):
    decision_str = "FORWARD (1)" if preds[i] == 1 else "HOLD (0)"
    print(f"[{i+1}] {row['name']}: Expected Decision = {decision_str}")
