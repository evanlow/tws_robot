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
    DUPLICATE_ORDER_BLOCKED,
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
        return (
            None,
            None,
            f"{symbol}: basket leg trade_type {trade_type!r} is not BUY_SHARES; only BUY_SHARES is supported",
            [],
        )
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
    idempotency_acquisition = None
    if not self._config.live_dry_run:
        duplicate_reason = self._duplicate_symbol_reason(symbol)
        if duplicate_reason:
            self._block_duplicate_plan(
                lifecycle_events=lifecycle_events,
                lifecycle_id=entry_lifecycle_id,
                symbol=symbol,
                reason=duplicate_reason,
            )
            return None, None, duplicate_reason, lifecycle_events
        try:
            idempotency_acquisition = self._acquire_idempotency_for_plan(
                decision,
                plan,
            )
        except OSError as exc:
            logger.exception("failed to acquire autonomous idempotency lock")
            return None, None, f"idempotency lock write failed before submission: {exc}", lifecycle_events
        if not idempotency_acquisition.acquired:
            reason = idempotency_acquisition.reason or "duplicate idempotency lock"
            self._block_duplicate_plan(
                lifecycle_events=lifecycle_events,
                lifecycle_id=entry_lifecycle_id,
                symbol=symbol,
                reason=reason,
                idempotency_key=idempotency_acquisition.lock.key,
            )
            return None, None, reason, lifecycle_events
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
        self._clear_idempotency_lock(
            idempotency_acquisition,
            reason="order lifecycle write failed before submission",
        )
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
        self._clear_idempotency_lock(
            idempotency_acquisition,
            reason="OrderExecutor raised before returning a result",
        )
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
        self._clear_idempotency_lock(
            idempotency_acquisition,
            reason=f"OrderExecutor rejected: {result.reason}",
        )
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
    if result.status == OrderStatus.SUBMITTED:
        self._mark_idempotency_submitted(
            idempotency_acquisition,
            broker_order_id=result.order_id,
            autonomous_trade_id=trade.autonomous_trade_id if trade else None,
            metadata={"symbol": symbol, "quantity": quantity, "basket_leg": True},
        )
    return result, trade, None, lifecycle_events


def _duplicate_event_seen(events: List[Dict[str, Any]]) -> bool:
    return any(
        event.get("state") == OrderLifecycleState.DUPLICATE_ORDER_BLOCKED.value
        for event in events
    )


def _preflight_duplicate_basket(self: AutonomousLiveRunner, trade_plans: List[Dict[str, Any]]) -> Optional[tuple[str, List[Dict[str, Any]]]]:
    if self._config.live_dry_run or self._config.allow_duplicate_symbol_live_entries:
        return None

    lifecycle_events: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()
    try:
        active_locks = self._idempotency_store.current_locks()
    except OSError as exc:
        logger.exception("failed to replay autonomous idempotency locks")
        return f"idempotency lock replay failed before basket submission: {exc}", lifecycle_events

    for plan in trade_plans:
        symbol = str(plan.get("symbol") or "").strip().upper()
        lifecycle_id = OrderLifecycleEvent.new_id()
        reason = None
        idempotency_key = None
        if not symbol:
            reason = "missing symbol for idempotency check"
        elif symbol in seen_symbols:
            reason = f"basket contains more than one live entry for {symbol}"
        else:
            duplicate_reason = self._duplicate_symbol_reason(symbol)
            if duplicate_reason:
                reason = duplicate_reason
            else:
                key = self._idempotency_store.build_key(
                    symbol=symbol,
                    intended_action="BUY",
                )
                lock = active_locks.get(key)
                if lock is not None and lock.active:
                    reason = f"active idempotency lock exists for {key}"
                    idempotency_key = key
        if reason:
            self._block_duplicate_plan(
                lifecycle_events=lifecycle_events,
                lifecycle_id=lifecycle_id,
                symbol=symbol,
                reason=reason,
                idempotency_key=idempotency_key,
            )
            return reason, lifecycle_events
        seen_symbols.add(symbol)
    return None


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
        DecisionStatus.UNECONOMIC_AFTER_COMMISSION,
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

    duplicate_preflight = _preflight_duplicate_basket(self, trade_plans)
    if duplicate_preflight is not None:
        duplicate_reason, lifecycle_events = duplicate_preflight
        status = (
            DUPLICATE_ORDER_BLOCKED
            if _duplicate_event_seen(lifecycle_events)
            else EXECUTION_FAILED
        )
        return AutonomousLiveRunResult(
            status=status,
            gates=gates,
            rejection_reason=duplicate_reason,
            decision=decision_payload,
            order_lifecycle=lifecycle_events,
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

    # Preflight pass: compute the deployable-cash-capped quantity and run the
    # commission-aware profitability re-check for *every* basket leg before any
    # leg is submitted.  Submitting leg 1 and then rejecting leg 2 after the cap
    # would leave unsurfaced partial live exposure, so the whole basket must be
    # rejected up front if any capped leg is unbuyable or uneconomic.  The
    # profitability gate is a no-op when disabled.
    gate = getattr(self._engine, "profitability_gate", None)
    gate_enabled = gate is not None and getattr(gate, "enabled", False)
    capped_plans: List[Dict[str, Any]] = []
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

        if gate_enabled and plan.get("trade_type") == TradeType.BUY_SHARES.value:
            profit_decision = gate.evaluate_buy_shares(
                symbol=str(plan.get("symbol") or ""),
                quantity=quantity,
                entry_price=limit_price,
                target_price=plan.get("target_price"),
            )
            if not profit_decision.allowed:
                return AutonomousLiveRunResult(
                    status=NO_TRADE,
                    gates=gates,
                    rejection_reason=(
                        f"uneconomic after commission — {profit_decision.reason}"
                    ),
                    decision=decision_payload,
                    dry_run=self._config.live_dry_run,
                    notes=notes + [f"profitability={profit_decision.to_dict()}"],
                )

        capped_plans.append({"plan": plan, "quantity": quantity})

    for entry in capped_plans:
        plan = entry["plan"]
        quantity = entry["quantity"]
        result, trade, error, leg_lifecycle_events = _execute_one_live_plan(
            self, decision, plan, quantity, gates, deployable_cash, max_trade_value
        )
        lifecycle_events.extend(leg_lifecycle_events)
        if error:
            status = (
                DUPLICATE_ORDER_BLOCKED
                if _duplicate_event_seen(leg_lifecycle_events)
                else EXECUTION_FAILED
            )
            return AutonomousLiveRunResult(
                status=status,
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
    if len(trade_plans) == 1:
        single_trade = submitted_trades[0] if submitted_trades else None
        trade_payload = None
        if single_trade is not None:
            trade_payload = {"submitted_trades": [single_trade], **single_trade}
        return AutonomousLiveRunResult(
            status=status,
            gates=gates,
            decision=decision_payload,
            trade=trade_payload,
            order_lifecycle=lifecycle_events,
            notes=notes,
            dry_run=dry_run_seen,
        )
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
