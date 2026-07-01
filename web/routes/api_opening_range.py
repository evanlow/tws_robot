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

from flask import Blueprint, current_app, has_app_context, jsonify, render_template, request

from autonomous.opening_range import Candle, OpeningRangeConfig
from autonomous.orb_backtest_reports import (
    ReadinessCriteria,
    classify_readiness,
    run_backtest,
    run_sweep,
    save_evidence,
)
from autonomous.orb_session_manager import ORBSessionManager, ORBValidationError
from autonomous.orb_proposals import (
    ExpiryReason,
    ORBProposalStore,
    ProposalError,
    ProposalNotFoundError,
)
from autonomous.orb_execution import (
    ORBBlockReason,
    ORBExecutionBlocked,
    ORBExecutionError,
    ORBExecutionMode,
    ORBPaperExecutor,
)
from autonomous.orb_session_manager import ORBMode

logger = logging.getLogger(__name__)

bp = Blueprint("api_opening_range", __name__, url_prefix="/api/opening-range")
orb_bp = Blueprint("api_orb", __name__, url_prefix="/api/orb")
page_bp = Blueprint("opening_range", __name__, url_prefix="/opening-range")

_manager: Optional[ORBSessionManager] = None
_proposal_store: Optional[ORBProposalStore] = None
_executor: Optional[ORBPaperExecutor] = None


def get_manager() -> ORBSessionManager:
    """Lazily build the singleton ORB session manager.

    Honors ``orb_config_dir`` / ``orb_evidence_dir`` app config for test
    isolation; defaults to the production config/logs directories.
    """
    global _manager
    if _manager is None:
        cfg = current_app.config if has_app_context() else {}
        _manager = ORBSessionManager(
            config_dir=cfg.get("orb_config_dir", "config"),
            evidence_dir=cfg.get("orb_evidence_dir", "logs"),
        )
    return _manager


def get_proposal_store() -> ORBProposalStore:
    """Lazily build the singleton recommend-only ORB proposal store.

    Honors ``orb_evidence_dir`` app config (audit log directory) for test
    isolation; defaults to the production logs directory.
    """
    global _proposal_store
    if _proposal_store is None:
        cfg = current_app.config if has_app_context() else {}
        _proposal_store = ORBProposalStore(log_dir=cfg.get("orb_evidence_dir", "logs"))
    return _proposal_store


def get_executor() -> ORBPaperExecutor:
    """Lazily build the singleton ORB paper executor (paper trades only).

    Honors ``orb_evidence_dir`` app config (audit log directory) for test
    isolation. The exit-manager fallback stays disabled unless explicitly
    enabled via the ``orb_allow_exit_manager_fallback`` app config so missing
    broker-visible protection is rejected by default.
    """
    global _executor
    if _executor is None:
        cfg = current_app.config if has_app_context() else {}
        _executor = ORBPaperExecutor(
            get_proposal_store(),
            log_dir=cfg.get("orb_evidence_dir", "logs"),
            allow_exit_manager_fallback=bool(
                cfg.get("orb_allow_exit_manager_fallback", False)
            ),
        )
    return _executor


@page_bp.route("/backtest")
def backtest_page():
    return render_template(
        "opening_range/backtest.html",
        title="ORB Backtest Lab",
        active_page="opening_range_backtest",
        defaults=OpeningRangeConfig(),
    )


@page_bp.route("/")
def index():
    return render_template(
        "opening_range/index.html",
        title="ORB Autonomous Session",
        active_page="opening_range",
        defaults=OpeningRangeConfig(),
    )


