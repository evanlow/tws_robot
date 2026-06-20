"""Fit-for-trading readiness API.

This endpoint turns the informal trading-readiness discussion into a concrete
machine-readable status report.  It does not place orders.  It evaluates whether
TWS Robot is fit for increasingly risky operating modes and explains the gates
that still block each mode.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from flask import Blueprint, jsonify

from autonomous.runner_config import (
    AutonomousLiveRunnerConfig,
    FIRST_LIVE_EXPERIMENT_MAX_DEPLOYABLE_CASH_PCT,
)
from autonomous.signal_provider import StaticSignalProvider
from data.cash_availability import CashAvailabilityAnalyzer
from web.services import get_services

bp = Blueprint(
    "api_trading_readiness",
    __name__,
    url_prefix="/api/trading-readiness",
)


YES = "YES"
NO = "NO"
BLOCKED = "BLOCKED"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default


def _mask_account(account_id: str) -> str:
    account_id = str(account_id or "").strip()
    if not account_id:
        return ""
    if len(account_id) <= 4:
        return "****"
    return f"***{account_id[-4:]}"


def _criterion(
    key: str,
    label: str,
    status: str,
    reasons: List[str] | None = None,
    evidence: Dict[str, Any] | None = None,
    next_tasks: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "fit": status == YES,
        "reasons": reasons or [],
        "evidence": evidence or {},
        "next_tasks": next_tasks or [],
    }


def _provider_ready(provider: Any) -> bool:
    return provider is not None and not isinstance(provider, StaticSignalProvider)


def _current_signal_provider():
    from web.routes.api_autonomous import _resolve_signal_provider

    return _resolve_signal_provider()


def _current_live_config() -> AutonomousLiveRunnerConfig:
    from web.routes.api_autonomous import _live_runner_config

    return _live_runner_config()


def _emergency_stop_active() -> bool:
    from web.routes.api_autonomous import EMERGENCY_STOP_FILE

    try:
        return EMERGENCY_STOP_FILE.exists()
    except OSError:
        return True  # fail closed when the stop-file state is unreadable


def _resolve_paper_adapter(svc):
    from web.routes.api_autonomous import _resolve_paper_adapter as _resolve

    return _resolve(svc)


def _deployable_cash(svc) -> Tuple[float, str]:
    """Return deployable cash and a source label.

    Prefer the same analyzer used by the autonomous runner.  Fall back to common
    account-summary keys so readiness status still works in partially mocked
    tests and early connection states.
    """

    try:
        result = CashAvailabilityAnalyzer().analyze(
            account_summary=svc.get_account_summary(),
            positions=svc.get_positions(),
            orders=svc.get_orders(),
        )
        return float(result.deployable_cash), "cash_availability_analyzer"
    except Exception:
        account = svc.get_account_summary()
        for key in ("available_funds", "cash_balance", "buying_power", "equity"):
            value = account.get(key)
            try:
                if value is not None:
                    return float(value), f"account_summary.{key}"
            except (TypeError, ValueError):
                continue
    return 0.0, "unavailable"


def _build_status_payload() -> Dict[str, Any]:
    svc = get_services()
    live_config = _current_live_config()
    provider = _current_signal_provider()
    signal_ready = _provider_ready(provider)
    emergency_stop = _emergency_stop_active()

    connected = bool(getattr(svc, "connected", False))
    env = getattr(svc, "connection_env", None)
    connection_info = getattr(svc, "connection_info", {}) or {}
    account_id = str(connection_info.get("account") or "").strip()
    bridge = getattr(svc, "tws_bridge", None)
    bridge_connected = bool(getattr(bridge, "is_connected", False))
    account_data_ready = bool(getattr(svc, "account_data_ready", False))

    deployable_cash, deployable_cash_source = _deployable_cash(svc)
    max_single_trade_value = round(
        deployable_cash * live_config.max_deployable_cash_pct,
        2,
    )
    first_live_max_trade_value = _env_float(
        "FIT_FOR_TRADING_MAX_SINGLE_TRADE_VALUE",
        300.0,
    )

    connection_evidence = {
        "connected": connected,
        "connection_env": env,
        "account_id_masked": _mask_account(account_id),
        "account_data_ready": account_data_ready,
        "tws_bridge_connected": bridge_connected,
    }
    config_evidence = {
        "live_enabled": live_config.live_enabled,
        "live_continuous_enabled": live_config.live_continuous_enabled,
        "live_limit_orders_only": live_config.live_limit_orders_only,
        "live_require_account_confirmation": live_config.live_require_account_confirmation,
        "buy_shares_only": live_config.buy_shares_only,
        "max_open_live_trades": live_config.max_open_live_trades,
        "max_live_trades_per_day": live_config.max_live_trades_per_day,
        "max_deployable_cash_pct": live_config.max_deployable_cash_pct,
        "deployable_cash": round(deployable_cash, 2),
        "deployable_cash_source": deployable_cash_source,
        "max_single_trade_value": max_single_trade_value,
        "first_live_max_trade_value": first_live_max_trade_value,
        "default_first_live_cash_pct": FIRST_LIVE_EXPERIMENT_MAX_DEPLOYABLE_CASH_PCT,
    }

    criteria: Dict[str, Dict[str, Any]] = {}

    criteria["recommend_only"] = _criterion(
        "recommend_only",
        "Recommend-only scan / proposal",
        YES,
        evidence={
            "places_orders": False,
            "requires_broker_connection": False,
        },
    )

    paper_reasons: List[str] = []
    paper_tasks: List[str] = []
    if emergency_stop:
        paper_reasons.append("Emergency stop is active")
        paper_tasks.append("Clear EMERGENCY_STOP only after verifying no unsafe orders are pending")
    if not connected or env != "paper":
        paper_reasons.append("IBKR paper account is not connected")
        paper_tasks.append("Connect TWS/Gateway in paper mode")
    if not signal_ready:
        paper_reasons.append("Production signal provider is not ready")
        paper_tasks.append("Wire TechnicalAnalysisSignalProvider or another real signal provider")
    paper_adapter_ready = _resolve_paper_adapter(svc) is not None
    if not paper_adapter_ready:
        paper_reasons.append("Paper execution adapter is not ready")
        paper_tasks.append("Verify the paper TWS bridge handshake and adapter wiring")

    criteria["paper_execution"] = _criterion(
        "paper_execution",
        "Paper autonomous execution",
        YES if not paper_reasons else NO,
        paper_reasons,
        evidence={
            **connection_evidence,
            "signal_provider": type(provider).__name__,
            "signal_provider_ready": signal_ready,
            "paper_adapter_ready": paper_adapter_ready,
            "emergency_stop_active": emergency_stop,
        },
        next_tasks=paper_tasks,
    )

    live_common_reasons: List[str] = []
    live_common_tasks: List[str] = []
    if emergency_stop:
        live_common_reasons.append("Emergency stop is active")
        live_common_tasks.append("Clear EMERGENCY_STOP only after manual broker review")
    if not connected or env != "live":
        live_common_reasons.append("IBKR live account is not connected")
        live_common_tasks.append("Connect TWS/Gateway in live mode only when ready for rehearsal")
    if not account_id:
        live_common_reasons.append("Live account ID has not been detected")
        live_common_tasks.append("Wait for account callbacks and verify the detected account ID")
    if not live_config.live_enabled:
        live_common_reasons.append("AUTONOMOUS_LIVE_ENABLED is false")
        live_common_tasks.append("Set AUTONOMOUS_LIVE_ENABLED=true only for a monitored rehearsal")
    if not signal_ready:
        live_common_reasons.append("Production signal provider is not ready")
        live_common_tasks.append("Wire the real signal provider before any live dry-run")
    if not account_data_ready:
        live_common_reasons.append("Live account equity/cash data is not ready")
        live_common_tasks.append("Wait until account_data_ready is true before live rehearsal")
    if deployable_cash < live_config.min_deployable_cash:
        live_common_reasons.append(
            f"Deployable cash {deployable_cash:.2f} is below minimum "
            f"{live_config.min_deployable_cash:.2f}"
        )
        live_common_tasks.append("Confirm cash availability and minimum deployable cash setting")

    criteria["live_dry_run"] = _criterion(
        "live_dry_run",
        "Live dry-run rehearsal",
        YES if not live_common_reasons else NO,
        live_common_reasons,
        evidence={
            **connection_evidence,
            **config_evidence,
            "signal_provider": type(provider).__name__,
            "signal_provider_ready": signal_ready,
            "emergency_stop_active": emergency_stop,
            "orders_to_tws": False,
        },
        next_tasks=live_common_tasks,
    )

    single_reasons = list(live_common_reasons)
    single_tasks = list(live_common_tasks)
    if not bridge_connected:
        single_reasons.append("Persistent TWS bridge is not connected")
        single_tasks.append("Reconnect through the dashboard and verify bridge.is_connected")
    if not live_config.live_limit_orders_only:
        single_reasons.append("Live limit-orders-only is disabled")
        single_tasks.append("Keep AUTONOMOUS_LIVE_LIMIT_ORDERS_ONLY=true")
    if not live_config.buy_shares_only:
        single_reasons.append("Buy-shares-only restriction is disabled")
        single_tasks.append("Keep buy_shares_only=true for first live experiments")
    if live_config.max_open_live_trades != 1:
        single_reasons.append("max_open_live_trades must be exactly 1 for first live experiment")
        single_tasks.append("Set AUTONOMOUS_MAX_OPEN_LIVE_TRADES=1")
    if live_config.max_live_trades_per_day != 1:
        single_reasons.append("max_live_trades_per_day must be exactly 1 for first live experiment")
        single_tasks.append("Set AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY=1")
    if max_single_trade_value <= 0:
        single_reasons.append("Calculated maximum single-trade value is zero")
        single_tasks.append("Check deployable cash and max_deployable_cash_pct")
    if max_single_trade_value > first_live_max_trade_value:
        single_reasons.append(
            f"Max single-trade value {max_single_trade_value:.2f} exceeds first-live cap "
            f"{first_live_max_trade_value:.2f}"
        )
        single_tasks.append(
            "Lower AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT or FIT_FOR_TRADING_MAX_SINGLE_TRADE_VALUE"
        )

    criteria["actual_live_single_trade"] = _criterion(
        "actual_live_single_trade",
        "Actual live single-trade experiment",
        YES if not single_reasons else NO,
        single_reasons,
        evidence={
            **connection_evidence,
            **config_evidence,
            "signal_provider": type(provider).__name__,
            "signal_provider_ready": signal_ready,
            "emergency_stop_active": emergency_stop,
            "requires_bracket_exit": True,
            "orders_to_tws": True,
        },
        next_tasks=single_tasks,
    )

    continuous_allowed = _env_bool("FIT_FOR_TRADING_ALLOW_CONTINUOUS_EXPERIMENT", False)
    continuous_reasons: List[str] = []
    continuous_tasks: List[str] = []
    if not continuous_allowed:
        continuous_reasons.append(
            "Continuous actual-live is policy-blocked for fit-for-trading status"
        )
        continuous_tasks.append(
            "Complete multiple monitored single-trade live experiments before enabling continuous policy"
        )
    else:
        continuous_reasons.extend(live_common_reasons)
        continuous_tasks.extend(live_common_tasks)
        if not live_config.live_continuous_enabled:
            continuous_reasons.append("AUTONOMOUS_LIVE_CONTINUOUS_ENABLED is false")
            continuous_tasks.append("Set AUTONOMOUS_LIVE_CONTINUOUS_ENABLED=true only after single-trade evidence")
        if live_config.max_live_trades_per_day <= 1:
            continuous_reasons.append("Continuous mode requires max_live_trades_per_day > 1")
            continuous_tasks.append("Set an explicit conservative daily cap greater than 1")

    criteria["actual_live_continuous"] = _criterion(
        "actual_live_continuous",
        "Actual live continuous trading",
        YES if continuous_allowed and not continuous_reasons else (NO if continuous_allowed else BLOCKED),
        continuous_reasons,
        evidence={
            **connection_evidence,
            **config_evidence,
            "policy_flag": "FIT_FOR_TRADING_ALLOW_CONTINUOUS_EXPERIMENT",
            "policy_flag_enabled": continuous_allowed,
        },
        next_tasks=continuous_tasks,
    )

    capital_growth_allowed = _env_bool("FIT_FOR_TRADING_ALLOW_CAPITAL_GROWTH", False)
    capital_reasons = []
    capital_tasks = []
    if not capital_growth_allowed:
        capital_reasons.append(
            "Managing meaningful capital remains policy-blocked until live evidence, monitoring, and operator runbooks are proven"
        )
        capital_tasks.extend([
            "Complete and review a live dry-run log",
            "Complete multiple single-trade live experiments with bracket exits confirmed",
            "Document operator monitoring and emergency procedures",
            "Review performance evidence before raising capital allocation",
        ])

    criteria["capital_growth_50k"] = _criterion(
        "capital_growth_50k",
        "Autonomous management of meaningful capital",
        YES if capital_growth_allowed else BLOCKED,
        capital_reasons,
        evidence={
            "policy_flag": "FIT_FOR_TRADING_ALLOW_CAPITAL_GROWTH",
            "policy_flag_enabled": capital_growth_allowed,
        },
        next_tasks=capital_tasks,
    )

    small_live_ready = (
        criteria["live_dry_run"]["fit"]
        and criteria["actual_live_single_trade"]["fit"]
    )
    if small_live_ready:
        overall = "FIT_FOR_SMALL_LIVE_EXPERIMENT"
        overall_reasons: List[str] = []
    else:
        overall = "NOT_READY_FOR_LIVE_EXPERIMENT"
        overall_reasons = (
            criteria["live_dry_run"]["reasons"]
            + criteria["actual_live_single_trade"]["reasons"]
        )

    live_config_dict = live_config.to_dict()
    if "expected_account_id" in live_config_dict:
        live_config_dict["expected_account_id"] = _mask_account(
            live_config_dict["expected_account_id"] or ""
        )

    return {
        "overall_status": overall,
        "overall_fit": small_live_ready,
        "scope": "small_single_trade_live_experiment",
        "overall_reasons": overall_reasons,
        "connection": connection_evidence,
        "live_config": live_config_dict,
        "criteria": criteria,
    }


@bp.route("/status", methods=["GET"])
def trading_readiness_status():
    """Return the current fit-for-trading status matrix."""

    return jsonify(_build_status_payload())
