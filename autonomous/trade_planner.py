"""Trade-plan generation for autonomous trading candidates.

Given a single selected :class:`CandidateSignal` plus deployable cash and
optional option-chain hints, decide between:

* ``BUY_SHARES`` — straight long stock with a limit price.
* ``SELL_CASH_SECURED_PUT`` — sell-to-open an OTM put fully cash-secured
  by ``strike * 100 * contracts``.

The planner never places an order, never talks to a broker; it only
produces a structured :class:`TradePlan` that the engine later validates
and (optionally) executes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal


# Default options multiplier — kept local so this module has no hard
# dependency on data/cash_availability.py.
_OPTION_MULTIPLIER = 100


class TradeType(str, Enum):
    BUY_SHARES = "BUY_SHARES"
    SELL_CASH_SECURED_PUT = "SELL_CASH_SECURED_PUT"


@dataclass
class OptionChainHint:
    """Minimal option-chain information used by the planner.

    The planner stays agnostic of any concrete options data feed; callers
    provide a hint object when they have real chain data, and the planner
    falls back to ``BUY_SHARES`` otherwise.
    """

    strike: float
    expiry: date
    bid: float = 0.0
    ask: float = 0.0
    contracts_available: int = 0  # 0 ⇒ assumed illiquid

    @property
    def midpoint(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.ask or self.bid


@dataclass
class TradePlan:
    """A concrete trade proposal produced by :class:`TradePlanner`."""

    symbol: str
    trade_type: TradeType
    action: str  # "BUY" | "SELL"
    quantity: int  # shares (BUY_SHARES) or 0 for options
    limit_price: float
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    expiry: Optional[date] = None
    strike: Optional[float] = None
    contracts: int = 0
    required_cash: float = 0.0
    expected_premium: float = 0.0
    reason: str = ""
    risk_notes: List[str] = field(default_factory=list)
    exit_plan: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trade_type": self.trade_type.value,
            "action": self.action,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "target_price": self.target_price,
            "stop_price": self.stop_price,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "strike": self.strike,
            "contracts": self.contracts,
            "required_cash": round(self.required_cash, 2),
            "expected_premium": round(self.expected_premium, 4),
            "reason": self.reason,
            "risk_notes": list(self.risk_notes),
            "exit_plan": self.exit_plan,
        }


class TradePlanner:
    """Translate a selected candidate + deployable cash → a :class:`TradePlan`.

    The planner is intentionally pure: no side effects, no I/O, no broker
    calls.  All decisions can be reproduced exactly from its inputs.
    """

    def __init__(self, config: AutonomousTradingConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def plan(
        self,
        candidate: CandidateSignal,
        deployable_cash: float,
        equity: float,
        option_hint: Optional[OptionChainHint] = None,
    ) -> Optional[TradePlan]:
        """Return a :class:`TradePlan` or ``None`` when nothing tradable.

        The planner prefers a cash-secured put when:

        * ``config.prefer_cash_secured_put`` and ``config.allow_short_put``
          are both True;
        * an ``option_hint`` is supplied with a positive strike and
          available contracts;
        * the strike sits at-or-below the candidate's support price
          (a conservative "below support" rule); and
        * deployable cash covers at least one contract's reserve.

        Otherwise it falls back to a BUY_SHARES plan, if allowed.
        """
        if candidate.last_price is None or candidate.last_price <= 0:
            return None

        if (
            self.config.prefer_cash_secured_put
            and self.config.allow_short_put
            and option_hint is not None
        ):
            put_plan = self._plan_short_put(candidate, deployable_cash, option_hint)
            if put_plan is not None:
                return put_plan

        if self.config.allow_share_buy:
            return self._plan_buy_shares(candidate, deployable_cash, equity)

        return None

    # ------------------------------------------------------------------
    # Buy shares
    # ------------------------------------------------------------------

    def _plan_buy_shares(
        self,
        candidate: CandidateSignal,
        deployable_cash: float,
        equity: float,
    ) -> Optional[TradePlan]:
        price = candidate.last_price
        if price <= 0:
            return None

        # Position-size cap is min(deployable_cash, max_new_position_pct * equity).
        cap = deployable_cash
        if equity > 0:
            cap = min(cap, equity * self.config.max_new_position_pct)
        if cap < price:
            return None  # can't afford a single share within the cap

        quantity = int(math.floor(cap / price))
        if quantity <= 0:
            return None

        required_cash = quantity * price
        # Conservative limit price: do not chase — cap at last_price.
        limit_price = round(price, 2)

        target_price = (
            round(candidate.resistance_price, 2)
            if candidate.resistance_price and candidate.resistance_price > price
            else None
        )
        stop_price = (
            round(candidate.support_price * 0.97, 2)
            if candidate.support_price and candidate.support_price > 0
            else None
        )

        return TradePlan(
            symbol=candidate.symbol,
            trade_type=TradeType.BUY_SHARES,
            action="BUY",
            quantity=quantity,
            limit_price=limit_price,
            target_price=target_price,
            stop_price=stop_price,
            required_cash=required_cash,
            reason=(
                f"{candidate.signal_label} (strength={candidate.strength_score}); "
                f"buy {quantity} shares at limit {limit_price}"
            ),
            risk_notes=[
                "Limit order only; never market.",
                f"Sized to <= {self.config.max_new_position_pct:.0%} of equity.",
            ],
            exit_plan=(
                "Exit on target_price or stop_price; "
                "review on next Strong(100) re-evaluation."
            ),
        )

    # ------------------------------------------------------------------
    # Sell cash-secured OTM put
    # ------------------------------------------------------------------

    def _plan_short_put(
        self,
        candidate: CandidateSignal,
        deployable_cash: float,
        option_hint: OptionChainHint,
    ) -> Optional[TradePlan]:
        if option_hint.contracts_available <= 0:
            return None
        if option_hint.strike <= 0:
            return None

        # Conservative rule: strike must be at-or-below the candidate's
        # technical support level (i.e. OTM put with strike already at the
        # safer side of the chart).  If we have no support level we
        # decline rather than guess.
        if (
            candidate.support_price is None
            or candidate.support_price <= 0
            or option_hint.strike > candidate.support_price
        ):
            return None

        per_contract_cash = option_hint.strike * _OPTION_MULTIPLIER
        if per_contract_cash <= 0:
            return None

        max_contracts_by_cash = int(math.floor(deployable_cash / per_contract_cash))
        contracts = min(max_contracts_by_cash, option_hint.contracts_available)
        if contracts <= 0:
            return None

        # Limit (sell-to-open) at the midpoint; never market.
        limit_price = round(option_hint.midpoint, 2)
        if limit_price <= 0:
            return None

        required_cash = per_contract_cash * contracts
        expected_premium = limit_price * _OPTION_MULTIPLIER * contracts

        return TradePlan(
            symbol=candidate.symbol,
            trade_type=TradeType.SELL_CASH_SECURED_PUT,
            action="SELL",
            quantity=0,
            limit_price=limit_price,
            expiry=option_hint.expiry,
            strike=option_hint.strike,
            contracts=contracts,
            required_cash=required_cash,
            expected_premium=expected_premium,
            reason=(
                f"{candidate.signal_label}; sell {contracts}x "
                f"{candidate.symbol} {option_hint.expiry} "
                f"{option_hint.strike}P @ limit {limit_price}"
            ),
            risk_notes=[
                "Sell-to-open limit only; never market.",
                "Strike at-or-below technical support (OTM).",
                "Cash-secured: full strike * 100 * contracts reserved.",
            ],
            exit_plan=(
                "Plan buy-to-close at 50% of premium captured or "
                "on technical breakdown below support."
            ),
        )
