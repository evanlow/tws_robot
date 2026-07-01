"""Tests for the ORB Phase 2.7 evidence ledger & session review (#211).

Covers reconstructing trade and no-trade sessions purely from the existing
audit trail (autonomous/orb_proposals.py, autonomous/orb_execution.py,
autonomous/orb_exit_manager.py), grouping evidence by symbol/model/date/
result, promotion classification, JSON/CSV export, operator notes, and the
review/evidence API endpoints.
"""

import json
from datetime import datetime, timezone

import pytest

from autonomous.audit import AuditLogger
from autonomous.opening_range import (
    BreakoutConfirmation,
    Candle,
    ORBDirection,
    ORBEntryModel,
    ORBSetup,
    OpeningRange,
)
from autonomous.orb_evidence import (
    DO_NOT_TRADE,
    NEEDS_MORE_DATA,
    READY_FOR_PAPER,
    TINY_LIVE_CANDIDATE,
    PromotionCriteria,
    build_evidence_summary,
    build_proposal_ledger,
    build_rejection_ledger,
    build_session_evidence,
    build_trade_ledger,
    classify_promotion,
    export_evidence,
    group_trades,
)
from autonomous.orb_execution import (
    ORBExecutionBlocked,
    ORBExecutionMode,
    ORBPaperExecutor,
)
from autonomous.orb_exit_manager import ORBExitManager
from autonomous.orb_proposals import ORBProposalStore, ProposalGates
from autonomous.orb_session_review import (
    ORBSessionReviewStore,
    parse_session_id,
    session_id,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _candle(symbol="QQQ", o=103.0, h=103.5, l=102.8, c=103.4):
    start = datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc)
    return Candle(symbol, "5m", start, start, o, h, l, c, volume=1000.0)


def _setup(symbol="QQQ", entry=104.0, stop=103.0, target=106.0):
    start = datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc)
    c5 = _candle(symbol)
    rng = OpeningRange(symbol, "2026-06-01", start, start, 102.0, 100.0, c5)
    conf = BreakoutConfirmation(symbol, ORBDirection.LONG, c5, 102.0, 100.0, start)
    return ORBSetup(
        symbol=symbol, direction=ORBDirection.LONG,
        model=ORBEntryModel.MODEL_A_DISPLACEMENT_GAP, detected_at=start,
        entry_price=entry, stop_price=stop, target_price=target,
        risk_per_share=entry - stop, reward_per_share=target - entry,
        rr_ratio=(target - entry) / (entry - stop),
        opening_range=rng, confirmation=conf, evidence={"gap_low": 100.0},
    )


class _Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


