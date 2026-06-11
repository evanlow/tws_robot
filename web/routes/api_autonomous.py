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
from collections import deque
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
from autonomous.audit import AuditLogger
from autonomous.autonomous_runner import (
    AutonomousPaperRunner,
    NOT_CONNECTED,
)
from autonomous.autonomous_mode import (
    AutonomousModeState,
    TradingCycle,
    infer_account_type,
    normalise_trading_cycle,
)
from autonomous.exit_manager import AutonomousExitManager
from autonomous.runner_config import AutonomousRunnerConfig
from autonomous.trade_store import FAILED, OPEN, TradeStore
from autonomous.technical_analysis_signal_provider import (
    TechnicalAnalysisSignalProvider,
)
from data.cash_availability import CashAvailabilityAnalyzer
from execution.autonomous_paper_adapter import AutonomousPaperAdapter
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

    scanner = CandidateScanner(signal_provider=_resolve_signal_provider())
    cash_analyzer = CashAvailabilityAnalyzer()
    paper_adapter = _resolve_paper_adapter(svc)
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=cash_analyzer,
        account_provider=svc.get_account_summary,
        positions_provider=svc.get_positions,
        orders_provider=svc.get_orders,
        config=base_config,
        risk_manager=getattr(svc, "risk_manager", None),
        paper_adapter=paper_adapter,
        spy_price_provider=_resolve_spy_price_provider(),
    )


# ---------------------------------------------------------------------------
# Signal provider / paper adapter resolution
# ---------------------------------------------------------------------------

def _resolve_signal_provider():
    """Return the active signal provider, preferring the real one.

    Resolution order:

    1. ``current_app.config['autonomous_signal_provider']`` — explicit
       override (used by tests and operators who want to swap in a
       different production provider).
    2. :class:`TechnicalAnalysisSignalProvider` — production provider
       backed by the S&P 500 screener service.  If construction fails
       for any reason we fall back to the static stub.
    3. :class:`StaticSignalProvider` — placeholder that returns no
       signals.  Surfaces a warning in the ``/status`` payload so the
       dashboard renders ``STATIC PROVIDER``.
    """
    override = current_app.config.get("autonomous_signal_provider")
    if override is not None:
        return override
    provider = TechnicalAnalysisSignalProvider.try_build()
    if provider is not None:
        return provider
    return StaticSignalProvider()


def _resolve_paper_adapter(svc):
    """Return the active paper-execution adapter or ``None``.

    Resolution order:

    1. ``current_app.config['autonomous_paper_adapter']`` — explicit
       override (used by tests and operators who already wired their
       own adapter).
    2. :class:`AutonomousPaperAdapter` wrapping the live service
       manager **only** when it is connected to the IBKR paper account.
       Returning ``None`` when not connected (or connected to live)
       keeps ``/execute-paper`` returning a safe ``execution_failed``
       result instead of placing orders.
    """
    override = current_app.config.get("autonomous_paper_adapter")
    if override is not None:
        return override
    try:
        if (
            getattr(svc, "connected", False)
            and getattr(svc, "connection_env", None) == "paper"
        ):
            adapter = AutonomousPaperAdapter(svc)
            if adapter.is_ready():
                return adapter
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to construct AutonomousPaperAdapter")
    return None


def _signal_provider_info(provider) -> Dict[str, Any]:
    """Describe the active signal provider for ``/status`` responses."""
    name = type(provider).__name__
    is_real = not isinstance(provider, StaticSignalProvider)
    info: Dict[str, Any] = {
        "signal_provider": name,
        "signal_provider_ready": is_real,
    }
    if not is_real:
        info["warning"] = SIGNAL_PROVIDER_WARNING
    return info


# Surfaced in API responses so operators know the live signal pipeline
# is still using the placeholder ``StaticSignalProvider``.  Remove (or
# clear) this notice once a production ``TechnicalAnalysisSignalProvider``
# is wired into :func:`_build_engine`.
SIGNAL_PROVIDER_WARNING = (
    "Production signal provider not wired; using StaticSignalProvider "
    "stub. /scan and /propose will return no_candidate until the "
    "TechnicalAnalysisSignalProvider (or another real adapter) is "
    "registered via current_app.config['autonomous_signal_provider']."
)

