from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from autonomous import (
    AutonomousLiveRunner,
    AutonomousLiveRunnerConfig,
    AutonomousMode,
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    CandidateSignal,
    IdempotencyStore,
    OrderLifecycleState,
    OrderLifecycleStore,
    ProtectionVerifier,
    StaticSignalProvider,
)
from autonomous.audit import AuditLogger
from autonomous.trade_store import AutonomousTrade, OPEN, TradeStore
from data.cash_availability import CashAvailabilityAnalyzer
from execution.order_executor import OrderResult, OrderStatus


class _RealProvider:
    pass


class _BracketSubmittingExecutor:
    def __init__(self, parent_id: int = 700, target_id: int = 701, stop_id: int = 702):
        self.parent_id = parent_id
        self.target_id = target_id
        self.stop_id = stop_id
        self.calls = []

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        self.calls.append(signal.symbol)
        result = OrderResult(
            status=OrderStatus.SUBMITTED,
            order_id=self.parent_id,
            signal=signal,
            quantity=signal.quantity,
            price=signal.target_price or 0.0,
            reason="bracket submitted",
        )
        result.bracket_target_order_id = self.target_id
        result.bracket_stop_order_id = self.stop_id
        return result


def _signal(symbol: str = "AAA") -> CandidateSignal:
    return CandidateSignal(
        symbol=symbol,
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )


def _build_engine(tmp_path: Path, *, signal: CandidateSignal) -> AutonomousTradingEngine:
    provider = StaticSignalProvider([signal])
    scanner = CandidateScanner(
        signal_provider=provider,
        symbols=[{"symbol": signal.symbol, "security": signal.symbol, "sector": "X", "sub_industry": ""}],
    )
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        require_user_confirmation=True,
        max_trades_per_day=5,
        audit_log_dir=str(tmp_path),
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {"cash_balance": 100_000, "equity": 100_000},
        positions_provider=lambda: {},
        config=cfg,
        paper_adapter=None,
        audit_logger=AuditLogger(log_dir=str(tmp_path)),
    )


def _runner(
    tmp_path: Path,
    *,
    lifecycle_store: OrderLifecycleStore,
    trade_store: TradeStore | None = None,
    executor=None,
    rejected_order_ids_provider=None,
    filled_order_ids_provider=None,
    broker_positions_provider=None,
    broker_open_orders_provider=None,
    idempotency_store: IdempotencyStore | None = None,
    require_broker_protection_confirmation: bool = True,
) -> AutonomousLiveRunner:
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        max_open_live_trades=5,
        max_live_trades_per_day=5,
        require_broker_protection_confirmation=require_broker_protection_confirmation,
        trade_store_path=str(tmp_path / "live_trades.jsonl"),
        order_lifecycle_store_path=str(tmp_path / "lifecycle.jsonl"),
        idempotency_store_path=str(tmp_path / "idempotency.jsonl"),
    )
    store = trade_store or TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    return AutonomousLiveRunner(
        engine=_build_engine(tmp_path, signal=_signal()),
        trade_store=store,
        live_config=cfg,
        order_executor=executor or _BracketSubmittingExecutor(),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _RealProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 50_000.0,
        broker_positions_provider=broker_positions_provider,
        rejected_order_ids_provider=rejected_order_ids_provider,
        filled_order_ids_provider=filled_order_ids_provider,
        broker_open_orders_provider=broker_open_orders_provider,
        order_lifecycle_store=lifecycle_store,
        idempotency_store=idempotency_store,
    )


def test_order_lifecycle_store_replays_latest_state(tmp_path):
    store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))

    store.record_transition(
        lifecycle_id="order-1",
        state=OrderLifecycleState.PLANNED,
        symbol="AAA",
        reason="planned",
    )
    store.record_transition(
        lifecycle_id="order-1",
        state=OrderLifecycleState.SUBMITTED,
        symbol="AAA",
        broker_order_id=700,
        reason="submitted",
    )

    events = store.list_events("order-1")
    assert [event.state for event in events] == [
        OrderLifecycleState.PLANNED,
        OrderLifecycleState.SUBMITTED,
    ]
    assert store.get_current("order-1").state == OrderLifecycleState.SUBMITTED


def test_live_runner_records_submitted_entry_and_bracket_child_lifecycle(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    runner = _runner(tmp_path, lifecycle_store=lifecycle_store)

    result = runner.run_once()

    assert result.status == "executed"
    trade = result.trade["submitted_trades"][0]
    current = lifecycle_store.current_states()
    assert current[trade["entry_lifecycle_id"]].state == OrderLifecycleState.SUBMITTED
    assert current[trade["target_lifecycle_id"]].state == OrderLifecycleState.TARGET_PENDING
    assert current[trade["stop_lifecycle_id"]].state == OrderLifecycleState.PROTECTIVE_STOP_PENDING
    assert current[trade["entry_lifecycle_id"]].broker_order_id == 700
    assert {event["state"] for event in result.order_lifecycle} >= {
        "PLANNED",
        "SUBMITTED",
        "TARGET_PENDING",
        "PROTECTIVE_STOP_PENDING",
    }


def test_live_runner_marks_idempotency_lock_submitted_after_broker_acceptance(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    idempotency_store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))
    runner = _runner(
        tmp_path,
        lifecycle_store=lifecycle_store,
        idempotency_store=idempotency_store,
    )

    result = runner.run_once()

    assert result.status == "executed"
    active = idempotency_store.active_locks()
    assert len(active) == 1
    lock = active[0]
    assert lock.key == "autonomous-live:BUY:AAA"
    assert lock.status == "SUBMITTED"
    assert lock.broker_order_id == 700
    assert lock.autonomous_trade_id == result.trade["submitted_trades"][0]["autonomous_trade_id"]


