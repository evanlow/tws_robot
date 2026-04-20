"""Opportunity Detector.

Identifies portfolio gaps, generates rebalancing suggestions, and screens
for dividend opportunities based on current holdings and market data.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class OpportunityType(str, Enum):
    """Categories of detected opportunities."""
    REBALANCE = "REBALANCE"
    SECTOR_GAP = "SECTOR_GAP"
    DIVIDEND = "DIVIDEND"
    UNDERWEIGHT = "UNDERWEIGHT"
    OVERWEIGHT = "OVERWEIGHT"
    CORRELATION = "CORRELATION"
    NEW_POSITION = "NEW_POSITION"


class Urgency(str, Enum):
    """How urgently an opportunity should be acted upon."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class Opportunity:
    """A single actionable opportunity."""
    opportunity_type: OpportunityType
    symbol: str
    description: str
    urgency: Urgency = Urgency.LOW
    suggested_action: str = ""
    potential_impact: float = 0.0  # estimated $ impact
    metadata: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "type": self.opportunity_type.value,
            "symbol": self.symbol,
            "description": self.description,
            "urgency": self.urgency.value,
            "suggested_action": self.suggested_action,
            "potential_impact": round(self.potential_impact, 2),
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SectorAllocation:
    """Target vs. actual sector allocation."""
    sector: str
    target_pct: float
    actual_pct: float

    @property
    def deviation(self) -> float:
        return self.actual_pct - self.target_pct

    @property
    def is_overweight(self) -> bool:
        return self.deviation > 0.05  # 5pp threshold

    @property
    def is_underweight(self) -> bool:
        return self.deviation < -0.05

    def to_dict(self) -> dict:
        return {
            "sector": self.sector,
            "target_pct": round(self.target_pct * 100, 2),
            "actual_pct": round(self.actual_pct * 100, 2),
            "deviation_pct": round(self.deviation * 100, 2),
            "status": (
                "overweight" if self.is_overweight
                else "underweight" if self.is_underweight
                else "on_target"
            ),
        }


@dataclass
class RebalanceSuggestion:
    """Concrete rebalancing action."""
    symbol: str
    current_weight: float
    target_weight: float
    action: str  # "BUY" or "SELL"
    suggested_amount_usd: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_weight_pct": round(self.current_weight * 100, 2),
            "target_weight_pct": round(self.target_weight * 100, 2),
            "action": self.action,
            "suggested_amount_usd": round(self.suggested_amount_usd, 2),
            "reason": self.reason,
        }


