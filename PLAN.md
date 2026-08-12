# QTrack Vision — ESP32-CAM Firmware Development

## Project context & stages
QTrack Vision is a real-time queue-monitoring system for Indian ration
shops, bank branches, and utility counters (built for Samsung Solve for
Tomorrow). Full pipeline:

1. [DONE] Idea validated, architecture locked: ESP32-CAM does capture +
   transmit ONLY — no on-device inference (RAM/compute insufficient for
   YOLO on this chip).
2. [DONE] Hardware acquired and bring-up tested: AI-Thinker ESP32-CAM
   (ESP32-S chip) + OV3660 sensor + FTDI motherboard. Basic snapshot
   capture already confirmed working.
3. [THIS TASK] Firmware: capture a frame every 5s, POST it to a FastAPI
   endpoint over WiFi.
4. [NEXT] FastAPI receives frame → runs YOLOv8n detection + ByteTrack for
   person counting/tracking → computes queue length + exit-rate wait time
   → writes to DB → pushes update via SSE to a React dashboard.

## Hardware
- Board: AI-Thinker ESP32-CAM
- Chip: ESP32-S, with PSRAM present
- Sensor: OV3660 — NOT the default OV2640 this board usually ships with.
  The esp32-camera library auto-detects sensor type over I2C, but OV3660
  has different default PLL clock and orientation behavior than OV2640.
  If the image comes out distorted, over/under-exposed, or mirrored,
  fix it via esp_camera_sensor_get() and correct s->set_vflip() /
  s->set_hmirror() / s->set_brightness() rather than assuming OV2640
  defaults are correct.
- Programming: via FTDI/motherboard adapter (GPIO0 to GND for flash mode)

## Task
Write complete, well-commented firmware (Arduino .ino, or PlatformIO if
you prefer — state which and why) that:

1. Connects to WiFi using credentials from a separate `secrets.h`
   (never hardcode SSID/password/server URL inline).
2. Initializes the OV3660 sensor correctly, applying any OV3660-specific
   correction noted above.
3. Captures a JPEG frame every 10 seconds using a non-blocking timer
   (millis()-based, not delay()) so WiFi and the watchdog stay responsive.
4. Sends the frame as an HTTP POST with the raw JPEG bytes as the body,
   and shop_id + timestamp (epoch or ISO8601) as either query params or
   custom headers — to http://<SERVER_IP>:8000/api/queue/frame
5. Handles WiFi disconnects with auto-reconnect, and retries a failed
   POST with backoff instead of hanging or crashing.
6. Logs connection state, capture success/failure, and POST response
   code over Serial for debugging.
7. Sets frame size/JPEG quality to target ~640x480 output, keeping
   payload under ~50KB — enough detail for YOLO, light enough for a
   shop's typical WiFi.
8. (Stretch goal, flag as optional) Use light sleep between captures to
   cut power draw without breaking the 5s cadence — this device runs
   unattended all day in a shop.

## Non-functional requirements
- Modular: separate functions for wifi_init(), camera_init(), and
  capture_and_upload() — not one monolithic loop().
- No memory leaks: every esp_camera_fb_get() must be paired with
  esp_camera_fb_return().
- Must survive prolonged unattended runtime without manual reset.

## API contract (for reference — flag if you'd design it differently)
POST /api/queue/frame?shop_id=<string>&timestamp=<epoch>
Content-Type: image/jpeg
Body: raw JPEG bytes
Expected response: 200 OK, JSON {"status": "received"}

## Deliverable
- Complete .ino (or PlatformIO src/main.cpp + platformio.ini)
- Separate secrets.h template
- Inline comments explaining any OV3660-specific config decisions
- Call out any assumptions about the API contract so I can adjust the
  FastAPI side to match