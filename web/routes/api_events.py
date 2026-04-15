"""Server-Sent Events stream for real-time dashboard updates.

GET /api/events/stream   — SSE endpoint (long-lived connection)
GET /api/events/history  — recent event history from EventBus
"""

import json
import logging
import queue
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

from core.event_bus import EventType
from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_events", __name__, url_prefix="/api/events")

# Keepalive interval (seconds) for SSE connections.
# Browsers and reverse proxies may close idle connections after ~30s,
# so we send a comment every 25s to keep the connection alive.
SSE_KEEPALIVE_TIMEOUT = 25


def _serialize_event(event) -> str:
    """Turn an EventBus Event into a JSON string for SSE."""
    return json.dumps({
        "type": event.event_type.name,
        "data": _safe_data(event.data),
        "source": event.source,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
    })


def _safe_data(obj):
    """Ensure the event data is JSON-serializable."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _safe_data(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_data(i) for i in obj]
    if isinstance(obj, (int, float, str, bool)):
        return obj
    return str(obj)


@bp.route("/stream", methods=["GET"])
def event_stream():
    """SSE endpoint — pushes EventBus events to connected browsers."""
    svc = get_services()

    q: queue.Queue = queue.Queue(maxsize=200)
    svc.register_sse_queue(q)

    # Also subscribe to the EventBus to feed the queue
    def _bridge(event):
        try:
            q.put_nowait(("event", _serialize_event(event)))
        except queue.Full:
            pass  # drop if consumer is slow

    svc.event_bus.subscribe_all(_bridge)

    def generate():
        try:
            # Initial keepalive
            yield ": connected\n\n"
            while True:
                try:
                    event_name, data = q.get(timeout=SSE_KEEPALIVE_TIMEOUT)
                    yield f"event: {event_name}\ndata: {data}\n\n"
                except queue.Empty:
                    # Send keepalive comment every 25s
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            svc.event_bus.unsubscribe_all(_bridge)
            svc.unregister_sse_queue(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@bp.route("/history", methods=["GET"])
def event_history():
    """Return recent event history from the EventBus."""
    svc = get_services()
    limit = min(int(request.args.get("limit", 50)), 200)

    # Optional type filter
    type_filter = request.args.get("type")
    event_type = None
    if type_filter:
        try:
            event_type = EventType[type_filter]
        except KeyError:
            return jsonify({"error": f"Unknown event type: {type_filter}"}), 400

    events = svc.event_bus.get_history(event_type=event_type, limit=limit)
    serialized = []
    for e in events:
        serialized.append({
            "type": e.event_type.name,
            "data": _safe_data(e.data),
            "source": e.source,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        })

    return jsonify({"events": serialized, "count": len(serialized)})