BEARISH_SPY_MESSAGE = (
    "Autonomous Mode strategy doesn't work well in current bearish market. "
    "Terminating Autonomous Mode."
)


def _provider_warning_if_default() -> Dict[str, Any]:
    """Return a ``{"warning": ...}`` dict when the active provider is the
    fallback stub; empty dict otherwise.

    When an ``autonomous_engine_factory`` is registered we trust the
    operator wired a real provider and suppress the stub warning.
    """
    factory = current_app.config.get("autonomous_engine_factory")
    if callable(factory):
        return {}
    provider = _resolve_signal_provider()
    if not isinstance(provider, StaticSignalProvider):
        return {}
    return {"warning": SIGNAL_PROVIDER_WARNING}


def _mode_state() -> AutonomousModeState:
    state = current_app.config.get("autonomous_mode_state")
    if isinstance(state, AutonomousModeState):
        return state
    state = AutonomousModeState()
    current_app.config["autonomous_mode_state"] = state
    return state


def force_autonomous_mode_off(message: str | None = None, status: str = "Not Ready") -> None:
    """Public helper for connection routes to enforce default-OFF safety."""

    try:
        _mode_state().turn_off(message=message, status=status)
    except RuntimeError:
        # No Flask app context; callers without one cannot own dashboard state.
        return


def _audit_mode_event(event: str, payload: Dict[str, Any] | None = None) -> None:
    log_dir = Path(
        current_app.config.get("autonomous_audit_log_dir")
        or AutonomousTradingConfig().audit_log_dir
    )
    AuditLogger(log_dir=str(log_dir)).log_decision({
        "engine": "AutonomousModeController",
        "event": event,
        "payload": payload or {},
    })


def _resolve_spy_price_provider():
    override = current_app.config.get("autonomous_spy_price_provider")
    if callable(override):
        return override
    return None


def _connection_verification_payload(svc) -> Dict[str, Any]:
    selected = getattr(svc, "connection_env", None)
    info = getattr(svc, "connection_info", {}) or {}
    actual = (
        current_app.config.get("autonomous_actual_account_type")
        or infer_account_type(info.get("account"))
    )
    if not selected or not actual:
        match = "Unknown"
    elif selected == actual:
        match = "Verified"
    else:
        match = "Mismatch"
    return {
        "selected_connection_type": selected,
        "running_account_type": actual,
        "paper_live_match_status": match,
    }


