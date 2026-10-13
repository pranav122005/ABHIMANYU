# ABHIMANYU DTN Integrated Demo System

Integrated demonstration linking the Streamlit Monitoring Dashboard and Flutter Messenger Client to the authentic decentralized DTN AI Routing Simulator.

## Architecture & Data Flow

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│  Flutter Messenger Client App   │       │   Streamlit Monitoring Web UI   │
│       (dtn-user-app)            │       │   (dtn-monitoring-dashboard)    │
└────────────────┬────────────────┘       └────────────────┬────────────────┘
                 │ HTTP Bearer                             │ HTTP REST
                 ▼                                         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│               FastAPI Single Source of Truth Service                      │
│                           (src/api/server.py)                             │
├───────────────────────────────────────────────────────────────────────────┤
│  • SQLite Thread-Safe Persistent Storage (data/demo_system.db)            │
│  • 10 Configurable Virtual DTN Nodes with PBKDF2 Password Authentication  │
│  • Message Lifecycle & Delivery Event State Machine                       │
├───────────────────────────────────────────────────────────────────────────┤
│                   DTN Integrated Service (src/api/service.py)             │
│  • Live DTNNode Buffer Simulation                                         │
│  • Autonomous Contact Link Evaluations                                    │
│  • Stage 5.2 Shallow Decision Tree Model Inference (Causal Features)      │
│  • Baseline Heuristics (Direct Delivery, Two-Hop Relay, Epidemic)        │
└───────────────────────────────────────────────────────────────────────────┘
```

## Running the Integrated Demonstration

### 1. Start the Shared FastAPI Backend Service
In PowerShell:
```powershell
cd D:\ABHIMANYU\dtn-ai-routing
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation (Swagger UI): `http://127.0.0.1:8000/docs`

### 2. Start the DTN Monitoring Dashboard
In a second PowerShell terminal:
```powershell
cd D:\ABHIMANYU\dtn-monitoring-dashboard
python -m streamlit run app.py
```
Dashboard Web URL: `http://localhost:8501`

### 3. Run the Flutter Messaging Application
In a third PowerShell terminal:
```powershell
cd D:\ABHIMANYU\dtn-user-app
flutter run -d windows
```

## Virtual Node Accounts (Defaults)
| Node ID | Display Name | Demo Password |
|---|---|---|
| `node-01` | Alpha Gateway | `pass-node-01` |
| `node-02` | Bravo Field Unit | `pass-node-02` |
| `node-03` | Charlie Relay | `pass-node-03` |
| `node-04` | Delta Scout | `pass-node-04` |
| `node-05` | Echo Depot | `pass-node-05` |
| `node-06` | Foxtrot Vehicle | `pass-node-06` |
| `node-07` | Golf Sensor Hub | `pass-node-07` |
| `node-08` | Hotel Outpost | `pass-node-08` |
| `node-09` | India Patrol | `pass-node-09` |
| `node-10` | Juliet HQ Base | `pass-node-10` |

*Note: Passwords and display names can be customized via the Dashboard Node Manager tab.*

## Hardware vs. Simulation Notice
The network topology, contact opportunities, and packet routing are evaluated using the discrete-event DTN simulator with verified causal features. This system is clearly labeled **MODE: SIMULATION** and is **NOT** represented as physical radio hardware telemetry.
