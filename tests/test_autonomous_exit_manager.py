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


# ---------------------------------------------------------------------------
# Fix #1: Live exit via order_executor
# ---------------------------------------------------------------------------


class _SubmittingOrderExecutor:
    """Stub OrderExecutor that always returns SUBMITTED for any signal."""

    def __init__(self, order_id: int = 5555) -> None:
        self._order_id = order_id
        self.calls: list = []

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        from execution.order_executor import OrderResult, OrderStatus
        self.calls.append({"symbol": signal.symbol, "price": signal.target_price})
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            order_id=self._order_id,
            signal=signal,
            quantity=signal.quantity or 1,
            price=signal.target_price or 0.0,
            reason=f"Order {self._order_id} submitted",
        )


class _RejectingOrderExecutor:
    """Stub OrderExecutor that always returns REJECTED."""

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        from execution.order_executor import OrderResult, OrderStatus, RejectionReason
        return OrderResult(
            status=OrderStatus.REJECTED,
            order_id=None,
            signal=signal,
            quantity=signal.quantity or 1,
            price=0.0,
            reason="Rejected by test stub",
            rejection_reason=RejectionReason.PRICE_SANITY_FAILED,
        )


def test_order_executor_exit_submits_sell_and_marks_exit_pending(store, tmp_path):
    """When paper_adapter=None and order_executor is provided, a triggered exit
    must call execute_signal on the executor and mark the trade EXIT_PENDING."""
    trade = _open_trade()  # target=110, stop=95, last_price will trigger at 112
    store.record_trade(trade)
    executor = _SubmittingOrderExecutor(order_id=7777)
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=None,
        order_executor=executor,
        positions_provider=lambda: {"AAA": {"current_price": 112.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    decisions = mgr.evaluate_open_trades()
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision == TAKE_PROFIT
    assert len(executor.calls) == 1
    assert executor.calls[0]["symbol"] == "AAA"
    assert executor.calls[0]["price"] == 112.0
    assert store.get(trade.autonomous_trade_id).status == "EXIT_PENDING"


def test_order_executor_exit_rejected_leaves_trade_open(store, tmp_path):
    """When the order_executor rejects the exit order, trade must stay OPEN."""
    trade = _open_trade()
    store.record_trade(trade)
    executor = _RejectingOrderExecutor()
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=None,
        order_executor=executor,
        positions_provider=lambda: {"AAA": {"current_price": 112.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    decisions = mgr.evaluate_open_trades()
    d = decisions[0]
    # Rejection → NO_EXIT returned, trade remains OPEN
    assert d.decision == NO_EXIT
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


def test_no_paper_adapter_and_no_order_executor_records_no_exit(store, tmp_path):
    """When neither paper_adapter nor order_executor is set, the manager must
    return NO_EXIT with an explanatory reason (not raise)."""
    trade = _open_trade()
    store.record_trade(trade)
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=None,
        order_executor=None,
        positions_provider=lambda: {"AAA": {"current_price": 112.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    decisions = mgr.evaluate_open_trades()
    d = decisions[0]
    assert d.decision == NO_EXIT
    assert "no paper_adapter" in d.reason or "order_executor" in d.reason
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


# ---------------------------------------------------------------------------
# Live exit via OrderExecutor with realistic equity/positions
# ---------------------------------------------------------------------------


class _CapturingOrderExecutor:
    """Stub OrderExecutor that captures the equity/positions passed in and
    returns SUBMITTED if quantity matches, or REJECTED otherwise."""

    def __init__(self, tws_quantity: int = 10) -> None:
        self._tws_quantity = tws_quantity
        self.calls: list = []

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        from execution.order_executor import OrderResult, OrderStatus, RejectionReason
        self.calls.append({
            "symbol": signal.symbol,
            "price": signal.target_price,
            "quantity": signal.quantity,
            "current_equity": current_equity,
            "positions": positions,
        })
        # Simulate quantity check: if the signal quantity exceeds TWS
        # position size, reject the exit (mirrors what a real executor's
        # reconciliation would do).
        if signal.quantity > self._tws_quantity:
            return OrderResult(
                status=OrderStatus.REJECTED,
                order_id=None,
                signal=signal,
                quantity=signal.quantity,
                price=0.0,
                reason=(
                    f"SELL qty {signal.quantity} exceeds TWS position "
                    f"qty {self._tws_quantity}"
                ),
            )
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            order_id=9999,
            signal=signal,
            quantity=signal.quantity,
            price=signal.target_price or 0.0,
            reason="Order 9999 submitted",
        )


def test_live_exit_passes_realistic_equity_and_positions(store, tmp_path):
    """A TAKE_PROFIT live exit must supply current_equity > 0 and a positions
    dict containing the trade's symbol/quantity so OrderExecutor sanity checks
    and portfolio reconciliation can pass."""
    trade = _open_trade()  # qty=10, entry_limit_price=100
    store.record_trade(trade)
    executor = _CapturingOrderExecutor(tws_quantity=10)
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=None,
        order_executor=executor,
        positions_provider=lambda: {"AAA": {"current_price": 112.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    decisions = mgr.evaluate_open_trades()
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision == TAKE_PROFIT
    assert store.get(trade.autonomous_trade_id).status == "EXIT_PENDING"

    # Verify realistic values were passed to the executor
    call = executor.calls[0]
    assert call["current_equity"] > 0.0, "equity must not be zero"
    assert call["current_equity"] >= call["price"], (
        "equity must be >= limit price for sanity check"
    )
    positions = call["positions"]
    assert trade.symbol in positions
    pos = positions[trade.symbol]
    assert pos.quantity == trade.quantity


def test_live_exit_rejected_when_tws_position_insufficient(store, tmp_path):
    """If TWS has fewer shares than the exit order quantity, the executor must
    reject the exit and the trade stays OPEN."""
    trade = _open_trade()  # qty=10
    store.record_trade(trade)
    # TWS only has 5 shares — exit of 10 should be rejected
    executor = _CapturingOrderExecutor(tws_quantity=5)
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=None,
        order_executor=executor,
        positions_provider=lambda: {"AAA": {"current_price": 112.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    decisions = mgr.evaluate_open_trades()
    d = decisions[0]
    assert d.decision == NO_EXIT
    assert "exceeds TWS position" in d.reason or "rejected" in d.reason
    assert store.get(trade.autonomous_trade_id).status == "OPEN"


def test_live_stop_loss_exit_submitted_with_realistic_equity(store, tmp_path):
    """A STOP_LOSS live exit also gets realistic equity/positions and is
    actually submitted (not just evaluated)."""
    trade = _open_trade()  # stop=95
    store.record_trade(trade)
    executor = _CapturingOrderExecutor(tws_quantity=10)
    mgr = AutonomousExitManager(
        trade_store=store,
        paper_adapter=None,
        order_executor=executor,
        positions_provider=lambda: {"AAA": {"current_price": 90.0}},
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    decisions = mgr.evaluate_open_trades()
    d = decisions[0]
    assert d.decision == STOP_LOSS
    assert store.get(trade.autonomous_trade_id).status == "EXIT_PENDING"
    call = executor.calls[0]
    assert call["current_equity"] > 0.0
    assert call["quantity"] == 10
    assert trade.symbol in call["positions"]
