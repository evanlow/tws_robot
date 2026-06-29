"""Tests for ORB recommend-only proposals (autonomous/orb_proposals.py, #208)."""

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
from autonomous.orb_proposals import (
    ExpiryReason,
    ORBProposalStore,
    ProposalError,
    ProposalGates,
    ProposalStatus,
    build_proposal,
    size_quantity,
)


def _candle(symbol="QQQ", o=103.0, h=103.5, l=102.8, c=103.4):
    start = datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc)
    return Candle(symbol, "5m", start, start, o, h, l, c, volume=1000.0)


def _setup(symbol="QQQ", entry=104.0, stop=103.0, target=106.0,
           direction=ORBDirection.LONG):
    rng = OpeningRange(
        symbol=symbol, session_date="2026-06-01",
        range_start=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        range_end=datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc),
        high=102.0, low=100.0, source_candle=_candle(symbol),
    )
    conf = BreakoutConfirmation(
        symbol=symbol, direction=direction, candle_5m=_candle(symbol),
        range_high=102.0, range_low=100.0,
        confirmed_at=datetime(2026, 6, 1, 9, 50, tzinfo=timezone.utc),
    )
    risk = entry - stop
    return ORBSetup(
        symbol=symbol, direction=direction,
        model=ORBEntryModel.MODEL_A_DISPLACEMENT_GAP,
        detected_at=datetime(2026, 6, 1, 9, 51, tzinfo=timezone.utc),
        entry_price=entry, stop_price=stop, target_price=target,
        risk_per_share=risk, reward_per_share=target - entry,
        rr_ratio=(target - entry) / risk if risk else 0.0,
        opening_range=rng, confirmation=conf,
        evidence={"gap_low": 103.1},
    )


def _store(tmp_path) -> ORBProposalStore:
    return ORBProposalStore(audit=AuditLogger(str(tmp_path)), log_dir=str(tmp_path))


# ---- sizing -------------------------------------------------------------
def test_size_quantity_within_risk_budget():
    # 100k * 0.002 = $200 budget; $1/share risk -> 200 shares.
    assert size_quantity(100_000.0, 0.002, 1.0) == 200


def test_size_quantity_zero_when_unfundable():
    assert size_quantity(100_000.0, 0.002, 0.0) == 0
    assert size_quantity(0.0, 0.002, 1.0) == 0


# ---- proposal construction ---------------------------------------------
def test_valid_setup_builds_recommend_only_proposal():
    p = build_proposal(
        _setup(), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
        equity=100_000.0, risk_per_trade_equity_pct=0.002,
    )
    assert p.recommend_only is True
    assert p.order_type == "LIMIT"  # never a raw market order
    assert p.status == ProposalStatus.PENDING.value
    assert p.stop_price < p.entry_price < p.target_price
    assert p.quantity == 200  # $200 budget / $1 risk
    assert p.risk_dollars == pytest.approx(200.0)
    assert p.position_value == pytest.approx(200 * 104.0)
    assert p.rr_ratio == pytest.approx(2.0)


def test_proposal_requires_stop_and_target():
    with pytest.raises(ProposalError):
        build_proposal(_setup(stop=0.0), strategy_name="ORB1",
                       session_date="2026-06-01", orb_state="X", gates=ProposalGates())
    with pytest.raises(ProposalError):
        build_proposal(_setup(target=0.0), strategy_name="ORB1",
                       session_date="2026-06-01", orb_state="X", gates=ProposalGates())


def test_proposal_rejects_non_long_direction():
    with pytest.raises(ProposalError):
        build_proposal(_setup(direction=ORBDirection.SHORT), strategy_name="ORB1",
                       session_date="2026-06-01", orb_state="X", gates=ProposalGates())


def test_proposal_rejects_stop_not_below_entry():
    with pytest.raises(ProposalError):
        build_proposal(_setup(entry=104.0, stop=104.5), strategy_name="ORB1",
                       session_date="2026-06-01", orb_state="X", gates=ProposalGates())


def test_proposal_to_dict_exposes_gates_and_context():
    p = build_proposal(_setup(), strategy_name="ORB1", session_date="2026-06-01",
                       orb_state="PROPOSAL_READY", gates=ProposalGates())
    d = p.to_dict()
    for key in ("entry_price", "stop_price", "target_price", "quantity",
                "risk_dollars", "rr_ratio", "range_high", "range_low",
                "confirmation_candle", "evidence", "gates", "expiry_reason"):
        assert key in d
    assert d["gates"]["stop_present"] is True
    assert d["gates"]["target_present"] is True
    assert "gates_failing" in d


# ---- gates --------------------------------------------------------------
def test_gates_spread_optional_when_no_quote():
    g = ProposalGates(
        opening_range_valid=True, breakout_5m_confirmed=True,
        model_1m_detected=True, market_data_healthy=True,
        risk_manager_approved=True, stop_present=True, target_present=True,
        session_cap_available=True, no_existing_open_orb_trade=True,
        emergency_stop_inactive=True, spread_acceptable=None,
    )
    assert g.all_pass() is True
    g.spread_acceptable = False
    assert g.all_pass() is False
    assert "spread_acceptable" in g.failing()


def test_gates_failing_lists_missing():
    g = ProposalGates()
    assert "risk_manager_approved" in g.failing()
    assert g.all_pass() is False


# ---- store lifecycle ----------------------------------------------------
def test_store_create_and_get(tmp_path):
    store = _store(tmp_path)
    p = store.create_from_setup(
        _setup(), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )
    assert store.get(p.proposal_id) is p
    assert store.list()[0].proposal_id == p.proposal_id


