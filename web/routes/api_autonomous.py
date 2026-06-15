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
from typing import Any, Dict, Optional

from flask import Blueprint, current_app, jsonify, request

from autonomous import (
    AutonomousMode,
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    StaticSignalProvider,
)
from autonomous.audit import AuditLogger
from autonomous.autonomous_live_runner import (
    AutonomousLiveRunner,
    EXECUTED as LIVE_EXECUTED,
    DRY_RUN_EXECUTED,
    NOT_CONNECTED as LIVE_NOT_CONNECTED,
    NOT_LIVE_MODE,
    LIVE_DISABLED,
    LIVE_CONTINUOUS_DISABLED,
)
from autonomous.autonomous_runner import (
    AutonomousPaperRunner,
    NOT_CONNECTED,
)
from autonomous.autonomous_mode import (
    AccountMode,
    AutonomousDisplayMode,
    AutonomousModeState,
    TradingCycle,
    infer_account_type,
    normalise_trading_cycle,
)
from autonomous.exit_manager import AutonomousExitManager
from autonomous.runner_config import AutonomousRunnerConfig, AutonomousLiveRunnerConfig
from autonomous.trade_store import CLOSED, EXIT_PENDING, FAILED, OPEN, TradeStore
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
        elif key == "exit_target_mode":
            if isinstance(value, str) and value in (
                "resistance", "percent", "adr_intraday"
            ):
                cleaned[key] = value
        elif key in {
            "take_profit_pct",
            "adr_target_fraction",
            "adr_max_target_pct",
            "adr_min_target_pct",
        }:
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and float(value) > 0
            ):
                cleaned[key] = float(value)
        elif key == "adr_lookback_days":
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                cleaned[key] = value
        elif key == "adr_respect_resistance_cap":
            if isinstance(value, bool):
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

    # --- Read ADR / exit-target settings from environment ----------------
    env_config_kwargs: Dict[str, Any] = {}
    _exit_mode = os.environ.get("AUTONOMOUS_EXIT_TARGET_MODE", "").strip().lower()
    if _exit_mode in ("resistance", "percent", "adr_intraday"):
        env_config_kwargs["exit_target_mode"] = _exit_mode

    for env_key, config_key, converter, default in [
        ("AUTONOMOUS_TAKE_PROFIT_PCT", "take_profit_pct", float, None),
        ("AUTONOMOUS_ADR_LOOKBACK_DAYS", "adr_lookback_days", int, None),
        ("AUTONOMOUS_ADR_TARGET_FRACTION", "adr_target_fraction", float, None),
        ("AUTONOMOUS_ADR_MAX_TARGET_PCT", "adr_max_target_pct", float, None),
        ("AUTONOMOUS_ADR_MIN_TARGET_PCT", "adr_min_target_pct", float, None),
    ]:
        raw = os.environ.get(env_key, "").strip()
        if raw:
            try:
                val = converter(raw)
                if val > 0:
                    env_config_kwargs[config_key] = val
            except (ValueError, TypeError):
                pass  # Invalid env value — use dataclass default

    _adr_resist_raw = os.environ.get(
        "AUTONOMOUS_ADR_RESPECT_RESISTANCE_CAP", ""
    ).strip().lower()
    if _adr_resist_raw in ("true", "1", "yes", "on"):
        env_config_kwargs["adr_respect_resistance_cap"] = True
    elif _adr_resist_raw in ("false", "0", "no", "off"):
        env_config_kwargs["adr_respect_resistance_cap"] = False

    base_config = AutonomousTradingConfig(
        emergency_stop_file=str(EMERGENCY_STOP_FILE),
        **env_config_kwargs,
    )

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
            "exit_target_mode",
            "take_profit_pct",
            "adr_lookback_days",
            "adr_target_fraction",
            "adr_max_target_pct",
            "adr_min_target_pct",
            "adr_respect_resistance_cap",
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


def _spy_price_from_yfinance() -> Dict[str, Any]:
    """Fetch SPY day-open and current price via yfinance.

    Fails closed: returns zero prices when data is unavailable,
    which the engine treats as bearish (not suitable) and blocks trading.
    """
    try:
        import yfinance as yf  # type: ignore[import]
        ticker = yf.Ticker("SPY")
        fast_info = ticker.fast_info
        open_price = float(getattr(fast_info, "open", 0.0) or 0.0)
        current_price = float(getattr(fast_info, "last_price", 0.0) or 0.0)
        if open_price > 0 and current_price > 0:
            return {"open": open_price, "current": current_price}
        # Fall back to intraday history if fast_info returns zeros
        hist = ticker.history(period="1d")
        if not hist.empty:
            open_price = float(hist["Open"].iloc[0])
            current_price = float(hist["Close"].iloc[-1])
            return {"open": open_price, "current": current_price}
    except Exception:
        logger.exception("Failed to fetch SPY price from yfinance")
    # Fail closed: zero prices → engine classifies as Bearish / Not Suitable
    return {"open": 0.0, "current": 0.0, "error": "SPY data unavailable — failing closed"}


def _resolve_spy_price_provider():
    override = current_app.config.get("autonomous_spy_price_provider")
    if callable(override):
        return override
    # Default: always wire the yfinance provider so the SPY gate is never
    # skipped in production.  Fails closed when market data is unavailable.
    #
    # NOTE: yfinance is a third-party source and may differ slightly from
    # TWS/IBKR broker data.  It is used here as a reliable, zero-config
    # default.  Wiring the provider to a TWS reqMktData snapshot is preferred
    # for production and can be done by registering an override via
    # ``current_app.config['autonomous_spy_price_provider']``.
    return _spy_price_from_yfinance


def _connection_verification_payload(svc) -> Dict[str, Any]:
    selected = getattr(svc, "connection_env", None)
    info = getattr(svc, "connection_info", {}) or {}
    account_id = str(info.get("account") or "").strip()
    actual = (
        current_app.config.get("autonomous_actual_account_type")
        or infer_account_type(account_id)
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
        "running_account_id": account_id,
        "paper_live_match_status": match,
    }


