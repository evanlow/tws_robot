"""Autonomous Trading API.

JSON endpoints that wrap :class:`autonomous.AutonomousTradingEngine`.

Endpoints:

* ``GET  /api/autonomous/status``       — current config + emergency stop state
* ``POST /api/autonomous/scan``         — non-executing recommendation pass
* ``POST /api/autonomous/propose``      — full ``run_once`` in recommend_only mode
* ``POST /api/autonomous/execute-paper``— full ``run_once`` in paper_execute mode
* ``POST /api/autonomous/emergency-stop`` — create the EMERGENCY_STOP file
* ``GET  /api/autonomous/audit``        — recent audit-log entries (read-only)

The engine itself enforces every safety rule; these routes are thin
adapters that convert HTTP bodies into engine calls and serialise the
decision to JSON.
"""

from __future__ import annotations

import json
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


def _sanitize_config_overrides(overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Return a type-safe subset of request overrides."""
    cleaned: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key == "mode":
            if isinstance(value, str):
                try:
                    cleaned[key] = AutonomousMode(value).value
                except ValueError:
                    continue
        elif key in {"allow_live_execution", "require_user_confirmation"}:
            if isinstance(value, bool):
                cleaned[key] = value
        elif key in {"max_trades_per_day", "min_signal_strength"}:
            if isinstance(value, int) and not isinstance(value, bool):
                cleaned[key] = value
        elif key in {"max_new_position_pct", "min_deployable_cash"}:
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                cleaned[key] = float(value)
        elif key == "required_signal_label":
            if isinstance(value, str):
                cleaned[key] = value
    return cleaned


def _build_engine(config_overrides: Dict[str, Any] | None = None) -> AutonomousTradingEngine:
    """Construct an engine wired to the live ServiceManager.

    Override hooks live in :data:`current_app.config['autonomous_engine_factory']`
    so tests can inject a fully-mocked engine.  When no override is
    registered we build a default engine using a stub
    :class:`StaticSignalProvider` (i.e. the engine returns "no candidate"
    until a real signal provider is wired in) — this keeps the endpoint
    exercising the full safety path without inventing trading signals.

    A paper-execution adapter may optionally be supplied via
    ``current_app.config['autonomous_paper_adapter']``.  When absent,
    ``/execute-paper`` requests still flow through the engine but the
    engine returns ``EXECUTION_FAILED`` with a clear
    ``no paper_adapter configured`` reason instead of silently faking a
    fill.  Operators must wire a real ``PaperTradingAdapter`` (or
    compatible object exposing ``buy()`` / ``sell()``) before
    ``/execute-paper`` will actually place orders.

    .. note::

       **Production signal provider is not yet wired.**  The default
       :class:`StaticSignalProvider` returns no signals, so live
       ``/scan`` / ``/propose`` calls will report ``no_candidate``
       until a real ``Strong(100)`` / ``Confirmed Rebound`` adapter
       (planned name: ``TechnicalAnalysisSignalProvider`` or
       ``StockAnalysisSignalProvider``) is registered as the factory.
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
        for k, v in _sanitize_config_overrides(config_overrides).items():
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
    paper_adapter = current_app.config.get("autonomous_paper_adapter")
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=cash_analyzer,
        account_provider=svc.get_account_summary,
        positions_provider=svc.get_positions,
        orders_provider=svc.get_orders,
        config=base_config,
        risk_manager=getattr(svc, "risk_manager", None),
        paper_adapter=paper_adapter,
    )


# Surfaced in API responses so operators know the live signal pipeline
# is still using the placeholder ``StaticSignalProvider``.  Remove (or
# clear) this notice once a production ``TechnicalAnalysisSignalProvider``
# is wired into :func:`_build_engine`.
SIGNAL_PROVIDER_WARNING = (
    "TODO: production signal provider not yet wired; using "
    "StaticSignalProvider stub. /scan and /propose will return "
    "no_candidate until a Strong(100) / Confirmed Rebound adapter "
    "(planned: TechnicalAnalysisSignalProvider) is registered."
)


def _provider_warning_if_default() -> Dict[str, Any]:
    """Return a ``{"warning": ...}`` dict when the engine is still using
    the default ``StaticSignalProvider``; empty dict otherwise."""
    factory = current_app.config.get("autonomous_engine_factory")
    if callable(factory):
        return {}
    return {"warning": SIGNAL_PROVIDER_WARNING}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/status", methods=["GET"])
