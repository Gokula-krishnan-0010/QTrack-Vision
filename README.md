# QTrack Vision

> **AI-powered real-time queue monitoring for Indian ration shops, bank branches, and utility counters.**

QTrack Vision uses an ESP32-CAM to capture live footage, sends it to a FastAPI backend running YOLOv8n person detection with ByteTrack tracking, and streams analytics to a React dashboard via Server-Sent Events (SSE).

---

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Stage 1 — ESP32-CAM Firmware](#stage-1--esp32-cam-firmware)
  - [Hardware Required](#hardware-required)
  - [Arduino IDE Setup](#arduino-ide-setup)
  - [Configure Credentials](#configure-credentials)
  - [Flash the Firmware](#flash-the-firmware)
  - [Expected Serial Output](#expected-serial-output)
- [Stage 2 — FastAPI Backend](#stage-2--fastapi-backend)
  - [Install Python Dependencies](#install-python-dependencies)
  - [Run the Server](#run-the-server)
  - [Expected Startup Output](#expected-startup-output)
  - [Test with curl](#test-with-curl)
  - [API Endpoints](#api-endpoints)
- [Stage 3 — React Dashboard](#stage-3--react-dashboard)
  - [Install and Run](#install-and-run)
  - [Expected Output](#expected-dashboard-output)
- [Full Integration Test](#full-integration-test)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Tech Stack](#tech-stack)
- [License](#license)

---

## Architecture

```
┌─────────────────┐         HTTP POST (JPEG)        ┌─────────────────────┐
│                 │  ────────────────────────────►   │                     │
│   ESP32-CAM     │   every 5s, raw JPEG bytes       │   FastAPI Backend   │
│   (OV3660)      │   ?shop_id=...&timestamp=...     │   (Python 3.10+)   │
│                 │                                   │                     │
└─────────────────┘                                   │  ┌───────────────┐ │
                                                      │  │ YOLOv8n +     │ │
                                                      │  │ ByteTrack     │ │
                                                      │  │ Detection     │ │
                                                      │  └──────┬────────┘ │
                                                      │         │          │
                                                      │  ┌──────▼────────┐ │
                                                      │  │ Analytics     │ │
                                                      │  │ Engine        │ │
                                                      │  │ (queue len,   │ │
                                                      │  │  wait time,   │ │
                                                      │  │  exit rate)   │ │
                                                      │  └──────┬────────┘ │
                                                      │         │          │
                                                      │  ┌──────▼────────┐ │
                                                      │  │ SQLite DB     │ │
                                                      │  └──────┬────────┘ │
                                                      │         │          │
                                                      │         │ SSE      │
                                                      └─────────┼──────────┘
                                                                │
                                                     Server-Sent Events
                                                       (real-time push)
                                                                │
                                                      ┌─────────▼──────────┐
                                                      │                    │
                                                      │  React Dashboard   │
                                                      │  (Vite + Chart.js) │
                                                      │                    │
                                                      │  • Live feed       │
                                                      │  • Queue stats     │
                                                      │  • Trend charts    │
                                                      └────────────────────┘
```

**Data flow:**
1. **ESP32-CAM** captures a 640×480 JPEG frame every 5 seconds
2. Frame is HTTP POST'd to the FastAPI backend with `shop_id` and `timestamp`
3. **YOLOv8n** detects persons (class 0), **ByteTrack** maintains persistent IDs
4. **Analytics engine** computes queue length, estimated wait time, and exit rate
5. Results are persisted to **SQLite** and broadcast via **SSE**
6. **React dashboard** receives events and updates metrics, charts, and live feed in real-time

---

## Project Structure

```
QTrack Vision/
├── firmware/                          # ESP32-CAM firmware
│   ├── secrets.h                      # WiFi/server credentials (template)
│   └── qtrack_cam/
│       └── qtrack_cam.ino             # Arduino sketch (~290 lines)
│
├── server/                            # FastAPI backend
│   ├── requirements.txt               # Python dependencies
│   ├── main.py                        # App entry point + lifespan
│   ├── config.py                      # Environment-based settings
│   ├── database.py                    # Async SQLAlchemy engine
│   ├── models.py                      # ORM models (frame_records)
│   ├── bytetrack.yaml                 # Tracker configuration
│   ├── routers/
│   │   ├── frames.py                  # Frame ingestion + history APIs
│   │   └── events.py                  # SSE streaming endpoint
│   └── services/
│       ├── detector.py                # YOLOv8n + ByteTrack inference
│       └── analytics.py               # Queue metrics computation
│
├── dashboard/                         # React frontend (Vite)
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css                  # Dark glassmorphism design system
│       ├── hooks/
│       │   └── useQueueStream.js      # SSE hook with auto-reconnect
│       └── components/
│           ├── Header.jsx
│           ├── ConnectionBadge.jsx
│           ├── QueueStats.jsx
│           ├── LiveFeed.jsx
│           └── TrendChart.jsx
│
├── PLAN.md                            # Original project plan
├── TROUBLESHOOT.md                    # Debugging guide
└── README.md                          # ← You are here
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Arduino IDE** | 2.x | Flash ESP32-CAM firmware |
| **Python** | 3.10+ | Run FastAPI backend |
| **Node.js** | 18+ | Run React dashboard |
| **pip** | latest | Install Python packages |
| **npm** | 9+ | Install JS packages |
| **Git** | any | Clone the repository |

---

## Stage 1 — ESP32-CAM Firmware

### Hardware Required

| Component | Specification |
|-----------|--------------|
| Board | AI-Thinker ESP32-CAM |
| Chip | ESP32-S with 4MB PSRAM |
| Camera sensor | **OV3660** (not the default OV2640) |
| Programmer | FTDI adapter or ESP32-CAM-MB motherboard |
| Power | 5V / 2A supply (critical for WiFi stability) |

### Arduino IDE Setup

1. **Install ESP32 board package:**
   - Open Arduino IDE → **File → Preferences**
   - Add this URL to "Additional Boards Manager URLs":
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Go to **Tools → Board → Boards Manager** → Search "esp32" → Install **esp32 by Espressif Systems** (latest)

2. **Select board settings:**

   | Setting | Value |
   |---------|-------|
   | Board | `AI Thinker ESP32-CAM` |
   | PSRAM | `Enabled` |
   | Partition Scheme | `Huge APP (3MB No OTA / 1MB SPIFFS)` |
   | Upload Speed | `115200` |
   | Flash Mode | `QIO` |
   | Port | Your FTDI/USB port (e.g., `/dev/ttyUSB0`) |

### Configure Credentials

Edit `firmware/secrets.h` with your actual values:

```cpp
#define WIFI_SSID     "YourWiFiName"
#define WIFI_PASSWORD "YourWiFiPassword"
#define SERVER_URL    "http://192.168.1.100:8000"   // Your PC's local IP
#define SHOP_ID       "ration-shop-01"              // Unique per camera
```

> **⚠️ Never commit `secrets.h` to Git.** It's already in `.gitignore`.

> **💡 Finding your PC's IP:** Run `hostname -I` (Linux) or `ipconfig` (Windows) on the machine running the FastAPI server.

### Flash the Firmware

1. Connect the ESP32-CAM to your computer via FTDI/motherboard adapter
2. **Enter flash mode:** Hold the `IO0`/`GPIO0` button (or connect GPIO0 → GND) while pressing Reset
3. In Arduino IDE: **File → Open** → select `firmware/qtrack_cam/qtrack_cam.ino`
4. Click **Upload** (→ arrow button)
5. After upload completes: release GPIO0, press **Reset**
6. Open **Serial Monitor** at `115200` baud

### Expected Serial Output

```
╔══════════════════════════════════════╗
║    QTrack Vision — ESP32-CAM FW      ║
║    AI-Thinker + OV3660               ║
╚══════════════════════════════════════╝
[CFG] Server: http://192.168.1.100:8000
[CFG] Shop ID: ration-shop-01
[CFG] Capture interval: 5000 ms
[WiFi] Connecting to "YourWiFiName" ...
.....
[WiFi] ✓ Connected  IP: 192.168.1.42  RSSI: -45 dBm
[WiFi] NTP time sync requested (IST offset applied)
[CAM] PSRAM detected — using PSRAM frame buffers
[CAM] Sensor PID: 0x3660
[CAM] OV3660 detected — applied vflip, hmirror, brightness +1
[CAM] ✓ Camera initialized successfully
[CAP] ✓ Frame captured  38294 bytes  640x480
[NET] POST attempt 1/3 → http://192.168.1.100:8000/api/queue/frame?shop_id=ration-shop-01&timestamp=1723456789
[NET] ✓ 200 OK  Response: {"status":"received","person_count":5,"queue_length":5}
```

> **If you see `[CAM] ✗ Init failed`:** Check that the ribbon cable is firmly seated and you have a stable 5V supply. See [TROUBLESHOOT.md](TROUBLESHOOT.md) for more.

---

## Stage 2 — FastAPI Backend

### Install Python Dependencies

```bash
# Navigate to the server directory
cd server

# (Recommended) Create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

> **📦 First run note:** The `ultralytics` package will automatically download the `yolov8n.pt` model (~6 MB) on first startup. Ensure you have internet access.

### Run the Server

```bash
cd server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Expected Startup Output

```
10:30:01  qtrack.main           INFO   ╔══════════════════════════════════════╗
10:30:01  qtrack.main           INFO   ║   QTrack Vision — FastAPI Backend    ║
10:30:01  qtrack.main           INFO   ╚══════════════════════════════════════╝
10:30:01  qtrack.main           INFO   [DB] ✓ Database tables ready
10:30:03  qtrack.detector       INFO   [YOLO] Loading model: yolov8n.pt
10:30:04  qtrack.detector       INFO   [YOLO] ✓ Model loaded successfully
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
```

### Test with curl

You can test the frame ingestion endpoint without the ESP32-CAM using any JPEG image:

```bash
# Send a test JPEG frame
curl -X POST "http://localhost:8000/api/queue/frame?shop_id=test-shop&timestamp=0" \
     -H "Content-Type: image/jpeg" \
     --data-binary @/path/to/any/photo.jpg
```

**Expected response:**

```json
{
  "status": "received",
  "person_count": 3,
  "queue_length": 3
}
```

```bash
# Check server health
curl http://localhost:8000/
```

```json
{
  "status": "ok",
  "service": "QTrack Vision"
}
```

```bash
# List all shops that have sent frames
curl http://localhost:8000/api/queue/shops
```

```json
{
  "shops": ["test-shop", "ration-shop-01"]
}
```

```bash
# Get historical data (last 1 hour)
curl "http://localhost:8000/api/queue/history?shop_id=test-shop&hours=1"
```

```json
[
  {
    "id": 1,
    "shop_id": "test-shop",
    "timestamp": "2026-08-12T10:30:15+00:00",
    "person_count": 3,
    "queue_length": 3,
    "avg_wait_sec": 90.0,
    "exit_rate": 0.0,
    "created_at": "2026-08-12T10:30:15+00:00"
  }
]
```

```bash
# Test SSE stream (will block, waiting for events)
curl -N "http://localhost:8000/api/queue/events?shop_id=test-shop"
```

**Expected SSE output (when a frame arrives):**

```
event: queue_update
data: {"id":1,"shop_id":"test-shop","person_count":3,"queue_length":3,"avg_wait_sec":90.0,"exit_rate":0.0,"annotated_frame_url":"/frames/test-shop/latest.jpg"}
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/api/queue/frame?shop_id=<str>&timestamp=<epoch>` | Receive JPEG frame |
| `GET` | `/api/queue/events?shop_id=<str>` | SSE real-time stream |
| `GET` | `/api/queue/history?shop_id=<str>&hours=<int>` | Historical analytics |
| `GET` | `/api/queue/shops` | List all known shop IDs |
| `GET` | `/frames/{shop_id}/latest.jpg` | Latest annotated frame (static file) |

---

## Stage 3 — React Dashboard

### Install and Run

```bash
# Navigate to the dashboard directory
cd dashboard

# Install dependencies
npm install

# Start the development server
npm run dev
```

### Expected Dashboard Output

```
  VITE v8.x.x  ready in 450 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.1.100:5173/
  ➜  press h + enter to show help
```

Open `http://localhost:5173` in your browser. You should see:

**Dashboard Layout:**

```
┌──────────────────────────────────────────────────────────────┐
│  🔷 QTrack Vision                    [shop-selector ▼] 🟢 Live │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐│
│  │ 👥 12      │ │ 📊 8       │ │ ⏱️ 145.5s  │ │ 🚪 0.150   ││
│  │ Persons    │ │ Queue Len  │ │ Wait Time  │ │ Exit Rate  ││
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘│
│                                                              │
│  ┌──────────────────────┐  ┌───────────────────────────────┐ │
│  │ 📹 Camera Feed       │  │ 📈 Queue Trends               │ │
│  │                      │  │                               │ │
│  │   [Latest annotated  │  │   ╱╲    ╱╲                    │ │
│  │    camera frame      │  │  ╱  ╲╱╲╱  ╲    (Chart.js)    │ │
│  │    with YOLO boxes]  │  │ ╱         ╲                  │ │
│  │                      │  │                               │ │
│  └──────────────────────┘  └───────────────────────────────┘ │
│                                                              │
│                        QTrack Vision                         │
└──────────────────────────────────────────────────────────────┘
```

**Features:**
- 🟢 **Connection badge** — pulses green when SSE is live, amber when reconnecting, red when offline
- 📊 **Animated stat cards** — numbers count up smoothly with ease-out cubic easing
- 📹 **Live camera feed** — shows the latest annotated frame with YOLO bounding boxes
- 📈 **Trend chart** — dual-axis line chart (queue length + wait time over time)
- 🌙 **Dark glassmorphism UI** — frosted glass panels on deep navy background
- 📱 **Responsive** — adapts from desktop (4-column) to tablet (2-column) to mobile (1-column)

> **💡 Dashboard without backend:** The dashboard will show "Offline" and "Waiting for camera feed..." placeholders until the FastAPI backend is running. No errors — it reconnects automatically.

---

## Full Integration Test

Run all three components simultaneously for the full pipeline:

**Terminal 1 — Backend:**
```bash
cd server
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Dashboard:**
```bash
cd dashboard
npm run dev
```

**Terminal 3 (or ESP32-CAM) — Send test frames:**
```bash
# Simulate the ESP32-CAM with a test image (run every 5 seconds)
while true; do
  curl -s -X POST "http://localhost:8000/api/queue/frame?shop_id=test-shop&timestamp=$(date +%s)" \
       -H "Content-Type: image/jpeg" \
       --data-binary @/path/to/test-image.jpg
  echo ""
  sleep 5
done
```

**Expected full-pipeline behavior:**
1. `curl` sends a JPEG → backend logs `[YOLO] Detected N person(s)`
2. Backend broadcasts SSE event → dashboard connection badge turns 🟢 Live
3. Dashboard stat cards animate to new values
4. Camera feed panel shows the annotated frame (with bounding boxes)
5. Trend chart begins plotting a new data point every 5 seconds

---

## Configuration Reference

### Firmware (`firmware/secrets.h`)

| Macro | Description | Example |
|-------|-------------|---------|
| `WIFI_SSID` | WiFi network name | `"MyWiFi"` |
| `WIFI_PASSWORD` | WiFi password | `"password123"` |
| `SERVER_URL` | FastAPI server base URL | `"http://192.168.1.100:8000"` |
| `SHOP_ID` | Unique camera/shop identifier | `"ration-shop-01"` |

### Firmware tunables (`qtrack_cam.ino`)

| Define | Default | Description |
|--------|---------|-------------|
| `CAPTURE_INTERVAL_MS` | `5000` | Milliseconds between captures |
| `JPEG_QUALITY` | `12` | 0–63, lower = better quality |
| `FRAME_SIZE` | `FRAMESIZE_VGA` | 640×480 output resolution |
| `MAX_POST_RETRIES` | `3` | Retries per frame before dropping |
| `ENABLE_LIGHT_SLEEP` | `0` | Set to `1` for power saving |

### Backend (`server/.env` or environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `FRAME_DIR` | `./frames` | Where uploaded JPEGs are stored |
| `DB_URL` | `sqlite+aiosqlite:///./qtrack.db` | Database connection string |
| `YOLO_MODEL_PATH` | `yolov8n.pt` | Path to YOLO weights |
| `CONFIDENCE_THRESHOLD` | `0.4` | Min detection confidence |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed dashboard origins |

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `[CAM] ✗ Init failed (0x105)` | Loose ribbon cable or power issue | Reseat the ribbon cable; use a 5V/2A supply |
| `[WiFi] ✗ Connection timed out` | Wrong SSID/password or out of range | Double-check `secrets.h`; move closer to router |
| `[NET] ✗ Connection failed` | Backend not running or wrong IP | Start `uvicorn`; verify `SERVER_URL` in `secrets.h` |
| Dashboard shows "Offline" | Backend not running on port 8000 | Start the FastAPI server first |
| YOLO model download fails | No internet on first run | Manually download `yolov8n.pt` and place in `server/` |
| Image upside-down or mirrored | OV3660 sensor orientation | Adjust `set_vflip()` / `set_hmirror()` in `camera_init()` |
| Brownout reset loop | Insufficient power supply | Use 5V/2A dedicated supply; not USB-TTL 3.3V |

See [TROUBLESHOOT.md](TROUBLESHOOT.md) for detailed debugging steps.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Hardware** | AI-Thinker ESP32-CAM + OV3660 | Edge image capture |
| **Firmware** | Arduino (C++) | WiFi + camera + HTTP POST |
| **Backend** | FastAPI + Uvicorn | REST API + SSE streaming |
| **Detection** | YOLOv8n (Ultralytics) | Person detection |
| **Tracking** | ByteTrack | Persistent person IDs |
| **Analytics** | Custom Python | Queue length, wait time, exit rate |
| **Database** | SQLite (aiosqlite) | Frame metadata persistence |
| **Annotation** | Supervision (Roboflow) | Bounding box visualization |
| **Frontend** | React + Vite | Dashboard SPA |
| **Charts** | Chart.js + react-chartjs-2 | Trend visualization |
| **Streaming** | SSE (EventSource) | Real-time browser updates |



