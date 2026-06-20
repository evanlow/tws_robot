"""Autonomous trading engine.

Top-level orchestrator that combines:

* :class:`data.cash_availability.CashAvailabilityAnalyzer` (deployable cash)
* :class:`autonomous.candidate_scanner.CandidateScanner` (S&P 500 universe)
* :class:`autonomous.candidate_ranker.CandidateRanker` (Strong/Rebound filter)
* :class:`autonomous.trade_planner.TradePlanner` (buy-shares / short-put plan)
* Optional :class:`risk.risk_manager.RiskManager` (final risk-check gate)
* Optional paper / live execution adapters

Default behaviour is **recommendation only**: the engine returns a structured
:class:`AutonomousDecision` and never places an order.  Paper execution requires
``mode=PAPER_EXECUTE`` and a paper adapter; live execution additionally requires
``allow_live_execution=True`` and explicit confirmation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from autonomous.audit import AuditLogger
from autonomous.autonomous_config import AutonomousMode, AutonomousTradingConfig
from autonomous.basket_planner import BasketPlanner
from autonomous.candidate_ranker import CandidateRanker
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.evidence_store import TradeEvidenceStore
from autonomous.market_regime import evaluate_market_regime
from autonomous.trade_planner import OptionChainHint, TradePlan, TradePlanner, TradeType

logger = logging.getLogger(__name__)


class DecisionStatus(str, Enum):
    """Outcome of one ``run_once()`` invocation."""

    EMERGENCY_STOP = "emergency_stop"
    NO_DEPLOYABLE_CASH = "no_deployable_cash"
    NO_CANDIDATE = "no_candidate"
    NO_TRADE_PLAN = "no_trade_plan"
    RISK_REJECTED = "risk_rejected"
    LIVE_BLOCKED = "live_blocked"
    LIVE_PLAN_READY = "live_plan_ready"
    CONFIRMATION_REQUIRED = "confirmation_required"
    DAILY_LIMIT_REACHED = "daily_limit_reached"
    MARKET_NOT_SUITABLE = "market_not_suitable"
    RECOMMENDED = "recommended"
    PAPER_EXECUTED = "paper_executed"
    LIVE_EXECUTED = "live_executed"
    EXECUTION_FAILED = "execution_failed"


@dataclass
class AutonomousDecision:
    """Structured outcome of one ``AutonomousTradingEngine.run_once()`` call."""

    status: DecisionStatus
    mode: AutonomousMode
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rejection_reason: Optional[str] = None
    deployable_cash: float = 0.0
    cash_snapshot: Dict[str, Any] = field(default_factory=dict)
    shortlist: List[Dict[str, Any]] = field(default_factory=list)
    rejected_candidates: List[Dict[str, Any]] = field(default_factory=list)
    selected: Optional[Dict[str, Any]] = None
    trade_plan: Optional[Dict[str, Any]] = None
    selected_basket: List[Dict[str, Any]] = field(default_factory=list)
    trade_plans: List[Dict[str, Any]] = field(default_factory=list)
    basket_plan: Optional[Dict[str, Any]] = None
    risk_check: Optional[Dict[str, Any]] = None
    order_id: Optional[int] = None
    order_ids: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    market_gate: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "mode": self.mode.value,
            "timestamp": self.timestamp.isoformat(),
            "rejection_reason": self.rejection_reason,
            "deployable_cash": round(self.deployable_cash, 2),
            "cash_snapshot": dict(self.cash_snapshot),
            "shortlist": list(self.shortlist),
            "rejected_candidates": list(self.rejected_candidates),
            "selected": self.selected,
            "trade_plan": self.trade_plan,
            "selected_basket": list(self.selected_basket),
            "trade_plans": list(self.trade_plans),
            "basket_plan": self.basket_plan,
            "risk_check": self.risk_check,
            "order_id": self.order_id,
            "order_ids": list(self.order_ids),
            "notes": list(self.notes),
            "market_gate": self.market_gate,
        }


OptionHintProvider = Callable[[CandidateSignal], Optional[OptionChainHint]]
SpyPriceProvider = Callable[[], Optional[Dict[str, Any]]]


class AutonomousTradingEngine:
    """Top-level orchestrator for the guarded autonomous trading flow."""

    def __init__(
        self,
        scanner: CandidateScanner,
        cash_analyzer,
        account_provider: Callable[[], Dict[str, Any]],
        positions_provider: Callable[[], Dict[str, Dict[str, Any]]],
        config: Optional[AutonomousTradingConfig] = None,
        orders_provider: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        risk_manager: Any = None,
        paper_adapter: Any = None,
        option_hint_provider: Optional[OptionHintProvider] = None,
        spy_price_provider: Optional[SpyPriceProvider] = None,
        audit_logger: Optional[AuditLogger] = None,
        evidence_store: Optional[TradeEvidenceStore] = None,
    ) -> None:
        self.config = config or AutonomousTradingConfig()
        self.scanner = scanner
        self.cash_analyzer = cash_analyzer
        self._account_provider = account_provider
        self._positions_provider = positions_provider
        self._orders_provider = orders_provider or (lambda: [])
        self.risk_manager = risk_manager
        self.paper_adapter = paper_adapter
        self.option_hint_provider = option_hint_provider
        self.spy_price_provider = spy_price_provider

        self.ranker = CandidateRanker(self.config)
        self.planner = TradePlanner(self.config)
        self.basket_planner = BasketPlanner(self.config)
        self.audit = audit_logger or AuditLogger(self.config.audit_log_dir)
        self.evidence = evidence_store or TradeEvidenceStore(self.config.audit_log_dir)

    def _emergency_stop_active(self) -> bool:
        try:
            if Path(self.config.emergency_stop_file).exists():
                return True
        except OSError:
            pass
        if self.risk_manager is not None:
            if getattr(self.risk_manager, "emergency_stop_active", False):
                return True
        return False

    def _emit(self, decision: AutonomousDecision) -> AutonomousDecision:
        record = {
            "engine": "AutonomousTradingEngine",
            "config": self.config.to_dict(),
            "decision": decision.to_dict(),
        }
        self.audit.log_decision(record, when=decision.timestamp)
        try:
            self.evidence.log_decision(record, when=decision.timestamp)
        except Exception:
            logger.exception("Failed to write autonomous evidence record")
        return decision

    def _daily_limit_reached(self, when: datetime) -> bool:
        limit = self.config.max_trades_per_day
        if limit <= 0:
            return True
        executed = self.audit.count_executions_on(when=when)
        return executed >= limit

    def _check_spy_gate(self) -> Optional[Dict[str, Any]]:
        if self.spy_price_provider is None:
            return None
        payload = self.spy_price_provider() or {}
        return evaluate_market_regime(
            payload,
            vix_guard_enabled=self.config.vix_guard_enabled,
            vix_caution_level=self.config.vix_caution_level,
            vix_block_level=self.config.vix_block_level,
            vix_caution_intraday_rise_pct=self.config.vix_caution_intraday_rise_pct,
            vix_block_intraday_rise_pct=self.config.vix_block_intraday_rise_pct,
            vix_missing_blocks_trade=self.config.vix_missing_blocks_trade,
            vix_caution_size_multiplier=self.config.vix_caution_size_multiplier,
            vix_high_size_multiplier=self.config.vix_high_size_multiplier,
        )

    def run_once(
        self,
        confirm: bool = False,
        today: Optional[date] = None,
        max_symbols: Optional[int] = None,
    ) -> AutonomousDecision:
        decision = AutonomousDecision(
            status=DecisionStatus.NO_CANDIDATE,
            mode=self.config.mode,
        )

        if self._emergency_stop_active():
            decision.status = DecisionStatus.EMERGENCY_STOP
            decision.rejection_reason = "EMERGENCY_STOP active (file or RiskManager flag)"
            return self._emit(decision)

        account_summary = self._account_provider() or {}
        positions = self._positions_provider() or {}
        orders = self._orders_provider() or []

        cash_result = self.cash_analyzer.analyze(
            account_summary=account_summary,
            positions=positions,
            orders=orders,
        )
        decision.deployable_cash = float(cash_result.deployable_cash)
        decision.cash_snapshot = cash_result.to_dict()

        if decision.deployable_cash < self.config.min_deployable_cash:
            decision.status = DecisionStatus.NO_DEPLOYABLE_CASH
            decision.rejection_reason = (
                f"deployable_cash {decision.deployable_cash:.2f} < "
                f"min {self.config.min_deployable_cash:.2f}"
            )
            return self._emit(decision)

        try:
            spy_gate = self._check_spy_gate()
        except Exception:
            logger.exception("market-regime provider raised")
            spy_gate = {
                "symbol": "SPY",
                "classification": "Bearish / Not Suitable",
                "bullish": False,
                "trade_allowed": False,
                "size_multiplier": 0.0,
                "reasons": ["Market-regime provider raised an exception"],
                "error": "market-regime provider raised an exception",
            }
        if spy_gate is not None:
            decision.market_gate = spy_gate
            trade_allowed = bool(spy_gate.get("trade_allowed", spy_gate.get("bullish")))
            if not trade_allowed:
                decision.status = DecisionStatus.MARKET_NOT_SUITABLE
                open_p = float(spy_gate.get("open") or 0.0)
                curr_p = float(spy_gate.get("current") or 0.0)
                price_info = (
                    f" (SPY Open: ${open_p:.2f}, Current: ${curr_p:.2f})"
                    if open_p > 0 or curr_p > 0
                    else " (SPY price unavailable)"
                )
                reasons = "; ".join(spy_gate.get("reasons") or [])
                reason_suffix = f" {reasons}." if reasons else ""
                decision.rejection_reason = (
                    "Autonomous Mode strategy doesn't work well in current market regime."
                    f"{price_info}{reason_suffix} Terminating Autonomous Mode."
                )
                return self._emit(decision)

            _raw_mult = spy_gate.get("size_multiplier")
            size_multiplier = float(_raw_mult) if _raw_mult is not None else 1.0
            if self.config.apply_market_regime_size_multiplier and size_multiplier < 1.0:
                original_deployable_cash = decision.deployable_cash
                decision.deployable_cash = original_deployable_cash * size_multiplier
                decision.cash_snapshot["market_regime_adjustment"] = {
                    "original_deployable_cash": round(original_deployable_cash, 2),
                    "size_multiplier": size_multiplier,
                    "adjusted_deployable_cash": round(decision.deployable_cash, 2),
                    "classification": spy_gate.get("classification"),
                    "warnings": list(spy_gate.get("warnings") or []),
                }
                decision.notes.append(f"market regime size multiplier applied: {size_multiplier:.2f}x")
                if decision.deployable_cash < self.config.min_deployable_cash:
                    decision.status = DecisionStatus.NO_DEPLOYABLE_CASH
                    decision.rejection_reason = (
                        f"deployable_cash {decision.deployable_cash:.2f} < "
                        f"min {self.config.min_deployable_cash:.2f} after market regime adjustment"
                    )
                    return self._emit(decision)

        equity = float(account_summary.get("equity") or 0.0)
        if equity <= 0 and self.risk_manager is not None:
            equity = float(getattr(self.risk_manager, "current_equity", 0.0))

        candidates = self.scanner.scan(
            max_symbols=max_symbols,
            symbol_whitelist=self.config.symbol_whitelist,
            symbol_blacklist=self.config.symbol_blacklist,
        )
        ranked, rejected = self.ranker.rank_with_rejections(
            candidates,
            positions=positions,
            equity=equity,
            today=today,
            market_gate=decision.market_gate,
        )
        decision.shortlist = [rc.to_dict() for rc in ranked]
        decision.rejected_candidates = rejected

        if not ranked:
            decision.status = DecisionStatus.NO_CANDIDATE
            decision.rejection_reason = (
                f"no candidates matched strength>={self.config.min_signal_strength} "
                f"+ label={self.config.required_signal_label!r}"
            )
            return self._emit(decision)

        basket_plan = None
        if self.config.basket_enabled:
            basket_plan = self.basket_planner.plan(
                ranked,
                deployable_cash=decision.deployable_cash,
                equity=equity,
                option_hint_provider=self.option_hint_provider,
            )
            if basket_plan is not None:
                decision.basket_plan = basket_plan.to_dict()
                decision.selected_basket = list(decision.basket_plan["selected"])
                decision.trade_plans = list(decision.basket_plan["trade_plans"])
                decision.selected = decision.selected_basket[0] if decision.selected_basket else None
                decision.trade_plan = decision.trade_plans[0] if decision.trade_plans else None
                decision.notes.append(
                    f"basket mode — {len(decision.trade_plans)} planned legs"
                )
            else:
                decision.notes.append("basket mode enabled but no basket plan produced; falling back to top candidate")

        if basket_plan is None:
            best = ranked[0]
            decision.selected = best.to_dict()
            option_hint = None
            if self.option_hint_provider is not None:
                try:
                    option_hint = self.option_hint_provider(best.candidate)
                except Exception as exc:
                    logger.warning("option_hint_provider raised: %s", exc)
                    option_hint = None

            plan = self.planner.plan(
                best.candidate,
                deployable_cash=decision.deployable_cash,
                equity=equity,
                option_hint=option_hint,
                reasons=(planner_reasons := []),
            )
            if plan is None:
                decision.status = DecisionStatus.NO_TRADE_PLAN
                detail = "; ".join(planner_reasons) if planner_reasons else "insufficient cash or no allowed trade type"
                decision.rejection_reason = f"no tradable plan — {detail}"
                return self._emit(decision)
            decision.trade_plan = plan.to_dict()
            decision.trade_plans = [decision.trade_plan]

        risk_result = self._check_trade_plans_risk(decision.trade_plans, positions)
        if risk_result is not None:
            approved, reason = risk_result
            decision.risk_check = {"approved": approved, "reason": reason}
            if not approved:
                decision.status = DecisionStatus.RISK_REJECTED
                decision.rejection_reason = reason
                return self._emit(decision)

        if self.config.mode == AutonomousMode.RECOMMEND_ONLY:
            decision.status = DecisionStatus.RECOMMENDED
            decision.notes.append("recommend_only mode — no order placed")
            return self._emit(decision)

        if self.config.mode == AutonomousMode.PAPER_EXECUTE:
            if self.config.require_user_confirmation and not confirm:
                decision.status = DecisionStatus.CONFIRMATION_REQUIRED
                decision.rejection_reason = "paper_execute requires confirm=True"
                return self._emit(decision)
            if self._daily_limit_reached(decision.timestamp):
                decision.status = DecisionStatus.DAILY_LIMIT_REACHED
                decision.rejection_reason = (
                    f"max_trades_per_day ({self.config.max_trades_per_day}) already reached for today"
                )
                return self._emit(decision)
            if len(decision.trade_plans) > 1:
                return self._emit(self._execute_paper_basket(decision))
            return self._emit(self._execute_paper(decision, self._dict_to_plan(decision.trade_plan)))

        if self.config.mode == AutonomousMode.ASSISTED_LIVE:
            if not self.config.allow_live_execution:
                decision.status = DecisionStatus.LIVE_BLOCKED
                decision.rejection_reason = "assisted_live mode but allow_live_execution=False"
                return self._emit(decision)
            if not confirm:
                decision.status = DecisionStatus.CONFIRMATION_REQUIRED
                decision.rejection_reason = "assisted_live execution requires confirm=True"
                return self._emit(decision)
            if self._daily_limit_reached(decision.timestamp):
                decision.status = DecisionStatus.DAILY_LIMIT_REACHED
                decision.rejection_reason = (
                    f"max_trades_per_day ({self.config.max_trades_per_day}) already reached for today"
                )
                return self._emit(decision)
            decision.status = DecisionStatus.LIVE_PLAN_READY
            decision.notes.append("live_plan_ready — AutonomousLiveRunner must submit via OrderExecutor")
            return self._emit(decision)

        decision.status = DecisionStatus.LIVE_BLOCKED
        decision.rejection_reason = f"unknown mode {self.config.mode!r}"
        return self._emit(decision)

    def _check_trade_plans_risk(
        self,
        trade_plans: List[Dict[str, Any]],
        positions: Dict[str, Dict[str, Any]],
    ) -> Optional[tuple[bool, str]]:
        if self.risk_manager is None:
            return None
        for plan in trade_plans:
            if plan.get("trade_type") != TradeType.BUY_SHARES.value:
                continue
            quantity = int(plan.get("quantity") or 0)
            if quantity <= 0:
                continue
            try:
                approved, reason = self.risk_manager.check_trade_risk(
                    symbol=plan.get("symbol"),
                    side="LONG",
                    quantity=quantity,
                    price=float(plan.get("limit_price") or 0.0),
                    positions=self._risk_positions(positions),
                )
            except Exception:
                logger.exception("risk_manager.check_trade_risk raised")
                return False, "risk_manager raised an exception"
            if not approved:
                return False, f"{plan.get('symbol')}: {reason}"
        return True, "all planned trades approved"

    def _execute_paper(self, decision: AutonomousDecision, plan: TradePlan) -> AutonomousDecision:
        if self.paper_adapter is None:
            decision.status = DecisionStatus.EXECUTION_FAILED
            decision.rejection_reason = "no paper_adapter configured"
            return decision
        if plan.trade_type != TradeType.BUY_SHARES:
            decision.status = DecisionStatus.EXECUTION_FAILED
            decision.rejection_reason = f"paper execution for {plan.trade_type.value} not implemented in MVP"
            return decision
        try:
            order_id = self.paper_adapter.buy(
                symbol=plan.symbol,
                quantity=plan.quantity,
                order_type="LIMIT",
                limit_price=plan.limit_price,
            )
        except Exception:
            logger.exception("paper_adapter.buy raised")
            decision.status = DecisionStatus.EXECUTION_FAILED
            decision.rejection_reason = "paper adapter raised an exception"
            return decision
        decision.status = DecisionStatus.PAPER_EXECUTED
        decision.order_id = int(order_id) if order_id is not None else None
        decision.order_ids = [decision.order_id] if decision.order_id is not None else []
        decision.notes.append("order placed via paper adapter")
        return decision

    def _execute_paper_basket(self, decision: AutonomousDecision) -> AutonomousDecision:
        if self.paper_adapter is None:
            decision.status = DecisionStatus.EXECUTION_FAILED
            decision.rejection_reason = "no paper_adapter configured"
            return decision
        order_ids: List[int] = []
        executed_symbols: List[str] = []
        for plan_dict in decision.trade_plans:
            plan = self._dict_to_plan(plan_dict)
            if plan.trade_type != TradeType.BUY_SHARES:
                decision.status = DecisionStatus.EXECUTION_FAILED
                decision.rejection_reason = f"paper basket execution for {plan.trade_type.value} not implemented"
                return decision
            try:
                order_id = self.paper_adapter.buy(
                    symbol=plan.symbol,
                    quantity=plan.quantity,
                    order_type="LIMIT",
                    limit_price=plan.limit_price,
                )
            except Exception:
                logger.exception("paper_adapter.buy raised for basket leg %s", plan.symbol)
                decision.status = DecisionStatus.EXECUTION_FAILED
                decision.rejection_reason = f"paper adapter raised for basket leg {plan.symbol}"
                return decision
            if order_id is not None:
                order_ids.append(int(order_id))
            executed_symbols.append(plan.symbol)
        decision.status = DecisionStatus.PAPER_EXECUTED
        decision.order_ids = order_ids
        decision.order_id = order_ids[0] if order_ids else None
        decision.notes.append(
            f"paper basket executed: {len(executed_symbols)} legs ({', '.join(executed_symbols)})"
        )
        return decision

    @staticmethod
    def _dict_to_plan(plan_dict: Dict[str, Any]) -> TradePlan:
        return TradePlan(
            symbol=str(plan_dict.get("symbol") or ""),
            trade_type=TradeType(plan_dict.get("trade_type")),
            action=str(plan_dict.get("action") or "BUY"),
            quantity=int(plan_dict.get("quantity") or 0),
            limit_price=float(plan_dict.get("limit_price") or 0.0),
            target_price=plan_dict.get("target_price"),
            stop_price=plan_dict.get("stop_price"),
            required_cash=float(plan_dict.get("required_cash") or 0.0),
            target_mode=str(plan_dict.get("target_mode") or ""),
            sizing=dict(plan_dict.get("sizing") or {}),
        )

    @staticmethod
    def _risk_positions(positions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        class _P:
            __slots__ = ("symbol", "quantity", "side", "market_value")

            def __init__(self, symbol, quantity, side, market_value):
                self.symbol = symbol
                self.quantity = quantity
                self.side = side
                self.market_value = market_value

        out: Dict[str, Any] = {}
        for symbol, pos in positions.items():
            out[symbol] = _P(
                symbol=symbol,
                quantity=float(pos.get("quantity", 0) or 0),
                side=str(pos.get("side", "LONG") or "LONG").upper(),
                market_value=float(pos.get("market_value", 0) or 0),
            )
        return out
