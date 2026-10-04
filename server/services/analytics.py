"""Queue-region membership and progression calculations for consecutive frames."""
from typing import Any

# Position change smaller than this normalized image distance is treated as noise.
MOVEMENT_EPSILON = 0.01


def estimate_average_wait(queue_count: int, service_seconds_per_person: float) -> float:
    """Estimate remaining wait averaged across the visible line, assuming FCFS service."""
    if queue_count <= 1:
        return 0.0
    return round((queue_count - 1) * service_seconds_per_person / 2, 1)


def _inside_polygon(x: float, y: float, polygon: list) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def prepare_detections(detections: list[dict], width: int, height: int,
                       roi: Any, direction_x: Any, direction_y: Any) -> list[dict]:
    """Add normalized foot point, queue membership, and projected queue position."""
    polygon = roi if isinstance(roi, list) and len(roi) >= 3 else None
    dx = float(direction_x) if direction_x is not None else None
    dy = float(direction_y) if direction_y is not None else None
    norm = ((dx * dx + dy * dy) ** 0.5) if dx is not None and dy is not None else 0
    if norm:
        dx, dy = dx / norm, dy / norm
    prepared = []
    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        # Bottom-center (foot point) better represents where someone stands than box center.
        x = min(max(((x1 + x2) / 2) / width, 0), 1)
        y = min(max(y2 / height, 0), 1)
        in_queue = _inside_polygon(x, y, polygon) if polygon else True
        prepared.append({
            **detection,
            "center_x": x,
            "center_y": y,
            "in_queue": in_queue,
            "queue_position": (x * dx + y * dy) if norm and in_queue else None,
        })
    return prepared


def compare_frames(previous: list[dict], current: list[dict],
                   previous_queue_count: int, current_queue_count: int,
                   previous_time, current_time, direction_configured: bool) -> dict:
    """Compare IDs and queue locations; missing detections alone do not count as exits."""
    def indexed(rows):
        return {int(row["tracker_id"]): row for row in rows
                if row.get("tracker_id") is not None and int(row["tracker_id"]) >= 0}

    old, new = indexed(previous), indexed(current)
    advanced, entered, exited = [], [], []
    for track_id, now in new.items():
        before = old.get(track_id)
        if now["in_queue"] and (before is None or not before["in_queue"]):
            entered.append(track_id)
        elif before and before["in_queue"] and not now["in_queue"]:
            exited.append(track_id)
        elif (before and before["in_queue"] and now["in_queue"] and direction_configured
              and now["queue_position"] is not None and before["queue_position"] is not None
              and now["queue_position"] - before["queue_position"] > MOVEMENT_EPSILON):
            advanced.append(track_id)
    elapsed = max((current_time - previous_time).total_seconds(), 0.0)
    return {
        "elapsed_seconds": round(elapsed, 3),
        "previous_queue_count": previous_queue_count,
        "current_queue_count": current_queue_count,
        "queue_count_delta": current_queue_count - previous_queue_count,
        "advanced_tracker_ids": advanced,
        "advanced_person_count": len(advanced),
        "entered_tracker_ids": entered,
        "entered_queue_count": len(entered),
        "exited_tracker_ids": exited,
        "exited_queue_count": len(exited),
        "exit_rate": round(len(exited) / max(previous_queue_count, 1), 5),
    }
