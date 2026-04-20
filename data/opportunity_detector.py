"""Opportunity Detector.

Identifies portfolio gaps, generates rebalancing suggestions, screens
for dividend opportunities, and detects concentration risk based on
current holdings and market data.

Produces novice-friendly, actionable opportunities with concrete ticker
suggestions, dollar amounts, and plain-English summaries.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Sector → representative ETF mapping
# ------------------------------------------------------------------

SECTOR_ETF_MAP: Dict[str, List[Dict[str, str]]] = {
    "Technology": [
        {"symbol": "XLK", "name": "Technology Select Sector SPDR"},
        {"symbol": "QQQ", "name": "Invesco QQQ Trust"},
    ],
    "Healthcare": [
        {"symbol": "XLV", "name": "Health Care Select Sector SPDR"},
    ],
    "Financials": [
        {"symbol": "XLF", "name": "Financial Select Sector SPDR"},
    ],
    "Consumer Discretionary": [
        {"symbol": "XLY", "name": "Consumer Discretionary Select Sector SPDR"},
    ],
    "Industrials": [
        {"symbol": "XLI", "name": "Industrial Select Sector SPDR"},
    ],
    "Consumer Staples": [
        {"symbol": "XLP", "name": "Consumer Staples Select Sector SPDR"},
    ],
    "Energy": [
        {"symbol": "XLE", "name": "Energy Select Sector SPDR"},
    ],
    "Utilities": [
        {"symbol": "XLU", "name": "Utilities Select Sector SPDR"},
    ],
    "Materials": [
        {"symbol": "XLB", "name": "Materials Select Sector SPDR"},
    ],
    "Real Estate": [
        {"symbol": "XLRE", "name": "Real Estate Select Sector SPDR"},
    ],
    "Communication Services": [
        {"symbol": "XLC", "name": "Communication Services Select Sector SPDR"},
    ],
}


class OpportunityType(str, Enum):
    """Categories of detected opportunities."""
    REBALANCE = "REBALANCE"
    SECTOR_GAP = "SECTOR_GAP"
    DIVIDEND = "DIVIDEND"
    UNDERWEIGHT = "UNDERWEIGHT"
    OVERWEIGHT = "OVERWEIGHT"
    CONCENTRATION = "CONCENTRATION"
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
    conditions to surface actionable opportunities with concrete,
    novice-friendly suggestions.
    """

    # Default sector targets roughly matching S&P 500 weights (US market)
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
        concentration_top_n: int = 3,
        concentration_warn_pct: float = 0.80,
    ):
        self.sector_targets = sector_targets or dict(self.DEFAULT_SECTOR_TARGETS)
        self.rebalance_threshold = rebalance_threshold
        self.max_single_position_pct = max_single_position_pct
        self.min_dividend_yield = min_dividend_yield
        self.concentration_top_n = concentration_top_n
        self.concentration_warn_pct = concentration_warn_pct
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
    # Concentration Risk
    # ------------------------------------------------------------------

    def detect_concentration_risk(
        self,
        positions: List[Dict],
        equity: float,
    ) -> List[Opportunity]:
        """Detect portfolio concentration risk.

        Warns when the top N positions represent more than a threshold
        percentage of total equity.

        Args:
            positions: Dicts with ``symbol`` and ``market_value``.
            equity: Total account equity.

        Returns:
            List of concentration-risk opportunities (may be empty).
        """
        if equity <= 0 or len(positions) == 0:
            return []

        sorted_pos = sorted(
            positions,
            key=lambda p: abs(p.get("market_value", 0.0)),
            reverse=True,
        )
        top_n = min(self.concentration_top_n, len(positions))
        top = sorted_pos[:top_n]
        top_value = sum(abs(p.get("market_value", 0.0)) for p in top)
        top_pct = top_value / equity

        if top_pct < self.concentration_warn_pct:
            return []

        top_symbols = [p.get("symbol", "?") for p in top]
        symbols_str = ", ".join(top_symbols)
        urgency = Urgency.HIGH if top_pct >= 0.90 else Urgency.MEDIUM

        opp = Opportunity(
            opportunity_type=OpportunityType.CONCENTRATION,
            symbol=symbols_str,
            description=(
                f"Your top {top_n} position{'s' if top_n > 1 else ''} "
                f"({symbols_str}) represent{'' if top_n > 1 else 's'} {top_pct*100:.0f}% of your portfolio"
            ),
            urgency=urgency,
            suggested_action=(
                f"Consider diversifying — spread risk across more positions "
                f"to reduce concentration in {symbols_str}"
            ),
            potential_impact=top_value,
            metadata={
                "top_symbols": top_symbols,
                "top_pct": round(top_pct, 4),
                "top_value": round(top_value, 2),
            },
        )
        return [opp]

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def generate_rebalance_suggestions(
        self,
        positions: List[Dict],
        equity: float,
    ) -> List[RebalanceSuggestion]:
        """Generate concrete rebalance suggestions.

        Only flags positions that exceed the maximum single-position
        limit.  Naive equal-weight rebalancing is intentionally omitted
        because it produces noise for portfolios that are deliberately
        sized by conviction or sector.

        Args:
            positions: Dicts with ``symbol``, ``market_value`` keys.
            equity: Total account equity.

        Returns:
            List of sell suggestions for overweight positions.
        """
        if equity <= 0:
            return []

        suggestions: List[RebalanceSuggestion] = []
        weights: Dict[str, float] = {}
        for pos in positions:
            sym = pos.get("symbol", "?")
            mv = abs(pos.get("market_value", 0.0))
            weights[sym] = mv / equity

        # Flag positions that exceed the per-position cap
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
            if dy is None:
                dy = 0.0
            if dy >= self.min_dividend_yield:
                sym = c.get("symbol", "?")
                payout = c.get("payout_ratio") or 0.0
                urgency = Urgency.HIGH if dy >= 0.05 else Urgency.MEDIUM
                opp = Opportunity(
                    opportunity_type=OpportunityType.DIVIDEND,
                    symbol=sym,
                    description=f"{sym} yields {dy*100:.1f}% (payout ratio {payout*100:.0f}%)",
                    urgency=urgency,
                    suggested_action=f"Consider adding {sym} for dividend income",
                    potential_impact=0.0,
                    metadata={
                        "dividend_yield": dy,
                        "payout_ratio": payout,
                        "sector": c.get("sector", ""),
                    },
                )
                opps.append(opp)
        return opps

    # ------------------------------------------------------------------
    # Helpers — ETF suggestions for sectors
    # ------------------------------------------------------------------

    @staticmethod
    def _etf_symbol_for_sector(sector: str) -> str:
        """Return the primary ETF ticker for a sector, or empty string."""
        etfs = SECTOR_ETF_MAP.get(sector)
        if etfs:
            return etfs[0]["symbol"]
        return ""

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

        # 1. Concentration risk
        all_opps.extend(self.detect_concentration_risk(positions, equity))

        # 2. Sector gaps → opportunities with concrete ETF suggestions
        gaps = self.analyze_sector_gaps(positions, equity)
        for g in gaps:
            if g.is_underweight:
                etf_sym = self._etf_symbol_for_sector(g.sector)
                gap_usd = abs(g.deviation) * equity if equity > 0 else 0.0
                deviation_pp = abs(g.deviation) * 100

                # Build a novice-friendly description
                desc = f"{g.sector} underweight by {deviation_pp:.1f}pp"
                if etf_sym:
                    desc += f" — consider {etf_sym}"

                # Suggested action with dollar amount
                if etf_sym and gap_usd > 0:
                    action = f"Buy ~${gap_usd:,.0f} of {etf_sym}"
                elif etf_sym:
                    action = f"Add exposure via {etf_sym}"
                else:
                    action = f"Add exposure to {g.sector}"

                urgency = Urgency.MEDIUM if deviation_pp > 10 else Urgency.LOW

                opp = Opportunity(
                    opportunity_type=OpportunityType.SECTOR_GAP,
                    symbol=etf_sym,
                    description=desc,
                    urgency=urgency,
                    suggested_action=action,
                    potential_impact=round(gap_usd, 2),
                    metadata={
                        "sector": g.sector,
                        "deviation_pp": round(deviation_pp, 1),
                        "target_pct": round(g.target_pct * 100, 1),
                        "actual_pct": round(g.actual_pct * 100, 1),
                        "etf": etf_sym,
                    },
                )
                all_opps.append(opp)

            elif g.is_overweight:
                deviation_pp = g.deviation * 100
                over_usd = g.deviation * equity if equity > 0 else 0.0

                opp = Opportunity(
                    opportunity_type=OpportunityType.OVERWEIGHT,
                    symbol="",
                    description=f"{g.sector} overweight by {deviation_pp:.1f}pp",
                    urgency=Urgency.HIGH if deviation_pp > 30 else Urgency.MEDIUM,
                    suggested_action=f"Trim {g.sector} exposure (~${over_usd:,.0f})",
                    potential_impact=round(over_usd, 2),
                    metadata={
                        "sector": g.sector,
                        "deviation_pp": round(deviation_pp, 1),
                    },
                )
                all_opps.append(opp)

        # 3. Rebalance suggestions (overweight positions only)
        rebs = self.generate_rebalance_suggestions(positions, equity)
        for r in rebs:
            opp = Opportunity(
                opportunity_type=OpportunityType.REBALANCE,
                symbol=r.symbol,
                description=(
                    f"{r.symbol} is {r.current_weight*100:.1f}% of portfolio "
                    f"(max {r.target_weight*100:.0f}%) — consider trimming"
                ),
                urgency=Urgency.HIGH if r.current_weight > 0.40 else Urgency.MEDIUM,
                suggested_action=f"Sell ~${r.suggested_amount_usd:,.0f} of {r.symbol}",
                potential_impact=r.suggested_amount_usd,
            )
            all_opps.append(opp)

        # 4. Dividends
        if dividend_candidates:
            all_opps.extend(self.screen_dividend_opportunities(dividend_candidates))

        # Sort by urgency (HIGH first)
        urgency_order = {Urgency.HIGH: 0, Urgency.MEDIUM: 1, Urgency.LOW: 2}
        all_opps.sort(key=lambda o: urgency_order.get(o.urgency, 9))

        self._detected.extend(all_opps)
        return all_opps

    # ------------------------------------------------------------------
    # Plain-English Summary
    # ------------------------------------------------------------------

    def generate_plain_summary(
        self,
        positions: List[Dict],
        equity: float,
    ) -> str:
        """Generate a novice-friendly plain-English summary of the portfolio.

        Args:
            positions: Current portfolio positions.
            equity: Total account equity.

        Returns:
            A human-readable summary string.
        """
        if not positions:
            return (
                "Your portfolio is empty. Consider starting with a diversified "
                "ETF like SPY (S&P 500) or VTI (Total Stock Market) to build "
                "broad market exposure."
            )

        parts: List[str] = []
        n_positions = len(positions)
        parts.append(f"You hold {n_positions} position{'s' if n_positions != 1 else ''}.")

        # Sector breakdown
        sectors: Dict[str, float] = {}
        for pos in positions:
            s = pos.get("sector", "Unknown")
            mv = abs(pos.get("market_value", 0.0))
            sectors[s] = sectors.get(s, 0.0) + mv

        if equity > 0:
            sorted_sectors = sorted(sectors.items(), key=lambda x: x[1], reverse=True)
            top_sector, top_val = sorted_sectors[0]
            top_pct = top_val / equity * 100
            if top_pct > 60:
                parts.append(
                    f"Your portfolio is heavily concentrated in {top_sector} "
                    f"({top_pct:.0f}% of equity). Diversifying across sectors "
                    f"can reduce risk."
                )
            elif top_pct > 40:
                parts.append(
                    f"{top_sector} makes up {top_pct:.0f}% of your portfolio."
                )

            # Missing sectors
            missing = [
                s for s in self.sector_targets
                if s not in sectors and self.sector_targets[s] >= 0.05
            ]
            if missing:
                etf_hints = []
                for s in missing[:3]:
                    etf = self._etf_symbol_for_sector(s)
                    etf_hints.append(f"{s} ({etf})" if etf else s)
                parts.append(
                    "You have no exposure to " + ", ".join(etf_hints) + "."
                )

        return " ".join(parts)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @property
    def detected_opportunities(self) -> List[Opportunity]:
        return list(self._detected)

    def get_summary(self) -> dict:
        high_count = sum(
            1 for o in self._detected if o.urgency == Urgency.HIGH
        )
        return {
            "total_detected": len(self._detected),
            "high_urgency_count": high_count,
            "by_type": self._count_by_type(),
            "rebalance_threshold_pct": round(self.rebalance_threshold * 100, 2),
        }

    def _count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for o in self._detected:
            key = o.opportunity_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts
