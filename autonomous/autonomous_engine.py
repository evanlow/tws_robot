"""Autonomous trading engine.

Top-level orchestrator that combines scanner, ranking, planning, risk gates,
market-regime gates, evidence logging, and optional paper/live execution.
"""

from __future__ import annotations

import logging
import time
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
from autonomous.edge_estimator import EdgeEstimate
from autonomous.evidence_calibrator import SetupEvidenceSummary
from autonomous.evidence_store import TradeEvidenceStore
from autonomous.market_data_provider import MarketDataProvider
from autonomous.market_regime import evaluate_market_regime
from autonomous.opening_range_signal_provider import STRATEGY_OPENING_RANGE_BREAKOUT
from autonomous.profitability_gate import ProfitabilityDecision, ProfitabilityGate
from autonomous.risk_lifecycle import LossLimitGuard
from autonomous.trade_planner import OptionChainHint, TradePlan, TradePlanner, TradeType

logger = logging.getLogger(__name__)


class DecisionStatus(str, Enum):
    EMERGENCY_STOP = "emergency_stop"
    NO_DEPLOYABLE_CASH = "no_deployable_cash"
    NO_CANDIDATE = "no_candidate"
    NO_TRADE_PLAN = "no_trade_plan"
    RISK_REJECTED = "risk_rejected"
    UNECONOMIC_AFTER_COMMISSION = "uneconomic_after_commission"
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
    risk_lifecycle: Optional[Dict[str, Any]] = None
    profitability: Optional[Dict[str, Any]] = None
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
            "risk_lifecycle": self.risk_lifecycle,
            "profitability": self.profitability,
            "order_id": self.order_id,
            "order_ids": list(self.order_ids),
            "notes": list(self.notes),
            "market_gate": self.market_gate,
        }


OptionHintProvider = Callable[[CandidateSignal], Optional[OptionChainHint]]
SpyPriceProvider = Callable[[], Optional[Dict[str, Any]]]
CashFxRateProvider = Callable[[], Optional[float]]
SetupEvidenceProvider = Callable[
    [CandidateSignal, Dict[str, Any], EdgeEstimate],
    Optional[SetupEvidenceSummary],
]


