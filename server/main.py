"""QTrack Vision FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import CORS_ORIGINS, FRAME_DIR
from database import init_db

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("qtrack.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database schema ready")
    yield
    logger.info("QTrack Vision shutting down")


app = FastAPI(title="QTrack Vision",
              description="ESP32-CAM person detection, ByteTrack and queue progression analytics.",
              version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/frames", StaticFiles(directory=str(FRAME_DIR)), name="frames")
from routers.frames import router as frames_router
from routers.events import router as events_router
app.include_router(frames_router)
app.include_router(events_router)


@app.get("/", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "QTrack Vision"}
