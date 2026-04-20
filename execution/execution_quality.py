"""Execution Quality Analyzer.

Measures order-execution quality through slippage analysis, VWAP comparison,
fill-rate metrics, and rejection-pattern tracking.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FillQuality(str, Enum):
    """Qualitative fill assessment."""
    EXCELLENT = "EXCELLENT"   # better than VWAP
    GOOD = "GOOD"             # within 1 tick of VWAP
    FAIR = "FAIR"             # within 0.1% of VWAP
    POOR = "POOR"             # worse than 0.1% of VWAP


@dataclass
class ExecutionRecord:
    """Record of a single execution for quality analysis."""
    order_id: str
    symbol: str
    side: str             # "BUY" or "SELL"
    quantity: float
    limit_price: float    # intended price
    fill_price: float     # actual fill price
    vwap: float = 0.0     # volume-weighted average price at fill time
    market_price: float = 0.0  # mid-price at order submission
    fill_time_ms: float = 0.0  # time from submit to fill
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def slippage(self) -> float:
        """Signed slippage in price terms (positive = adverse)."""
        if self.side == "BUY":
            return self.fill_price - self.market_price
        return self.market_price - self.fill_price

    @property
    def slippage_pct(self) -> float:
        if self.market_price <= 0:
            return 0.0
        return self.slippage / self.market_price

    @property
    def slippage_bps(self) -> float:
        return self.slippage_pct * 10_000

    @property
    def vwap_deviation(self) -> float:
        """Deviation from VWAP (positive = worse than VWAP)."""
        if self.vwap <= 0:
            return 0.0
        if self.side == "BUY":
            return (self.fill_price - self.vwap) / self.vwap
        return (self.vwap - self.fill_price) / self.vwap

    @property
    def fill_quality(self) -> FillQuality:
        dev = abs(self.vwap_deviation)
        if self.vwap_deviation < 0:
            return FillQuality.EXCELLENT  # beat VWAP
        if dev <= 0.0002:
            return FillQuality.GOOD
        if dev <= 0.001:
            return FillQuality.FAIR
        return FillQuality.POOR

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "limit_price": round(self.limit_price, 4),
            "fill_price": round(self.fill_price, 4),
            "vwap": round(self.vwap, 4),
            "market_price": round(self.market_price, 4),
            "slippage": round(self.slippage, 4),
            "slippage_pct": round(self.slippage_pct * 100, 4),
            "slippage_bps": round(self.slippage_bps, 2),
            "vwap_deviation_pct": round(self.vwap_deviation * 100, 4),
            "fill_quality": self.fill_quality.value,
            "fill_time_ms": round(self.fill_time_ms, 1),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RejectionRecord:
    """Record of an order rejection."""
    order_id: str
    symbol: str
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ExecutionSummary:
    """Aggregate execution quality metrics over a period."""
    total_fills: int = 0
    total_rejections: int = 0
    fill_rate: float = 0.0
    avg_slippage_bps: float = 0.0
    median_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    avg_fill_time_ms: float = 0.0
    avg_vwap_deviation_pct: float = 0.0
    quality_breakdown: Dict[str, int] = field(default_factory=dict)
    top_rejection_reasons: Dict[str, int] = field(default_factory=dict)
    total_slippage_cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_fills": self.total_fills,
            "total_rejections": self.total_rejections,
            "fill_rate_pct": round(self.fill_rate * 100, 2),
            "avg_slippage_bps": round(self.avg_slippage_bps, 2),
            "median_slippage_bps": round(self.median_slippage_bps, 2),
            "max_slippage_bps": round(self.max_slippage_bps, 2),
            "avg_fill_time_ms": round(self.avg_fill_time_ms, 1),
            "avg_vwap_deviation_pct": round(self.avg_vwap_deviation_pct, 4),
            "quality_breakdown": self.quality_breakdown,
            "top_rejection_reasons": self.top_rejection_reasons,
            "total_slippage_cost": round(self.total_slippage_cost, 2),
        }


class ExecutionQualityAnalyzer:
    """Tracks and analyses execution quality across all order fills.

    Records every fill and rejection, then provides aggregate statistics
    including slippage distribution, VWAP comparison, fill-rate metrics,
    and rejection-pattern analysis.
    """

    def __init__(self) -> None:
        self._fills: List[ExecutionRecord] = []
        self._rejections: List[RejectionRecord] = []

    # ------------------------------------------------------------------
    # Data Ingestion
    # ------------------------------------------------------------------

    def record_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        limit_price: float,
        fill_price: float,
        vwap: float = 0.0,
        market_price: float = 0.0,
        fill_time_ms: float = 0.0,
        timestamp: Optional[datetime] = None,
    ) -> ExecutionRecord:
        """Record a completed order fill."""
        rec = ExecutionRecord(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            fill_price=fill_price,
            vwap=vwap,
            market_price=market_price or limit_price,
            fill_time_ms=fill_time_ms,
            timestamp=timestamp or datetime.utcnow(),
        )
        self._fills.append(rec)
        return rec

    def record_rejection(
        self,
        order_id: str,
        symbol: str,
        reason: str,
        timestamp: Optional[datetime] = None,
    ) -> RejectionRecord:
        """Record an order rejection."""
        rec = RejectionRecord(
            order_id=order_id,
            symbol=symbol,
            reason=reason,
            timestamp=timestamp or datetime.utcnow(),
        )
        self._rejections.append(rec)
        return rec

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def get_summary(self, period_days: Optional[int] = None) -> ExecutionSummary:
        """Compute aggregate execution quality metrics.

        Args:
            period_days: If set, only analyse records from the last N days.

        Returns:
            ExecutionSummary with slippage, fill quality, and rejection stats.
        """
        fills = self._filter_fills(period_days)
        rejections = self._filter_rejections(period_days)

        total = len(fills) + len(rejections)
        fill_rate = len(fills) / total if total > 0 else 1.0

        slippages = [f.slippage_bps for f in fills]
        fill_times = [f.fill_time_ms for f in fills]
        vwap_devs = [f.vwap_deviation * 100 for f in fills if f.vwap > 0]

        quality_breakdown: Dict[str, int] = {}
        for f in fills:
            q = f.fill_quality.value
            quality_breakdown[q] = quality_breakdown.get(q, 0) + 1

        rejection_reasons: Dict[str, int] = {}
        for r in rejections:
            rejection_reasons[r.reason] = rejection_reasons.get(r.reason, 0) + 1
        # Top 5 reasons
        sorted_reasons = sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True)[:5]

        total_cost = sum(
            abs(f.slippage) * f.quantity for f in fills
        )

        return ExecutionSummary(
            total_fills=len(fills),
            total_rejections=len(rejections),
            fill_rate=fill_rate,
            avg_slippage_bps=self._mean(slippages),
            median_slippage_bps=self._median(slippages),
            max_slippage_bps=max(slippages) if slippages else 0.0,
            avg_fill_time_ms=self._mean(fill_times),
            avg_vwap_deviation_pct=self._mean(vwap_devs),
            quality_breakdown=quality_breakdown,
            top_rejection_reasons=dict(sorted_reasons),
            total_slippage_cost=total_cost,
        )

    def get_symbol_analysis(self, symbol: str) -> ExecutionSummary:
        """Get execution quality for a specific symbol."""
        sym_fills = [f for f in self._fills if f.symbol == symbol]
        sym_rej = [r for r in self._rejections if r.symbol == symbol]

        # Temporarily swap and compute
        orig_fills, orig_rej = self._fills, self._rejections
        self._fills, self._rejections = sym_fills, sym_rej
        try:
            return self.get_summary()
        finally:
            self._fills, self._rejections = orig_fills, orig_rej

    def get_fills(self, limit: int = 100) -> List[ExecutionRecord]:
        """Return recent fills."""
        return list(reversed(self._fills[-limit:]))

    def get_rejections(self, limit: int = 100) -> List[RejectionRecord]:
        """Return recent rejections."""
        return list(reversed(self._rejections[-limit:]))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_fills(self, period_days: Optional[int]) -> List[ExecutionRecord]:
        if period_days is None:
            return self._fills
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        return [f for f in self._fills if f.timestamp >= cutoff]

    def _filter_rejections(self, period_days: Optional[int]) -> List[RejectionRecord]:
        if period_days is None:
            return self._rejections
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        return [r for r in self._rejections if r.timestamp >= cutoff]

    @staticmethod
    def _mean(values: List[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _median(values: List[float]) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        n = len(s)
        if n % 2 == 1:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2.0
