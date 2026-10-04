"""Frame ingestion, per-camera frame comparison, persistence and history APIs."""
import asyncio
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import FRAME_DIR, SERVICE_SECONDS_PER_PERSON
from database import get_session
from models import Camera, Detection, Frame, QueueUpdate, TrackingSession
from services.analytics import compare_frames, estimate_average_wait, prepare_detections
from services.detector import annotate_frame, detect_persons
from routers.events import broadcast_event

logger = logging.getLogger("qtrack.frames")
router = APIRouter(prefix="/api/queue", tags=["queue"])
_camera_locks: dict[str, asyncio.Lock] = {}
_runtime_sessions: dict[str, int] = {}


def _camera_lock(shop_id: str) -> asyncio.Lock:
    return _camera_locks.setdefault(shop_id, asyncio.Lock())


def _detection_payload(detection: Detection) -> dict:
    return {
        "tracker_id": detection.tracker_id,
        "in_queue": bool(detection.in_queue),
        "queue_position": float(detection.queue_position) if detection.queue_position is not None else None,
    }


def _frame_payload(frame: Frame, shop_id: str) -> dict:
    return {
        "id": frame.id,
        "sequence_no": frame.sequence_no,
        "shop_id": shop_id,
        "timestamp": frame.captured_at.isoformat() if frame.captured_at else None,
        "created_at": frame.received_at.isoformat() if frame.received_at else None,
        "person_count": frame.person_count,
        "queue_length": frame.queue_count,
        "image_path": frame.image_path,
    }