def test_live_runner_blocks_entry_when_idempotency_lock_active(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    idempotency_store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))
    idempotency_store.acquire(symbol="AAA", intended_action="BUY", run_id="prior-run")
    executor = _BracketSubmittingExecutor()
    runner = _runner(
        tmp_path,
        lifecycle_store=lifecycle_store,
        idempotency_store=idempotency_store,
        executor=executor,
    )

    result = runner.run_once()

    assert result.status == "restart_recovery_required"
    assert executor.calls == []
    assert result.order_lifecycle == []
    assert "idempotency lock" in result.rejection_reason


def test_live_runner_blocks_duplicate_symbol_open_trade_before_submission(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    trade_store = TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    trade_store.record_trade(
        AutonomousTrade(
            autonomous_trade_id=AutonomousTrade.new_id(),
            symbol="AAA",
            trade_type="BUY_SHARES",
            status=OPEN,
            entry_order_id=7,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            quantity=1,
        )
    )
    executor = _BracketSubmittingExecutor()
    runner = _runner(
        tmp_path,
        lifecycle_store=lifecycle_store,
        trade_store=trade_store,
        executor=executor,
        require_broker_protection_confirmation=False,
        broker_positions_provider=lambda: {"AAA": {"quantity": 1}},
    )

    result = runner.run_once()

    assert result.status == "duplicate_order_blocked"
    assert executor.calls == []
    assert result.order_lifecycle[0]["state"] == "DUPLICATE_ORDER_BLOCKED"
    assert "open autonomous trade already exists" in result.rejection_reason


def test_rejected_order_reconciliation_writes_rejected_lifecycle(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    trade_store = TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=7,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=1,
        entry_lifecycle_id="entry-lifecycle",
    )
    trade_store.record_trade(trade)
    runner = _runner(
        tmp_path,
        lifecycle_store=lifecycle_store,
        trade_store=trade_store,
        rejected_order_ids_provider=lambda: {7},
    )

    runner.evaluate_gates()

    assert lifecycle_store.get_current("entry-lifecycle").state == OrderLifecycleState.REJECTED


def test_bracket_fill_writes_child_filled_and_parent_closed_lifecycle(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    trade_store = TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=700,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=1,
        target_order_id=701,
        stop_order_id=702,
        entry_lifecycle_id="entry-lifecycle",
        target_lifecycle_id="target-lifecycle",
        stop_lifecycle_id="stop-lifecycle",
    )
    trade_store.record_trade(trade)
    runner = _runner(
        tmp_path,
        lifecycle_store=lifecycle_store,
        trade_store=trade_store,
        filled_order_ids_provider=lambda: {702},
    )

    runner.evaluate_gates()

    assert lifecycle_store.get_current("stop-lifecycle").state == OrderLifecycleState.FILLED
    assert lifecycle_store.get_current("entry-lifecycle").state == OrderLifecycleState.CLOSED


def test_protection_verifier_confirms_matching_active_stop_quantity():
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=700,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=5,
        stop_order_id=702,
    )

    result = ProtectionVerifier().verify_trade(
        trade,
        broker_positions={"AAA": {"quantity": 3}},
        open_orders=[
            {
                "order_id": 702,
                "symbol": "AAA",
                "action": "SELL",
                "order_type": "STP",
                "quantity": 3,
                "status": "Submitted",
            }
        ],
    )

    assert result.protected is True
    assert result.recovery_required is False
    assert result.expected_quantity == 3


def test_live_runner_marks_recovery_required_when_protection_missing(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    trade_store = TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=700,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=2,
        stop_order_id=702,
        entry_lifecycle_id="entry-lifecycle",
        stop_lifecycle_id="stop-lifecycle",
    )
    trade_store.record_trade(trade)
    runner = _runner(
        tmp_path,
        lifecycle_store=lifecycle_store,
        trade_store=trade_store,
        broker_positions_provider=lambda: {"AAA": {"quantity": 2}},
        broker_open_orders_provider=lambda: [],
    )

    gates = runner.evaluate_gates()

    assert gates.ready is False
    assert gates.protection_recovery_required == 1
    assert lifecycle_store.get_current("stop-lifecycle").state == OrderLifecycleState.RECOVERY_REQUIRED


def test_live_runner_confirms_protective_stop_before_new_entry_capacity(tmp_path):
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    trade_store = TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=700,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=2,
        stop_order_id=702,
        entry_lifecycle_id="entry-lifecycle",
        stop_lifecycle_id="stop-lifecycle",
    )
    trade_store.record_trade(trade)
    runner = _runner(
        tmp_path,
        lifecycle_store=lifecycle_store,
        trade_store=trade_store,
        broker_positions_provider=lambda: {"AAA": {"quantity": 2}},
        broker_open_orders_provider=lambda: [
            {
                "order_id": 702,
                "symbol": "AAA",
                "action": "SELL",
                "order_type": "STP",
                "quantity": 2,
                "remaining": 2,
                "status": "Submitted",
                "parent_id": 700,
            }
        ],
    )

    gates = runner.evaluate_gates()

    assert gates.ready is True
    assert gates.protection_recovery_required == 0
    assert lifecycle_store.get_current("stop-lifecycle").state == (
        OrderLifecycleState.PROTECTIVE_STOP_CONFIRMED
    )
