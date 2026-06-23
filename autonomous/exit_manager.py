"""Paper-only exit manager for autonomous BUY_SHARES trades.

Evaluates open :class:`autonomous.trade_store.AutonomousTrade` records
and decides whether each one should be closed by a paper SELL limit
order.  Exit rules in MVP scope:

* ``TAKE_PROFIT`` — last price >= ``target_price``
* ``STOP_LOSS``  — last price <= ``stop_price``
* ``TIME_EXIT``  — open for longer than ``max_holding_days``
* ``RISK_EXIT``  — EMERGENCY_STOP file or RiskManager flag is active

Safety invariants:

* Exit orders are placed **only** through the paper adapter; live
  execution is impossible from this module.
* Only ``BUY_SHARES`` trades are acted on in this MVP.  Any other
  trade type returns ``NO_EXIT`` with a reason indicating the
  skip — we never submit unsupported exit orders.
* Every submitted SELL LIMIT order is anchored to the current live
  price.  When no live price is available — including for
  ``RISK_EXIT`` / emergency-stop cases — the trade is left as
  ``OPEN`` and a ``NO_PRICE_AVAILABLE`` decision is returned (with a
  ``would_exit:<REASON>`` note for visibility).  We never guess an
  exit or fall back to a stale ``entry_limit_price``.
* No fake fills.  After submitting the SELL order the trade is set to
  ``EXIT_PENDING`` until real fill information is available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from autonomous.audit import AuditLogger
from autonomous.trade_planner import TradeType
from autonomous.trade_store import (
    AutonomousTrade,
    ENTRY_PENDING,
    EXIT_PENDING,
    TradeStore,
)

logger = logging.getLogger(__name__)


# Exit reasons --------------------------------------------------------------

TAKE_PROFIT = "TAKE_PROFIT"
STOP_LOSS = "STOP_LOSS"
TIME_EXIT = "TIME_EXIT"
RISK_EXIT = "RISK_EXIT"
NO_PRICE_AVAILABLE = "NO_PRICE_AVAILABLE"
NO_EXIT = "NO_EXIT"


@dataclass
class ExitDecision:
    """Result of evaluating one open trade for exit."""

    autonomous_trade_id: str
    symbol: str
    decision: str           # one of the *_EXIT / NO_EXIT / NO_PRICE_AVAILABLE
    reason: str             # human-readable
    price: Optional[float] = None
    exit_order_id: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "autonomous_trade_id": self.autonomous_trade_id,
            "symbol": self.symbol,
            "decision": self.decision,
            "reason": self.reason,
            "price": self.price,
            "exit_order_id": self.exit_order_id,
            "notes": list(self.notes),
        }


PositionsProvider = Callable[[], Dict[str, Dict[str, Any]]]


class AutonomousExitManager:
    """Evaluate open autonomous trades and place SELL orders.

    Parameters
    ----------
    trade_store:
        Persistence layer that holds open trades.
    paper_adapter:
        Object exposing ``sell(symbol, quantity, order_type, limit_price)``
        compatible with :class:`execution.autonomous_paper_adapter.AutonomousPaperAdapter`.
        May be ``None`` when ``order_executor`` is supplied; in all other
        cases (both ``None``) no exit orders are placed and each evaluated
        trade returns a ``NO_EXIT`` decision with a ``no adapter configured``
        reason.
    positions_provider:
        Callable returning ``ServiceManager.get_positions()``.  Used to
        read the live ``current_price`` for the trade's symbol.
    risk_manager:
        Optional; ``emergency_stop_active`` triggers ``RISK_EXIT``.
    emergency_stop_file:
        Path to the file-based emergency stop flag.  Existence triggers
        ``RISK_EXIT``.
    audit_logger:
        Optional; receives one JSONL entry per exit decision (executed
        or not).
    order_executor:
        Optional :class:`execution.order_executor.OrderExecutor`.  When
        supplied (and ``paper_adapter`` is ``None``), exit SELL orders are
        routed through this executor using a SELL signal with
        ``target_price`` set to the current live price.  This is the
        correct path for live account exits.
    account_equity_provider:
        Optional callable returning the current account equity (net
        liquidation value) from the broker.  Used for live exits so
        ``OrderExecutor`` sanity checks use real equity rather than a
        synthetic estimate.  When ``None`` or when the provider returns
        ``None``/``0``, a conservative fallback is used and an audit note
        is recorded.
    broker_positions_provider:
        Optional callable returning all broker positions as
        ``Dict[str, RiskPosition]`` (keyed by symbol).  Used for live
        exits so ``OrderExecutor._reconcile_portfolio()`` sees all
        account holdings and does not reject the exit due to
        ``PORTFOLIO_MISMATCH`` from unrelated positions.  When ``None``,
        only the autonomous trade's position is passed (which may fail
        reconciliation if the account holds other symbols).
    """

    def __init__(
        self,
        trade_store: TradeStore,
        paper_adapter: Any,
        positions_provider: PositionsProvider,
        risk_manager: Any = None,
        emergency_stop_file: str = "EMERGENCY_STOP",
        audit_logger: Optional[AuditLogger] = None,
        order_executor: Any = None,
        account_equity_provider: Optional[Callable[[], Optional[float]]] = None,
        broker_positions_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self._store = trade_store
        self._paper_adapter = paper_adapter
        self._positions_provider = positions_provider
        self._risk_manager = risk_manager
        self._emergency_stop_file = Path(emergency_stop_file)
        self._audit = audit_logger
        self._order_executor = order_executor
        self._account_equity_provider = account_equity_provider
        self._broker_positions_provider = broker_positions_provider

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def evaluate_open_trades(
        self,
        now: Optional[datetime] = None,
        force_risk_exit_reason: Optional[str] = None,
    ) -> List[ExitDecision]:
        """Evaluate every open trade and return one ExitDecision each."""
        moment = now or datetime.now(timezone.utc)
        risk_active = self._risk_active()
        forced_reason = str(force_risk_exit_reason or "").strip()
        if forced_reason:
            risk_active = True
        positions = self._positions_provider() or {}

        decisions: List[ExitDecision] = []
        for trade in self._store.list_open():
            decision = self._evaluate_one(
                trade,
                positions,
                moment,
                risk_active,
                forced_risk_reason=forced_reason,
            )
            decisions.append(decision)
            self._audit_decision(decision)
        return decisions

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _risk_active(self) -> bool:
        try:
            if self._emergency_stop_file.exists():
                return True
        except OSError:  # pragma: no cover - defensive
            pass
        if self._risk_manager is not None and getattr(
            self._risk_manager, "emergency_stop_active", False
        ):
            return True
        return False

    @staticmethod
    def _last_price(
        symbol: str,
        positions: Dict[str, Dict[str, Any]],
    ) -> Optional[float]:
        pos = positions.get(symbol)
        if not pos:
            return None
        for key in ("current_price", "market_price", "last_price"):
            value = pos.get(key)
            if value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    def _evaluate_one(
        self,
        trade: AutonomousTrade,
        positions: Dict[str, Dict[str, Any]],
        now: datetime,
        risk_active: bool,
        forced_risk_reason: str = "",
    ) -> ExitDecision:
        if str(getattr(trade, "status", "")) == ENTRY_PENDING:
            return ExitDecision(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=trade.symbol,
                decision=NO_EXIT,
                reason="entry order submitted but not filled yet; waiting for fill reconciliation",
            )

        # 0. MVP only acts on BUY_SHARES trades.  Anything else is left
        #    untouched so non-equity lifecycle handling can be added
        #    later without the exit manager submitting unsupported
        #    orders.
        trade_type = str(getattr(trade, "trade_type", "") or "")
        if trade_type.upper() != TradeType.BUY_SHARES.value:
            return ExitDecision(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=trade.symbol,
                decision=NO_EXIT,
                reason=f"trade_type {trade_type!r} is not BUY_SHARES; skipped",
            )

        # 1. Risk / emergency stop overrides everything else — but we
        #    still require a current price before submitting any order.
        #    Submitting a SELL LIMIT at a stale entry/target/stop would
        #    be guessing the exit, which this MVP explicitly refuses to
        #    do.
        if risk_active:
            risk_reason = (
                forced_risk_reason
                or "emergency stop or risk_manager halt active"
            )
            price = self._last_price(trade.symbol, positions)
            if price is None:
                return ExitDecision(
                    autonomous_trade_id=trade.autonomous_trade_id,
                    symbol=trade.symbol,
                    decision=NO_PRICE_AVAILABLE,
                    reason=(
                        f"{risk_reason} but "
                        "no current_price for symbol; refusing to submit "
                        "blind exit"
                    ),
                    notes=[f"would_exit:{RISK_EXIT}"],
                )
            return self._submit_exit(
                trade,
                RISK_EXIT,
                risk_reason,
                price=price,
            )

        # 2. Time-based exit — still requires a current price so the
        #    submitted LIMIT order is anchored to a real quote rather
        #    than a stale entry price.
        entry_time = trade.entry_time
        if isinstance(entry_time, str):
            try:
                entry_time = datetime.fromisoformat(entry_time)
            except ValueError:
                entry_time = None
        if entry_time is not None:
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            age = now - entry_time
            if age >= timedelta(days=max(1, int(trade.max_holding_days))):
                price = self._last_price(trade.symbol, positions)
                if price is None:
                    return ExitDecision(
                        autonomous_trade_id=trade.autonomous_trade_id,
                        symbol=trade.symbol,
                        decision=NO_PRICE_AVAILABLE,
                        reason=(
                            f"open for {age.days}d >= "
                            f"max_holding_days={trade.max_holding_days} but "
                            "no current_price for symbol; refusing to submit "
                            "blind exit"
                        ),
                        notes=[f"would_exit:{TIME_EXIT}"],
                    )
                return self._submit_exit(
                    trade,
                    TIME_EXIT,
                    f"open for {age.days}d >= max_holding_days={trade.max_holding_days}",
                    price=price,
                )

        # 3. Price-driven exits.
        price = self._last_price(trade.symbol, positions)
        if price is None:
            return ExitDecision(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=trade.symbol,
                decision=NO_PRICE_AVAILABLE,
                reason="no current_price for symbol in positions snapshot",
            )

        if trade.target_price is not None and price >= float(trade.target_price):
            return self._submit_exit(
                trade,
                TAKE_PROFIT,
                f"price {price:.2f} >= target {float(trade.target_price):.2f}",
                price=price,
            )
        if trade.stop_price is not None and price <= float(trade.stop_price):
            return self._submit_exit(
                trade,
                STOP_LOSS,
                f"price {price:.2f} <= stop {float(trade.stop_price):.2f}",
                price=price,
            )

        return ExitDecision(
            autonomous_trade_id=trade.autonomous_trade_id,
            symbol=trade.symbol,
            decision=NO_EXIT,
            reason=(
                f"price {price:.2f} within target/stop band"
            ),
            price=price,
        )

    def _submit_exit(
        self,
        trade: AutonomousTrade,
        reason_code: str,
        reason_text: str,
        price: Optional[float],
    ) -> ExitDecision:
        """Submit a SELL limit order and mark the trade EXIT_PENDING.

        ``price`` is the current live price for the symbol and is
        **required**.  We deliberately do not fall back to
        ``entry_limit_price``, ``target_price`` or ``stop_price`` here:
        callers are responsible for returning ``NO_PRICE_AVAILABLE``
        when no live quote is known so that we never submit a SELL
        LIMIT at a stale anchor.

        When ``paper_adapter`` is configured, exits are routed through it
        (paper account path).  When ``order_executor`` is configured
        instead, exits are routed through
        :meth:`execution.order_executor.OrderExecutor.execute_signal` using
        a SELL signal with ``target_price`` set to the current live price
        (live account path).  If neither is configured, no order is
        submitted — the decision is still returned so the dashboard /
        audit log can surface the reason.
        """
        if price is None or price <= 0:
            # Defensive: callers should already have returned
            # NO_PRICE_AVAILABLE; refuse to guess if they did not.
            return ExitDecision(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=trade.symbol,
                decision=NO_PRICE_AVAILABLE,
                reason="no current price; refusing to submit blind exit",
                price=price,
                notes=[f"would_exit:{reason_code}", reason_text],
            )
        limit_price = float(price)

        # --- Paper adapter path -------------------------------------------
        if self._paper_adapter is not None:
            return self._submit_exit_via_paper_adapter(
                trade, reason_code, reason_text, limit_price
            )

        # --- OrderExecutor path (live exits) ---------------------------------
        if self._order_executor is not None:
            return self._submit_exit_via_order_executor(
                trade, reason_code, reason_text, limit_price
            )

        # --- No adapter configured -------------------------------------------
        return ExitDecision(
            autonomous_trade_id=trade.autonomous_trade_id,
            symbol=trade.symbol,
            decision=NO_EXIT,
            reason="no paper_adapter or order_executor configured; cannot exit",
            price=limit_price,
            notes=[f"would_exit:{reason_code}", reason_text],
        )

    def _submit_exit_via_paper_adapter(
        self,
        trade: AutonomousTrade,
        reason_code: str,
        reason_text: str,
        limit_price: float,
    ) -> ExitDecision:
        """Place a paper SELL limit order via paper_adapter."""
        try:
            order_id = self._paper_adapter.sell(
                symbol=trade.symbol,
                quantity=int(trade.quantity),
                order_type="LIMIT",
                limit_price=float(limit_price),
            )
        except Exception as exc:
            logger.exception("paper_adapter.sell raised for %s", trade.symbol)
            return ExitDecision(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=trade.symbol,
                decision=NO_EXIT,
                reason=f"paper adapter raised: {exc}",
                price=limit_price,
                notes=[f"would_exit:{reason_code}", reason_text],
            )

        return self._mark_exit_pending(trade, reason_code, reason_text, limit_price, order_id)

    def _submit_exit_via_order_executor(
        self,
        trade: AutonomousTrade,
        reason_code: str,
        reason_text: str,
        limit_price: float,
    ) -> ExitDecision:
        """Place a live SELL limit order via order_executor.

        Uses broker-grounded account data for equity and positions:

        * ``current_equity`` is sourced from ``account_equity_provider``
          (the real broker net liquidation value).  If unavailable, a
          conservative fallback is used and noted in the audit trail.
        * ``positions`` is sourced from ``broker_positions_provider``
          which returns ALL broker positions so that
          ``OrderExecutor._reconcile_portfolio()`` does not reject the
          exit due to unrelated holdings appearing as ``only_in_tws``.

        Before calling the executor, we pre-validate:
        * The broker must hold the exit symbol.
        * The broker quantity for the symbol must be >= the exit quantity.
        """
        try:
            from strategies.signal import Signal, SignalType, SignalStrength
            from risk.risk_manager import Position as RiskPosition

            # --- Pre-validate: broker must hold enough shares to exit ---
            equity_source, exit_equity = self._resolve_exit_equity(trade, limit_price)
            positions_source, exit_positions = self._resolve_exit_positions(trade, limit_price)

            # Verify the exit symbol exists in broker positions with
            # sufficient quantity BEFORE calling the executor.
            pre_check_ok, pre_check_reason = self._pre_validate_exit_position(
                trade, exit_positions
            )
            if not pre_check_ok:
                return ExitDecision(
                    autonomous_trade_id=trade.autonomous_trade_id,
                    symbol=trade.symbol,
                    decision=NO_EXIT,
                    reason=pre_check_reason,
                    price=limit_price,
                    notes=[
                        f"would_exit:{reason_code}",
                        reason_text,
                        f"equity_source:{equity_source}",
                        f"positions_source:{positions_source}",
                    ],
                )

            sell_signal = Signal(
                symbol=trade.symbol,
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG,
                timestamp=datetime.now(timezone.utc),
                quantity=int(trade.quantity),
                target_price=limit_price,
            )

            result = self._order_executor.execute_signal(
                strategy_name="AutonomousExitManager:LIVE_EXIT",
                signal=sell_signal,
                current_equity=exit_equity,
                positions=exit_positions,
            )
        except Exception as exc:
            logger.exception(
                "order_executor.execute_signal raised for live exit %s",
                trade.symbol,
            )
            return ExitDecision(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=trade.symbol,
                decision=NO_EXIT,
                reason=f"order_executor raised: {exc}",
                price=limit_price,
                notes=[f"would_exit:{reason_code}", reason_text],
            )

        from execution.order_executor import OrderStatus
        if result.status not in (OrderStatus.SUBMITTED, OrderStatus.DRY_RUN):
            return ExitDecision(
                autonomous_trade_id=trade.autonomous_trade_id,
                symbol=trade.symbol,
                decision=NO_EXIT,
                reason=f"order_executor rejected exit: {result.reason}",
                price=limit_price,
                notes=[f"would_exit:{reason_code}", reason_text],
            )

        order_id = result.order_id
        decision = self._mark_exit_pending(trade, reason_code, reason_text, limit_price, order_id)
        # Append audit context about the data sources used for this exit.
        decision.notes.append(f"equity_source:{equity_source}")
        decision.notes.append(f"positions_source:{positions_source}")
        return decision

    # ------------------------------------------------------------------
    # Broker-grounded helpers for live exits
    # ------------------------------------------------------------------

    def _resolve_exit_equity(
        self,
        trade: AutonomousTrade,
        limit_price: float,
    ) -> Tuple[str, float]:
        """Return (source_label, equity_value) for a live exit.

        Prefers the broker-provided ``account_equity_provider``.  Falls
        back to a conservative estimate when unavailable — but the
        source is always recorded so auditors can distinguish.
        """
        if self._account_equity_provider is not None:
            try:
                broker_equity = self._account_equity_provider()
                if broker_equity is not None and broker_equity > 0:
                    return ("broker_account_summary", float(broker_equity))
            except Exception:
                logger.warning(
                    "account_equity_provider raised; using fallback equity"
                )
        # Conservative fallback: 10× position value or $100k minimum.
        position_value = int(trade.quantity) * limit_price
        fallback = max(position_value * 10.0, 100_000.0)
        return ("fallback_estimate", fallback)

    def _resolve_exit_positions(
        self,
        trade: AutonomousTrade,
        limit_price: float,
    ) -> Tuple[str, Dict[str, Any]]:
        """Return (source_label, positions_dict) for a live exit.

        Prefers the broker-provided ``broker_positions_provider`` which
        returns all account holdings.  Falls back to a single-symbol
        dict containing only the trade's position.
        """
        from risk.risk_manager import Position as RiskPosition

        if self._broker_positions_provider is not None:
            try:
                broker_positions = self._broker_positions_provider()
                if broker_positions is not None:
                    return ("broker_positions", broker_positions)
            except Exception:
                logger.warning(
                    "broker_positions_provider raised; using single-symbol fallback"
                )
        # Fallback: only the autonomous trade position (may fail
        # reconciliation if account has other holdings).
        fallback_positions: Dict[str, Any] = {
            trade.symbol: RiskPosition(
                symbol=trade.symbol,
                quantity=int(trade.quantity),
                entry_price=float(trade.entry_limit_price),
                current_price=limit_price,
                side="LONG",
            ),
        }
        return ("single_symbol_fallback", fallback_positions)

    @staticmethod
    def _pre_validate_exit_position(
        trade: AutonomousTrade,
        positions: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Verify that positions contain the exit symbol with enough shares.

        Returns (True, "") on success or (False, reason) on failure.
        """
        pos = positions.get(trade.symbol)
        if pos is None:
            return (
                False,
                f"broker does not hold {trade.symbol}; cannot exit",
            )
        # pos can be a RiskPosition (has .quantity) or a dataclass Position
        broker_qty = getattr(pos, "quantity", 0)
        exit_qty = int(trade.quantity)
        if broker_qty < exit_qty:
            return (
                False,
                (
                    f"broker holds {broker_qty} shares of {trade.symbol} "
                    f"but exit requires {exit_qty}; rejecting"
                ),
            )
        return (True, "")

    def _mark_exit_pending(
        self,
        trade: AutonomousTrade,
        reason_code: str,
        reason_text: str,
        limit_price: float,
        order_id: Optional[int],
    ) -> ExitDecision:
        """Mark trade EXIT_PENDING after a successful order submission."""
        # Do NOT fake the fill.  Real fill information will be reconciled
        # separately when available.
        try:
            self._store.update_trade(
                trade.autonomous_trade_id,
                status=EXIT_PENDING,
                exit_order_id=int(order_id) if order_id is not None else None,
                exit_reason=reason_code,
                exit_time=datetime.now(timezone.utc),
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "failed to persist EXIT_PENDING for %s",
                trade.autonomous_trade_id,
            )

        return ExitDecision(
            autonomous_trade_id=trade.autonomous_trade_id,
            symbol=trade.symbol,
            decision=reason_code,
            reason=reason_text,
            price=limit_price,
            exit_order_id=int(order_id) if order_id is not None else None,
        )

    def _audit_decision(self, decision: ExitDecision) -> None:
        if self._audit is None:
            return
        try:
            self._audit.log_decision({
                "engine": "AutonomousExitManager",
                "decision": decision.to_dict(),
            })
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to write exit decision audit entry")
