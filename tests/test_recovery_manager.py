from __future__ import annotations

from datetime import datetime, timezone

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
    RecoveryClassification,
    RecoveryManager,
    StaticSignalProvider,
)
from autonomous.idempotency import IdempotencyLock
from autonomous.audit import AuditLogger
from autonomous.market_data_provider import (
    IBKR_MARKET_DATA_TYPE_LIVE,
    IBKR_SOURCE,
    MarketDataProviderStatus,
    MarketDataQuote,
)
from autonomous.continuous_supervisor import (
    PAUSED,
    UNRECONCILED_LIFECYCLE_STATE,
    ContinuousSupervisor,
)
from autonomous.trade_store import OPEN, AutonomousTrade, TradeStore
from data.cash_availability import CashAvailabilityAnalyzer
from execution.order_executor import OrderResult, OrderStatus


class _RealProvider:
    pass


class _LiveMarketDataProvider:
    def __init__(self, symbol: str = "AAA", price: float = 100.0) -> None:
        now = datetime.now(timezone.utc)
        self.quote = MarketDataQuote(
            symbol=symbol,
            bid=round(price - 0.05, 2),
            ask=round(price + 0.05, 2),
            last=price,
            timestamp=now,
            bid_timestamp=now,
            ask_timestamp=now,
            last_timestamp=now,
            source=IBKR_SOURCE,
            market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
            feed_healthy=True,
        )
        self.subscribed: list[str] = []

    def subscribe(self, symbols):
        self.subscribed.extend([str(s).upper() for s in symbols])

    def unsubscribe(self, symbols):
        pass

    def latest_quote(self, symbol):
        if str(symbol).upper() == self.quote.symbol:
            return self.quote
        return None

    def status(self):
        return MarketDataProviderStatus(
            provider=IBKR_SOURCE,
            connected=True,
            healthy=True,
            subscribed_symbols=list(self.subscribed),
            market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
            last_error=None,
            reason="test market-data provider",
        )


class _Executor:
    def execute_signal(self, strategy_name, signal, current_equity, positions):
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            order_id=100,
            signal=signal,
            quantity=signal.quantity,
            price=signal.target_price or 0.0,
            reason="submitted",
        )


def _trade(
    *,
    trade_id: str = "trade-1",
    symbol: str = "AAA",
    quantity: int = 2,
    entry_order_id: int = 100,
    stop_order_id: int = 102,
    entry_lifecycle_id: str = "entry-life",
    stop_lifecycle_id: str = "stop-life",
) -> AutonomousTrade:
    return AutonomousTrade(
        autonomous_trade_id=trade_id,
        symbol=symbol,
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=entry_order_id,
        entry_time=datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc),
        entry_limit_price=100.0,
        quantity=quantity,
        stop_order_id=stop_order_id,
        entry_lifecycle_id=entry_lifecycle_id,
        stop_lifecycle_id=stop_lifecycle_id,
    )


def _manager() -> RecoveryManager:
    return RecoveryManager(idempotency_stale_minutes=30)


def _signal(symbol: str = "AAA") -> CandidateSignal:
    return CandidateSignal(
        symbol=symbol,
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
        extras={
            "bid": 99.95,
            "ask": 100.05,
            "quote_last": 100.0,
            "bid_timestamp": datetime.now(timezone.utc).isoformat(),
            "ask_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_timestamp": datetime.now(timezone.utc).isoformat(),
            "quote_timestamp": datetime.now(timezone.utc).isoformat(),
            "market_data_source": IBKR_SOURCE,
            "market_data_type": IBKR_MARKET_DATA_TYPE_LIVE,
            "market_data_status": "healthy",
            "market_data_feed_healthy": True,
            "market_is_open": True,
        },
    )