class OpportunityDetector:
    """Detects portfolio improvement opportunities.

    Analyses current holdings against target allocations and market
    conditions to surface actionable opportunities.
    """

    # Default equal-weighted sector targets (US market)
    DEFAULT_SECTOR_TARGETS: Dict[str, float] = {
        "Technology": 0.25,
        "Healthcare": 0.15,
        "Financials": 0.15,
        "Consumer Discretionary": 0.10,
        "Industrials": 0.10,
        "Consumer Staples": 0.05,
        "Energy": 0.05,
        "Utilities": 0.05,
        "Materials": 0.05,
        "Real Estate": 0.05,
    }

    def __init__(
        self,
        sector_targets: Optional[Dict[str, float]] = None,
        rebalance_threshold: float = 0.05,
        max_single_position_pct: float = 0.25,
        min_dividend_yield: float = 0.02,
    ):
        self.sector_targets = sector_targets or dict(self.DEFAULT_SECTOR_TARGETS)
        self.rebalance_threshold = rebalance_threshold
        self.max_single_position_pct = max_single_position_pct
        self.min_dividend_yield = min_dividend_yield
        self._detected: List[Opportunity] = []

    # ------------------------------------------------------------------
    # Portfolio Gap Analysis
    # ------------------------------------------------------------------

    def analyze_sector_gaps(
        self,
        positions: List[Dict],
        equity: float,
    ) -> List[SectorAllocation]:
        """Compare actual sector allocations to targets.

        Args:
            positions: List of dicts with ``sector`` and ``market_value`` keys.
            equity: Total account equity.

        Returns:
            List of SectorAllocation comparisons.
        """
        actual: Dict[str, float] = {}
        for pos in positions:
            sector = pos.get("sector", "Unknown")
            mv = abs(pos.get("market_value", 0.0))
            actual[sector] = actual.get(sector, 0.0) + mv

        all_sectors = set(self.sector_targets) | set(actual)
        results: List[SectorAllocation] = []
        for sector in sorted(all_sectors):
            target = self.sector_targets.get(sector, 0.0)
            act_val = actual.get(sector, 0.0)
            act_pct = act_val / equity if equity > 0 else 0.0
            results.append(SectorAllocation(sector=sector, target_pct=target, actual_pct=act_pct))
        return results

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def generate_rebalance_suggestions(
        self,
        positions: List[Dict],
        equity: float,
    ) -> List[RebalanceSuggestion]:
        """Generate concrete rebalance suggestions.

        Args:
            positions: Dicts with ``symbol``, ``market_value`` keys.
            equity: Total account equity.

        Returns:
            List of buy/sell suggestions to bring portfolio into alignment.
        """
        if equity <= 0:
            return []

        suggestions: List[RebalanceSuggestion] = []
        weights: Dict[str, float] = {}
        for pos in positions:
            sym = pos.get("symbol", "?")
            mv = abs(pos.get("market_value", 0.0))
            weights[sym] = mv / equity

        # Check for overweight positions
        for sym, weight in weights.items():
            if weight > self.max_single_position_pct:
                over = weight - self.max_single_position_pct
                suggestions.append(RebalanceSuggestion(
                    symbol=sym,
                    current_weight=weight,
                    target_weight=self.max_single_position_pct,
                    action="SELL",
                    suggested_amount_usd=over * equity,
                    reason=f"Position exceeds {self.max_single_position_pct*100:.0f}% limit",
                ))

        # Equal-weight rebalance among existing positions
        n = len(positions)
        if n > 0:
            equal_weight = 1.0 / n
            for pos in positions:
                sym = pos.get("symbol", "?")
                current = weights.get(sym, 0.0)
                diff = current - equal_weight
                if abs(diff) > self.rebalance_threshold:
                    action = "SELL" if diff > 0 else "BUY"
                    suggestions.append(RebalanceSuggestion(
                        symbol=sym,
                        current_weight=current,
                        target_weight=equal_weight,
                        action=action,
                        suggested_amount_usd=abs(diff) * equity,
                        reason="Rebalance toward equal weight",
                    ))

        return suggestions

    # ------------------------------------------------------------------
    # Dividend Screening
    # ------------------------------------------------------------------

    def screen_dividend_opportunities(
        self,
        candidates: List[Dict],
    ) -> List[Opportunity]:
        """Screen candidates for dividend income opportunities.

        Args:
            candidates: Dicts with ``symbol``, ``dividend_yield``, ``sector``,
                        and optional ``ex_date``, ``payout_ratio``.

        Returns:
            Opportunities for dividend-yielding instruments.
        """
        opps: List[Opportunity] = []
        for c in candidates:
            dy = c.get("dividend_yield", 0.0)
            if dy >= self.min_dividend_yield:
                sym = c.get("symbol", "?")
                payout = c.get("payout_ratio", 0.0)
                urgency = Urgency.HIGH if dy >= 0.05 else Urgency.MEDIUM
                opp = Opportunity(
                    opportunity_type=OpportunityType.DIVIDEND,
                    symbol=sym,
                    description=f"{sym} yields {dy*100:.1f}% (payout ratio {payout*100:.0f}%)",
                    urgency=urgency,
                    suggested_action=f"Consider adding {sym} for income",
                    potential_impact=0.0,
                    metadata={"dividend_yield": dy, "payout_ratio": payout, "sector": c.get("sector", "")},
                )
                opps.append(opp)
                self._detected.append(opp)
        return opps

    # ------------------------------------------------------------------
    # Master Scan
    # ------------------------------------------------------------------

    def scan(
        self,
        positions: List[Dict],
        equity: float,
        dividend_candidates: Optional[List[Dict]] = None,
    ) -> List[Opportunity]:
        """Run full opportunity scan.

        Args:
            positions: Current portfolio positions.
            equity: Total account equity.
            dividend_candidates: Optional list of dividend screening candidates.

        Returns:
            All detected opportunities sorted by urgency.
        """
        all_opps: List[Opportunity] = []

        # Sector gaps → opportunities
        gaps = self.analyze_sector_gaps(positions, equity)
        for g in gaps:
            if g.is_underweight:
                opp = Opportunity(
                    opportunity_type=OpportunityType.SECTOR_GAP,
                    symbol="",
                    description=f"{g.sector} underweight by {abs(g.deviation)*100:.1f}pp",
                    urgency=Urgency.MEDIUM if abs(g.deviation) > 0.10 else Urgency.LOW,
                    suggested_action=f"Add exposure to {g.sector}",
                )
                all_opps.append(opp)
            elif g.is_overweight:
                opp = Opportunity(
                    opportunity_type=OpportunityType.OVERWEIGHT,
                    symbol="",
                    description=f"{g.sector} overweight by {g.deviation*100:.1f}pp",
                    urgency=Urgency.MEDIUM,
                    suggested_action=f"Trim {g.sector} exposure",
                )
                all_opps.append(opp)

        # Rebalance suggestions → opportunities
        rebs = self.generate_rebalance_suggestions(positions, equity)
        for r in rebs:
            opp = Opportunity(
                opportunity_type=OpportunityType.REBALANCE,
                symbol=r.symbol,
                description=f"{r.action} {r.symbol}: {r.current_weight*100:.1f}% → {r.target_weight*100:.1f}%",
                urgency=Urgency.MEDIUM,
                suggested_action=f"{r.action} ~${r.suggested_amount_usd:,.0f}",
                potential_impact=r.suggested_amount_usd,
            )
            all_opps.append(opp)

        # Dividends
        if dividend_candidates:
            all_opps.extend(self.screen_dividend_opportunities(dividend_candidates))

        # Sort by urgency
        urgency_order = {Urgency.HIGH: 0, Urgency.MEDIUM: 1, Urgency.LOW: 2}
        all_opps.sort(key=lambda o: urgency_order.get(o.urgency, 9))

        self._detected.extend(all_opps)
        return all_opps

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @property
    def detected_opportunities(self) -> List[Opportunity]:
        return list(self._detected)

    def get_summary(self) -> dict:
        return {
            "total_detected": len(self._detected),
            "by_type": self._count_by_type(),
            "rebalance_threshold_pct": round(self.rebalance_threshold * 100, 2),
        }

    def _count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for o in self._detected:
            key = o.opportunity_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts
