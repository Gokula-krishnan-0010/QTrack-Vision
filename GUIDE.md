# QTrack Vision — MySQL schema and setup guide

This guide defines the database foundation for the QTrack Vision flow: an ESP32-CAM uploads one JPEG about every five seconds; FastAPI runs person detection and tracking; the backend compares each frame with the previous frame from the same camera; and it stores analytics and movement changes in MySQL.

## Current project state

The current server defaults to SQLite (`server/qtrack.db`) and has a `frame_records` table. Its detector already calls Ultralytics YOLO tracking with ByteTrack, but queue analytics currently use total detected people as queue length and keep previous IDs only in process memory. MySQL is not enabled by this schema guide alone; the server configuration and persistence code must later be changed to use it.

## Data model

- `cameras`: one record per ESP32-CAM/shop, including its queue direction and optional queue-region settings.
- `tracking_sessions`: a tracker continuity period for a camera. Start a new session after a backend restart or tracker reset so reused ByteTrack IDs cannot be mistaken for old people.
- `frames`: one row per received image, with a monotonically increasing per-camera sequence number, capture/receive timestamps, image path, detection count, queue count, and link to the preceding frame.
- `detections`: one row per person detection, including the ByteTrack ID scoped to the tracking session and the bounding box. Normalized coordinates make image dimensions changes easier to handle.
- `queue_updates`: one row per analyzed frame transition. Stores counts and measurable changes from the prior frame. Use this as the dashboard/event history source and publish only after its transaction commits.

The frame row and its detections and queue update should be committed in one transaction. The first frame in a session has no previous frame and therefore has no frame-to-frame movement result. Store UTC timestamps; convert to local time for display.

## MySQL schema

Run this in MySQL 8.0 or newer using an administrative account. The application user should have access only to this project database.

