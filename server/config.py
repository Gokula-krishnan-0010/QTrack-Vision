"""
QTrack Vision — Application configuration.

Loads settings from environment variables (or .env file).
All paths are resolved relative to this file's directory.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
FRAME_DIR = Path(os.getenv("FRAME_DIR", str(BASE_DIR / "frames")))
FRAME_DIR.mkdir(parents=True, exist_ok=True)

# ── Database ────────────────────────────────────────────────────────────────
DB_URL = os.getenv("DB_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'qtrack.db'}")

# ── YOLO ────────────────────────────────────────────────────────────────────
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))

# ── Server ──────────────────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
