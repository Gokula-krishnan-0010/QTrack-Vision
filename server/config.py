"""QTrack Vision configuration loaded from environment or server/.env."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
FRAME_DIR = Path(os.getenv("FRAME_DIR", str(BASE_DIR / "frames")))
FRAME_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError(
        "DB_URL is not set. Configure server/.env with the MySQL connection URL "
        "from GUIDE.md before starting the backend."
    )
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", str(BASE_DIR / "yolov8n.pt"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))
SERVICE_SECONDS_PER_PERSON = max(0.0, float(os.getenv("SERVICE_SECONDS_PER_PERSON", "30")))
CORS_ORIGINS = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",") if origin.strip()]
