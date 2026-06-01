"""Autonomous Trading API.

JSON endpoints that wrap :class:`autonomous.AutonomousTradingEngine`.

Endpoints:

* ``GET  /api/autonomous/status``       — current config + emergency stop state
* ``POST /api/autonomous/scan``         — scan + rank only, no plan, no order
* ``POST /api/autonomous/propose``      — full ``run_once`` in recommend_only mode
* ``POST /api/autonomous/execute-paper``— full ``run_once`` in paper_execute mode
* ``POST /api/autonomous/emergency-stop`` — create the EMERGENCY_STOP file

The engine itself enforces every safety rule; these routes are thin
adapters that convert HTTP bodies into engine calls and serialise the
decision to JSON.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request

from autonomous import (
    AutonomousMode,
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    StaticSignalProvider,
)
from data.cash_availability import CashAvailabilityAnalyzer
from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_autonomous", __name__, url_prefix="/api/autonomous")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Same default location as web.routes.api_emergency.EMERGENCY_STOP_FILE.
EMERGENCY_STOP_FILE = Path(
    os.environ.get(
        "EMERGENCY_STOP_FILE",
        str(Path(__file__).resolve().parent.parent.parent / "EMERGENCY_STOP"),
    )
)


def _build_engine(config_overrides: Dict[str, Any] | None = None) -> AutonomousTradingEngine:
    """Construct an engine wired to the live ServiceManager.

    Override hooks live in :data:`current_app.config['autonomous_engine_factory']`
    so tests can inject a fully-mocked engine.  When no override is
    registered we build a default engine using a stub
    :class:`StaticSignalProvider` (i.e. the engine returns "no candidate"
    until a real signal provider is wired in) — this keeps the endpoint
    exercising the full safety path without inventing trading signals.
    """
    factory = current_app.config.get("autonomous_engine_factory")
    if callable(factory):
        return factory(config_overrides or {})

    svc = get_services()
    base_config = AutonomousTradingConfig()
    if config_overrides:
        # Only allow whitelisted overrides from HTTP requests — operators
        # can switch mode and live-flag through the dashboard, but the
        # request body is never trusted to widen the emergency-stop file.
        allowed = {
            "mode",
            "allow_live_execution",
            "require_user_confirmation",
            "max_trades_per_day",
            "max_new_position_pct",
            "min_deployable_cash",
            "min_signal_strength",
            "required_signal_label",
        }
        kwargs = base_config.to_dict()
        for k, v in config_overrides.items():
            if k in allowed:
                kwargs[k] = v
        kwargs.pop("audit_log_dir", None)
        kwargs.pop("emergency_stop_file", None)
        base_config = AutonomousTradingConfig(**{
            **kwargs,
            "audit_log_dir": AutonomousTradingConfig().audit_log_dir,
            "emergency_stop_file": str(EMERGENCY_STOP_FILE),
        })
    else:
        base_config = AutonomousTradingConfig(
            emergency_stop_file=str(EMERGENCY_STOP_FILE),
        )

    scanner = CandidateScanner(signal_provider=StaticSignalProvider())
    cash_analyzer = CashAvailabilityAnalyzer()
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=cash_analyzer,
        account_provider=svc.get_account_summary,
        positions_provider=svc.get_positions,
        orders_provider=lambda: list(getattr(svc, "_orders", []) or []),
        config=base_config,
        risk_manager=getattr(svc, "risk_manager", None),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/status", methods=["GET"])
def status():
    """Return current configuration + emergency-stop state."""
    config = AutonomousTradingConfig().to_dict()
    return jsonify({
        "config": config,
        "emergency_stop_file_exists": EMERGENCY_STOP_FILE.exists(),
        "emergency_stop_file": str(EMERGENCY_STOP_FILE),
    })


@bp.route("/scan", methods=["POST"])
def scan():
    """Run scan + ranking without generating a trade plan."""
    body = request.get_json(silent=True) or {}
    overrides = dict(body)
    # Force recommend_only — /scan must never propose or execute.
    overrides["mode"] = AutonomousMode.RECOMMEND_ONLY.value
    engine = _build_engine(overrides)
    decision = engine.run_once(confirm=False)
    return jsonify({
        "shortlist": decision.shortlist,
        "rejected_candidates": decision.rejected_candidates,
        "deployable_cash": decision.deployable_cash,
        "status": decision.status.value,
        "rejection_reason": decision.rejection_reason,
    })


@bp.route("/propose", methods=["POST"])
def propose():
    """Return a full decision in recommend_only mode (no order placed)."""
    body = request.get_json(silent=True) or {}
    overrides = dict(body)
    overrides["mode"] = AutonomousMode.RECOMMEND_ONLY.value
    engine = _build_engine(overrides)
    decision = engine.run_once(confirm=False)
    return jsonify(decision.to_dict())


@bp.route("/execute-paper", methods=["POST"])
def execute_paper():
    """Run the engine in paper_execute mode.

    Requires an explicit ``confirm=true`` field in the request body.
    The engine itself also requires a configured paper adapter.
    """
    body = request.get_json(silent=True) or {}
    confirm = bool(body.get("confirm", False))
    overrides = dict(body)
    overrides["mode"] = AutonomousMode.PAPER_EXECUTE.value
    engine = _build_engine(overrides)
    decision = engine.run_once(confirm=confirm)
    return jsonify(decision.to_dict())


@bp.route("/emergency-stop", methods=["POST"])
def emergency_stop():
    """Create the EMERGENCY_STOP file so subsequent runs are blocked."""
    body = request.get_json(silent=True) or {}
    reason = body.get("reason", "Autonomous emergency stop")
    try:
        EMERGENCY_STOP_FILE.write_text(
            f"EMERGENCY STOP - {reason}\n"
            f"Triggered: {datetime.now(timezone.utc).isoformat()}\n"
        )
    except OSError:
        logger.exception("Failed to write EMERGENCY_STOP file")
        return jsonify({
            "status": "error",
            "error": "Failed to write emergency stop file",
        }), 500

    return jsonify({
        "status": "halted",
        "emergency_stop_file": str(EMERGENCY_STOP_FILE),
        "reason": reason,
    })