def status():
    """Return current configuration + emergency-stop state."""
    config = AutonomousTradingConfig(
        emergency_stop_file=str(EMERGENCY_STOP_FILE),
    ).to_dict()
    payload = {
        "config": config,
        "emergency_stop_file_exists": EMERGENCY_STOP_FILE.exists(),
        "emergency_stop_file": str(EMERGENCY_STOP_FILE),
        "paper_adapter_configured": bool(
            current_app.config.get("autonomous_paper_adapter")
        ),
    }
    payload.update(_provider_warning_if_default())
    return jsonify(payload)


@bp.route("/scan", methods=["POST"])
def scan():
    """Run a non-executing recommendation pass and return scan/rank outputs."""
    body = request.get_json(silent=True) or {}
    overrides = _sanitize_config_overrides(dict(body))
    # Force recommend_only — /scan must never propose or execute.
    overrides["mode"] = AutonomousMode.RECOMMEND_ONLY.value
    engine = _build_engine(overrides)
    decision = engine.run_once(confirm=False)
    payload = {
        "shortlist": decision.shortlist,
        "rejected_candidates": decision.rejected_candidates,
        "deployable_cash": decision.deployable_cash,
        "status": decision.status.value,
        "rejection_reason": decision.rejection_reason,
    }
    payload.update(_provider_warning_if_default())
    return jsonify(payload)


@bp.route("/propose", methods=["POST"])
def propose():
    """Return a full decision in recommend_only mode (no order placed)."""
    body = request.get_json(silent=True) or {}
    overrides = _sanitize_config_overrides(dict(body))
    overrides["mode"] = AutonomousMode.RECOMMEND_ONLY.value
    engine = _build_engine(overrides)
    decision = engine.run_once(confirm=False)
    payload = decision.to_dict()
    payload.update(_provider_warning_if_default())
    return jsonify(payload)


@bp.route("/execute-paper", methods=["POST"])
def execute_paper():
    """Run the engine in paper_execute mode.

    Requires an explicit ``confirm=true`` field in the request body.
    The engine itself also requires a configured paper adapter (registered
    via ``current_app.config['autonomous_paper_adapter']``); without one
    the engine returns ``EXECUTION_FAILED`` rather than silently
    skipping the trade.
    """
    body = request.get_json(silent=True) or {}
    confirm = body.get("confirm") is True
    overrides = _sanitize_config_overrides(dict(body))
    overrides["mode"] = AutonomousMode.PAPER_EXECUTE.value
    engine = _build_engine(overrides)
    decision = engine.run_once(confirm=confirm)
    payload = decision.to_dict()
    payload.update(_provider_warning_if_default())
    return jsonify(payload)


@bp.route("/audit", methods=["GET"])
def audit():
    """Return the most recent autonomous-trading audit entries.

    Reads today's JSONL audit log (plus, if needed, the previous day's
    file) and returns up to ``limit`` of the most recent decisions in
    reverse-chronological order.  This is a read-only endpoint intended
    for the dashboard timeline view.
    """
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    if limit <= 0:
        limit = 20
    if limit > 200:
        limit = 200

    log_dir = Path(
        current_app.config.get("autonomous_audit_log_dir")
        or AutonomousTradingConfig().audit_log_dir
    )
    entries: list[Dict[str, Any]] = []
    if log_dir.exists():
        files = sorted(
            log_dir.glob("autonomous_trading_*.jsonl"),
            reverse=True,
        )
        for path in files:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    file_records: list[Dict[str, Any]] = []
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            file_records.append(json.loads(line))
                        except ValueError:
                            continue
                    # Newest entries are at the end of the file.
                    entries.extend(reversed(file_records))
            except OSError:
                logger.exception("Failed to read autonomous audit log %s", path)
            if len(entries) >= limit:
                break

    summarised: list[Dict[str, Any]] = []
    for record in entries[:limit]:
        decision = record.get("decision") or {}
        selected = decision.get("selected") or {}
        trade_plan = decision.get("trade_plan") or {}
        summarised.append({
            "timestamp": record.get("timestamp") or decision.get("timestamp"),
            "mode": decision.get("mode"),
            "status": decision.get("status"),
            "selected_symbol": selected.get("symbol")
            or trade_plan.get("symbol"),
            "trade_type": trade_plan.get("trade_type"),
            "order_id": decision.get("order_id"),
            "rejection_reason": decision.get("rejection_reason"),
        })

    return jsonify({"entries": summarised, "count": len(summarised)})


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
