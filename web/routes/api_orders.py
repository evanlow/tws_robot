"""Order management API.

GET    /api/orders       — all orders with status
POST   /api/orders       — record a manual order request (local-only)
DELETE /api/orders/<id>  — cancel an order

Note on cancellation
--------------------
Orders created through this API are recorded locally with
``execution_mode = "local_only"`` and are never submitted to a broker.
The DELETE endpoint marks such orders as CANCELLED in the local store only
and returns a ``warning`` field in the response to make this explicit.

If an order carries a ``broker_order_id`` field the cancellation request is
also forwarded to the connected broker (if any); successful forwarding
returns ``status = "cancel_requested"`` with ``execution_mode = "broker"``.
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_orders", __name__, url_prefix="/api/orders")


@bp.route("/", methods=["GET"])
def list_orders():
    """Return all tracked orders."""
    svc = get_services()
    orders = svc.get_orders()
    return jsonify({"orders": orders, "count": len(orders)})


@bp.route("/", methods=["POST"])
def record_order():
    """Record a manual order request (local-only).

    Body::

        {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "order_type": "MARKET",
            "limit_price": null
        }
    """
    svc = get_services()
    if svc.risk_manager.emergency_stop_active:
        return jsonify({"error": "Emergency stop is active — cannot record orders"}), 403

    if not svc.trading_state.allows_order_submission:
        return jsonify({
            "error": f"Order recording not allowed in state: {svc.trading_state.value}",
        }), 403

    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol", "").upper()
    action = data.get("action", "").upper()
    quantity = data.get("quantity", 0)
    order_type = data.get("order_type", "MARKET").upper()
    limit_price = data.get("limit_price")

    if not symbol or action not in ("BUY", "SELL") or quantity <= 0:
        return jsonify({
            "error": "symbol, action (BUY/SELL), and quantity (>0) required",
        }), 400

    order_record = {
        "id": f"WEB-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "symbol": symbol,
        "action": action,
        "quantity": quantity,
        "order_type": order_type,
        "limit_price": limit_price,
        "status": "RECORDED",
        "execution_mode": "local_only",
        "recorded_at": datetime.now().isoformat(),
        "source": "web_dashboard",
    }

    svc.add_order(order_record)
    logger.info("Manual order recorded locally (not broker-submitted): %s", order_record)

    return jsonify({
        "status": "recorded",
        "execution_mode": "local_only",
        "message": "Order was recorded locally but not submitted to a broker.",
        "order": order_record,
    }), 201


@bp.route("/<order_id>", methods=["DELETE"])
def cancel_order(order_id: str):
    """Cancel a pending order.

    For orders with ``execution_mode`` of ``local_only`` the cancellation is
    applied to the local store only — no request is forwarded to the broker.
    The response includes an explicit ``warning`` field and
    ``execution_mode = "local_only"`` so callers are never misled.

    For orders that carry a ``broker_order_id`` field a cancellation request
    is also forwarded to the connected broker (if any). Successful forwarding
    returns ``status = "cancel_requested"`` with
    ``execution_mode = "broker"``.

    Returns 409 if the order is already in a terminal state
    (CANCELLED, FILLED, or REJECTED).
    """
    svc = get_services()
    cancelled_at = datetime.now().isoformat()
    cancellation = svc.cancel_order(order_id, cancelled_at)

    if cancellation["result"] == "terminal":
        return jsonify({
            "error": (
                f"Order '{order_id}' cannot be cancelled "
                f"(current status: {cancellation['status']})"
            ),
        }), 409

    if cancellation["result"] == "not_found":
        return jsonify({"error": f"Order '{order_id}' not found"}), 404

    order = cancellation["order"]
    broker_order_id = order.get("broker_order_id")
    broker_cancel_sent = False
    if broker_order_id is not None:
        broker_cancel_sent = svc.cancel_broker_order(int(broker_order_id))

    if broker_cancel_sent:
        logger.info(
            "Order cancellation forwarded to broker: %s "
            "(broker_order_id=%s)",
            order_id,
            broker_order_id,
        )
        return jsonify({
            "status": "cancel_requested",
            "order_id": order_id,
            "execution_mode": "broker",
            "broker_order_id": broker_order_id,
            "forwarded_to_broker": True,
        })

    if broker_order_id is not None:
        logger.info(
            "Order cancelled locally but broker forwarding was unavailable: %s "
            "(broker_order_id=%s)",
            order_id,
            broker_order_id,
        )
        return jsonify({
            "status": "cancelled",
            "order_id": order_id,
            "execution_mode": "broker",
            "broker_order_id": broker_order_id,
            "forwarded_to_broker": False,
            "warning": (
                "Cancellation was recorded locally, but forwarding to the "
                "broker was not possible."
            ),
        })

    logger.info(
        "Order cancelled locally (not forwarded to broker): %s",
        order_id,
    )
    return jsonify({
        "status": "cancelled",
        "order_id": order_id,
        "execution_mode": "local_only",
        "warning": (
            "Cancellation applied to local record only — "
            "no request was sent to the broker."
        ),
    })
