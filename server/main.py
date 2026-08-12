"""
QTrack Vision — FastAPI application entry point.

Lifecycle:
    1. On startup: initialize database tables, pre-load YOLO model
    2. Runtime: serve frame ingestion + SSE + static frames
    3. On shutdown: (graceful — nothing special needed for SQLite)

Run with:
    cd server
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS, FRAME_DIR
from database import init_db

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("qtrack.main")


# ── Lifespan (startup / shutdown) ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on server startup and shutdown."""
    logger.info("╔══════════════════════════════════════╗")
    logger.info("║   QTrack Vision — FastAPI Backend    ║")
    logger.info("╚══════════════════════════════════════╝")

    # Initialize database tables
    await init_db()
    logger.info("[DB] ✓ Database tables ready")

    # Pre-load YOLO model (so the first frame doesn't have a cold start)
    try:
        from services.detector import _get_model
        _get_model()
    except Exception as e:
        logger.warning(f"[YOLO] Model pre-load failed (will retry on first frame): {e}")

    yield  # ← App runs here

    logger.info("[SHUTDOWN] QTrack Vision shutting down")


# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="QTrack Vision",
    description="Real-time queue monitoring API — receives ESP32-CAM frames, "
                "runs YOLOv8n detection, and streams analytics via SSE.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS (allow dashboard to connect) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files: serve annotated frames for the dashboard ──
app.mount("/frames", StaticFiles(directory=str(FRAME_DIR)), name="frames")

# ── Routers ──
from routers.frames import router as frames_router
from routers.events import router as events_router

app.include_router(frames_router)
app.include_router(events_router)


@app.get("/", tags=["health"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "QTrack Vision"}
