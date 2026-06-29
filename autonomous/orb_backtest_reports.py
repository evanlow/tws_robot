"""ORB backtest reporting, parameter sweeps, and readiness classification.

Turns the Phase-1 :class:`backtest.opening_range_strategy.OpeningRangeBacktest`
runner into a research workflow that a trader can drive without writing Python:
rich performance reports, comparable parameter sweeps, conservative readiness
classification, and durable JSONL evidence the paper-promotion gate can require.

Safety posture (Prime Directive): backtest-only. No broker, TWS, or live/paper
order placement happens here. Saved evidence is a *prerequisite* for promotion,
never an approval; promotion still requires explicit operator/audit steps
elsewhere.
"""

from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from autonomous.opening_range import Candle, ORBEntryModel, OpeningRangeConfig
from backtest.opening_range_strategy import (
    ORBBacktestResult,
    ORBTradeResult,
    OpeningRangeBacktest,
)

SCHEMA_VERSION = 1

# Default per-share commission used as a sensitivity bump floor.
DEFAULT_COMMISSION_PER_SHARE = 0.005

# Readiness statuses.
READY_FOR_PAPER = "READY_FOR_PAPER"
NEEDS_MORE_DATA = "NEEDS_MORE_DATA"
DO_NOT_TRADE = "DO_NOT_TRADE"


@dataclass
class ReadinessCriteria:
    """Conservative, configurable thresholds for readiness classification."""

    min_trade_count: int = 30
    min_avg_r: float = 0.0  # non-negative average R after costs
    max_drawdown_r: float = 6.0  # below threshold (in R)
    max_slippage_sensitivity_r: float = 0.5  # catastrophic if avg R degrades more
    max_no_data_failures: int = 0  # excessive no-data / invalid-range failures

    def as_dict(self) -> dict:
        return {
            "min_trade_count": self.min_trade_count,
            "min_avg_r": self.min_avg_r,
            "max_drawdown_r": self.max_drawdown_r,
            "max_slippage_sensitivity_r": self.max_slippage_sensitivity_r,
            "max_no_data_failures": self.max_no_data_failures,
        }


