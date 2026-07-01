"""Tests for ORB paper-autonomous execution (autonomous/orb_execution.py, #209).

Covers the ORB Phase 2.5 safety posture: paper-only execution, mandatory
stop/target, no raw market orders, bracket-preferred protection with an
explicitly-configured exit-manager fallback, idempotency, emergency-stop and
session-cap gating, and end-to-end ORB evidence linkage.
"""

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
from autonomous.orb_execution import (
    ORBBlockReason,
    ORBExecutionBlocked,
    ORBExecutionError,
    ORBExecutionMode,
    ORBOrderProtectionStatus,
    ORBOrderRole,
    ORBPaperExecutor,
    SimulatedPaperBracketAdapter,
)
from autonomous.orb_proposals import (
    ORBProposalStore,
    ProposalGates,
    ProposalStatus,
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
        evidence={"setup_id": "setup-xyz"},
    )


def _store(tmp_path) -> ORBProposalStore:
    return ORBProposalStore(audit=AuditLogger(str(tmp_path)), log_dir=str(tmp_path))


def _proposal(store, strategy="ORB1", symbol="QQQ", **kwargs):
    return store.create_from_setup(
        _setup(symbol=symbol), strategy_name=strategy, session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(), **kwargs,
    )


def _executor(tmp_path, store, **kwargs) -> ORBPaperExecutor:
    return ORBPaperExecutor(
        store, audit=AuditLogger(str(tmp_path)), log_dir=str(tmp_path), **kwargs,
    )


# ---- happy path: bracket-confirmed paper trade --------------------------

