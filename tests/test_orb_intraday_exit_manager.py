"""Tests for ORB Phase 2.6 intraday exit lifecycle & in-trade monitor (#210).

Covers the ORB-specific exit lifecycle built on top of the Phase 2.5 paper
executor (`autonomous/orb_execution.py`): target/stop/force-flat/max-holding/
emergency-stop/manual-close exit triggers, the ENTRY_PENDING -> OPEN ->
EXIT_PENDING -> CLOSED/FAILED state machine, R/MFE/MAE/slippage computation,
missing-price handling, duplicate-exit prevention, and oversell/over-close
prevention (force-close can only ever reduce exposure).
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
from autonomous.orb_execution import ORBPaperExecutor
from autonomous.orb_exit_manager import ORBExitManager, ORBExitManagerError
from autonomous.orb_proposals import ORBProposalStore, ProposalGates
from autonomous.orb_trade_store import ORBExitReason, ORBTradeState, ORBTradeStoreError


# ---- fixtures / helpers ---------------------------------------------------

def _candle(symbol="QQQ", o=103.0, h=103.5, l=102.8, c=103.4):
    start = datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc)
    return Candle(symbol, "5m", start, start, o, h, l, c, volume=1000.0)


def _setup(symbol="QQQ", entry=104.0, stop=103.0, target=106.0):
    rng = OpeningRange(
        symbol=symbol, session_date="2026-06-01",
        range_start=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        range_end=datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc),
        high=102.0, low=100.0, source_candle=_candle(symbol),
    )
    conf = BreakoutConfirmation(
        symbol=symbol, direction=ORBDirection.LONG, candle_5m=_candle(symbol),
        range_high=102.0, range_low=100.0,
        confirmed_at=datetime(2026, 6, 1, 9, 50, tzinfo=timezone.utc),
    )
    risk = entry - stop
    return ORBSetup(
        symbol=symbol, direction=ORBDirection.LONG,
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


def _proposal(store, strategy="ORB1", symbol="QQQ", session_date="2026-06-01",
              entry=104.0, stop=103.0, target=106.0, **kwargs):
    return store.create_from_setup(
        _setup(symbol=symbol, entry=entry, stop=stop, target=target),
        strategy_name=strategy, session_date=session_date,
        orb_state="PROPOSAL_READY", gates=ProposalGates(), **kwargs,
    )


def _executor(tmp_path, store) -> ORBPaperExecutor:
    return ORBPaperExecutor(store, audit=AuditLogger(str(tmp_path)), log_dir=str(tmp_path))


class _Clock:
    """Mutable now() for deterministic time-travel in tests."""

    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def _manager(tmp_path, prices, clock, **kwargs) -> ORBExitManager:
    return ORBExitManager(
        price_provider=lambda symbol: prices.get(symbol),
        audit=AuditLogger(str(tmp_path)), log_dir=str(tmp_path),
        now_fn=clock, **kwargs,
    )


def _open_trade(tmp_path, prices, clock, *, entry=104.0, stop=103.0, target=106.0,
                 force_flat_time="15:55", max_holding_minutes=None, entry_fill=None):
    """Build a fully-registered, OPEN ORB intraday trade ready for evaluation."""
    store = _store(tmp_path)
    proposal = _proposal(store, entry=entry, stop=stop, target=target)
    executor = _executor(tmp_path, store)
    trade = executor.execute_paper(proposal)
    mgr = _manager(tmp_path, prices, clock, id_prefix="ORB-EXIT-TEST")
    mgr.register_trade(
        trade, force_flat_time=force_flat_time, max_holding_minutes=max_holding_minutes,
    )
    mgr.mark_entry_filled(trade.trade_id, entry_fill if entry_fill is not None else entry)
    return mgr, trade.trade_id


# ---- target / stop ---------------------------------------------------------

def test_target_exit_closes_trade_with_realized_r(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 106.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == ORBExitReason.TARGET.value
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.CLOSED.value
    assert trade.exit_reason == ORBExitReason.TARGET.value
    assert trade.exit_price == 106.0  # fills at the target level, not the spike price
    assert trade.realized_r == pytest.approx(2.0)  # (106-104)/(104-103)
    assert trade.mfe_r == pytest.approx(2.5)  # best R seen before the exit fill


def test_stop_exit_closes_trade_with_negative_realized_r(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 102.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == ORBExitReason.STOP.value
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.CLOSED.value
    assert trade.exit_price == 103.0
    assert trade.realized_r == pytest.approx(-1.0)
    assert trade.mae_r == pytest.approx(-1.5)


def test_no_exit_when_price_between_stop_and_target(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == "NO_EXIT"
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.OPEN.value
    assert trade.current_r == pytest.approx(0.5)


# ---- force-flat -------------------------------------------------------------

def test_force_flat_closes_open_trade_past_flat_time(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 19, 56, tzinfo=timezone.utc))  # 15:56 NY (EDT, UTC-4)
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock, force_flat_time="15:55")

    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == ORBExitReason.FORCE_FLAT.value
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.CLOSED.value
    assert trade.exit_price == 104.5


def test_force_flat_before_time_does_not_exit(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 19, 0, tzinfo=timezone.utc))  # 15:00 NY
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock, force_flat_time="15:55")

    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == "NO_EXIT"
    assert mgr.get_trade(trade_id).state == ORBTradeState.OPEN.value


def test_force_flat_countdown_seconds(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 19, 0, tzinfo=timezone.utc))  # 15:00 NY
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock, force_flat_time="15:55")
    trade = mgr.get_trade(trade_id)
    seconds = mgr.force_flat_countdown_seconds(trade)
    assert seconds == pytest.approx(55 * 60, abs=1)


# ---- max holding minutes -----------------------------------------------------

def test_max_holding_minutes_exit(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock, max_holding_minutes=30)

    # Not yet elapsed.
    decision = mgr.evaluate_trade(trade_id)
    assert decision.decision == "NO_EXIT"

    clock.now = clock.now.replace(minute=31)
    decision = mgr.evaluate_trade(trade_id)
    assert decision.decision == ORBExitReason.MAX_HOLDING_MINUTES.value
    assert mgr.get_trade(trade_id).state == ORBTradeState.CLOSED.value


# ---- emergency stop -----------------------------------------------------------

def test_emergency_stop_flattens_open_trade_regardless_of_price(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 104.5}  # inside stop/target band; would otherwise be NO_EXIT
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    mgr.trip_emergency_stop()
    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == ORBExitReason.EMERGENCY_STOP.value
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.CLOSED.value
    assert trade.exit_price == 104.5

    mgr.reset_emergency_stop()
    assert not mgr.emergency_stopped


# ---- manual close ---------------------------------------------------------

def test_manual_close_flattens_open_trade(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    decision = mgr.close_now(trade_id)

    assert decision.decision == ORBExitReason.MANUAL_CLOSE.value
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.CLOSED.value
    assert trade.exit_price == 104.5


def test_manual_close_requires_open_trade(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 106.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)
    mgr.evaluate_trade(trade_id)  # closes on TARGET
    assert mgr.get_trade(trade_id).state == ORBTradeState.CLOSED.value

    with pytest.raises(ORBExitManagerError):
        mgr.close_now(trade_id)


def test_cancel_entry_before_fill_never_opens_exposure(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(tmp_path, store)
    trade = executor.execute_paper(proposal)
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    mgr = _manager(tmp_path, {"QQQ": 104.0}, clock)
    mgr.register_trade(trade)

    assert mgr.get_trade(trade.trade_id).state == ORBTradeState.ENTRY_PENDING.value
    cancelled = mgr.cancel_entry(trade.trade_id)
    assert cancelled.state == ORBTradeState.CLOSED.value
    assert cancelled.exit_reason == ORBExitReason.ENTRY_CANCELLED.value

    # Cancelling twice, or cancelling an already-open trade, is rejected —
    # never silently re-opens or increases exposure.
    with pytest.raises(ORBExitManagerError):
        mgr.cancel_entry(trade.trade_id)


def test_cancel_entry_rejected_once_open(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)
    with pytest.raises(ORBExitManagerError):
        mgr.cancel_entry(trade_id)


# ---- missing price ----------------------------------------------------------

def test_missing_price_leaves_trade_open_with_no_price_decision(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {}  # no quote available
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == "NO_PRICE_AVAILABLE"
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.OPEN.value  # never guesses a fill


def test_force_flat_with_no_price_marks_failed_not_silently_open(tmp_path):
    """Force-flat boundary hit but no price: must record an explicit failure,
    never remain silently OPEN past the mandatory flatten time."""
    clock = _Clock(datetime(2026, 6, 1, 19, 56, tzinfo=timezone.utc))  # 15:56 NY
    prices = {}
    mgr, trade_id = _open_trade(tmp_path, prices, clock, force_flat_time="15:55")

    decision = mgr.evaluate_trade(trade_id)

    assert decision.decision == "NO_PRICE_AVAILABLE"
    trade = mgr.get_trade(trade_id)
    assert trade.state == ORBTradeState.FAILED.value
    assert trade.failure_note and "no live price" in trade.failure_note


# ---- duplicate exit / oversell prevention -----------------------------------

def test_duplicate_exit_evaluation_is_a_no_op(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 106.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    first = mgr.evaluate_trade(trade_id)
    assert first.decision == ORBExitReason.TARGET.value
    trade_after_first = mgr.get_trade(trade_id)
    first_exit_order_id = trade_after_first.exit_order_id

    # Re-evaluating an already-CLOSED trade must never mint a second exit
    # order or otherwise touch the trade (evaluate_trade only considers OPEN
    # trades to begin with).
    second = mgr.evaluate_trade(trade_id)
    assert second is None
    trade_after_second = mgr.get_trade(trade_id)
    assert trade_after_second.exit_order_id == first_exit_order_id
    assert trade_after_second.state == ORBTradeState.CLOSED.value


def test_close_now_after_target_fill_is_rejected_not_duplicated(tmp_path):
    """close_now on an already-closed trade must never place a second, larger
    reducing order (oversell/over-close prevention)."""
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 106.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)
    mgr.evaluate_trade(trade_id)
    assert mgr.get_trade(trade_id).state == ORBTradeState.CLOSED.value

    with pytest.raises(ORBExitManagerError):
        mgr.close_now(trade_id)
    # Quantity/exit price are unchanged — no second sell was ever placed.
    trade = mgr.get_trade(trade_id)
    assert trade.exit_price == 106.0


def test_request_exit_never_increases_quantity_and_is_idempotent(tmp_path):
    """Directly exercises the trade-store guarantee: a second exit request
    against a non-OPEN trade is a no-op, and the exit quantity always equals
    the trade's original (never increased) quantity."""
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 106.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)
    original_quantity = mgr.get_trade(trade_id).quantity

    mgr.evaluate_trade(trade_id)  # first (and only legitimate) exit
    trade = mgr.get_trade(trade_id)
    assert trade.quantity == original_quantity  # never resized upward

    # A raw duplicate request against the underlying store is also a no-op.
    pending = mgr.store.request_exit(
        trade_id, ORBExitReason.MANUAL_CLOSE, requested_price=999.0,
        exit_order_id="should-not-apply",
    )
    assert pending is None
    assert mgr.get_trade(trade_id).exit_order_id != "should-not-apply"


