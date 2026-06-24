"""Tests for autonomous trade/order fill reconciliation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from autonomous.trade_reconciler import TradeReconciler
from autonomous.trade_store import (
    CLOSED,
    EXIT_PENDING,
    FAILED,
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


def test_exit_pending_trade_reopens_when_exit_order_is_rejected(tmp_path):
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
                "status": "REJECTED",
            }
        ],
    ).reconcile()

    trade = store.get("t1")
    assert result.exit_fills == 0
    assert trade is not None
    assert trade.status == OPEN
    assert trade.exit_order_id is None
    assert any("reverted to OPEN for retry" in note for note in (trade.notes or []))


def test_exit_pending_trade_reopens_when_exit_order_is_inactive(tmp_path):
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
                "order_id": 200,
                "status": "INACTIVE",
            }
        ],
    ).reconcile()

    trade = store.get("t1")
    assert result.exit_fills == 0
    assert trade is not None
    assert trade.status == OPEN
    assert trade.exit_order_id is None


def test_exit_pending_without_entry_fill_is_marked_failed(tmp_path):
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
            entry_filled_price=None,
            quantity=10,
            exit_order_id=200,
            exit_reason="TAKE_PROFIT",
        )
    )

    result = TradeReconciler(
        store,
        orders_provider=lambda: [
            {"order_id": 200, "status": "SUBMITTED"},
        ],
    ).reconcile()

    trade = store.get("t1")
    assert result.exit_fills == 0
    assert trade is not None
    assert trade.status == FAILED
    assert trade.exit_price is None
    assert trade.realised_pnl is None


def test_stale_unconfirmed_exit_pending_reopens_for_retry(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    stale_exit_time = datetime.now(timezone.utc) - timedelta(seconds=120)
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
            exit_time=stale_exit_time,
            exit_reason="TAKE_PROFIT",
        )
    )

    result = TradeReconciler(
        store,
        orders_provider=lambda: [],
    ).reconcile(now=datetime.now(timezone.utc))

    trade = store.get("t1")
    assert result.exit_fills == 0
    assert any("exit unconfirmed" in note for note in result.notes)
    assert trade is not None
    assert trade.status == OPEN
    assert trade.exit_order_id is None
    assert trade.exit_time is None


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


def _stale_exit_pending_store(tmp_path):
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    stale_exit_time = datetime.now(timezone.utc) - timedelta(seconds=120)
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
            exit_time=stale_exit_time,
            exit_reason="TAKE_PROFIT",
        )
    )
    return store


def test_stale_exit_cancels_broker_order_before_revert(tmp_path):
    """A stale unconfirmed exit must cancel the working order at the broker
    BEFORE reverting to OPEN, so the retry cannot double-fill into a short."""
    store = _stale_exit_pending_store(tmp_path)
    cancelled: list[int] = []

    def _cancel(order_id: int) -> bool:
        cancelled.append(order_id)
        return True

    result = TradeReconciler(
        store,
        orders_provider=lambda: [],
        cancel_order_provider=_cancel,
    ).reconcile(now=datetime.now(timezone.utc))

    trade = store.get("t1")
    assert cancelled == [200]
    assert trade is not None
    assert trade.status == OPEN
    assert trade.exit_order_id is None
    assert trade.exit_time is None
    assert any("cancelled and reverted" in n for n in (trade.notes or []))


def test_stale_exit_kept_pending_when_cancel_not_confirmed(tmp_path):
    """If the broker cancel cannot be confirmed, the trade must stay
    EXIT_PENDING (fail closed) rather than orphan a live SELL order."""
    store = _stale_exit_pending_store(tmp_path)

    def _cancel(order_id: int) -> bool:
        return False

    result = TradeReconciler(
        store,
        orders_provider=lambda: [],
        cancel_order_provider=_cancel,
    ).reconcile(now=datetime.now(timezone.utc))

    trade = store.get("t1")
    assert result.exit_fills == 0
    assert any("exit cancel unconfirmed" in n for n in result.notes)
    assert trade is not None
    assert trade.status == EXIT_PENDING
    assert trade.exit_order_id == 200


def test_stale_exit_kept_pending_when_cancel_raises(tmp_path):
    """If the cancel hook raises, fail closed and keep EXIT_PENDING."""
    store = _stale_exit_pending_store(tmp_path)

    def _cancel(order_id: int) -> bool:
        raise ConnectionError("TWS disconnected")

    result = TradeReconciler(
        store,
        orders_provider=lambda: [],
        cancel_order_provider=_cancel,
    ).reconcile(now=datetime.now(timezone.utc))

    trade = store.get("t1")
    assert any("exit cancel unconfirmed" in n for n in result.notes)
    assert trade is not None
    assert trade.status == EXIT_PENDING
    assert trade.exit_order_id == 200
