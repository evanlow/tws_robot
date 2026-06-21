"""Basket-level stop-risk allocation for autonomous trading.

The allocator is deliberately conservative: it can only reduce a basket leg's
quantity or reject the leg. It never increases size beyond the existing
TradePlanner and PositionSizer output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from autonomous.trade_planner import TradePlan, TradeType


@dataclass
class BasketRiskLegDecision:
    """Risk allocation result for one basket leg."""

    symbol: str
    allowed: bool
    allocated_risk_dollars: float
    planned_risk_dollars: float = 0.0
    original_planned_risk_dollars: float = 0.0
    risk_per_share: Optional[float] = None
    original_quantity: int = 0
    final_quantity: int = 0
    resized: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "allowed": self.allowed,
            "allocated_risk_dollars": round(self.allocated_risk_dollars, 2),
            "planned_risk_dollars": round(self.planned_risk_dollars, 2),
            "original_planned_risk_dollars": round(self.original_planned_risk_dollars, 2),
            "risk_per_share": round(self.risk_per_share, 4) if self.risk_per_share is not None else None,
            "original_quantity": self.original_quantity,
            "final_quantity": self.final_quantity,
            "resized": self.resized,
            "reason": self.reason,
        }


@dataclass
class BasketRiskAllocation:
    """Aggregate basket risk allocation diagnostics."""

    enabled: bool
    allocation_mode: str
    max_basket_risk_dollars: float
    total_planned_risk_dollars: float
    budget_usage_pct: float
    legs: List[BasketRiskLegDecision] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "allocation_mode": self.allocation_mode,
            "max_basket_risk_dollars": round(self.max_basket_risk_dollars, 2),
            "total_planned_risk_dollars": round(self.total_planned_risk_dollars, 2),
            "budget_usage_pct": round(self.budget_usage_pct, 6),
            "legs": [leg.to_dict() for leg in self.legs],
        }


class BasketRiskAllocator:
    """Allocate one shared basket stop-risk budget across planned legs."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_basket_risk_equity_pct: float = 0.002,
        allocation_mode: str = "equal_risk",
        min_leg_risk_dollars: float = 20.0,
    ) -> None:
        self.enabled = enabled
        self.max_basket_risk_equity_pct = max_basket_risk_equity_pct
        self.allocation_mode = allocation_mode
        self.min_leg_risk_dollars = min_leg_risk_dollars

    def allocate(
        self,
        plans: List[TradePlan],
        *,
        equity: float,
    ) -> tuple[List[TradePlan], List[Dict[str, Any]], BasketRiskAllocation]:
        if not plans:
            return [], [], BasketRiskAllocation(
                enabled=self.enabled,
                allocation_mode=self.allocation_mode,
                max_basket_risk_dollars=0.0,
                total_planned_risk_dollars=0.0,
                budget_usage_pct=0.0,
            )

        max_risk = max(0.0, equity * self.max_basket_risk_equity_pct)
        if not self.enabled:
            diagnostics = [
                self._existing_leg_decision(plan, allocated_risk_dollars=0.0)
                for plan in plans
            ]
            total_risk = sum(leg.planned_risk_dollars for leg in diagnostics)
            return plans, [], BasketRiskAllocation(
                enabled=False,
                allocation_mode=self.allocation_mode,
                max_basket_risk_dollars=max_risk,
                total_planned_risk_dollars=total_risk,
                budget_usage_pct=_usage(total_risk, max_risk),
                legs=diagnostics,
            )

        if equity <= 0 or max_risk <= 0:
            rejected = [
                {"symbol": plan.symbol, "reason": "basket risk allocator requires positive equity and risk budget"}
                for plan in plans
            ]
            allocation = BasketRiskAllocation(
                enabled=True,
                allocation_mode=self.allocation_mode,
                max_basket_risk_dollars=max_risk,
                total_planned_risk_dollars=0.0,
                budget_usage_pct=0.0,
            )
            return [], rejected, allocation

        if self.allocation_mode != "equal_risk":
            rejected = [
                {"symbol": plan.symbol, "reason": f"unsupported basket risk allocation mode {self.allocation_mode!r}"}
                for plan in plans
            ]
            allocation = BasketRiskAllocation(
                enabled=True,
                allocation_mode=self.allocation_mode,
                max_basket_risk_dollars=max_risk,
                total_planned_risk_dollars=0.0,
                budget_usage_pct=0.0,
            )
            return [], rejected, allocation

        allocated_per_leg = max_risk / len(plans)
        adjusted: List[TradePlan] = []
        rejected: List[Dict[str, Any]] = []
        leg_diagnostics: List[BasketRiskLegDecision] = []

        for plan in plans:
            adjusted_plan, decision = self._allocate_leg(plan, allocated_per_leg)
            leg_diagnostics.append(decision)
            if adjusted_plan is None:
                rejected.append({"symbol": plan.symbol, "reason": decision.reason})
                continue
            adjusted.append(adjusted_plan)

        total_risk = sum(leg.planned_risk_dollars for leg in leg_diagnostics if leg.allowed)
        allocation = BasketRiskAllocation(
            enabled=True,
            allocation_mode=self.allocation_mode,
            max_basket_risk_dollars=max_risk,
            total_planned_risk_dollars=total_risk,
            budget_usage_pct=_usage(total_risk, max_risk),
            legs=leg_diagnostics,
        )
        return adjusted, rejected, allocation

    def _allocate_leg(
        self,
        plan: TradePlan,
        allocated_risk_dollars: float,
    ) -> tuple[Optional[TradePlan], BasketRiskLegDecision]:
        if plan.trade_type != TradeType.BUY_SHARES:
            return None, BasketRiskLegDecision(
                symbol=plan.symbol,
                allowed=False,
                allocated_risk_dollars=allocated_risk_dollars,
                reason="basket risk allocator supports BUY_SHARES legs only",
            )

        risk_per_share = _risk_per_share(plan)
        original_quantity = int(plan.quantity or 0)
        if risk_per_share is None:
            return None, BasketRiskLegDecision(
                symbol=plan.symbol,
                allowed=False,
                allocated_risk_dollars=allocated_risk_dollars,
                original_quantity=original_quantity,
                reason="basket risk allocator requires a valid stop_price below entry",
            )

        original_risk = risk_per_share * original_quantity
        if allocated_risk_dollars < self.min_leg_risk_dollars:
            return None, BasketRiskLegDecision(
                symbol=plan.symbol,
                allowed=False,
                allocated_risk_dollars=allocated_risk_dollars,
                original_planned_risk_dollars=original_risk,
                risk_per_share=risk_per_share,
                original_quantity=original_quantity,
                reason=(
                    f"allocated basket risk ${allocated_risk_dollars:.2f} below "
                    f"minimum leg risk ${self.min_leg_risk_dollars:.2f}"
                ),
            )

        max_quantity = int(math.floor(allocated_risk_dollars / risk_per_share))
        if max_quantity <= 0:
            return None, BasketRiskLegDecision(
                symbol=plan.symbol,
                allowed=False,
                allocated_risk_dollars=allocated_risk_dollars,
                original_planned_risk_dollars=original_risk,
                risk_per_share=risk_per_share,
                original_quantity=original_quantity,
                reason=(
                    f"one-share risk ${risk_per_share:.2f} exceeds allocated "
                    f"basket risk ${allocated_risk_dollars:.2f}"
                ),
            )

        final_quantity = min(original_quantity, max_quantity)
        planned_risk = risk_per_share * final_quantity
        resized = final_quantity < original_quantity
        adjusted = plan
        if resized:
            adjusted = replace(
                plan,
                quantity=final_quantity,
                required_cash=final_quantity * plan.limit_price,
                sizing=_sizing_with_basket_risk(
                    plan=plan,
                    final_quantity=final_quantity,
                    planned_risk=planned_risk,
                    allocated_risk_dollars=allocated_risk_dollars,
                    risk_per_share=risk_per_share,
                ),
                risk_notes=[
                    *plan.risk_notes,
                    (
                        "Basket risk allocator reduced quantity from "
                        f"{original_quantity} to {final_quantity} shares."
                    ),
                ],
            )
        else:
            adjusted = replace(
                plan,
                sizing=_sizing_with_basket_risk(
                    plan=plan,
                    final_quantity=final_quantity,
                    planned_risk=planned_risk,
                    allocated_risk_dollars=allocated_risk_dollars,
                    risk_per_share=risk_per_share,
                ),
            )

        return adjusted, BasketRiskLegDecision(
            symbol=plan.symbol,
            allowed=True,
            allocated_risk_dollars=allocated_risk_dollars,
            planned_risk_dollars=planned_risk,
            original_planned_risk_dollars=original_risk,
            risk_per_share=risk_per_share,
            original_quantity=original_quantity,
            final_quantity=final_quantity,
            resized=resized,
            reason=(
                "within allocated basket risk"
                if not resized
                else f"reduced to {final_quantity} shares to fit allocated basket risk"
            ),
        )

    def _existing_leg_decision(
        self,
        plan: TradePlan,
        *,
        allocated_risk_dollars: float,
    ) -> BasketRiskLegDecision:
        risk_per_share = _risk_per_share(plan)
        planned_risk = (risk_per_share or 0.0) * int(plan.quantity or 0)
        return BasketRiskLegDecision(
            symbol=plan.symbol,
            allowed=True,
            allocated_risk_dollars=allocated_risk_dollars,
            planned_risk_dollars=planned_risk,
            original_planned_risk_dollars=planned_risk,
            risk_per_share=risk_per_share,
            original_quantity=int(plan.quantity or 0),
            final_quantity=int(plan.quantity or 0),
            reason="basket risk allocator disabled",
        )


