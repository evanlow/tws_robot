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

from autonomous.adr_calculator import compute_adr_target_price
from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal


# Default options multiplier — kept local so this module has no hard
# dependency on data/cash_availability.py.
_OPTION_MULTIPLIER = 100


def _add(reasons: Optional[List[str]], msg: str) -> None:
    """Append ``msg`` to ``reasons`` when the caller passed an accumulator.

    Used by the planner to record quantitative rejection details (cap vs.
    price, contracts vs. cash, strike vs. support, etc.) so the engine
    can surface them in ``decision.rejection_reason`` instead of the
    generic "no tradable plan" string.
    """
    if reasons is not None:
        reasons.append(msg)


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
    # ADR target metadata (populated when exit_target_mode=adr_intraday)
    target_mode: str = ""
    adr: Optional[float] = None
    adr_pct: Optional[float] = None
    adr_target_fraction: Optional[float] = None

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
            "target_mode": self.target_mode,
            "adr": round(self.adr, 4) if self.adr is not None else None,
            "adr_pct": round(self.adr_pct, 6) if self.adr_pct is not None else None,
            "adr_target_fraction": self.adr_target_fraction,
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
        reasons: Optional[List[str]] = None,
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

        When ``reasons`` is provided, the planner appends one short,
        numeric explanation per rejection branch so callers can surface
        a quantitative "no tradable plan" message instead of the generic
        catch-all.
        """
        if candidate.last_price is None or candidate.last_price <= 0:
            _add(reasons, f"candidate.last_price invalid ({candidate.last_price!r})")
            return None

        if (
            self.config.prefer_cash_secured_put
            and self.config.allow_short_put
            and option_hint is not None
        ):
            put_plan = self._plan_short_put(
                candidate, deployable_cash, equity, option_hint, reasons=reasons
            )
            if put_plan is not None:
                return put_plan

        if self.config.allow_share_buy:
            return self._plan_buy_shares(
                candidate, deployable_cash, equity, reasons=reasons
            )

        _add(reasons, "config.allow_share_buy=False and no put plan produced")
        return None

    # ------------------------------------------------------------------
    # Buy shares
    # ------------------------------------------------------------------

    def _plan_buy_shares(
        self,
        candidate: CandidateSignal,
        deployable_cash: float,
        equity: float,
        reasons: Optional[List[str]] = None,
    ) -> Optional[TradePlan]:
        price = candidate.last_price
        if price <= 0:
            _add(reasons, f"{candidate.symbol}: price <= 0 ({price})")
            return None

        # Position-size cap is the lower of:
        #   * deployable_cash * deployable_cash_cap_pct
        #   * equity          * equity_cap_pct
        # Either fraction may be overridden independently via env vars;
        # both fall back to max_new_position_pct when unset.
        cash_pct = self.config.deployable_cash_cap_pct()
        eq_pct = self.config.equity_cap_pct()
        cash_cap = deployable_cash * cash_pct
        cap = cash_cap
        equity_cap = None
        if equity > 0:
            equity_cap = equity * eq_pct
            cap = min(cap, equity_cap)
        if cap < price:
            equity_str = (
                f", equity_cap=${equity_cap:,.2f} (equity ${equity:,.2f} * {eq_pct:.0%})"
                if equity_cap is not None else ""
            )
            _add(
                reasons,
                f"{candidate.symbol}: position cap ${cap:,.2f} < share price ${price:,.2f} "
                f"[deployable ${deployable_cash:,.2f} * {cash_pct:.0%} = ${cash_cap:,.2f}"
                f"{equity_str}] — can't afford 1 share within sizing cap"
            )
            return None  # can't afford a single share within the cap

        quantity = int(math.floor(cap / price))
        if quantity <= 0:
            _add(
                reasons,
                f"{candidate.symbol}: floor(cap ${cap:,.2f} / price ${price:,.2f}) = 0"
            )
            return None

        required_cash = quantity * price
        # Conservative limit price: do not chase — cap at last_price.
        limit_price = round(price, 2)

        # --- Target price calculation based on exit_target_mode ---
        target_price, target_mode, adr_val, adr_pct_val, adr_frac = (
            self._compute_target(candidate, price)
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
            target_mode=target_mode,
            adr=adr_val,
            adr_pct=adr_pct_val,
            adr_target_fraction=adr_frac,
            reason=(
                f"{candidate.signal_label} (strength={candidate.strength_score}); "
                f"buy {quantity} shares at limit {limit_price}"
            ),
            risk_notes=[
                "Limit order only; never market.",
                (
                    f"Sized to <= {self.config.equity_cap_pct():.0%} of equity "
                    f"and <= {self.config.deployable_cash_cap_pct():.0%} of deployable cash."
                ),
            ],
            exit_plan=(
                f"Exit on target_price ({target_mode}) or stop_price; "
                "review on next Strong(100) re-evaluation."
            ),
        )

    # ------------------------------------------------------------------
    # Target price computation
    # ------------------------------------------------------------------

    def _compute_target(
        self,
        candidate: CandidateSignal,
        entry_price: float,
    ) -> tuple:
        """Compute target price based on configured exit_target_mode.

        Returns (target_price, target_mode, adr, adr_pct, adr_target_fraction).
        """
        mode = self.config.exit_target_mode

        if mode == "adr_intraday":
            adr_val = candidate.extras.get("adr")
            adr_pct_val = candidate.extras.get("adr_pct")
            adr_valid = candidate.extras.get("adr_valid", False)

            if adr_valid and adr_val and adr_val > 0:
                target = compute_adr_target_price(
                    entry_price=entry_price,
                    adr=adr_val,
                    target_fraction=self.config.adr_target_fraction,
                    min_target_pct=self.config.adr_min_target_pct,
                    max_target_pct=self.config.adr_max_target_pct,
                    resistance_price=(
                        candidate.resistance_price
                        if candidate.resistance_price
                        and candidate.resistance_price > entry_price
                        else None
                    ),
                    respect_resistance_cap=self.config.adr_respect_resistance_cap,
                )
                if target is not None and target > entry_price:
                    return (
                        target,
                        "adr_intraday",
                        adr_val,
                        adr_pct_val,
                        self.config.adr_target_fraction,
                    )

            # ADR data unavailable — fall back to resistance then percent
            return self._fallback_target(candidate, entry_price)

        if mode == "percent":
            target = round(entry_price * (1.0 + self.config.take_profit_pct), 2)
            return (target, "percent", None, None, None)

        # Default: resistance mode
        return self._resistance_target(candidate, entry_price)

    def _resistance_target(
        self, candidate: CandidateSignal, entry_price: float
    ) -> tuple:
        """Resistance-based target (original behaviour)."""
        if candidate.resistance_price and candidate.resistance_price > entry_price:
            return (
                round(candidate.resistance_price, 2),
                "resistance",
                None,
                None,
                None,
            )
        return (None, "resistance", None, None, None)

    def _fallback_target(
        self, candidate: CandidateSignal, entry_price: float
    ) -> tuple:
        """Fallback when ADR data is unavailable: try resistance, then percent."""
        # Try resistance first
        if candidate.resistance_price and candidate.resistance_price > entry_price:
            return (
                round(candidate.resistance_price, 2),
                "resistance_fallback",
                None,
                None,
                None,
            )
        # Final fallback: configured percent target
        if self.config.take_profit_pct > 0:
            target = round(entry_price * (1.0 + self.config.take_profit_pct), 2)
            return (target, "percent_fallback", None, None, None)
        return (None, "none", None, None, None)

    # ------------------------------------------------------------------
    # Sell cash-secured OTM put
    # ------------------------------------------------------------------

    def _plan_short_put(
        self,
        candidate: CandidateSignal,
        deployable_cash: float,
        equity: float,
        option_hint: OptionChainHint,
        reasons: Optional[List[str]] = None,
    ) -> Optional[TradePlan]:
        if option_hint.contracts_available <= 0:
            _add(
                reasons,
                f"{candidate.symbol}: option_hint.contracts_available "
                f"= {option_hint.contracts_available} (need > 0)"
            )
            return None
        if option_hint.strike <= 0:
            _add(reasons, f"{candidate.symbol}: option_hint.strike = {option_hint.strike}")
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
            _add(
                reasons,
                f"{candidate.symbol}: strike {option_hint.strike} > support "
                f"{candidate.support_price} (require strike <= support)"
            )
            return None

        per_contract_cash = option_hint.strike * _OPTION_MULTIPLIER
        if per_contract_cash <= 0:
            _add(reasons, f"{candidate.symbol}: per_contract_cash = {per_contract_cash}")
            return None

        cash_pct = self.config.deployable_cash_cap_pct()
        eq_pct = self.config.equity_cap_pct()
        cash_cap = deployable_cash * cash_pct
        cap = cash_cap
        equity_cap = None
        if equity > 0:
            equity_cap = equity * eq_pct
            cap = min(cap, equity_cap)
        max_contracts_by_cash = int(math.floor(cap / per_contract_cash))
        contracts = min(max_contracts_by_cash, option_hint.contracts_available)
        if contracts <= 0:
            equity_str = (
                f", equity ${equity:,.2f} * {eq_pct:.0%} = ${equity_cap:,.2f}"
                if equity_cap is not None
                else ""
            )
            _add(
                reasons,
                f"{candidate.symbol}: 0 affordable put contracts — "
                f"floor(cap ${cap:,.2f} / ${per_contract_cash:,.2f} per contract) = "
                f"{max_contracts_by_cash} [deployable ${deployable_cash:,.2f} * "
                f"{cash_pct:.0%} = ${cash_cap:,.2f}{equity_str}]"
            )
            return None

        # Limit (sell-to-open) at the midpoint; never market.
        limit_price = round(option_hint.midpoint, 2)
        if limit_price <= 0:
            _add(
                reasons,
                f"{candidate.symbol}: option midpoint <= 0 "
                f"(bid={option_hint.bid}, ask={option_hint.ask})"
            )
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
