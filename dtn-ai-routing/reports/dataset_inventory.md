# DTN AI Routing — Dataset Inventory & Inspection Report

## Executive Summary
This document establishes the verified inventory, structural schemas, data quality metrics, and documented semantics for all real datasets downloaded for the DTN AI Routing System.

**No artificial labels or models have been created.** All reported properties reflect ground truth from source files and published author documentation.

---

## 1. Raw Dataset Folder Status

| Dataset Target | Expected Path | Status | Discovered Files |
| :--- | :--- | :--- | :--- |
| vannes | `data\raw\vannes` | Present | vbn_0.zip |
| haggle | `data\raw\haggle` | Present | cambridge-haggle-readme.txt, imote-traces-cambridge.tar.gz |
| salzburg | `data\raw\salzburg` | Present | SRFG-v1.csv |

---

## 2. Archive Inspection and Safe Extraction

All archives were pre-screened to verify member paths, enforce path traversal guards (`is_relative_to`), and prevent Zip Slip / TAR symlink attacks. Original archive integrity is preserved.

### Archive: `vbn_0.zip`
- **Format**: ZIP
- **Archive Size**: 15,117,015 bytes (14.42 MB)
- **Destination Directory**: `data\extracted\vannes`
- **Extraction Execution**: Unchanged (Skipped redundant extraction)
- **Member Count**: 2 items
- **Security Verification**: Path traversal validation passed. 0 errors reported.

**Archive Members Sample:**
```text
  vbn_0.dgs (64,820,183 bytes)
  README (2,672 bytes)
```

### Archive: `imote-traces-cambridge.tar.gz`
- **Format**: TAR.GZ
- **Archive Size**: 311,253 bytes (0.30 MB)
- **Destination Directory**: `data\extracted\haggle`
- **Extraction Execution**: Unchanged (Skipped redundant extraction)
- **Member Count**: 62 items
- **Security Verification**: Path traversal validation passed. 0 errors reported.

**Archive Members Sample:**
```text
  imote-traces-cambridge (0 bytes)
  imote-traces-cambridge/.DS_Store (6,148 bytes)
  imote-traces-cambridge/LR-2mins (0 bytes)
  imote-traces-cambridge/LR-2mins/37.dat (40,305 bytes)
  imote-traces-cambridge/LR-2mins/38.dat (101,791 bytes)
  imote-traces-cambridge/LR-2mins/39.dat (61,087 bytes)
  imote-traces-cambridge/LR-2mins/40.dat (96,547 bytes)
  imote-traces-cambridge/MAC3table (103,104 bytes)
  imote-traces-cambridge/README.txt (11,023 bytes)
  imote-traces-cambridge/SR-10mins-FixLocation (0 bytes)
  ... and 52 more members
```

---

## 3. Discovered Dataset Profiles

### 3.1 Vannes Bus Mobility Dataset (`vannes`)
- **Source & Provenance**: IRISA / CASA research team, Université de Bretagne-Sud (LEPTON platform). OpenStreetMap bus routes + Kicéo 2017 public transit timetables in Vannes, France.
- **Primary File**: `data/extracted/vannes/vbn_0.dgs` (extracted from `vbn_0.zip`)
- **Associated Documentation**: `data/extracted/vannes/README`
- **File Size**: 64,820,183 bytes (61.82 MB)
- **Total Rows / Events**: 1,964,512
- **Format**: GraphStream DGS004 (Dynamic Graph Stream)
- **Unique Nodes (Buses)**: 60 total buses (max 56 simultaneous active buses)
- **Scenario Time Span**: 51,240,000 ms (~14 hours 14 minutes, 05:25 AM to 19:39 PM)
- **Reference Coordinates**: Cartesian (x, y) in meters relative to reference GPS point (47.66515° N, -2.75828° W)
- **Documented Radio Range**: **No radio transmission assumed** in `vbn_0` baseline. Pairwise contacts require defining a communication range threshold (e.g., 50m, 100m, 250m).
- **Candidate Node Identifiers**: `line-xx-yy` (e.g. `line01-01` to `line11-04`)
- **Missing / Duplicate Records**: 0 missing values, 0 duplicate events.