def _risk_per_share(plan: TradePlan) -> Optional[float]:
    if plan.limit_price <= 0:
        return None
    if plan.stop_price is None or plan.stop_price <= 0 or plan.stop_price >= plan.limit_price:
        return None
    return plan.limit_price - plan.stop_price


def _sizing_with_basket_risk(
    *,
    plan: TradePlan,
    final_quantity: int,
    planned_risk: float,
    allocated_risk_dollars: float,
    risk_per_share: float,
) -> Dict[str, Any]:
    sizing = dict(plan.sizing or {})
    caps = dict(sizing.get("caps") or {})
    cap_values = dict(caps.get("cap_values") or {})
    basket_cap_value = final_quantity * plan.limit_price
    cap_values["basket_risk_cap"] = round(basket_cap_value, 2)
    caps["cap_values"] = cap_values
    caps["basket_risk"] = {
        "allocated_risk_dollars": round(allocated_risk_dollars, 2),
        "planned_risk_dollars": round(planned_risk, 2),
        "risk_per_share": round(risk_per_share, 4),
    }
    if final_quantity < int(plan.quantity or 0):
        sizing["binding_cap"] = "basket_risk_cap"
        caps["final_cap_value"] = round(basket_cap_value, 2)
    sizing["quantity"] = final_quantity
    sizing["required_cash"] = round(basket_cap_value, 2)
    sizing["caps"] = caps
    return sizing


def _usage(total_risk: float, max_risk: float) -> float:
    if max_risk <= 0:
        return 0.0
    return total_risk / max_risk