def _engine(tmp_path, *, signal: CandidateSignal | None = None) -> AutonomousTradingEngine:
    signal = signal or _signal()
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
    tmp_path,
    *,
    trade_store: TradeStore,
    lifecycle_store: OrderLifecycleStore,
    idempotency_store: IdempotencyStore,
    broker_positions,
    broker_open_orders,
) -> AutonomousLiveRunner:
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        max_open_live_trades=5,
        max_live_trades_per_day=5,
        trade_store_path=str(tmp_path / "trades.jsonl"),
        order_lifecycle_store_path=str(tmp_path / "lifecycle.jsonl"),
        idempotency_store_path=str(tmp_path / "idempotency.jsonl"),
    )
    return AutonomousLiveRunner(
        engine=_engine(tmp_path),
        trade_store=trade_store,
        live_config=cfg,
        order_executor=_Executor(),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _RealProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 50_000.0,
        broker_positions_provider=lambda: broker_positions,
        broker_open_orders_provider=lambda: broker_open_orders,
        order_lifecycle_store=lifecycle_store,
        idempotency_store=idempotency_store,
        market_data_provider=_LiveMarketDataProvider(),
    )


def test_recovery_manager_classifies_clean_state_safe_to_trade():
    trade = _trade()
    report = _manager().evaluate(
        trades=[trade],
        broker_positions={"AAA": {"quantity": 2}},
        broker_open_orders=[
            {
                "order_id": 102,
                "symbol": "AAA",
                "action": "SELL",
                "order_type": "STP",
                "quantity": 2,
                "status": "Submitted",
                "parent_id": 100,
            }
        ],
        lifecycle_events=[],
        idempotency_locks=[],
        protection_results=[],
        deployable_cash=50_000.0,
    )

    assert report.classification == RecoveryClassification.SAFE_TO_TRADE
    assert report.ready_to_trade is True
    assert report.recovery_required is False


def test_recovery_manager_blocks_local_open_trade_without_broker_position():
    trade = _trade()
    report = _manager().evaluate(
        trades=[trade],
        broker_positions={},
        broker_open_orders=[],
        lifecycle_events=[],
        idempotency_locks=[],
    )

    assert report.classification == RecoveryClassification.RECOVERY_REQUIRED
    assert report.recovery_required is True
    assert report.issues[0].code == "local_open_trade_missing_broker_position"


def test_recovery_manager_blocks_unmatched_active_broker_buy_order():
    report = _manager().evaluate(
        trades=[],
        broker_positions={},
        broker_open_orders=[
            {
                "order_id": 800,
                "symbol": "AAA",
                "action": "BUY",
                "order_type": "LMT",
                "quantity": 1,
                "status": "Submitted",
            }
        ],
        lifecycle_events=[],
        idempotency_locks=[],
    )

    assert report.classification == RecoveryClassification.RECOVERY_REQUIRED
    assert report.issues[0].code == "unmatched_broker_entry_order"


def test_recovery_manager_blocks_stale_idempotency_lock():
    lock = IdempotencyLock(
        key="autonomous-live:BUY:AAA",
        status="SUBMITTED",
        symbol="AAA",
        intended_action="BUY",
        updated_at=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
    )

    report = _manager().evaluate(
        trades=[],
        broker_positions={},
        broker_open_orders=[],
        lifecycle_events=[],
        idempotency_locks=[lock],
        now=datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc),
    )

    assert report.classification == RecoveryClassification.RECOVERY_REQUIRED
    assert report.stale_idempotency_locks == 1
    assert report.issues[0].code == "stale_idempotency_lock"


def test_live_runner_gates_include_recovery_report_and_block_mismatch(tmp_path):
    trade_store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    idempotency_store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))
    trade_store.record_trade(_trade())
    runner = _runner(
        tmp_path,
        trade_store=trade_store,
        lifecycle_store=lifecycle_store,
        idempotency_store=idempotency_store,
        broker_positions={},
        broker_open_orders=[],
    )

    gates = runner.evaluate_gates()

    assert gates.ready is False
    assert gates.recovery_required is True
    assert gates.recovery_classification == "RECOVERY_REQUIRED"
    assert gates.recovery_diagnostics["issues"]