def _autonomous_status_payload() -> Dict[str, Any]:
    svc = get_services()
    runner = _build_runner()
    gates = runner.evaluate_gates()
    state = _mode_state()
    verification = _connection_verification_payload(svc)
    connected = bool(getattr(svc, "connected", False))

    if (
        state.is_on
        and (not connected or verification["paper_live_match_status"] == "Mismatch"
             or gates.emergency_stop_active)
    ):
        state.turn_off(
            message="Autonomous Mode turned OFF by connection/safety state change.",
            status="Halted" if gates.emergency_stop_active else "Not Ready",
        )

    readiness = state.readiness_status
    if not state.is_on and gates.emergency_stop_active:
        readiness = "Halted"
    elif not state.is_on and gates.ready and verification["paper_live_match_status"] == "Verified":
        readiness = "Ready"
    elif not state.is_on:
        readiness = "Not Ready"
    state.readiness_status = readiness
    state.refresh()

    return {
        "mode": state.to_dict(),
        "connection": {
            "connected": connected,
            "status": "Connected" if connected else "Disconnected",
            **verification,
        },
        "readiness": {
            "status": readiness,
            "message": state.message,
            "gates": gates.to_dict(),
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/status", methods=["GET"])
def status():
    """Return current configuration + emergency-stop state."""
    config = AutonomousTradingConfig(
        emergency_stop_file=str(EMERGENCY_STOP_FILE),
    ).to_dict()
    svc = get_services()
    provider = _resolve_signal_provider()
    paper_adapter = _resolve_paper_adapter(svc)

    payload: Dict[str, Any] = {
        "config": config,
        "emergency_stop_file_exists": EMERGENCY_STOP_FILE.exists(),
        "emergency_stop_file": str(EMERGENCY_STOP_FILE),
        "paper_adapter_configured": paper_adapter is not None,
        "connection_env": getattr(svc, "connection_env", None),
        "connected": bool(getattr(svc, "connected", False)),
    }
    payload.update(_signal_provider_info(provider))
    payload["autonomous_mode"] = _autonomous_status_payload()

    # Helpful reason string so the dashboard can explain why paper
    # execution is disabled even when the user hasn't tried clicking yet.
    if not payload["paper_adapter_configured"]:
        if not payload["connected"]:
            payload["paper_adapter_reason"] = (
                "Connect to IBKR paper mode to enable paper execution."
            )
        elif payload["connection_env"] != "paper":
            env_name = payload["connection_env"] or "unknown"
            payload["paper_adapter_reason"] = (
                f"Connected to {env_name} mode; paper execution requires "
                "the paper account."
            )
        else:
            payload["paper_adapter_reason"] = (
                "Paper TWS bridge not ready yet; retry once the connection "
                "handshake completes."
            )

    # Include a cash snapshot so the Deployable Cash panel populates on
    # page load / Refresh Status without needing a full scan/propose run.
    if payload["connected"]:
        try:
            cash_analyzer = CashAvailabilityAnalyzer()
            cash_result = cash_analyzer.analyze(
                account_summary=svc.get_account_summary(),
                positions=svc.get_positions(),
                orders=svc.get_orders(),
            )
            payload["cash_snapshot"] = cash_result.to_dict()
        except Exception:
            pass  # Non-critical — dashboard keeps showing dashes if unavailable

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

    Scans audit log files matching ``autonomous_trading_*.jsonl`` in
    newest-file-first order and returns up to ``limit`` of the most
    recent decisions in reverse-chronological order. This is a
    read-only endpoint intended for the dashboard timeline view.
    """
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    if limit <= 0:
        limit = 1
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
                    remaining = limit - len(entries)
                    if remaining <= 0:
                        break
                    file_records = deque(maxlen=remaining)
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

    force_autonomous_mode_off(
        message="Emergency stop active. Autonomous Mode has been turned OFF.",
        status="Halted",
    )
    _audit_mode_event("halt", {"reason": reason, "source": "emergency_stop"})

    return jsonify({
        "status": "halted",
        "emergency_stop_file": str(EMERGENCY_STOP_FILE),
        "reason": reason,
    })


# ---------------------------------------------------------------------------
# Paper-only autonomous runner
# ---------------------------------------------------------------------------


@bp.route("/mode/status", methods=["GET"])
def autonomous_mode_status():
    """Return the binary user-facing Autonomous Mode status."""

    return jsonify(_autonomous_status_payload())


@bp.route("/mode/activate", methods=["POST"])
def autonomous_mode_activate():
    """Turn Autonomous Mode ON after readiness checks and run one lifecycle."""

    body = request.get_json(silent=True) or {}
    cycle = normalise_trading_cycle(body.get("trading_cycle"))
    if cycle is None:
        return jsonify({"error": "trading_cycle must be single_trade or continuous"}), 400

    status_payload = _autonomous_status_payload()
    connection = status_payload["connection"]
    if connection["paper_live_match_status"] != "Verified":
        msg = "Paper/Live connection match is not verified."
        _mode_state().turn_off(message=msg, status="Not Ready")
        return jsonify({"status": "rejected", "error": msg, **status_payload}), 409

    gates = status_payload["readiness"]["gates"]
    if not gates.get("ready"):
        msg = "; ".join(gates.get("reasons") or []) or "Autonomous readiness checks failed"
        _mode_state().turn_off(message=msg, status="Not Ready")
        return jsonify({"status": "rejected", "error": msg, **status_payload}), 409

    state = _mode_state()
    state.turn_on(cycle)
    _audit_mode_event("activate", {"trading_cycle": cycle.value})

    result = _build_runner().run_once()
    payload = result.to_dict()
    decision = payload.get("decision") or {}
    if decision.get("status") == "market_not_suitable":
        state.turn_off(message=BEARISH_SPY_MESSAGE, status="Halted")
        _audit_mode_event("halt", {"reason": BEARISH_SPY_MESSAGE, "source": "spy_gate"})
    elif payload.get("status") == "no_trade" and cycle == TradingCycle.SINGLE_TRADE:
        message = payload.get("rejection_reason") or "No trade. Autonomous Mode has been turned OFF."
        state.turn_off(message=message, status="Not Ready")
        _audit_mode_event("halt", {"reason": message, "source": "single_trade_no_trade"})

    return jsonify({
        "status": "activated" if state.is_on else "halted",
        "run": payload,
        "autonomous_mode": _autonomous_status_payload(),
    })


@bp.route("/mode/halt", methods=["POST"])
def autonomous_mode_halt():
    """Turn Autonomous Mode OFF without liquidating positions."""

    body = request.get_json(silent=True) or {}
    reason = str(body.get("reason") or "Operator turned Autonomous Mode OFF")
    _mode_state().turn_off(message=reason, status="Halted")
    _audit_mode_event("halt", {"reason": reason, "source": "operator"})
    return jsonify({"status": "halted", "autonomous_mode": _autonomous_status_payload()})

def _runner_config() -> AutonomousRunnerConfig:
    """Return the active runner config.

    Tests / operators can register a fully constructed
    :class:`AutonomousRunnerConfig` via
    ``current_app.config['autonomous_runner_config']`` to enable the
    runner.  The default config has ``runner_enabled=False`` which the
    runner enforces — ``/runner/run-once-paper`` will safely refuse to
    act unless explicitly enabled.
    """
    cfg = current_app.config.get("autonomous_runner_config")
    if isinstance(cfg, AutonomousRunnerConfig):
        return cfg
    return AutonomousRunnerConfig.from_env()


def _trade_store() -> TradeStore:
    """Return a shared :class:`TradeStore` instance."""
    store = current_app.config.get("autonomous_trade_store")
    if isinstance(store, TradeStore):
        return store
    store = TradeStore(path=_runner_config().trade_store_path)
    current_app.config["autonomous_trade_store"] = store
    return store


def _build_runner() -> AutonomousPaperRunner:
    """Construct an :class:`AutonomousPaperRunner` wired to the live app."""
    override = current_app.config.get("autonomous_runner_factory")
    if callable(override):
        return override()

    svc = get_services()
    runner_config = _runner_config()
    engine = _build_engine({"mode": AutonomousMode.PAPER_EXECUTE.value})

    def _connected() -> bool:
        return bool(getattr(svc, "connected", False))

    def _env():
        return getattr(svc, "connection_env", None)

    def _adapter():
        return _resolve_paper_adapter(svc)

    def _provider():
        return _resolve_signal_provider()

    def _estop() -> bool:
        try:
            return EMERGENCY_STOP_FILE.exists()
        except OSError:  # pragma: no cover - defensive
            return False

    return AutonomousPaperRunner(
        engine=engine,
        trade_store=_trade_store(),
        runner_config=runner_config,
        connected_provider=_connected,
        connection_env_provider=_env,
        paper_adapter_provider=_adapter,
        signal_provider_provider=_provider,
        emergency_stop_provider=_estop,
    )


def _build_exit_manager() -> AutonomousExitManager:
    override = current_app.config.get("autonomous_exit_manager_factory")
    if callable(override):
        return override()
    svc = get_services()
    return AutonomousExitManager(
        trade_store=_trade_store(),
        paper_adapter=_resolve_paper_adapter(svc),
        positions_provider=svc.get_positions,
        risk_manager=getattr(svc, "risk_manager", None),
        emergency_stop_file=str(EMERGENCY_STOP_FILE),
    )


def _cancel_entry_order(order_id: int) -> bool:
    """Forward an entry-order cancellation to the broker.

    Supports a test override via ``current_app.config['autonomous_cancel_order']``.
    """
    override = current_app.config.get("autonomous_cancel_order")
    if callable(override):
        try:
            return bool(override(int(order_id)))
        except Exception:  # pragma: no cover - defensive
            logger.exception("autonomous_cancel_order override raised")
            return False
    svc = get_services()
    return bool(svc.cancel_broker_order(int(order_id)))


@bp.route("/runner/status", methods=["GET"])
def runner_status():
    """Return runner config and current readiness gates."""
    runner = _build_runner()
    gates = runner.evaluate_gates()
    return jsonify({
        "runner_config": runner.config.to_dict(),
        "gates": gates.to_dict(),
        "open_autonomous_trades": gates.open_autonomous_trades,
    })


@bp.route("/runner/run-once-paper", methods=["POST"])
def runner_run_once_paper():
    """Run one full paper-autonomous cycle.  Paper-only; never live."""
    runner = _build_runner()
    result = runner.run_once()
    return jsonify(result.to_dict())


@bp.route("/runner/evaluate-exits", methods=["POST"])
def runner_evaluate_exits():
    """Evaluate every open autonomous trade and submit paper SELL exits."""
    manager = _build_exit_manager()
    decisions = manager.evaluate_open_trades()
    return jsonify({
        "decisions": [d.to_dict() for d in decisions],
        "count": len(decisions),
    })


@bp.route("/runner/cancel-entry", methods=["POST"])
def runner_cancel_entry():
    """Cancel an OPEN autonomous entry order and close its lifecycle record.

    Request body:
        {"autonomous_trade_id": "..."}

    This endpoint forwards a cancel request to the broker for the trade's
    ``entry_order_id``. On successful forwarding, the trade lifecycle is moved
    from ``OPEN`` to ``FAILED`` with ``exit_reason='ENTRY_CANCELLED'`` so the
    open-trade gate can clear immediately.
    """
    body = request.get_json(silent=True) or {}
    trade_id = str(body.get("autonomous_trade_id") or "").strip()
    if not trade_id:
        return jsonify({"error": "autonomous_trade_id is required"}), 400

    store = _trade_store()
    trade = store.get(trade_id)
    if trade is None:
        return jsonify({"error": f"Autonomous trade '{trade_id}' not found"}), 404

    if str(trade.status) != OPEN:
        return jsonify({
            "error": (
                f"Autonomous trade '{trade_id}' is not OPEN "
                f"(current status: {trade.status})"
            ),
        }), 409

    order_id = int(getattr(trade, "entry_order_id", 0) or 0)
    if order_id <= 0:
        return jsonify({
            "error": (
                f"Autonomous trade '{trade_id}' has no valid entry_order_id "
                "to cancel"
            ),
        }), 409

    forwarded = _cancel_entry_order(order_id)
    if not forwarded:
        return jsonify({
            "status": "cancel_not_forwarded",
            "autonomous_trade_id": trade_id,
            "entry_order_id": order_id,
            "forwarded_to_broker": False,
            "warning": (
                "Cancellation was not forwarded to broker. Trade remains OPEN."
            ),
        }), 503

    notes = list(getattr(trade, "notes", []) or [])
    notes.append("entry cancel requested by operator")
    store.update_trade(
        trade_id,
        status=FAILED,
        exit_reason="ENTRY_CANCELLED",
        exit_time=datetime.now(timezone.utc),
        notes=notes,
    )

    return jsonify({
        "status": "cancel_requested",
        "autonomous_trade_id": trade_id,
        "entry_order_id": order_id,
        "forwarded_to_broker": True,
        "trade_status": FAILED,
        "message": (
            "Cancel request forwarded to broker. "
            "Autonomous trade lifecycle marked FAILED (ENTRY_CANCELLED)."
        ),
    })


@bp.route("/runner/trades", methods=["GET"])
def runner_trades():
    """Return open and recently-closed autonomous trades."""
    store = _trade_store()
    trades = store.list_all()
    open_trades = [t.to_dict() for t in trades if t.status == "OPEN"]
    exit_pending = [t.to_dict() for t in trades if t.status == "EXIT_PENDING"]
    closed = [t.to_dict() for t in trades if t.status in ("CLOSED", "FAILED")]
    return jsonify({
        "open": open_trades,
        "exit_pending": exit_pending,
        "closed": closed,
        "counts": {
            "open": len(open_trades),
            "exit_pending": len(exit_pending),
            "closed": len(closed),
            "total": len(trades),
        },
    })