def _autonomous_status_payload() -> Dict[str, Any]:
    svc = get_services()
    runner = _build_runner()
    gates = runner.evaluate_gates()
    state = _mode_state()
    verification = _connection_verification_payload(svc)
    connected = bool(getattr(svc, "connected", False))
    match_status = verification["paper_live_match_status"]

    # Force mode OFF for any safety-critical gate failure while mode is ON.
    # Handled explicitly per-case so that max_open_trades_reached (a normal
    # operational state during an active trade lifecycle) does NOT trigger a
    # spurious shutdown.
    _infrastructure_gate_failed = (
        not gates.runner_enabled
        or not gates.paper_adapter_ready
        or not gates.signal_provider_ready
    )
    if state.is_on and (
        not connected
        or match_status != "Verified"
        or gates.emergency_stop_active
        or _infrastructure_gate_failed
    ):
        if gates.emergency_stop_active:
            off_status = "Halted"
            off_message = "Autonomous Mode turned OFF: emergency stop active."
        elif not connected or match_status != "Verified":
            off_status = "Not Ready"
            off_message = "Autonomous Mode turned OFF by connection/safety state change."
        else:
            failure_reason = "; ".join(gates.reasons()) or "Infrastructure readiness gate failed"
            off_status = "Not Ready"
            off_message = f"Autonomous Mode turned OFF: {failure_reason}"
        state.turn_off(message=off_message, status=off_status)

    # Advance Single Trade lifecycle: if all trades opened since activation
    # have closed, turn Autonomous Mode OFF automatically.
    if (
        state.is_on
        and state.cycles_started > 0
        and state.trading_cycle == TradingCycle.SINGLE_TRADE
    ):
        _advance_single_trade_if_complete(state)

    readiness = state.readiness_status
    if not state.is_on and gates.emergency_stop_active:
        readiness = "Halted"
    elif not state.is_on and gates.ready and match_status == "Verified":
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


def _trades_since_activation(state: "AutonomousModeState"):
    """Return all trades opened at or after the current mode activation time.

    Returns an empty list when ``activated_at`` is not set or the store
    cannot be read.  Callers must guard against empty results.
    """
    activated_at_str = state.activated_at
    if not activated_at_str:
        return []
    activated_at = datetime.fromisoformat(activated_at_str)
    return [
        t for t in _trade_store().list_all()
        if t.entry_time >= activated_at
    ]


def _advance_single_trade_if_complete(state: "AutonomousModeState") -> None:
    """Turn Autonomous Mode OFF if every trade opened since activation is closed.

    Safe to call repeatedly; does nothing when:
    - ``activated_at`` is not set
    - no trade has been placed since activation
    - at least one trade is still OPEN or EXIT_PENDING

    Callers are responsible for ensuring mode is ON, ``cycles_started > 0``,
    and ``trading_cycle == SINGLE_TRADE`` before calling this function.
    """
    try:
        since_activation = _trades_since_activation(state)
        if not since_activation:
            return  # No trade placed yet in this activation
        still_active = [t for t in since_activation if t.status in (OPEN, EXIT_PENDING)]
        if still_active:
            return  # Trade lifecycle still in progress
        # All trades since activation are CLOSED or FAILED → lifecycle done
        state.turn_off(
            message="Single Trade lifecycle completed. Autonomous Mode turned OFF.",
            status="Ready",
        )
        _audit_mode_event("halt", {"reason": "single_trade_completed", "source": "lifecycle"})
    except Exception:
        logger.exception("Single trade completion check failed")


def _maybe_advance_lifecycle() -> None:
    """Advance the autonomous lifecycle after exit evaluation completes.

    **This function is poll/evaluate-driven, not a background loop.**  It is
    called exclusively from the ``/runner/evaluate-exits`` endpoint.  The
    operator (or a scheduler) must call that endpoint periodically to advance
    the lifecycle.  Continuous Trading does *not* loop on its own; each new
    cycle begins only after an explicit evaluate-exits call returns with all
    prior trades closed.

    Does nothing when mode is OFF or ``cycles_started == 0`` (no lifecycle
    has been started yet).

    For Single Trade: delegates to ``_advance_single_trade_if_complete``,
    which turns mode OFF once all trades are closed.

    For Continuous Trading: if every trade since activation is closed,
    rechecks the SPY gate and starts the next cycle.  Turns mode OFF if
    SPY is bearish or the runner raises an error.
    """
    state = _mode_state()
    if not state.is_on or state.cycles_started == 0:
        return

    try:
        since_activation = _trades_since_activation(state)
        if not since_activation:
            return  # No trade placed yet
        still_active = [t for t in since_activation if t.status in (OPEN, EXIT_PENDING)]
        if still_active:
            return  # Lifecycle still in progress

        cycle = state.trading_cycle
        if cycle == TradingCycle.SINGLE_TRADE:
            _advance_single_trade_if_complete(state)
        elif cycle == TradingCycle.CONTINUOUS:
            # Recheck SPY gate and start next cycle
            try:
                result = _build_runner().run_once()
                state.cycles_started += 1
                _audit_mode_event(
                    "continuous_cycle",
                    {"cycles_started": state.cycles_started},
                )
                r_payload = result.to_dict()
                decision = r_payload.get("decision") or {}
                if decision.get("status") == "market_not_suitable":
                    state.turn_off(message=BEARISH_SPY_MESSAGE, status="Halted")
                    _audit_mode_event(
                        "halt",
                        {"reason": BEARISH_SPY_MESSAGE, "source": "spy_gate_continuous"},
                    )
            except Exception:
                logger.exception("Continuous lifecycle cycle failed")
                state.turn_off(
                    message="Continuous lifecycle error. Autonomous Mode turned OFF.",
                    status="Halted",
                )
    except Exception:
        logger.exception("Lifecycle advancement check failed")


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
    """Turn Autonomous Mode ON after readiness checks and run one lifecycle.

    Requires ``{"confirm": true}`` in the request body to prevent accidental
    activation via direct API calls.
    """

    body = request.get_json(silent=True) or {}

    # Explicit confirmation flag required — mirrors the confirm pattern used
    # by /execute-paper to prevent accidental lifecycle invocation.
    if body.get("confirm") is not True:
        return jsonify({
            "error": "confirm must be true to activate Autonomous Mode",
            "status": "confirmation_required",
        }), 400

    cycle = normalise_trading_cycle(body.get("trading_cycle"))
    if cycle is None:
        return jsonify({"error": "trading_cycle must be single_trade or continuous"}), 400

    status_payload = _autonomous_status_payload()
    connection = status_payload["connection"]
    if connection["paper_live_match_status"] != "Verified":
        msg = "Paper/Live connection match is not verified."
        _mode_state().turn_off(message=msg, status="Not Ready")
        # Re-fetch after state change so the response is not stale.
        return jsonify({"status": "rejected", "error": msg,
                        **_autonomous_status_payload()}), 409

    gates = status_payload["readiness"]["gates"]
    if not gates.get("ready"):
        msg = "; ".join(gates.get("reasons") or []) or "Autonomous readiness checks failed"
        _mode_state().turn_off(message=msg, status="Not Ready")
        return jsonify({"status": "rejected", "error": msg,
                        **_autonomous_status_payload()}), 409

    state = _mode_state()
    state.turn_on(cycle, AccountMode.PAPER)
    _audit_mode_event("activate", {"trading_cycle": cycle.value, "account_mode": "paper"})

    try:
        result = _build_runner().run_once()
        state.cycles_started += 1
        payload = result.to_dict()
        decision = payload.get("decision") or {}
        if decision.get("status") == "market_not_suitable":
            state.turn_off(message=BEARISH_SPY_MESSAGE, status="Halted")
            _audit_mode_event("halt", {"reason": BEARISH_SPY_MESSAGE, "source": "spy_gate"})
        elif payload.get("status") == "no_trade" and cycle == TradingCycle.SINGLE_TRADE:
            message = (
                payload.get("rejection_reason")
                or "No trade. Autonomous Mode has been turned OFF."
            )
            state.turn_off(message=message, status="Not Ready")
            _audit_mode_event("halt", {"reason": message, "source": "single_trade_no_trade"})
    except Exception:
        logger.exception("Autonomous lifecycle run failed after activation")
        state.turn_off(
            message="Lifecycle run failed. Autonomous Mode turned OFF.",
            status="Halted",
        )
        _audit_mode_event("halt", {"reason": "lifecycle_run_exception", "source": "activate"})
        payload = {}

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
    """Run one full paper-autonomous cycle.  Paper-only; never live.

    Requires Autonomous Mode to be ON.  Autonomous execution must not be
    possible while Autonomous Mode is OFF.
    """
    if not _mode_state().is_on:
        return jsonify({
            "status": "autonomous_mode_off",
            "rejection_reason": (
                "Autonomous Mode is OFF. Activate Autonomous Mode before running a lifecycle cycle."
            ),
        }), 409
    runner = _build_runner()
    result = runner.run_once()
    return jsonify(result.to_dict())


