# ABHIMANYU DTN — Complete Production Deployment & Operations Guide

This guide details the end-to-end production deployment, configuration, security hardening, and maintenance procedures for the three components of the ABHIMANYU Delay-Tolerant Network (DTN) system:

1. **Backend & DTN Engine**: `dtn-ai-routing` (FastAPI + DTN Engine + SQLite -> Target: Railway)
2. **Monitoring Dashboard**: `dtn-monitoring-dashboard` (Streamlit -> Target: Streamlit Community Cloud)
3. **DTN Messenger App**: `dtn-user-app` (Flutter -> Target: Windows Desktop & Android APK)

---

## 1. System Architecture & Topology

```
+-------------------------------------------------------------+
|                     Public Internet                         |
+-------------------------------------------------------------+
         │                                        │
         │ HTTPS / WSS                            │ HTTPS / API
         ▼                                        ▼
+───────────────────────────+         +───────────────────────────+
|   Monitoring Dashboard    |         |     DTN Messenger App     |
| (Streamlit Community Cloud|         | (Windows .exe / Android)  |
|      or Local Streamlit)  |         |                           |
+──────────────┬────────────+         +─────────────┬─────────────+
               │                                    │
               │ REST / JSON (Admin Token)          │ REST / Bearer Token
               ▼                                    ▼
       +───────────────────────────────────────────────────+
       |             FastAPI Backend (Railway)             |
       |  - Autonomous AI Decision-Tree Router (Stage 5.2) |
       |  - Contact Topology Engine & Temporal A* Routing  |
       |  - Store-Carry-Forward Buffer Management          |
       |  - Dynamic CORS Whitelist & Secure Auth Gate      |
       +─────────────────────────┬─────────────────────────+
                                 │
                                 ▼
       +───────────────────────────────────────────────────+
       |           Railway Persistent Volume (/data)       |
       |  - SQLite DB in WAL Mode (/data/demo_system.db)   |
       |  - Persists nodes, contacts, bundles, audit logs  |
       +───────────────────────────────────────────────────+
```

---

## 2. Component 1: FastAPI Backend Deployment (Railway)

### 2.1 Deployment Files
The repository `D:\ABHIMANYU\dtn-ai-routing` contains production-ready configuration:
- `Dockerfile`: Multi-stage Python 3.12-slim container with dynamic `$PORT` binding to `0.0.0.0` and `/data` mount point.
- `requirements.txt`: Locked dependencies (`fastapi`, `uvicorn[standard]`, `pydantic`, `scikit-learn`, `joblib`, `numpy`, `pandas`, `pytest`).
- `.dockerignore`: Excludes local SQLite databases, research notebooks, and temporary files.
- `.env.example`: Reference template for production environment variables.