def _run_full_trade(tmp_path, *, strategy="ORB1", symbol="QQQ",
                    session_date="2026-06-01", prices=None):
    """Drive a real proposal -> paper execution -> intraday exit lifecycle
    end to end so the resulting audit trail is genuine (not hand-built)."""
    audit = AuditLogger(str(tmp_path))
    store = ORBProposalStore(audit=audit, log_dir=str(tmp_path))
    setup = _setup(symbol=symbol)
    proposal = store.create_from_setup(
        setup, strategy_name=strategy, session_date=session_date,
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    executor = ORBPaperExecutor(store, audit=audit, log_dir=str(tmp_path))
    trade = executor.execute_paper(proposal, mode=ORBExecutionMode.PAPER_AUTONOMOUS)

    clock = _Clock(datetime(2026, 6, 1, 9, 50, tzinfo=timezone.utc))
    prices = list(prices or [104.5, 103.5, 106.5])

    def price_provider(sym):
        return prices.pop(0) if prices else None

    exit_mgr = ORBExitManager(
        price_provider=price_provider, audit=audit, log_dir=str(tmp_path), now_fn=clock,
    )
    exit_mgr.register_trade(trade)
    exit_mgr.mark_entry_filled(trade.trade_id, trade.entry_price)
    decisions = []
    while prices:
        decisions.append(exit_mgr.evaluate_trade(trade.trade_id))
    return trade, decisions


# ---------------------------------------------------------------------------
# no-trade session evidence
# ---------------------------------------------------------------------------

def test_no_trade_session_no_proposals_at_all(tmp_path):
    ev = build_session_evidence(str(tmp_path), "ORB1", "2026-06-01",
                                symbols_watched=["QQQ", "SPY"])
    assert ev["no_trade"] is True
    assert ev["proposals"]["total"] == 0
    assert ev["trades"]["total"] == 0
    assert "QQQ" in ev["no_trade_explanation"]
    assert ev["symbols_watched"] == ["QQQ", "SPY"]


def test_no_trade_session_skipped_and_expired_proposals(tmp_path):
    audit = AuditLogger(str(tmp_path))
    store = ORBProposalStore(audit=audit, log_dir=str(tmp_path))
    p1 = store.create_from_setup(
        _setup(symbol="QQQ"), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    store.skip(p1.proposal_id, reason="spread too wide")
    p2 = store.create_from_setup(
        _setup(symbol="SPY"), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    from autonomous.orb_proposals import ExpiryReason
    store.expire(p2.proposal_id, ExpiryReason.ENTRY_CUTOFF)

    ev = build_session_evidence(str(tmp_path), "ORB1", "2026-06-01",
                                symbols_watched=["QQQ", "SPY"])
    assert ev["no_trade"] is True
    assert ev["proposals"]["total"] == 2
    assert ev["proposals"]["skipped"] == 1
    assert ev["proposals"]["expired"] == 1
    explanation = ev["no_trade_explanation"]
    assert "skipped" in explanation
    assert "spread too wide" in explanation
    assert "expired" in explanation
    assert "entry_cutoff" in explanation

    # Even though neither proposal ever became a trade, the review must still
    # reconstruct the full setup context (model/range/entry/stop/target/gates)
    # from the audit log alone (#211).
    skipped_item = next(p for p in ev["proposals"]["items"] if p["proposal_id"] == p1.proposal_id)
    assert skipped_item["entry_model"] == "MODEL_A_DISPLACEMENT_GAP"
    assert skipped_item["direction"] == "LONG"
    assert skipped_item["entry_price"] == pytest.approx(104.0)
    assert skipped_item["stop_price"] == pytest.approx(103.0)
    assert skipped_item["target_price"] == pytest.approx(106.0)
    assert skipped_item["range_high"] == pytest.approx(102.0)
    assert skipped_item["range_low"] == pytest.approx(100.0)
    assert skipped_item["confirmation_candle"] is not None
    assert skipped_item["confirmation_candle"]["direction"] == "LONG"
    assert skipped_item["evidence"] == {"gap_low": 100.0}
    assert skipped_item["gates"] is not None
    assert skipped_item["gates"]["opening_range_valid"] is True

    expired_item = next(p for p in ev["proposals"]["items"] if p["proposal_id"] == p2.proposal_id)
    assert expired_item["entry_model"] == "MODEL_A_DISPLACEMENT_GAP"
    assert expired_item["target_price"] == pytest.approx(106.0)


def test_rejection_ledger_and_explanation(tmp_path):
    audit = AuditLogger(str(tmp_path))
    store = ORBProposalStore(audit=audit, log_dir=str(tmp_path))
    proposal = store.create_from_setup(
        _setup(), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    executor = ORBPaperExecutor(store, audit=audit, log_dir=str(tmp_path))
    executor.trip_emergency_stop()
    with pytest.raises(ORBExecutionBlocked):
        executor.execute_paper(proposal, mode=ORBExecutionMode.PAPER_AUTONOMOUS)

    rejections = build_rejection_ledger(str(tmp_path), strategy_name="ORB1",
                                        session_date="2026-06-01")
    assert len(rejections) == 1
    assert rejections[0]["reason"] == "emergency_stop"

    ev = build_session_evidence(str(tmp_path), "ORB1", "2026-06-01")
    assert ev["no_trade"] is True
    assert "blocked" in ev["no_trade_explanation"]
    assert "emergency_stop" in ev["no_trade_explanation"]


# ---------------------------------------------------------------------------
# trade session evidence (full lifecycle, real audit trail)
# ---------------------------------------------------------------------------

def test_trade_session_full_evidence(tmp_path):
    trade, decisions = _run_full_trade(tmp_path)
    assert decisions[-1].decision == "TARGET"

    ledger = build_trade_ledger(str(tmp_path))
    assert trade.trade_id in ledger
    te = ledger[trade.trade_id]
    assert te.status == "CLOSED"
    assert te.symbol == "QQQ"
    assert te.entry_model == "MODEL_A_DISPLACEMENT_GAP"
    assert te.exit_reason == "TARGET"
    assert te.exit_price == 106.0
    assert te.realized_r == pytest.approx(2.0)
    assert te.mfe_r == pytest.approx(2.5)
    assert te.mae_r == pytest.approx(-0.5)
    assert te.quantity == 200  # 100_000 * 0.002 / 1.0 risk-per-share

    d = te.to_dict()
    assert d["risk_dollars"] == pytest.approx(200.0)
    assert d["rr_ratio"] == pytest.approx(2.0)
    assert d["commission"] == pytest.approx(2.0)  # 2 * 0.005 * 200
    assert d["realized_pnl"] == pytest.approx((106.0 - 104.0) * 200)
    assert d["result"] == "WIN"

    ev = build_session_evidence(str(tmp_path), "ORB1", "2026-06-01",
                                symbols_watched=["QQQ"])
    assert ev["no_trade"] is False
    assert ev["no_trade_explanation"] is None
    assert ev["trades"]["total"] == 1
    assert ev["trades"]["closed"] == 1
    assert ev["trades"]["exits_by_reason"] == {"TARGET": 1}
    assert ev["proposals"]["executed"] == 1


def test_losing_trade_result_and_failed_trade(tmp_path):
    # A trade stopped out is a LOSS.
    trade, _ = _run_full_trade(tmp_path, prices=[103.5, 103.0])
    ledger = build_trade_ledger(str(tmp_path))
    te = ledger[trade.trade_id]
    assert te.exit_reason == "STOP"
    assert te.result() == "LOSS"

    # A trade whose entry fails is FAILED (no exit at all).
    audit = AuditLogger(str(tmp_path))
    store = ORBProposalStore(audit=audit, log_dir=str(tmp_path))
    proposal = store.create_from_setup(
        _setup(symbol="SPY"), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    executor = ORBPaperExecutor(store, audit=audit, log_dir=str(tmp_path))
    failed_trade = executor.execute_paper(proposal, mode=ORBExecutionMode.PAPER_AUTONOMOUS)
    exit_mgr = ORBExitManager(audit=audit, log_dir=str(tmp_path))
    exit_mgr.register_trade(failed_trade)
    exit_mgr.mark_entry_failed(failed_trade.trade_id, "simulated broker rejection")

    ledger2 = build_trade_ledger(str(tmp_path))
    fte = ledger2[failed_trade.trade_id]
    assert fte.status == "FAILED"
    assert fte.result() == "FAILED"
    assert fte.failure_note == "simulated broker rejection"


def test_cancelled_entries_excluded_from_closed_and_promotion_counts(tmp_path):
    audit = AuditLogger(str(tmp_path))
    store = ORBProposalStore(audit=audit, log_dir=str(tmp_path))
    proposal = store.create_from_setup(
        _setup(), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    executor = ORBPaperExecutor(store, audit=audit, log_dir=str(tmp_path))
    trade = executor.execute_paper(proposal, mode=ORBExecutionMode.PAPER_AUTONOMOUS)
    exit_mgr = ORBExitManager(audit=audit, log_dir=str(tmp_path))
    exit_mgr.register_trade(trade)
    exit_mgr.cancel_entry(trade.trade_id)

    ledger = build_trade_ledger(str(tmp_path))
    assert ledger[trade.trade_id].status == "CANCELLED"

    summary = build_evidence_summary(str(tmp_path), "ORB1")
    assert summary["paper"]["closed_trades"] == 0
    assert summary["paper"]["cancelled_trades"] == 1
    assert summary["promotion"]["status"] == NEEDS_MORE_DATA


def test_ledger_force_flat_no_price_reconstructs_exit_reason(tmp_path):
    """A force-flat-no-price failure must still show a structured exit reason.

    ``_trigger_exit`` logs ``exit_failed_no_price`` with ``would_exit_reason``
    when a mandatory exit (force-flat/emergency-stop) cannot get a live price;
    the ledger must surface that as ``trade.exit_reason`` rather than leaving
    a trader to guess why the trade failed.
    """
    audit = AuditLogger(str(tmp_path))
    store = ORBProposalStore(audit=audit, log_dir=str(tmp_path))
    proposal = store.create_from_setup(
        _setup(), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    executor = ORBPaperExecutor(store, audit=audit, log_dir=str(tmp_path))
    trade = executor.execute_paper(proposal, mode=ORBExecutionMode.PAPER_AUTONOMOUS)

    # Past the 15:55 America/New_York force-flat cutoff for 2026-06-01, and no
    # live price is ever available (simulates a broker/data outage at flatten
    # time).
    clock = _Clock(datetime(2026, 6, 1, 9, 50, tzinfo=timezone.utc))

    def no_price(_sym):
        return None

    exit_mgr = ORBExitManager(
        price_provider=no_price, audit=audit, log_dir=str(tmp_path), now_fn=clock,
    )
    exit_mgr.register_trade(trade)
    exit_mgr.mark_entry_filled(trade.trade_id, trade.entry_price)
    clock.now = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)  # well past 15:55 ET
    decision = exit_mgr.evaluate_trade(trade.trade_id)
    assert decision.decision == "NO_PRICE_AVAILABLE"

    ledger = build_trade_ledger(str(tmp_path))
    te = ledger[trade.trade_id]
    assert te.status == "FAILED"
    assert te.exit_reason == "FORCE_FLAT"


# ---------------------------------------------------------------------------
# grouping / summary / promotion classification
# ---------------------------------------------------------------------------

def test_group_trades_by_symbol_model_date_result():
    trades = [
        {"symbol": "QQQ", "entry_model": "model_a", "session_date": "2026-06-01", "result": "WIN"},
        {"symbol": "QQQ", "entry_model": "model_b", "session_date": "2026-06-02", "result": "LOSS"},
        {"symbol": "SPY", "entry_model": "model_a", "session_date": "2026-06-01", "result": "WIN"},
    ]
    by_symbol = group_trades(trades, "symbol")
    assert set(by_symbol) == {"QQQ", "SPY"}
    assert len(by_symbol["QQQ"]) == 2
    by_model = group_trades(trades, "model")
    assert len(by_model["model_a"]) == 2
    by_date = group_trades(trades, "date")
    assert len(by_date["2026-06-01"]) == 2
    by_result = group_trades(trades, "result")
    assert len(by_result["WIN"]) == 2
    with pytest.raises(ValueError):
        group_trades(trades, "bogus")


def test_evidence_summary_needs_more_data_when_no_trades(tmp_path):
    summary = build_evidence_summary(str(tmp_path), "ORB1")
    assert summary["promotion"]["status"] == NEEDS_MORE_DATA


def test_evidence_summary_ready_for_paper_from_backtest_when_no_paper_trades(tmp_path):
    ev_path = tmp_path / "orb_backtest_evidence_20260601.jsonl"
    ev_path.write_text(json.dumps({
        "symbols": ["QQQ"], "readiness": {"status": "READY_FOR_PAPER"},
    }) + "\n", encoding="utf-8")
    summary = build_evidence_summary(str(tmp_path), "ORB1")
    assert summary["backtest"]["latest_readiness_status"] == "READY_FOR_PAPER"
    assert summary["promotion"]["status"] == READY_FOR_PAPER


def test_evidence_summary_backtest_evidence_scoped_by_strategy_name(tmp_path):
    """READY_FOR_PAPER backtest evidence tagged with an explicit strategy_name
    must never leak into an unrelated strategy's evidence summary, even when
    the unrelated strategy shares the same symbol."""
    ev_path = tmp_path / "orb_backtest_evidence_20260601.jsonl"
    ev_path.write_text(json.dumps({
        "strategy_name": "ORB1", "symbols": ["QQQ"],
        "readiness": {"status": "READY_FOR_PAPER"},
    }) + "\n", encoding="utf-8")

    own = build_evidence_summary(str(tmp_path), "ORB1")
    assert own["backtest"]["saved_evidence_count"] == 1
    assert own["backtest"]["latest_readiness_status"] == "READY_FOR_PAPER"
    assert own["promotion"]["status"] == READY_FOR_PAPER

    other = build_evidence_summary(str(tmp_path), "ORB2", symbols=["QQQ"])
    assert other["backtest"]["saved_evidence_count"] == 0
    assert other["backtest"]["latest_readiness_status"] is None
    assert other["promotion"]["status"] == NEEDS_MORE_DATA


def test_evidence_summary_backtest_evidence_symbol_fallback_when_untagged(tmp_path):
    """Untagged (no strategy_name) legacy evidence falls back to a symbol-
    overlap match against the caller-supplied watched symbols."""
    ev_path = tmp_path / "orb_backtest_evidence_20260601.jsonl"
    ev_path.write_text(json.dumps({
        "symbols": ["QQQ"], "readiness": {"status": "READY_FOR_PAPER"},
    }) + "\n", encoding="utf-8")

    matching = build_evidence_summary(str(tmp_path), "ORB1", symbols=["QQQ"])
    assert matching["backtest"]["saved_evidence_count"] == 1

    non_matching = build_evidence_summary(str(tmp_path), "ORB2", symbols=["SPY"])
    assert non_matching["backtest"]["saved_evidence_count"] == 0
    assert non_matching["promotion"]["status"] == NEEDS_MORE_DATA


def test_classify_promotion_do_not_trade_on_negative_avg_r():
    summary = {"total_trades": 5, "closed_trades": 5, "failed_trades": 0, "avg_realized_r": -0.5}
    result = classify_promotion(summary)
    assert result["status"] == DO_NOT_TRADE


def test_classify_promotion_needs_more_data_below_min_trades():
    summary = {"total_trades": 5, "closed_trades": 5, "failed_trades": 0, "avg_realized_r": 0.3}
    result = classify_promotion(summary, criteria=PromotionCriteria(min_trade_count=10))
    assert result["status"] == NEEDS_MORE_DATA


def test_classify_promotion_ready_for_paper_when_thresholds_met():
    summary = {"total_trades": 20, "closed_trades": 20, "failed_trades": 0, "avg_realized_r": 0.3}
    result = classify_promotion(summary, criteria=PromotionCriteria(
        min_trade_count=10, tiny_live_min_trade_count=50,
    ))
    assert result["status"] == READY_FOR_PAPER


def test_classify_promotion_tiny_live_candidate():
    summary = {"total_trades": 60, "closed_trades": 60, "failed_trades": 0, "avg_realized_r": 0.5}
    result = classify_promotion(summary, criteria=PromotionCriteria(
        min_trade_count=10, tiny_live_min_trade_count=50, tiny_live_min_avg_r=0.2,
    ))
    assert result["status"] == TINY_LIVE_CANDIDATE


def test_classify_promotion_do_not_trade_high_failure_ratio():
    summary = {"total_trades": 10, "closed_trades": 8, "failed_trades": 2, "avg_realized_r": 0.5}
    result = classify_promotion(summary, criteria=PromotionCriteria(max_failed_trade_ratio=0.1))
    assert result["status"] == DO_NOT_TRADE


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_evidence_json_and_csv(tmp_path):
    _run_full_trade(tmp_path)
    js = export_evidence(str(tmp_path), "ORB1", "json")
    parsed = json.loads(js)
    assert parsed["strategy_name"] == "ORB1"
    assert parsed["paper"]["closed_trades"] == 1

    csv_text = export_evidence(str(tmp_path), "ORB1", "csv")
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("trade_id,")
    assert len(lines) == 2

    with pytest.raises(ValueError):
        export_evidence(str(tmp_path), "ORB1", "xml")


# ---------------------------------------------------------------------------
# session review store (operator notes)
# ---------------------------------------------------------------------------

def test_session_id_roundtrip():
    sid = session_id("ORB1", "2026-06-01")
    assert sid == "ORB1:2026-06-01"
    assert parse_session_id(sid) == ("ORB1", "2026-06-01")
    assert parse_session_id("no-colon-here") is None


def test_review_store_notes_persist(tmp_path):
    store = ORBSessionReviewStore(config_dir=str(tmp_path / "config"),
                                  evidence_dir=str(tmp_path / "logs"))
    sid = session_id("ORB1", "2026-06-01")
    store.add_note(sid, "checked slippage, looks fine")
    assert "checked slippage" in store.get_notes(sid)

    # Persists across a fresh store instance (same config dir).
    store2 = ORBSessionReviewStore(config_dir=str(tmp_path / "config"),
                                   evidence_dir=str(tmp_path / "logs"))
    assert "checked slippage" in store2.get_notes(sid)

    review = store2.get_review("ORB1", "2026-06-01", symbols_watched=["QQQ"])
    assert review["operator_notes"] == store2.get_notes(sid)
    assert review["session_id"] == sid


def test_review_store_list_reviews_for_date(tmp_path):
    store = ORBSessionReviewStore(config_dir=str(tmp_path / "config"),
                                  evidence_dir=str(tmp_path / "logs"))
    strategies = [
        {"name": "ORB1", "symbols": ["QQQ"], "parameters": {}},
        {"name": "ORB2", "symbols": ["SPY"], "parameters": {}},
    ]
    reviews = store.list_reviews_for_date("2026-06-01", strategies)
    assert {r["strategy_name"] for r in reviews} == {"ORB1", "ORB2"}
    assert all(r["no_trade"] for r in reviews)


# ---------------------------------------------------------------------------
# API endpoints (web/routes/api_opening_range.py, #211)
# ---------------------------------------------------------------------------

import web.routes.api_opening_range as api
from web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    api._manager = None
    api._proposal_store = None
    api._executor = None
    api._exit_manager = None
    api._review_store = None
    app = create_app({
        "TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False,
        "orb_config_dir": str(tmp_path / "config"),
        "orb_evidence_dir": str(tmp_path / "logs"),
    })
    yield app.test_client()
    api._manager = None
    api._proposal_store = None
    api._executor = None
    api._exit_manager = None
    api._review_store = None


def _make_strategy(client, name="ORB1", symbols=None):
    return client.post("/api/orb/strategies", json={
        "name": name, "symbols": symbols or ["QQQ"], "mode": "recommend_only",
    })


def test_review_page_loads(client):
    assert client.get("/opening-range/review").status_code == 200


def test_review_requires_date(client):
    res = client.get("/api/orb/review")
    assert res.status_code == 400


def test_review_no_trade_for_all_strategies(client):
    _make_strategy(client, "ORB1", ["QQQ"])
    _make_strategy(client, "ORB2", ["SPY"])
    res = client.get("/api/orb/review?date=2026-06-01")
    assert res.status_code == 200
    sessions = res.get_json()["sessions"]
    assert {s["strategy_name"] for s in sessions} == {"ORB1", "ORB2"}
    assert all(s["no_trade"] for s in sessions)


def test_review_single_strategy_not_found(client):
    res = client.get("/api/orb/review?date=2026-06-01&strategy=NOPE")
    assert res.status_code == 404


def test_review_single_strategy_found(client):
    _make_strategy(client, "ORB1", ["QQQ"])
    res = client.get("/api/orb/review?date=2026-06-01&strategy=ORB1")
    assert res.status_code == 200
    sessions = res.get_json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["strategy_name"] == "ORB1"


def test_evidence_summary_endpoint(client):
    _make_strategy(client, "ORB1", ["QQQ"])
    res = client.get("/api/orb/evidence/ORB1")
    assert res.status_code == 200
    body = res.get_json()
    assert body["strategy_name"] == "ORB1"
    assert body["promotion"]["status"] == NEEDS_MORE_DATA


def test_evidence_export_json_and_csv(client):
    _make_strategy(client, "ORB1", ["QQQ"])
    js = client.get("/api/orb/evidence/ORB1/export?format=json")
    assert js.status_code == 200
    assert js.mimetype == "application/json"
    payload = json.loads(js.get_data(as_text=True))
    assert payload["strategy_name"] == "ORB1"

    csv_res = client.get("/api/orb/evidence/ORB1/export?format=csv")
    assert csv_res.status_code == 200
    assert csv_res.mimetype == "text/csv"
    assert csv_res.get_data(as_text=True).startswith("trade_id,")


def test_evidence_export_invalid_format(client):
    res = client.get("/api/orb/evidence/ORB1/export?format=xml")
    assert res.status_code == 400


def test_evidence_endpoints_unknown_strategy_404(client):
    assert client.get("/api/orb/evidence/NOPE").status_code == 404
    assert client.get("/api/orb/evidence/NOPE/export?format=json").status_code == 404


def test_review_notes_endpoint(client):
    sid = "ORB1:2026-06-01"
    res = client.post(f"/api/orb/review/{sid}/notes", json={"note": "looks clean"})
    assert res.status_code == 201
    assert res.get_json()["operator_notes"] == "looks clean"

    # Notes surface back through the review.
    _make_strategy(client, "ORB1", ["QQQ"])
    review = client.get("/api/orb/review?date=2026-06-01&strategy=ORB1").get_json()
    assert review["sessions"][0]["operator_notes"] == "looks clean"


def test_review_notes_invalid_session_id(client):
    res = client.post("/api/orb/review/no-colon-here/notes", json={"note": "x"})
    assert res.status_code == 400


def test_review_notes_requires_note(client):
    res = client.post("/api/orb/review/ORB1:2026-06-01/notes", json={})
    assert res.status_code == 400
