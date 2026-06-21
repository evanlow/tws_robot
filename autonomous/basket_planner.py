"""Basket planning for autonomous trading.

A basket plan converts the ranked candidate shortlist into multiple individual
``TradePlan`` objects while respecting total basket exposure, per-position
exposure, and same-sector concentration caps.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.basket_risk_allocator import BasketRiskAllocation, BasketRiskAllocator
from autonomous.candidate_ranker import RankedCandidate
from autonomous.trade_planner import TradePlan, TradePlanner


@dataclass
class BasketPlan:
    """A collection of individual trade plans produced for one engine run."""

    trade_plans: List[TradePlan]
    selected: List[Dict[str, Any]]
    rejected: List[Dict[str, Any]]
    total_required_cash: float
    max_basket_value: float
    risk_allocation: Optional[BasketRiskAllocation] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_plans": [plan.to_dict() for plan in self.trade_plans],
            "selected": list(self.selected),
            "rejected": list(self.rejected),
            "total_required_cash": round(self.total_required_cash, 2),
            "max_basket_value": round(self.max_basket_value, 2),
            "risk_allocation": self.risk_allocation.to_dict() if self.risk_allocation else None,
        }


class BasketPlanner:
    """Build a capped top-N basket from ranked autonomous candidates."""

    def __init__(self, config: AutonomousTradingConfig) -> None:
        self.config = config
        self.risk_allocator = BasketRiskAllocator(
            enabled=config.basket_risk_allocator_enabled,
            max_basket_risk_equity_pct=config.max_basket_risk_equity_pct,
            allocation_mode=config.basket_risk_allocation_mode,
            min_leg_risk_dollars=config.basket_min_leg_risk_dollars,
        )

    def plan(
        self,
        ranked: List[RankedCandidate],
        *,
        deployable_cash: float,
        equity: float,
        option_hint_provider=None,
    ) -> Optional[BasketPlan]:
        if not self.config.basket_enabled:
            return None
        if not ranked:
            return None

        max_basket_value = deployable_cash * self.config.basket_total_deployable_cash_pct
        if max_basket_value <= 0:
            return None

        # Use a cloned config for each leg so existing TradePlanner sizing logic
        # applies the single-position basket cap without widening the caller's
        # global config.
        leg_config = replace(
            self.config,
            max_position_deployable_cash_pct=self.config.basket_single_position_deployable_cash_pct,
            max_position_equity_pct=(
                self.config.max_position_equity_pct
                if self.config.max_position_equity_pct is not None
                else self.config.basket_single_position_deployable_cash_pct
            ),
        )
        planner = TradePlanner(leg_config)

        plans: List[TradePlan] = []
        selected: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        sector_counts: Dict[str, int] = {}
        total_required_cash = 0.0

        for ranked_candidate in ranked:
            if len(plans) >= self.config.basket_max_size:
                break

            candidate = ranked_candidate.candidate
            sector = candidate.sector or "UNKNOWN"
            if sector_counts.get(sector, 0) >= self.config.basket_max_same_sector_positions:
                rejected.append({
                    "symbol": candidate.symbol,
                    "reason": f"basket sector cap reached for {sector}",
                })
                continue

            option_hint = None
            if option_hint_provider is not None:
                try:
                    option_hint = option_hint_provider(candidate)
                except Exception:
                    option_hint = None

            reasons: List[str] = []
            plan = planner.plan(
                candidate,
                deployable_cash=deployable_cash,
                equity=equity,
                option_hint=option_hint,
                reasons=reasons,
            )
            if plan is None:
                rejected.append({
                    "symbol": candidate.symbol,
                    "reason": "; ".join(reasons) or "no tradable basket leg",
                })
                continue

            if total_required_cash + plan.required_cash > max_basket_value:
                rejected.append({
                    "symbol": candidate.symbol,
                    "reason": (
                        f"basket cash cap exceeded: current {total_required_cash:.2f} + "
                        f"leg {plan.required_cash:.2f} > max {max_basket_value:.2f}"
                    ),
                })
                continue

            plans.append(plan)
            selected.append(ranked_candidate.to_dict())
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            total_required_cash += float(plan.required_cash or 0.0)

        if not plans:
            return None

        plans, risk_rejected, risk_allocation = self.risk_allocator.allocate(plans, equity=equity)
        if risk_rejected:
            rejected.extend(risk_rejected)
        if not plans:
            return None
        allowed_symbols = {plan.symbol for plan in plans}
        selected = [
            item
            for item in selected
            if (item.get("candidate") or {}).get("symbol") in allowed_symbols
        ]
        total_required_cash = sum(float(plan.required_cash or 0.0) for plan in plans)

        return BasketPlan(
            trade_plans=plans,
            selected=selected,
            rejected=rejected,
            total_required_cash=total_required_cash,
            max_basket_value=max_basket_value,
            risk_allocation=risk_allocation,
        )