def _config_from(data: dict) -> OpeningRangeConfig:
    cfg = OpeningRangeConfig()
    model = str(data.get("model", "AB")).upper()
    cfg.model_a_enabled = model in ("A", "AB")
    cfg.model_b_enabled = model in ("B", "AB")
    for key in ("entry_cutoff_time", "force_flat_time"):
        if data.get(key) is not None:
            setattr(cfg, key, str(data[key]))
    for key in (
        "continuation_rr",
        "retest_tolerance_bps",
        "max_entry_slippage_bps",
        "risk_per_trade_equity_pct",
    ):
        if data.get(key) is not None:
            setattr(cfg, key, float(data[key]))
    if data.get("max_total_orb_trades_per_session") is not None:
        cfg.max_total_orb_trades_per_session = int(data["max_total_orb_trades_per_session"])
    if data.get("symbols"):
        cfg.symbols = [str(s).strip().upper() for s in data["symbols"] if str(s).strip()]
    return cfg


def _candles_from_inline(rows: List[dict]) -> List[Candle]:
    out: List[Candle] = []
    for r in rows:
        start_raw = str(r["start"])
        start = datetime.fromisoformat(
            f"{start_raw[:-1]}+00:00" if start_raw.endswith("Z") else start_raw
        )
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
    for key in ("min_trade_count", "max_no_data_failures"):
        if data.get(key) is not None:
            setattr(c, key, int(data[key]))
    for key in ("min_avg_r", "max_drawdown_r", "max_slippage_sensitivity_r"):
        if data.get(key) is not None:
            setattr(c, key, float(data[key]))
    return c