def test_live_runner_gates_safe_when_broker_state_matches(tmp_path):
    trade_store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    idempotency_store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))
    trade_store.record_trade(_trade())
    runner = _runner(
        tmp_path,
        trade_store=trade_store,
        lifecycle_store=lifecycle_store,
        idempotency_store=idempotency_store,
        broker_positions={"AAA": {"quantity": 2}},
        broker_open_orders=[
            {
                "order_id": 102,
                "symbol": "AAA",
                "action": "SELL",
                "order_type": "STP",
                "quantity": 2,
                "remaining": 2,
                "status": "Submitted",
                "parent_id": 100,
            }
        ],
    )

    gates = runner.evaluate_gates()

    assert gates.ready is True
    assert gates.recovery_required is False
    assert gates.recovery_classification == "SAFE_TO_TRADE"


def test_supervisor_pauses_on_recovery_required_gate():
    supervisor = ContinuousSupervisor()

    class Gates:
        connected = True
        emergency_stop_active = False
        protection_recovery_required = 0
        protection_confirmed = True
        recovery_required = True
        recovery_classification = "RECOVERY_REQUIRED"
        recovery_diagnostics = {"issues": [{"code": "local_broker_quantity_mismatch"}]}

    result = supervisor.run_cycle(lambda: "nope", gates_provider=lambda: Gates())

    assert result.status == PAUSED
    assert result.reason == UNRECONCILED_LIFECYCLE_STATE
    assert result.fault.details["recovery_classification"] == "RECOVERY_REQUIRED"


def test_recovery_manager_flags_opposite_sign_broker_position():
    """Broker short position must not match a local long trade."""
    trade = _trade(quantity=2)
    report = _manager().evaluate(
        trades=[trade],
        broker_positions={"AAA": {"quantity": -2}},
        broker_open_orders=[],
        lifecycle_events=[],
        idempotency_locks=[],
    )

    assert report.classification == RecoveryClassification.RECOVERY_REQUIRED
    assert any(i.code == "local_broker_quantity_mismatch" for i in report.issues)
    mismatch = next(i for i in report.issues if i.code == "local_broker_quantity_mismatch")
    assert mismatch.details["broker_quantity"] == -2


def test_recovery_manager_flags_active_buy_order_with_terminal_lifecycle():
    """An active broker BUY order whose lifecycle is terminal must be flagged."""
    from autonomous.order_lifecycle import OrderLifecycleEvent, OrderLifecycleState

    lifecycle_event = OrderLifecycleEvent(
        lifecycle_id="entry-life",
        state=OrderLifecycleState.FILLED,
        symbol="AAA",
        broker_order_id=800,
    )
    report = _manager().evaluate(
        trades=[],
        broker_positions={},
        broker_open_orders=[
            {
                "order_id": 800,
                "symbol": "AAA",
                "action": "BUY",
                "order_type": "LMT",
                "quantity": 1,
                "status": "Submitted",
            }
        ],
        lifecycle_events=[lifecycle_event],
        idempotency_locks=[],
    )

    assert report.classification == RecoveryClassification.RECOVERY_REQUIRED
    assert any(i.code == "unmatched_broker_entry_order" for i in report.issues)


def test_live_runner_gates_block_safe_to_monitor_only(tmp_path):
    """SAFE_TO_MONITOR_ONLY must set recovery_required=True on the readiness gates."""
    from autonomous.order_lifecycle import OrderLifecycleEvent, OrderLifecycleState

    lifecycle_store = OrderLifecycleStore(path=str(tmp_path / "lifecycle.jsonl"))
    lifecycle_store.record_transition(
        lifecycle_id="entry-life",
        state=OrderLifecycleState.DUPLICATE_ORDER_BLOCKED,
        symbol="AAA",
        reason="duplicate detected",
    )
    trade_store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    idempotency_store = IdempotencyStore(path=str(tmp_path / "idempotency.jsonl"))
    runner = _runner(
        tmp_path,
        trade_store=trade_store,
        lifecycle_store=lifecycle_store,
        idempotency_store=idempotency_store,
        broker_positions={},
        broker_open_orders=[],
    )

    gates = runner.evaluate_gates()

    assert gates.recovery_required is True
    assert gates.recovery_classification == "SAFE_TO_MONITOR_ONLY"
    assert gates.ready is False