class AutonomousTradingEngine:
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
        cash_fx_rate_provider: Optional[CashFxRateProvider] = None,
        setup_evidence_provider: Optional[SetupEvidenceProvider] = None,
        market_data_provider: Optional[MarketDataProvider] = None,
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
        self.cash_fx_rate_provider = cash_fx_rate_provider
        self.market_data_provider = market_data_provider
        self.ranker = CandidateRanker(
            self.config,
            setup_evidence_provider=setup_evidence_provider,
        )
        self.planner = TradePlanner(self.config)
        self.basket_planner = BasketPlanner(self.config)
        self.profitability_gate = ProfitabilityGate(
            enabled=self.config.commission_aware_sizing_enabled,
            estimated_commission_per_order=self.config.estimated_commission_per_order,
            min_net_profit_usd=self.config.min_net_profit_usd,
            min_net_profit_pct_of_trade=self.config.min_net_profit_pct_of_trade,
        )
        self.audit = audit_logger or AuditLogger(self.config.audit_log_dir)
        self.evidence = evidence_store or TradeEvidenceStore(self.config.audit_log_dir)
        self.loss_limit_guard = LossLimitGuard(
            enabled=self.config.risk_lifecycle_guard_enabled,
            max_daily_loss_r=self.config.max_daily_loss_r,
            max_weekly_loss_r=self.config.max_weekly_loss_r,
            max_monthly_loss_r=self.config.max_monthly_loss_r,
            max_consecutive_losses=self.config.max_consecutive_losses,
            max_drawdown_r=self.config.max_strategy_drawdown_r,
        )

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

    def _check_risk_lifecycle(self, decision: AutonomousDecision) -> bool:
        if not self.loss_limit_guard.enabled:
            decision.risk_lifecycle = {"allowed": True, "reason": "risk lifecycle guard disabled"}
            return True
        try:
            records = self.evidence.recent_outcomes(self.config.risk_lifecycle_recent_record_limit)
            lifecycle = self.loss_limit_guard.evaluate(records, now=decision.timestamp)
        except Exception:
            logger.exception("risk lifecycle guard raised")
            decision.risk_lifecycle = {
                "allowed": False,
                "reason": "risk lifecycle guard raised an exception",
            }
            decision.status = DecisionStatus.RISK_REJECTED
            decision.rejection_reason = "risk lifecycle guard raised an exception"
            return False
        decision.risk_lifecycle = lifecycle.to_dict()
        if not lifecycle.allowed:
            decision.status = DecisionStatus.RISK_REJECTED
            decision.rejection_reason = lifecycle.reason
            return False
        return True

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

    def _apply_live_market_data(self, candidates: List[CandidateSignal]) -> None:
        if self.config.mode != AutonomousMode.ASSISTED_LIVE:
            return
        provider = self.market_data_provider
        if provider is None:
            for candidate in candidates:
                candidate.extras.setdefault("market_data_status", "not_configured")
                candidate.extras.setdefault("market_data_source", "UNKNOWN")
            return

        symbols = [candidate.symbol for candidate in candidates]
        try:
            provider.subscribe(symbols)
        except Exception:
            logger.exception("live market-data provider subscribe failed")
            for candidate in candidates:
                candidate.extras["market_data_status"] = "provider_error"
                candidate.extras["market_data_source"] = "UNKNOWN"
                candidate.extras["market_data_error_message"] = "provider subscribe failed"
            return

        for candidate in candidates:
            quote = None
            for _ in range(10):
                try:
                    quote = provider.latest_quote(candidate.symbol)
                except Exception:
                    logger.exception(
                        "live market-data provider latest_quote failed for %s",
                        candidate.symbol,
                    )
                    candidate.extras["market_data_status"] = "provider_error"
                    candidate.extras["market_data_source"] = "UNKNOWN"
                    candidate.extras["market_data_error_message"] = "latest_quote failed"
                    quote = None
                    break
                if quote is not None:
                    quote_data = quote.to_dict()
                    if (
                        quote_data.get("bid") is not None
                        and quote_data.get("ask") is not None
                        and quote_data.get("quote_timestamp") is not None
                        and str(quote_data.get("market_data_type") or "").upper() == "LIVE"
                    ):
                        break
                time.sleep(0.1)
            if quote is None:
                candidate.extras["market_data_status"] = "missing_quote"
                candidate.extras.setdefault("market_data_source", "IBKR")
                candidate.extras["market_data_error_message"] = "no IBKR live quote available"
                continue
            candidate.extras.update(quote.to_candidate_extras())
            price = _execution_price_from_quote(quote.to_dict())
            if price is not None:
                candidate.last_price = price

    def run_once(
        self,
        confirm: bool = False,
        today: Optional[date] = None,
        max_symbols: Optional[int] = None,
    ) -> AutonomousDecision:
        decision = AutonomousDecision(status=DecisionStatus.NO_CANDIDATE, mode=self.config.mode)

        if self._emergency_stop_active():
            decision.status = DecisionStatus.EMERGENCY_STOP
            decision.rejection_reason = "EMERGENCY_STOP active (file or RiskManager flag)"
            return self._emit(decision)

        if not self._check_risk_lifecycle(decision):
            return self._emit(decision)

        account_summary = self._account_provider() or {}
        positions = self._positions_provider() or {}
        orders = self._orders_provider() or []
        usd_sgd_rate = None
        if self.cash_fx_rate_provider is not None:
            try:
                usd_sgd_rate = self.cash_fx_rate_provider()
            except Exception:
                logger.exception("cash FX rate provider raised")

        cash_result = self.cash_analyzer.analyze(
            account_summary=account_summary,
            positions=positions,
            orders=orders,
            usd_sgd_rate=usd_sgd_rate,
        )
        decision.deployable_cash = float(cash_result.deployable_cash)
        decision.cash_snapshot = cash_result.to_dict()

        if decision.deployable_cash < self.config.min_deployable_cash:
            decision.status = DecisionStatus.NO_DEPLOYABLE_CASH
            decision.rejection_reason = (
                f"deployable_cash {decision.deployable_cash:.2f} < min {self.config.min_deployable_cash:.2f}"
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
                source = str(spy_gate.get("source") or "").strip()
                source_info = f", Source: {source}" if source else ""
                price_info = (
                    f" (SPY Open: ${open_p:.2f}, Current: ${curr_p:.2f}{source_info})"
                    if open_p > 0 or curr_p > 0
                    else f" (SPY price unavailable{source_info})"
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
                        f"deployable_cash {decision.deployable_cash:.2f} < min {self.config.min_deployable_cash:.2f} after market regime adjustment"
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
        if ranked and self.config.mode == AutonomousMode.ASSISTED_LIVE:
            # Keep IBKR line usage small in assisted-live mode: screening can
            # be broad, but live quote validation should focus on symbols that
            # are actually eligible for immediate planning/execution.
            live_quote_limit = 10
            live_quote_targets = [
                rc.candidate
                for rc in ranked[
                    : (
                        self.config.basket_max_size
                        if self.config.basket_enabled
                        else live_quote_limit
                    )
                ]
            ]
            self._apply_live_market_data(live_quote_targets)
        decision.shortlist = [rc.to_dict() for rc in ranked]
        decision.rejected_candidates = rejected

        if not ranked:
            decision.status = DecisionStatus.NO_CANDIDATE
            decision.rejection_reason = (
                f"no candidates matched strength>={self.config.min_signal_strength} + label={self.config.required_signal_label!r}"
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
                decision.notes.append(f"basket mode — {len(decision.trade_plans)} planned legs")
            else:
                decision.notes.append("basket mode enabled but no basket plan produced; falling back to top candidate")

        if basket_plan is None:
            planner_reasons_all: list[str] = []
            plan = None
            selected_candidate = None
            for ranked_candidate in ranked:
                option_hint = None
                if self.option_hint_provider is not None:
                    try:
                        option_hint = self.option_hint_provider(ranked_candidate.candidate)
                    except Exception as exc:
                        logger.warning("option_hint_provider raised: %s", exc)
                        option_hint = None

                planner_reasons: list[str] = []
                candidate_plan = self.planner.plan(
                    ranked_candidate.candidate,
                    deployable_cash=decision.deployable_cash,
                    equity=equity,
                    option_hint=option_hint,
                    reasons=planner_reasons,
                )
                if candidate_plan is not None:
                    plan = candidate_plan
                    selected_candidate = ranked_candidate
                    break
                if planner_reasons:
                    planner_reasons_all.extend(planner_reasons[:3])

            if plan is None or selected_candidate is None:
                decision.status = DecisionStatus.NO_TRADE_PLAN
                detail = "; ".join(planner_reasons_all) if planner_reasons_all else "insufficient cash or no allowed trade type"
                decision.rejection_reason = f"no tradable plan — {detail}"
                return self._emit(decision)
            decision.selected = selected_candidate.to_dict()
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

        profit_result = self._check_profitability(decision.trade_plans)
        if profit_result is not None:
            allowed, reason, payload = profit_result
            decision.profitability = payload
            if not allowed:
                decision.status = DecisionStatus.UNECONOMIC_AFTER_COMMISSION
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
                decision.rejection_reason = f"max_trades_per_day ({self.config.max_trades_per_day}) already reached for today"
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
                decision.rejection_reason = f"max_trades_per_day ({self.config.max_trades_per_day}) already reached for today"
                return self._emit(decision)
            decision.status = DecisionStatus.LIVE_PLAN_READY
            decision.notes.append("live_plan_ready — AutonomousLiveRunner must submit via OrderExecutor")
            return self._emit(decision)

        decision.status = DecisionStatus.LIVE_BLOCKED
        decision.rejection_reason = f"unknown mode {self.config.mode!r}"
        return self._emit(decision)

    def _check_profitability(
        self,
        trade_plans: List[Dict[str, Any]],
    ) -> Optional[tuple[bool, str, Dict[str, Any]]]:
        """Reject share-buy plans whose expected net profit after estimated
        round-trip commission falls below the configured minimum.

        Returns ``None`` when the gate is disabled (so it leaves no trace on
        the decision), otherwise a ``(allowed, reason, payload)`` tuple where
        ``payload`` is recorded on the decision for the API, dashboard, and
        audit log.  The first failing share-buy leg short-circuits.
        """

        if not self.profitability_gate.enabled:
            return None

        evaluations: List[Dict[str, Any]] = []
        first_rejection: Optional[ProfitabilityDecision] = None
        for plan in trade_plans:
            if plan.get("trade_type") != TradeType.BUY_SHARES.value:
                continue
            decision = self.profitability_gate.evaluate_buy_shares(
                symbol=str(plan.get("symbol") or ""),
                quantity=int(plan.get("quantity") or 0),
                entry_price=float(plan.get("limit_price") or 0.0),
                target_price=plan.get("target_price"),
            )
            evaluations.append(decision.to_dict())
            if not decision.allowed and first_rejection is None:
                first_rejection = decision

        if not evaluations:
            return None

        payload: Dict[str, Any] = {
            "enabled": True,
            "approved": first_rejection is None,
            "evaluations": evaluations,
        }
        if first_rejection is None:
            payload["reason"] = "all planned trades clear minimum net profit after commissions"
            return True, payload["reason"], payload
        payload["reason"] = first_rejection.reason
        return False, first_rejection.reason, payload

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
        if plan.strategy == STRATEGY_OPENING_RANGE_BREAKOUT:
            decision.status = DecisionStatus.EXECUTION_FAILED
            decision.rejection_reason = (
                "ORB paper execution must use ORBProposal/ORBPaperExecutor protected path"
            )
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
            if plan.strategy == STRATEGY_OPENING_RANGE_BREAKOUT:
                decision.status = DecisionStatus.EXECUTION_FAILED
                decision.rejection_reason = (
                    "ORB paper execution must use ORBProposal/ORBPaperExecutor protected path"
                )
                return decision
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
        decision.notes.append(f"paper basket executed: {len(executed_symbols)} legs ({', '.join(executed_symbols)})")
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
            market_data_health=dict(plan_dict.get("market_data_health") or {}),
            execution_quality=dict(plan_dict.get("execution_quality") or {}),
            strategy=str(plan_dict.get("strategy") or ""),
            extras=dict(plan_dict.get("extras") or {}),
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


def _execution_price_from_quote(payload: Dict[str, Any]) -> Optional[float]:
    last = _positive_float(payload.get("last"))
    if last is not None:
        return last
    bid = _positive_float(payload.get("bid"))
    ask = _positive_float(payload.get("ask"))
    if bid is not None and ask is not None and ask >= bid:
        return round((bid + ask) / 2.0, 4)
    return bid or ask


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None
