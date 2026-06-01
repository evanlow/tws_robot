"""Tests for the autonomous trade lifecycle store."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from autonomous.trade_store import (
    CLOSED,
    EXIT_PENDING,
    OPEN,
    AutonomousTrade,
    TradeStore,
)


def _trade(symbol="AAA", **overrides):
    base = dict(
        autonomous_trade_id=overrides.pop("autonomous_trade_id", AutonomousTrade.new_id()),
        symbol=symbol,
        trade_type="buy_shares",
        status=OPEN,
        entry_order_id=42,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=10,
        target_price=110.0,
        stop_price=95.0,
        max_holding_days=5,
    )
    base.update(overrides)
    return AutonomousTrade(**base)


def test_record_and_read_open_trade(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    trade = _trade()
    store.record_trade(trade)

    open_trades = store.list_open()
    assert len(open_trades) == 1
    assert open_trades[0].autonomous_trade_id == trade.autonomous_trade_id
    assert store.count_open() == 1


def test_update_trade_to_exit_pending(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    trade = _trade()
    store.record_trade(trade)

    store.update_trade(
        trade.autonomous_trade_id,
        status=EXIT_PENDING,
        exit_order_id=99,
        exit_reason="STOP_LOSS",
    )
    refreshed = store.get(trade.autonomous_trade_id)
    assert refreshed.status == EXIT_PENDING
    assert refreshed.exit_order_id == 99
    assert refreshed.exit_reason == "STOP_LOSS"
    assert store.count_open() == 0


def test_update_trade_to_closed(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    trade = _trade()
    store.record_trade(trade)
    store.update_trade(
        trade.autonomous_trade_id,
        status=CLOSED,
        exit_price=110.5,
        realised_pnl=105.0,
    )
    closed = store.list_closed()
    assert len(closed) == 1
    assert closed[0].exit_price == 110.5
    assert closed[0].realised_pnl == 105.0


def test_invalid_status_rejected(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    trade = _trade()
    store.record_trade(trade)
    with pytest.raises(ValueError):
        store.update_trade(trade.autonomous_trade_id, status="BOGUS")


def test_malformed_lines_are_tolerated(tmp_path):
    path = tmp_path / "trades.jsonl"
    store = TradeStore(path=str(path))
    trade = _trade(symbol="BBB")
    store.record_trade(trade)
    # Append malformed garbage that must not crash readers.
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{this is not json\n")
        fh.write("\n")
        fh.write('{"op":"UPDATE"}\n')  # missing trade id — must be ignored
    open_trades = store.list_open()
    assert len(open_trades) == 1
    assert open_trades[0].symbol == "BBB"


def test_replay_after_reopen(tmp_path):
    """Persistence works across new TradeStore instances pointed at the same file."""
    path = str(tmp_path / "trades.jsonl")
    store1 = TradeStore(path=path)
    trade = _trade(symbol="ZZZ")
    store1.record_trade(trade)
    store1.update_trade(trade.autonomous_trade_id, entry_filled_price=99.5)

    store2 = TradeStore(path=path)
    refreshed = store2.get(trade.autonomous_trade_id)
    assert refreshed is not None
    assert refreshed.entry_filled_price == 99.5
    assert refreshed.symbol == "ZZZ"
