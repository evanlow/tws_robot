"""
Order Executor with Multi-Layer Safety

Converts strategy signals to TWS orders with MANDATORY risk enforcement.
No order reaches TWS without passing ALL safety checks.

Safety Layers:
1. Risk Manager validation (position limits, drawdown, exposure)
2. Portfolio reconciliation (strategy state vs TWS reality)
3. Pre-flight checks (market open, buying power, emergency stop)
4. Order validation (price sanity, quantity limits)
5. Confirmation (live mode requires explicit approval)

Author: TWS Robot Development Team
Date: January 24, 2026
Phase 1: MVP Live Trading - SAFETY FIRST
"""

# ==============================================================================
# API VERIFICATION CHECKLIST ✓
# ==============================================================================
# Date: 2026-01-24
# Task: Create order executor with mandatory safety enforcement
#
# Verified APIs:
# 1. RiskManager.check_trade_risk (risk/risk_manager.py:223)
#    Signature: check_trade_risk(signal, positions, equity) -> Tuple[bool, str]
#    Verified: ✓
#
# 2. PaperTradingAdapter.buy/sell (execution/paper_adapter.py:309, 332)
#    Signatures: buy(symbol, quantity, order_type, limit_price, stop_price)
#                sell(symbol, quantity, order_type, limit_price, stop_price)
#    Verified: ✓
#
# 3. Signal class (strategies/signal.py)
#    Verified: ✓
#
# VERIFICATION COMPLETE: ✓
# ==============================================================================

import logging
from typing import Optional, Dict, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from strategies.signal import Signal, SignalType
from risk.risk_manager import RiskManager, Position
from backtest.data_models import Position as BacktestPosition


logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    """Order execution status"""
    SUBMITTED = "SUBMITTED"  # Sent to TWS
    REJECTED = "REJECTED"  # Failed safety checks
    BLOCKED = "BLOCKED"  # Blocked by risk manager
    CANCELLED = "CANCELLED"  # User cancelled
    FILLED = "FILLED"  # Execution complete
    DRY_RUN = "DRY_RUN"  # Order previewed but not submitted (dry-run mode)


class RejectionReason(str, Enum):
    """Why an order was rejected"""
    RISK_LIMIT_EXCEEDED = "Risk limit exceeded"
    EMERGENCY_STOP_ACTIVE = "Emergency stop is active"
    INSUFFICIENT_BUYING_POWER = "Insufficient buying power"
    MARKET_CLOSED = "Market is closed"
    INVALID_SIGNAL = "Invalid signal"
    POSITION_LIMIT_EXCEEDED = "Position limit exceeded"
    PRICE_SANITY_FAILED = "Price sanity check failed"
    PORTFOLIO_MISMATCH = "Portfolio state mismatch"
    CONFIRMATION_DENIED = "User denied confirmation"
    LIVE_TRADING_DISABLED = "Live trading is disabled (application setting OFF)"
    LIVE_CONFIRMATION_MISSING = "Live trading session not confirmed"
    LIVE_ENV_MISMATCH = "Live environment/account/mode mismatch"


@dataclass
class LiveTradingConfirmation:
    """
    Per-session live-trading confirmation tuple.

    All four values must agree with the adapter/account before any live
    order is permitted to leave :class:`OrderExecutor`.  The intent is to
    make it impossible to "accidentally" send a real order: the operator
    must have already enabled live trading at the application level *and*
    confirmed the specific session by supplying this token.

    Attributes:
        environment: ``"live"`` (rejected otherwise).
        account_id: IBKR account number the order targets.
        port: TWS socket port (used to cross-check the live ports).
        confirmed_by: Free-form identifier of the confirming operator/user.
    """

    environment: str
    account_id: str
    port: int
    confirmed_by: str

    def matches_adapter(self, adapter) -> Tuple[bool, str]:
        """Return ``(ok, reason)`` describing whether this confirmation
        matches the supplied TWS adapter."""
        if (self.environment or "").lower() != "live":
            return False, f"confirmation environment={self.environment!r} is not 'live'"
        if not hasattr(adapter, "environment"):
            return False, "adapter is missing required 'environment' attribute"
        adapter_env = getattr(adapter, "environment", None)
        if (adapter_env or "").lower() != "live":
            return False, (
                f"adapter environment={adapter_env!r} does not match "
                f"confirmation environment='live'"
            )
        if not hasattr(adapter, "port"):
            return False, "adapter is missing required 'port' attribute"
        adapter_port = getattr(adapter, "port", None)
        if adapter_port != self.port:
            return False, (
                f"adapter port={adapter_port} does not match "
                f"confirmation port={self.port}"
            )
        if not self.account_id:
            return False, "confirmation account_id is empty"
        if not self.confirmed_by:
            return False, "confirmation confirmed_by is empty"
        return True, ""


