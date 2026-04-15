"""Order management API.

GET    /api/orders       — all orders with status
POST   /api/orders       — submit a manual order
DELETE /api/orders/<id>  — cancel an order
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
def submit_order():
    """Submit a manual order.

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
        return jsonify({"error": "Emergency stop is active — cannot submit orders"}), 403

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
        "status": "SUBMITTED",
        "submitted_at": datetime.now().isoformat(),
        "source": "web_dashboard",
    }

    svc.add_order(order_record)
    logger.info("Manual order submitted: %s", order_record)

    return jsonify({"status": "submitted", "order": order_record}), 201


@bp.route("/<order_id>", methods=["DELETE"])
def cancel_order(order_id: str):
    """Cancel a pending order (mark as CANCELLED in local store)."""
    svc = get_services()
    orders = svc.get_orders()
    for order in orders:
        if order.get("id") == order_id:
            order["status"] = "CANCELLED"
            order["cancelled_at"] = datetime.now().isoformat()
            logger.info("Order cancelled: %s", order_id)
            return jsonify({"status": "cancelled", "order_id": order_id})

    return jsonify({"error": f"Order '{order_id}' not found"}), 404
