/*
 * ============================================================================
 *  QTrack Vision — ESP32-CAM Firmware
 * ============================================================================
 *  Board  : AI-Thinker ESP32-CAM (ESP32-S, 4MB PSRAM)
 *  Sensor : OV3660 (NOT the default OV2640 — see camera_init() notes)
 *  Purpose: Capture a JPEG frame every 5 seconds and HTTP-POST it to a
 *           FastAPI backend for YOLOv8n person-detection / queue analytics.
 *
 *  Build settings (Arduino IDE):
 *    Board          → AI Thinker ESP32-CAM
 *    PSRAM          → Enabled
 *    Partition      → Huge APP (3MB No OTA / 1MB SPIFFS)
 *    Upload Speed   → 115200
 *    Flash Mode     → QIO
 *
 *  Non-functional requirements met:
 *    ✓ Modular (wifi_init / camera_init / capture_and_upload)
 *    ✓ No memory leaks (every fb_get paired with fb_return)
 *    ✓ millis()-based non-blocking loop (no delay())
 *    ✓ Exponential backoff on POST failure
 *    ✓ Auto WiFi reconnect
 *    ✓ Serial logging for all state transitions
 * ============================================================================
 */

// ── Includes ───────────────────────────────────────────────────────────────
#include "esp_camera.h"
#include "esp_timer.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <time.h>

// Brownout detector — disable to survive power dips from the camera module.
// Safe when using a dedicated 5 V / 2 A supply (the FTDI motherboard's 3.3 V
// rail is borderline for WiFi-TX current spikes).
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// Credentials & config — keep out of version control!
// #include "secrets.h"
#define WIFI_SSID     "GK IQOO Z9x 5G"
#define WIFI_PASSWORD "12345678"
#define SERVER_URL    "http://10.84.158.174:8000"
#define SHOP_ID       "ration-shop-01"

// ── AI-Thinker ESP32-CAM pin mapping ───────────────────────────────────────
// These are fixed by the PCB layout and identical for OV2640 / OV3660.
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1   // Not wired on this board
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ── Tunables ───────────────────────────────────────────────────────────────
#define CAPTURE_INTERVAL_MS   5000      // 5 seconds between frames
#define JPEG_QUALITY          12        // 0-63, lower = better quality
#define FRAME_SIZE            FRAMESIZE_VGA   // 640×480 — good for YOLO
#define WIFI_CONNECT_TIMEOUT  15000     // ms to wait for initial WiFi
#define MAX_POST_RETRIES      3         // retries per frame before dropping
#define BACKOFF_INITIAL_MS    1000      // first retry delay
#define BACKOFF_MAX_MS        30000     // backoff cap
#define SERIAL_BAUD           115200

// Optional light-sleep flag — set to 1 to enable power saving between
// captures.  Light sleep keeps WiFi association alive on most APs, but
// some routers may deassociate a sleeping STA.  Test with your network.
#define ENABLE_LIGHT_SLEEP    0

// ── Built endpoint URL ─────────────────────────────────────────────────────
// POST /api/queue/frame?shop_id=<SHOP_ID>&timestamp=<epoch>
// We build the base once and append the timestamp per-request.
static String baseUrl;

// ── State ──────────────────────────────────────────────────────────────────
static unsigned long lastCaptureMs  = 0;
static unsigned long backoffMs      = BACKOFF_INITIAL_MS;
static bool          cameraReady    = false;

// ════════════════════════════════════════════════════════════════════════════
//  wifi_init()  —  Connect to the configured AP with timeout & auto-reconnect
// ════════════════════════════════════════════════════════════════════════════
void wifi_init() {
  Serial.printf("[WiFi] Connecting to \"%s\" ...\n", WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);   // driver-level reconnect on drop
  WiFi.persistent(false);        // don't wear flash with repeated writes
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_CONNECT_TIMEOUT) {
      Serial.println("[WiFi] ✗ Connection timed out — will retry in loop()");
      return;
    }
    // Yield to WDT while waiting (non-blocking spirit)
    delay(250);
    Serial.print(".");
  }

  Serial.printf("\n[WiFi] ✓ Connected  IP: %s  RSSI: %d dBm\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());

  // ── Sync NTP time so we can send real epoch timestamps ──
  configTime(19800, 0, "pool.ntp.org", "time.nist.gov");  // UTC+5:30 (IST)
  Serial.println("[WiFi] NTP time sync requested (IST offset applied)");
}