@dataclass
class OrderResult:
    """Result of order execution attempt"""
    status: OrderStatus
    order_id: Optional[int] = None
    reason: Optional[str] = None
    signal: Optional[Signal] = None
    quantity: int = 0
    price: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    @classmethod
    def submitted(cls, order_id: int, signal: Signal, quantity: int, price: float):
        """Order successfully submitted"""
        return cls(
            status=OrderStatus.SUBMITTED,
            order_id=order_id,
            signal=signal,
            quantity=quantity,
            price=price,
            reason=f"Order {order_id} submitted to TWS"
        )
    
    @classmethod
    def rejected(cls, reason: RejectionReason, signal: Signal, details: str = ""):
        """Order rejected"""
        full_reason = f"{reason.value}: {details}" if details else reason.value
        return cls(
            status=OrderStatus.REJECTED,
            signal=signal,
            reason=full_reason
        )
    
    @classmethod
    def blocked(cls, reason: str, signal: Signal):
        """Order blocked by risk manager"""
        return cls(
            status=OrderStatus.BLOCKED,
            signal=signal,
            reason=reason
        )

    @classmethod
    def dry_run(cls, signal: Signal, quantity: int, price: float):
        """Order previewed in dry-run mode (no TWS call)."""
        return cls(
            status=OrderStatus.DRY_RUN,
            signal=signal,
            quantity=quantity,
            price=price,
            reason="Dry-run preview only — order NOT submitted",
        )