def _profit_factor(trades: Sequence[ORBTradeResult]) -> float:
    gains = sum(t.pnl for t in trades if t.pnl > 0)
    losses = -sum(t.pnl for t in trades if t.pnl < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _max_drawdown_r(trades: Sequence[ORBTradeResult]) -> float:
    """Peak-to-trough drawdown of the cumulative R curve (positive value)."""
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for t in trades:
        cum += t.r_multiple
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return round(max_dd, 4)


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _net_r(t: ORBTradeResult) -> float:
    """Net R after costs: realized pnl over per-trade risk (entry-stop)*qty."""
    risk_capital = (t.entry_price - t.stop_price) * t.quantity
    if risk_capital <= 0:
        return 0.0
    return t.pnl / risk_capital


def _bucket(trades: Sequence[ORBTradeResult]) -> dict:
    n = len(trades)
    rs = [t.r_multiple for t in trades]
    holds = [t.hold_minutes for t in trades if t.hold_minutes is not None]
    return {
        "trades": n,
        "win_rate": (sum(1 for t in trades if t.pnl > 0) / n) if n else 0.0,
        "total_pnl": round(sum(t.pnl for t in trades), 2),
        "avg_r": round(_avg(rs), 4),
        "median_r": round(_median(rs), 4),
        "profit_factor": _profit_factor(trades),
        "max_drawdown_r": _max_drawdown_r(trades),
        "avg_hold_minutes": round(_avg(holds), 2),
    }


def _model_label(name: str) -> str:
    if name.startswith("MODEL_A"):
        return "MODEL_A"
    if name.startswith("MODEL_B"):
        return "MODEL_B"
    return name


def build_report(
    result: ORBBacktestResult,
    config: Optional[OpeningRangeConfig] = None,
    *,
    commission_per_share: float = 0.005,
    no_trade_reasons: Optional[Sequence[str]] = None,
    slippage_sensitivity_r: float = 0.0,
    commission_sensitivity_r: float = 0.0,
) -> dict:
    """Build the full ORB backtest report dictionary from a result."""

    cfg = config or OpeningRangeConfig()
    tz = cfg.tzinfo()
    trades = list(result.trades)
    rs = [t.r_multiple for t in trades]
    net_rs = [_net_r(t) for t in trades]
    holds = [t.hold_minutes for t in trades if t.hold_minutes is not None]

    by_model: Dict[str, List[ORBTradeResult]] = defaultdict(list)
    by_symbol: Dict[str, List[ORBTradeResult]] = defaultdict(list)
    by_hour: Dict[int, List[ORBTradeResult]] = defaultdict(list)
    for t in trades:
        by_model[_model_label(t.model)].append(t)
        by_symbol[t.symbol].append(t)
        if t.entry_time is not None:
            et = t.entry_time
            ny = et.astimezone(tz) if et.tzinfo is not None else et
            by_hour[ny.hour].append(t)

    reasons = Counter(no_trade_reasons or [])

    return {
        "total_trades": len(trades),
        "win_rate": round(result.win_rate, 4),
        "avg_r": round(_avg(rs), 4),
        "median_r": round(_median(rs), 4),
        "avg_net_r": round(_avg(net_rs), 4),
        "total_pnl": round(result.total_pnl, 2),
        "profit_factor": _profit_factor(trades),
        "max_drawdown_r": _max_drawdown_r(trades),
        "avg_hold_minutes": round(_avg(holds), 2),
        "by_model": {m: _bucket(ts) for m, ts in by_model.items()},
        "by_symbol": {s: _bucket(ts) for s, ts in by_symbol.items()},
        "by_hour": {str(h): _bucket(ts) for h, ts in sorted(by_hour.items())},
        "slippage_sensitivity_r": round(slippage_sensitivity_r, 4),
        "commission_sensitivity_r": round(commission_sensitivity_r, 4),
        "no_trade_reasons": dict(reasons),
    }


def run_backtest(
    candles_1m: Sequence[Candle],
    config: Optional[OpeningRangeConfig] = None,
    *,
    equity: float = 100_000.0,
    commission_per_share: float = 0.005,
) -> dict:
    """Run an ORB backtest and return a report including sensitivities."""

    cfg = config or OpeningRangeConfig()
    base = OpeningRangeBacktest(cfg, equity=equity, commission_per_share=commission_per_share)
    result = base.run(list(candles_1m))
    base_net = _avg([_net_r(t) for t in result.trades])

    # Slippage sensitivity: widen entry slippage and measure net-R degradation.
    worse_slip = replace(cfg, max_entry_slippage_bps=cfg.max_entry_slippage_bps * 2 + 1)
    slip_res = OpeningRangeBacktest(worse_slip, equity=equity,
                                    commission_per_share=commission_per_share).run(list(candles_1m))
    slip_sens = base_net - _avg([_net_r(t) for t in slip_res.trades])

    # Commission sensitivity: double commission and measure net-R degradation.
    bumped_commission = commission_per_share * 2 + DEFAULT_COMMISSION_PER_SHARE
    comm_res = OpeningRangeBacktest(cfg, equity=equity,
                                    commission_per_share=bumped_commission).run(list(candles_1m))
    comm_sens = base_net - _avg([_net_r(t) for t in comm_res.trades])

    return build_report(
        result, cfg,
        commission_per_share=commission_per_share,
        no_trade_reasons=result.no_trade_reasons,
        slippage_sensitivity_r=slip_sens,
        commission_sensitivity_r=comm_sens,
    )


def _model_flags(model: str) -> dict:
    if model == "A":
        return {"model_a_enabled": True, "model_b_enabled": False}
    if model == "B":
        return {"model_a_enabled": False, "model_b_enabled": True}
    return {"model_a_enabled": True, "model_b_enabled": True}


def run_sweep(
    candles_1m: Sequence[Candle],
    base_config: Optional[OpeningRangeConfig] = None,
    *,
    entry_cutoff_times: Optional[Sequence[str]] = None,
    continuation_rrs: Optional[Sequence[float]] = None,
    retest_tolerances_bps: Optional[Sequence[float]] = None,
    max_entry_slippages_bps: Optional[Sequence[float]] = None,
    models: Optional[Sequence[str]] = None,
    equity: float = 100_000.0,
    commission_per_share: float = 0.005,
) -> List[dict]:
    """Run comparable backtests across a simple grid of parameters."""

    cfg = base_config or OpeningRangeConfig()
    variants: List[tuple] = []
    for cutoff in (entry_cutoff_times or [cfg.entry_cutoff_time]):
        for rr in (continuation_rrs or [cfg.continuation_rr]):
            for retest in (retest_tolerances_bps or [cfg.retest_tolerance_bps]):
                for slip in (max_entry_slippages_bps or [cfg.max_entry_slippage_bps]):
                    for model in (models or ["AB"]):
                        variant = replace(
                            cfg,
                            entry_cutoff_time=cutoff,
                            continuation_rr=rr,
                            retest_tolerance_bps=retest,
                            max_entry_slippage_bps=slip,
                            **_model_flags(model),
                        )
                        params = {
                            "entry_cutoff_time": cutoff,
                            "continuation_rr": rr,
                            "retest_tolerance_bps": retest,
                            "max_entry_slippage_bps": slip,
                            "model": model,
                        }
                        variants.append((params, variant))

    out: List[dict] = []
    for params, variant in variants:
        report = run_backtest(candles_1m, variant, equity=equity,
                              commission_per_share=commission_per_share)
        out.append({"params": params, "report": report})
    return out


def classify_readiness(report: dict, criteria: Optional[ReadinessCriteria] = None) -> dict:
    """Classify a backtest report as READY_FOR_PAPER / NEEDS_MORE_DATA / DO_NOT_TRADE."""

    c = criteria or ReadinessCriteria()
    reasons: List[str] = []
    blocking = False

    total = report.get("total_trades", 0)
    avg_r = report.get("avg_net_r", report.get("avg_r", 0.0))
    dd = report.get("max_drawdown_r", 0.0)
    slip = report.get("slippage_sensitivity_r", 0.0)
    no_data = sum(
        v for k, v in (report.get("no_trade_reasons") or {}).items()
        if "no_data" in k or "invalid" in k or "range_width_zero" in k
    )

    # DO_NOT_TRADE (blocking) conditions.
    if avg_r < c.min_avg_r:
        reasons.append(f"avg_net_r {avg_r} below minimum {c.min_avg_r}")
        blocking = True
    if dd > c.max_drawdown_r:
        reasons.append(f"max_drawdown_r {dd} above threshold {c.max_drawdown_r}")
        blocking = True
    if slip > c.max_slippage_sensitivity_r:
        reasons.append(f"slippage sensitivity {slip} above {c.max_slippage_sensitivity_r}")
        blocking = True

    if blocking:
        status = DO_NOT_TRADE
    elif total < c.min_trade_count or no_data > c.max_no_data_failures:
        status = NEEDS_MORE_DATA
        if total < c.min_trade_count:
            reasons.append(f"trades {total} below minimum {c.min_trade_count}")
        if no_data > c.max_no_data_failures:
            reasons.append(f"no-data/invalid failures {no_data} above {c.max_no_data_failures}")
    else:
        status = READY_FOR_PAPER

    return {"status": status, "reasons": reasons, "criteria": c.as_dict()}


def save_evidence(report: dict, readiness: dict, *, log_dir: str = "logs",
                  symbols: Optional[Sequence[str]] = None, params: Optional[dict] = None) -> str:
    """Append a backtest evidence record to ``logs/orb_backtest_evidence_YYYYMMDD.jsonl``."""

    ts = datetime.now(timezone.utc)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    path = os.path.join(log_dir, f"orb_backtest_evidence_{ts.strftime('%Y%m%d')}.jsonl")
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": "orb_backtest",
        "timestamp": ts.isoformat(),
        "symbols": list(symbols or []),
        "params": params or {},
        "report": report,
        "readiness": readiness,
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return path
