"""Backtest-first Opening Range Breakout (ORB) strategy.

Runs the deterministic long-only ORB state machine over 1-minute OHLCV data and
simulates bracket exits (target / stop / force-flat). Requires no broker or TWS
connection — only historical 1-minute candles. This is the Phase-1 MVP entry
point for evaluating ORB before any paper/live promotion.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from autonomous.opening_range import (
    Candle,
    ORBSetup,
    OpeningRangeConfig,
    OpeningRangeSession,
)


@dataclass
class ORBTradeResult:
    symbol: str
    session_date: str
    model: str
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    exit_price: float
    exit_reason: str  # "target" | "stop" | "force_flat" | "session_end"
    quantity: int
    r_multiple: float
    pnl: float


@dataclass
class ORBBacktestResult:
    trades: List[ORBTradeResult] = field(default_factory=list)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.pnl > 0)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.trades else 0.0

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def avg_r(self) -> float:
        return sum(t.r_multiple for t in self.trades) / self.total_trades if self.trades else 0.0

    def by_model(self) -> Dict[str, dict]:
        out: Dict[str, List[ORBTradeResult]] = defaultdict(list)
        for t in self.trades:
            out[t.model].append(t)
        return {m: _summary(ts) for m, ts in out.items()}

    def by_symbol(self) -> Dict[str, dict]:
        out: Dict[str, List[ORBTradeResult]] = defaultdict(list)
        for t in self.trades:
            out[t.symbol].append(t)
        return {s: _summary(ts) for s, ts in out.items()}

    def summary(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "avg_r": self.avg_r,
            "by_model": self.by_model(),
            "by_symbol": self.by_symbol(),
        }


def _summary(trades: List[ORBTradeResult]) -> dict:
    n = len(trades)
    return {
        "trades": n,
        "win_rate": (sum(1 for t in trades if t.pnl > 0) / n) if n else 0.0,
        "total_pnl": sum(t.pnl for t in trades),
        "avg_r": (sum(t.r_multiple for t in trades) / n) if n else 0.0,
    }


def _quantity(equity: float, entry: float, stop: float, cfg: OpeningRangeConfig) -> int:
    risk_per_share = entry - stop
    if risk_per_share <= 0 or entry <= 0:
        return 0
    qty = int((equity * cfg.risk_per_trade_equity_pct) // risk_per_share)
    max_qty = int((equity * cfg.max_position_equity_pct) // entry)
    qty = min(qty, max_qty)
    return max(qty, 0)


class OpeningRangeBacktest:
    """Backtest runner for ORB across one or more session dates."""

    def __init__(self, config: Optional[OpeningRangeConfig] = None,
                 equity: float = 100_000.0, commission_per_share: float = 0.005):
        self.config = config or OpeningRangeConfig()
        self.equity = equity
        self.commission_per_share = commission_per_share

    def run(self, candles_1m: List[Candle]) -> ORBBacktestResult:
        result = ORBBacktestResult()
        by_day: Dict[tuple, List[Candle]] = defaultdict(list)
        for c in candles_1m:
            by_day[(c.symbol, c.start.date())].append(c)

        force_flat = self.config.parse_time(self.config.force_flat_time)
        max_per_session = self.config.max_total_orb_trades_per_session
        trades_per_date: Dict[object, int] = defaultdict(int)
        for (symbol, day), bars in sorted(by_day.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if max_per_session and trades_per_date[day] >= max_per_session:
                continue
            bars.sort(key=lambda b: b.start)
            session_date = day.isoformat()
            session = OpeningRangeSession(symbol, session_date, self.config)
            setup: Optional[ORBSetup] = None
            entry_idx: Optional[int] = None
            for i, bar in enumerate(bars):
                s = session.on_closed_1m(bar)
                if s is not None and setup is None:
                    setup = s
                    entry_idx = i
                    break
            if setup is None or entry_idx is None:
                continue
            qty = _quantity(self.equity, setup.entry_price, setup.stop_price, self.config)
            if qty <= 0:
                continue
            trade = self._simulate_exit(bars, entry_idx, setup, qty, force_flat)
            if trade is not None:
                result.trades.append(trade)
                trades_per_date[day] += 1
        return result

    def _simulate_exit(self, bars, entry_idx, setup, qty, force_flat) -> Optional[ORBTradeResult]:
        exit_price = setup.entry_price
        exit_reason = "session_end"
        for j in range(entry_idx + 1, len(bars)):
            b = bars[j]
            if b.low <= setup.stop_price:
                exit_price = setup.stop_price
                exit_reason = "stop"
                break
            if b.high >= setup.target_price:
                exit_price = setup.target_price
                exit_reason = "target"
                break
            bar_t = b.start.time()
            if bar_t >= force_flat:
                exit_price = b.close
                exit_reason = "force_flat"
                break
        else:
            exit_price = bars[-1].close
        gross = (exit_price - setup.entry_price) * qty
        commission = self.commission_per_share * qty * 2
        pnl = gross - commission
        risk = setup.entry_price - setup.stop_price
        r = (exit_price - setup.entry_price) / risk if risk > 0 else 0.0
        return ORBTradeResult(
            symbol=setup.symbol,
            session_date=setup.opening_range.session_date,
            model=setup.model.value,
            direction=setup.direction.value,
            entry_price=setup.entry_price,
            stop_price=setup.stop_price,
            target_price=setup.target_price,
            exit_price=round(exit_price, 4),
            exit_reason=exit_reason,
            quantity=qty,
            r_multiple=round(r, 4),
            pnl=round(pnl, 2),
        )