@bp.route("/runner/evaluate-exits", methods=["POST"])
def runner_evaluate_exits():
    """Evaluate every open autonomous trade and submit paper SELL exits."""
    manager = _build_exit_manager()
    decisions = manager.evaluate_open_trades()
    # Advance lifecycle after exits are evaluated: Single Trade turns OFF when
    # complete; Continuous Trading starts the next cycle after SPY recheck.
    _maybe_advance_lifecycle()
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


# ---------------------------------------------------------------------------
# Live autonomous runner helpers
# ---------------------------------------------------------------------------


def _live_runner_config() -> AutonomousLiveRunnerConfig:
    """Return the active live runner config.

    Tests / operators can register a fully constructed
    :class:`AutonomousLiveRunnerConfig` via
    ``current_app.config['autonomous_live_runner_config']``.  The default
    config has ``live_enabled=False`` which the runner enforces.

    When activation-time session values are persisted in app config,
    they are applied to the returned config so subsequent lifecycle
    calls use the same confirmed account and dry-run intent even when
    config is re-built from env.
    """
    cfg = current_app.config.get("autonomous_live_runner_config")
    if isinstance(cfg, AutonomousLiveRunnerConfig):
        return cfg
    cfg = AutonomousLiveRunnerConfig.from_env()
    # Apply the activation-time expected_account_id so it persists across calls.
    persisted_account_id = current_app.config.get("autonomous_live_expected_account_id")
    if persisted_account_id and not cfg.expected_account_id:
        cfg.expected_account_id = persisted_account_id
    persisted_dry_run = current_app.config.get("autonomous_live_dry_run")
    if persisted_dry_run is not None:
        cfg.live_dry_run = bool(persisted_dry_run)
    return cfg


def _build_broker_positions(svc) -> Dict[str, Any]:
    """Convert ServiceManager positions to RiskPosition dict for reconciliation.

    Returns ALL broker positions (not just autonomous ones) so that
    ``OrderExecutor._reconcile_portfolio()`` does not reject live exits
    merely because the account holds other, unrelated positions.
    """
    from risk.risk_manager import Position as RiskPosition

    positions_raw = svc.get_positions() or {}
    result: Dict[str, Any] = {}
    for symbol, pos_data in positions_raw.items():
        qty = 0
        for key in ("quantity", "position", "shares"):
            raw = pos_data.get(key)
            if raw is not None:
                try:
                    qty = int(float(raw))
                except (TypeError, ValueError):
                    pass
                if qty != 0:
                    break
        avg_cost = 0.0
        # "entry_price" is the key used by TWSBridge.updatePortfolio (the
        # primary live source).  The remaining keys are fallbacks for other
        # adapters or position snapshot formats that may spell the field
        # differently (e.g. paper-adapter snapshots use "average_cost",
        # while raw IBKR API data may use the camelCase "avgCost").
        for key in ("entry_price", "average_cost", "avg_cost", "avgCost"):
            raw = pos_data.get(key)
            if raw is not None:
                try:
                    avg_cost = float(raw)
                except (TypeError, ValueError):
                    pass
                if avg_cost > 0:
                    break
        current_price = 0.0
        for key in ("current_price", "market_price", "last_price"):
            raw = pos_data.get(key)
            if raw is not None:
                try:
                    current_price = float(raw)
                except (TypeError, ValueError):
                    pass
                if current_price > 0:
                    break
        side = "LONG" if qty >= 0 else "SHORT"
        if qty == 0:
            continue  # Skip zero-quantity entries
        result[symbol] = RiskPosition(
            symbol=symbol,
            quantity=abs(qty),
            entry_price=avg_cost if avg_cost > 0 else current_price,
            current_price=current_price,
            side=side,
        )
    return result


