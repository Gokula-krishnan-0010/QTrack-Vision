"""
QTrack Vision — Frame ingestion router.

Endpoints:
    POST /api/queue/frame   — Receive a JPEG frame from an ESP32-CAM
    GET  /api/queue/history  — Fetch historical analytics for charts
    GET  /api/queue/shops    — List all known shop IDs
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import FRAME_DIR
from database import get_session
from models import FrameRecord
from services.detector import detect_persons
from services.analytics import compute_queue_metrics

# Shared event bus — SSE clients subscribe to this; we import it
# from the events router to avoid circular deps.
from routers.events import broadcast_event

logger = logging.getLogger("qtrack.frames")
router = APIRouter(prefix="/api/queue", tags=["queue"])


@router.post("/frame")
async def receive_frame(
    request: Request,
    shop_id: str = Query(..., description="Unique shop / camera identifier"),
    timestamp: int = Query(0, description="Epoch seconds from ESP32 (0 = use server time)"),
    session: AsyncSession = Depends(get_session),
):
    """
    Receive a raw JPEG frame from an ESP32-CAM.

    API contract (matches firmware):
        Content-Type: image/jpeg
        Body: raw JPEG bytes
        Query params: shop_id, timestamp
    """
    # ── 1. Read raw JPEG body ──
    body = await request.body()
    if len(body) < 500:
        raise HTTPException(status_code=400, detail="Body too small to be a valid JPEG")

    # ── 2. Determine timestamp ──
    if timestamp and timestamp > 1700000000:
        frame_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    else:
        frame_time = datetime.now(timezone.utc)

    # ── 3. Save frame to disk ──
    shop_dir = FRAME_DIR / shop_id
    shop_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{int(frame_time.timestamp())}.jpg"
    file_path = shop_dir / filename
    file_path.write_bytes(body)

    # Also save as "latest.jpg" for the dashboard live-feed
    latest_path = shop_dir / "latest.jpg"
    latest_path.write_bytes(body)

    logger.info(f"[{shop_id}] Frame saved: {file_path} ({len(body)} bytes)")

    # ── 4. Run YOLOv8n detection ──
    detections = detect_persons(str(file_path))
    person_count = len(detections)

    # ── 5. Compute queue analytics ──
    metrics = compute_queue_metrics(shop_id, detections, person_count)

    # ── 6. Persist to database ──
    record = FrameRecord(
        shop_id=shop_id,
        timestamp=frame_time,
        file_path=str(file_path.relative_to(FRAME_DIR)),
        person_count=person_count,
        queue_length=metrics["queue_length"],
        avg_wait_sec=metrics["avg_wait_sec"],
        exit_rate=metrics["exit_rate"],
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    # ── 7. Broadcast to SSE clients ──
    event_data = {
        **record.to_dict(),
        "annotated_frame_url": f"/frames/{shop_id}/latest.jpg",
    }
    await broadcast_event(shop_id, event_data)

    # ── 8. Respond to ESP32 ──
    return JSONResponse(
        content={
            "status": "received",
            "person_count": person_count,
            "queue_length": metrics["queue_length"],
        }
    )


@router.get("/history")
async def get_history(
    shop_id: str = Query(...),
    hours: int = Query(1, ge=1, le=168, description="Hours of history to fetch"),
    session: AsyncSession = Depends(get_session),
):
    """Return recent analytics for the trend chart."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await session.execute(
        select(FrameRecord)
        .where(FrameRecord.shop_id == shop_id, FrameRecord.created_at >= cutoff)
        .order_by(FrameRecord.created_at.asc())
    )
    records = result.scalars().all()
    return [r.to_dict() for r in records]


@router.get("/shops")
async def list_shops(session: AsyncSession = Depends(get_session)):
    """Return a list of all shop IDs that have sent at least one frame."""
    result = await session.execute(
        select(FrameRecord.shop_id).distinct()
    )
    shops = [row[0] for row in result.all()]
    return {"shops": shops}
