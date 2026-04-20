"""Cash Management Engine.

Implements cash reserve policies, idle-cash detection, and simple cash-flow
forecasting to keep liquidity aligned with trading requirements.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ReservePolicy(str, Enum):
    """Pre-defined cash reserve strategies."""
    CONSERVATIVE = "CONSERVATIVE"   # 20% cash reserve
    MODERATE = "MODERATE"           # 10% cash reserve
    AGGRESSIVE = "AGGRESSIVE"       # 5% cash reserve
    CUSTOM = "CUSTOM"


@dataclass
class CashReserveConfig:
    """Configuration for the cash-reserve target."""
    policy: ReservePolicy = ReservePolicy.MODERATE
    reserve_pct: float = 0.10       # default 10%
    min_reserve_usd: float = 5000.0
    max_idle_days: int = 7

    def __post_init__(self) -> None:
        if self.policy == ReservePolicy.CONSERVATIVE:
            self.reserve_pct = 0.20
        elif self.policy == ReservePolicy.MODERATE:
            self.reserve_pct = 0.10
        elif self.policy == ReservePolicy.AGGRESSIVE:
            self.reserve_pct = 0.05

    def to_dict(self) -> dict:
        return {
            "policy": self.policy.value,
            "reserve_pct": round(self.reserve_pct * 100, 2),
            "min_reserve_usd": round(self.min_reserve_usd, 2),
            "max_idle_days": self.max_idle_days,
        }


@dataclass
class CashFlowEntry:
    """A single expected cash-flow event (dividend, expiry, settlement)."""
    date: datetime
    amount: float
    description: str
    category: str = "other"  # dividend, settlement, expiry, deposit, withdrawal

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "amount": round(self.amount, 2),
            "description": self.description,
            "category": self.category,
        }


@dataclass
class CashAnalysis:
    """Result of a cash-management analysis."""
    cash_balance: float = 0.0
    equity: float = 0.0
    target_reserve: float = 0.0
    excess_cash: float = 0.0
    deficit: float = 0.0
    idle_cash: float = 0.0
    idle_days: int = 0
    recommendations: List[str] = field(default_factory=list)
    forecast: List[CashFlowEntry] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def cash_pct(self) -> float:
        if self.equity <= 0:
            return 0.0
        return self.cash_balance / self.equity

    @property
    def is_adequate(self) -> bool:
        return self.deficit <= 0

    def to_dict(self) -> dict:
        return {
            "cash_balance": round(self.cash_balance, 2),
            "equity": round(self.equity, 2),
            "target_reserve": round(self.target_reserve, 2),
            "excess_cash": round(self.excess_cash, 2),
            "deficit": round(self.deficit, 2),
            "idle_cash": round(self.idle_cash, 2),
            "idle_days": self.idle_days,
            "cash_pct": round(self.cash_pct * 100, 2),
            "is_adequate": self.is_adequate,
            "recommendations": self.recommendations,
            "forecast": [f.to_dict() for f in self.forecast],
            "timestamp": self.timestamp.isoformat(),
        }


class CashManagementEngine:
    """Manages cash reserves and forecasts cash flow.

    The engine tracks cash balances over time, detects idle cash, and
    generates recommendations to keep liquidity aligned with the
    configured reserve policy.
    """

    def __init__(self, config: Optional[CashReserveConfig] = None):
        self.config = config or CashReserveConfig()
        self._balance_history: List[Tuple[datetime, float]] = []
        self._scheduled_flows: List[CashFlowEntry] = []

    # ------------------------------------------------------------------
    # Core Analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        cash_balance: float,
        equity: float,
        last_trade_date: Optional[datetime] = None,
    ) -> CashAnalysis:
        """Run cash-management analysis.

        Args:
            cash_balance: Current settled cash.
            equity: Total account equity (cash + positions).
            last_trade_date: When the last trade was executed (for idle detection).

        Returns:
            CashAnalysis with reserve status, idle cash detection, and recommendations.
        """
        now = datetime.utcnow()
        self._balance_history.append((now, cash_balance))

        target = self._compute_target_reserve(equity)
        excess = max(0.0, cash_balance - target)
        deficit = max(0.0, target - cash_balance)

        # Idle cash detection
        idle_cash = 0.0
        idle_days = 0
        if last_trade_date:
            idle_days = (now - last_trade_date).days
            if idle_days > self.config.max_idle_days:
                idle_cash = excess

        recommendations = self._generate_recommendations(
            cash_balance, equity, target, excess, deficit, idle_cash, idle_days,
        )

        # Upcoming forecast
        future_flows = [f for f in self._scheduled_flows if f.date >= now]
        future_flows.sort(key=lambda f: f.date)

        return CashAnalysis(
            cash_balance=cash_balance,
            equity=equity,
            target_reserve=target,
            excess_cash=excess,
            deficit=deficit,
            idle_cash=idle_cash,
            idle_days=idle_days,
            recommendations=recommendations,
            forecast=future_flows[:20],
        )

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def add_expected_flow(
        self,
        date: datetime,
        amount: float,
        description: str,
        category: str = "other",
    ) -> None:
        """Register an expected future cash-flow event."""
        self._scheduled_flows.append(
            CashFlowEntry(date=date, amount=amount, description=description, category=category)
        )

    def get_forecast(self, days: int = 30) -> List[CashFlowEntry]:
        """Return expected cash-flow entries for the next *days* days."""
        cutoff = datetime.utcnow() + timedelta(days=days)
        now = datetime.utcnow()
        flows = [f for f in self._scheduled_flows if now <= f.date <= cutoff]
        flows.sort(key=lambda f: f.date)
        return flows

    def forecast_balance(
        self,
        current_cash: float,
        days: int = 30,
    ) -> List[Tuple[datetime, float]]:
        """Project daily cash balance over the forecast horizon.

        Returns list of (date, projected_balance) tuples.
        """
        flows = self.get_forecast(days)
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        flow_by_day: Dict[str, float] = {}
        for f in flows:
            key = f.date.strftime("%Y-%m-%d")
            flow_by_day[key] = flow_by_day.get(key, 0.0) + f.amount

        result: List[Tuple[datetime, float]] = []
        balance = current_cash
        for d in range(days + 1):
            dt = today + timedelta(days=d)
            key = dt.strftime("%Y-%m-%d")
            balance += flow_by_day.get(key, 0.0)
            result.append((dt, balance))
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_target_reserve(self, equity: float) -> float:
        pct_target = equity * self.config.reserve_pct
        return max(pct_target, self.config.min_reserve_usd)

    def _generate_recommendations(
        self,
        cash: float,
        equity: float,
        target: float,
        excess: float,
        deficit: float,
        idle_cash: float,
        idle_days: int,
    ) -> List[str]:
        recs: List[str] = []
        if deficit > 0:
            recs.append(
                f"Cash reserve deficit of ${deficit:,.0f}. "
                f"Consider reducing positions or depositing funds."
            )
        if idle_cash > 0 and idle_days > self.config.max_idle_days:
            recs.append(
                f"${idle_cash:,.0f} idle for {idle_days} days. "
                f"Consider deploying into income-generating positions."
            )
        if excess > equity * 0.30:
            recs.append(
                f"Large cash position ({cash/equity*100:.0f}% of equity). "
                f"Review opportunity cost of uninvested capital."
            )
        if cash < self.config.min_reserve_usd:
            recs.append(
                f"Cash below minimum reserve of ${self.config.min_reserve_usd:,.0f}."
            )
        return recs

    # ------------------------------------------------------------------
    # History & Summaries
    # ------------------------------------------------------------------

    @property
    def balance_history(self) -> List[Tuple[datetime, float]]:
        return list(self._balance_history)

    def get_summary(self) -> dict:
        """JSON-friendly summary of configuration and recent state."""
        return {
            "config": self.config.to_dict(),
            "balance_history_count": len(self._balance_history),
            "scheduled_flows": len(self._scheduled_flows),
        }
