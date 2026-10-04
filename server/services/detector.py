"""YOLOv8 person detection with a persistent ByteTrack instance per camera."""
import logging
import threading
from pathlib import Path
from typing import Any
from config import YOLO_MODEL_PATH, CONFIDENCE_THRESHOLD

logger = logging.getLogger("qtrack.detector")
_models: dict[str, Any] = {}
_models_lock = threading.Lock()


def _get_model(camera_id: str):
    # Ultralytics stores tracker state on its model/predictor. Separate model
    # instances prevent IDs from one camera leaking into another camera.
    with _models_lock:
        if camera_id not in _models:
            from ultralytics import YOLO
            logger.info("Loading YOLO model for camera %s: %s", camera_id, YOLO_MODEL_PATH)
            _models[camera_id] = YOLO(YOLO_MODEL_PATH)
        return _models[camera_id]


def detect_persons(frame_path: str, camera_id: str) -> dict:
    """Return person detections and source dimensions; inference errors propagate."""
    model = _get_model(camera_id)
    results = model.track(
        source=frame_path, classes=[0], conf=CONFIDENCE_THRESHOLD,
        tracker=str(Path(__file__).resolve().parents[1] / "bytetrack.yaml"),
        persist=True, verbose=False,
    )
    detections = []
    height, width = 0, 0
    if results:
        result = results[0]
        height, width = result.orig_shape
        boxes = result.boxes
        if boxes is not None and len(boxes):
            for i in range(len(boxes)):
                track_id = int(boxes.id[i]) if boxes.id is not None else -1
                detections.append({
                    "tracker_id": track_id if track_id >= 0 else None,
                    "bbox": boxes.xyxy[i].tolist(),
                    "confidence": float(boxes.conf[i]),
                })
    logger.info("[%s] Detected %d persons in %s", camera_id, len(detections), Path(frame_path).name)
    return {"detections": detections, "width": int(width), "height": int(height)}


def annotate_frame(frame_path: str, detections: list[dict]) -> str:
    """Write an annotated latest.jpg preview when OpenCV/supervision are available."""
    try:
        import cv2
        import numpy as np
        import supervision as sv
        image = cv2.imread(frame_path)
        if image is None:
            return frame_path
        if detections:
            xyxy = np.array([d["bbox"] for d in detections])
            confidence = np.array([d["confidence"] for d in detections])
            ids = np.array([d["tracker_id"] if d["tracker_id"] is not None else -1 for d in detections])
            sv_detections = sv.Detections(
                xyxy=xyxy,
                confidence=confidence,
                class_id=np.zeros(len(detections), dtype=int),
                tracker_id=ids,
            )
            labels = [f"#{d['tracker_id']} {d['confidence']:.0%}" for d in detections]
            image = sv.BoxAnnotator(thickness=2).annotate(image, sv_detections)
            image = sv.LabelAnnotator(text_scale=0.5, text_thickness=1).annotate(image, sv_detections, labels)
        output = str(Path(frame_path).parent / "latest.jpg")
        cv2.imwrite(output, image)
        return output
    except ImportError:
        logger.warning("OpenCV/supervision unavailable; skipping frame annotation")
        return frame_path
    except Exception:
        # Annotation is only a preview feature. A drawing-library error must not
        # turn a successfully persisted frame into an HTTP failure.
        logger.exception("Could not annotate frame %s", frame_path)
        return frame_path
