"""Tests for :class:`AutonomousExitManager`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autonomous.exit_manager import (
    AutonomousExitManager,
    EXIT_PENDING,
    NO_EXIT,
    NO_PRICE_AVAILABLE,
    RISK_EXIT,
    STOP_LOSS,
    TAKE_PROFIT,
    TIME_EXIT,
)
from autonomous.trade_store import (
    AutonomousTrade,
    TradeStore,
)


class _FakeAdapter:
    def __init__(self):
        self.calls = []
        self._next_id = 1000

    def sell(self, **kw):
        self.calls.append(kw)
        self._next_id += 1
        return self._next_id


def _open_trade(symbol="AAA", *, target=110.0, stop=95.0, age_days=0):
    return AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol=symbol,
        trade_type="buy_shares",
        status="OPEN",
        entry_order_id=11,
        entry_time=datetime.now(timezone.utc) - timedelta(days=age_days),
        entry_limit_price=100.0,
        quantity=10,
        target_price=target,
        stop_price=stop,
        max_holding_days=5,
    )


@pytest.fixture
def store(tmp_path):
    return TradeStore(path=str(tmp_path / "trades.jsonl"))


def test_target_price_triggers_take_profit(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    adapter = _FakeAdapter()

    positions = {"AAA": {"current_price": 112.5}}
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: positions,
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    decisions = mgr.evaluate_open_trades()
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision == TAKE_PROFIT
    assert d.exit_order_id is not None
    assert adapter.calls and adapter.calls[0]["order_type"] == "LIMIT"
    assert adapter.calls[0]["limit_price"] == 112.5

    refreshed = store.get(trade.autonomous_trade_id)
    assert refreshed.status == EXIT_PENDING
    assert refreshed.exit_reason == TAKE_PROFIT


def test_stop_price_triggers_stop_loss(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    adapter = _FakeAdapter()
    positions = {"AAA": {"current_price": 90.0}}

    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: positions,
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == STOP_LOSS
    refreshed = store.get(trade.autonomous_trade_id)
    assert refreshed.exit_reason == STOP_LOSS


def test_time_exit(store, tmp_path):
    trade = _open_trade(age_days=10)
    store.record_trade(trade)
    adapter = _FakeAdapter()
    positions = {"AAA": {"current_price": 101.0}}  # within band

    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: positions,
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == TIME_EXIT


def test_emergency_stop_triggers_risk_exit(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    estop = tmp_path / "ESTOP"
    estop.write_text("halt")
    adapter = _FakeAdapter()

    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {"AAA": {"current_price": 100.0}},
        emergency_stop_file=str(estop),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == RISK_EXIT


def test_no_price_available_blocks_exit(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    adapter = _FakeAdapter()
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {},  # no live price
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == NO_PRICE_AVAILABLE
    assert adapter.calls == []
    # Trade must remain OPEN — no fake fill.
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


def test_no_exit_when_price_within_band(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    adapter = _FakeAdapter()
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {"AAA": {"current_price": 102.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == NO_EXIT
    assert adapter.calls == []
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


def test_no_paper_adapter_records_decision_without_order(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=None,
        positions_provider=lambda: {"AAA": {"current_price": 112.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == NO_EXIT
    assert "no paper_adapter" in d.reason
    # No fake fill: trade still OPEN.
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


def test_paper_sell_uses_limit_order_only(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    adapter = _FakeAdapter()
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {"AAA": {"current_price": 112.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    mgr.evaluate_open_trades()
    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["order_type"] == "LIMIT"
    assert call["limit_price"] > 0
    assert call["quantity"] == 10
    assert call["symbol"] == "AAA"


def test_emergency_stop_without_price_does_not_submit_blind_order(store, tmp_path):
    """RISK_EXIT must not fall back to a stale entry/target/stop price."""
    trade = _open_trade()
    store.record_trade(trade)
    estop = tmp_path / "ESTOP"
    estop.write_text("halt")
    adapter = _FakeAdapter()

    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {},  # no live price
        emergency_stop_file=str(estop),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == NO_PRICE_AVAILABLE
    assert any(n == f"would_exit:{RISK_EXIT}" for n in d.notes)
    assert adapter.calls == []
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


def test_emergency_stop_with_price_submits_paper_sell_limit(store, tmp_path):
    trade = _open_trade()
    store.record_trade(trade)
    estop = tmp_path / "ESTOP"
    estop.write_text("halt")
    adapter = _FakeAdapter()

    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {"AAA": {"current_price": 101.25}},
        emergency_stop_file=str(estop),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == RISK_EXIT
    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["order_type"] == "LIMIT"
    assert call["limit_price"] == 101.25


def test_time_exit_without_price_does_not_submit_blind_order(store, tmp_path):
    trade = _open_trade(age_days=10)
    store.record_trade(trade)
    adapter = _FakeAdapter()
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {},  # no live price
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == NO_PRICE_AVAILABLE
    assert any(n == f"would_exit:{TIME_EXIT}" for n in d.notes)
    assert adapter.calls == []
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


def test_non_buy_shares_trade_is_skipped(store, tmp_path):
    """Exit manager only acts on BUY_SHARES in this MVP."""
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="SELL_PUT",  # not BUY_SHARES
        status="OPEN",
        entry_order_id=99,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=1,
        target_price=110.0,
        stop_price=95.0,
        max_holding_days=5,
    )
    store.record_trade(trade)
    adapter = _FakeAdapter()
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=adapter,
        positions_provider=lambda: {"AAA": {"current_price": 200.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    d = mgr.evaluate_open_trades()[0]
    assert d.decision == NO_EXIT
    assert "BUY_SHARES" in d.reason
    assert adapter.calls == []
    assert store.get(trade.autonomous_trade_id).status == "OPEN"