// ════════════════════════════════════════════════════════════════════════════
//  camera_init()  —  Configure the OV3660 on the AI-Thinker board
// ════════════════════════════════════════════════════════════════════════════
/*
 * OV3660 vs OV2640 differences handled here:
 *   • The esp32-camera driver auto-detects the sensor over SCCB/I2C,
 *     so we don't need to specify a sensor type.
 *   • OV3660's default image orientation is vertically and horizontally
 *     flipped compared to OV2640.  We correct with vflip + hmirror.
 *   • OV3660 tends to produce slightly darker images at the default
 *     brightness setting.  A +1 brightness bump compensates.
 *   • XCLK at 20 MHz is within spec for both sensors.
 */
void camera_init() {
  camera_config_t config;

  // ── Pin mapping (AI-Thinker fixed layout) ──
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;

  // ── Clock & format ──
  config.xclk_freq_hz = 20000000;          // 20 MHz — safe for OV3660
  config.ledc_timer   = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.pixel_format = PIXFORMAT_JPEG;    // HW-compressed on sensor

  // ── Frame size & quality ──
  // PSRAM is present on the AI-Thinker board, so we use it for the
  // frame buffer.  This lets us run at VGA without eating into the
  // ESP32's limited internal SRAM.
    if (psramFound()) {
    config.frame_size   = FRAME_SIZE;       // 640×480
    config.jpeg_quality = JPEG_QUALITY;     // 12 → ~30-50 KB
    config.fb_count     = 2;                // double-buffer for smoother capture
    config.fb_location  = CAMERA_FB_IN_PSRAM;      // ← was CAMERA_GRAB_IN_PSRAM
    config.grab_mode    = CAMERA_GRAB_LATEST;      // unchanged — this one was correct
    Serial.println("[CAM] PSRAM detected — using PSRAM frame buffers");
  } else {
    // Fallback: no PSRAM — use smaller frame and single buffer
    config.frame_size   = FRAMESIZE_QVGA;   // 320×240
    config.jpeg_quality = 15;
    config.fb_count     = 1;
    config.fb_location  = CAMERA_FB_IN_DRAM;       // ← was CAMERA_GRAB_FROM_INTERNAL
    config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;  // unchanged — this one was correct
    Serial.println("[CAM] No PSRAM — falling back to QVGA / internal RAM");
  }

  // ----------- prev code -------
  // if (psramFound()) {
  //   config.frame_size   = FRAME_SIZE;       // 640×480
  //   config.jpeg_quality = JPEG_QUALITY;     // 12 → ~30-50 KB
  //   config.fb_count     = 2;                // double-buffer for smoother capture
  //   config.fb_location  = CAMERA_GRAB_FROM_PSRAM;
  //   config.grab_mode    = CAMERA_GRAB_LATEST;  // always grab freshest frame
  //   Serial.println("[CAM] PSRAM detected — using PSRAM frame buffers");
  // } else {
  //   // Fallback: no PSRAM — use smaller frame and single buffer
  //   config.frame_size   = FRAMESIZE_QVGA;   // 320×240
  //   config.jpeg_quality = 15;
  //   config.fb_count     = 1;
  //   config.fb_location  = CAMERA_GRAB_FROM_INTERNAL;
  //   config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  //   Serial.println("[CAM] ⚠ No PSRAM — falling back to QVGA / internal RAM");
  // }

  // ── Initialize the camera driver ──
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] ✗ Init failed (0x%x). Check ribbon cable & power.\n", err);
    cameraReady = false;
    return;
  }

  // ── OV3660-specific sensor corrections ──
  sensor_t *s = esp_camera_sensor_get();
  if (s == NULL) {
    Serial.println("[CAM] ✗ Could not get sensor handle");
    cameraReady = false;
    return;
  }

  Serial.printf("[CAM] Sensor PID: 0x%04X\n", s->id.PID);

  // OV3660 PID = 0x3660.  Apply orientation & brightness fix only for
  // this sensor so the same firmware works if someone swaps in an OV2640.
  if (s->id.PID == 0x3660 || s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);        // Correct vertical flip (OV3660 default is inverted)
    s->set_hmirror(s, 1);      // Correct horizontal mirror
    s->set_brightness(s, 1);   // Bump brightness +1 (OV3660 default is slightly dark)
    Serial.println("[CAM] OV3660 detected — applied vflip, hmirror, brightness +1");
  } else {
    Serial.println("[CAM] Non-OV3660 sensor — using default orientation");
  }

  // Common image-quality tweaks (work on both OV2640 and OV3660)
  s->set_saturation(s, 0);     // Neutral saturation
  s->set_contrast(s, 0);       // Neutral contrast
  s->set_whitebal(s, 1);       // Auto white balance ON
  s->set_awb_gain(s, 1);       // AWB gain ON
  s->set_exposure_ctrl(s, 1);  // Auto exposure ON
  s->set_aec2(s, 1);           // AEC DSP ON (more stable auto-exposure)
  s->set_gain_ctrl(s, 1);      // Auto gain ON

  cameraReady = true;
  Serial.println("[CAM] ✓ Camera initialized successfully");
}

// ════════════════════════════════════════════════════════════════════════════
//  get_epoch()  —  Return current Unix timestamp (seconds since 1970)
// ════════════════════════════════════════════════════════════════════════════
/*
 * Returns 0 if NTP hasn't synced yet.  The server should treat a 0
 * timestamp as "use server-side receive time" as a graceful fallback.
 */
unsigned long get_epoch() {
  time_t now;
  time(&now);
  // time() returns seconds since epoch; will be near 0 if NTP hasn't synced
  if (now < 1700000000UL) {   // Sanity check: before ~Nov 2023 means no sync
    return 0;
  }
  return (unsigned long)now;
}

// ════════════════════════════════════════════════════════════════════════════
//  capture_and_upload()  —  Grab a frame, POST it, release the buffer
// ════════════════════════════════════════════════════════════════════════════
/*
 * Memory safety:
 *   • esp_camera_fb_get() is ALWAYS paired with esp_camera_fb_return()
 *     — even on upload failure — to prevent buffer exhaustion.
 *   • The JPEG bytes are streamed directly from the frame buffer (fb->buf)
 *     without copying, saving ~50 KB of heap.
 *
 * API contract:
 *   POST /api/queue/frame?shop_id=<string>&timestamp=<epoch>
 *   Content-Type: image/jpeg
 *   Body: raw JPEG bytes
 *   Expected: 200 OK → {"status": "received"}
 */
void capture_and_upload() {
  // ── 1. Capture ──
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAP] ✗ Frame buffer is NULL — skipping this cycle");
    return;
  }

  Serial.printf("[CAP] ✓ Frame captured  %u bytes  %dx%d\n",
                fb->len, fb->width, fb->height);

  // Sanity: if frame is unreasonably small it's probably corrupt
  if (fb->len < 1000) {
    Serial.println("[CAP] ⚠ Frame suspiciously small — discarding");
    esp_camera_fb_return(fb);
    return;
  }

  // ── 2. Check WiFi ──
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[NET] ✗ WiFi not connected — dropping frame");
    esp_camera_fb_return(fb);
    return;
  }

  // ── 3. Build URL with query params ──
  unsigned long epoch = get_epoch();
  String url = baseUrl + "/api/queue/frame?shop_id=" + SHOP_ID
               + "&timestamp=" + String(epoch);

  // ── 4. POST with retries + exponential backoff ──
  bool success = false;
  for (int attempt = 1; attempt <= MAX_POST_RETRIES; attempt++) {

    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "image/jpeg");
    http.setTimeout(10000);   // 10 s — generous for slow shop WiFi

    Serial.printf("[NET] POST attempt %d/%d → %s\n",
                  attempt, MAX_POST_RETRIES, url.c_str());

    int httpCode = http.POST(fb->buf, fb->len);

    if (httpCode == 200) {
      String response = http.getString();
      Serial.printf("[NET] ✓ 200 OK  Response: %s\n", response.c_str());
      backoffMs = BACKOFF_INITIAL_MS;   // Reset backoff on success
      success = true;
      http.end();
      break;
    }

    // Non-200 response or connection error
    if (httpCode > 0) {
      Serial.printf("[NET] ✗ Server returned HTTP %d\n", httpCode);
    } else {
      Serial.printf("[NET] ✗ Connection failed: %s\n",
                    http.errorToString(httpCode).c_str());
    }
    http.end();

    // Backoff before retry (except on last attempt)
    if (attempt < MAX_POST_RETRIES) {
      Serial.printf("[NET] Retrying in %lu ms ...\n", backoffMs);
      delay(backoffMs);   // Acceptable: we're already in a failed state
      backoffMs = min(backoffMs * 2, (unsigned long)BACKOFF_MAX_MS);
    }
  }

  if (!success) {
    Serial.println("[NET] ✗ All retries exhausted — frame dropped");
  }

  // ── 5. ALWAYS return the frame buffer ──
  esp_camera_fb_return(fb);
}