def _live_trade_store() -> TradeStore:
    """Return a shared live-trades :class:`TradeStore` instance."""
    store = current_app.config.get("autonomous_live_trade_store")
    if isinstance(store, TradeStore):
        return store
    store = TradeStore(path=_live_runner_config().trade_store_path)
    current_app.config["autonomous_live_trade_store"] = store
    return store


def _build_live_runner(
    live_config: AutonomousLiveRunnerConfig,
    *,
    continuous_mode: bool = False,
    executor_override=None,
) -> AutonomousLiveRunner:
    """Construct an :class:`AutonomousLiveRunner` wired to the live app.

    The runner uses the supplied ``executor_override`` if given, otherwise
    falls back to the test factory or builds a default dry-run-safe executor.

    The ``executor_override`` parameter is the preferred way to inject
    a request-scoped executor for actual-live mode, ensuring the runner
    always uses the intended executor rather than a stale/global one.

    For the dry-run path (``live_config.live_dry_run=True``), no global
    executor lookup is performed — a fresh dry-run executor is always built
    to prevent bleed-through from a previous actual-live activation.
    """
    override = current_app.config.get("autonomous_live_runner_factory")
    if callable(override):
        return override(live_config, continuous_mode=continuous_mode)

    svc = get_services()

    def _connected() -> bool:
        return bool(getattr(svc, "connected", False))

    def _env():
        return getattr(svc, "connection_env", None)

    def _account_id() -> Optional[str]:
        info = getattr(svc, "connection_info", None) or {}
        return info.get("account") or None

    def _provider():
        return _resolve_signal_provider()

    def _estop() -> bool:
        try:
            return EMERGENCY_STOP_FILE.exists()
        except OSError:  # pragma: no cover - defensive
            return False

    def _deployable_cash() -> float:
        try:
            cash_analyzer = CashAvailabilityAnalyzer()
            result = cash_analyzer.analyze(
                account_summary=svc.get_account_summary(),
                positions=svc.get_positions(),
                orders=svc.get_orders(),
            )
            return float(result.deployable_cash)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to calculate deployable cash for live runner")
            return 0.0

    # Build engine in ASSISTED_LIVE mode (the runner overrides this before run)
    engine = _build_engine({"mode": AutonomousMode.ASSISTED_LIVE.value})

    # Resolve OrderExecutor.
    # Priority: explicit executor_override > default build.
    # The dry-run path ALWAYS builds a fresh dry-run executor to prevent
    # bleed-through from a stale actual-live executor stored globally.
    executor = executor_override
    if executor is None:
        try:
            from execution.order_executor import OrderExecutor
            from risk.risk_manager import RiskManager
            risk_manager = getattr(svc, "risk_manager", None) or RiskManager()

            # Dry-run path: always build with tws_adapter=None and dry_run=True
            # to guarantee no real orders can be submitted.
            executor = OrderExecutor(
                tws_adapter=None,
                risk_manager=risk_manager,
                is_live_mode=True,
                dry_run=True,  # Always dry-run when no explicit executor supplied
                live_trading_enabled=live_config.live_enabled,
                live_confirmation=None,
                expected_account_id=live_config.expected_account_id,
                limit_orders_only=live_config.live_limit_orders_only,
            )
        except Exception:
            logger.exception("Failed to build default live OrderExecutor")
            executor = None

    return AutonomousLiveRunner(
        engine=engine,
        trade_store=_live_trade_store(),
        live_config=live_config,
        order_executor=executor,
        connected_provider=_connected,
        connection_env_provider=_env,
        account_id_provider=_account_id,
        signal_provider_provider=_provider,
        emergency_stop_provider=_estop,
        deployable_cash_provider=_deployable_cash,
        broker_positions_provider=lambda: _build_broker_positions(svc),
        continuous_mode=continuous_mode,
    )


def _live_mode_state() -> AutonomousModeState:
    """Return (or create) the autonomous live-mode state object."""
    state = current_app.config.get("autonomous_live_mode_state")
    if isinstance(state, AutonomousModeState):
        return state
    state = AutonomousModeState()
    current_app.config["autonomous_live_mode_state"] = state
    return state


def _maybe_advance_live_lifecycle() -> None:
    """Advance the live autonomous lifecycle after exit evaluation.

    Mirror of ``_maybe_advance_lifecycle`` but for the live runner.
    Called from the live evaluate-exits endpoint.
    """
    state = _live_mode_state()
    if not state.is_on or state.cycles_started == 0:
        return

    try:
        activated_at_str = state.activated_at
        if not activated_at_str:
            return
        activated_at = datetime.fromisoformat(activated_at_str)
        live_store = _live_trade_store()
        since_activation = [
            t for t in live_store.list_all()
            if t.entry_time >= activated_at
        ]
        if not since_activation:
            return
        still_active = [t for t in since_activation if t.status in (OPEN, EXIT_PENDING)]
        if still_active:
            return

        cycle = state.trading_cycle
        if cycle == TradingCycle.SINGLE_TRADE:
            state.turn_off(
                message="Live Single Trade lifecycle completed. Autonomous Mode turned OFF.",
                status="Ready",
            )
            _audit_mode_event(
                "halt",
                {"reason": "live_single_trade_completed", "source": "lifecycle", "account_mode": "live"},
            )
        elif cycle == TradingCycle.CONTINUOUS:
            # Start next live cycle.
            live_config = _live_runner_config()
            live_config.live_dry_run = bool(getattr(state, "dry_run", live_config.live_dry_run))
            try:
                runner = _build_live_runner(live_config, continuous_mode=True)
                result = runner.run_once()
                state.cycles_started += 1
                _audit_mode_event(
                    "live_continuous_cycle",
                    {"cycles_started": state.cycles_started, "result_status": result.status},
                )
                if result.decision:
                    decision_status = (result.decision or {}).get("status")
                    if decision_status == "market_not_suitable":
                        state.turn_off(message=BEARISH_SPY_MESSAGE, status="Halted")
                        _audit_mode_event(
                            "halt",
                            {"reason": BEARISH_SPY_MESSAGE, "source": "live_spy_gate_continuous"},
                        )
            except Exception:
                logger.exception("Live continuous lifecycle cycle failed")
                state.turn_off(
                    message="Live continuous lifecycle error. Autonomous Mode turned OFF.",
                    status="Halted",
                )
    except Exception:
        logger.exception("Live lifecycle advancement check failed")


# ---------------------------------------------------------------------------
# Live autonomous runner endpoints
# ---------------------------------------------------------------------------


@bp.route("/live/status", methods=["GET"])
def live_runner_status():
    """Return live runner config and current readiness gates."""
    live_config = _live_runner_config()
    try:
        runner = _build_live_runner(live_config, continuous_mode=False)
        gates = runner.evaluate_gates()
    except Exception:
        logger.exception("Failed to build live runner for status check")
        return jsonify({
            "error": "Failed to evaluate live runner gates",
            "live_runner_config": live_config.to_dict(),
        }), 500

    state = _live_mode_state()
    return jsonify({
        "live_runner_config": live_config.to_dict(),
        "gates": gates.to_dict(),
        "autonomous_live_mode": state.to_dict(),
    })


@bp.route("/live/activate", methods=["POST"])
def live_activate():
    """Activate Full Live Continuous Autonomous Mode.

    Request body (all fields required unless noted):

    .. code-block:: json

        {
            "confirm": true,
            "account_mode": "live",
            "trading_cycle": "continuous",
            "live_trading_enabled": true,
            "confirmed_by": "Operator",
            "expected_account_id": "U1234567",
            "dry_run": false
        }

    Activation is rejected when:

    * ``confirm`` is not ``true``,
    * ``account_mode`` is not ``"live"``,
    * the TWS connection is not a live account,
    * the account ID does not match ``expected_account_id``,
    * ``AUTONOMOUS_LIVE_ENABLED`` is ``false``,
    * ``AUTONOMOUS_LIVE_CONTINUOUS_ENABLED`` is ``false`` (for continuous),
    * emergency stop is active,
    * signal provider is not ready,
    * deployable cash is below the configured minimum.
    """
    body = request.get_json(silent=True) or {}

    # 1. Explicit confirmation required.
    if body.get("confirm") is not True:
        return jsonify({
            "error": "confirm must be true to activate Live Autonomous Mode",
            "status": "confirmation_required",
        }), 400

    # 2. account_mode must be "live".
    account_mode_raw = str(body.get("account_mode") or "").lower().strip()
    if account_mode_raw != "live":
        return jsonify({
            "error": "account_mode must be 'live' to activate Live Autonomous Mode",
            "status": "rejected",
        }), 400

    # 3. trading_cycle validation.
    cycle = normalise_trading_cycle(body.get("trading_cycle"))
    if cycle is None:
        return jsonify({"error": "trading_cycle must be single_trade or continuous"}), 400

    # 4. Build live runner config, applying request overrides where allowed.
    live_config = _live_runner_config()

    # Allow operator to supply expected_account_id and dry_run per-request.
    expected_account_id = str(body.get("expected_account_id") or "").strip() or None
    if expected_account_id:
        live_config.expected_account_id = expected_account_id

    if body.get("dry_run") is True:
        live_config.live_dry_run = True

    continuous_mode = (cycle == TradingCycle.CONTINUOUS)

    # 5. Build the runner and evaluate gates.
    try:
        runner = _build_live_runner(live_config, continuous_mode=continuous_mode)
    except Exception:
        logger.exception("Failed to build AutonomousLiveRunner")
        return jsonify({
            "error": "Failed to construct live runner",
            "status": "rejected",
        }), 500

    gates = runner.evaluate_gates()
    if not gates.ready:
        msg = "; ".join(gates.reasons()) or "Live runner readiness checks failed"
        return jsonify({
            "status": "rejected",
            "error": msg,
            "gates": gates.to_dict(),
        }), 409

    # 6. Activate live mode state and persist session context.
    state = _live_mode_state()
    state.turn_on(cycle, AccountMode.LIVE, dry_run=live_config.live_dry_run)
    confirmed_by = str(body.get("confirmed_by") or "operator")

    # Persist expected_account_id so all subsequent lifecycle calls use the
    # same account confirmed at activation, even when the config is re-built
    # from env.
    if expected_account_id:
        current_app.config["autonomous_live_expected_account_id"] = expected_account_id
    current_app.config["autonomous_live_dry_run"] = bool(live_config.live_dry_run)

    # Build and persist a LiveTradingConfirmation for the session so that the
    # OrderExecutor can verify the account/environment on every live order.
    if expected_account_id and not live_config.live_dry_run:
        try:
            from execution.order_executor import LiveTradingConfirmation
            svc = get_services()
            connection_info = getattr(svc, "connection_info", None) or {}
            port = int(connection_info.get("port") or 7496)
            env = getattr(svc, "connection_env", "") or ""
            if env.lower() == "live":
                confirmation = LiveTradingConfirmation(
                    environment="live",
                    account_id=expected_account_id,
                    port=port,
                    confirmed_by=confirmed_by,
                )
                current_app.config["autonomous_live_confirmation"] = confirmation
                logger.info(
                    "LiveTradingConfirmation persisted for account=%s port=%d confirmed_by=%r",
                    expected_account_id,
                    port,
                    confirmed_by,
                )
        except Exception:
            logger.exception("Failed to build/persist LiveTradingConfirmation at activation")

    _audit_mode_event(
        "live_activate",
        {
            "trading_cycle": cycle.value,
            "account_mode": "live",
            "dry_run": live_config.live_dry_run,
            "expected_account_id": expected_account_id,
            "confirmed_by": confirmed_by,
        },
    )

    # 7. Run the first live cycle.
    payload: Dict[str, Any] = {}
    try:
        result = runner.run_once()
        state.cycles_started += 1
        payload = result.to_dict()

        # Determine outcome label for the dashboard.
        run_status = payload.get("status", "")
        if live_config.live_dry_run:
            payload["outcome"] = "LIVE_DRY_RUN_PREVIEW_ONLY"
        elif run_status == "executed":
            payload["outcome"] = "LIVE_ORDER_SUBMITTED"
        elif run_status == "no_trade":
            payload["outcome"] = "NO_TRADE"
        else:
            payload["outcome"] = "LIVE_ORDER_REJECTED"

        # Check for market gate failure.
        decision = payload.get("decision") or {}
        if decision.get("status") == "market_not_suitable":
            state.turn_off(message=BEARISH_SPY_MESSAGE, status="Halted")
            _audit_mode_event(
                "halt",
                {"reason": BEARISH_SPY_MESSAGE, "source": "live_spy_gate"},
            )
        elif payload.get("status") == "no_trade" and cycle == TradingCycle.SINGLE_TRADE:
            message = (
                payload.get("rejection_reason")
                or "No live trade. Autonomous Mode has been turned OFF."
            )
            state.turn_off(message=message, status="Not Ready")
            _audit_mode_event(
                "halt",
                {"reason": message, "source": "live_single_trade_no_trade"},
            )
    except Exception:
        logger.exception("Live autonomous lifecycle run failed after activation")
        state.turn_off(
            message="Live lifecycle run failed. Autonomous Mode turned OFF.",
            status="Halted",
        )
        _audit_mode_event(
            "halt",
            {"reason": "live_lifecycle_run_exception", "source": "live_activate"},
        )
        payload = {}

    return jsonify({
        "status": "activated" if state.is_on else "halted",
        "run": payload,
        "autonomous_live_mode": state.to_dict(),
    })


