"""Performance Benchmarking.

Compares portfolio returns against market benchmarks (SPY, QQQ), calculates
fee drag, and tracks tax-lot information for wash-sale awareness.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BenchmarkIndex(str, Enum):
    """Supported benchmark indices."""
    SPY = "SPY"       # S&P 500
    QQQ = "QQQ"       # Nasdaq 100
    IWM = "IWM"       # Russell 2000
    DIA = "DIA"       # Dow Jones
    CUSTOM = "CUSTOM"


@dataclass
class BenchmarkComparison:
    """Side-by-side return comparison between portfolio and benchmark."""
    benchmark: str
    period_days: int
    portfolio_return_pct: float
    benchmark_return_pct: float
    alpha: float = 0.0  # portfolio − benchmark
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    beta: float = 0.0
    correlation: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        self.alpha = self.portfolio_return_pct - self.benchmark_return_pct

    def to_dict(self) -> dict:
        return {
            "benchmark": self.benchmark,
            "period_days": self.period_days,
            "portfolio_return_pct": round(self.portfolio_return_pct, 4),
            "benchmark_return_pct": round(self.benchmark_return_pct, 4),
            "alpha_pct": round(self.alpha, 4),
            "tracking_error": round(self.tracking_error, 4),
            "information_ratio": round(self.information_ratio, 4),
            "beta": round(self.beta, 4),
            "correlation": round(self.correlation, 4),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FeeDragAnalysis:
    """Breakdown of fee impact on portfolio returns."""
    total_commissions: float = 0.0
    total_fees: float = 0.0  # exchange, regulatory, etc.
    total_slippage_estimate: float = 0.0
    gross_return_pct: float = 0.0
    net_return_pct: float = 0.0
    fee_drag_pct: float = 0.0
    trades_analyzed: int = 0

    def to_dict(self) -> dict:
        return {
            "total_commissions": round(self.total_commissions, 2),
            "total_fees": round(self.total_fees, 2),
            "total_slippage_estimate": round(self.total_slippage_estimate, 2),
            "gross_return_pct": round(self.gross_return_pct, 4),
            "net_return_pct": round(self.net_return_pct, 4),
            "fee_drag_pct": round(self.fee_drag_pct, 4),
            "trades_analyzed": self.trades_analyzed,
        }


@dataclass
class TaxLot:
    """Individual tax lot for a position."""
    symbol: str
    quantity: float
    cost_basis: float
    acquisition_date: datetime
    lot_id: str = ""
    is_short_term: bool = True  # < 1 year
    unrealized_gain: float = 0.0

    def update_gain(self, current_price: float) -> None:
        self.unrealized_gain = (current_price - self.cost_basis) * self.quantity
        holding_days = (datetime.utcnow() - self.acquisition_date).days
        self.is_short_term = holding_days < 365

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "cost_basis": round(self.cost_basis, 4),
            "acquisition_date": self.acquisition_date.isoformat(),
            "lot_id": self.lot_id,
            "is_short_term": self.is_short_term,
            "unrealized_gain": round(self.unrealized_gain, 2),
            "holding_days": (datetime.utcnow() - self.acquisition_date).days,
        }


@dataclass
class WashSaleAlert:
    """Alert for potential wash-sale violation."""
    symbol: str
    sale_date: datetime
    sale_price: float
    loss_amount: float
    wash_window_end: datetime  # +30 days
    message: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "sale_date": self.sale_date.isoformat(),
            "sale_price": round(self.sale_price, 4),
            "loss_amount": round(self.loss_amount, 2),
            "wash_window_end": self.wash_window_end.isoformat(),
            "message": self.message,
        }


class PerformanceBenchmarker:
    """Compares portfolio performance against benchmarks and tracks fees/taxes.

    Maintains daily portfolio equity history alongside benchmark prices
    to compute alpha, tracking error, information ratio, and beta.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        default_commission_per_trade: float = 1.0,
    ):
        self.initial_capital = initial_capital
        self.default_commission = default_commission_per_trade
        self._portfolio_history: List[Tuple[datetime, float]] = []
        self._benchmark_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self._tax_lots: Dict[str, List[TaxLot]] = {}  # symbol → lots
        self._wash_sale_alerts: List[WashSaleAlert] = []
        self._trade_fees: List[Dict] = []

    # ------------------------------------------------------------------
    # Data Ingestion
    # ------------------------------------------------------------------

    def record_portfolio_value(self, timestamp: datetime, equity: float) -> None:
        """Record a daily portfolio equity snapshot."""
        self._portfolio_history.append((timestamp, equity))

    def record_benchmark_value(self, benchmark: str, timestamp: datetime, price: float) -> None:
        """Record a daily benchmark price."""
        if benchmark not in self._benchmark_history:
            self._benchmark_history[benchmark] = []
        self._benchmark_history[benchmark].append((timestamp, price))

    def record_trade_fee(
        self,
        symbol: str,
        commission: float,
        fees: float = 0.0,
        slippage: float = 0.0,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record fees from a trade execution."""
        self._trade_fees.append({
            "symbol": symbol,
            "commission": commission,
            "fees": fees,
            "slippage": slippage,
            "timestamp": (timestamp or datetime.utcnow()).isoformat(),
        })

    # ------------------------------------------------------------------
    # Benchmark Comparison
    # ------------------------------------------------------------------

    def compare_to_benchmark(
        self,
        benchmark: str = "SPY",
        period_days: int = 30,
    ) -> BenchmarkComparison:
        """Compare portfolio return to a benchmark over the given period.

        Args:
            benchmark: Benchmark ticker (e.g. "SPY").
            period_days: Look-back period in days.

        Returns:
            BenchmarkComparison with alpha, tracking error, etc.
        """
        port_ret = self._compute_period_return(self._portfolio_history, period_days)
        bench_hist = self._benchmark_history.get(benchmark, [])
        bench_ret = self._compute_period_return(bench_hist, period_days)

        # Daily returns for risk metrics
        port_daily = self._daily_returns(self._portfolio_history, period_days)
        bench_daily = self._daily_returns(bench_hist, period_days)

        te = self._tracking_error(port_daily, bench_daily)
        ir = (port_ret - bench_ret) / te if te > 0 else 0.0
        beta = self._compute_beta(port_daily, bench_daily)
        corr = self._compute_correlation(port_daily, bench_daily)

        return BenchmarkComparison(
            benchmark=benchmark,
            period_days=period_days,
            portfolio_return_pct=port_ret,
            benchmark_return_pct=bench_ret,
            tracking_error=te,
            information_ratio=ir,
            beta=beta,
            correlation=corr,
        )

    # ------------------------------------------------------------------
    # Fee Drag
    # ------------------------------------------------------------------

    def compute_fee_drag(self, period_days: int = 30) -> FeeDragAnalysis:
        """Compute the drag of fees and commissions on returns.

        Args:
            period_days: Period for gross/net return calculation.

        Returns:
            FeeDragAnalysis with gross vs. net returns.
        """
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        recent = [t for t in self._trade_fees if datetime.fromisoformat(t["timestamp"]) >= cutoff]

        total_comm = sum(t["commission"] for t in recent)
        total_fees = sum(t["fees"] for t in recent)
        total_slip = sum(t["slippage"] for t in recent)

        gross_ret = self._compute_period_return(self._portfolio_history, period_days)
        total_drag = total_comm + total_fees + total_slip
        capital = self.initial_capital
        if self._portfolio_history:
            # Use average equity as base
            recent_vals = [v for _, v in self._portfolio_history[-period_days:]]
            if recent_vals:
                capital = sum(recent_vals) / len(recent_vals)

        drag_pct = total_drag / capital if capital > 0 else 0.0
        net_ret = gross_ret - drag_pct

        return FeeDragAnalysis(
            total_commissions=total_comm,
            total_fees=total_fees,
            total_slippage_estimate=total_slip,
            gross_return_pct=gross_ret,
            net_return_pct=net_ret,
            fee_drag_pct=drag_pct,
            trades_analyzed=len(recent),
        )

    # ------------------------------------------------------------------
    # Tax-Lot Tracking
    # ------------------------------------------------------------------

    def add_tax_lot(
        self,
        symbol: str,
        quantity: float,
        cost_basis: float,
        acquisition_date: datetime,
        lot_id: str = "",
    ) -> TaxLot:
        """Register a new tax lot."""
        lot = TaxLot(
            symbol=symbol,
            quantity=quantity,
            cost_basis=cost_basis,
            acquisition_date=acquisition_date,
            lot_id=lot_id or f"{symbol}-{acquisition_date.strftime('%Y%m%d')}-{len(self._tax_lots.get(symbol, []))}",
        )
        if symbol not in self._tax_lots:
            self._tax_lots[symbol] = []
        self._tax_lots[symbol].append(lot)
        return lot

    def check_wash_sale(
        self,
        symbol: str,
        sale_date: datetime,
        sale_price: float,
        cost_basis: float,
        quantity: float,
    ) -> Optional[WashSaleAlert]:
        """Check if a sale triggers a wash-sale warning.

        A wash sale occurs when you sell at a loss and repurchase the same
        (or substantially identical) security within 30 days before or after.
        """
        loss = (sale_price - cost_basis) * quantity
        if loss >= 0:
            return None  # No loss, no wash sale concern

        window_end = sale_date + timedelta(days=30)
        alert = WashSaleAlert(
            symbol=symbol,
            sale_date=sale_date,
            sale_price=sale_price,
            loss_amount=loss,
            wash_window_end=window_end,
            message=(
                f"Sold {symbol} at a loss of ${abs(loss):,.2f}. "
                f"Avoid repurchasing until {window_end.strftime('%Y-%m-%d')} "
                f"to prevent wash-sale disallowance."
            ),
        )
        self._wash_sale_alerts.append(alert)
        return alert

    def get_tax_lots(self, symbol: Optional[str] = None) -> List[TaxLot]:
        """Return tax lots, optionally filtered by symbol."""
        if symbol:
            return list(self._tax_lots.get(symbol, []))
        lots: List[TaxLot] = []
        for sym_lots in self._tax_lots.values():
            lots.extend(sym_lots)
        return lots

    def get_unrealized_tax_summary(self, current_prices: Dict[str, float]) -> dict:
        """Summarise unrealised gains/losses across all lots.

        Args:
            current_prices: Dict mapping symbol → current price.

        Returns:
            Summary with short-term / long-term gain split.
        """
        short_term_gain = 0.0
        long_term_gain = 0.0
        for sym, lots in self._tax_lots.items():
            price = current_prices.get(sym, 0.0)
            for lot in lots:
                lot.update_gain(price)
                if lot.is_short_term:
                    short_term_gain += lot.unrealized_gain
                else:
                    long_term_gain += lot.unrealized_gain
        return {
            "short_term_unrealized": round(short_term_gain, 2),
            "long_term_unrealized": round(long_term_gain, 2),
            "total_unrealized": round(short_term_gain + long_term_gain, 2),
            "total_lots": sum(len(v) for v in self._tax_lots.values()),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_period_return(
        history: List[Tuple[datetime, float]],
        period_days: int,
    ) -> float:
        if len(history) < 2:
            return 0.0
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        relevant = [(t, v) for t, v in history if t >= cutoff]
        if len(relevant) < 2:
            relevant = history[-min(len(history), period_days):]
        if len(relevant) < 2:
            return 0.0
        start_val = relevant[0][1]
        end_val = relevant[-1][1]
        if start_val <= 0:
            return 0.0
        return (end_val - start_val) / start_val

    @staticmethod
    def _daily_returns(
        history: List[Tuple[datetime, float]],
        period_days: int,
    ) -> List[float]:
        if len(history) < 2:
            return []
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        relevant = [(t, v) for t, v in history if t >= cutoff]
        if len(relevant) < 2:
            relevant = history[-min(len(history), period_days):]
        returns: List[float] = []
        for i in range(1, len(relevant)):
            prev = relevant[i - 1][1]
            curr = relevant[i][1]
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

    @staticmethod
    def _tracking_error(port_returns: List[float], bench_returns: List[float]) -> float:
        n = min(len(port_returns), len(bench_returns))
        if n < 2:
            return 0.0
        diffs = [port_returns[i] - bench_returns[i] for i in range(n)]
        mean = sum(diffs) / n
        var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
        return math.sqrt(var) if var > 0 else 0.0

    @staticmethod
    def _compute_beta(port_returns: List[float], bench_returns: List[float]) -> float:
        n = min(len(port_returns), len(bench_returns))
        if n < 2:
            return 0.0
        p_mean = sum(port_returns[:n]) / n
        b_mean = sum(bench_returns[:n]) / n
        cov = sum((port_returns[i] - p_mean) * (bench_returns[i] - b_mean) for i in range(n)) / (n - 1)
        b_var = sum((bench_returns[i] - b_mean) ** 2 for i in range(n)) / (n - 1)
        if b_var <= 0:
            return 0.0
        return cov / b_var

    @staticmethod
    def _compute_correlation(port_returns: List[float], bench_returns: List[float]) -> float:
        n = min(len(port_returns), len(bench_returns))
        if n < 2:
            return 0.0
        p_mean = sum(port_returns[:n]) / n
        b_mean = sum(bench_returns[:n]) / n
        cov = sum((port_returns[i] - p_mean) * (bench_returns[i] - b_mean) for i in range(n)) / (n - 1)
        p_var = sum((port_returns[i] - p_mean) ** 2 for i in range(n)) / (n - 1)
        b_var = sum((bench_returns[i] - b_mean) ** 2 for i in range(n)) / (n - 1)
        denom = math.sqrt(p_var * b_var) if p_var > 0 and b_var > 0 else 0.0
        if denom <= 0:
            return 0.0
        return cov / denom

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        return {
            "portfolio_history_points": len(self._portfolio_history),
            "benchmarks_tracked": list(self._benchmark_history.keys()),
            "total_tax_lots": sum(len(v) for v in self._tax_lots.values()),
            "wash_sale_alerts": len(self._wash_sale_alerts),
            "trade_fees_recorded": len(self._trade_fees),
        }