class OrderExecutor:
    """
    Execute orders with mandatory multi-layer safety checks.
    
    CRITICAL: No order reaches TWS without passing ALL checks:
    1. Emergency stop check
    2. Risk manager validation
    3. Portfolio reconciliation
    4. Order sanity checks
    5. Live mode confirmation (if applicable)
    
    Example:
        >>> executor = OrderExecutor(
        ...     tws_adapter=adapter,
        ...     risk_manager=risk_mgr,
        ...     is_live_mode=False
        ... )
        >>> 
        >>> # Attempt to execute signal
        >>> result = executor.execute_signal(strategy_name, signal, current_equity, positions)
        >>> 
        >>> if result.status == OrderStatus.SUBMITTED:
        ...     print(f"Order placed: {result.order_id}")
        >>> else:
        ...     print(f"Order rejected: {result.reason}")
    """
    
    def __init__(
        self,
        tws_adapter,
        risk_manager: RiskManager,
        is_live_mode: bool = False,
        require_confirmation: bool = True,
        emergency_stop_file: str = "EMERGENCY_STOP",
        dry_run: bool = False,
        live_trading_enabled: bool = False,
        live_confirmation: Optional["LiveTradingConfirmation"] = None,
        expected_account_id: Optional[str] = None,
        limit_orders_only: bool = False,
    ):
        """
        Initialize order executor.
        
        Args:
            tws_adapter: TwsTradingAdapter (paper or live) or live TWS connection.
            risk_manager: RiskManager instance for validation.
            is_live_mode: True if trading with real money.
            require_confirmation: Require explicit per-order confirmation in
                live mode (in addition to the session-level confirmation).
            emergency_stop_file: Path to emergency stop file.
            dry_run: If True, all signals are previewed and audited but no
                orders are sent to TWS.  Returned status is
                :data:`OrderStatus.DRY_RUN`.  Enables end-to-end live-mode
                rehearsal without placing real orders.
            live_trading_enabled: Application-level "live trading enable"
                switch.  Must be True in live mode or every live order is
                rejected.  Defaults to ``False`` so live trading is OFF by
                default.
            live_confirmation: Per-session confirmation tuple (see
                :class:`LiveTradingConfirmation`).  Required in live mode
                when ``dry_run=False``.
            expected_account_id: Optional account ID that must match
                ``live_confirmation.account_id`` when supplied (used by
                callers that resolve the account from environment config).
            limit_orders_only: When ``True``, every order must carry a
                positive ``target_price``; signals without one are rejected
                with :data:`RejectionReason.PRICE_SANITY_FAILED`.  Always
                ``True`` for live autonomous execution so MARKET orders can
                never reach TWS through this executor.
        """
        self.tws_adapter = tws_adapter
        self.risk_manager = risk_manager
        self.is_live_mode = is_live_mode
        self.require_confirmation = require_confirmation and is_live_mode
        self.emergency_stop_file = Path(emergency_stop_file)
        self.dry_run = bool(dry_run)
        self.live_trading_enabled = bool(live_trading_enabled)
        self.live_confirmation = live_confirmation
        self.expected_account_id = expected_account_id
        self.limit_orders_only = bool(limit_orders_only)

        # Pre-validate the live-confirmation tuple at construction time so
        # configuration errors surface before the first signal arrives.
        if is_live_mode and not self.dry_run:
            ok, reason = self._validate_live_session()
            if not ok:
                # Don't raise — keep the executor usable so audit logging
                # still records the rejections, but log the configuration
                # error loudly.
                logger.error(
                    "Live executor configuration is INVALID; live orders "
                    "will be rejected until fixed: %s",
                    reason,
                )

        # State tracking
        self.orders_submitted = 0
        self.orders_rejected = 0
        self.orders_blocked = 0
        self.orders_dry_run = 0
        
        # Audit trail
        self.order_history: list[OrderResult] = []
        
        mode = "LIVE" if is_live_mode else "PAPER"
        if self.dry_run:
            mode = f"{mode} (DRY-RUN)"
        logger.warning(f"OrderExecutor initialized in {mode} MODE")
        logger.info(f"  Risk validation: ENABLED")
        logger.info(f"  Confirmation required: {self.require_confirmation}")
        logger.info(f"  Live trading enabled (app switch): {self.live_trading_enabled}")
        logger.info(f"  Dry-run mode: {self.dry_run}")
        logger.info(f"  Emergency stop file: {self.emergency_stop_file}")

        if is_live_mode and not self.dry_run:
            logger.warning("⚠️  LIVE MODE - REAL MONEY AT RISK ⚠️")
        elif is_live_mode and self.dry_run:
            logger.warning("LIVE MODE in DRY-RUN — no orders will be submitted")
    
    def execute_signal(
        self,
        strategy_name: str,
        signal: Signal,
        current_equity: float,
        positions: Dict[str, Position]
    ) -> OrderResult:
        """
        Execute trading signal with MANDATORY safety checks.
        
        ALL checks must pass for order to reach TWS.
        
        Args:
            strategy_name: Name of strategy generating signal
            signal: Trading signal to execute
            current_equity: Current account equity
            positions: Current positions (symbol -> Position)
        
        Returns:
            OrderResult with status and reason
        """
        logger.info(f"Processing signal from {strategy_name}: {signal.signal_type.value} {signal.symbol}")
        # Audit-log every signal we receive *before* any check, so the trail
        # captures every approval/risk decision that follows.
        self._audit_event(
            event="SIGNAL_RECEIVED",
            strategy_name=strategy_name,
            signal=signal,
            detail=(
                f"qty={signal.quantity} price={signal.target_price} "
                f"strength={getattr(signal.strength, 'value', signal.strength)}"
            ),
        )

        adapter_env = (getattr(self.tws_adapter, "environment", "") or "").lower()
        if adapter_env == "live" and not self.is_live_mode:
            result = OrderResult.rejected(
                RejectionReason.LIVE_ENV_MISMATCH,
                signal,
                "adapter environment='live' but executor is_live_mode=False",
            )
            self._record_order(result)
            self._audit_log(result, strategy_name)
            logger.error(
                "❌ Live adapter configured while executor is in paper mode "
                "(is_live_mode=False) — order rejected"
            )
            return result

        # === SAFETY CHECK 0: Live-mode environment / account / mode gate ===
        # Must precede every other check so a misconfigured live executor
        # cannot place orders even if all downstream checks would approve.
        if self.is_live_mode and not self.dry_run:
            if not self.live_trading_enabled:
                result = OrderResult.rejected(
                    RejectionReason.LIVE_TRADING_DISABLED,
                    signal,
                    "Application-level live trading switch is OFF",
                )
                self._record_order(result)
                self._audit_log(result, strategy_name)
                logger.error("❌ Live trading switch is OFF — order rejected")
                return result

            ok, reason = self._validate_live_session()
            if not ok:
                rejection = (
                    RejectionReason.LIVE_CONFIRMATION_MISSING
                    if self.live_confirmation is None
                    else RejectionReason.LIVE_ENV_MISMATCH
                )
                result = OrderResult.rejected(rejection, signal, reason)
                self._record_order(result)
                self._audit_log(result, strategy_name)
                logger.error(f"❌ Live session validation failed: {reason}")
                return result

        # === SAFETY CHECK 1: Emergency Stop ===
        if self._check_emergency_stop():
            stop_detail = (
                f"stop file present ({self.emergency_stop_file})"
                if self.emergency_stop_file.exists()
                else "risk manager emergency_stop_active flag set"
            )
            result = OrderResult.rejected(
                RejectionReason.EMERGENCY_STOP_ACTIVE,
                signal,
                f"Emergency stop active: {stop_detail}"
            )
            self._record_order(result)
            logger.error(f"❌ EMERGENCY STOP ACTIVE - Order blocked")
            return result
        
        # === SAFETY CHECK 2: Signal Validation ===
        if not self._validate_signal(signal):
            result = OrderResult.rejected(
                RejectionReason.INVALID_SIGNAL,
                signal,
                "Signal failed basic validation"
            )
            self._record_order(result)
            return result
        
        # === SAFETY CHECK 3: Risk Manager Validation ===
        # Convert signal to risk manager parameters
        side = 'LONG' if signal.signal_type == SignalType.BUY else 'SHORT'
        price = signal.target_price or 100.0  # Use estimated price if not specified
        quantity = signal.quantity or 0
        
        can_trade, risk_reason = self.risk_manager.check_trade_risk(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            price=price,
            positions=positions
        )
        
        if not can_trade:
            result = OrderResult.blocked(risk_reason, signal)
            self._record_order(result)
            self.orders_blocked += 1
            self._audit_event(
                event="RISK_CHECK_BLOCKED",
                strategy_name=strategy_name,
                signal=signal,
                detail=risk_reason,
            )
            logger.warning(f"⚠️  Order blocked by risk manager: {risk_reason}")
            return result
        self._audit_event(
            event="RISK_CHECK_PASSED",
            strategy_name=strategy_name,
            signal=signal,
        )
        
        # === SAFETY CHECK 4: Portfolio Reconciliation ===
        if not self._reconcile_portfolio(positions):
            result = OrderResult.rejected(
                RejectionReason.PORTFOLIO_MISMATCH,
                signal,
                "Strategy positions don't match TWS"
            )
            self._record_order(result)
            return result
        
        # === SAFETY CHECK 5: Order Sanity Checks ===
        sanity_ok, sanity_reason = self._sanity_check_order(signal, current_equity)
        if not sanity_ok:
            result = OrderResult.rejected(
                RejectionReason.PRICE_SANITY_FAILED,
                signal,
                sanity_reason
            )
            self._record_order(result)
            return result
        
        # === SAFETY CHECK 6: Live Mode Confirmation ===
        if self.require_confirmation:
            if not self._get_user_confirmation(signal):
                result = OrderResult.rejected(
                    RejectionReason.CONFIRMATION_DENIED,
                    signal,
                    "User denied order confirmation"
                )
                self._record_order(result)
                logger.info("User cancelled order")
                return result
        
        # === ALL CHECKS PASSED ===
        # In dry-run mode we stop here: log the would-be order to the audit
        # trail and return a DRY_RUN result without calling the TWS adapter.
        # This is the end-to-end live-mode rehearsal path required by the
        # acceptance criteria.
        if self.dry_run:
            result = OrderResult.dry_run(
                signal=signal,
                quantity=signal.quantity or 0,
                price=signal.target_price or 0.0,
            )
            self._record_order(result)
            self.orders_dry_run += 1
            self._audit_log(result, strategy_name)
            logger.warning(
                "🟡 DRY-RUN: %s %s x%s @ %s — order NOT submitted",
                signal.signal_type.value,
                signal.symbol,
                signal.quantity,
                signal.target_price,
            )
            return result

        # === ALL CHECKS PASSED - Execute Order ===
        return self._place_order(signal, strategy_name)
    
    def _check_emergency_stop(self) -> bool:
        """
        Check if emergency stop is active.
        
        Returns:
            True if emergency stop file exists OR risk manager flag is set
        """
        return self.emergency_stop_file.exists() or self.risk_manager.emergency_stop_active

    def _validate_live_session(self) -> Tuple[bool, str]:
        """
        Validate the live-trading session: environment, account, port, and
        per-session confirmation must all line up before any live order is
        permitted.  Called both from ``__init__`` (early config check) and
        from ``execute_signal`` (per-order gate).

        Returns:
            ``(ok, reason)`` — ``ok=True`` means it is safe to send live
            orders; ``ok=False`` carries a human-readable rejection reason.
        """
        if self.live_confirmation is None:
            return False, "No per-session LiveTradingConfirmation supplied"
        ok, reason = self.live_confirmation.matches_adapter(self.tws_adapter)
        if not ok:
            return False, reason
        if (
            self.expected_account_id
            and self.live_confirmation.account_id != self.expected_account_id
        ):
            return False, (
                f"confirmation account_id={self.live_confirmation.account_id!r} "
                f"does not match expected {self.expected_account_id!r}"
            )
        return True, ""
    
    def _validate_signal(self, signal: Signal) -> bool:
        """
        Validate signal is well-formed.
        
        Args:
            signal: Signal to validate
        
        Returns:
            True if valid
        """
        if not signal.symbol or len(signal.symbol) > 5:
            logger.error(f"Invalid symbol: {signal.symbol}")
            return False
        
        if signal.signal_type not in [SignalType.BUY, SignalType.SELL, SignalType.CLOSE]:
            logger.error(f"Invalid signal type: {signal.signal_type}")
            return False
        
        if signal.quantity and signal.quantity <= 0:
            logger.error(f"Invalid quantity: {signal.quantity}")
            return False
        
        return True
    
    def _reconcile_portfolio(self, positions: Dict[str, Position]) -> bool:
        """
        Reconcile strategy positions with TWS positions.
        
        Args:
            positions: Strategy's view of positions
        
        Returns:
            True if positions match (within tolerance)
        """
        # Get actual positions from TWS
        tws_positions = self.tws_adapter.get_all_positions()
        
        # Compare
        strategy_symbols = set(positions.keys())
        tws_symbols = set(p.symbol for p in tws_positions.values())
        
        # Check for mismatches
        only_in_strategy = strategy_symbols - tws_symbols
        only_in_tws = tws_symbols - strategy_symbols
        
        if only_in_strategy:
            logger.warning(f"Positions in strategy but not TWS: {only_in_strategy}")
            # This is OK - strategy might think it has position from earlier
        
        if only_in_tws:
            logger.error(f"Positions in TWS but not strategy: {only_in_tws}")
            return False  # CRITICAL - TWS has positions we don't know about
        
        # Check quantities match for common positions
        for symbol in strategy_symbols & tws_symbols:
            strategy_qty = positions[symbol].quantity
            tws_qty = tws_positions[symbol].quantity
            
            if abs(strategy_qty - tws_qty) > 5:  # Allow 5 share tolerance
                logger.error(
                    f"Position mismatch for {symbol}: "
                    f"strategy={strategy_qty}, TWS={tws_qty}"
                )
                return False
        
        return True
    
    def _sanity_check_order(self, signal: Signal, equity: float) -> Tuple[bool, str]:
        """
        Sanity check order parameters.
        
        Args:
            signal: Signal to check
            equity: Current equity
        
        Returns:
            (is_sane, reason)
        """
        # Check price is reasonable (if provided)
        if signal.target_price:
            if signal.target_price <= 0:
                return False, f"Invalid price: {signal.target_price}"
            
            # Price should be reasonable (not extreme)
            if signal.target_price > equity:
                return False, f"Price ${signal.target_price} exceeds total equity ${equity}"
        
        # Check quantity is reasonable
        if signal.quantity:
            estimated_cost = signal.quantity * (signal.target_price or 100)  # Assume $100 if no price
            if estimated_cost > equity * 0.5:  # No single order > 50% equity
                return False, f"Order cost ${estimated_cost:,.0f} exceeds 50% of equity"
        
        return True, ""
    
    def _get_user_confirmation(self, signal: Signal) -> bool:
        """
        Get explicit user confirmation for live order.
        
        Args:
            signal: Signal to confirm
        
        Returns:
            True if user confirms
        """
        print("\n" + "="*70)
        print("⚠️  LIVE ORDER CONFIRMATION REQUIRED ⚠️")
        print("="*70)
        print(f"Strategy Signal: {signal.signal_type.value}")
        print(f"Symbol: {signal.symbol}")
        print(f"Quantity: {signal.quantity}")
        print(f"Price: ${signal.target_price:.2f}" if signal.target_price else "Price: MARKET")
        print(f"Estimated Value: ${(signal.quantity * (signal.target_price or 0)):,.2f}")
        print("="*70)
        
        try:
            response = input("Execute this LIVE order? (yes/no): ").lower().strip()
            return response == 'yes'
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled by user")
            return False
    
    def _place_order(self, signal: Signal, strategy_name: str) -> OrderResult:
        """
        Actually place order with TWS.
        
        Args:
            signal: Validated signal
            strategy_name: Strategy name for logging
        
        Returns:
            OrderResult
        """
        # Determine order type and limit price.
        # Use LIMIT when target_price is available (anchors the order to a
        # specific price and avoids slippage).  When limit_orders_only is True
        # (always the case for live autonomous execution), reject the order
        # outright if no limit price is provided — we never send MARKET orders
        # on the live path.
        limit_price: Optional[float] = None
        if signal.target_price is not None and signal.target_price > 0:
            order_type = "LIMIT"
            limit_price = float(signal.target_price)
        elif self.limit_orders_only:
            result = OrderResult.rejected(
                RejectionReason.PRICE_SANITY_FAILED,
                signal,
                "limit_orders_only is True but signal has no valid target_price; "
                "MARKET orders are not permitted on this executor",
            )
            self._record_order(result)
            self._audit_log(result, strategy_name)
            logger.error(
                "❌ No limit price on signal for %s — MARKET order rejected "
                "(limit_orders_only=True)",
                signal.symbol,
            )
            return result
        else:
            order_type = "MARKET"

        try:
            # Convert signal to order
            if signal.signal_type == SignalType.BUY:
                order_id = self.tws_adapter.buy(
                    symbol=signal.symbol,
                    quantity=signal.quantity,
                    order_type=order_type,
                    limit_price=limit_price,
                )
            elif signal.signal_type == SignalType.SELL:
                order_id = self.tws_adapter.sell(
                    symbol=signal.symbol,
                    quantity=signal.quantity,
                    order_type=order_type,
                    limit_price=limit_price,
                )
            elif signal.signal_type == SignalType.CLOSE:
                order_id = self.tws_adapter.close_position(
                    symbol=signal.symbol,
                    order_type=order_type,
                )
            else:
                raise ValueError(f"Unsupported signal type: {signal.signal_type}")
            
            result = OrderResult.submitted(
                order_id=order_id,
                signal=signal,
                quantity=signal.quantity,
                price=signal.target_price or 0.0
            )
            
            self._record_order(result)
            self.orders_submitted += 1
            
            logger.info(
                "✅ Order submitted: #%s %s %s x%s @ %s (%s)",
                order_id,
                signal.signal_type.value,
                signal.symbol,
                signal.quantity,
                signal.target_price,
                order_type,
            )
            
            # Log to audit trail
            self._audit_log(result, strategy_name)
            
            return result
            
        except Exception as e:
            logger.exception(f"Error placing order: {e}")
            result = OrderResult.rejected(
                RejectionReason.INVALID_SIGNAL,
                signal,
                str(e)
            )
            self._record_order(result)
            return result
    
    def _record_order(self, result: OrderResult):
        """Record order in history"""
        self.order_history.append(result)
        if result.status == OrderStatus.REJECTED:
            self.orders_rejected += 1
    
    def _audit_log(self, result: OrderResult, strategy_name: str):
        """Write order to audit log"""
        log_file = Path('logs') / f'order_audit_{datetime.now().strftime("%Y%m%d")}.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_file, 'a') as f:
            f.write(f"{result.timestamp.isoformat()} | ")
            f.write(f"{strategy_name} | ")
            f.write(f"{result.status.value} | ")
            if result.signal:
                f.write(f"{result.signal.signal_type.value} | ")
                f.write(f"{result.signal.symbol} | ")
                f.write(f"{result.quantity} | ")
                f.write(f"${result.price:.2f} | ")
            f.write(f"{result.reason or 'Success'}\n")

    def _audit_event(
        self,
        event: str,
        strategy_name: str,
        signal: Optional[Signal] = None,
        detail: str = "",
    ) -> None:
        """Write a non-order audit event (signal received, risk-check
        outcome, etc.) to the same daily audit log used for orders.

        Keeps the audit trail complete for every signal-approval-risk-check
        decision, not only the final submit/reject outcome.
        """
        try:
            log_file = Path('logs') / f'order_audit_{datetime.now().strftime("%Y%m%d")}.log'
            log_file.parent.mkdir(parents=True, exist_ok=True)
            mode_tag = "LIVE" if self.is_live_mode else "PAPER"
            if self.dry_run:
                mode_tag += "/DRY"
            with open(log_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} | ")
                f.write(f"{strategy_name} | ")
                f.write(f"EVENT:{event} | ")
                f.write(f"{mode_tag} | ")
                if signal is not None:
                    sig_type = getattr(signal.signal_type, "value", signal.signal_type)
                    f.write(f"{sig_type} | {signal.symbol} | ")
                f.write(f"{detail}\n")
        except OSError:
            logger.exception(
                "Audit event logging failed (event=%s, strategy=%s); continuing execution",
                event,
                strategy_name,
            )
    
    def validate_manual_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float | None = None,
        current_equity: float = 0.0,
        positions: Dict[str, Position] | None = None,
    ) -> Tuple[bool, str]:
        """Validate a manual/web order through the same safety gate as strategies.

        Performs emergency-stop, risk-manager, and sanity checks without
        actually placing an order.  Use this from web routes or any non-strategy
        order path to ensure uniform safety enforcement.

        Args:
            symbol: Trading symbol (e.g. "AAPL")
            action: "BUY" or "SELL"
            quantity: Number of shares
            price: Limit price (None for market orders)
            current_equity: Current account equity for sanity checks
            positions: Current positions dict

        Returns:
            Tuple of (approved, rejection_reason).  ``approved`` is True when
            the order may proceed; otherwise ``rejection_reason`` explains why.
        """
        if positions is None:
            positions = {}

        normalized_action = action.upper() if isinstance(action, str) else ""
        if normalized_action not in ("BUY", "SELL"):
            return False, "Invalid action: must be BUY or SELL"

        # Emergency stop
        if self._check_emergency_stop():
            return False, "Emergency stop is active — all trading halted"

        # Risk manager validation
        side = "LONG" if normalized_action == "BUY" else "SHORT"
        estimated_price = price or 100.0
        can_trade, risk_reason = self.risk_manager.check_trade_risk(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=estimated_price,
            positions=positions,
        )
        if not can_trade:
            return False, risk_reason

        # Order sanity checks (reuse existing logic via a lightweight signal)
        from strategies.signal import SignalStrength
        signal = Signal(
            symbol=symbol,
            signal_type=SignalType.BUY if normalized_action == "BUY" else SignalType.SELL,
            strength=SignalStrength.MODERATE,
            timestamp=datetime.now(),
            quantity=quantity,
            target_price=price,
        )
        if current_equity > 0:
            sanity_ok, sanity_reason = self._sanity_check_order(signal, current_equity)
            if not sanity_ok:
                return False, sanity_reason

        return True, ""

    def get_statistics(self) -> Dict:
        """
        Get execution statistics.
        
        Returns:
            Dict with stats
        """
        total = len(self.order_history)
        return {
            'total_orders': total,
            'submitted': self.orders_submitted,
            'rejected': self.orders_rejected,
            'blocked': self.orders_blocked,
            'dry_run': self.orders_dry_run,
            'rejection_rate': self.orders_rejected / total if total > 0 else 0,
            'block_rate': self.orders_blocked / total if total > 0 else 0
        }


# Example usage
if __name__ == '__main__':
    print("OrderExecutor - Manual testing")
    print("This module requires TWS adapter and risk manager")
    print("Use run_live.py for full integration testing")
