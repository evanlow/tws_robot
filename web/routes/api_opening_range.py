"""Opening Range Breakout (ORB) backtest lab API and page.

Lets a trader run ORB backtests, parameter sweeps, classify readiness, and save
evidence without writing Python. Backtest-only: no TWS connection, no live or
paper order placement. Promotion to paper still requires saved evidence (or an
explicit, audit-logged override) enforced elsewhere.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from autonomous.orb_exit_manager import ORBExitManager, ORBExitManagerError
from autonomous.orb_session_review import ORBSessionReviewStore, parse_session_id
from autonomous.orb_evidence import build_rejection_ledger
from autonomous.orb_live_readiness import (
    ASSISTED_LIVE_CANDIDATE,
    ASSISTED_LIVE_MODE,
    TINY_LIVE_CANDIDATE_MODE,
    ORBLiveReadinessConfirmationStore,
    ORBLiveReadinessInput,
    TinyLiveRiskCaps,
    compute_avg_entry_slippage_bps,
    compute_r_stats,
    evaluate_orb_live_readiness,
)
from autonomous.orb_live_order_rehearsal import (
    ORBAssistedLiveRefusal,
    ORBAssistedLiveRehearsalStore,
    build_assisted_live_rehearsal_package,
)
from autonomous.runner_config import AutonomousLiveRunnerConfig

logger = logging.getLogger(__name__)

bp = Blueprint("api_opening_range", __name__, url_prefix="/api/opening-range")
orb_bp = Blueprint("api_orb", __name__, url_prefix="/api/orb")
page_bp = Blueprint("opening_range", __name__, url_prefix="/opening-range")

_manager: Optional[ORBSessionManager] = None
_proposal_store: Optional[ORBProposalStore] = None
_executor: Optional[ORBPaperExecutor] = None
_exit_manager: Optional[ORBExitManager] = None
_review_store: Optional[ORBSessionReviewStore] = None
_live_readiness_confirmations: Optional[ORBLiveReadinessConfirmationStore] = None
_assisted_live_rehearsals: Optional[ORBAssistedLiveRehearsalStore] = None


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


def get_exit_manager() -> ORBExitManager:
    """Lazily build the singleton ORB intraday exit manager (Phase 2.6, #210).

    Honors ``orb_evidence_dir`` app config (audit log directory) for test
    isolation. ``orb_price_provider`` may be set in app config to a
    ``callable(symbol) -> Optional[float]`` for live/backtest price wiring;
    it defaults to returning ``None`` (no price available) so exits are never
    guessed from a fabricated source.
    """
    global _exit_manager
    if _exit_manager is None:
        cfg = current_app.config if has_app_context() else {}
        price_provider = cfg.get("orb_price_provider")
        _exit_manager = ORBExitManager(
            log_dir=cfg.get("orb_evidence_dir", "logs"),
            price_provider=price_provider if callable(price_provider) else None,
        )
    return _exit_manager


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


def get_review_store() -> ORBSessionReviewStore:
    """Lazily build the singleton ORB session-review/evidence store (#211).

    Honors ``orb_config_dir`` (notes persistence) and ``orb_evidence_dir``
    (audit log source) app config for test isolation.
    """
    global _review_store
    if _review_store is None:
        cfg = current_app.config if has_app_context() else {}
        _review_store = ORBSessionReviewStore(
            config_dir=cfg.get("orb_config_dir", "config"),
            evidence_dir=cfg.get("orb_evidence_dir", "logs"),
        )
    return _review_store


def get_live_readiness_confirmation_store() -> ORBLiveReadinessConfirmationStore:
    """Lazily build the singleton live-readiness confirmation store (#213).

    Honors ``orb_evidence_dir`` app config for test isolation. Confirmations
    are only ever written via the ``POST`` confirm endpoint below; the
    read-only ``GET`` readiness endpoint may only read from this store.
    """
    global _live_readiness_confirmations
    if _live_readiness_confirmations is None:
        cfg = current_app.config if has_app_context() else {}
        log_dir = cfg.get("orb_evidence_dir", "logs")
        _live_readiness_confirmations = ORBLiveReadinessConfirmationStore(
            path=str(Path(log_dir) / "orb_live_readiness_confirmations.json"),
        )
    return _live_readiness_confirmations


def get_assisted_live_rehearsal_store() -> ORBAssistedLiveRehearsalStore:
    """Lazily build the singleton assisted-live rehearsal store (Phase 5, #227).

    In-memory only; every rehearsal package it holds was already validated
    and audit-logged by :func:`build_assisted_live_rehearsal_package` before
    reaching this store. No order is ever placed here.
    """
    global _assisted_live_rehearsals
    if _assisted_live_rehearsals is None:
        _assisted_live_rehearsals = ORBAssistedLiveRehearsalStore()
    return _assisted_live_rehearsals


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


@page_bp.route("/review")
def review_page():
    return render_template(
        "opening_range/review.html",
        title="ORB Session Review",
        active_page="opening_range_review",
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
                         params=data.get("params"), strategy_name=data.get("strategy_name"))
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
    # Disarm all sessions, block any in-flight ORB paper execution, and
    # flatten every open ORB intraday trade.
    get_executor().trip_emergency_stop()
    get_exit_manager().trip_emergency_stop()
    for decision in get_exit_manager().evaluate_all():
        pass  # side effect: flattens every OPEN trade; decisions are audit-logged.
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

    # Operator gate (Phase 2.6, #210): new entries can be disabled for a
    # strategy without touching any already-open trade's exit management.
    if get_exit_manager().new_entries_disabled(proposal.strategy_name):
        return jsonify({
            "error": "new entries disabled",
            "detail": f"strategy '{proposal.strategy_name}' has new entries disabled",
        }), 400

    try:
        trade = get_executor().execute_paper(
            proposal,
            mode=ORBExecutionMode.PAPER_AUTONOMOUS,
            session_cap=_session_cap_for(rec),
        )
        params = (rec.get("parameters") or {})
        get_exit_manager().register_trade(
            trade,
            force_flat_time=str(params.get("force_flat_time", "15:55")),
            max_holding_minutes=params.get("max_holding_minutes"),
        )
        # Paper execution is fully simulated (SimulatedPaperBracketAdapter) —
        # there is no asynchronous broker fill to wait on, so the entry is
        # immediately reconciled as filled at the simulated entry price. This
        # is what moves the intraday monitor record from ENTRY_PENDING to
        # OPEN so the exit manager (which only evaluates OPEN trades) can
        # actually manage target/stop/force-flat/max-holding for it.
        get_exit_manager().mark_entry_filled(trade.trade_id, trade.entry_price)
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


# ---------------------------------------------------------------------------
# ORB intraday exit lifecycle & in-trade monitor (Phase 2.6, #210)
# Tracks each paper ORB trade from ENTRY_PENDING through OPEN/EXIT_PENDING to
# CLOSED/FAILED, evaluates target/stop/force-flat/max-holding exit triggers,
# and exposes the in-trade monitor plus close-now/cancel-entry/
# disable-new-entries operator actions. Paper only; every exit only ever
# reduces exposure and duplicate/oversell attempts are no-ops.
# ---------------------------------------------------------------------------


@orb_bp.route("/intraday-trades", methods=["GET"])
def list_orb_intraday_trades():
    args = request.args
    # Evaluate open trades for exit triggers before listing so the monitor
    # reflects the latest target/stop/force-flat/max-holding state.
    get_exit_manager().evaluate_all()
    trades = get_exit_manager().list_trades(
        symbol=args.get("symbol"),
        strategy_name=args.get("strategy"),
        session_date=args.get("session_date"),
        state=args.get("state"),
    )
    now = datetime.now(timezone.utc)
    out = []
    for t in trades:
        d = t.to_dict()
        d["force_flat_countdown_seconds"] = get_exit_manager().force_flat_countdown_seconds(
            t, now=now
        )
        out.append(d)
    return jsonify({"trades": out})


@orb_bp.route("/intraday-trades/<trade_id>", methods=["GET"])
def get_orb_intraday_trade(trade_id):
    get_exit_manager().evaluate_trade(trade_id)
    trade = get_exit_manager().get_trade(trade_id)
    if trade is None:
        return jsonify({"error": "not found"}), 404
    d = trade.to_dict()
    d["force_flat_countdown_seconds"] = get_exit_manager().force_flat_countdown_seconds(trade)
    return jsonify(d)


@orb_bp.route("/trades/<trade_id>/close-now", methods=["POST"])
def close_orb_trade_now(trade_id):
    try:
        decision = get_exit_manager().close_now(trade_id)
        return jsonify(decision.to_dict())
    except ORBExitManagerError as exc:
        logger.info("ORB close-now rejected for %s: %s", trade_id, exc)
        return jsonify({
            "error": "cannot close trade",
            "detail": "trade not found or not currently OPEN",
        }), 400


@orb_bp.route("/trades/<trade_id>/cancel-entry", methods=["POST"])
def cancel_orb_trade_entry(trade_id):
    try:
        trade = get_exit_manager().cancel_entry(trade_id)
        return jsonify(trade.to_dict())
    except ORBExitManagerError as exc:
        logger.info("ORB cancel-entry rejected for %s: %s", trade_id, exc)
        return jsonify({
            "error": "cannot cancel entry",
            "detail": "trade not found or not currently ENTRY_PENDING",
        }), 400


@orb_bp.route("/strategies/<name>/disable-new-entries", methods=["POST"])
def disable_orb_new_entries(name):
    get_exit_manager().disable_new_entries(name)
    return jsonify({"strategy": name, "new_entries_disabled": True})


@orb_bp.route("/strategies/<name>/enable-new-entries", methods=["POST"])
def enable_orb_new_entries(name):
    get_exit_manager().enable_new_entries(name)
    return jsonify({"strategy": name, "new_entries_disabled": False})


# ---------------------------------------------------------------------------
# ORB end-of-session review & evidence ledger (Phase 2.7, #211)
# Read-only reporting over the existing proposal/execution/exit audit trail:
# no order is placed or affected by anything below. Trade and no-trade
# sessions are both fully explainable from the review. Operator notes are the
# only mutation, and they never affect trading behavior.
# ---------------------------------------------------------------------------


@orb_bp.route("/review", methods=["GET"])
def orb_review():
    args = request.args
    date_str = args.get("date")
    if not date_str:
        return jsonify({"error": "date query parameter (YYYY-MM-DD) is required"}), 400
    strategy = args.get("strategy")
    store = get_review_store()
    if strategy:
        rec = get_manager().get_strategy(strategy)
        if rec is None:
            return jsonify({"error": "not found", "detail": f"unknown strategy '{strategy}'"}), 404
        return jsonify({"sessions": [store.get_review(
            strategy, date_str,
            symbols_watched=rec.get("symbols"),
            config_snapshot=rec.get("parameters"),
        )]})
    strategies = get_manager().list_strategies()
    return jsonify({"sessions": store.list_reviews_for_date(date_str, strategies)})


@orb_bp.route("/evidence/<strategy_name>", methods=["GET"])
def orb_evidence_summary(strategy_name):
    rec = get_manager().get_strategy(strategy_name)
    if rec is None:
        return jsonify({"error": "not found", "detail": f"unknown strategy '{strategy_name}'"}), 404
    symbols = rec.get("symbols")
    return jsonify(get_review_store().evidence_summary(strategy_name, symbols=symbols))


@orb_bp.route("/evidence/<strategy_name>/export", methods=["GET"])
def orb_evidence_export(strategy_name):
    fmt = request.args.get("format", "json").lower()
    if fmt not in ("json", "csv"):
        return jsonify({
            "error": "invalid_format",
            "detail": "unsupported export format; expected 'json' or 'csv'",
        }), 400
    rec = get_manager().get_strategy(strategy_name)
    if rec is None:
        return jsonify({"error": "not found", "detail": f"unknown strategy '{strategy_name}'"}), 404
    symbols = rec.get("symbols")
    try:
        content = get_review_store().export(strategy_name, fmt, symbols=symbols)
    except ValueError:
        logger.exception("ORB evidence export failed for %s", strategy_name)
        return jsonify({"error": "export_failed"}), 400
    if fmt == "csv":
        return current_app.response_class(
            content, mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="orb_evidence_{strategy_name}.csv"'},
        )
    return current_app.response_class(content, mimetype="application/json")


# ---------------------------------------------------------------------------
# ORB Phase 4 — tiny-live / assisted-live readiness gates (#213)
# Read-only evaluation of the guarded path from paper ORB evidence to
# tiny-live / assisted-live review. Never places, routes, or simulates an
# order, and never flips a live switch itself. Live remains locked unless
# every readiness gate passes; the result and every request are audit-logged.
# ---------------------------------------------------------------------------


def _bool_arg(args, key: str, default: bool = False) -> bool:
    raw = args.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _float_arg(args, key: str, default: float) -> float:
    raw = args.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _int_arg(args, key: str, default: int) -> int:
    raw = args.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _live_runner_config_for_readiness() -> AutonomousLiveRunnerConfig:
    """Best-effort live runner config; always fails closed (live disabled)."""
    cfg = current_app.config.get("autonomous_live_runner_config") if has_app_context() else None
    if isinstance(cfg, AutonomousLiveRunnerConfig):
        return cfg
    try:
        return AutonomousLiveRunnerConfig.from_env()
    except Exception:  # pragma: no cover - defensive; never crash the readiness check
        logger.exception("Failed to build AutonomousLiveRunnerConfig for ORB readiness")
        return AutonomousLiveRunnerConfig()


def _evidence_derived_gate_counts(evidence: dict, log_dir: str, strategy_name: str) -> dict:
    """Reconstruct risk/quality readiness counters from the ORB evidence ledger.

    Never relies on caller-supplied optimism: every value here is derived
    from persisted paper-trade/rejection evidence, not query-string input.
    """
    trades = evidence.get("trades") or []
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    # Evidence trades carry a session_date (not a precise timestamp); sort by
    # it (stable) to approximate chronological order for drawdown/streak math.
    closed_chronological = sorted(closed, key=lambda t: t.get("session_date") or "")
    r_stats = compute_r_stats([t.get("realized_r") for t in closed_chronological])

    data_quality_failures = sum(
        1 for t in trades
        if t.get("status") == "FAILED"
        and "no live price" in str(t.get("failure_note") or "").lower()
    )
    emergency_stop_incidents = sum(
        1 for t in trades if t.get("exit_reason") == "EMERGENCY_STOP"
    )

    rejections = build_rejection_ledger(log_dir, strategy_name=strategy_name)
    unresolved_protection_failures = sum(
        1 for r in rejections if r.get("reason") == ORBBlockReason.MISSING_PROTECTION.value
    )

    return {
        "max_drawdown_r": r_stats["max_drawdown_r"],
        "max_consecutive_losses": r_stats["max_consecutive_losses"],
        "avg_entry_slippage_bps": compute_avg_entry_slippage_bps(trades),
        "unresolved_protection_failures": unresolved_protection_failures,
        "data_quality_failures": data_quality_failures,
        "emergency_stop_incidents_from_orb": emergency_stop_incidents,
    }


def _compute_orb_live_readiness(name, rec, requested_mode, args):
    """Shared readiness computation for the GET endpoint and the assisted-live
    rehearsal endpoint below, so both always evaluate the *same* Phase 4
    readiness result from the same evidence/connection/confirmation sources.

    Returns ``(result, account_id, expected_account_id, operator_confirmed,
    live_config, log_dir)``.
    """
    symbols = rec.get("symbols")
    evidence = get_review_store().evidence_summary(name, symbols=symbols)
    paper_summary = evidence.get("paper", {}) or {}

    from web.services import get_services
    svc = get_services()
    connection_info = getattr(svc, "connection_info", {}) or {}
    account_id = str(connection_info.get("account") or "").strip() or None
    connected = bool(getattr(svc, "connected", False))

    from web.routes.api_autonomous import EMERGENCY_STOP_FILE
    try:
        emergency_stop_active = EMERGENCY_STOP_FILE.exists()
    except OSError:
        emergency_stop_active = True  # fail closed when unreadable

    live_config = _live_runner_config_for_readiness()
    params = rec.get("parameters") or {}
    cfg = current_app.config if has_app_context() else {}
    log_dir = cfg.get("orb_evidence_dir", "logs")

    evidence_counts = _evidence_derived_gate_counts(evidence, log_dir, name)

    # Query-string values are additive diagnostics only: they may raise an
    # observed failure above the evidence-derived floor, never lower it.
    max_drawdown_r = max(
        _float_arg(args, "max_drawdown_r", evidence_counts["max_drawdown_r"]),
        evidence_counts["max_drawdown_r"],
    )
    max_consecutive_losses = max(
        _int_arg(args, "max_consecutive_losses", evidence_counts["max_consecutive_losses"]),
        evidence_counts["max_consecutive_losses"],
    )
    unresolved_protection_failures = max(
        _int_arg(args, "unresolved_protection_failures", evidence_counts["unresolved_protection_failures"]),
        evidence_counts["unresolved_protection_failures"],
    )
    data_quality_failures = max(
        _int_arg(args, "data_quality_failures", evidence_counts["data_quality_failures"]),
        evidence_counts["data_quality_failures"],
    )
    emergency_stop_incidents_from_orb = max(
        _int_arg(args, "emergency_stop_incidents_from_orb", evidence_counts["emergency_stop_incidents_from_orb"]),
        evidence_counts["emergency_stop_incidents_from_orb"],
    )

    # Tiny-live caps used for the *gate itself* are always the actual
    # live-runner config values (the real readiness source of truth). A
    # query-string override can never replace or rescue these values in the
    # gate evaluation -- it is surfaced separately below as a diagnostic
    # "simulated_tiny_live_caps" only, so a caller cannot mask an unsafe
    # actual live-runner cap by supplying a smaller query-string value.
    tiny_live_caps = TinyLiveRiskCaps(
        max_deployable_cash_pct=live_config.max_deployable_cash_pct,
        max_live_orb_trades_per_day=live_config.max_live_trades_per_day,
    )

    simulated_tiny_live_caps = None
    if "max_deployable_cash_pct" in args or "max_live_orb_trades_per_day" in args:
        simulated_tiny_live_caps = TinyLiveRiskCaps(
            max_deployable_cash_pct=_float_arg(
                args, "max_deployable_cash_pct", live_config.max_deployable_cash_pct
            ),
            max_live_orb_trades_per_day=_int_arg(
                args, "max_live_orb_trades_per_day", live_config.max_live_trades_per_day
            ),
        )

    # Operator account/mode confirmation is only ever satisfied by a prior
    # explicit POST .../confirm call, never by a GET query string.
    confirmation = get_live_readiness_confirmation_store().get(name, requested_mode)
    operator_confirmed = bool(confirmation and confirmation.get("confirmed"))
    expected_account_id = (
        (confirmation or {}).get("expected_account_id") or live_config.expected_account_id
    )

    data = ORBLiveReadinessInput(
        strategy_name=name,
        strategy_config=rec,
        paper_summary=paper_summary,
        requested_mode=requested_mode,
        max_drawdown_r=max_drawdown_r,
        max_consecutive_losses=max_consecutive_losses,
        avg_entry_slippage_bps=evidence_counts["avg_entry_slippage_bps"],
        unresolved_protection_failures=unresolved_protection_failures,
        data_quality_failures=data_quality_failures,
        emergency_stop_incidents_from_orb=emergency_stop_incidents_from_orb,
        market_data_provider_healthy=connected,
        market_data_source=args.get("market_data_source", live_config.live_market_data_provider),
        broker_connected=connected,
        broker_account_id=account_id,
        expected_account_id=expected_account_id,
        live_master_switch_enabled=live_config.live_enabled,
        emergency_stop_available=True,
        emergency_stop_tested=_bool_arg(args, "emergency_stop_tested", False),
        emergency_stop_currently_active=emergency_stop_active,
        operator_confirmed_account=operator_confirmed,
        operator_confirmed_mode=operator_confirmed,
        tiny_live_caps=tiny_live_caps,
        paper_max_trades_per_session=params.get("max_total_orb_trades_per_session"),
    )

    result = evaluate_orb_live_readiness(data, log_dir=log_dir)
    if simulated_tiny_live_caps is not None:
        result["simulated_tiny_live_caps"] = simulated_tiny_live_caps.as_dict()
    return result, account_id, expected_account_id, operator_confirmed, live_config, log_dir


@orb_bp.route("/strategies/<name>/live-readiness", methods=["GET"])
def orb_live_readiness(name):
    """Evaluate tiny-live / assisted-live readiness for a strategy.

    Read-only: gathers paper evidence, connection/account status, the live
    master switch, and emergency-stop state, then delegates to
    :func:`autonomous.orb_live_readiness.evaluate_orb_live_readiness`. Every
    evaluation is audit-logged regardless of outcome. Never places an order
    and never itself enables live trading.

    Evidence-derived risk/quality counters (drawdown-R, consecutive losses,
    entry-slippage bps, protection/data-quality/emergency-stop counts) are
    reconstructed from the ORB evidence ledger. Query-string overrides may
    only ever *raise* an observed failure count above the evidence-derived
    floor (additive diagnostics for testing) — they can never lower it and
    so can never hide a real evidence-driven failure.

    Tiny-live caps used for the ``tiny_live_caps_valid`` gate are always the
    *actual* ``AutonomousLiveRunnerConfig`` values -- the real source of
    truth for what the live runner would enforce. A query-string cap
    override can never replace or rescue those values in the gate itself;
    it is only surfaced as a separate ``simulated_tiny_live_caps`` diagnostic
    in the response, so a caller cannot mask an unsafe actual live-runner
    cap by supplying a smaller query-string value.

    Operator account/mode confirmation can only come from a prior explicit
    ``POST .../confirm`` call (see :func:`orb_live_readiness_confirm`); this
    GET endpoint never accepts a confirmation via query string.
    """
    rec = get_manager().get_strategy(name)
    if rec is None:
        return jsonify({"error": "not found", "detail": f"unknown strategy '{name}'"}), 404

    args = request.args
    requested_mode = args.get("mode", TINY_LIVE_CANDIDATE_MODE)
    result, _account_id, _expected_account_id, _operator_confirmed, _live_config, _log_dir = (
        _compute_orb_live_readiness(name, rec, requested_mode, args)
    )
    return jsonify(result)


@orb_bp.route("/strategies/<name>/live-readiness/confirm", methods=["POST"])
def orb_live_readiness_confirm(name):
    """Explicit, audit-logged operator confirmation of account id + mode.

    This is the only way to satisfy the readiness ``operator_confirmation``
    gate: a confirmation must be an explicit ``POST`` action, never a GET
    query string. Never places an order and never itself enables live
    trading; it only records (persisted + audit-logged) that an operator
    confirmed the account id and requested mode for a future readiness
    evaluation.
    """
    rec = get_manager().get_strategy(name)
    if rec is None:
        return jsonify({"error": "not found", "detail": f"unknown strategy '{name}'"}), 404

    payload = request.get_json(silent=True) or {}
    requested_mode = str(payload.get("mode") or TINY_LIVE_CANDIDATE_MODE)
    if requested_mode not in (TINY_LIVE_CANDIDATE_MODE, ASSISTED_LIVE_MODE):
        return jsonify({
            "error": "invalid mode",
            "detail": f"mode must be one of {[TINY_LIVE_CANDIDATE_MODE, ASSISTED_LIVE_MODE]}",
        }), 400

    expected_account_id = str(payload.get("expected_account_id") or "").strip() or None

    from web.services import get_services
    svc = get_services()
    connection_info = getattr(svc, "connection_info", {}) or {}
    connected_account_id = str(connection_info.get("account") or "").strip() or None

    cfg = current_app.config if has_app_context() else {}
    record = get_live_readiness_confirmation_store().confirm(
        name, requested_mode,
        expected_account_id=expected_account_id,
        connected_account_id=connected_account_id,
        operator=payload.get("operator"),
        notes=payload.get("notes"),
        log_dir=cfg.get("orb_evidence_dir", "logs"),
    )
    return jsonify(record), 201


# ---------------------------------------------------------------------------
# ORB Phase 5 — assisted-live protected order-path rehearsal (#227)
# Builds the exact broker-visible protected order package (entry + stop +
# target/bracket) that assisted-live would submit for a valid ORB proposal,
# gated by the Phase 4 (#213) live-readiness result, the live master switch,
# and an explicit operator confirmation. Dry-run/rehearsal only: no order is
# ever placed here and there is no live-submit endpoint in this phase.
# ---------------------------------------------------------------------------


@orb_bp.route("/strategies/<name>/assisted-live/rehearse", methods=["POST"])
def orb_assisted_live_rehearse(name):
    """Build (and audit-log) an assisted-live rehearsal order package.

    Requires a ``proposal_id`` for a still-``PENDING`` proposal owned by
    ``name``. Re-evaluates Phase 4 assisted-live readiness from the same
    evidence/connection/confirmation sources as the ``GET .../live-readiness``
    endpoint (a caller cannot supply a stale or fabricated readiness result).
    Never places, routes, or simulates an order; this is rehearsal/dry-run
    only. Fails closed (400/404/409) on any missing safety condition.
    """
    rec = get_manager().get_strategy(name)
    if rec is None:
        return jsonify({"error": "not found", "detail": f"unknown strategy '{name}'"}), 404

    payload = request.get_json(silent=True) or {}
    proposal_id = payload.get("proposal_id")
    if not proposal_id:
        return jsonify({"error": "proposal_id is required"}), 400

    store = get_proposal_store()
    store.expire_due()
    proposal = store.get(proposal_id)
    if proposal is None:
        return jsonify({"error": "not found", "detail": f"unknown proposal '{proposal_id}'"}), 404
    if proposal.strategy_name != name:
        return jsonify({
            "error": "proposal does not belong to strategy",
            "detail": f"proposal '{proposal_id}' belongs to '{proposal.strategy_name}', not '{name}'",
        }), 400

    result, account_id, expected_account_id, operator_confirmed, live_config, log_dir = (
        _compute_orb_live_readiness(name, rec, ASSISTED_LIVE_MODE, request.args)
    )

    try:
        package = build_assisted_live_rehearsal_package(
            proposal,
            result,
            account_id=account_id,
            expected_account_id=expected_account_id,
            operator_confirmed=operator_confirmed,
            live_master_switch_enabled=live_config.live_enabled,
            evidence_id=payload.get("evidence_id"),
            time_in_force=str(payload.get("time_in_force") or "DAY"),
            log_dir=log_dir,
        )
    except ORBAssistedLiveRefusal as exc:
        logger.info("ORB assisted-live rehearsal refused (%s): %s", exc.reason.value, exc)
        return jsonify({
            "error": "rehearsal refused",
            "reason": exc.reason.value,
            "readiness": result,
        }), 409

    get_assisted_live_rehearsal_store().add(package)
    return jsonify(package.to_dict()), 201


@orb_bp.route("/strategies/<name>/assisted-live/rehearsals", methods=["GET"])
def list_orb_assisted_live_rehearsals(name):
    """List assisted-live rehearsal packages previously built for ``name``."""
    args = request.args
    rehearsals = get_assisted_live_rehearsal_store().list(
        strategy_name=name, symbol=args.get("symbol"), proposal_id=args.get("proposal_id"),
    )
    return jsonify({"rehearsals": [p.to_dict() for p in rehearsals]})


@orb_bp.route("/assisted-live/rehearsals/<rehearsal_id>", methods=["GET"])
def get_orb_assisted_live_rehearsal(rehearsal_id):
    """Fetch a single assisted-live rehearsal package by id."""
    package = get_assisted_live_rehearsal_store().get(rehearsal_id)
    if package is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(package.to_dict())


@orb_bp.route("/review/<path:review_session_id>/notes", methods=["POST"])
def orb_review_add_note(review_session_id):
    if parse_session_id(review_session_id) is None:
        return jsonify({
            "error": "invalid session_id",
            "detail": "expected '<strategy_name>:<YYYY-MM-DD>'",
        }), 400
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", "")).strip()
    if not note:
        return jsonify({"error": "note is required"}), 400
    combined = get_review_store().add_note(review_session_id, note)
    return jsonify({"session_id": review_session_id, "operator_notes": combined}), 201
