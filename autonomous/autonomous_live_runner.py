"""Live-account autonomous runner.

Wraps :class:`autonomous.AutonomousTradingEngine` with the additional
safety gates required to make a live-autonomous cycle safe:

* live-mode connection must be active (``connection_env == "live"``)
* account ID must match the expected ID
* ``AUTONOMOUS_LIVE_ENABLED`` must be ``true`` in config
* ``AUTONOMOUS_LIVE_CONTINUOUS_ENABLED`` must be ``true`` for continuous mode
* deployable cash must be above the configured minimum
* deployable-cash cap must be respected per trade
* emergency stop must not be active
* signal provider must be ready
* daily-trade-limit / max-open-trades must not be exceeded
* all orders route through :class:`execution.order_executor.OrderExecutor`
* only LIMIT orders are placed

Design notes
------------

**This module never uses AutonomousPaperAdapter.**  All order placement
flows through :class:`execution.order_executor.OrderExecutor`, which
enforces its own multi-layer safety checks (risk manager, portfolio
reconciliation, emergency stop, live-session confirmation, etc.) before
any order reaches TWS.

The runner is synchronous and single-shot: one :meth:`run_once` call
executes one decision cycle and returns.  Continuous mode is implemented
at the caller level (``api_autonomous.py``) by calling ``run_once``
repeatedly after each prior lifecycle completes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from autonomous.autonomous_config import AutonomousMode
from autonomous.autonomous_engine import AutonomousDecision, AutonomousTradingEngine, DecisionStatus
from autonomous.runner_config import AutonomousLiveRunnerConfig
from autonomous.signal_provider import StaticSignalProvider
from autonomous.trade_planner import TradeType
from autonomous.trade_store import (
    CLOSED,
    EXIT_PENDING,
    FAILED,
    OPEN,
    AutonomousTrade,
    TradeStore,
)
from execution.order_executor import OrderStatus
from strategies.signal import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rejection codes
# ---------------------------------------------------------------------------

NOT_CONNECTED = "not_connected"
NOT_LIVE_MODE = "not_live_mode"
LIVE_DISABLED = "live_disabled"
LIVE_CONTINUOUS_DISABLED = "live_continuous_disabled"
ACCOUNT_ID_MISMATCH = "account_id_mismatch"
ACCOUNT_ID_UNVERIFIED = "account_id_unverified"
SIGNAL_PROVIDER_NOT_READY = "signal_provider_not_ready"
EMERGENCY_STOP_ACTIVE = "emergency_stop_active"
MAX_OPEN_TRADES = "max_open_autonomous_trades_reached"
DAILY_LIVE_TRADE_LIMIT_REACHED = "daily_live_trade_limit_reached"
DEPLOYABLE_CASH_BELOW_MINIMUM = "deployable_cash_below_minimum"
EXECUTED = "executed"
DRY_RUN_EXECUTED = "dry_run_executed"
NO_TRADE = "no_trade"
ENGINE_REJECTED = "engine_rejected"
EXECUTION_FAILED = "execution_failed"


# ---------------------------------------------------------------------------
# Readiness gate snapshot
# ---------------------------------------------------------------------------


@dataclass
class LiveReadinessGates:
    """Snapshot of the readiness checks evaluated for a live ``run_once``."""

    connected: bool = False
    live_mode: bool = False
    live_enabled: bool = False
    live_continuous_enabled: bool = False
    account_id_verified: bool = False
    signal_provider_ready: bool = False
    emergency_stop_active: bool = False
    open_live_trades: int = 0
    max_open_live_trades: int = 1
    live_trades_today: int = 0
    max_live_trades_per_day: int = 1
    deployable_cash: float = 0.0
    min_deployable_cash: float = 1000.0
    # Set only when ``live_continuous_enabled`` check is skipped
    # (i.e. a non-continuous / single-cycle call).
    continuous_mode_required: bool = False

    @property
    def ready(self) -> bool:
        """All gates pass and we are below the open-trades limit."""
        base = (
            self.connected
            and self.live_mode
            and self.live_enabled
            and self.account_id_verified
            and self.signal_provider_ready
            and not self.emergency_stop_active
            and self.open_live_trades < self.max_open_live_trades
            and self.live_trades_today < self.max_live_trades_per_day
            and self.deployable_cash >= self.min_deployable_cash
        )
        if self.continuous_mode_required:
            return base and self.live_continuous_enabled
        return base

    def reasons(self) -> List[str]:
        """Human-readable list of failed gates (empty when ``ready``)."""
        out: List[str] = []
        if not self.connected:
            out.append("Not connected to IBKR")
        if not self.live_mode:
            out.append("Not connected to a live account (connection_env != 'live')")
        if not self.live_enabled:
            out.append(
                "Live autonomous trading is disabled. "
                "Set AUTONOMOUS_LIVE_ENABLED=true in .env to enable."
            )
        if self.continuous_mode_required and not self.live_continuous_enabled:
            out.append(
                "Live continuous mode is disabled. "
                "Set AUTONOMOUS_LIVE_CONTINUOUS_ENABLED=true in .env to enable."
            )
        if not self.account_id_verified:
            out.append("Live account ID could not be verified or does not match expected ID")
        if not self.signal_provider_ready:
            out.append("Signal provider not ready")
        if self.emergency_stop_active:
            out.append("Emergency stop active")
        if self.open_live_trades >= self.max_open_live_trades:
            out.append(
                f"Max open live autonomous trades reached "
                f"({self.open_live_trades}/{self.max_open_live_trades})"
            )
        if self.live_trades_today >= self.max_live_trades_per_day:
            out.append(
                f"Daily live trade limit reached "
                f"({self.live_trades_today}/{self.max_live_trades_per_day})"
            )
        if self.deployable_cash < self.min_deployable_cash:
            out.append(
                f"Deployable cash {self.deployable_cash:.2f} is below the "
                f"configured minimum {self.min_deployable_cash:.2f}"
            )
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "live_mode": self.live_mode,
            "live_enabled": self.live_enabled,
            "live_continuous_enabled": self.live_continuous_enabled,
            "account_id_verified": self.account_id_verified,
            "signal_provider_ready": self.signal_provider_ready,
            "emergency_stop_active": self.emergency_stop_active,
            "open_live_trades": self.open_live_trades,
            "max_open_live_trades": self.max_open_live_trades,
            "live_trades_today": self.live_trades_today,
            "max_live_trades_per_day": self.max_live_trades_per_day,
            "deployable_cash": round(self.deployable_cash, 2),
            "min_deployable_cash": self.min_deployable_cash,
            "continuous_mode_required": self.continuous_mode_required,
            "ready": self.ready,
            "reasons": self.reasons(),
        }


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------


@dataclass
class AutonomousLiveRunResult:
    """Structured result for a single :meth:`AutonomousLiveRunner.run_once` call."""

    status: str
    gates: LiveReadinessGates
    rejection_reason: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    trade: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "gates": self.gates.to_dict(),
            "decision": self.decision,
            "trade": self.trade,
            "notes": list(self.notes),
            "dry_run": self.dry_run,
        }


# ---------------------------------------------------------------------------
# Provider type aliases
# ---------------------------------------------------------------------------

ConnectedProvider = Callable[[], bool]
ConnectionEnvProvider = Callable[[], Optional[str]]
AccountIdProvider = Callable[[], Optional[str]]
EmergencyStopProvider = Callable[[], bool]
SignalProviderProvider = Callable[[], Any]
DeployableCashProvider = Callable[[], float]
BrokerPositionsProvider = Callable[[], Dict[str, Any]]
RejectedOrderIdsProvider = Callable[[], Iterable[int]]
FilledOrderIdsProvider = Callable[[], Iterable[int]]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class AutonomousLiveRunner:
    """Run one live-only autonomous cycle through OrderExecutor.

    Parameters
    ----------
    engine:
        Pre-built :class:`AutonomousTradingEngine`.  The runner enforces
        live-only gates and forwards to ``engine.run_once`` in
        ``ASSISTED_LIVE`` mode.  The engine itself performs the full
        scan / plan / risk-check pipeline.
    trade_store:
        Persistence for opened autonomous live trades.
    live_config:
        Safety configuration for the live runner (limits, switches,
        deployable-cash cap).
    order_executor:
        :class:`execution.order_executor.OrderExecutor` configured for
        live mode.  All orders route through this executor.
    connected_provider:
        Callable returning whether TWS is currently connected.
    connection_env_provider:
        Callable returning ``"live"`` / ``"paper"`` / ``None``.
    account_id_provider:
        Callable returning the active IBKR account identifier string.
    signal_provider_provider:
        Callable returning the active signal provider.
    emergency_stop_provider:
        Callable returning ``True`` when emergency stop is active.
    deployable_cash_provider:
        Callable returning current deployable cash (float).
    broker_positions_provider:
        Callable returning the current broker positions as a
        ``Dict[symbol, Position]`` for portfolio reconciliation.
        When ``None``, an empty dict is passed to
        :meth:`execution.order_executor.OrderExecutor.execute_signal`,
        which will cause reconciliation to reject any execution when the
        broker holds open positions.
    rejected_order_ids_provider:
        Callable returning an iterable of broker order IDs the broker
        has rejected since the last call (typically
        ``svc.tws_bridge.pop_rejected_order_ids``).  At the start of
        each ``run_once`` the runner marks any matching OPEN trade in
        the trade store as ``FAILED`` so a rejected order does not
        keep burning a slot against ``max_open_live_trades`` or
        ``max_live_trades_per_day``.
    filled_order_ids_provider:
        Callable returning an iterable of broker order IDs that TWS
        has reported fully filled since the last call (typically
        ``svc.tws_bridge.pop_filled_order_ids``).  At the start of
        each ``run_once`` the runner flips any OPEN/EXIT_PENDING
        trade whose ``target_order_id`` or ``stop_order_id`` matches
        to ``CLOSED`` — so a bracket child fill (take-profit / stop)
        unblocks Continuous mode for the next cycle.
    continuous_mode:
        When ``True``, the ``AUTONOMOUS_LIVE_CONTINUOUS_ENABLED`` gate
        is also checked.  Set to ``True`` for continuous live cycles.
    """

    def __init__(
        self,
        engine: AutonomousTradingEngine,
        trade_store: TradeStore,
        live_config: Optional[AutonomousLiveRunnerConfig] = None,
        *,
        order_executor: Any,
        connected_provider: ConnectedProvider,
        connection_env_provider: ConnectionEnvProvider,
        account_id_provider: AccountIdProvider,
        signal_provider_provider: SignalProviderProvider,
        emergency_stop_provider: EmergencyStopProvider,
        deployable_cash_provider: DeployableCashProvider,
        broker_positions_provider: Optional[BrokerPositionsProvider] = None,
        rejected_order_ids_provider: Optional[RejectedOrderIdsProvider] = None,
        filled_order_ids_provider: Optional[FilledOrderIdsProvider] = None,
        continuous_mode: bool = False,
    ) -> None:
        self._engine = engine
        self._store = trade_store
        self._config = live_config or AutonomousLiveRunnerConfig()
        self._executor = order_executor
        self._connected_provider = connected_provider
        self._connection_env_provider = connection_env_provider
        self._account_id_provider = account_id_provider
        self._signal_provider_provider = signal_provider_provider
        self._emergency_stop_provider = emergency_stop_provider
        self._deployable_cash_provider = deployable_cash_provider
        self._broker_positions_provider = broker_positions_provider
        self._rejected_order_ids_provider = rejected_order_ids_provider
        self._filled_order_ids_provider = filled_order_ids_provider
        self._continuous_mode = continuous_mode

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def config(self) -> AutonomousLiveRunnerConfig:
        return self._config

    @property
    def trade_store(self) -> TradeStore:
        return self._store

    @property
    def continuous_mode(self) -> bool:
        return self._continuous_mode

    @property
    def order_executor(self) -> Any:
        """The :class:`execution.order_executor.OrderExecutor` wired to this runner."""
        return self._executor

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    def evaluate_gates(self) -> LiveReadinessGates:
        """Evaluate every readiness gate; never raises."""
        # Drain any broker-rejected order IDs first so the trade-store
        # counters reflect reality (rejected orders → FAILED, not OPEN).
        self._reconcile_rejected_trades()
        # Then reconcile any bracket fills (target/stop) so a closed
        # trade no longer counts against the open-trades cap.
        self._reconcile_filled_brackets()

        try:
            connected = bool(self._connected_provider())
        except Exception:  # pragma: no cover - defensive
            connected = False

        try:
            env = self._connection_env_provider()
        except Exception:  # pragma: no cover - defensive
            env = None

        try:
            account_id = self._account_id_provider()
        except Exception:  # pragma: no cover - defensive
            account_id = None

        # Verify live account ID against the expected value (when set).
        account_id_verified = self._verify_account_id(account_id)

        try:
            provider = self._signal_provider_provider()
        except Exception:  # pragma: no cover - defensive
            provider = None
        provider_ready = provider is not None and not isinstance(
            provider, StaticSignalProvider
        )

        try:
            estop = bool(self._emergency_stop_provider())
        except Exception:  # pragma: no cover - defensive
            estop = False

        try:
            deployable_cash = float(self._deployable_cash_provider())
        except Exception:  # pragma: no cover - defensive
            deployable_cash = 0.0

        return LiveReadinessGates(
            connected=connected,
            live_mode=(env == "live"),
            live_enabled=self._config.live_enabled,
            live_continuous_enabled=self._config.live_continuous_enabled,
            account_id_verified=account_id_verified,
            signal_provider_ready=provider_ready,
            emergency_stop_active=estop,
            open_live_trades=self._store.count_open(),
            max_open_live_trades=self._config.max_open_live_trades,
            live_trades_today=self._count_live_trades_today(),
            max_live_trades_per_day=self._config.max_live_trades_per_day,
            deployable_cash=deployable_cash,
            min_deployable_cash=self._config.min_deployable_cash,
            continuous_mode_required=self._continuous_mode,
        )

    def _verify_account_id(self, account_id: Optional[str]) -> bool:
        """Check the active account ID against the expected ID.

        Returns ``True`` when:
        * ``live_require_account_confirmation`` is ``False`` (check
          disabled), **or**
        * the active account ID is non-empty **and** the expected ID
          is empty (no expectation set), **or**
        * the active account ID matches ``expected_account_id`` exactly.

        Returns ``False`` when the account ID is empty, unknown, or
        mismatches the expected ID.
        """
        if not self._config.live_require_account_confirmation:
            return True
        if not account_id:
            return False
        expected = self._config.expected_account_id
        if expected:
            return str(account_id).strip().upper() == str(expected).strip().upper()
        # No expected ID set — just confirm the account ID is non-empty
        # (i.e. we *have* an account ID from the broker).
        return True

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run_once(self) -> AutonomousLiveRunResult:
        """Execute one live autonomous cycle through OrderExecutor.

        The runner enforces every gate **before** invoking the engine so
        a rejected run never reaches OrderExecutor.  When the engine
        produces a trade plan the runner:

        1. applies the deployable-cash cap to compute ``max_trade_value``,
        2. submits the order through :class:`OrderExecutor`,
        3. records the opened trade in :class:`TradeStore`.

        When ``live_dry_run=True`` the full path runs but no order is
        sent to TWS (OrderExecutor returns ``DRY_RUN`` status).
        """
        gates = self.evaluate_gates()
        if not gates.ready:
            return AutonomousLiveRunResult(
                status=self._first_gate_status(gates),
                gates=gates,
                rejection_reason="; ".join(gates.reasons()) or "live runner gates failed",
                dry_run=self._config.live_dry_run,
            )

        # Force ASSISTED_LIVE mode; live execution is the runner's job.
        self._engine.config.mode = AutonomousMode.ASSISTED_LIVE
        self._engine.config.allow_live_execution = True

        decision = self._engine.run_once(confirm=True)
        decision_payload = decision.to_dict()

        # Decision statuses that indicate no executable trade was found.
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

        # Only proceed when the engine explicitly signals the plan is ready
        # for live execution.  Any other status (including LIVE_BLOCKED or
        # CONFIRMATION_REQUIRED) is treated as a hard rejection — this
        # ensures the runner cannot bypass an explicit engine-level safety
        # block by accident.
        if decision.status != DecisionStatus.LIVE_PLAN_READY:
            return AutonomousLiveRunResult(
                status=ENGINE_REJECTED,
                gates=gates,
                rejection_reason=(
                    f"engine returned {decision.status.value!r}; "
                    "only LIVE_PLAN_READY is executable by the live runner"
                ),
                decision=decision_payload,
                dry_run=self._config.live_dry_run,
            )

        # Engine reached the LIVE_PLAN_READY path — we now own order placement.
        # The engine has completed all its checks (cash, scan, rank, risk) and
        # set trade_plan.  The runner submits through OrderExecutor.
        plan = decision.trade_plan
        if not plan:
            return AutonomousLiveRunResult(
                status=EXECUTION_FAILED,
                gates=gates,
                rejection_reason="engine returned no trade plan",
                decision=decision_payload,
                dry_run=self._config.live_dry_run,
            )

        # Apply deployable-cash cap.
        deployable_cash = gates.deployable_cash
        max_trade_value = deployable_cash * self._config.max_deployable_cash_pct
        raw_limit_price = plan.get("limit_price")
        raw_quantity = plan.get("quantity")
        limit_price = float(raw_limit_price) if raw_limit_price is not None else 0.0
        quantity = int(raw_quantity) if raw_quantity is not None else 0

        if limit_price > 0 and quantity > 0:
            proposed_value = limit_price * quantity
            if proposed_value > max_trade_value:
                capped_quantity = int(max_trade_value // limit_price)
                logger.info(
                    "AutonomousLiveRunner: capping quantity from %d to %d "
                    "(deployable_cash=%.2f cap_pct=%.2f max_trade_value=%.2f)",
                    quantity,
                    capped_quantity,
                    deployable_cash,
                    self._config.max_deployable_cash_pct,
                    max_trade_value,
                )
                quantity = capped_quantity

        if quantity <= 0:
            return AutonomousLiveRunResult(
                status=NO_TRADE,
                gates=gates,
                rejection_reason=(
                    f"deployable-cash cap too small to buy 1 share at "
                    f"{limit_price:.2f} "
                    f"(max_trade_value={max_trade_value:.2f})"
                ),
                decision=decision_payload,
                dry_run=self._config.live_dry_run,
                notes=[
                    f"deployable_cash={deployable_cash:.2f}",
                    f"max_deployable_cash_pct={self._config.max_deployable_cash_pct}",
                    f"max_trade_value={max_trade_value:.2f}",
                ],
            )

        # Submit via OrderExecutor.
        symbol = str(plan.get("symbol") or "")
        # Build the bracket exit legs from the plan.  When the planner did
        # not derive a stop (e.g. no support level was available), fall
        # back to a configurable percentage of the entry limit so every
        # live entry has a defined exit on both sides.
        plan_target_price = _as_float(plan.get("target_price"))
        plan_stop_price = _as_float(plan.get("stop_price"))
        bracket_notes: List[str] = []
        if plan_stop_price is None or plan_stop_price <= 0:
            synthesized_stop = round(
                limit_price * (1.0 - self._config.default_stop_pct), 2
            )
            if synthesized_stop > 0 and synthesized_stop < limit_price:
                bracket_notes.append(
                    f"stop_price synthesised from default_stop_pct="
                    f"{self._config.default_stop_pct} → {synthesized_stop:.2f} "
                    f"(plan had no stop_price)"
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

        # Limit-orders-only enforcement: mark strategy name so callers / logs
        # can distinguish this signal from non-limit autonomous signals.
        if self._config.live_limit_orders_only:
            signal.strategy_name = "AutonomousLiveRunner:LIMIT"

        try:
            broker_positions: Dict[str, Any] = (
                self._broker_positions_provider()
                if self._broker_positions_provider is not None
                else {}
            )
            if not broker_positions and not self._config.live_dry_run:
                logger.warning(
                    "AutonomousLiveRunner: broker_positions is empty for live "
                    "execution of %s — OrderExecutor reconciliation will reject "
                    "the order if the account holds any TWS positions; ensure "
                    "broker_positions_provider is correctly wired",
                    symbol,
                )
            result = self._executor.execute_signal(
                strategy_name="AutonomousLiveRunner",
                signal=signal,
                current_equity=gates.deployable_cash,
                positions=broker_positions,
            )
        except Exception:
            logger.exception("OrderExecutor.execute_signal raised")
            return AutonomousLiveRunResult(
                status=EXECUTION_FAILED,
                gates=gates,
                rejection_reason="OrderExecutor raised an exception",
                decision=decision_payload,
                dry_run=self._config.live_dry_run,
            )

        if result.status == OrderStatus.DRY_RUN:
            # Dry-run: record the would-be trade and return.
            trade = self._record_trade(
                decision, plan, quantity, result.order_id,
                target_order_id=getattr(result, "bracket_target_order_id", None),
                stop_order_id=getattr(result, "bracket_stop_order_id", None),
                extra_notes=bracket_notes,
            )
            return AutonomousLiveRunResult(
                status=DRY_RUN_EXECUTED,
                gates=gates,
                decision=decision_payload,
                trade=trade.to_dict() if trade else None,
                notes=[
                    "dry-run preview — order NOT submitted to TWS",
                    f"would-be quantity={quantity}",
                    f"deployable_cash={deployable_cash:.2f}",
                    f"max_deployable_cash_pct={self._config.max_deployable_cash_pct}",
                    f"max_trade_value={max_trade_value:.2f}",
                ] + bracket_notes,
                dry_run=True,
            )

        if result.status == OrderStatus.SUBMITTED:
            target_id = getattr(result, "bracket_target_order_id", None)
            stop_id = getattr(result, "bracket_stop_order_id", None)
            trade = self._record_trade(
                decision, plan, quantity, result.order_id,
                target_order_id=target_id,
                stop_order_id=stop_id,
                extra_notes=bracket_notes,
            )
            submit_notes = [
                "live order submitted via OrderExecutor",
                f"order_id={result.order_id}",
                f"quantity={quantity}",
            ]
            if target_id is not None and stop_id is not None:
                submit_notes.append(
                    f"bracket attached: target_order_id={target_id} "
                    f"stop_order_id={stop_id}"
                )
            submit_notes += [
                f"deployable_cash={deployable_cash:.2f}",
                f"max_deployable_cash_pct={self._config.max_deployable_cash_pct}",
                f"max_trade_value={max_trade_value:.2f}",
            ] + bracket_notes
            return AutonomousLiveRunResult(
                status=EXECUTED,
                gates=gates,
                decision=decision_payload,
                trade=trade.to_dict() if trade else None,
                notes=submit_notes,
                dry_run=False,
            )

        # Rejected / blocked by OrderExecutor.
        return AutonomousLiveRunResult(
            status=EXECUTION_FAILED,
            gates=gates,
            rejection_reason=f"OrderExecutor rejected: {result.reason}",
            decision=decision_payload,
            dry_run=self._config.live_dry_run,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _count_live_trades_today(self, today: Optional[date] = None) -> int:
        """Count live trades with entry_time on ``today`` (UTC date).

        Uses the trade store as the source of truth so a process restart
        cannot reset the counter.  OPEN / EXIT_PENDING / CLOSED entries
        all count — they represent orders the broker accepted.  ``FAILED``
        entries are excluded because the order never entered the book
        (rejected by TWS / OrderExecutor) and should not burn one of
        today's allowed live-trade slots.

        On any store access error the method returns ``max_live_trades_per_day``
        so the gate fails closed rather than silently allowing trades through.
        """
        today_date = today or datetime.now(timezone.utc).date()
        count = 0
        try:
            for trade in self._store.list_all():
                if trade.status == FAILED:
                    continue
                entry_time = trade.entry_time
                if isinstance(entry_time, str):
                    try:
                        entry_time = datetime.fromisoformat(entry_time)
                    except ValueError:
                        continue
                if entry_time is None:
                    continue
                if entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=timezone.utc)
                if entry_time.date() == today_date:
                    count += 1
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "failed to count live trades for today; failing closed "
                "(returning max_live_trades_per_day=%d)",
                self._config.max_live_trades_per_day,
            )
            return self._config.max_live_trades_per_day
        return count

    def _reconcile_rejected_trades(self) -> None:
        """Mark trade-store entries as FAILED for broker-rejected orders.

        Drains the broker-rejection set from
        ``rejected_order_ids_provider`` and, for each ID, finds the
        single OPEN trade whose ``entry_order_id`` matches and flips it
        to ``FAILED``.  No-op when no provider is wired, when the drain
        is empty, or when the store contains no matching open trade
        (it may already have been reconciled or closed).

        Never raises — reconciliation is best-effort.  Counter accuracy
        is more important than a strict guarantee that every rejected
        ID can be matched to a stored trade.
        """
        if self._rejected_order_ids_provider is None:
            return
        try:
            rejected = set(self._rejected_order_ids_provider())
        except Exception:  # pragma: no cover - defensive
            logger.exception("rejected_order_ids_provider raised")
            return
        if not rejected:
            return

        try:
            open_trades = self._store.list_open()
        except Exception:  # pragma: no cover - defensive
            logger.exception("trade store list_open failed during reconcile")
            return

        for trade in open_trades:
            if trade.entry_order_id in rejected:
                try:
                    self._store.update_trade(
                        trade.autonomous_trade_id,
                        status=FAILED,
                        notes=list(trade.notes or []) + [
                            f"reconciled: broker rejected entry order "
                            f"#{trade.entry_order_id}"
                        ],
                    )
                    logger.warning(
                        "AutonomousLiveRunner: reconciled rejected order "
                        "#%s (trade %s, %s) → FAILED",
                        trade.entry_order_id,
                        trade.autonomous_trade_id,
                        trade.symbol,
                    )
                except Exception:  # pragma: no cover - defensive
                    logger.exception(
                        "failed to mark rejected trade %s as FAILED",
                        trade.autonomous_trade_id,
                    )

    def _reconcile_filled_brackets(self) -> None:
        """Flip OPEN/EXIT_PENDING trades to CLOSED on bracket-child fill.

        Drains the broker-filled order-ID set from
        ``filled_order_ids_provider``.  For each filled ID:

        * if it matches an open trade's ``target_order_id`` → mark
          CLOSED with ``exit_reason='TAKE_PROFIT'``
        * if it matches an open trade's ``stop_order_id`` → mark
          CLOSED with ``exit_reason='STOP_LOSS'``

        Bracket OCO semantics mean the other child is cancelled by TWS
        when one fills; we treat the first filled child as the exit.
        No-op when no provider is wired, when the drain is empty, or
        when no stored trade matches a filled ID.  Never raises —
        reconciliation is best-effort.
        """
        if self._filled_order_ids_provider is None:
            return
        try:
            filled = set(self._filled_order_ids_provider())
        except Exception:  # pragma: no cover - defensive
            logger.exception("filled_order_ids_provider raised")
            return
        if not filled:
            return

        try:
            open_trades = [
                trade for trade in self._store.list_all()
                if trade.status in {OPEN, EXIT_PENDING}
            ]
        except Exception:  # pragma: no cover - defensive
            logger.exception("trade store list_open failed during bracket reconcile")
            return

        for trade in open_trades:
            target_id = getattr(trade, "target_order_id", None)
            stop_id = getattr(trade, "stop_order_id", None)
            matched_id: Optional[int] = None
            exit_reason: Optional[str] = None
            if target_id is not None and target_id in filled:
                matched_id = int(target_id)
                exit_reason = "TAKE_PROFIT"
            elif stop_id is not None and stop_id in filled:
                matched_id = int(stop_id)
                exit_reason = "STOP_LOSS"
            if matched_id is None or exit_reason is None:
                continue
            try:
                self._store.update_trade(
                    trade.autonomous_trade_id,
                    status=CLOSED,
                    exit_order_id=matched_id,
                    exit_time=datetime.now(timezone.utc),
                    exit_reason=exit_reason,
                    notes=list(trade.notes or []) + [
                        f"reconciled: bracket {exit_reason} filled "
                        f"(order #{matched_id})"
                    ],
                )
                logger.info(
                    "AutonomousLiveRunner: bracket %s filled for trade %s "
                    "(%s, order #%s) → CLOSED",
                    exit_reason,
                    trade.autonomous_trade_id,
                    trade.symbol,
                    matched_id,
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "failed to mark trade %s as CLOSED on bracket fill",
                    trade.autonomous_trade_id,
                )

    @staticmethod
    def _first_gate_status(gates: LiveReadinessGates) -> str:
        if not gates.connected:
            return NOT_CONNECTED
        if not gates.live_mode:
            return NOT_LIVE_MODE
        if not gates.live_enabled:
            return LIVE_DISABLED
        if gates.continuous_mode_required and not gates.live_continuous_enabled:
            return LIVE_CONTINUOUS_DISABLED
        if not gates.account_id_verified:
            return ACCOUNT_ID_MISMATCH
        if not gates.signal_provider_ready:
            return SIGNAL_PROVIDER_NOT_READY
        if gates.emergency_stop_active:
            return EMERGENCY_STOP_ACTIVE
        if gates.open_live_trades >= gates.max_open_live_trades:
            return MAX_OPEN_TRADES
        if gates.live_trades_today >= gates.max_live_trades_per_day:
            return DAILY_LIVE_TRADE_LIMIT_REACHED
        if gates.deployable_cash < gates.min_deployable_cash:
            return DEPLOYABLE_CASH_BELOW_MINIMUM
        return ENGINE_REJECTED

    def _record_trade(
        self,
        decision: AutonomousDecision,
        plan: Dict[str, Any],
        quantity: int,
        order_id: Optional[int],
        *,
        target_order_id: Optional[int] = None,
        stop_order_id: Optional[int] = None,
        extra_notes: Optional[List[str]] = None,
    ) -> Optional[AutonomousTrade]:
        if self._config.buy_shares_only and plan.get("trade_type") != TradeType.BUY_SHARES.value:
            logger.info(
                "AutonomousLiveRunner: skipping trade store record for "
                "non-BUY_SHARES plan %s",
                plan.get("trade_type"),
            )
            return None
        try:
            notes = [
                "recorded by AutonomousLiveRunner",
                f"dry_run={self._config.live_dry_run}",
            ]
            if target_order_id is not None and stop_order_id is not None:
                notes.append(
                    f"bracket: target_order_id={target_order_id} "
                    f"stop_order_id={stop_order_id}"
                )
            if extra_notes:
                notes.extend(extra_notes)
            trade = AutonomousTrade(
                autonomous_trade_id=AutonomousTrade.new_id(),
                symbol=str(plan.get("symbol")),
                trade_type=str(plan.get("trade_type") or TradeType.BUY_SHARES.value),
                status=OPEN,
                entry_order_id=int(order_id) if order_id is not None else 0,
                entry_time=datetime.now(timezone.utc),
                entry_limit_price=float(plan.get("limit_price") or 0.0),
                quantity=quantity,
                target_price=_as_float(plan.get("target_price")),
                stop_price=_as_float(plan.get("stop_price")),
                max_holding_days=int(self._config.max_holding_days),
                target_order_id=int(target_order_id) if target_order_id is not None else None,
                stop_order_id=int(stop_order_id) if stop_order_id is not None else None,
                notes=notes,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to build AutonomousTrade from live decision")
            return None
        self._store.record_trade(trade)
        return trade


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
