"""Trade-plan generation for autonomous trading candidates."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from autonomous.adr_calculator import compute_adr_target_price
from autonomous.autonomous_config import AutonomousMode, AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.execution_quality import ExecutionQualityGuard
from autonomous.market_data_health import MarketDataHealthGuard
from autonomous.position_sizing import PositionSizer

_OPTION_MULTIPLIER = 100


def _add(reasons: Optional[List[str]], msg: str) -> None:
    if reasons is not None:
        reasons.append(msg)


class TradeType(str, Enum):
    BUY_SHARES = "BUY_SHARES"
    SELL_CASH_SECURED_PUT = "SELL_CASH_SECURED_PUT"


@dataclass
class OptionChainHint:
    """Minimal option-chain information used by the planner."""

    strike: float
    expiry: date
    bid: float = 0.0
    ask: float = 0.0
    contracts_available: int = 0

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
    action: str
    quantity: int
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
    target_mode: str = ""
    adr: Optional[float] = None
    adr_pct: Optional[float] = None
    adr_target_fraction: Optional[float] = None
    sizing: Dict[str, Any] = field(default_factory=dict)
    market_data_health: Dict[str, Any] = field(default_factory=dict)
    execution_quality: Dict[str, Any] = field(default_factory=dict)
    strategy: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)

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
            "sizing": dict(self.sizing or {}),
            "market_data_health": dict(self.market_data_health or {}),
            "execution_quality": dict(self.execution_quality or {}),
            "strategy": self.strategy,
            "extras": dict(self.extras or {}),
        }


class TradePlanner:
    """Translate a selected candidate + deployable cash into a trade plan."""

    def __init__(self, config: AutonomousTradingConfig) -> None:
        self.config = config
        self.sizer = PositionSizer(
            risk_per_trade_sizing_enabled=config.risk_per_trade_sizing_enabled,
            max_risk_per_trade_equity_pct=config.max_risk_per_trade_equity_pct,
            volatility_sizing_enabled=config.volatility_sizing_enabled,
            volatility_reference_pct=config.volatility_reference_pct,
            volatility_min_size_multiplier=config.volatility_min_size_multiplier,
            fractional_edge_sizing_enabled=config.fractional_edge_sizing_enabled,
            fractional_edge_fraction=config.fractional_edge_fraction,
            fractional_edge_min_trades=config.fractional_edge_min_trades,
            fractional_edge_max_position_pct=config.fractional_edge_max_position_pct,
            fractional_edge_retirement_mode_max_pct=config.fractional_edge_retirement_mode_max_pct,
            fractional_edge_allow_size_increase=config.fractional_edge_allow_size_increase,
            fractional_edge_can_reduce_size=config.fractional_edge_can_reduce_size,
            evidence_aware_sizing_enabled=config.evidence_aware_sizing_enabled,
            evidence_aware_min_trades_for_tiny_live=config.evidence_aware_min_trades_for_tiny_live,
            evidence_aware_min_trades_for_normal=config.evidence_aware_min_trades_for_normal,
            evidence_aware_tiny_live_max_position_pct=config.evidence_aware_tiny_live_max_position_pct,
            evidence_aware_reduced_size_multiplier=config.evidence_aware_reduced_size_multiplier,
            evidence_aware_min_confidence_for_normal=config.evidence_aware_min_confidence_for_normal,
            evidence_aware_strong_expected_r=config.evidence_aware_strong_expected_r,
            evidence_aware_max_drawdown_r_for_normal=config.evidence_aware_max_drawdown_r_for_normal,
            evidence_aware_max_slippage_bps_for_normal=config.evidence_aware_max_slippage_bps_for_normal,
            evidence_aware_allow_size_increase=config.evidence_aware_allow_size_increase,
            drawdown_governor_enabled=config.drawdown_governor_enabled,
            strategy_drawdown_pct=config.strategy_drawdown_pct,
        )
        self.execution_guard = ExecutionQualityGuard(
            enabled=config.execution_quality_guard_enabled,
            max_spread_pct=config.execution_max_spread_pct,
            max_slippage_pct=config.execution_max_slippage_pct,
            max_price_move_pct=config.execution_max_price_move_pct,
            block_on_missing_quote=config.execution_block_on_missing_quote,
        )
        self.market_data_guard = MarketDataHealthGuard(
            enabled=config.market_data_health_guard_enabled,
            max_quote_age_seconds=config.market_data_max_quote_age_seconds,
            max_spread_pct=config.market_data_max_spread_pct,
            max_last_mid_deviation_pct=config.market_data_max_last_mid_deviation_pct,
            block_stale_quotes_live=config.market_data_block_stale_quotes_live,
            block_missing_bid_ask_live=config.market_data_block_missing_bid_ask_live,
            block_missing_timestamp_live=config.market_data_block_missing_timestamp_live,
            block_feed_unhealthy_live=config.market_data_block_feed_unhealthy_live,
            block_market_closed_live=config.market_data_block_market_closed_live,
            required_live_source=config.live_market_data_required_source,
            require_live_market_data_type=config.live_market_data_require_live_type,
            allow_yahoo_for_live_trading=config.allow_yahoo_for_live_trading,
        )

    def plan(
        self,
        candidate: CandidateSignal,
        deployable_cash: float,
        equity: float,
        option_hint: Optional[OptionChainHint] = None,
        reasons: Optional[List[str]] = None,
    ) -> Optional[TradePlan]:
        if candidate.last_price is None or candidate.last_price <= 0:
            _add(reasons, f"candidate.last_price invalid ({candidate.last_price!r})")
            return None

        if (candidate.extras or {}).get("strategy") == "opening_range_breakout":
            return self._plan_orb_breakout(candidate, deployable_cash, equity, reasons=reasons)

        if self.config.prefer_cash_secured_put and self.config.allow_short_put and option_hint is not None:
            put_plan = self._plan_short_put(candidate, deployable_cash, equity, option_hint, reasons=reasons)
            if put_plan is not None:
                return put_plan

        if self.config.allow_share_buy:
            return self._plan_buy_shares(candidate, deployable_cash, equity, reasons=reasons)

        _add(reasons, "config.allow_share_buy=False and no put plan produced")
        return None

    def _position_cap(self, deployable_cash: float, equity: float) -> tuple[float, Optional[float], float, float, float]:
        cash_pct = self.config.deployable_cash_cap_pct()
        eq_pct = self.config.equity_cap_pct()
        cash_cap = deployable_cash * cash_pct
        cap = cash_cap
        equity_cap = None
        if equity > 0:
            equity_cap = equity * eq_pct
            cap = min(cap, equity_cap)
        return cap, equity_cap, cash_cap, cash_pct, eq_pct

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

        cap, equity_cap, cash_cap, cash_pct, eq_pct = self._position_cap(deployable_cash, equity)
        if cap < price:
            equity_str = f", equity_cap=${equity_cap:,.2f} (equity ${equity:,.2f} * {eq_pct:.0%})" if equity_cap is not None else ""
            _add(
                reasons,
                f"{candidate.symbol}: position cap ${cap:,.2f} < share price ${price:,.2f} "
                f"[deployable ${deployable_cash:,.2f} * {cash_pct:.0%} = ${cash_cap:,.2f}{equity_str}] — can't afford 1 share within sizing cap"
            )
            return None

        limit_price = round(price, 2)
        market_data_health = self._market_data_health(candidate)
        if not market_data_health.get("allowed", True):
            _add(reasons, f"market data health rejected - {market_data_health.get('reason')}")
            return None
        quality = self._execution_quality(candidate, limit_price)
        if not quality.get("allowed", True):
            _add(reasons, f"execution quality rejected — {quality.get('reason')}")
            return None

        target_price, target_mode, adr_val, adr_pct_val, adr_frac = self._compute_target(candidate, price)
        stop_price = round(candidate.support_price * 0.97, 2) if candidate.support_price and candidate.support_price > 0 else None

        if self.config.mode == AutonomousMode.ASSISTED_LIVE and self.config.require_stop_price_for_assisted_live and (stop_price is None or stop_price <= 0 or stop_price >= limit_price):
            _add(reasons, f"{candidate.symbol}: assisted_live requires valid stop_price from support/invalidation level")
            return None

        sizing = self.sizer.size_buy_shares(
            symbol=candidate.symbol,
            entry_price=limit_price,
            stop_price=stop_price,
            base_cap_value=cap,
            equity=equity,
            adr_pct=_positive_float(candidate.extras.get("adr_pct")),
            edge_estimate=_dict_or_none(candidate.extras.get("edge_estimate")),
            observed_edge_trades=_int(candidate.extras.get("edge_observed_trades"), default=0),
            setup_eligibility=_dict_or_none(candidate.extras.get("setup_eligibility")),
            strategy_drawdown_pct=_positive_float(candidate.extras.get("strategy_drawdown_pct")),
            avg_slippage_bps=_positive_float(
                _first(candidate.extras, "edge_avg_slippage_bps", "avg_slippage_bps")
            ),
        )
        quantity = sizing.quantity
        if quantity <= 0:
            _add(reasons, f"{candidate.symbol}: final sizing cap cannot buy 1 share; binding_cap={sizing.binding_cap}")
            return None

        required_cash = sizing.required_cash
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
            sizing=sizing.to_dict(),
            market_data_health=market_data_health,
            execution_quality=quality,
            reason=f"{candidate.signal_label} (strength={candidate.strength_score}); buy {quantity} shares at limit {limit_price}",
            risk_notes=[
                "Limit order only; never market.",
                f"Sized to <= {self.config.equity_cap_pct():.0%} of equity and <= {self.config.deployable_cash_cap_pct():.0%} of deployable cash.",
                f"Binding sizing cap: {sizing.binding_cap}.",
                f"Market-data health: {market_data_health.get('reason')}.",
                f"Execution quality: {quality.get('reason')}.",
            ] + list(sizing.notes)
            + [f"market_data_health: {w}" for w in market_data_health.get("warnings", [])]
            + [f"execution_quality: {w}" for w in quality.get("warnings", [])],
            exit_plan=f"Exit on target_price ({target_mode}) or stop_price; review on next Strong(100) re-evaluation.",
        )

    def _plan_orb_breakout(
        self,
        candidate: CandidateSignal,
        deployable_cash: float,
        equity: float,
        reasons: Optional[List[str]] = None,
    ) -> Optional[TradePlan]:
        """Plan an Opening Range Breakout (ORB) candidate.

        ORB entry/stop/target levels come directly from the runtime ORB
        strategy/proposal (see ``autonomous.opening_range_signal_provider``)
        and must be preserved exactly:

        - The target is *never* overwritten with support/resistance/ADR/
          percent logic (``_compute_target`` is intentionally not called).
        - The stop is *never* derived from generic support.
        - Malformed ORB extras (missing/invalid entry, stop, target, or R/R)
          are rejected rather than silently patched.
        """
        extras = candidate.extras or {}
        entry_price, stop_price, target_price, rr_ratio, error = _extract_orb_levels(extras)
        if error is not None:
            _add(reasons, f"{candidate.symbol}: malformed ORB extras — {error}")
            return None

        # Long-only (Prime Directive / ORB non-goals: no short-side entries).
        if extras.get("direction") not in (None, "LONG"):
            _add(reasons, f"{candidate.symbol}: ORB direction {extras.get('direction')!r} not supported (long-only)")
            return None

        # Stop and target are always required for paper/autonomous assisted
        # ORB paths — this is enforced unconditionally, not only in
        # assisted_live mode, because an ORB candidate without both levels
        # cannot be a valid bracket.
        if stop_price <= 0 or stop_price >= entry_price:
            _add(reasons, f"{candidate.symbol}: ORB requires a valid stop_price below entry")
            return None
        if target_price <= 0 or target_price <= entry_price:
            _add(reasons, f"{candidate.symbol}: ORB requires a valid target_price above entry")
            return None

        cap, equity_cap, cash_cap, cash_pct, eq_pct = self._position_cap(deployable_cash, equity)
        limit_price = round(entry_price, 2)
        if cap < limit_price:
            equity_str = f", equity_cap=${equity_cap:,.2f} (equity ${equity:,.2f} * {eq_pct:.0%})" if equity_cap is not None else ""
            _add(
                reasons,
                f"{candidate.symbol}: position cap ${cap:,.2f} < ORB entry price ${limit_price:,.2f} "
                f"[deployable ${deployable_cash:,.2f} * {cash_pct:.0%} = ${cash_cap:,.2f}{equity_str}] — can't afford 1 share within sizing cap"
            )
            return None

        market_data_health = self._market_data_health(candidate)
        if not market_data_health.get("allowed", True):
            _add(reasons, f"market data health rejected - {market_data_health.get('reason')}")
            return None
        quality = self._execution_quality(candidate, limit_price)
        if not quality.get("allowed", True):
            _add(reasons, f"execution quality rejected — {quality.get('reason')}")
            return None

        stop_for_sizing = round(stop_price, 2)
        sizing = self.sizer.size_buy_shares(
            symbol=candidate.symbol,
            entry_price=limit_price,
            stop_price=stop_for_sizing,
            base_cap_value=cap,
            equity=equity,
            adr_pct=_positive_float(extras.get("adr_pct")),
            edge_estimate=_dict_or_none(extras.get("edge_estimate")),
            observed_edge_trades=_int(extras.get("edge_observed_trades"), default=0),
            setup_eligibility=_dict_or_none(extras.get("setup_eligibility")),
            strategy_drawdown_pct=_positive_float(extras.get("strategy_drawdown_pct")),
            avg_slippage_bps=_positive_float(
                _first(extras, "edge_avg_slippage_bps", "avg_slippage_bps")
            ),
        )
        quantity = sizing.quantity
        if quantity <= 0:
            _add(reasons, f"{candidate.symbol}: final sizing cap cannot buy 1 share; binding_cap={sizing.binding_cap}")
            return None

        required_cash = sizing.required_cash
        orb_evidence = {
            "setup_model": extras.get("setup_model"),
            "direction": extras.get("direction"),
            "opening_range_high": extras.get("opening_range_high"),
            "opening_range_low": extras.get("opening_range_low"),
            "confirmation_time": extras.get("confirmation_time"),
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "risk_per_share": extras.get("risk_per_share"),
            "reward_per_share": extras.get("reward_per_share"),
            "rr_ratio": rr_ratio,
            "orb_evidence": extras.get("orb_evidence"),
        }
        return TradePlan(
            symbol=candidate.symbol,
            trade_type=TradeType.BUY_SHARES,
            action="BUY",
            quantity=quantity,
            limit_price=limit_price,
            target_price=round(target_price, 2),
            stop_price=stop_for_sizing,
            required_cash=required_cash,
            target_mode="opening_range_breakout",
            sizing=sizing.to_dict(),
            market_data_health=market_data_health,
            execution_quality=quality,
            strategy="opening_range_breakout",
            extras=orb_evidence,
            reason=(
                f"{candidate.signal_label} (strategy=opening_range_breakout, "
                f"model={extras.get('setup_model')}, rr_ratio={rr_ratio:.2f}); "
                f"buy {quantity} shares at limit {limit_price}"
            ),
            risk_notes=[
                "Limit order only; never market.",
                "ORB entry/stop/target preserved exactly from the ORB setup — "
                "not derived from generic support/resistance/ADR/percent logic.",
                f"Sized to <= {self.config.equity_cap_pct():.0%} of equity and <= {self.config.deployable_cash_cap_pct():.0%} of deployable cash.",
                f"Binding sizing cap: {sizing.binding_cap}.",
                f"Market-data health: {market_data_health.get('reason')}.",
                f"Execution quality: {quality.get('reason')}.",
            ] + list(sizing.notes)
            + [f"market_data_health: {w}" for w in market_data_health.get("warnings", [])]
            + [f"execution_quality: {w}" for w in quality.get("warnings", [])],
            exit_plan=f"Exit on ORB target_price ({round(target_price, 2)}) or ORB stop_price ({stop_for_sizing}); no re-target after entry.",
        )

    def _market_data_health(self, candidate: CandidateSignal) -> Dict[str, Any]:
        extras = candidate.extras or {}
        decision = self.market_data_guard.evaluate(
            symbol=candidate.symbol,
            mode=self.config.mode,
            bid=_first(extras, "bid", "quote_bid", "execution_bid"),
            ask=_first(extras, "ask", "quote_ask", "execution_ask"),
            last=_first(extras, "last", "quote_last", "execution_last", "current_price"),
            reference_price=candidate.last_price,
            bid_timestamp=_first(extras, "bid_timestamp", "quote_bid_timestamp", "bid_ts"),
            ask_timestamp=_first(extras, "ask_timestamp", "quote_ask_timestamp", "ask_ts"),
            last_timestamp=_first(extras, "last_timestamp", "quote_last_timestamp", "last_ts"),
            quote_timestamp=_first(
                extras,
                "quote_timestamp",
                "market_data_timestamp",
                "updated_at",
                "last_updated",
                "timestamp",
                "as_of",
            ),
            source=_first(extras, "market_data_source", "quote_source", "source"),
            market_data_type=_first(extras, "market_data_type", "ibkr_market_data_type"),
            feed_healthy=_first(extras, "market_data_feed_healthy", "feed_healthy"),
            feed_status=_first(extras, "market_data_status", "feed_status", "data_status"),
            market_open=_first(extras, "market_is_open", "market_open"),
        )
        return decision.to_dict()

    def _execution_quality(self, candidate: CandidateSignal, limit_price: float) -> Dict[str, Any]:
        extras = candidate.extras or {}
        decision = self.execution_guard.evaluate_buy_limit(
            symbol=candidate.symbol,
            limit_price=limit_price,
            reference_price=candidate.last_price,
            bid=_first(extras, "bid", "quote_bid", "execution_bid"),
            ask=_first(extras, "ask", "quote_ask", "execution_ask"),
            last=_first(extras, "last", "quote_last", "execution_last", "current_price"),
        )
        return decision.to_dict()

    def _compute_target(self, candidate: CandidateSignal, entry_price: float) -> tuple:
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
                    resistance_price=candidate.resistance_price if candidate.resistance_price and candidate.resistance_price > entry_price else None,
                    respect_resistance_cap=self.config.adr_respect_resistance_cap,
                )
                if target is not None and target > entry_price:
                    return (target, "adr_intraday", adr_val, adr_pct_val, self.config.adr_target_fraction)
            return self._fallback_target(candidate, entry_price)
        if mode == "percent":
            target = round(entry_price * (1.0 + self.config.take_profit_pct), 2)
            return (target, "percent", None, None, None)
        return self._resistance_target(candidate, entry_price)

    def _resistance_target(self, candidate: CandidateSignal, entry_price: float) -> tuple:
        if candidate.resistance_price and candidate.resistance_price > entry_price:
            return (round(candidate.resistance_price, 2), "resistance", None, None, None)
        return (None, "resistance", None, None, None)

    def _fallback_target(self, candidate: CandidateSignal, entry_price: float) -> tuple:
        if candidate.resistance_price and candidate.resistance_price > entry_price:
            return (round(candidate.resistance_price, 2), "resistance_fallback", None, None, None)
        if self.config.take_profit_pct > 0:
            target = round(entry_price * (1.0 + self.config.take_profit_pct), 2)
            return (target, "percent_fallback", None, None, None)
        return (None, "none", None, None, None)

    def _plan_short_put(self, candidate: CandidateSignal, deployable_cash: float, equity: float, option_hint: OptionChainHint, reasons: Optional[List[str]] = None) -> Optional[TradePlan]:
        if option_hint.contracts_available <= 0:
            _add(reasons, f"{candidate.symbol}: option_hint.contracts_available = {option_hint.contracts_available} (need > 0)")
            return None
        if option_hint.strike <= 0:
            _add(reasons, f"{candidate.symbol}: option_hint.strike = {option_hint.strike}")
            return None
        if candidate.support_price is None or candidate.support_price <= 0 or option_hint.strike > candidate.support_price:
            _add(reasons, f"{candidate.symbol}: strike {option_hint.strike} > support {candidate.support_price} (require strike <= support)")
            return None

        per_contract_cash = option_hint.strike * _OPTION_MULTIPLIER
        if per_contract_cash <= 0:
            _add(reasons, f"{candidate.symbol}: per_contract_cash = {per_contract_cash}")
            return None

        cap, equity_cap, cash_cap, cash_pct, eq_pct = self._position_cap(deployable_cash, equity)
        dd_decision = self.sizer.drawdown_governor.evaluate(_positive_float(candidate.extras.get("strategy_drawdown_pct")))
        if dd_decision.halted:
            _add(reasons, f"{candidate.symbol}: drawdown governor halted new entries ({dd_decision.reason})")
            return None
        if dd_decision.multiplier < 1.0:
            cap = cap * dd_decision.multiplier
        max_contracts_by_cash = int(math.floor(cap / per_contract_cash))
        contracts = min(max_contracts_by_cash, option_hint.contracts_available)
        if contracts <= 0:
            equity_str = f", equity ${equity:,.2f} * {eq_pct:.0%} = ${equity_cap:,.2f}" if equity_cap is not None else ""
            _add(reasons, f"{candidate.symbol}: 0 affordable put contracts — floor(cap ${cap:,.2f} / ${per_contract_cash:,.2f} per contract) = {max_contracts_by_cash} [deployable ${deployable_cash:,.2f} * {cash_pct:.0%} = ${cash_cap:,.2f}{equity_str}]")
            return None

        limit_price = round(option_hint.midpoint, 2)
        if limit_price <= 0:
            _add(reasons, f"{candidate.symbol}: option midpoint <= 0 (bid={option_hint.bid}, ask={option_hint.ask})")
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
            reason=f"{candidate.signal_label}; sell {contracts}x {candidate.symbol} {option_hint.expiry} {option_hint.strike}P @ limit {limit_price}",
            risk_notes=["Sell-to-open limit only; never market.", "Strike at-or-below technical support (OTM).", "Cash-secured: full strike * 100 * contracts reserved."],
            exit_plan="Plan buy-to-close at 50% of premium captured or on technical breakdown below support.",
        )


def _extract_orb_levels(extras: Dict[str, Any]) -> tuple:
    """Validate and extract ORB entry/stop/target/R:R from candidate extras.

    Returns ``(entry_price, stop_price, target_price, rr_ratio, error)`` where
    ``error`` is ``None`` on success or a short human-readable reason string
    describing why the extras are malformed.
    """
    entry_price = _positive_float(extras.get("entry_price"))
    stop_price = _positive_float(extras.get("stop_price"))
    target_price = _positive_float(extras.get("target_price"))
    rr_ratio = _positive_float(extras.get("rr_ratio"))

    if entry_price is None or entry_price <= 0:
        return None, None, None, None, f"entry_price invalid ({extras.get('entry_price')!r})"
    if stop_price is None or stop_price <= 0:
        return None, None, None, None, f"stop_price invalid ({extras.get('stop_price')!r})"
    if target_price is None or target_price <= 0:
        return None, None, None, None, f"target_price invalid ({extras.get('target_price')!r})"
    if rr_ratio is None or rr_ratio <= 0:
        return None, None, None, None, f"rr_ratio invalid ({extras.get('rr_ratio')!r})"
    if not (stop_price < entry_price < target_price):
        return (
            None, None, None, None,
            f"prices out of order (stop={stop_price}, entry={entry_price}, target={target_price}); "
            "expected stop < entry < target",
        )
    return entry_price, stop_price, target_price, rr_ratio, None


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dict_or_none(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _first(mapping: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None