### 2.2 Deploying via Railway Web Dashboard
1. Log in to [Railway.app](https://railway.app/).
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select the repository: `pranav122005/ABHIMANYU` (branch: `main` or path `dtn-ai-routing`).
4. Under **Settings** -> **Build & Deploy**:
   - Ensure the build type is set to **Dockerfile**.
5. Under **Volumes**:
   - Click **Add Volume**.
   - Mount path: `/data`.
   - Size: 1 GB (or as required for long-term bundle and telemetry retention).
6. Under **Variables**, add the following required environment variables:

| Variable Name | Required | Description | Example / Production Value |
|---|---|---|---|
| `DTN_ENV` | Yes | Runtime environment flag | `production` |
| `DTN_ADMIN_TOKEN` | Yes | High-entropy secret token (min 16 chars) for admin operations | `e.g. 32-hex characters from secrets.token_hex(16)` |
| `DTN_DB_PATH` | Yes | Path to persistent SQLite storage on volume | `/data/demo_system.db` |
| `DTN_CORS_ORIGINS` | Yes | Comma-separated allowed frontend origins | `https://your-dashboard.streamlit.app` |

> **Security Note:** In production (`DTN_ENV=production`), the backend validates `DTN_ADMIN_TOKEN` at startup. If the token is empty or shorter than 16 characters, the server safely aborts to prevent unauthorized exposure. Plain demonstration passwords are automatically wiped and suppressed from all API responses.

### 2.3 Generating a Secure Admin Token
Run this in PowerShell or Python to generate a secure 32-character token:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2.4 Verifying the Backend Deployment
Once deployed, verify the public endpoint:
```bash
# 1. Health check (public)
curl https://<your-railway-domain>.up.railway.app/api/health

# Expected response:
# {"status":"healthy","service":"ABHIMANYU DTN Integrated API","environment":"production","virtual_time_ms":1000000,"nodes_loaded":10,"ai_model_loaded":true}

# 2. Verify admin authentication
curl -H "X-Admin-Token: <your-admin-token>" https://<your-railway-domain>.up.railway.app/api/metrics
```

---

## 3. Component 2: Monitoring Dashboard Deployment (Streamlit Cloud)

### 3.1 Overview
The monitoring dashboard (`D:\ABHIMANYU\dtn-monitoring-dashboard`) provides real-time topology visualization, node buffer inspection, contact management, and route tracing.

### 3.2 Deploying to Streamlit Community Cloud
1. Push `dtn-monitoring-dashboard` to your GitHub account (see Git section below).
2. Go to [share.streamlit.io](https://share.streamlit.io/) and click **Create app**.
3. Select repository: `<your-github-username>/dtn-monitoring-dashboard`.
4. Branch: `main` (or `master`).
5. Main file path: `app.py`.
6. Under **Advanced Settings** -> **Secrets**, paste your production configuration:
```toml
DTN_API_BASE_URL = "https://<your-railway-domain>.up.railway.app"
DTN_ADMIN_TOKEN = "<your-admin-token>"
```
7. Click **Deploy!**.

### 3.3 Dashboard Features in Production
- **Live Mode by Default**: Loads nodes and dynamic topology directly from the Railway backend.
- **Admin Secret Header**: Passes `X-Admin-Token` to backend endpoints so administrators can toggle contacts, step virtual clocks, and inspect global routing decisions.
- **Credential Protection**: Node password modification masks input (`type="password"`) and does not expose or require existing passwords.

---

## 4. Component 3: Flutter DTN Messenger App Build & Distribution

The client application (`D:\ABHIMANYU\dtn-user-app`) is a WhatsApp-inspired cross-platform DTN communicator.

### 4.1 Production Configuration via Dart Define
Compile the app with the `--dart-define` flag to embed the Railway production API URL directly into the compiled binary:
```bash
--dart-define=DTN_API_BASE_URL=https://<your-railway-domain>.up.railway.app
```

### 4.2 Building the Windows Desktop Release Package
1. Open PowerShell and navigate to the project directory:
   ```powershell
   cd D:\ABHIMANYU\dtn-user-app
   ```
2. Build the optimized 64-bit release executable:
   ```powershell
   flutter build windows --release --dart-define=DTN_API_BASE_URL=https://<your-railway-domain>.up.railway.app
   ```
3. **Artifact Location**:
   ```
   D:\ABHIMANYU\dtn-user-app\build\windows\x64\runner\Release\
   ```
4. **Distribution Steps**:
   - The `Release` folder contains `dtn_messenger.exe` along with necessary Flutter and Windows runtime DLLs (`flutter_windows.dll`, `data/` folder).
   - Zip the entire contents of `build\windows\x64\runner\Release\` into `DTN_Messenger_Windows_x64.zip` for user distribution.
   - Users can unzip and immediately launch `dtn_messenger.exe` without installing developer SDKs.

### 4.3 Building the Android Release APK
1. Ensure the Android toolchain has network access to dl.google.com and Maven repositories to download required AndroidX libraries.
2. Build the release APK:
   ```bash
   flutter build apk --release --dart-define=DTN_API_BASE_URL=https://<your-railway-domain>.up.railway.app
   ```
3. **Artifact Location**:
   ```
   D:\ABHIMANYU\dtn-user-app\build\app\outputs\flutter-apk\app-release.apk
   ```
4. Distribute `app-release.apk` directly via download channel, internal MDM, or GitHub Releases.

---

## 5. Security & Authorization Architecture

### 5.1 Role Boundaries
| Operation / Endpoint | Public | Node Bearer Token | Admin Secret Token |
|---|:---:|:---:|:---:|
| `GET /api/health` | Yes | Yes | Yes |
| `GET /api/nodes` | Safe fields only | Safe fields only | Full details (dev only) |
| `POST /api/nodes/{id}/connect` | Yes (requires password) | Yes | Yes |
| `POST /api/messages` | No | Own identity only (`source_id == actor`) | Any node |
| `GET /api/messages/{id}` | No | Sender or Recipient only | Yes |
| `GET /api/messages/{id}/route` | No | Sender or Recipient only | Yes |
| `GET /api/nodes/{id}/inbox` | No | Node owner only | Yes |
| `GET /api/nodes/{id}/outbox` | No | Node owner only | Yes |
| `PATCH /api/nodes/{id}` | No | No | Yes |
| `POST /api/contacts` | No | No | Yes |
| `POST /api/simulation/*` | No | No | Yes |
| `GET /api/messages` (all) | No | No | Yes |
| `GET /api/events` (all) | No | No | Yes |

### 5.2 Credential Protection
- Passwords are encrypted using PBKDF2 with SHA-256 (100,000 iterations and 16-byte random salt).
- Constant-time comparison (`secrets.compare_digest`) prevents timing attacks.
- In `production` mode, plaintext demonstration passwords are never stored in the database or transmitted over the network.

---

## 6. Persistence, Backup, and Recovery

### 6.1 SQLite Database Operations
The backend database is stored at `DTN_DB_PATH` (`/data/demo_system.db` on Railway).
- The database operates in SQLite **WAL mode** (`PRAGMA journal_mode=WAL;`), ensuring non-blocking reads and concurrent write transactions.
- Foreign key constraints are enforced (`PRAGMA foreign_keys=ON;`).

### 6.2 Volume Backup Procedure
To back up the live database from Railway:
1. Using the Railway CLI:
   ```bash
   railway volume download /data/demo_system.db ./backup_demo_system_$(date +%Y%m%d).db
   ```
2. Alternatively, create volume snapshots directly from the Railway project dashboard under **Volumes** -> **Backups**.

### 6.3 State Reset
To clear active message queues and event logs while preserving node identities, topology, and trained AI models, call:
```bash
curl -X POST -H "X-Admin-Token: <your-admin-token>" https://<your-railway-domain>.up.railway.app/api/simulation/reset
```

---

## 7. Verification Checklist

- [x] Backend test suite passes 100% (83/83 unit, integration, parity, and security tests).
- [x] Dashboard test suite passes 100% (8/8 tests).
- [x] Flutter app unit, widget, and integration tests pass 100% (64/64 tests).
- [x] Flutter code analysis clean (`flutter analyze`: 0 warnings, 0 errors).
- [x] Windows 64-bit release binary compiled (`dtn_messenger.exe`).
- [x] Railway production configuration created (`Dockerfile`, `requirements.txt`, `.dockerignore`, `.env.example`).
- [x] Authorization boundaries, spoofing defenses, and CORS whitelists implemented and verified.
