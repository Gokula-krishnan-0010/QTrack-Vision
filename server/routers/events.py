"""
QTrack Vision — SSE (Server-Sent Events) router.

Streams real-time queue analytics updates to dashboard clients.
Uses an internal pub/sub pattern with asyncio.Queue per client.

Endpoint:
    GET /api/queue/events?shop_id=<str>  — SSE stream
"""

import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("qtrack.events")
router = APIRouter(prefix="/api/queue", tags=["events"])

# ── Internal pub/sub ────────────────────────────────────────────────────────
# Each connected SSE client gets its own asyncio.Queue.
# Keyed by shop_id → set of queues.
_subscribers: Dict[str, Set[asyncio.Queue]] = {}


async def broadcast_event(shop_id: str, data: dict):
    """
    Push an event to all SSE clients subscribed to this shop_id.
    Called from the frames router after each frame is processed.
    """
    queues = _subscribers.get(shop_id, set())
    payload = json.dumps(data, default=str)
    dead_queues = []

    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Client is too slow — drop this event (better than blocking)
            dead_queues.append(q)
            logger.warning(f"[SSE] Dropping event for slow client on {shop_id}")

    # Clean up dead queues
    for q in dead_queues:
        queues.discard(q)


async def _event_generator(request: Request, shop_id: str):
    """
    Async generator that yields SSE events for a specific shop.
    Automatically unsubscribes when the client disconnects.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    # Subscribe
    if shop_id not in _subscribers:
        _subscribers[shop_id] = set()
    _subscribers[shop_id].add(queue)
    logger.info(f"[SSE] Client subscribed to '{shop_id}' "
                f"(total: {len(_subscribers[shop_id])})")

    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for next event (with timeout to periodically
                # check for disconnection)
                payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {
                    "event": "queue_update",
                    "data": payload,
                }
            except asyncio.TimeoutError:
                # Send a keep-alive comment to prevent proxy/browser timeouts
                yield {"comment": "keep-alive"}

    finally:
        # Unsubscribe
        _subscribers.get(shop_id, set()).discard(queue)
        remaining = len(_subscribers.get(shop_id, set()))
        logger.info(f"[SSE] Client disconnected from '{shop_id}' "
                    f"(remaining: {remaining})")


@router.get("/events")
async def sse_endpoint(
    request: Request,
    shop_id: str = Query(..., description="Shop ID to subscribe to"),
):
    """
    Server-Sent Events stream for real-time queue updates.

    The dashboard connects here and receives a JSON payload
    every time a new frame is processed for the given shop.
    """
    return EventSourceResponse(
        _event_generator(request, shop_id),
        media_type="text/event-stream",
    )