@router.post("/frame")
async def receive_frame(
    request: Request,
    shop_id: str = Query(..., min_length=1, max_length=100, description="Unique shop / camera identifier"),
    timestamp: int = Query(0, description="Epoch seconds from ESP32; 0 uses server time"),
    session: AsyncSession = Depends(get_session),
):
    """Accept raw JPEG bytes; this contract matches the ESP32-CAM firmware."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", shop_id):
        raise HTTPException(status_code=400, detail="shop_id may contain only letters, digits, hyphens and underscores")
    body = await request.body()
    if len(body) < 500 or not body.startswith(b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="Body must contain a valid JPEG image")

    async with _camera_lock(shop_id):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        captured_at = (datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)
                       if timestamp > 1700000000 else now)
        device_frame_id = str(timestamp) if timestamp > 1700000000 else None

        try:
            camera = await session.scalar(select(Camera).where(Camera.shop_id == shop_id))
            if camera is None:
                camera = Camera(shop_id=shop_id, display_name=shop_id, enabled=True)
                session.add(camera)
                await session.flush()
            if not camera.enabled:
                raise HTTPException(status_code=403, detail="Camera is disabled")

            # Firmware retries resend the same capture timestamp. Do not run that
            # JPEG through ByteTrack a second time or create a duplicate transition.
            if device_frame_id is not None:
                existing = await session.scalar(select(Frame).where(
                    Frame.camera_id == camera.id,
                    Frame.device_frame_id == device_frame_id,
                ))
                if existing is not None:
                    saved_update = await session.scalar(select(QueueUpdate).where(
                        QueueUpdate.current_frame_id == existing.id
                    ))
                    return JSONResponse(content={
                        "status": "received", "duplicate": True,
                        "frame_id": existing.id, "sequence_no": existing.sequence_no,
                        "person_count": existing.person_count,
                        "queue_length": existing.queue_count,
                        "queue_update": saved_update.to_dict() if saved_update else None,
                    })

            shop_dir = FRAME_DIR / shop_id
            shop_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{int(captured_at.replace(tzinfo=timezone.utc).timestamp() * 1000)}_{secrets.token_hex(4)}.jpg"
            file_path = shop_dir / filename
            file_path.write_bytes(body)

            tracker_session_id = _runtime_sessions.get(shop_id)
            created_runtime_session = False
            if tracker_session_id is None:
                tracking_session = TrackingSession(camera_id=camera.id, reason="backend_startup")
                session.add(tracking_session)
                await session.flush()
                tracker_session_id = tracking_session.id
                created_runtime_session = True

            result = detect_persons(str(file_path), shop_id)
            raw_detections = result["detections"]
            prepared = prepare_detections(
                raw_detections, result["width"], result["height"], camera.queue_roi,
                camera.queue_direction_x, camera.queue_direction_y,
            )
            queue_count = sum(1 for item in prepared if item["in_queue"])
            movement_configured = (
                camera.queue_direction_x is not None and camera.queue_direction_y is not None
            )
            queue_roi_configured = isinstance(camera.queue_roi, list) and len(camera.queue_roi) >= 3

            previous_frame = await session.scalar(
                select(Frame).where(
                    Frame.camera_id == camera.id,
                    Frame.tracking_session_id == tracker_session_id,
                    Frame.processing_status == "processed",
                ).order_by(Frame.sequence_no.desc()).limit(1)
            )
            max_seq = await session.scalar(select(func.max(Frame.sequence_no)).where(Frame.camera_id == camera.id))
            sequence_no = int(max_seq or 0) + 1

            frame = Frame(
                camera_id=camera.id,
                tracking_session_id=tracker_session_id,
                sequence_no=sequence_no,
                device_frame_id=device_frame_id,
                captured_at=captured_at,
                image_path=str(file_path.relative_to(FRAME_DIR)).replace("\\", "/"),
                image_width=result["width"],
                image_height=result["height"],
                person_count=len(prepared),
                queue_count=queue_count,
                previous_frame_id=previous_frame.id if previous_frame else None,
                processing_status="processed",
            )
            session.add(frame)
            await session.flush()

            for item in prepared:
                x1, y1, x2, y2 = item["bbox"]
                width, height = result["width"], result["height"]
                session.add(Detection(
                    frame_id=frame.id,
                    tracker_id=item["tracker_id"],
                    confidence=round(item["confidence"], 5),
                    x1=round(max(0.0, min(float(x1) / width, 1.0)), 7),
                    y1=round(max(0.0, min(float(y1) / height, 1.0)), 7),
                    x2=round(max(0.0, min(float(x2) / width, 1.0)), 7),
                    y2=round(max(0.0, min(float(y2) / height, 1.0)), 7),
                    center_x=round(item["center_x"], 7), center_y=round(item["center_y"], 7),
                    in_queue=item["in_queue"],
                    queue_position=round(item["queue_position"], 6) if item["queue_position"] is not None else None,
                ))

            update = None
            if previous_frame is not None:
                previous_rows = (await session.scalars(
                    select(Detection).where(Detection.frame_id == previous_frame.id)
                )).all()
                previous_metrics = compare_frames(
                    [_detection_payload(d) for d in previous_rows], prepared,
                    previous_frame.queue_count, queue_count,
                    previous_frame.captured_at, captured_at,
                movement_configured,
                )
                update = QueueUpdate(
                    camera_id=camera.id,
                    tracking_session_id=tracker_session_id,
                    previous_frame_id=previous_frame.id,
                    current_frame_id=frame.id,
                    measured_at=captured_at,
                    avg_wait_seconds=estimate_average_wait(queue_count, SERVICE_SECONDS_PER_PERSON),
                    **previous_metrics,
                )
                session.add(update)

            await session.commit()
            if created_runtime_session:
                _runtime_sessions[shop_id] = tracker_session_id
            await session.refresh(frame)
            if update is not None:
                await session.refresh(update)

            # Save the annotated live preview only after source frame and DB transaction succeed.
            annotate_frame(str(file_path), raw_detections)
            payload = {
                **_frame_payload(frame, shop_id),
                "avg_wait_sec": estimate_average_wait(queue_count, SERVICE_SECONDS_PER_PERSON),
                "service_seconds_per_person": SERVICE_SECONDS_PER_PERSON,
                "movement_configured": movement_configured,
                "queue_roi_configured": queue_roi_configured,
                "tracked_people": [
                    {
                        "tracker_id": item["tracker_id"],
                        "confidence": round(item["confidence"], 3),
                        "in_queue": item["in_queue"],
                        "queue_position": item["queue_position"],
                    }
                    for item in prepared
                ],
                "exit_rate": float(update.exit_rate) if update and update.exit_rate is not None else 0.0,
                "queue_update": update.to_dict() if update else None,
                **(update.to_dict() if update else {}),
                "annotated_frame_url": f"/frames/{shop_id}/latest.jpg",
            }
            await broadcast_event(shop_id, payload)
            logger.info("[%s] frame=%s people=%s queue=%s delta=%s advanced=%s",
                        shop_id, frame.id, frame.person_count, frame.queue_count,
                        update.queue_count_delta if update else None,
                        update.advanced_person_count if update else None)
            return JSONResponse(content={
                "status": "received",
                "frame_id": frame.id,
                "sequence_no": frame.sequence_no,
                "person_count": frame.person_count,
                "queue_length": frame.queue_count,
                "avg_wait_sec": estimate_average_wait(queue_count, SERVICE_SECONDS_PER_PERSON),
                "service_seconds_per_person": SERVICE_SECONDS_PER_PERSON,
                "movement_configured": movement_configured,
                "queue_roi_configured": queue_roi_configured,
                "tracked_people": [
                    {
                        "tracker_id": item["tracker_id"],
                        "confidence": round(item["confidence"], 3),
                        "in_queue": item["in_queue"],
                        "queue_position": item["queue_position"],
                    }
                    for item in prepared
                ],
                "exit_rate": float(update.exit_rate) if update and update.exit_rate is not None else 0.0,
                "queue_update": update.to_dict() if update else None,
            })
        except HTTPException:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            logger.exception("[%s] frame processing failed", shop_id)
            raise HTTPException(status_code=500, detail="Frame processing failed; see backend logs")


@router.get("/history")
async def get_history(
    shop_id: str = Query(...),
    hours: int = Query(1, ge=1, le=168, description="Hours of history to fetch"),
    limit: int = Query(60, ge=1, le=1000, description="Maximum number of frames"),
    session: AsyncSession = Depends(get_session),
):
    """Return saved frame analytics and the frame-to-frame transition, if any."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    rows = (await session.execute(
        select(Frame, QueueUpdate, Camera.queue_roi, Camera.queue_direction_x, Camera.queue_direction_y)
        .select_from(Frame).join(
            Camera, Camera.id == Frame.camera_id
        ).outerjoin(
            QueueUpdate, QueueUpdate.current_frame_id == Frame.id
        ).where(
            Camera.shop_id == shop_id, Frame.received_at >= cutoff
        ).order_by(Frame.sequence_no.desc()).limit(limit)
    )).all()
    rows.reverse()
    response = []
    latest_frame_id = rows[-1][0].id if rows else None
    latest_detections = []
    if latest_frame_id is not None:
        detections = (await session.scalars(
            select(Detection).where(Detection.frame_id == latest_frame_id)
        )).all()
        latest_detections = [
            {
                "tracker_id": detection.tracker_id,
                "confidence": float(detection.confidence),
                "in_queue": bool(detection.in_queue),
                "queue_position": float(detection.queue_position) if detection.queue_position is not None else None,
            }
            for detection in detections
        ]
    for frame, update, queue_roi, direction_x, direction_y in rows:
        item = _frame_payload(frame, shop_id)
        item["avg_wait_sec"] = estimate_average_wait(frame.queue_count, SERVICE_SECONDS_PER_PERSON)
        item["service_seconds_per_person"] = SERVICE_SECONDS_PER_PERSON
        item["movement_configured"] = direction_x is not None and direction_y is not None
        item["queue_roi_configured"] = isinstance(queue_roi, list) and len(queue_roi) >= 3
        if frame.id == latest_frame_id:
            item["tracked_people"] = latest_detections
            item["annotated_frame_url"] = f"/frames/{shop_id}/latest.jpg"
        item["exit_rate"] = float(update.exit_rate) if update and update.exit_rate is not None else 0.0
        item["queue_update"] = update.to_dict() if update else None
        response.append(item)
    return response


@router.get("/shops")
async def list_shops(session: AsyncSession = Depends(get_session)):
    shops = (await session.scalars(select(Camera.shop_id).order_by(Camera.shop_id))).all()
    return {"shops": list(shops)}