# ---- registration / monitor fields ------------------------------------------

def test_registered_trade_exposes_monitor_fields(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(tmp_path, store)
    trade = executor.execute_paper(proposal)
    clock = _Clock(datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc))
    mgr = _manager(tmp_path, {"QQQ": 104.0}, clock)
    intraday = mgr.register_trade(trade, force_flat_time="15:55", max_holding_minutes=60)

    assert intraday.trade_id == trade.trade_id
    assert intraday.proposal_id == proposal.proposal_id
    assert intraday.strategy_name == "ORB1"
    assert intraday.symbol == "QQQ"
    assert intraday.entry_model == proposal.entry_model
    assert intraday.protection_status == trade.protection_status
    assert intraday.state == ORBTradeState.ENTRY_PENDING.value

    mgr.mark_entry_filled(trade.trade_id, 104.1)
    filled = mgr.get_trade(trade.trade_id)
    assert filled.state == ORBTradeState.OPEN.value
    assert filled.entry_slippage == pytest.approx(0.1)
    assert filled.actual_entry_price == 104.1


def test_entry_failure_marks_trade_failed(tmp_path):
    store = _store(tmp_path)
    proposal = _proposal(store)
    executor = _executor(tmp_path, store)
    trade = executor.execute_paper(proposal)
    clock = _Clock(datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc))
    mgr = _manager(tmp_path, {"QQQ": 104.0}, clock)
    mgr.register_trade(trade)

    failed = mgr.mark_entry_failed(trade.trade_id, "broker rejected entry order")
    assert failed.state == ORBTradeState.FAILED.value
    assert failed.exit_reason == ORBExitReason.BROKER_FAILURE.value


# ---- disable-new-entries operator gate (does not touch open trades) --------

def test_disable_new_entries_does_not_affect_existing_open_trade(tmp_path):
    clock = _Clock(datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc))
    prices = {"QQQ": 104.5}
    mgr, trade_id = _open_trade(tmp_path, prices, clock)

    mgr.disable_new_entries("ORB1")
    assert mgr.new_entries_disabled("ORB1")

    # The already-open trade is unaffected and still evaluates normally.
    decision = mgr.evaluate_trade(trade_id)
    assert decision.decision == "NO_EXIT"
    assert mgr.get_trade(trade_id).state == ORBTradeState.OPEN.value

    mgr.enable_new_entries("ORB1")
    assert not mgr.new_entries_disabled("ORB1")
