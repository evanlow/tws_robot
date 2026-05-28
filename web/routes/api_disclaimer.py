"""Disclaimer status and acceptance API.

GET  /api/disclaimer/status  — return whether current version is accepted
POST /api/disclaimer/accept  — record acceptance of the current version
"""

import logging

from flask import Blueprint, jsonify, request

from web.disclaimer import (
    RISK_DISCLAIMER_VERSION,
    get_acceptance_record,
    is_accepted,
    save_acceptance,
)

logger = logging.getLogger(__name__)

bp = Blueprint("api_disclaimer", __name__, url_prefix="/api/disclaimer")


@bp.route("/status", methods=["GET"])
def status():
    """Return disclaimer acceptance status for the current version."""
    accepted = is_accepted()
    record = get_acceptance_record()
    return jsonify(
        {
            "accepted": accepted,
            "current_version": RISK_DISCLAIMER_VERSION,
            "accepted_version": record.get("disclaimer_version"),
            "accepted_at": record.get("accepted_at"),
        }
    )


@bp.route("/accept", methods=["POST"])
def accept():
    """Record acceptance of the Risk & Liability Disclaimer.

    Body (optional)::

        { "app_version": "1.2.3" }
    """
    data = request.get_json(silent=True) or {}
    # Sanitise the user-supplied app_version: keep only safe printable ASCII
    # characters and cap the length to prevent oversized values in the log.
    raw_version = str(data.get("app_version", "unknown"))
    app_version = "".join(
        c for c in raw_version if c.isprintable() and c not in ("\n", "\r", "\x00")
    )[:64] or "unknown"

    try:
        save_acceptance(app_version=app_version)
    except OSError as exc:
        logger.error("Failed to save disclaimer acceptance: %s", exc)
        return jsonify({"error": "Could not persist acceptance record"}), 500

    return jsonify(
        {
            "status": "accepted",
            "disclaimer_version": RISK_DISCLAIMER_VERSION,
        }
    )
