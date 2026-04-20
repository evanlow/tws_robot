"""Account Health Analyzer.

Provides health scoring, margin utilization analysis, buying power adequacy
checks, and compound annual growth rate (CAGR) computation for trading accounts.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthGrade(str, Enum):
    """Overall account health grades."""
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    CRITICAL = "CRITICAL"


@dataclass
class MarginUtilization:
    """Snapshot of margin usage relative to limits."""
    margin_used: float = 0.0
    margin_available: float = 0.0
    maintenance_margin: float = 0.0
    excess_liquidity: float = 0.0

    @property
    def utilization_pct(self) -> float:
        total = self.margin_used + self.margin_available
        if total <= 0:
            return 0.0
        return self.margin_used / total

    @property
    def is_warning(self) -> bool:
        return self.utilization_pct >= 0.70

    @property
    def is_critical(self) -> bool:
        return self.utilization_pct >= 0.90

    def to_dict(self) -> dict:
        return {
            "margin_used": round(self.margin_used, 2),
            "margin_available": round(self.margin_available, 2),
            "maintenance_margin": round(self.maintenance_margin, 2),
            "excess_liquidity": round(self.excess_liquidity, 2),
            "utilization_pct": round(self.utilization_pct * 100, 2),
            "is_warning": self.is_warning,
            "is_critical": self.is_critical,
        }


@dataclass
class BuyingPowerAnalysis:
    """Buying power adequacy relative to strategy requirements."""
    current_buying_power: float = 0.0
    required_buying_power: float = 0.0
    reserved_for_pending: float = 0.0
    available_for_new_trades: float = 0.0

    @property
    def adequacy_ratio(self) -> float:
        if self.required_buying_power <= 0:
            return float("inf") if self.current_buying_power > 0 else 0.0
        return self.current_buying_power / self.required_buying_power

    @property
    def is_adequate(self) -> bool:
        return self.adequacy_ratio >= 1.0

    def to_dict(self) -> dict:
        return {
            "current_buying_power": round(self.current_buying_power, 2),
            "required_buying_power": round(self.required_buying_power, 2),
            "reserved_for_pending": round(self.reserved_for_pending, 2),
            "available_for_new_trades": round(self.available_for_new_trades, 2),
            "adequacy_ratio": round(self.adequacy_ratio, 4),
            "is_adequate": self.is_adequate,
        }


@dataclass
class HealthScore:
    """Composite health score with component breakdown."""
    overall_score: float = 0.0
    grade: HealthGrade = HealthGrade.FAIR
    components: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 1),
            "grade": self.grade.value,
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "warnings": self.warnings,
            "timestamp": self.timestamp.isoformat(),
        }


class AccountHealthAnalyzer:
    """Analyzes account health across multiple dimensions.

    Computes a composite health score (0-100) based on:
    - Margin utilization (weight 25%)
    - Drawdown level (weight 25%)
    - Buying power adequacy (weight 20%)
    - Diversification (weight 15%)
    - Cash buffer (weight 15%)
    """

    # Component weights (must sum to 1.0)
    WEIGHTS = {
        "margin": 0.25,
        "drawdown": 0.25,
        "buying_power": 0.20,
        "diversification": 0.15,
        "cash_buffer": 0.15,
    }

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        margin_warning_pct: float = 0.70,
        margin_critical_pct: float = 0.90,
        max_drawdown_pct: float = 0.20,
        min_cash_buffer_pct: float = 0.10,
        min_positions_for_diversification: int = 5,
    ):
        self.initial_capital = initial_capital
        self.margin_warning_pct = margin_warning_pct
        self.margin_critical_pct = margin_critical_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.min_cash_buffer_pct = min_cash_buffer_pct
        self.min_positions_for_diversification = min_positions_for_diversification
        self._history: List[HealthScore] = []

    # ------------------------------------------------------------------
    # Core Analysis
    # ------------------------------------------------------------------

    def compute_health_score(
        self,
        equity: float,
        cash_balance: float,
        margin_used: float,
        margin_available: float,
        peak_equity: float,
        positions: List[Dict],
        pending_orders: int = 0,
    ) -> HealthScore:
        """Compute a composite health score for the account.

        Args:
            equity: Current total equity.
            cash_balance: Current cash / settled funds.
            margin_used: Current margin in use.
            margin_available: Remaining margin capacity.
            peak_equity: All-time peak equity for drawdown calculation.
            positions: List of position dicts with at least ``market_value``.
            pending_orders: Number of unfilled orders consuming buying power.

        Returns:
            HealthScore with 0-100 composite score and component breakdown.
        """
        components: Dict[str, float] = {}
        warnings: List[str] = []

        # 1. Margin score
        margin = self.analyze_margin(margin_used, margin_available)
        components["margin"] = self._score_margin(margin, warnings)

        # 2. Drawdown score
        components["drawdown"] = self._score_drawdown(equity, peak_equity, warnings)

        # 3. Buying power score
        bp = self.analyze_buying_power(equity, cash_balance, margin_available, pending_orders)
        components["buying_power"] = self._score_buying_power(bp, warnings)

        # 4. Diversification score
        components["diversification"] = self._score_diversification(positions, equity, warnings)

        # 5. Cash buffer score
        components["cash_buffer"] = self._score_cash_buffer(cash_balance, equity, warnings)

        # Weighted composite
        overall = sum(
            self.WEIGHTS[k] * components[k] for k in self.WEIGHTS
        )
        grade = self._grade_from_score(overall)

        score = HealthScore(
            overall_score=overall,
            grade=grade,
            components=components,
            warnings=warnings,
        )
        self._history.append(score)
        return score

    # ------------------------------------------------------------------
    # Sub-Analyses
    # ------------------------------------------------------------------

    def analyze_margin(
        self,
        margin_used: float,
        margin_available: float,
        maintenance_margin: float = 0.0,
        excess_liquidity: float = 0.0,
    ) -> MarginUtilization:
        """Return a margin utilization snapshot."""
        return MarginUtilization(
            margin_used=margin_used,
            margin_available=margin_available,
            maintenance_margin=maintenance_margin,
            excess_liquidity=excess_liquidity,
        )

    def analyze_buying_power(
        self,
        equity: float,
        cash_balance: float,
        margin_available: float,
        pending_orders: int = 0,
        avg_order_size: float = 0.0,
    ) -> BuyingPowerAnalysis:
        """Compute buying power adequacy."""
        reserved = pending_orders * avg_order_size
        available = max(0.0, cash_balance + margin_available - reserved)
        required = equity * self.min_cash_buffer_pct
        return BuyingPowerAnalysis(
            current_buying_power=cash_balance + margin_available,
            required_buying_power=required,
            available_for_new_trades=available,
            reserved_for_pending=reserved,
        )

    @staticmethod
    def compute_cagr(
        start_value: float,
        end_value: float,
        days: int,
    ) -> float:
        """Compute compound annual growth rate.

        Args:
            start_value: Portfolio value at start of period.
            end_value: Portfolio value at end of period.
            days: Number of calendar days in the period.

        Returns:
            CAGR as a decimal (e.g. 0.12 for 12%).
        """
        if start_value <= 0 or days <= 0:
            return 0.0
        years = days / 365.25
        if years <= 0:
            return 0.0
        ratio = end_value / start_value
        if ratio <= 0:
            return -1.0
        return ratio ** (1.0 / years) - 1.0

    # ------------------------------------------------------------------
    # Scoring helpers (0-100 scale)
    # ------------------------------------------------------------------

    def _score_margin(self, margin: MarginUtilization, warnings: List[str]) -> float:
        util = margin.utilization_pct
        if util <= 0.30:
            score = 100.0
        elif util <= self.margin_warning_pct:
            score = 100.0 - (util - 0.30) / (self.margin_warning_pct - 0.30) * 40.0
        elif util <= self.margin_critical_pct:
            score = 60.0 - (util - self.margin_warning_pct) / (self.margin_critical_pct - self.margin_warning_pct) * 40.0
            warnings.append(f"Margin utilization at {util*100:.1f}% — approaching critical")
        else:
            score = max(0.0, 20.0 - (util - self.margin_critical_pct) / 0.10 * 20.0)
            warnings.append(f"Margin utilization at {util*100:.1f}% — CRITICAL")
        return max(0.0, min(100.0, score))

    def _score_drawdown(self, equity: float, peak_equity: float, warnings: List[str]) -> float:
        if peak_equity <= 0:
            return 100.0
        dd = (peak_equity - equity) / peak_equity
        if dd <= 0:
            return 100.0
        if dd <= 0.05:
            score = 100.0 - dd / 0.05 * 20.0
        elif dd <= self.max_drawdown_pct:
            score = 80.0 - (dd - 0.05) / (self.max_drawdown_pct - 0.05) * 50.0
            warnings.append(f"Drawdown at {dd*100:.1f}%")
        else:
            score = max(0.0, 30.0 - (dd - self.max_drawdown_pct) / 0.10 * 30.0)
            warnings.append(f"Drawdown at {dd*100:.1f}% — exceeds {self.max_drawdown_pct*100:.0f}% limit")
        return max(0.0, min(100.0, score))

    def _score_buying_power(self, bp: BuyingPowerAnalysis, warnings: List[str]) -> float:
        ratio = bp.adequacy_ratio
        if ratio == float("inf"):
            return 100.0
        if ratio >= 3.0:
            score = 100.0
        elif ratio >= 1.5:
            score = 80.0 + (ratio - 1.5) / 1.5 * 20.0
        elif ratio >= 1.0:
            score = 60.0 + (ratio - 1.0) / 0.5 * 20.0
        else:
            score = max(0.0, ratio * 60.0)
            warnings.append("Buying power below required threshold")
        return max(0.0, min(100.0, score))

    def _score_diversification(
        self,
        positions: List[Dict],
        equity: float,
        warnings: List[str],
    ) -> float:
        n = len(positions)
        if n == 0:
            return 50.0  # No positions — neutral

        # Check concentration
        if equity <= 0:
            return 50.0
        max_concentration = 0.0
        for pos in positions:
            mv = abs(pos.get("market_value", 0))
            concentration = mv / equity
            if concentration > max_concentration:
                max_concentration = concentration

        score = 100.0
        # Penalize low count
        if n < self.min_positions_for_diversification:
            ratio = n / self.min_positions_for_diversification
            score *= ratio

        # Penalize high concentration
        if max_concentration > 0.50:
            score *= 0.5
            warnings.append(f"Single position is {max_concentration*100:.1f}% of portfolio")
        elif max_concentration > 0.30:
            score *= 0.75
            warnings.append(f"Largest position is {max_concentration*100:.1f}% of portfolio")

        return max(0.0, min(100.0, score))

    def _score_cash_buffer(self, cash: float, equity: float, warnings: List[str]) -> float:
        if equity <= 0:
            return 0.0
        ratio = cash / equity
        if ratio >= self.min_cash_buffer_pct * 2:
            score = 100.0
        elif ratio >= self.min_cash_buffer_pct:
            score = 60.0 + (ratio - self.min_cash_buffer_pct) / self.min_cash_buffer_pct * 40.0
        else:
            score = max(0.0, ratio / self.min_cash_buffer_pct * 60.0)
            warnings.append(f"Cash buffer at {ratio*100:.1f}% — below {self.min_cash_buffer_pct*100:.0f}% minimum")
        return max(0.0, min(100.0, score))

    @staticmethod
    def _grade_from_score(score: float) -> HealthGrade:
        if score >= 85:
            return HealthGrade.EXCELLENT
        if score >= 70:
            return HealthGrade.GOOD
        if score >= 50:
            return HealthGrade.FAIR
        if score >= 30:
            return HealthGrade.POOR
        return HealthGrade.CRITICAL

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @property
    def history(self) -> List[HealthScore]:
        return list(self._history)

    def get_summary(self) -> dict:
        """Return a JSON-friendly summary of the most recent health score."""
        if not self._history:
            return {"status": "no_data"}
        return self._history[-1].to_dict()
