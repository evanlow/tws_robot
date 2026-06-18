"""Tests for autonomous trade/order fill reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone

from autonomous.trade_reconciler import TradeReconciler
from autonomous.trade_store import (
    CLOSED,
    EXIT_PENDING,
    OPEN,
    AutonomousTrade,
    TradeStore,
)


def test_exit_pending_trade_closes_when_exit_order_is_filled(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    store.record_trade(
        AutonomousTrade(
            autonomous_trade_id="t1",
            symbol="AAA",
            trade_type="buy_shares",
            status=EXIT_PENDING,
            entry_order_id=100,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            entry_filled_price=100.0,
            quantity=10,
            exit_order_id=200,
            exit_reason="TAKE_PROFIT",
        )
    )

    reconciler = TradeReconciler(
        store,
        orders_provider=lambda: [
            {
                "broker_order_id": 200,
                "status": "FILLED",
                "avg_fill_price": 111.25,
                "filled": 10,
            }
        ],
    )

    result = reconciler.reconcile()

    trade = store.get("t1")
    assert result.exit_fills == 1
    assert trade is not None
    assert trade.status == CLOSED
    assert trade.exit_price == 111.25
    assert trade.realised_pnl == 112.5
    assert trade.exit_time is not None


def test_exit_pending_trade_ignores_fill_with_remaining_quantity(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    store.record_trade(
        AutonomousTrade(
            autonomous_trade_id="t1",
            symbol="AAA",
            trade_type="buy_shares",
            status=EXIT_PENDING,
            entry_order_id=100,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            entry_filled_price=100.0,
            quantity=10,
            exit_order_id=200,
            exit_reason="TAKE_PROFIT",
        )
    )

    result = TradeReconciler(
        store,
        orders_provider=lambda: [
            {
                "broker_order_id": 200,
                "status": "FILLED",
                "avg_fill_price": 111.25,
                "filled": 5,
                "remaining": 5,
            }
        ],
    ).reconcile()

    trade = store.get("t1")
    assert result.exit_fills == 0
    assert trade is not None
    assert trade.status == EXIT_PENDING
    assert trade.exit_price is None


def test_open_trade_records_entry_fill_price(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    store.record_trade(
        AutonomousTrade(
            autonomous_trade_id="t1",
            symbol="AAA",
            trade_type="buy_shares",
            status=OPEN,
            entry_order_id=100,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            quantity=10,
        )
    )

    result = TradeReconciler(
        store,
        orders_provider=lambda: [
            {"id": 100, "status": "Filled", "avgFillPrice": 99.75}
        ],
    ).reconcile()

    trade = store.get("t1")
    assert result.entry_fills == 1
    assert trade is not None
    assert trade.status == OPEN
    assert trade.entry_filled_price == 99.75


def test_non_buy_shares_trade_is_ignored(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    store.record_trade(
        AutonomousTrade(
            autonomous_trade_id="t1",
            symbol="AAA",
            trade_type="SELL_CASH_SECURED_PUT",
            status=EXIT_PENDING,
            entry_order_id=100,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            entry_filled_price=100.0,
            quantity=0,
            exit_order_id=200,
            exit_reason="TAKE_PROFIT",
        )
    )

    result = TradeReconciler(
        store,
        orders_provider=lambda: [
            {
                "broker_order_id": 200,
                "status": "FILLED",
                "avg_fill_price": 1.5,
                "filled": 1,
            }
        ],
    ).reconcile()

    trade = store.get("t1")
    assert result.exit_fills == 0
    assert trade is not None
    assert trade.status == EXIT_PENDING
    assert trade.exit_price is None