### 3.2 Cambridge Haggle iMotes Dataset (`haggle`)
- **Source & Provenance**: CRAWDAD dataset `cambridge/haggle`, University of Cambridge, Intel Research, and LIP6 (Leguay et al., CHANTS 2006).
- **Primary Files**: 54 `.dat` contact trace files in 4 categories (`LR-2mins`, `SR-10mins-FixLocation`, `SR-10mins-Students`, `SR-6mins-FixLocation`), plus `MAC3table`.
- **Associated Documentation**: `cambridge-haggle-readme.txt` and `README.txt`
- **Total Contact Records**: 41,587 contact records across 54 observer devices.
- **Format**: Space-delimited ASCII contact tuples: `<seen_node_id> <contact_start_time> <contact_end_time>`
- **Unique Observer Nodes**: 54 (Nodes 1–36 students, 37–40 fixed long-range, 41–52 fixed short-range 10m, 53–54 fixed short-range 6m)
- **Unique Encountered Devices**: 11418 unique Bluetooth MAC IDs
- **Timestamp Format**: Unix epoch timestamp in seconds (UTC). Range: 1130493332 to 1132551949 (Oct 28, 2005 to Nov 21, 2005)
- **Location / Speed Telemetry**: Explicitly confirmed absent in README ('Do you have any location or speed data? The answer is no').
- **Duplicate Contacts**: Filtered and cataloged (identical observer-seen-interval tuples).

### 3.3 Salzburg LTE Drive Tests Dataset (`salzburg`)
- **Source & Provenance**: CRAWDAD repository `srfg/lte-4g-highway-drive-tests-salzburg`, Salzburg Research Forschungsgesellschaft (Farthofer, Herlich, Maier et al.).
- **Primary File**: `data/raw/salzburg/SRFG-v1.csv`
- **File Size**: 46,993,726 bytes (44.82 MB)
- **Total Rows / Observations**: 267,198 records across 22 columns.
- **Format**: Comma-Separated Values (CSV)
- **Geographic Coverage**: Austrian highway mobile drive test measurements.
- **Time Range**: 2018-01-15 16:43:52 to 2019-12-20 13:26:17 UTC across 501 distinct trips.
- **Observed Physical Layer & Telemetry Columns**:
  - `time`: UTC datetime (`YYYY-MM-DD HH:MM:SS`)
  - `lat`, `long`, `ele`: GPS coordinates (WGS84 degrees, elevation in meters)
  - `newpos`: Boolean position acquisition flag
  - `rsrq`: Reference Signal Received Quality in dB (3,371 nulls during handover/out-of-coverage)
  - `sinr`: Signal-to-Interference-plus-Noise Ratio in dB (2,973 nulls)
  - `signal`: Android signal strength level 0–5 (0 nulls)
  - `rssi`: Received Signal Strength Indicator in dBm (122,608 nulls where LTE report lacks RSSI)
  - `rsrp`: Reference Signal Received Power in dBm (3,371 nulls)
  - `cell_id`, `pci`: LTE E-UTRAN Cell Identifier and Physical Cell Identity
  - `technology`, `netmode`: Radio Access Technology ('LTE', mode 19)
  - `datarate`: Instantaneous throughput in bits/second (min: 0, max: 80+ Mbps)
  - `trip`, `file`, `line`: Session identifier and traceability markers
- **Duplicate Rows**: 0 duplicates.

---

## 4. Next Phase Recommendations
1. **Graph Derivation Pipeline for Vannes**: Implement a contact graph generator with parameterized radio range thresholds (e.g. 50m, 100m, 200m) to generate edge contact intervals from `vbn_0.dgs` coordinates.
2. **Contact Graph Cleaning for Haggle**: Filter spurious 1-second single-appearance MACs and corrupted MAC range (IDs 11168–11421) as specified in `cambridge-haggle-readme.txt`.
3. **Heterogeneous Cellular Offload Modeling with Salzburg**: Utilize the empirical `datarate`, `rsrp`, and `sinr` distributions from Salzburg to train/parameterize a cellular offload decision policy in heterogeneous DTN routing simulations.