# ---------------------------------------------------------------------------
# Actual Live Trading — explicit activation with strong confirmation gates
# ---------------------------------------------------------------------------

# Required confirmation phrase the operator must type to enable actual live
# trading from the dashboard.  This phrase is validated server-side.
ACTUAL_LIVE_CONFIRMATION_PHRASE = "ENABLE ACTUAL LIVE TRADING"


@bp.route("/live/actual-live/activate", methods=["POST"])
def actual_live_activate():
    """Activate **Actual Live Trading** — real orders submitted to TWS.

    This is separate from the dry-run ``/live/activate`` path.  All safety
    gates must pass, and the operator must supply a strong confirmation
    including account ID, operator identifier, and the exact confirmation
    phrase.

    Request body (all fields required):

    .. code-block:: json

        {
            "confirm": true,
            "account_mode": "live",
            "trading_cycle": "single_trade",
            "expected_account_id": "U1234567",
            "confirmed_by": "operator-name",
            "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
            "acknowledge_real_money_risk": true
        }

    Continuous trading is blocked in v1 — only ``single_trade`` is allowed.

    The dashboard confirmation is treated as the explicit operator
    confirmation; the backend does NOT block on terminal ``input()``.  The
    ``OrderExecutor`` is constructed with ``require_confirmation=False``.
    """
    body = request.get_json(silent=True) or {}

    # --- Validation gates (all must pass before any execution) ---

    # 1. confirm flag
    if body.get("confirm") is not True:
        return jsonify({
            "error": "confirm must be true",
            "status": "rejected",
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": "confirm flag missing",
        }), 400

    # 2. account_mode must be "live"
    if str(body.get("account_mode") or "").lower().strip() != "live":
        return jsonify({
            "error": "account_mode must be 'live'",
            "status": "rejected",
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": "account_mode not live",
        }), 400

    # 3. trading_cycle — v1 restricts to single_trade only
    cycle = normalise_trading_cycle(body.get("trading_cycle"))
    if cycle is None or cycle != TradingCycle.SINGLE_TRADE:
        return jsonify({
            "error": "Actual live trading v1 supports only single_trade cycle",
            "status": "rejected",
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": "only single_trade allowed in v1",
        }), 400

    # 4. expected_account_id (non-empty)
    expected_account_id = str(body.get("expected_account_id") or "").strip()
    if not expected_account_id:
        return jsonify({
            "error": "expected_account_id is required",
            "status": "rejected",
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": "expected_account_id missing",
        }), 400

    # 5. confirmed_by (non-empty operator identifier)
    confirmed_by = str(body.get("confirmed_by") or "").strip()
    if not confirmed_by:
        return jsonify({
            "error": "confirmed_by operator identifier is required",
            "status": "rejected",
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": "confirmed_by missing",
        }), 400

    # 6. confirmation_phrase must match exactly
    confirmation_phrase = str(body.get("confirmation_phrase") or "").strip()
    if confirmation_phrase != ACTUAL_LIVE_CONFIRMATION_PHRASE:
        return jsonify({
            "error": (
                "confirmation_phrase must be exactly: "
                f"'{ACTUAL_LIVE_CONFIRMATION_PHRASE}'"
            ),
            "status": "rejected",
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": "confirmation phrase mismatch",
        }), 400

    # 7. acknowledge_real_money_risk
    if body.get("acknowledge_real_money_risk") is not True:
        return jsonify({
            "error": "acknowledge_real_money_risk must be true",
            "status": "rejected",
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": "risk acknowledgement missing",
        }), 400

    # --- All input validation passed; build config and evaluate gates ---
    #
    # Ordering (addresses review issue #1):
    #   1. Validate confirmation fields (done above)
    #   2. Validate detected live account / port / env
    #   3. Build LiveTradingConfirmation
    #   4. Build a connected, actual-live OrderExecutor
    #   5. Build the AutonomousLiveRunner WITH that executor
    #   6. Evaluate gates
    #   7. Run once

    live_config = _live_runner_config()
    live_config.expected_account_id = expected_account_id
    live_config.live_dry_run = False  # Actual live — NOT dry run

    # v1 enforcement: single trade, buy-shares-only, limit-orders-only,
    # max 1 open trade, max 1 per day.
    live_config.buy_shares_only = True
    live_config.live_limit_orders_only = True
    live_config.max_open_live_trades = 1
    live_config.max_live_trades_per_day = 1

    # --- Step 2: Validate detected live account / port / env ---
    svc = get_services()
    connection_info = getattr(svc, "connection_info", None) or {}
    port = int(connection_info.get("port") or 7496)
    host = str(connection_info.get("host") or "127.0.0.1")

    # --- Step 3: Build LiveTradingConfirmation ---
    from execution.order_executor import LiveTradingConfirmation
    confirmation = LiveTradingConfirmation(
        environment="live",
        account_id=expected_account_id,
        port=port,
        confirmed_by=confirmed_by,
    )

    # --- Steps 4+5: Build executor and runner ---
    # If a test runner factory is registered, it handles executor injection
    # internally.  Otherwise, build a real adapter, connect it, and pass
    # the executor directly into the runner.
    tws_adapter = None  # Will be set only if we build a real adapter
    runner_factory = current_app.config.get("autonomous_live_runner_factory")

    if callable(runner_factory):
        # Test/development path: factory handles everything.
        try:
            runner = runner_factory(live_config, continuous_mode=False)
        except Exception:
            logger.exception("Failed to build AutonomousLiveRunner via factory")
            _audit_mode_event("actual_live_activate_failed", {
                "expected_account_id": expected_account_id,
                "confirmed_by": confirmed_by,
                "reason": "runner_factory_failed",
            })
            return jsonify({
                "error": "Failed to construct live runner",
                "status": "rejected",
                "outcome": "LIVE_ORDER_REJECTED",
                "rejection_reason": "runner construction failed",
            }), 500
    else:
        # Production path: build a connected adapter and executor, then runner.
        # The executor is request-scoped — NOT stored globally (addresses
        # review issue #3: prevents dry-run bleed-through).
        try:
            from execution.paper_adapter import TwsTradingAdapter
            from execution.order_executor import OrderExecutor
            from risk.risk_manager import RiskManager

            risk_manager = getattr(svc, "risk_manager", None) or RiskManager()

            tws_adapter = TwsTradingAdapter(
                host=host,
                port=port,
                environment="live",
            )

            # Connect and verify readiness (addresses review issue #2).
            # If TWS is not available, fail clearly rather than allowing the
            # UI to imply "Actual Live Trading" is ready.
            adapter_connected = tws_adapter.connect_and_run()
            if not adapter_connected or not tws_adapter.ready:
                _audit_mode_event("actual_live_activate_failed", {
                    "expected_account_id": expected_account_id,
                    "confirmed_by": confirmed_by,
                    "reason": "adapter_not_connected",
                    "host": host,
                    "port": port,
                })
                return jsonify({
                    "error": (
                        "TWS adapter could not connect or is not ready. "
                        "Verify TWS/Gateway is running and accepting connections "
                        f"on {host}:{port}."
                    ),
                    "status": "rejected",
                    "outcome": "LIVE_ORDER_REJECTED",
                    "rejection_reason": "adapter not connected/ready",
                }), 503

            executor = OrderExecutor(
                tws_adapter=tws_adapter,
                risk_manager=risk_manager,
                is_live_mode=True,
                require_confirmation=False,  # Dashboard confirmation replaces input()
                dry_run=False,
                live_trading_enabled=True,
                live_confirmation=confirmation,
                expected_account_id=expected_account_id,
                limit_orders_only=True,
            )
        except Exception:
            logger.exception("Failed to build actual-live OrderExecutor")
            if tws_adapter is not None:
                try:
                    tws_adapter.disconnect_gracefully()
                except Exception:
                    pass
            _audit_mode_event("actual_live_activate_failed", {
                "expected_account_id": expected_account_id,
                "confirmed_by": confirmed_by,
                "reason": "executor_construction_failed",
            })
            return jsonify({
                "error": "Failed to construct actual-live OrderExecutor",
                "status": "rejected",
                "outcome": "LIVE_ORDER_REJECTED",
                "rejection_reason": "executor construction failed",
            }), 500

        # Build the runner WITH the actual-live executor (addresses review
        # issue #1: executor available BEFORE runner.run_once()).
        try:
            runner = _build_live_runner(
                live_config, continuous_mode=False, executor_override=executor
            )
        except Exception:
            logger.exception("Failed to build AutonomousLiveRunner for actual-live")
            tws_adapter.disconnect_gracefully()
            _audit_mode_event("actual_live_activate_failed", {
                "expected_account_id": expected_account_id,
                "confirmed_by": confirmed_by,
                "reason": "runner_construction_failed",
            })
            return jsonify({
                "error": "Failed to construct live runner",
                "status": "rejected",
                "outcome": "LIVE_ORDER_REJECTED",
                "rejection_reason": "runner construction failed",
            }), 500

    # --- Step 6: Evaluate gates ---
    gates = runner.evaluate_gates()
    if not gates.ready:
        msg = "; ".join(gates.reasons()) or "Live runner readiness checks failed"
        if tws_adapter is not None:
            tws_adapter.disconnect_gracefully()
        _audit_mode_event("actual_live_activate_rejected", {
            "expected_account_id": expected_account_id,
            "confirmed_by": confirmed_by,
            "gates": gates.to_dict(),
            "reason": msg,
        })
        return jsonify({
            "status": "rejected",
            "error": msg,
            "outcome": "LIVE_ORDER_REJECTED",
            "rejection_reason": msg,
            "gates": gates.to_dict(),
        }), 409

    # --- Activate live mode state ---
    state = _live_mode_state()
    state.turn_on(cycle, AccountMode.LIVE, dry_run=False)

    # Persist session values (but NOT the executor — it is request-scoped)
    current_app.config["autonomous_live_expected_account_id"] = expected_account_id
    current_app.config["autonomous_live_dry_run"] = False
    current_app.config["autonomous_live_confirmation"] = confirmation

    # Audit the activation
    _audit_mode_event("actual_live_activate", {
        "trading_cycle": cycle.value,
        "account_mode": "live",
        "dry_run": False,
        "expected_account_id": expected_account_id,
        "confirmed_by": confirmed_by,
        "confirmation_phrase_valid": True,
        "acknowledge_real_money_risk": True,
        "port": port,
        "gates": gates.to_dict(),
    })

    # --- Step 7: Run the single trade cycle ---
    payload: Dict[str, Any] = {}
    try:
        result = runner.run_once()
        state.cycles_started += 1
        payload = result.to_dict()

        # Determine outcome label
        run_status = payload.get("status", "")
        if run_status == "executed":
            payload["outcome"] = "LIVE_ORDER_SUBMITTED"
            # Provide a clear submitted_order_id field (addresses review issue #5)
            trade = payload.get("trade") or {}
            payload["submitted_order_id"] = (
                trade.get("entry_order_id") or trade.get("order_id") or None
            )
        elif run_status == "dry_run_executed":
            # Should not happen on this path, but handle gracefully
            payload["outcome"] = "LIVE_DRY_RUN_PREVIEW_ONLY"
        elif run_status == "no_trade":
            payload["outcome"] = "NO_TRADE"
        else:
            payload["outcome"] = "LIVE_ORDER_REJECTED"

        # v1 single-trade actual-live: turn OFF for ALL non-executed outcomes
        # (addresses review issue #4).  Only "executed" keeps mode ON.
        if run_status != "executed":
            message = (
                payload.get("rejection_reason")
                or f"Actual live single-trade ended with status '{run_status}'. "
                "Autonomous Mode has been turned OFF."
            )
            state.turn_off(message=message, status="Not Ready")
            _audit_mode_event("halt", {
                "reason": message,
                "run_status": run_status,
                "source": "actual_live_single_trade_non_executed",
            })

        # Check market gate
        decision = payload.get("decision") or {}
        if decision.get("status") == "market_not_suitable":
            if state.is_on:
                state.turn_off(message=BEARISH_SPY_MESSAGE, status="Halted")
                _audit_mode_event("halt", {
                    "reason": BEARISH_SPY_MESSAGE,
                    "source": "actual_live_spy_gate",
                })
            payload["outcome"] = "NO_TRADE"

    except Exception:
        logger.exception("Actual live autonomous lifecycle run failed")
        state.turn_off(
            message="Actual live lifecycle run failed. Autonomous Mode turned OFF.",
            status="Halted",
        )
        _audit_mode_event("halt", {
            "reason": "actual_live_lifecycle_run_exception",
            "source": "actual_live_activate",
        })
        payload = {"outcome": "LIVE_ORDER_REJECTED", "rejection_reason": "lifecycle exception"}
    finally:
        # Always disconnect the request-scoped adapter after execution
        if tws_adapter is not None:
            try:
                tws_adapter.disconnect_gracefully()
            except Exception:
                pass

    return jsonify({
        "status": "activated" if state.is_on else "halted",
        "run": payload,
        "autonomous_live_mode": state.to_dict(),
    })


