"""Risk Intelligence Engine.

Provides Monte Carlo simulation, historical stress testing, and position
liquidity analysis for risk-adjusted portfolio management.
"""

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class StressScenario(str, Enum):
    """Pre-defined market stress scenarios."""
    MARKET_CRASH_2008 = "MARKET_CRASH_2008"     # −38% equity drawdown
    COVID_CRASH_2020 = "COVID_CRASH_2020"       # −34% rapid drawdown
    RATE_SHOCK = "RATE_SHOCK"                   # interest-rate sensitive
    SECTOR_ROTATION = "SECTOR_ROTATION"         # growth → value shift
    FLASH_CRASH = "FLASH_CRASH"                 # short-lived liquidity crisis
    CUSTOM = "CUSTOM"


# Approximate single-day shocks for pre-defined scenarios
_SCENARIO_SHOCKS: Dict[StressScenario, float] = {
    StressScenario.MARKET_CRASH_2008: -0.08,
    StressScenario.COVID_CRASH_2020: -0.12,
    StressScenario.RATE_SHOCK: -0.05,
    StressScenario.SECTOR_ROTATION: -0.03,
    StressScenario.FLASH_CRASH: -0.06,
}


@dataclass
class MonteCarloResult:
    """Outcome of a Monte Carlo simulation run."""
    simulations: int
    horizon_days: int
    mean_return: float
    median_return: float
    std_dev: float
    percentile_5: float
    percentile_25: float
    percentile_75: float
    percentile_95: float
    var_95: float       # Value at Risk (95% confidence)
    cvar_95: float      # Conditional VaR (expected shortfall)
    probability_of_loss: float
    max_simulated_loss: float
    max_simulated_gain: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "simulations": self.simulations,
            "horizon_days": self.horizon_days,
            "mean_return_pct": round(self.mean_return * 100, 4),
            "median_return_pct": round(self.median_return * 100, 4),
            "std_dev_pct": round(self.std_dev * 100, 4),
            "percentile_5_pct": round(self.percentile_5 * 100, 4),
            "percentile_25_pct": round(self.percentile_25 * 100, 4),
            "percentile_75_pct": round(self.percentile_75 * 100, 4),
            "percentile_95_pct": round(self.percentile_95 * 100, 4),
            "var_95_pct": round(self.var_95 * 100, 4),
            "cvar_95_pct": round(self.cvar_95 * 100, 4),
            "probability_of_loss_pct": round(self.probability_of_loss * 100, 2),
            "max_simulated_loss_pct": round(self.max_simulated_loss * 100, 4),
            "max_simulated_gain_pct": round(self.max_simulated_gain * 100, 4),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class StressTestResult:
    """Result of applying a stress scenario to the portfolio."""
    scenario: str
    shock_pct: float
    portfolio_value_before: float
    portfolio_value_after: float
    estimated_loss: float
    positions_impacted: int
    worst_position: str
    worst_position_loss: float

    def to_dict(self) -> dict:
        raw_loss_pct = (
            self.estimated_loss / self.portfolio_value_before * 100
            if self.portfolio_value_before > 0 else 0.0
        )
        if raw_loss_pct >= 15:
            severity = "HIGH"
        elif raw_loss_pct >= 7:
            severity = "MEDIUM"
        else:
            severity = "LOW"
        return {
            "scenario": self.scenario,
            "shock_pct": round(self.shock_pct * 100, 2),
            "portfolio_value_before": round(self.portfolio_value_before, 2),
            "portfolio_value_after": round(self.portfolio_value_after, 2),
            "estimated_loss": round(self.estimated_loss, 2),
            "loss_pct": round(raw_loss_pct, 2),
            "severity": severity,
            "positions_impacted": self.positions_impacted,
            "worst_position": self.worst_position,
            "worst_position_loss": round(self.worst_position_loss, 2),
        }