def test_store_skip_with_reason_audit_logged(tmp_path):
    store = _store(tmp_path)
    p = store.create_from_setup(_setup(), strategy_name="ORB1",
                                session_date="2026-06-01", orb_state="X",
                                gates=ProposalGates())
    skipped = store.skip(p.proposal_id, reason="not enough volume")
    assert skipped.status == ProposalStatus.SKIPPED.value
    assert skipped.skip_reason == "not enough volume"
    logs = sorted(tmp_path.glob("autonomous_trading_*.jsonl"))
    assert logs, "audit log file should be written"
    content = logs[0].read_text(encoding="utf-8")
    assert "proposal_created" in content
    assert "proposal_skipped" in content


def test_store_skip_optional_reason(tmp_path):
    store = _store(tmp_path)
    p = store.create_from_setup(_setup(), strategy_name="ORB1",
                                session_date="2026-06-01", orb_state="X",
                                gates=ProposalGates())
    skipped = store.skip(p.proposal_id)
    assert skipped.status == ProposalStatus.SKIPPED.value
    assert skipped.skip_reason == ""


def test_store_expire_reasons(tmp_path):
    for reason in (ExpiryReason.ENTRY_CUTOFF, ExpiryReason.INVALIDATION,
                   ExpiryReason.STALE_DATA, ExpiryReason.SESSION_CAP_CONSUMED):
        store = _store(tmp_path)
        p = store.create_from_setup(_setup(), strategy_name="ORB1",
                                    session_date="2026-06-01", orb_state="X",
                                    gates=ProposalGates())
        expired = store.expire(p.proposal_id, reason=reason)
        assert expired.status == ProposalStatus.EXPIRED.value
        assert expired.expiry_reason == reason.value


def test_cannot_skip_expired_proposal(tmp_path):
    store = _store(tmp_path)
    p = store.create_from_setup(_setup(), strategy_name="ORB1",
                                session_date="2026-06-01", orb_state="X",
                                gates=ProposalGates())
    store.expire(p.proposal_id, reason=ExpiryReason.INVALIDATION)
    with pytest.raises(ProposalError):
        store.skip(p.proposal_id)


def test_expire_due_uses_cutoff(tmp_path):
    store = _store(tmp_path)
    p = store.create_from_setup(
        _setup(), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="X", gates=ProposalGates(),
        expires_at=datetime(2026, 6, 1, 11, 30, tzinfo=timezone.utc).isoformat(),
    )
    # Before cutoff: not expired.
    assert store.expire_due(now=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)) == []
    assert store.get(p.proposal_id).status == ProposalStatus.PENDING.value
    # After cutoff: auto-expired with entry_cutoff reason.
    expired = store.expire_due(now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc))
    assert len(expired) == 1
    assert store.get(p.proposal_id).status == ProposalStatus.EXPIRED.value
    assert store.get(p.proposal_id).expiry_reason == ExpiryReason.ENTRY_CUTOFF.value


def test_get_missing_returns_none_and_skip_raises(tmp_path):
    store = _store(tmp_path)
    assert store.get("nope") is None
    with pytest.raises(ProposalError):
        store.skip("nope")


def test_list_filters(tmp_path):
    store = _store(tmp_path)
    store.create_from_setup(_setup("QQQ"), strategy_name="ORB1",
                            session_date="2026-06-01", orb_state="X",
                            gates=ProposalGates())
    store.create_from_setup(_setup("SPY"), strategy_name="ORB2",
                            session_date="2026-06-01", orb_state="X",
                            gates=ProposalGates())
    assert len(store.list(symbol="QQQ")) == 1
    assert len(store.list(strategy_name="ORB2")) == 1
    assert len(store.list(status=ProposalStatus.PENDING.value)) == 2


# ---- add() re-validates safety invariants -------------------------------
def _valid_proposal():
    return build_proposal(_setup(), strategy_name="ORB1",
                          session_date="2026-06-01", orb_state="X",
                          gates=ProposalGates())


def test_add_accepts_valid_proposal(tmp_path):
    store = _store(tmp_path)
    p = _valid_proposal()
    assert store.add(p) is p
    assert store.get(p.proposal_id) is p


def test_add_rejects_non_limit_order_type(tmp_path):
    store = _store(tmp_path)
    p = _valid_proposal()
    p.order_type = "MKT"
    with pytest.raises(ProposalError):
        store.add(p)
    assert store.get(p.proposal_id) is None


def test_add_rejects_not_recommend_only(tmp_path):
    store = _store(tmp_path)
    p = _valid_proposal()
    p.recommend_only = False
    with pytest.raises(ProposalError):
        store.add(p)
    assert store.get(p.proposal_id) is None


def test_add_rejects_short_direction(tmp_path):
    store = _store(tmp_path)
    p = _valid_proposal()
    p.direction = ORBDirection.SHORT.value
    with pytest.raises(ProposalError):
        store.add(p)


def test_add_rejects_non_pending_status(tmp_path):
    store = _store(tmp_path)
    p = _valid_proposal()
    p.status = ProposalStatus.EXECUTED.value
    with pytest.raises(ProposalError):
        store.add(p)


def test_add_rejects_invalid_stop_target(tmp_path):
    store = _store(tmp_path)
    p = _valid_proposal()
    p.stop_price = p.entry_price + 1.0  # stop no longer below entry
    with pytest.raises(ProposalError):
        store.add(p)

    p2 = _valid_proposal()
    p2.target_price = 0.0  # missing target
    with pytest.raises(ProposalError):
        store.add(p2)

