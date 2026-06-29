"""Opening Range Breakout (ORB) backtest lab API and page.

Lets a trader run ORB backtests, parameter sweeps, classify readiness, and save
evidence without writing Python. Backtest-only: no TWS connection, no live or
paper order placement. Promotion to paper still requires saved evidence (or an
explicit, audit-logged override) enforced elsewhere.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from flask import Blueprint, jsonify, render_template, request

from autonomous.opening_range import Candle, OpeningRangeConfig
from autonomous.orb_backtest_reports import (
    ReadinessCriteria,
    classify_readiness,
    run_backtest,
    run_sweep,
    save_evidence,
)

logger = logging.getLogger(__name__)

bp = Blueprint("api_opening_range", __name__, url_prefix="/api/opening-range")
page_bp = Blueprint("opening_range", __name__, url_prefix="/opening-range")


@page_bp.route("/backtest")
def backtest_page():
    return render_template(
        "opening_range/backtest.html",
        title="ORB Backtest Lab",
        active_page="opening_range",
        defaults=OpeningRangeConfig(),
    )


def _config_from(data: dict) -> OpeningRangeConfig:
    cfg = OpeningRangeConfig()
    model = str(data.get("model", "AB")).upper()
    cfg.model_a_enabled = model in ("A", "AB")
    cfg.model_b_enabled = model in ("B", "AB")
    for key in (
        "entry_cutoff_time", "force_flat_time", "continuation_rr",
        "retest_tolerance_bps", "max_entry_slippage_bps",
        "risk_per_trade_equity_pct", "max_total_orb_trades_per_session",
    ):
        if data.get(key) is not None:
            setattr(cfg, key, data[key])
    if data.get("symbols"):
        cfg.symbols = [str(s).strip().upper() for s in data["symbols"] if str(s).strip()]
    return cfg


def _candles_from_inline(rows: List[dict]) -> List[Candle]:
    out: List[Candle] = []
    for r in rows:
        start = datetime.fromisoformat(r["start"])
        out.append(Candle(
            symbol=str(r["symbol"]).upper(),
            timeframe="1m",
            start=start,
            end=start + timedelta(minutes=1),
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]),
            volume=float(r.get("volume", 0.0)),
        ))
    return out


def _fetch_candles(symbols, start, end) -> List[Candle]:
    """Fetch 1-minute candles via yfinance (no TWS connection required)."""
    try:
        import yfinance as yf  # type: ignore[import]
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("yfinance not available for 1m candle fetch") from exc
    candles: List[Candle] = []
    for symbol in symbols:
        sym = str(symbol).strip().upper()
        if not sym:
            continue
        hist = yf.download(sym, start=start, end=end, interval="1m",
                           auto_adjust=False, progress=False)
        if hist is None or hist.empty:
            continue
        if getattr(hist.columns, "nlevels", 1) > 1:
            hist.columns = [c[0] if isinstance(c, tuple) else c for c in hist.columns]
        for ts, row in hist.iterrows():
            start_dt = ts.to_pydatetime()
            candles.append(Candle(sym, "1m", start_dt, start_dt + timedelta(minutes=1),
                                  float(row["Open"]), float(row["High"]),
                                  float(row["Low"]), float(row["Close"]),
                                  float(row.get("Volume", 0.0))))
    return candles


def _load_candles(data: dict) -> List[Candle]:
    candles: List[Candle] = []
    if data.get("candles"):
        return _candles_from_inline(data["candles"])
    symbols = data.get("symbols") or ["QQQ", "SPY"]
    start = data.get("start") or (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
    end = data.get("end") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _fetch_candles(symbols, start, end)


def _criteria_from(data: dict) -> ReadinessCriteria:
    c = ReadinessCriteria()
    for key in ("min_trade_count", "min_avg_r", "max_drawdown_r",
                "max_slippage_sensitivity_r", "max_no_data_failures"):
        if data.get(key) is not None:
            setattr(c, key, data[key])
    return c


@bp.route("/backtest/run", methods=["POST"])
def run():
    data = request.get_json(silent=True) or {}
    try:
        candles = _load_candles(data)
    except RuntimeError as exc:
        logger.warning("ORB backtest data load failed: %s", exc)
        return jsonify({"error": "could not load candle data"}), 400
    cfg = _config_from(data)
    equity = float(data.get("equity", 100_000.0))
    commission = float(data.get("commission_per_share", 0.005))
    report = run_backtest(candles, cfg, equity=equity, commission_per_share=commission)
    readiness = classify_readiness(report, _criteria_from(data.get("criteria") or {}))
    return jsonify({"report": report, "readiness": readiness})


@bp.route("/backtest/sweep", methods=["POST"])
def sweep():
    data = request.get_json(silent=True) or {}
    try:
        candles = _load_candles(data)
    except RuntimeError as exc:
        logger.warning("ORB sweep data load failed: %s", exc)
        return jsonify({"error": "could not load candle data"}), 400
    cfg = _config_from(data)
    grid = data.get("sweep") or {}
    results = run_sweep(
        candles, cfg,
        entry_cutoff_times=grid.get("entry_cutoff_time"),
        continuation_rrs=grid.get("continuation_rr"),
        retest_tolerances_bps=grid.get("retest_tolerance_bps"),
        max_entry_slippages_bps=grid.get("max_entry_slippage_bps"),
        models=grid.get("model"),
        equity=float(data.get("equity", 100_000.0)),
        commission_per_share=float(data.get("commission_per_share", 0.005)),
    )
    crit = _criteria_from(data.get("criteria") or {})
    for r in results:
        r["readiness"] = classify_readiness(r["report"], crit)
    return jsonify({"count": len(results), "results": results})


@bp.route("/backtest/save-evidence", methods=["POST"])
def save():
    data = request.get_json(silent=True) or {}
    report = data.get("report")
    if not report:
        return jsonify({"error": "report required"}), 400
    readiness = data.get("readiness") or classify_readiness(report)
    path = save_evidence(report, readiness, symbols=data.get("symbols"),
                         params=data.get("params"))
    return jsonify({"saved": True, "path": path, "readiness": readiness})
