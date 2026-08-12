"""
QTrack Vision — YOLOv8n person detection + ByteTrack tracking.

This module loads the YOLO model once at import time and exposes
a detect_persons() function that runs inference on a saved JPEG frame.

The model runs person-class-only detection (class 0 in COCO) and
uses ByteTrack for persistent object IDs across consecutive frames.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from config import YOLO_MODEL_PATH, CONFIDENCE_THRESHOLD

logger = logging.getLogger("qtrack.detector")

# ── Lazy model loading ──────────────────────────────────────────────────────
# We load the model at first use (not import time) so the server can
# start even if the model file hasn't been downloaded yet.
_model = None


def _get_model():
    """Load YOLOv8n model (singleton). Downloads on first run if missing."""
    global _model
    if _model is None:
        try:
            from ultralytics import YOLO
            logger.info(f"[YOLO] Loading model: {YOLO_MODEL_PATH}")
            _model = YOLO(YOLO_MODEL_PATH)
            logger.info("[YOLO] ✓ Model loaded successfully")
        except Exception as e:
            logger.error(f"[YOLO] ✗ Failed to load model: {e}")
            raise
    return _model


def detect_persons(frame_path: str) -> List[Dict[str, Any]]:
    """
    Run YOLOv8n + ByteTrack on a single JPEG frame.

    Args:
        frame_path: Absolute path to the saved JPEG file.

    Returns:
        List of detection dicts, each containing:
            - track_id: int (persistent across frames, or -1 if tracking fails)
            - bbox: [x1, y1, x2, y2] in pixel coordinates
            - confidence: float (0-1)
    """
    model = _get_model()
    detections: List[Dict[str, Any]] = []

    try:
        # Run tracking (ByteTrack is the default tracker in ultralytics)
        results = model.track(
            source=frame_path,
            classes=[0],                        # Person class only (COCO index 0)
            conf=CONFIDENCE_THRESHOLD,
            tracker="bytetrack.yaml",           # Use our custom ByteTrack config
            persist=True,                        # Keep track IDs across calls
            verbose=False,                       # Suppress per-frame logs
        )

        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            if boxes is not None and len(boxes) > 0:
                for i in range(len(boxes)):
                    bbox = boxes.xyxy[i].tolist()
                    conf = float(boxes.conf[i])

                    # Track ID may be None if tracking failed for this box
                    track_id = -1
                    if boxes.id is not None:
                        track_id = int(boxes.id[i])

                    detections.append({
                        "track_id": track_id,
                        "bbox": bbox,
                        "confidence": conf,
                    })

        logger.info(f"[YOLO] Detected {len(detections)} person(s) in {Path(frame_path).name}")

    except Exception as e:
        logger.error(f"[YOLO] Detection failed: {e}")
        # Return empty list on failure — don't crash the frame pipeline

    return detections


def annotate_frame(frame_path: str, detections: List[Dict[str, Any]]) -> str:
    """
    Draw bounding boxes on the frame and save as 'annotated_<filename>'.
    Uses the supervision library for clean annotations.

    Returns the path to the annotated image.
    """
    try:
        import cv2
        import supervision as sv
        import numpy as np

        image = cv2.imread(frame_path)
        if image is None:
            logger.warning(f"[ANNO] Could not read image: {frame_path}")
            return frame_path

        if not detections:
            return frame_path

        # Build supervision Detections object
        xyxy = np.array([d["bbox"] for d in detections])
        confidence = np.array([d["confidence"] for d in detections])
        tracker_ids = np.array([d["track_id"] for d in detections])

        sv_detections = sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
            tracker_id=tracker_ids,
        )

        # Annotate
        box_annotator = sv.BoxAnnotator(thickness=2)
        label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)

        labels = [
            f"#{d['track_id']} {d['confidence']:.0%}"
            for d in detections
        ]

        annotated = box_annotator.annotate(image.copy(), sv_detections)
        annotated = label_annotator.annotate(annotated, sv_detections, labels)

        # Save — overwrite latest.jpg so the dashboard always shows annotated
        output_path = str(Path(frame_path).parent / "latest.jpg")
        cv2.imwrite(output_path, annotated)
        logger.info(f"[ANNO] ✓ Annotated frame saved: {output_path}")
        return output_path

    except ImportError:
        logger.warning("[ANNO] supervision/cv2 not installed — skipping annotation")
        return frame_path
    except Exception as e:
        logger.error(f"[ANNO] Annotation failed: {e}")
        return frame_path