@dataclass
class LiquidityProfile:
    """Liquidity assessment for a position or portfolio."""
    symbol: str
    avg_daily_volume: float
    position_size: float
    days_to_liquidate: float
    liquidity_score: float  # 0-100
    is_illiquid: bool

    def to_dict(self) -> dict:
        days = (
            round(self.days_to_liquidate, 2)
            if math.isfinite(self.days_to_liquidate)
            else None
        )
        return {
            "symbol": self.symbol,
            "avg_daily_volume": round(self.avg_daily_volume, 0),
            "position_size": round(self.position_size, 0),
            "days_to_liquidate": days,
            "liquidity_score": round(self.liquidity_score, 1),
            "is_illiquid": self.is_illiquid,
        }


class RiskIntelligenceEngine:
    """Risk-adjusted portfolio intelligence.

    Provides Monte Carlo simulation, historical stress tests, and
    position-level liquidity analysis.
    """

    def __init__(
        self,
        confidence_level: float = 0.95,
        max_participation_rate: float = 0.10,
        illiquidity_threshold_days: float = 3.0,
        seed: Optional[int] = None,
    ):
        self.confidence_level = confidence_level
        self.max_participation_rate = max_participation_rate
        self.illiquidity_threshold_days = illiquidity_threshold_days
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Monte Carlo Simulation
    # ------------------------------------------------------------------

    def run_monte_carlo(
        self,
        daily_returns: List[float],
        horizon_days: int = 21,
        simulations: int = 1000,
        initial_value: float = 100_000.0,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation of future portfolio returns.

        Uses historical daily returns to bootstrap future paths.

        Args:
            daily_returns: Historical daily return series (decimals).
            horizon_days: Number of trading days to simulate forward.
            simulations: Number of simulation paths.
            initial_value: Starting portfolio value.

        Returns:
            MonteCarloResult with VaR, CVaR, and return distribution.
        """
        if not daily_returns:
            return self._empty_monte_carlo(simulations, horizon_days)

        mean_ret = sum(daily_returns) / len(daily_returns)
        std_ret = math.sqrt(
            sum((r - mean_ret) ** 2 for r in daily_returns) / max(len(daily_returns) - 1, 1)
        )

        terminal_returns: List[float] = []
        for _ in range(simulations):
            cumulative = 1.0
            for _ in range(horizon_days):
                daily = self._rng.gauss(mean_ret, std_ret)
                cumulative *= (1 + daily)
            terminal_returns.append(cumulative - 1.0)

        terminal_returns.sort()
        n = len(terminal_returns)

        idx_5 = max(0, int(n * 0.05) - 1)
        idx_25 = max(0, int(n * 0.25) - 1)
        idx_50 = max(0, int(n * 0.50) - 1)
        idx_75 = max(0, int(n * 0.75) - 1)
        idx_95 = max(0, int(n * 0.95) - 1)

        var_idx = max(0, int(n * (1 - self.confidence_level)) - 1)
        var_95 = -terminal_returns[var_idx]

        # CVaR = average of losses beyond VaR
        tail = terminal_returns[: var_idx + 1]
        cvar_95 = -sum(tail) / len(tail) if tail else 0.0

        losses = [r for r in terminal_returns if r < 0]
        prob_loss = len(losses) / n if n > 0 else 0.0

        return MonteCarloResult(
            simulations=simulations,
            horizon_days=horizon_days,
            mean_return=sum(terminal_returns) / n,
            median_return=terminal_returns[idx_50],
            std_dev=math.sqrt(sum((r - sum(terminal_returns) / n) ** 2 for r in terminal_returns) / max(n - 1, 1)),
            percentile_5=terminal_returns[idx_5],
            percentile_25=terminal_returns[idx_25],
            percentile_75=terminal_returns[idx_75],
            percentile_95=terminal_returns[idx_95],
            var_95=var_95,
            cvar_95=cvar_95,
            probability_of_loss=prob_loss,
            max_simulated_loss=terminal_returns[0],
            max_simulated_gain=terminal_returns[-1],
        )

    # ------------------------------------------------------------------
    # Stress Testing
    # ------------------------------------------------------------------

    def run_stress_test(
        self,
        positions: List[Dict],
        scenario: StressScenario = StressScenario.MARKET_CRASH_2008,
        custom_shock: Optional[float] = None,
    ) -> StressTestResult:
        """Apply a stress scenario to the current portfolio.

        Args:
            positions: Dicts with ``symbol``, ``market_value``, and
                       optional ``beta`` for per-position scaling.
            scenario: Pre-defined scenario or CUSTOM.
            custom_shock: Custom single-day shock (used when scenario is CUSTOM).

        Returns:
            StressTestResult with estimated portfolio impact.
        """
        shock = custom_shock if scenario == StressScenario.CUSTOM else _SCENARIO_SHOCKS.get(scenario, -0.05)

        total_before = sum(abs(p.get("market_value", 0)) for p in positions)
        total_loss = 0.0
        worst_sym = ""
        worst_loss = 0.0

        for pos in positions:
            mv = abs(pos.get("market_value", 0))
            beta = pos.get("beta", 1.0)
            pos_shock = shock * beta
            loss = mv * abs(pos_shock)
            total_loss += loss
            if loss > worst_loss:
                worst_loss = loss
                worst_sym = pos.get("symbol", "?")

        return StressTestResult(
            scenario=scenario.value,
            shock_pct=shock,
            portfolio_value_before=total_before,
            portfolio_value_after=total_before - total_loss,
            estimated_loss=total_loss,
            positions_impacted=len(positions),
            worst_position=worst_sym,
            worst_position_loss=worst_loss,
        )

    def run_all_stress_tests(self, positions: List[Dict]) -> List[StressTestResult]:
        """Run all pre-defined stress scenarios."""
        results: List[StressTestResult] = []
        for scenario in StressScenario:
            if scenario == StressScenario.CUSTOM:
                continue
            results.append(self.run_stress_test(positions, scenario))
        return results

    # ------------------------------------------------------------------
    # Liquidity Analysis
    # ------------------------------------------------------------------

    def analyze_liquidity(
        self,
        positions: List[Dict],
    ) -> List[LiquidityProfile]:
        """Assess liquidation difficulty for each position.

        Args:
            positions: Dicts with ``symbol``, ``quantity``, ``current_price``,
                       and ``avg_daily_volume``.

        Returns:
            List of LiquidityProfile assessments.
        """
        profiles: List[LiquidityProfile] = []
        for pos in positions:
            sym = pos.get("symbol", "?")
            qty = abs(pos.get("quantity", 0))
            price = pos.get("current_price", 0.0)
            adv = pos.get("avg_daily_volume", 0.0)
            position_value = qty * price

            if adv > 0 and self.max_participation_rate > 0:
                daily_capacity = adv * price * self.max_participation_rate
                days = position_value / daily_capacity if daily_capacity > 0 else float("inf")
            else:
                days = float("inf")

            # Score: 100 = instantly liquid, 0 = very illiquid
            if days <= 0.1:
                score = 100.0
            elif days <= 1.0:
                score = 90.0
            elif days <= self.illiquidity_threshold_days:
                score = 90.0 - (days - 1.0) / (self.illiquidity_threshold_days - 1.0) * 40.0
            else:
                score = max(0.0, 50.0 - (days - self.illiquidity_threshold_days) * 10.0)

            profiles.append(LiquidityProfile(
                symbol=sym,
                avg_daily_volume=adv,
                position_size=position_value,
                days_to_liquidate=days,
                liquidity_score=max(0.0, min(100.0, score)),
                is_illiquid=days > self.illiquidity_threshold_days,
            ))
        return profiles

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        return {
            "confidence_level": self.confidence_level,
            "max_participation_rate": self.max_participation_rate,
            "illiquidity_threshold_days": self.illiquidity_threshold_days,
        }

    @staticmethod
    def _empty_monte_carlo(simulations: int, horizon_days: int) -> MonteCarloResult:
        return MonteCarloResult(
            simulations=simulations,
            horizon_days=horizon_days,
            mean_return=0.0,
            median_return=0.0,
            std_dev=0.0,
            percentile_5=0.0,
            percentile_25=0.0,
            percentile_75=0.0,
            percentile_95=0.0,
            var_95=0.0,
            cvar_95=0.0,
            probability_of_loss=0.0,
            max_simulated_loss=0.0,
            max_simulated_gain=0.0,
        )