```sql
CREATE DATABASE qtrack
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'qtrack_app'@'localhost' IDENTIFIED BY 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON qtrack.* TO 'qtrack_app'@'localhost';
FLUSH PRIVILEGES;

USE qtrack;

CREATE TABLE cameras (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  shop_id VARCHAR(100) NOT NULL UNIQUE,
  display_name VARCHAR(150) NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  -- Optional normalized queue polygon, e.g. [[0.1,0.2],[0.8,0.2],...]
  queue_roi JSON NULL,
  -- Unit vector for the direction people advance along the queue (image coordinates).
  queue_direction_x DECIMAL(8,6) NULL,
  queue_direction_y DECIMAL(8,6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

CREATE TABLE tracking_sessions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  camera_id BIGINT UNSIGNED NOT NULL,
  started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  ended_at DATETIME(6) NULL,
  reason VARCHAR(64) NOT NULL DEFAULT 'startup',
  CONSTRAINT fk_tracking_sessions_camera FOREIGN KEY (camera_id)
    REFERENCES cameras(id) ON DELETE RESTRICT,
  INDEX ix_tracking_sessions_camera_started (camera_id, started_at)
) ENGINE=InnoDB;

CREATE TABLE frames (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  camera_id BIGINT UNSIGNED NOT NULL,
  tracking_session_id BIGINT UNSIGNED NOT NULL,
  sequence_no BIGINT UNSIGNED NOT NULL,
  device_frame_id VARCHAR(100) NULL,
  captured_at DATETIME(6) NOT NULL,
  received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  image_path VARCHAR(512) NULL,
  image_width SMALLINT UNSIGNED NULL,
  image_height SMALLINT UNSIGNED NULL,
  person_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  queue_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  previous_frame_id BIGINT UNSIGNED NULL,
  processing_status ENUM('processed','failed') NOT NULL DEFAULT 'processed',
  error_message VARCHAR(500) NULL,
  CONSTRAINT fk_frames_camera FOREIGN KEY (camera_id)
    REFERENCES cameras(id) ON DELETE RESTRICT,
  CONSTRAINT fk_frames_session FOREIGN KEY (tracking_session_id)
    REFERENCES tracking_sessions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_frames_previous FOREIGN KEY (previous_frame_id)
    REFERENCES frames(id) ON DELETE SET NULL,
  UNIQUE KEY uq_frames_camera_sequence (camera_id, sequence_no),
  UNIQUE KEY uq_frames_camera_device_id (camera_id, device_frame_id),
  INDEX ix_frames_camera_captured (camera_id, captured_at),
  INDEX ix_frames_session_sequence (tracking_session_id, sequence_no)
) ENGINE=InnoDB;

CREATE TABLE detections (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  frame_id BIGINT UNSIGNED NOT NULL,
  tracker_id BIGINT UNSIGNED NULL,
  class_id SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  confidence DECIMAL(6,5) NOT NULL,
  -- Bounding box in normalized image coordinates, each value in [0,1].
  x1 DECIMAL(8,7) NOT NULL,
  y1 DECIMAL(8,7) NOT NULL,
  x2 DECIMAL(8,7) NOT NULL,
  y2 DECIMAL(8,7) NOT NULL,
  center_x DECIMAL(8,7) NOT NULL,
  center_y DECIMAL(8,7) NOT NULL,
  in_queue BOOLEAN NOT NULL DEFAULT FALSE,
  queue_position DECIMAL(10,6) NULL,
  CONSTRAINT fk_detections_frame FOREIGN KEY (frame_id)
    REFERENCES frames(id) ON DELETE CASCADE,
  INDEX ix_detections_frame (frame_id),
  INDEX ix_detections_tracker (tracker_id)
) ENGINE=InnoDB;

CREATE TABLE queue_updates (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  camera_id BIGINT UNSIGNED NOT NULL,
  tracking_session_id BIGINT UNSIGNED NOT NULL,
  previous_frame_id BIGINT UNSIGNED NOT NULL,
  current_frame_id BIGINT UNSIGNED NOT NULL,
  measured_at DATETIME(6) NOT NULL,
  elapsed_seconds DECIMAL(10,3) NOT NULL,
  previous_queue_count SMALLINT UNSIGNED NOT NULL,
  current_queue_count SMALLINT UNSIGNED NOT NULL,
  queue_count_delta SMALLINT NOT NULL,
  -- Distinct matched tracks whose projected queue position advanced.
  advanced_person_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  -- Entries/exits here mean crossing the configured queue ROI boundary,
  -- not merely a tracker ID appearing/disappearing in one sparse frame.
  entered_queue_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  exited_queue_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  advanced_tracker_ids JSON NULL,
  entered_tracker_ids JSON NULL,
  exited_tracker_ids JSON NULL,
  avg_wait_seconds DECIMAL(10,2) NULL,
  exit_rate DECIMAL(8,5) NULL,
  CONSTRAINT fk_queue_updates_camera FOREIGN KEY (camera_id)
    REFERENCES cameras(id) ON DELETE RESTRICT,
  CONSTRAINT fk_queue_updates_session FOREIGN KEY (tracking_session_id)
    REFERENCES tracking_sessions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_queue_updates_previous FOREIGN KEY (previous_frame_id)
    REFERENCES frames(id) ON DELETE CASCADE,
  CONSTRAINT fk_queue_updates_current FOREIGN KEY (current_frame_id)
    REFERENCES frames(id) ON DELETE CASCADE,
  UNIQUE KEY uq_queue_updates_current_frame (current_frame_id),
  INDEX ix_queue_updates_camera_time (camera_id, measured_at)
) ENGINE=InnoDB;
```

`device_frame_id` is optional if firmware does not send a stable frame identifier. The unique key permits multiple `NULL` values in MySQL; use a generated firmware sequence for safe retries and deduplication. If the application uses a different MySQL collation or MySQL-compatible server, adjust the database collation as needed.

## How to calculate frame-to-frame queue progression

1. Serialize inference per camera, so two uploads cannot update the same camera's tracker/history out of order.
2. Use YOLO person detections and ByteTrack IDs. Scope every tracker ID to a `tracking_session_id`; an ID such as `17` is not globally unique.
3. Determine whether each person's foot point (usually the bottom-center of the box) is inside the configured queue ROI. Counting every person in the image as a queue member is not a queue measurement.
4. Project each in-queue foot point onto a configured queue direction/axis and save its queue position. Compare matching tracker IDs from the previous frame to the current frame; count an advance only when their projected position changes toward the service point beyond a small noise threshold.
5. Compare ROI membership across the pair to identify entry and exit. A track missing from one image is not proof the person exited; the camera can miss detections, and a five-second gap is long for tracking. Consider requiring a boundary crossing or repeated absence before recording an exit.
6. Insert the current frame, detections, and one queue update referencing both frame IDs in the same MySQL transaction. Commit, then publish that persisted update to SSE/dashboard clients. On the first frame after session start, save detections/current count without a progression row.
7. Keep ByteTrack's frame buffer in units of frames, not seconds. At one processed frame every five seconds, a buffer of 60 frames spans up to five minutes, but gaps, missed uploads, and ID switches still affect continuity.

The resulting measurements are image-space estimates. For physical movement in centimeters/meters or robust waiting-time estimates, calibrate the camera and queue geometry; track IDs alone cannot provide those measurements.

## Set up MySQL locally

1. Install and start MySQL Server 8.0+ (for example, MySQL Community Server). Confirm the service is running and that the FastAPI host can reach it.
2. Open a MySQL client as an administrator:

   ```powershell
   mysql -u root -p
   ```

3. Run the SQL above. Replace the example password. For a remote deployment, create the application user for the backend host rather than `localhost`, restrict network access to the backend machine, and require TLS.
4. Verify access:

   ```sql
   SHOW DATABASES LIKE 'qtrack';
   USE qtrack;
   SHOW TABLES;
   ```

5. Install an async MySQL driver in the server virtual environment. For SQLAlchemy's `mysql+asyncmy` URL, install `asyncmy`:

   ```powershell
   cd server
   .\venv\Scripts\Activate.ps1
   pip install asyncmy
   ```

   The project currently uses an environment-managed SQLAlchemy URL, so retain SQLAlchemy's async engine/session pattern when switching its configuration. Add the chosen driver to `server/requirements.txt` as part of that code change.

6. Set `DB_URL` in a local `server/.env` file (keep secrets out of source control):

   ```dotenv
   DB_URL=mysql+asyncmy://qtrack_app:URL_ENCODED_PASSWORD@127.0.0.1:3306/qtrack?charset=utf8mb4
   ```

   URL-encode special characters in the password. Do not put the database password in firmware; the ESP32-CAM sends images to FastAPI, and only FastAPI connects to MySQL.

7. Before pointing the backend at this schema, implement corresponding SQLAlchemy models/migrations and update `server/config.py`, database initialization, and frame ingestion. `Base.metadata.create_all()` does not migrate existing SQLite data or safely evolve production tables. Back up `server/qtrack.db` before any planned data migration.

8. Start FastAPI as usual and check its health route at `http://127.0.0.1:8000/`. Then upload two frames from the same camera and inspect the resulting `frames`, `detections`, and `queue_updates` rows. MySQL being reachable alone does not mean that frame comparison/analytics have been implemented; confirm both frame IDs appear on each update and that duplicate uploads are handled as intended.

## Application configuration notes

A local development URL should use credentials from `.env`, with `.env` excluded from Git. Production should use a dedicated least-privilege MySQL user, network restrictions, managed secrets, backups, and encrypted connections. Do not expose port 3306 to the public internet.

`SERVICE_SECONDS_PER_PERSON` optionally sets the assumed service interval for the dashboard's **estimated average remaining wait**; it defaults to 30 seconds per person. The estimate is `(queue_count - 1) × service_seconds / 2`, assumes a first-in-first-out line, and is not an observed wait duration. Put a locally calibrated value in `server/.env` to change it.

### Configure the queue region and advance direction

After the camera has uploaded its first frame, the backend creates its `cameras` row. Set a polygon around the actual queue, using normalized `[x, y]` coordinates from 0 to 1. Set the direction vector toward the service counter. For example, if the queue advances upward in the image, positive movement is `(0, -1)`:

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

Replace the sample corners and direction with the camera's view. The backend uses each person's bottom-center point and counts forward movement when the projected position changes by more than 0.01 normalized image units. If the ROI is unset, all visible people are included in `queue_count`; if the direction is unset, the backend stores count/entry/exit changes but cannot identify forward movement. These are image-space estimates, not physical distances.

Run one Uvicorn worker per camera-tracking process (`uvicorn main:app --host 0.0.0.0 --port 8000`). The tracker state is held in memory per camera; after a backend restart a new tracking session is created, so the first incoming frame establishes a new comparison baseline.
