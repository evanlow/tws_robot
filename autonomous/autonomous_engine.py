"""Autonomous trading engine.

Top-level orchestrator that combines:

* :class:`data.cash_availability.CashAvailabilityAnalyzer` (deployable cash)
* :class:`autonomous.candidate_scanner.CandidateScanner` (S&P 500 universe)
* :class:`autonomous.candidate_ranker.CandidateRanker` (Strong/Rebound filter)
* :class:`autonomous.trade_planner.TradePlanner` (buy-shares / short-put plan)
* Optional :class:`risk.risk_manager.RiskManager` (final risk-check gate)
* Optional paper / live execution adapters

Default behaviour is **recommendation only**: the engine returns a
structured :class:`AutonomousDecision` and never places an order.  Paper
execution requires ``mode=PAPER_EXECUTE`` and a paper adapter; live
execution additionally requires ``allow_live_execution=True`` **and** an
explicit ``confirm=True`` argument to :meth:`run_once`.

Safety invariants:

* EMERGENCY_STOP file (or RiskManager.emergency_stop_active) blocks
  every execution path before any order is placed.
* Cash availability is always computed via
  ``CashAvailabilityAnalyzer.analyze`` — raw broker cash is never used.
* Every run writes one JSONL audit-log entry, including rejected runs.
* Every run also writes one schema-versioned evidence record for future
  edge estimation, basket construction, and sizing intelligence.
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
from autonomous.candidate_ranker import CandidateRanker
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.evidence_store import TradeEvidenceStore
from autonomous.market_regime import evaluate_market_regime
from autonomous.trade_planner import OptionChainHint, TradePlan, TradePlanner, TradeType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision data class
# ---------------------------------------------------------------------------

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
    risk_check: Optional[Dict[str, Any]] = None
    order_id: Optional[int] = None
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
            "risk_check": self.risk_check,
            "order_id": self.order_id,
            "notes": list(self.notes),
            "market_gate": self.market_gate,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# Public type alias: a callable that returns an :class:`OptionChainHint`
# (or None) for a given candidate.  Keeping this as a callable means the
# engine doesn't need to know how the option chain is fetched.
OptionHintProvider = Callable[[CandidateSignal], Optional[OptionChainHint]]
SpyPriceProvider = Callable[[], Optional[Dict[str, Any]]]


class AutonomousTradingEngine:
    """Top-level orchestrator for the guarded autonomous trading flow.

    Parameters
    ----------
    config:
        Safety configuration; defaults to :class:`AutonomousTradingConfig`
        defaults (recommend-only, live disabled).
    scanner:
        :class:`CandidateScanner` instance configured with a signal
        provider.  Required.
    cash_analyzer:
        :class:`data.cash_availability.CashAvailabilityAnalyzer`.  Required;
        the engine must never use raw broker cash directly.
    account_provider:
        Callable returning a dict shaped like
        ``ServiceManager.get_account_summary()``.  Required.
    positions_provider:
        Callable returning a dict shaped like
        ``ServiceManager.get_positions()``.  Required.
    orders_provider:
        Optional callable returning ``ServiceManager._orders`` (list).
    risk_manager:
        Optional :class:`risk.risk_manager.RiskManager`; when provided the
        engine consults ``check_trade_risk`` before executing.
    paper_adapter:
        Optional object exposing ``buy()`` / ``sell()`` methods compatible
        with :class:`execution.paper_adapter.PaperTradingAdapter`.  Only
        used when ``mode=PAPER_EXECUTE``.
    option_hint_provider:
        Optional callable returning an :class:`OptionChainHint` for the
        selected candidate.  When absent, the planner falls back to
        ``BUY_SHARES`` plans.
    audit_logger:
        Optional :class:`AuditLogger`.  Defaults to one rooted at
        ``config.audit_log_dir``.
    evidence_store:
        Optional :class:`TradeEvidenceStore`.  Defaults to one rooted at
        ``config.audit_log_dir`` so audit and evidence files rotate together.
    """

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
        self.audit = audit_logger or AuditLogger(self.config.audit_log_dir)
        self.evidence = evidence_store or TradeEvidenceStore(self.config.audit_log_dir)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emergency_stop_active(self) -> bool:
        """File-based emergency stop or RiskManager flag triggers a halt."""
        try:
            if Path(self.config.emergency_stop_file).exists():
                return True
        except OSError:  # pragma: no cover - defensive
            pass
        if self.risk_manager is not None:
            if getattr(self.risk_manager, "emergency_stop_active", False):
                return True
        return False

    def _emit(self, decision: AutonomousDecision) -> AutonomousDecision:
        """Write audit/evidence log entries and return the decision unchanged."""
        record = {
            "engine": "AutonomousTradingEngine",
            "config": self.config.to_dict(),
            "decision": decision.to_dict(),
        }
        self.audit.log_decision(record, when=decision.timestamp)
        try:
            self.evidence.log_decision(record, when=decision.timestamp)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to write autonomous evidence record")
        return decision

    def _daily_limit_reached(self, when: datetime) -> bool:
        """True when today's audit log already contains ``max_trades_per_day``
        executed decisions.

        The audit log is used as the persisted source of truth so that a
        process restart cannot reset the daily counter and allow more
        trades than the operator configured.
        """
        limit = self.config.max_trades_per_day
        if limit <= 0:
            # ``0`` means "no execution allowed".  Treat as reached.
            return True
        executed = self.audit.count_executions_on(when=when)
        return executed >= limit

    def _check_spy_gate(self) -> Optional[Dict[str, Any]]:
        """Return SPY/VIX market-regime payload when a provider is configured.

        The provider historically returned only ``{"open": ..., "current": ...}``
        for SPY.  It may now also return VIX fields (``vix_open`` and
        ``vix_current``).  The evaluator preserves the legacy SPY fields while
        adding ``trade_allowed`` and ``size_multiplier`` for the VIX overlay.
        """

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

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_once(
        self,
        confirm: bool = False,
        today: Optional[date] = None,
        max_symbols: Optional[int] = None,
    ) -> AutonomousDecision:
        """Run the full guarded scan / plan / (optional) execute cycle.

        Parameters
        ----------
        confirm:
            Caller-supplied confirmation flag.  Required for live execution
            (in addition to ``config.allow_live_execution=True``) and, when
            ``config.require_user_confirmation`` is True, also required
            for paper execution.
        today:
            Override "today" used for earnings-window filtering (test hook).
        max_symbols:
            Optional cap on how many universe symbols to scan.
        """
        decision = AutonomousDecision(
            status=DecisionStatus.NO_CANDIDATE,
            mode=self.config.mode,
        )

        # 1. Emergency stop ------------------------------------------------
        if self._emergency_stop_active():
            decision.status = DecisionStatus.EMERGENCY_STOP
            decision.rejection_reason = (
                "EMERGENCY_STOP active (file or RiskManager flag)"
            )
            return self._emit(decision)

        # 2-3. Account snapshot + cash availability ------------------------
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

        # 4. Deployable cash gate -----------------------------------------
        if decision.deployable_cash < self.config.min_deployable_cash:
            decision.status = DecisionStatus.NO_DEPLOYABLE_CASH
            decision.rejection_reason = (
                f"deployable_cash {decision.deployable_cash:.2f} < "
                f"min {self.config.min_deployable_cash:.2f}"
            )
            return self._emit(decision)

        # 5. SPY + VIX market-regime gate ---------------------------------
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
                if open_p > 0 or curr_p > 0:
                    price_info = f" (SPY Open: ${open_p:.2f}, Current: ${curr_p:.2f})"
                else:
                    price_info = " (SPY price unavailable)"
                reasons = "; ".join(spy_gate.get("reasons") or [])
                reason_suffix = f" {reasons}." if reasons else ""
                decision.rejection_reason = (
                    "Autonomous Mode strategy doesn't work well in current market regime."
                    f"{price_info}{reason_suffix} Terminating Autonomous Mode."
                )
                return self._emit(decision)

            _raw_mult = spy_gate.get("size_multiplier")
            size_multiplier = float(_raw_mult) if _raw_mult is not None else 1.0
            if (
                self.config.apply_market_regime_size_multiplier
                and size_multiplier < 1.0
            ):
                original_deployable_cash = decision.deployable_cash
                decision.deployable_cash = original_deployable_cash * size_multiplier
                decision.cash_snapshot["market_regime_adjustment"] = {
                    "original_deployable_cash": round(original_deployable_cash, 2),
                    "size_multiplier": size_multiplier,
                    "adjusted_deployable_cash": round(decision.deployable_cash, 2),
                    "classification": spy_gate.get("classification"),
                    "warnings": list(spy_gate.get("warnings") or []),
                }
                decision.notes.append(
                    "market regime size multiplier applied: "
                    f"{size_multiplier:.2f}x"
                )
                if decision.deployable_cash < self.config.min_deployable_cash:
                    decision.status = DecisionStatus.NO_DEPLOYABLE_CASH
                    decision.rejection_reason = (
                        f"deployable_cash {decision.deployable_cash:.2f} < "
                        f"min {self.config.min_deployable_cash:.2f} after "
                        "market regime adjustment"
                    )
                    return self._emit(decision)

        # 6-8. Scan + filter + rank ---------------------------------------
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

        best = ranked[0]
        decision.selected = best.to_dict()

        # 8. Trade plan ---------------------------------------------------
        option_hint = None
        if self.option_hint_provider is not None:
            try:
                option_hint = self.option_hint_provider(best.candidate)
            except Exception as exc:  # pragma: no cover - defensive
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
            detail = "; ".join(planner_reasons) if planner_reasons else (
                "insufficient cash or no allowed trade type"
            )
            decision.rejection_reason = f"no tradable plan — {detail}"
            return self._emit(decision)
        decision.trade_plan = plan.to_dict()

        # 9. Risk-manager check (best-effort) -----------------------------
        if (
            self.risk_manager is not None
            and plan.trade_type == TradeType.BUY_SHARES
            and plan.quantity > 0
        ):
            try:
                approved, reason = self.risk_manager.check_trade_risk(
                    symbol=plan.symbol,
                    side="LONG",
                    quantity=plan.quantity,
                    price=plan.limit_price,
                    positions=self._risk_positions(positions),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("risk_manager.check_trade_risk raised")
                approved, reason = False, "risk_manager raised an exception"
            decision.risk_check = {"approved": approved, "reason": reason}
            if not approved:
                decision.status = DecisionStatus.RISK_REJECTED
                decision.rejection_reason = reason
                return self._emit(decision)

        # 10. Recommend-only ----------------------------------------------
        if self.config.mode == AutonomousMode.RECOMMEND_ONLY:
            decision.status = DecisionStatus.RECOMMENDED
            decision.notes.append("recommend_only mode — no order placed")
            return self._emit(decision)

        # 11. Paper-execute -----------------------------------------------
        if self.config.mode == AutonomousMode.PAPER_EXECUTE:
            if self.config.require_user_confirmation and not confirm:
                decision.status = DecisionStatus.CONFIRMATION_REQUIRED
                decision.rejection_reason = (
                    "paper_execute requires confirm=True"
                )
                return self._emit(decision)
            if self._daily_limit_reached(decision.timestamp):
                decision.status = DecisionStatus.DAILY_LIMIT_REACHED
                decision.rejection_reason = (
                    f"max_trades_per_day ({self.config.max_trades_per_day}) "
                    "already reached for today"
                )
                return self._emit(decision)
            return self._emit(self._execute_paper(decision, plan))

        # 12. Assisted live -----------------------------------------------
        if self.config.mode == AutonomousMode.ASSISTED_LIVE:
            if not self.config.allow_live_execution:
                decision.status = DecisionStatus.LIVE_BLOCKED
                decision.rejection_reason = (
                    "assisted_live mode but allow_live_execution=False"
                )
                return self._emit(decision)
            if not confirm:
                decision.status = DecisionStatus.CONFIRMATION_REQUIRED
                decision.rejection_reason = (
                    "assisted_live execution requires confirm=True"
                )
                return self._emit(decision)
            if self._daily_limit_reached(decision.timestamp):
                decision.status = DecisionStatus.DAILY_LIMIT_REACHED
                decision.rejection_reason = (
                    f"max_trades_per_day ({self.config.max_trades_per_day}) "
                    "already reached for today"
                )
                return self._emit(decision)
            # Trade plan is ready; signal the runner to execute via OrderExecutor.
            # LIVE_PLAN_READY means all engine-level checks have passed and the
            # trade plan is safe to submit through the wired live executor.
            decision.status = DecisionStatus.LIVE_PLAN_READY
            decision.notes.append(
                "live_plan_ready — AutonomousLiveRunner must submit via OrderExecutor"
            )
            return self._emit(decision)

        # Unknown mode — refuse to act.
        decision.status = DecisionStatus.LIVE_BLOCKED
        decision.rejection_reason = f"unknown mode {self.config.mode!r}"
        return self._emit(decision)

    # ------------------------------------------------------------------
    # Internal: paper execution
    # ------------------------------------------------------------------

    def _execute_paper(
        self,
        decision: AutonomousDecision,
        plan: TradePlan,
    ) -> AutonomousDecision:
        if self.paper_adapter is None:
            decision.status = DecisionStatus.EXECUTION_FAILED
            decision.rejection_reason = "no paper_adapter configured"
            return decision

        # Only BUY_SHARES is supported on the paper path in this MVP —
        # option order plumbing through PaperTradingAdapter is out of
        # scope for this issue.
        if plan.trade_type != TradeType.BUY_SHARES:
            decision.status = DecisionStatus.EXECUTION_FAILED
            decision.rejection_reason = (
                f"paper execution for {plan.trade_type.value} not "
                "implemented in MVP"
            )
            return decision

        try:
            # NOTE: use ``"LIMIT"`` (not ``"LMT"``).  ``PaperTradingAdapter``
            # only populates ``order.lmtPrice`` when ``order_type == "LIMIT"``
            # (see ``execution/paper_adapter.py``); passing ``"LMT"`` would
            # silently drop the limit price and emit a market-style order,
            # which violates ``use_limit_orders_only``.
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
        decision.notes.append("order placed via paper adapter")
        return decision

    # ------------------------------------------------------------------
    # Convert ServiceManager positions → RiskManager positions
    # ------------------------------------------------------------------

    @staticmethod
    def _risk_positions(
        positions: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Adapt ServiceManager positions to the shape RiskManager expects.

        RiskManager.check_trade_risk reads ``.market_value``, ``.side`` and
        ``.quantity`` off Position objects; we provide a lightweight
        namespace-like wrapper rather than importing the Position class
        (keeps the engine decoupled from risk internals).
        """

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