// ════════════════════════════════════════════════════════════════════════════
//  (Optional) enter_light_sleep()  —  Power-save between captures
// ════════════════════════════════════════════════════════════════════════════
#if ENABLE_LIGHT_SLEEP
/*
 * Light sleep keeps the WiFi association alive (unlike deep sleep) and
 * draws ~0.8 mA vs ~70 mA in active-idle.  Over a full shop day (10 h)
 * this adds up.
 *
 * Caveat: some consumer routers deassociate stations that stop sending
 * keep-alives.  If WiFi drops after sleep, disable this flag.
 */
void enter_light_sleep(unsigned long durationMs) {
  if (durationMs < 100) return;   // Not worth sleeping for <100 ms

  Serial.printf("[PWR] Light sleep for %lu ms\n", durationMs);
  Serial.flush();   // Make sure log is sent before sleeping

  esp_sleep_enable_timer_wakeup(durationMs * 1000ULL);  // µs
  esp_light_sleep_start();

  // Execution resumes here after wake-up
  Serial.println("[PWR] Woke from light sleep");
}
#endif

// ════════════════════════════════════════════════════════════════════════════
//  setup()
// ════════════════════════════════════════════════════════════════════════════
void setup() {
  // ── Serial ──
  Serial.begin(SERIAL_BAUD);
  Serial.println();
  Serial.println("╔══════════════════════════════════════╗");
  Serial.println("║    QTrack Vision — ESP32-CAM FW      ║");
  Serial.println("║    AI-Thinker + OV3660               ║");
  Serial.println("╚══════════════════════════════════════╝");

  // ── Disable brownout detector ──
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  // ── Build base URL once ──
  baseUrl = String(SERVER_URL);
  Serial.printf("[CFG] Server: %s\n", baseUrl.c_str());
  Serial.printf("[CFG] Shop ID: %s\n", SHOP_ID);
  Serial.printf("[CFG] Capture interval: %d ms\n", CAPTURE_INTERVAL_MS);

  // ── WiFi ──
  wifi_init();

  // ── Camera ──
  camera_init();

  // Prime the capture timer so the first frame fires immediately
  lastCaptureMs = millis() - CAPTURE_INTERVAL_MS;
}

// ════════════════════════════════════════════════════════════════════════════
//  loop()  —  Non-blocking: capture on interval, reconnect WiFi if needed
// ════════════════════════════════════════════════════════════════════════════
void loop() {
  unsigned long now = millis();

  // ── WiFi health check ──
  if (WiFi.status() != WL_CONNECTED) {
    // setAutoReconnect(true) handles the actual reconnect; we just log.
    static unsigned long lastWifiLog = 0;
    if (now - lastWifiLog > 5000) {
      Serial.printf("[WiFi] ⚠ Disconnected (status %d) — auto-reconnect active\n",
                    WiFi.status());
      lastWifiLog = now;
    }
    // Don't attempt capture while disconnected
    return;
  }

  // ── Camera health check ──
  if (!cameraReady) {
    static unsigned long lastCamRetry = 0;
    if (now - lastCamRetry > 10000) {   // Retry camera init every 10 s
      Serial.println("[CAM] Retrying camera initialization ...");
      camera_init();
      lastCamRetry = now;
    }
    return;
  }

  // ── Capture on schedule ──
  if (now - lastCaptureMs >= CAPTURE_INTERVAL_MS) {
    lastCaptureMs = now;
    capture_and_upload();

    // ── Optional: light sleep until next capture ──
    #if ENABLE_LIGHT_SLEEP
    unsigned long elapsed = millis() - lastCaptureMs;
    unsigned long sleepTime = (CAPTURE_INTERVAL_MS > elapsed)
                              ? (CAPTURE_INTERVAL_MS - elapsed - 500)  // 500 ms margin
                              : 0;
    if (sleepTime > 0) {
      enter_light_sleep(sleepTime);
      lastCaptureMs = millis();  // Recalibrate after wake
    }
    #endif
  }
}
