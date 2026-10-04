# QTrack Vision — Setup and Working Guide

This guide covers the current Windows development workflow: MySQL, FastAPI, the React dashboard, test image uploads, ESP32-CAM configuration, and how a frame becomes live analytics.

## Prerequisites

- MySQL Server running locally, with the `qtrack` database created.
- Python 3.10 or newer and Node.js/npm installed.
- The YOLO weights file at `server/yolov8n.pt` (already included in this checkout).
- For camera use: ESP32-CAM and a computer running the backend on the same reachable network.

## Configure MySQL

The backend reads `server/.env` and requires `DB_URL`; it will stop at startup if this setting is missing. Keep the file private and do not paste its password into source files or commit it.

For the local `qtrack` database and a MySQL `root` account, use this URL format in `server/.env` and replace the placeholder locally:

```dotenv
DB_URL=mysql+asyncmy://root:URL_ENCODED_PASSWORD@127.0.0.1:3306/qtrack?charset=utf8mb4
SERVICE_SECONDS_PER_PERSON=30
```

URL-encode special characters in the password. `SERVICE_SECONDS_PER_PERSON` is optional; its default is 30. See [GUIDE.md](GUIDE.md) for the schema and MySQL setup details.

On startup, FastAPI creates any missing tables from the SQLAlchemy models. It does not migrate existing tables or copy data from the old SQLite database. The current data tables are `cameras`, `tracking_sessions`, `frames`, `detections`, and `queue_updates`.

## Start the backend

Open a PowerShell terminal at the repository root:

```powershell
Set-Location .\server

# Create a Windows virtual environment if this project does not already have one.
py -m venv venv

.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Leave the terminal running. `0.0.0.0` lets another device on the LAN reach the backend; on the same computer, use `http://127.0.0.1:8000` or `http://localhost:8000`.

Check the backend from a second PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/
```

Expected response:

```json
{"status":"ok","service":"QTrack Vision"}
```

The API docs are at `http://127.0.0.1:8000/docs`.

## Start the React dashboard

Open another terminal at the repository root:

```powershell
Set-Location .\dashboard
npm install
npm run dev
```

Open the URL Vite prints, usually `http://localhost:5173`. Keep both the backend and Vite terminals running. The dashboard calls the backend at `http://localhost:8000`.

## Dashboard controls and metrics

The header has one dropdown: the **shop/camera selector**. Its options come from `GET /api/queue/shops`; each camera has a `shop_id`. Selecting an option switches the history request and the SSE connection to that camera. A shop appears after the backend has received a frame from it.

The header's Live/Connecting/Offline indicator is a connection status badge, not a dropdown. It describes the browser's Server-Sent Events connection to FastAPI.

The dashboard displays:

- **People in queue**: detections inside the configured queue ROI. If the ROI is unset, the backend currently counts every detected person and the dashboard labels this as “People detected · ROI unset”.
- **Estimated average remaining wait**: a rough estimate using `(queue_count - 1) × SERVICE_SECONDS_PER_PERSON / 2`. The default service interval is 30 seconds per person. This is not measured time spent waiting.
- **Moved forward**: number of matched ByteTrack IDs whose projected position advanced along the configured queue direction between the previous and current frame. The dashboard shows that direction setup is required until configured.
- **Queue change**: current queue count minus the count in the previous processed frame.
- **Entered queue / Left queue**: tracked people observed crossing into/out of the configured ROI. A person missing from a frame is not by itself treated as an exit.
- **ByteTrack people IDs**: currently detected tracker IDs, confidence, and ROI membership. IDs are local to a camera's tracking session; a backend restart starts a new session.
- **Trend chart**: the latest 60 saved frames, including queue count, detected people, people moved forward, and estimated wait time.
- **Camera feed**: latest annotated frame served by FastAPI from the server's `frames` directory.

The ROI and movement direction are per camera. After the camera sends at least one frame, configure them in MySQL. The polygon uses normalized `[x, y]` image coordinates from 0 to 1. Choose a direction vector that points toward the service counter. For a queue advancing upward in the image, for example:

```sql
UPDATE cameras
SET queue_roi = JSON_ARRAY(
      JSON_ARRAY(0.10, 0.15), JSON_ARRAY(0.90, 0.15),
      JSON_ARRAY(0.90, 0.95), JSON_ARRAY(0.10, 0.95)
    ),
    queue_direction_x = 0,
    queue_direction_y = -1
WHERE shop_id = 'ration-shop-01';
```

Replace the example polygon and direction with the actual camera view. Forward movement is image-space movement, not a distance in meters. Without a suitable fixed camera view and calibration, the wait and movement numbers are estimates.

## Send `frame1.jpg` and `frame2.jpg` from PowerShell