@bp.route("/backtest/run", methods=["POST"])
def run():
    data = request.get_json(silent=True) or {}
    try:
        candles = _load_candles(data)
        cfg = _config_from(data)
        equity = float(data.get("equity", 100_000.0))
        commission = float(data.get("commission_per_share", 0.005))
        report = run_backtest(candles, cfg, equity=equity, commission_per_share=commission)
        readiness = classify_readiness(report, _criteria_from(data.get("criteria") or {}))
        return jsonify({"report": report, "readiness": readiness})
    except RuntimeError as exc:
        logger.warning("ORB backtest data load failed: %s", exc)
        return jsonify({"error": "Unable to load candle data; check symbols and date range"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid request payload"}), 400
    except Exception:
        logger.exception("ORB backtest run failed")
        return jsonify({"error": "Backtest run failed"}), 400


@bp.route("/backtest/sweep", methods=["POST"])
def sweep():
    data = request.get_json(silent=True) or {}
    try:
        candles = _load_candles(data)
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
    except RuntimeError as exc:
        logger.warning("ORB sweep data load failed: %s", exc)
        return jsonify({"error": "Unable to load candle data; check symbols and date range"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid request payload"}), 400
    except Exception:
        logger.exception("ORB backtest sweep failed")
        return jsonify({"error": "Backtest sweep failed"}), 400


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


# ---------------------------------------------------------------------------
# ORB strategy configuration & autonomous session controls (Phase 2.3, #207)
# These manage trader-facing config, mode, and arm/disarm state only. No paper
# or live order is placed here; live modes are locked and paper-autonomous is
# gated on readiness. All control actions are audit logged.
# ---------------------------------------------------------------------------


@orb_bp.route("/strategies", methods=["GET"])
def list_orb_strategies():
    return jsonify({"strategies": get_manager().list_strategies()})


@orb_bp.route("/strategies", methods=["POST"])
def create_orb_strategy():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(get_manager().upsert_strategy(data)), 201
    except ORBValidationError as exc:
        return jsonify({"error": "validation_failed", "messages": exc.errors}), 400


@orb_bp.route("/strategies/<name>", methods=["GET"])
def get_orb_strategy(name):
    rec = get_manager().get_strategy(name)
    if rec is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(rec)


@orb_bp.route("/strategies/<name>", methods=["PUT"])
def update_orb_strategy(name):
    data = request.get_json(silent=True) or {}
    data["name"] = name
    try:
        return jsonify(get_manager().upsert_strategy(data))
    except ORBValidationError as exc:
        return jsonify({"error": "validation_failed", "messages": exc.errors}), 400


@orb_bp.route("/strategies/<name>/arm", methods=["POST"])
def arm_orb_strategy(name):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(get_manager().arm(name, when=str(data.get("when", "today"))))
    except ORBValidationError as exc:
        return jsonify({"error": "validation_failed", "messages": exc.errors}), 400


@orb_bp.route("/strategies/<name>/disarm", methods=["POST"])
def disarm_orb_strategy(name):
    try:
        return jsonify(get_manager().disarm(name))
    except ORBValidationError as exc:
        return jsonify({"error": "validation_failed", "messages": exc.errors}), 400


@orb_bp.route("/strategies/<name>/disable-today", methods=["POST"])
def disable_orb_today(name):
    try:
        return jsonify(get_manager().disable_today(name))
    except ORBValidationError as exc:
        return jsonify({"error": "validation_failed", "messages": exc.errors}), 400


@orb_bp.route("/emergency-stop", methods=["POST"])
def emergency_stop_orb():
    # Disarm all sessions and block any in-flight ORB paper execution.
    get_executor().trip_emergency_stop()
    return jsonify(get_manager().emergency_stop())


@orb_bp.route("/status", methods=["GET"])
def orb_status():
    return jsonify(get_manager().status())


# ---------------------------------------------------------------------------
# ORB recommend-only proposals (Phase 2.4, #208)
# Transparent trade cards showing what ORB would do before any order is placed.
# Read-only plus skip/expire lifecycle controls; every action is audit logged.
# The execute-paper endpoint is intentionally reserved for the paper-execution
# phase. No paper or live order is placed here.
# ---------------------------------------------------------------------------


@orb_bp.route("/proposals", methods=["GET"])
def list_orb_proposals():
    args = request.args
    store = get_proposal_store()
    # Surface any past-cutoff proposals as expired before listing.
    store.expire_due()
    proposals = store.list(
        status=args.get("status"),
        symbol=args.get("symbol"),
        strategy_name=args.get("strategy"),
    )
    return jsonify({"proposals": [p.to_dict() for p in proposals]})


@orb_bp.route("/proposals/<proposal_id>", methods=["GET"])
def get_orb_proposal(proposal_id):
    store = get_proposal_store()
    # Self-heal: surface a past-cutoff proposal as expired even on a direct read.
    store.expire_due()
    proposal = store.get(proposal_id)
    if proposal is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(proposal.to_dict())


@orb_bp.route("/proposals/<proposal_id>/skip", methods=["POST"])
def skip_orb_proposal(proposal_id):
    data = request.get_json(silent=True) or {}
    try:
        proposal = get_proposal_store().skip(proposal_id, reason=data.get("reason"))
        return jsonify(proposal.to_dict())
    except ProposalNotFoundError:
        return jsonify({"error": "not found"}), 404
    except ProposalError:
        return jsonify({"error": "cannot skip proposal in its current state"}), 400


@orb_bp.route("/proposals/<proposal_id>/expire", methods=["POST"])
def expire_orb_proposal(proposal_id):
    data = request.get_json(silent=True) or {}
    try:
        reason = ExpiryReason(str(data.get("reason", ExpiryReason.MANUAL.value)))
    except ValueError:
        reason = ExpiryReason.MANUAL
    try:
        proposal = get_proposal_store().expire(proposal_id, reason=reason)
        return jsonify(proposal.to_dict())
    except ProposalNotFoundError:
        return jsonify({"error": "not found"}), 404
    except ProposalError:
        return jsonify({"error": "cannot expire proposal in its current state"}), 400


# ---------------------------------------------------------------------------
# ORB paper-autonomous execution (Phase 2.5, #209)
# Wires a valid recommend-only proposal into a *paper* trade with mandatory
# stop/target protection. Paper only: there is no live execution path here.
# Execution requires the owning strategy to be in paper_autonomous mode; raw
# market orders are impossible; missing protection is rejected outside the
# explicitly configured paper fallback; emergency stop and the session cap both
# block execution; and duplicate execution of a proposal is idempotent.
# ---------------------------------------------------------------------------


def _session_cap_for(rec) -> int:
    """Per-session ORB paper-trade cap from the strategy config (default 1)."""
    params = (rec or {}).get("parameters") or {}
    try:
        return max(1, int(params.get("max_total_orb_trades_per_session", 1)))
    except (TypeError, ValueError):
        return 1


@orb_bp.route("/proposals/<proposal_id>/execute-paper", methods=["POST"])
def execute_orb_proposal_paper(proposal_id):
    store = get_proposal_store()
    # Surface any past-cutoff proposals as expired before attempting execution.
    store.expire_due()
    proposal = store.get(proposal_id)
    if proposal is None:
        return jsonify({"error": "not found"}), 404

    # Emergency stop is the highest-priority block and takes precedence over the
    # mode/arming gates below (which would otherwise report the disarmed state).
    if get_executor().emergency_stopped:
        return jsonify({"error": "execution blocked",
                        "reason": ORBBlockReason.EMERGENCY_STOP.value}), 409

    # Recommend-only mode never submits orders: the owning strategy must be in
    # paper_autonomous mode for any paper trade to be placed.
    rec = get_manager().get_strategy(proposal.strategy_name)
    if rec is None:
        return jsonify({
            "error": "unknown strategy",
            "detail": f"no ORB strategy named '{proposal.strategy_name}'",
        }), 400
    mode = getattr(rec.get("mode"), "value", rec.get("mode"))
    if mode != ORBMode.PAPER_AUTONOMOUS.value:
        return jsonify({
            "error": "paper_autonomous mode required",
            "detail": (
                "ORB paper execution requires the strategy to be in "
                "paper_autonomous mode; recommend-only never submits orders"
            ),
            "mode": mode,
        }), 400

    # Paper-autonomous mode alone is not sufficient: the trader must have armed
    # the ORB session (where readiness/evidence gates are enforced) for the
    # proposal's session date. This keeps execution behind the dashboard arming
    # workflow rather than mode selection.
    session = rec.get("session") or {}
    if not session.get("armed"):
        return jsonify({
            "error": "orb session not armed",
            "detail": (
                "ORB paper execution requires the strategy to be armed for "
                "the proposal session"
            ),
        }), 400
    if session.get("armed_for") != proposal.session_date:
        return jsonify({
            "error": "orb session date mismatch",
            "detail": (
                f"strategy is armed for {session.get('armed_for')}, "
                f"but proposal is for {proposal.session_date}"
            ),
        }), 400
    if session.get("disabled_today"):
        return jsonify({"error": "orb disabled for session"}), 400

    try:
        trade = get_executor().execute_paper(
            proposal,
            mode=ORBExecutionMode.PAPER_AUTONOMOUS,
            session_cap=_session_cap_for(rec),
        )
        return jsonify(trade.to_dict()), 201
    except ORBExecutionBlocked as exc:
        # Surface the structured block reason only; the exception message is
        # logged server-side rather than returned to avoid leaking internals.
        logger.info("ORB paper execution blocked (%s): %s", exc.reason.value, exc)
        return jsonify({"error": "execution blocked",
                        "reason": exc.reason.value}), 409
    except ORBExecutionError as exc:
        logger.info("ORB paper execution rejected: %s", exc)
        return jsonify({"error": "cannot execute proposal"}), 400


@orb_bp.route("/trades", methods=["GET"])
def list_orb_trades():
    args = request.args
    trades = get_executor().list_trades(
        symbol=args.get("symbol"),
        strategy_name=args.get("strategy"),
        session_date=args.get("session_date"),
    )
    return jsonify({"trades": [t.to_dict() for t in trades]})


@orb_bp.route("/trades/<trade_id>", methods=["GET"])
def get_orb_trade(trade_id):
    trade = get_executor().get_trade(trade_id)
    if trade is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(trade.to_dict())
