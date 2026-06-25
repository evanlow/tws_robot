from datetime import datetime, timezone

from autonomous import AutonomousMode, AutonomousTradingConfig
from autonomous.autonomous_engine import (
    AutonomousDecision,
    AutonomousTradingEngine,
    DecisionStatus,
)
from autonomous.autonomous_live_runner import AutonomousLiveRunner, EXECUTED, NO_TRADE
from autonomous.live_basket_patch import _execute_one_live_plan
from autonomous.profitability_gate import ProfitabilityGate
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.market_data_provider import (
    IBKR_MARKET_DATA_TYPE_LIVE,
    IBKR_SOURCE,
    MarketDataProviderStatus,
    MarketDataQuote,
)
from autonomous.runner_config import AutonomousLiveRunnerConfig
from autonomous.trade_planner import TradeType
from autonomous.trade_store import TradeStore
from data.cash_availability import CashAvailabilityAnalyzer
from execution.order_executor import OrderResult, OrderStatus


class _LiveMarketDataProvider:
    """Healthy IBKR realtime market-data provider stub for the live readiness gate."""

    def __init__(self, *, connected: bool = True, healthy: bool = True) -> None:
        self.connected = connected
        self.healthy = healthy
        self.subscribed: list[str] = []

    def subscribe(self, symbols):
        self.subscribed.extend([str(s).upper() for s in symbols])

    def unsubscribe(self, symbols):
        pass

    def latest_quote(self, symbol):
        now = datetime.now(timezone.utc)
        return MarketDataQuote(
            symbol=str(symbol).upper(),
            bid=99.95,
            ask=100.05,
            last=100.0,
            timestamp=now,
            bid_timestamp=now,
            ask_timestamp=now,
            last_timestamp=now,
            source=IBKR_SOURCE,
            market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
            feed_healthy=True,
        )

    def status(self):
        return MarketDataProviderStatus(
            provider=IBKR_SOURCE,
            connected=self.connected,
            healthy=self.healthy,
            subscribed_symbols=list(self.subscribed),
            market_data_type=IBKR_MARKET_DATA_TYPE_LIVE,
            last_error=None,
            reason="test market-data provider",
        )


def _live_quote_extras() -> dict:
    """Healthy IBKR live-quote snapshot so the planner market-data guard allows
    assisted-live planning for each basket leg."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "bid": 99.95,
        "ask": 100.05,
        "quote_last": 100.0,
        "quote_timestamp": now,
        "bid_timestamp": now,
        "ask_timestamp": now,
        "last_timestamp": now,
        "market_data_source": IBKR_SOURCE,
        "market_data_type": IBKR_MARKET_DATA_TYPE_LIVE,
        "market_data_status": "healthy",
        "market_data_feed_healthy": True,
    }


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
        extras=_live_quote_extras(),
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
        market_data_provider=_LiveMarketDataProvider(),
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
        market_data_provider=_LiveMarketDataProvider(),
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


def test_live_runner_rejects_whole_basket_when_a_capped_leg_is_uneconomic(tmp_path):
    """Regression: the post-cap profitability re-check must reject the entire
    basket before *any* leg is submitted.

    Both legs are sized so the deployable-cash cap shrinks them to 10 shares.
    The first leg stays economical at that size while the second does not.  No
    executor calls must be made, so a partial basket can never be left in the
    market unsurfaced.
    """

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
    # Enable the commission-aware gate on the engine so the live runner's
    # post-cap re-check is active.
    engine.profitability_gate = ProfitabilityGate(
        enabled=True,
        estimated_commission_per_order=1.09,
        min_net_profit_usd=0.0,
        min_net_profit_pct_of_trade=0.0,
    )

    # Return a ready two-leg live plan.  Both legs price at 50 with a planned
    # quantity of 100 (value 5000); the deployable-cash cap below shrinks each
    # to 10 shares.  Leg AAA (target 51.00) nets +7.82; leg BBB (target 50.10)
    # nets -1.18 and must veto the whole basket.
    def _fake_run_once(confirm=False):
        plans = [
            {
                "symbol": "AAA",
                "trade_type": TradeType.BUY_SHARES.value,
                "limit_price": 50.0,
                "quantity": 100,
                "target_price": 51.0,
            },
            {
                "symbol": "BBB",
                "trade_type": TradeType.BUY_SHARES.value,
                "limit_price": 50.0,
                "quantity": 100,
                "target_price": 50.10,
            },
        ]
        return AutonomousDecision(
            status=DecisionStatus.LIVE_PLAN_READY,
            mode=AutonomousMode.ASSISTED_LIVE,
            trade_plan=plans[0],
            trade_plans=plans,
        )

    engine.run_once = _fake_run_once

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
            max_deployable_cash_pct=0.005,
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
        market_data_provider=_LiveMarketDataProvider(),
    )

    result = runner.run_once()

    assert result.status == NO_TRADE
    assert "uneconomic after commission" in result.rejection_reason
    # The vetoing leg must be the second one (BBB); the first leg stays economical.
    assert "BBB" in result.rejection_reason
    # Critically: no leg may have been submitted.
    assert executor.calls == []