def test_execute_paper_places_bracket_protected_trade(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(tmp_path, store)

    trade = executor.execute_paper(proposal)

    assert trade.protection_status == ORBOrderProtectionStatus.BRACKET_CONFIRMED.value
    assert trade.mode == ORBExecutionMode.PAPER_AUTONOMOUS.value
    # entry/stop/target all present and linked to ORB evidence.
    roles = {o.role for o in trade.orders}
    assert roles == {"ENTRY", "STOP", "TARGET"}
    assert trade.entry_order_id and trade.stop_order_id and trade.target_order_id
    for order in trade.orders:
        assert order.links["proposal_id"] == proposal.proposal_id
        assert order.links["strategy_name"] == "ORB1"
        assert order.links["session_date"] == "2026-06-01"
        assert order.links["setup_ref"] == "setup-xyz"
    # The proposal is marked EXECUTED in its store.
    assert store.get(proposal.proposal_id).status == ProposalStatus.EXECUTED.value


def test_no_raw_market_orders_are_possible(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    trade = _executor(tmp_path, store).execute_paper(proposal)
    for order in trade.orders:
        assert order.order_type in ("LIMIT", "STOP")
        assert order.order_type != "MARKET"
    # The marketable entry is a LIMIT order; protective stop is a STOP order.
    entry = next(o for o in trade.orders if o.role == "ENTRY")
    stop = next(o for o in trade.orders if o.role == "STOP")
    assert entry.order_type == "LIMIT" and entry.action == "BUY"
    assert stop.order_type == "STOP" and stop.action == "SELL"


def test_simulated_adapter_refuses_non_limit_stop_order(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    adapter = SimulatedPaperBracketAdapter()
    with pytest.raises(ORBExecutionError):
        adapter._order(proposal, ORBOrderRole.ENTRY, "BUY", "MARKET",
                       limit_price=100.0)


# ---- mandatory stop/target & executability ------------------------------

def test_missing_stop_rejected(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    proposal.stop_price = 0.0  # corrupt the card after creation
    with pytest.raises(ORBExecutionError):
        _executor(tmp_path, store).execute_paper(proposal)


def test_missing_target_rejected(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    proposal.target_price = 0.0
    with pytest.raises(ORBExecutionError):
        _executor(tmp_path, store).execute_paper(proposal)


def test_skipped_proposal_not_executable(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    store.skip(proposal.proposal_id, reason="trader skip")
    with pytest.raises(ORBExecutionError):
        _executor(tmp_path, store).execute_paper(store.get(proposal.proposal_id))


def test_zero_quantity_proposal_not_executable(tmp_path):
    store = _store(tmp_path)
    # A tiny risk budget cannot fund even one share -> quantity 0.
    proposal = store.create_from_setup(
        _setup(), strategy_name="ORB1", session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
        equity=1.0,
    )
    assert proposal.quantity == 0
    with pytest.raises(ORBExecutionError):
        _executor(tmp_path, store).execute_paper(proposal)


# ---- protection model: bracket / fallback / rejection -------------------

class _NoBracketAdapter(SimulatedPaperBracketAdapter):
    supports_bracket = False


def test_missing_protection_rejected_without_fallback(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(tmp_path, store, adapter=_NoBracketAdapter())
    with pytest.raises(ORBExecutionBlocked) as exc:
        executor.execute_paper(proposal)
    assert exc.value.reason == ORBBlockReason.MISSING_PROTECTION
    # No naked entry placed and the proposal stays pending.
    assert store.get(proposal.proposal_id).status == ProposalStatus.PENDING.value
    assert executor.get_trade_for_proposal(proposal.proposal_id) is None


def test_exit_manager_fallback_when_explicitly_configured(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(
        tmp_path, store, adapter=_NoBracketAdapter(),
        allow_exit_manager_fallback=True,
    )
    trade = executor.execute_paper(proposal)
    assert trade.protection_status == ORBOrderProtectionStatus.EXIT_MANAGER_FALLBACK.value
    # Only the marketable-limit entry is placed; exit manager owns the exits.
    assert [o.role for o in trade.orders] == ["ENTRY"]
    assert trade.orders[0].order_type == "LIMIT"


# ---- paper only ----------------------------------------------------------

@pytest.mark.parametrize("mode", [
    ORBExecutionMode.ASSISTED_LIVE,
    ORBExecutionMode.TINY_LIVE_CANDIDATE,
])
def test_non_paper_modes_are_rejected(tmp_path, mode):
    store = _store(tmp_path)
    proposal = _proposal(store)
    with pytest.raises(ORBExecutionBlocked) as exc:
        _executor(tmp_path, store).execute_paper(proposal, mode=mode)
    assert exc.value.reason == ORBBlockReason.UNSUPPORTED_MODE
    assert store.get(proposal.proposal_id).status == ProposalStatus.PENDING.value


# ---- idempotency ---------------------------------------------------------

def test_duplicate_execution_is_idempotent(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(tmp_path, store)
    first = executor.execute_paper(proposal)
    second = executor.execute_paper(proposal)
    assert first.trade_id == second.trade_id
    # Only one trade exists and only one set of orders was minted.
    assert len(executor.list_trades()) == 1
    assert first.orders[0].order_id == second.orders[0].order_id


# ---- emergency stop ------------------------------------------------------

def test_emergency_stop_blocks_execution(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(tmp_path, store)
    executor.trip_emergency_stop()
    with pytest.raises(ORBExecutionBlocked) as exc:
        executor.execute_paper(proposal)
    assert exc.value.reason == ORBBlockReason.EMERGENCY_STOP
    assert store.get(proposal.proposal_id).status == ProposalStatus.PENDING.value
    # Resetting allows execution again.
    executor.reset_emergency_stop()
    assert executor.execute_paper(proposal).protection_status == (
        ORBOrderProtectionStatus.BRACKET_CONFIRMED.value
    )


# ---- session cap ---------------------------------------------------------

def test_session_cap_blocks_after_consumed(tmp_path):
    store = _store(tmp_path)
    executor = _executor(tmp_path, store, session_cap=1)
    first = _proposal(store)
    second = _proposal(store)  # same strategy + session date
    executor.execute_paper(first)
    with pytest.raises(ORBExecutionBlocked) as exc:
        executor.execute_paper(second)
    assert exc.value.reason == ORBBlockReason.SESSION_CAP_CONSUMED


def test_session_cap_allows_up_to_limit(tmp_path):
    store = _store(tmp_path)
    executor = _executor(tmp_path, store, session_cap=2)
    first = _proposal(store)
    second = _proposal(store)
    assert executor.execute_paper(first).trade_id
    assert executor.execute_paper(second).trade_id
    assert len(executor.list_trades()) == 2


# ---- lookups -------------------------------------------------------------

def test_get_and_list_trades(tmp_path):
    store = _store(tmp_path)
    executor = _executor(tmp_path, store, session_cap=5)
    trade = executor.execute_paper(_proposal(store, symbol="QQQ"))
    other = executor.execute_paper(_proposal(store, strategy="ORB2", symbol="SPY"))
    assert executor.get_trade(trade.trade_id).trade_id == trade.trade_id
    assert executor.get_trade("missing") is None
    assert [t.symbol for t in executor.list_trades(symbol="SPY")] == ["SPY"]
    assert [t.trade_id for t in executor.list_trades(strategy_name="ORB2")] == [
        other.trade_id
    ]
