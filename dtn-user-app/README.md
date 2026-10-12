# DTN Messenger

A polished, WhatsApp-inspired messaging application built with Flutter for Android and Windows, designed to operate over a decentralized Delay-Tolerant Network (DTN).

---

## 1. Overview & Architecture

DTN Messenger provides store-carry-and-forward messaging for intermittently connected environments. The app is a **client interface** and intentionally delegates all routing and forwarding decisions to the underlying DTN engine.

```
┌─────────────────────────────────────────────────────────────┐
│                    Flutter UI Layer                         │
│  Conversations • Chat (Text/Media) • Nearby • Outbox • Diag │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    State & Providers                        │
│   ConversationsProvider  •  ChatProvider  •  NearbyProvider │
│   OutboxProvider         •  SettingsProvider                │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
┌──────────────▼──────────────┐ ┌──────────────▼──────────────┐
│     SQLite Persistence      │ │     DTN Transport Client    │
│  (sqflite / ffi)            │ │  ┌───────────────────────┐  │
│  Messages • Conversations   │ │  │ DtnClient (interface) │  │
│  Outbox queues • Unread     │ │  └───────────┬───────────┘  │
└─────────────────────────────┘ │              │              │
                                │   ┌──────────┴──────────┐   │
                                │   ▼                     ▼   │
                                │ SimulatedDtnClient  Http... │
                                └─────────────────────────────┘
```

---

## 2. Supported Content & Delivery States

### Content Types
- **Text messages**
- **Images:** JPEG, PNG, WebP
- **Audio:** MP3 (with in-app scrubber playback)
- **Video:** MP4 (with in-app player controls)

### DTN Delivery States
- `LOCAL_QUEUED` — Persisted locally, waiting for an encounter with a peer or relay.
- `PEER_TRANSFERRED` — Accepted by an intermediate node or relay. *(Note: NOT considered final delivery)*.
- `DESTINATION_DELIVERED` — Confirmed received by the final recipient node.
- `FAILED` — Reported transfer or route failure.
- `EXPIRED` — TTL elapsed before reaching destination.

---

## 3. Real DTN Integration Contract

When connecting to a real physical gateway node (e.g., an ESP8266 or PC node running the DTN engine), the gateway must expose the following REST/WebSocket contract:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/message/submit` | Submit an outgoing bundle (JSON payload matching `Message.toJson()`) |
| `GET` | `/api/v1/message/receive?node={nodeId}` | Retrieve inbound bundles addressed to this node |
| `GET` | `/api/v1/message/{messageId}/status` | Query current delivery state of an outgoing bundle |
| `GET` | `/api/v1/peers` | Discovered compatible peers list |
| `POST` | `/api/v1/session/request` | Initiate a session/contact handshake with a peer |
| `DELETE` | `/api/v1/session/{nodeId}` | Close an active session |
| `WS` | `/api/v1/events` | Push delivery lifecycle events in real time |

### Missing Backend / Physical Radio Blockers
1. **HTTP/WebSocket Gateway Server:** The existing Python simulation repository (`dtn-ai-routing`) is an offline discrete-event research simulator. It does not currently run a persistent HTTP daemon exposing the above endpoints.
2. **Physical Radio Driver:** The target ESP8266 NodeMCU firmware requires an active radio driver (Wi-Fi SoftAP mesh or ESP-NOW) to bridge network packets to the Flutter app.
3. **mDNS / UDP Broadcast Discovery:** Local LAN discovery will require either an mDNS advertiser on the gateway or a UDP broadcast listener.

Until these components are deployed, the app operates in **Development Simulation Mode** using `SimulatedDtnClient`, which provides deterministic peers, realistic latency, and delivery progression for end-to-end testing.

---

## 4. How to Run & Build

### Prerequisites
- Flutter SDK 3.47+ with Dart 3.13+
- Windows 10/11 with Visual Studio Build Tools 2019+ (for Windows desktop)
- Android SDK with command-line tools (for Android APK)

### Run Locally (Windows Desktop)
```powershell
cd D:\ABHIMANYU\dtn-user-app
flutter run -d windows
```

### Run Locally (Chrome Web / Development)
```powershell
cd D:\ABHIMANYU\dtn-user-app
flutter run -d chrome
```

### Run Tests
```powershell
cd D:\ABHIMANYU\dtn-user-app
flutter test
```

### Build Windows Desktop Executable
```powershell
cd D:\ABHIMANYU\dtn-user-app
flutter build windows --release
```
*Output: `build/windows/x64/runner/Release/dtn_messenger.exe`*

### Build Android APK
*(Requires Android SDK licenses and command-line tools)*
```powershell
cd D:\ABHIMANYU\dtn-user-app
flutter build apk --release
```
*Output: `build/app/outputs/flutter-apk/app-release.apk`*

---

## 5. Security & Privacy

- **No Hardcoded Credentials:** Node IDs are generated deterministically or randomly via UUID v4.
- **Local Isolation:** Attachments are copied into the app's protected sandbox directory before hashing and queueing.
- **Idempotency:** Stable message UUIDs and SHA-256 digests prevent duplicate bundles across restarts and multi-hop transfers.
