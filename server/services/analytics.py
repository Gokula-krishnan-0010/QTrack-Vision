"""
QTrack Vision — Queue analytics computation.

Computes queue metrics from detection results:
    - queue_length: persons currently in the queue zone (= person_count for now)
    - avg_wait_sec: estimated wait time based on exit-rate moving average
    - exit_rate:    fraction of tracked persons who left in the last N frames

All state is kept in-memory per shop_id. This is reset on server restart,
which is acceptable for a demo / Solve for Tomorrow presentation.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Dict, Any, List, Set

logger = logging.getLogger("qtrack.analytics")

# ── Per-shop tracking state ─────────────────────────────────────────────────
# track_history[shop_id] = deque of sets of track_ids from recent frames
_track_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))

# exit_times[shop_id] = deque of timestamps when a person exited
_exit_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

# last_seen[shop_id] = set of track_ids from the previous frame
_last_seen: Dict[str, Set[int]] = defaultdict(set)

# Average service time per person (rolling, in seconds)
_avg_service_times: Dict[str, float] = defaultdict(lambda: 30.0)  # default 30s


def compute_queue_metrics(
    shop_id: str,
    detections: List[Dict[str, Any]],
    person_count: int,
) -> Dict[str, Any]:
    """
    Compute queue analytics from the latest frame's detections.

    Args:
        shop_id:      Identifier for the shop / camera.
        detections:   List of detection dicts from detector.py
                      (each has 'track_id', 'bbox', 'confidence').
        person_count: Total persons detected in this frame.

    Returns:
        Dict with keys: queue_length, avg_wait_sec, exit_rate
    """
    now = time.time()

    # ── Extract current track IDs ──
    current_ids: Set[int] = set()
    for d in detections:
        tid = d.get("track_id", -1)
        if tid >= 0:
            current_ids.add(tid)

    # ── Compute exits (IDs that were in the last frame but not this one) ──
    prev_ids = _last_seen[shop_id]
    exited_ids = prev_ids - current_ids

    if exited_ids:
        for _ in exited_ids:
            _exit_times[shop_id].append(now)
        logger.info(f"[ANALYTICS] {shop_id}: {len(exited_ids)} person(s) exited")

    # Update last-seen
    _last_seen[shop_id] = current_ids
    _track_history[shop_id].append(current_ids)

    # ── Exit rate ──
    # Fraction of people who left in the last 60 seconds relative to
    # the average number of people seen.
    recent_exits = sum(1 for t in _exit_times[shop_id] if now - t < 60)
    all_seen = set()
    for frame_ids in _track_history[shop_id]:
        all_seen |= frame_ids
    total_seen = max(len(all_seen), 1)
    exit_rate = round(min(recent_exits / total_seen, 1.0), 3)

    # ── Average service time (exponential moving average) ──
    # If we observed exits, update the service time estimate.
    # We use the inter-exit interval as a proxy for service time.
    exit_list = list(_exit_times[shop_id])
    if len(exit_list) >= 2:
        # Average gap between consecutive exits
        gaps = [exit_list[i] - exit_list[i - 1]
                for i in range(1, len(exit_list))
                if exit_list[i] - exit_list[i - 1] < 300]  # Cap at 5 min
        if gaps:
            new_avg = sum(gaps) / len(gaps)
            # EMA with alpha = 0.3
            _avg_service_times[shop_id] = (
                0.7 * _avg_service_times[shop_id] + 0.3 * new_avg
            )

    # ── Estimated wait time ──
    # Simple model: wait = queue_position × avg_service_time
    # For now, queue_length = person_count (no zone filtering yet).
    queue_length = person_count
    avg_service = _avg_service_times[shop_id]
    avg_wait_sec = round(queue_length * avg_service, 1)

    metrics = {
        "queue_length": queue_length,
        "avg_wait_sec": avg_wait_sec,
        "exit_rate": exit_rate,
    }

    logger.debug(f"[ANALYTICS] {shop_id}: {metrics}")
    return metrics
