from autonomous import AutonomousMode, AutonomousTradingConfig
from autonomous.autonomous_engine import AutonomousTradingEngine
from autonomous.autonomous_live_runner import AutonomousLiveRunner, EXECUTED, NO_TRADE
from autonomous.live_basket_patch import _execute_one_live_plan
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.runner_config import AutonomousLiveRunnerConfig
from autonomous.trade_planner import TradeType
from autonomous.trade_store import TradeStore
from data.cash_availability import CashAvailabilityAnalyzer
from execution.order_executor import OrderResult, OrderStatus


class _Provider:
    def __init__(self, signals):
        self.signals = {s.symbol: s for s in signals}

    def analyze(self, symbol):
        return self.signals.get(symbol)


class _ReadyProvider:
    pass


class _Executor:
    def __init__(self):
        self.calls = []

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        self.calls.append(signal.symbol)
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            order_id=9000 + len(self.calls),
            signal=signal,
            quantity=signal.quantity,
            price=signal.target_price or 0.0,
        )


def _signal(symbol, sector):
    return CandidateSignal(
        symbol=symbol,
        strength_score=100,
        signal_label="Confirmed Rebound",
        sector=sector,
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )


def test_live_runner_executes_all_basket_legs_when_slots_allow(tmp_path):
    signals = [_signal("AAA", "Tech"), _signal("BBB", "Health")]
    scanner = CandidateScanner(
        signal_provider=_Provider(signals),
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": s.sector, "sub_industry": ""}
            for s in signals
        ],
    )
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        basket_enabled=True,
        basket_max_size=2,
        basket_total_deployable_cash_pct=0.004,
        basket_single_position_deployable_cash_pct=0.002,
        basket_max_same_sector_positions=1,
        max_trades_per_day=5,
        audit_log_dir=str(tmp_path),
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    engine = AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {"cash_balance": 100_000, "available_funds": 100_000, "equity": 100_000},
        positions_provider=lambda: {},
        orders_provider=lambda: [],
        config=cfg,
        spy_price_provider=lambda: {"open": 500, "current": 505},
    )
    executor = _Executor()
    store = TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    runner = AutonomousLiveRunner(
        engine=engine,
        trade_store=store,
        live_config=AutonomousLiveRunnerConfig(
            live_enabled=True,
            live_continuous_enabled=True,
            expected_account_id="U1234567",
            max_open_live_trades=5,
            max_live_trades_per_day=5,
            trade_store_path=str(tmp_path / "live_trades.jsonl"),
            idempotency_store_path=str(tmp_path / "idempotency.jsonl"),
        ),
        order_executor=executor,
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _ReadyProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 100_000.0,
        broker_positions_provider=lambda: {},
    )

    result = runner.run_once()

    assert result.status == EXECUTED
    assert executor.calls == ["AAA", "BBB"]
    assert result.trade["basket"] is True
    assert len(result.trade["submitted_trades"]) == 2


def test_live_runner_blocks_basket_when_slots_insufficient(tmp_path):
    signals = [_signal("AAA", "Tech"), _signal("BBB", "Health")]
    scanner = CandidateScanner(
        signal_provider=_Provider(signals),
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": s.sector, "sub_industry": ""}
            for s in signals
        ],
    )
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        basket_enabled=True,
        basket_max_size=2,
        basket_total_deployable_cash_pct=0.004,
        basket_single_position_deployable_cash_pct=0.002,
        max_trades_per_day=5,
        audit_log_dir=str(tmp_path),
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    engine = AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {"cash_balance": 100_000, "available_funds": 100_000, "equity": 100_000},
        positions_provider=lambda: {},
        orders_provider=lambda: [],
        config=cfg,
        spy_price_provider=lambda: {"open": 500, "current": 505},
    )
    runner = AutonomousLiveRunner(
        engine=engine,
        trade_store=TradeStore(path=str(tmp_path / "live_trades.jsonl")),
        live_config=AutonomousLiveRunnerConfig(
            live_enabled=True,
            live_continuous_enabled=True,
            expected_account_id="U1234567",
            max_open_live_trades=1,
            max_live_trades_per_day=1,
            trade_store_path=str(tmp_path / "live_trades.jsonl"),
            idempotency_store_path=str(tmp_path / "idempotency.jsonl"),
        ),
        order_executor=_Executor(),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _ReadyProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 100_000.0,
        broker_positions_provider=lambda: {},
    )

    result = runner.run_once()

    assert result.status == NO_TRADE
    assert "live trade slots" in result.rejection_reason


def test_execute_one_live_plan_returns_lifecycle_tuple_for_unsupported_trade_type():
    result, trade, error, lifecycle_events = _execute_one_live_plan(
        None,
        None,
        {"symbol": "AAA", "trade_type": TradeType.SELL_CASH_SECURED_PUT.value},
        1,
        None,
        0.0,
        0.0,
    )

    assert result is None
    assert trade is None
    assert "not BUY_SHARES" in error
    assert lifecycle_events == []