@bp.route("/live/halt", methods=["POST"])
def live_halt():
    """Turn Live Autonomous Mode OFF without liquidating positions."""
    body = request.get_json(silent=True) or {}
    reason = str(body.get("reason") or "Operator turned Live Autonomous Mode OFF")
    _live_mode_state().turn_off(message=reason, status="Halted")
    _audit_mode_event(
        "live_halt",
        {"reason": reason, "source": "operator"},
    )
    state = _live_mode_state()
    return jsonify({
        "status": "halted",
        "autonomous_live_mode": state.to_dict(),
    })


@bp.route("/live/run-once", methods=["POST"])
def live_run_once():
    """Run one full live-autonomous cycle.  Requires Live Mode to be ON.

    This endpoint is intended for manual triggering or for use by an
    external scheduler.  It does not start a background loop.
    """
    state = _live_mode_state()
    if not state.is_on:
        return jsonify({
            "status": "live_mode_off",
            "rejection_reason": (
                "Live Autonomous Mode is OFF. Activate it before running a lifecycle cycle."
            ),
        }), 409

    live_config = _live_runner_config()
    # Preserve activation-time mode semantics for all subsequent cycles.
    live_config.live_dry_run = bool(getattr(state, "dry_run", live_config.live_dry_run))
    continuous_mode = (state.trading_cycle == TradingCycle.CONTINUOUS)
    try:
        runner = _build_live_runner(live_config, continuous_mode=continuous_mode)
    except Exception:
        logger.exception("Failed to build AutonomousLiveRunner for run-once")
        return jsonify({
            "status": "error",
            "error": "Failed to construct live runner",
        }), 500

    result = runner.run_once()
    state.cycles_started += 1
    return jsonify(result.to_dict())