With the backend running, open a second terminal in the `server` directory. The images are one directory above it, so the paths start with `..\`:

```powershell
$shop = "manual-frame-test"
$base = "http://127.0.0.1:8000"
$t = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

curl.exe -X POST "$base/api/queue/frame?shop_id=$shop&timestamp=$t" `
  -H "Content-Type: image/jpeg" `
  --data-binary "@..\frame1.jpg"

Start-Sleep -Seconds 5
$t += 5

curl.exe -X POST "$base/api/queue/frame?shop_id=$shop&timestamp=$t" `
  -H "Content-Type: image/jpeg" `
  --data-binary "@..\frame2.jpg"
```

Use a distinct `shop_id` for each camera/test stream. `timestamp` is a Unix epoch timestamp in seconds; retries of the same capture should reuse its timestamp so FastAPI can deduplicate them. Run `frame1.jpg` before `frame2.jpg` to establish and then compare the baseline. The first frame has no transition; the second frame response includes `queue_update`.

From the repository root instead of `server`, use `@frame1.jpg` and `@frame2.jpg` as the `--data-binary` paths. A relative path is resolved from the terminal's current directory.

To fetch the saved records for this camera:

```powershell
Invoke-RestMethod "$base/api/queue/history?shop_id=$shop&hours=24&limit=60" |
  ConvertTo-Json -Depth 8
```

The transition includes `previous_frame_id`, `current_frame_id`, `previous_queue_count`, `current_queue_count`, `queue_count_delta`, `advanced_person_count`, entered/exited counts, and the corresponding tracker-ID lists.

## Configure and flash the ESP32-CAM

The current firmware settings are defined as macros near the top of `firmware/qtrack_cam/qtrack_cam.ino`:

```cpp
#define WIFI_SSID     "YourWiFiName"
#define WIFI_PASSWORD "YourWiFiPassword"
#define SERVER_URL    "http://192.168.1.100:8000"
#define SHOP_ID       "ration-shop-01"
```

Set the WiFi credentials, use the backend computer's LAN IPv4 address for `SERVER_URL` (not `localhost`), and set a unique `SHOP_ID`. Permit inbound connections to port 8000 on the backend computer's firewall. Do not put the MySQL URL or database password in firmware; the board only sends JPEGs to FastAPI.

Open `firmware/qtrack_cam/qtrack_cam.ino` in Arduino IDE, select the AI-Thinker ESP32-CAM board with PSRAM enabled, and flash it. The loop captures a JPEG about every five seconds and sends `POST /api/queue/frame?shop_id=...&timestamp=...` with `Content-Type: image/jpeg`. Watch the Serial Monitor at 115200 baud for connection and HTTP status messages.

## How a frame is processed

1. The ESP32-CAM captures JPEG bytes and posts them to FastAPI. The request body is the image; `shop_id` identifies the camera and `timestamp` identifies the capture time.
2. FastAPI validates the JPEG, saves it under `server/frames/<shop_id>/`, and runs YOLO person-class detection followed by ByteTrack.
3. The backend scopes tracker IDs to the camera's tracking session. It stores one frame row and one detection row per detected person. Bounding boxes and foot points are stored as normalized image coordinates.
4. If a queue polygon exists, the foot point determines whether the person is in the queue. If a direction vector also exists, the backend compares matched tracker positions with the prior processed frame and records advances above a small image-space movement threshold.
5. It calculates the queue-count change, entries/exits, and estimated wait. The frame, detections, and transition are committed to MySQL together. The first frame in a tracking session is the baseline and has no transition row.
6. After the commit, FastAPI publishes the update to `/api/queue/events?shop_id=...` using SSE. The React hook listens to that stream, merges the update into the chart and metrics, and refreshes the live-feed image.
7. When the dashboard opens or reconnects, it fetches `/api/queue/history` to restore saved readings. This also recovers events received while the browser was disconnected.

The JPEG files are stored on the backend filesystem; MySQL stores frame metadata, detection/tracker data, and analytics. ByteTrack IDs can switch when detections are missed or people overlap, especially with five-second sampling. A missing ID is therefore not automatically considered a person leaving the queue.

## Useful API routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/` | Backend health |
| `GET` | `/docs` | Interactive API documentation |
| `POST` | `/api/queue/frame?shop_id=<id>&timestamp=<epoch>` | Upload one raw JPEG |
| `GET` | `/api/queue/shops` | List registered shop/camera IDs |
| `GET` | `/api/queue/history?shop_id=<id>&hours=24&limit=60` | Read saved frame analytics |
| `GET` | `/api/queue/events?shop_id=<id>` | Subscribe to live updates using SSE |
| `GET` | `/frames/<shop_id>/latest.jpg` | View the latest annotated frame |

For database schema details and ROI examples, see [GUIDE.md](GUIDE.md). For common camera/network issues, see [TROUBLESHOOT.md](TROUBLESHOOT.md).
