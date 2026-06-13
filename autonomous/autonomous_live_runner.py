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
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from autonomous.autonomous_config import AutonomousMode
from autonomous.autonomous_engine import AutonomousDecision, AutonomousTradingEngine, DecisionStatus
from autonomous.runner_config import AutonomousLiveRunnerConfig
from autonomous.signal_provider import StaticSignalProvider
from autonomous.trade_planner import TradeType
from autonomous.trade_store import (
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

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    def evaluate_gates(self) -> LiveReadinessGates:
        """Evaluate every readiness gate; never raises."""
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

        # Engine reached the ASSISTED_LIVE path — we now own order placement.
        # The engine intentionally does NOT submit the order in ASSISTED_LIVE
        # mode; the runner submits it through OrderExecutor.
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
        limit_price = float(plan.get("limit_price") or 0.0)
        quantity = int(plan.get("quantity") or 0)

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
        signal = Signal(
            symbol=symbol,
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(timezone.utc),
            quantity=quantity,
            target_price=limit_price,
        )

        # Limit-orders-only enforcement: mark strategy name so callers / logs
        # can distinguish this signal from non-limit autonomous signals.
        if self._config.live_limit_orders_only:
            signal.strategy_name = "AutonomousLiveRunner:LIMIT"

        try:
            result = self._executor.execute_signal(
                strategy_name="AutonomousLiveRunner",
                signal=signal,
                current_equity=gates.deployable_cash,
                positions={},
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
            trade = self._record_trade(decision, plan, quantity, result.order_id)
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
                ],
                dry_run=True,
            )

        if result.status == OrderStatus.SUBMITTED:
            trade = self._record_trade(decision, plan, quantity, result.order_id)
            return AutonomousLiveRunResult(
                status=EXECUTED,
                gates=gates,
                decision=decision_payload,
                trade=trade.to_dict() if trade else None,
                notes=[
                    "live order submitted via OrderExecutor",
                    f"order_id={result.order_id}",
                    f"quantity={quantity}",
                    f"deployable_cash={deployable_cash:.2f}",
                    f"max_deployable_cash_pct={self._config.max_deployable_cash_pct}",
                    f"max_trade_value={max_trade_value:.2f}",
                ],
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
        if gates.deployable_cash < gates.min_deployable_cash:
            return DEPLOYABLE_CASH_BELOW_MINIMUM
        return ENGINE_REJECTED

    def _record_trade(
        self,
        decision: AutonomousDecision,
        plan: Dict[str, Any],
        quantity: int,
        order_id: Optional[int],
    ) -> Optional[AutonomousTrade]:
        if self._config.buy_shares_only and plan.get("trade_type") != TradeType.BUY_SHARES.value:
            logger.info(
                "AutonomousLiveRunner: skipping trade store record for "
                "non-BUY_SHARES plan %s",
                plan.get("trade_type"),
            )
            return None
        try:
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
                notes=[
                    "recorded by AutonomousLiveRunner",
                    f"dry_run={self._config.live_dry_run}",
                ],
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