@bp.route("/live/evaluate-exits", methods=["POST"])
def live_evaluate_exits():
    """Evaluate open live autonomous trades and advance lifecycle."""
    live_config = _live_runner_config()
    live_config.live_dry_run = bool(
        getattr(_live_mode_state(), "dry_run", live_config.live_dry_run)
    )
    svc = get_services()
    from autonomous.exit_manager import AutonomousExitManager

    # Use the live trade store for exit evaluation.
    live_store = _live_trade_store()

    # Build exit manager using live adapter when available.
    override = current_app.config.get("autonomous_live_exit_manager_factory")
    if callable(override):
        manager = override()
    else:
        # Resolve the live OrderExecutor (same as used for entries) so that
        # exit orders are submitted through the same safety gates as entries.
        # When no executor is available (e.g. TWS not connected), exits fall
        # back to evaluation-only mode and the dashboard shows would_exit notes.
        live_executor = current_app.config.get("autonomous_live_order_executor")
        if live_executor is None:
            try:
                live_executor = _build_live_runner(
                    live_config, continuous_mode=False
                ).order_executor
            except Exception:
                logger.warning(
                    "Could not resolve live OrderExecutor for exit manager; "
                    "exits will be evaluation-only"
                )
                live_executor = None

        manager = AutonomousExitManager(
            trade_store=live_store,
            paper_adapter=None,
            positions_provider=svc.get_positions,
            risk_manager=getattr(svc, "risk_manager", None),
            emergency_stop_file=str(EMERGENCY_STOP_FILE),
            order_executor=live_executor,
            account_equity_provider=lambda: (
                svc.get_account_summary().get("equity")
            ),
            broker_positions_provider=lambda: _build_broker_positions(svc),
        )

    decisions = manager.evaluate_open_trades()
    _maybe_advance_live_lifecycle()
    return jsonify({
        "decisions": [d.to_dict() for d in decisions],
        "count": len(decisions),
    })


@bp.route("/live/trades", methods=["GET"])
def live_trades():
    """Return open and recently-closed live autonomous trades."""
    store = _live_trade_store()
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
