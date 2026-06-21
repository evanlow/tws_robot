"""Basket-aware live-runner execution patch.

This module patches ``AutonomousLiveRunner.run_once`` so assisted-live mode can
submit either a single trade plan or a basket of trade plans returned by
``AutonomousTradingEngine``.  The feature remains governed by the same live
runner gates, OrderExecutor safety checks, bracket logic, and trade-store
recording used for single-leg live execution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from autonomous.autonomous_config import AutonomousMode
from autonomous.autonomous_engine import DecisionStatus
from autonomous.autonomous_live_runner import (
    AutonomousLiveRunResult,
    AutonomousLiveRunner,
    DAILY_LIVE_TRADE_LIMIT_REACHED,
    DRY_RUN_EXECUTED,
    EMERGENCY_STOP_ACTIVE,
    ENGINE_REJECTED,
    EXECUTED,
    EXECUTION_FAILED,
    NO_TRADE,
    _as_float,
)
from autonomous.order_lifecycle import ENTRY, STOP, TARGET, OrderLifecycleEvent, OrderLifecycleState
from autonomous.trade_planner import TradeType
from execution.order_executor import OrderStatus
from strategies.signal import Signal, SignalStrength, SignalType

logger = logging.getLogger(__name__)


def _execute_one_live_plan(self: AutonomousLiveRunner, decision, plan: Dict[str, Any], quantity: int, gates, deployable_cash: float, max_trade_value: float):
    symbol = str(plan.get("symbol") or "")
    trade_type = plan.get("trade_type")
    if trade_type != TradeType.BUY_SHARES.value:
        return None, None, f"{symbol}: basket leg trade_type {trade_type!r} is not BUY_SHARES; only BUY_SHARES is supported"
    limit_price = float(plan.get("limit_price") or 0.0)
    plan_target_price = _as_float(plan.get("target_price"))
    plan_stop_price = _as_float(plan.get("stop_price"))
    bracket_notes: List[str] = []

    if plan_stop_price is None or plan_stop_price <= 0:
        synthesized_stop = round(limit_price * (1.0 - self._config.default_stop_pct), 2)
        if synthesized_stop > 0 and synthesized_stop < limit_price:
            bracket_notes.append(
                f"stop_price synthesised from default_stop_pct={self._config.default_stop_pct} → "
                f"{synthesized_stop:.2f} (plan had no stop_price)"
            )
            plan_stop_price = synthesized_stop

    signal = Signal(
        symbol=symbol,
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(timezone.utc),
        quantity=quantity,
        target_price=limit_price,
        take_profit=plan_target_price,
        stop_loss=plan_stop_price,
    )
    if self._config.live_limit_orders_only:
        signal.strategy_name = "AutonomousLiveRunner:LIMIT"

    lifecycle_events: List[Dict[str, Any]] = []
    entry_lifecycle_id = OrderLifecycleEvent.new_id()
    try:
        lifecycle_events.append(
            self._record_order_lifecycle_transition(
                lifecycle_id=entry_lifecycle_id,
                state=OrderLifecycleState.PLANNED,
                symbol=symbol,
                order_role=ENTRY,
                reason="basket live runner prepared leg for OrderExecutor",
                metadata={
                    "quantity": quantity,
                    "limit_price": limit_price,
                    "target_price": plan_target_price,
                    "stop_price": plan_stop_price,
                    "dry_run": self._config.live_dry_run,
                    "basket_leg": True,
                },
            )
        )
    except OSError as exc:
        logger.exception("failed to record autonomous order lifecycle PLANNED event")
        return None, None, f"order lifecycle write failed before submission: {exc}", lifecycle_events

    try:
        broker_positions: Dict[str, Any] = (
            self._broker_positions_provider()
            if self._broker_positions_provider is not None
            else {}
        )
        result = self._executor.execute_signal(
            strategy_name="AutonomousLiveRunner",
            signal=signal,
            current_equity=gates.deployable_cash,
            positions=broker_positions,
        )
    except Exception:
        logger.exception("OrderExecutor.execute_signal raised")
        self._safe_record_order_lifecycle_transition(
            lifecycle_events,
            lifecycle_id=entry_lifecycle_id,
            state=OrderLifecycleState.BROKER_DISCONNECTED,
            symbol=symbol,
            order_role=ENTRY,
            reason="OrderExecutor raised an exception before returning a result",
        )
        return None, None, "OrderExecutor raised an exception", lifecycle_events

    if result.status not in {OrderStatus.SUBMITTED, OrderStatus.DRY_RUN}:
        self._safe_record_order_lifecycle_transition(
            lifecycle_events,
            lifecycle_id=entry_lifecycle_id,
            state=OrderLifecycleState.REJECTED,
            symbol=symbol,
            order_role=ENTRY,
            reason=f"OrderExecutor rejected {symbol}: {result.reason}",
        )
        return result, None, f"OrderExecutor rejected {symbol}: {result.reason}", lifecycle_events

    target_id = getattr(result, "bracket_target_order_id", None)
    stop_id = getattr(result, "bracket_stop_order_id", None)
    target_lifecycle_id = None
    stop_lifecycle_id = None
    if result.status == OrderStatus.DRY_RUN:
        self._safe_record_order_lifecycle_transition(
            lifecycle_events,
            lifecycle_id=entry_lifecycle_id,
            state=OrderLifecycleState.EXPIRED,
            symbol=symbol,
            order_role=ENTRY,
            reason="dry-run preview; basket leg was not submitted to broker",
        )
    else:
        self._safe_record_order_lifecycle_transition(
            lifecycle_events,
            lifecycle_id=entry_lifecycle_id,
            state=OrderLifecycleState.SUBMITTED,
            symbol=symbol,
            order_role=ENTRY,
            broker_order_id=result.order_id,
            reason="OrderExecutor returned SUBMITTED for basket leg",
            metadata={"quantity": quantity, "limit_price": limit_price},
        )
        if target_id is not None:
            target_lifecycle_id = OrderLifecycleEvent.new_id()
            self._safe_record_order_lifecycle_transition(
                lifecycle_events,
                lifecycle_id=target_lifecycle_id,
                state=OrderLifecycleState.TARGET_PENDING,
                symbol=symbol,
                order_role=TARGET,
                broker_order_id=target_id,
                parent_lifecycle_id=entry_lifecycle_id,
                reason="basket bracket target child order submitted with parent",
                metadata={"target_price": plan_target_price},
            )
        if stop_id is not None:
            stop_lifecycle_id = OrderLifecycleEvent.new_id()
            self._safe_record_order_lifecycle_transition(
                lifecycle_events,
                lifecycle_id=stop_lifecycle_id,
                state=OrderLifecycleState.PROTECTIVE_STOP_PENDING,
                symbol=symbol,
                order_role=STOP,
                broker_order_id=stop_id,
                parent_lifecycle_id=entry_lifecycle_id,
                reason="basket bracket protective stop child order submitted with parent",
                metadata={"stop_price": plan_stop_price},
            )

    trade = self._record_trade(
        decision,
        plan,
        quantity,
        result.order_id,
        entry_lifecycle_id=entry_lifecycle_id,
        target_lifecycle_id=target_lifecycle_id,
        stop_lifecycle_id=stop_lifecycle_id,
        target_order_id=target_id,
        stop_order_id=stop_id,
        extra_notes=bracket_notes,
    )
    return result, trade, None, lifecycle_events


def _basket_aware_run_once(self: AutonomousLiveRunner) -> AutonomousLiveRunResult:
    gates = self.evaluate_gates()
    if not gates.ready:
        return AutonomousLiveRunResult(
            status=self._first_gate_status(gates),
            gates=gates,
            rejection_reason="; ".join(gates.reasons()) or "live runner gates failed",
            dry_run=self._config.live_dry_run,
        )

    self._engine.config.mode = AutonomousMode.ASSISTED_LIVE
    self._engine.config.allow_live_execution = True

    decision = self._engine.run_once(confirm=True)
    decision_payload = decision.to_dict()

    no_trade_statuses = (
        DecisionStatus.NO_CANDIDATE,
        DecisionStatus.NO_TRADE_PLAN,
        DecisionStatus.NO_DEPLOYABLE_CASH,
        DecisionStatus.MARKET_NOT_SUITABLE,
        DecisionStatus.DAILY_LIMIT_REACHED,
        DecisionStatus.RISK_REJECTED,
    )
    if decision.status in no_trade_statuses:
        return AutonomousLiveRunResult(
            status=NO_TRADE,
            gates=gates,
            rejection_reason=decision.rejection_reason,
            decision=decision_payload,
            dry_run=self._config.live_dry_run,
        )

    if decision.status == DecisionStatus.EMERGENCY_STOP:
        return AutonomousLiveRunResult(
            status=EMERGENCY_STOP_ACTIVE,
            gates=gates,
            rejection_reason=decision.rejection_reason,
            decision=decision_payload,
            dry_run=self._config.live_dry_run,
        )

    if decision.status != DecisionStatus.LIVE_PLAN_READY:
        return AutonomousLiveRunResult(
            status=ENGINE_REJECTED,
            gates=gates,
            rejection_reason=(
                f"engine returned {decision.status.value!r}; only LIVE_PLAN_READY is executable by the live runner"
            ),
            decision=decision_payload,
            dry_run=self._config.live_dry_run,
        )

    trade_plans = list(getattr(decision, "trade_plans", []) or [])
    if not trade_plans and decision.trade_plan:
        trade_plans = [decision.trade_plan]
    if not trade_plans:
        return AutonomousLiveRunResult(
            status=EXECUTION_FAILED,
            gates=gates,
            rejection_reason="engine returned no trade plan",
            decision=decision_payload,
            dry_run=self._config.live_dry_run,
        )

    available_slots = max(0, gates.max_open_live_trades - gates.open_live_trades)
    available_daily = max(0, gates.max_live_trades_per_day - gates.live_trades_today)
    max_legs = min(available_slots, available_daily)
    if len(trade_plans) > max_legs:
        return AutonomousLiveRunResult(
            status=NO_TRADE,
            gates=gates,
            rejection_reason=(
                f"basket has {len(trade_plans)} legs but only {max_legs} live trade slots available"
            ),
            decision=decision_payload,
            dry_run=self._config.live_dry_run,
        )

    deployable_cash = gates.deployable_cash
    max_trade_value = deployable_cash * self._config.max_deployable_cash_pct
    submitted_trades = []
    order_ids: List[int] = []
    notes = [
        f"live basket execution path — legs={len(trade_plans)}",
        f"deployable_cash={deployable_cash:.2f}",
        f"max_deployable_cash_pct={self._config.max_deployable_cash_pct}",
        f"max_trade_value={max_trade_value:.2f}",
    ]
    dry_run_seen = False
    lifecycle_events: List[Dict[str, Any]] = []

    for plan in trade_plans:
        limit_price = float(plan.get("limit_price") or 0.0)
        quantity = int(plan.get("quantity") or 0)
        if limit_price > 0 and quantity > 0:
            proposed_value = limit_price * quantity
            if proposed_value > max_trade_value:
                quantity = int(max_trade_value // limit_price)
        if quantity <= 0:
            return AutonomousLiveRunResult(
                status=NO_TRADE,
                gates=gates,
                rejection_reason=(
                    f"deployable-cash cap too small to buy 1 share of {plan.get('symbol')} at {limit_price:.2f}"
                ),
                decision=decision_payload,
                dry_run=self._config.live_dry_run,
                notes=notes,
            )

        result, trade, error, leg_lifecycle_events = _execute_one_live_plan(
            self, decision, plan, quantity, gates, deployable_cash, max_trade_value
        )
        lifecycle_events.extend(leg_lifecycle_events)
        if error:
            return AutonomousLiveRunResult(
                status=EXECUTION_FAILED,
                gates=gates,
                rejection_reason=error,
                decision=decision_payload,
                trade={"submitted_trades": submitted_trades} if submitted_trades else None,
                order_lifecycle=lifecycle_events,
                dry_run=self._config.live_dry_run,
                notes=notes,
            )
        if result is not None and result.order_id is not None:
            order_ids.append(int(result.order_id))
        if result is not None and result.status == OrderStatus.DRY_RUN:
            dry_run_seen = True
        if trade is not None:
            submitted_trades.append(trade.to_dict())
        notes.append(f"{plan.get('symbol')}: quantity={quantity} status={getattr(result, 'status', None)}")

    status = DRY_RUN_EXECUTED if dry_run_seen else EXECUTED
    return AutonomousLiveRunResult(
        status=status,
        gates=gates,
        decision=decision_payload,
        trade={
            "basket": len(trade_plans) > 1,
            "submitted_trades": submitted_trades,
            "order_ids": order_ids,
        },
        order_lifecycle=lifecycle_events,
        notes=notes,
        dry_run=dry_run_seen,
    )


# Patch once at import time.  This avoids rewriting the long live-runner module
# while keeping its existing gates, constants, and reconciliation helpers.
if getattr(AutonomousLiveRunner.run_once, "__name__", "") != "_basket_aware_run_once":
    AutonomousLiveRunner.run_once = _basket_aware_run_once
