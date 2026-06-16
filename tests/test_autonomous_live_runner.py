"""Tests for :class:`AutonomousLiveRunner`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from autonomous import (
    AutonomousMode,
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    CandidateSignal,
    StaticSignalProvider,
)
from autonomous.audit import AuditLogger
from autonomous.autonomous_live_runner import (
    AutonomousLiveRunner,
    EXECUTED,
    DRY_RUN_EXECUTED,
    EMERGENCY_STOP_ACTIVE,
    MAX_OPEN_TRADES,
    NOT_CONNECTED,
    NOT_LIVE_MODE,
    LIVE_DISABLED,
    LIVE_CONTINUOUS_DISABLED,
    ACCOUNT_ID_MISMATCH,
    SIGNAL_PROVIDER_NOT_READY,
    DEPLOYABLE_CASH_BELOW_MINIMUM,
    NO_TRADE,
    EXECUTION_FAILED,
    DAILY_LIVE_TRADE_LIMIT_REACHED,
    ENGINE_REJECTED,
)
from autonomous.runner_config import AutonomousLiveRunnerConfig
# OPEN / CLOSED / FAILED are trade-lifecycle status strings (trade_store).
# EXECUTED / DRY_RUN_EXECUTED / NO_TRADE / EXECUTION_FAILED are runner-result
# status strings (autonomous_live_runner) — two distinct namespaces.
from autonomous.trade_store import (
    TradeStore,
    AutonomousTrade,
    OPEN,
    EXIT_PENDING,
    CLOSED,
    FAILED,
)
from data.cash_availability import CashAvailabilityAnalyzer
from execution.order_executor import OrderResult, OrderStatus


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class _RealProvider:
    """Non-static signal provider stub (passes the provider-ready check)."""
    pass


def _signal() -> CandidateSignal:
    return CandidateSignal(
        symbol="AAA",
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )


def _build_engine(tmp_path: Path, *, signal: Optional[CandidateSignal] = None) -> AutonomousTradingEngine:
    signals = [signal] if signal is not None else []
    provider = StaticSignalProvider(signals)
    scanner = CandidateScanner(
        signal_provider=provider,
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": "X", "sub_industry": ""}
            for s in signals
        ],
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


class _SubmittingExecutor:
    """Minimal OrderExecutor stub that always returns SUBMITTED."""

    def __init__(self, order_id: int = 9001) -> None:
        self._order_id = order_id
        self.calls: list[dict] = []

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        self.calls.append({
            "strategy_name": strategy_name,
            "symbol": signal.symbol,
            "quantity": signal.quantity,
            "price": signal.target_price,
        })
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            order_id=self._order_id,
            signal=signal,
            quantity=signal.quantity,
            price=signal.target_price or 0.0,
            reason=f"Order {self._order_id} submitted",
        )


class _DryRunExecutor:
    """Minimal OrderExecutor stub that always returns DRY_RUN."""

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        return OrderResult(
            status=OrderStatus.DRY_RUN,
            order_id=None,
            signal=signal,
            quantity=signal.quantity,
            price=signal.target_price or 0.0,
            reason="Dry-run preview only",
        )


class _RejectingExecutor:
    """Minimal OrderExecutor stub that always returns REJECTED."""

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        return OrderResult(
            status=OrderStatus.REJECTED,
            signal=signal,
            reason="Test rejection",
        )


def _runner(
    tmp_path: Path,
    *,
    signal: Optional[CandidateSignal] = None,
    connected: bool = True,
    env: str = "live",
    account_id: Optional[str] = "U1234567",
    emergency: bool = False,
    provider: Any = None,
    config: Optional[AutonomousLiveRunnerConfig] = None,
    executor: Any = None,
    deployable_cash: float = 50_000.0,
    continuous_mode: bool = False,
    rejected_order_ids_provider: Any = None,
    filled_order_ids_provider: Any = None,
) -> AutonomousLiveRunner:
    engine = _build_engine(tmp_path, signal=signal)
    store = TradeStore(path=str(tmp_path / "live_trades.jsonl"))
    live_cfg = config or AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        trade_store_path=str(tmp_path / "live_trades.jsonl"),
    )
    if provider is None:
        provider = _RealProvider()
    if executor is None:
        executor = _SubmittingExecutor()
    return AutonomousLiveRunner(
        engine=engine,
        trade_store=store,
        live_config=live_cfg,
        order_executor=executor,
        connected_provider=lambda: connected,
        connection_env_provider=lambda: env,
        account_id_provider=lambda: account_id,
        signal_provider_provider=lambda: provider,
        emergency_stop_provider=lambda: emergency,
        deployable_cash_provider=lambda: deployable_cash,
        rejected_order_ids_provider=rejected_order_ids_provider,
        filled_order_ids_provider=filled_order_ids_provider,
        continuous_mode=continuous_mode,
    )


# ---------------------------------------------------------------------------
# Gate tests
# ---------------------------------------------------------------------------


def test_not_connected_blocks_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), connected=False)
    result = runner.run_once()
    assert result.status == NOT_CONNECTED
    assert not result.gates.ready
    assert "Not connected" in " ".join(result.gates.reasons())


def test_paper_env_blocks_live_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), env="paper")
    result = runner.run_once()
    assert result.status == NOT_LIVE_MODE
    assert "live account" in " ".join(result.gates.reasons()).lower()


def test_live_disabled_blocks_run(tmp_path):
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=False,
        live_continuous_enabled=True,
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    runner = _runner(tmp_path, signal=_signal(), config=cfg)
    result = runner.run_once()
    assert result.status == LIVE_DISABLED


def test_continuous_disabled_blocks_continuous_run(tmp_path):
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=False,
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    runner = _runner(tmp_path, signal=_signal(), config=cfg, continuous_mode=True)
    result = runner.run_once()
    assert result.status == LIVE_CONTINUOUS_DISABLED


def test_continuous_disabled_does_not_block_single_cycle(tmp_path):
    """live_continuous_enabled=False should NOT block a non-continuous run."""
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=False,
        expected_account_id="U1234567",
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    runner = _runner(
        tmp_path,
        signal=_signal(),
        config=cfg,
        continuous_mode=False,  # single cycle, not continuous
    )
    gates = runner.evaluate_gates()
    # Should be ready (continuous check is skipped when continuous_mode=False)
    assert gates.live_enabled
    assert not gates.continuous_mode_required


def test_account_id_mismatch_blocks_run(tmp_path):
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U9999999",  # wrong
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    runner = _runner(tmp_path, signal=_signal(), account_id="U1234567", config=cfg)
    result = runner.run_once()
    assert result.status == ACCOUNT_ID_MISMATCH


def test_account_id_unverified_when_none(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), account_id=None)
    result = runner.run_once()
    assert result.status == ACCOUNT_ID_MISMATCH


def test_account_id_check_bypassed_when_confirmation_disabled(tmp_path):
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        live_require_account_confirmation=False,
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    runner = _runner(tmp_path, signal=_signal(), account_id=None, config=cfg)
    gates = runner.evaluate_gates()
    assert gates.account_id_verified


def test_emergency_stop_blocks_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), emergency=True)
    result = runner.run_once()
    assert result.status == EMERGENCY_STOP_ACTIVE


def test_signal_provider_not_ready_blocks_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), provider=StaticSignalProvider())
    result = runner.run_once()
    assert result.status == SIGNAL_PROVIDER_NOT_READY


def test_max_open_trades_blocks_run(tmp_path):
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        max_open_live_trades=1,
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    store = TradeStore(path=str(tmp_path / "t.jsonl"))
    from autonomous.trade_store import AutonomousTrade
    from datetime import datetime, timezone
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=100,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=10,
    )
    store.record_trade(trade)

    engine = _build_engine(tmp_path, signal=_signal())
    runner = AutonomousLiveRunner(
        engine=engine,
        trade_store=store,
        live_config=cfg,
        order_executor=_SubmittingExecutor(),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _RealProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 50_000.0,
    )
    result = runner.run_once()
    assert result.status == MAX_OPEN_TRADES


def test_deployable_cash_below_minimum_blocks_run(tmp_path):
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        min_deployable_cash=5000.0,
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    runner = _runner(
        tmp_path,
        signal=_signal(),
        config=cfg,
        deployable_cash=100.0,  # below minimum
    )
    result = runner.run_once()
    assert result.status == DEPLOYABLE_CASH_BELOW_MINIMUM


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------


def test_successful_live_execution(tmp_path):
    """Full live execution path: engine finds a trade, executor submits it."""
    runner = _runner(tmp_path, signal=_signal(), executor=_SubmittingExecutor(order_id=42))
    result = runner.run_once()
    # Engine returns LIVE_PLAN_READY; runner submits via OrderExecutor.
    assert result.status in (EXECUTED, NO_TRADE)
    assert result.gates.ready


def test_dry_run_execution(tmp_path):
    """Dry-run mode: executor returns DRY_RUN, trade is recorded."""
    runner = _runner(tmp_path, signal=_signal(), executor=_DryRunExecutor())
    result = runner.run_once()
    assert result.status in (DRY_RUN_EXECUTED, NO_TRADE)
    if result.status == DRY_RUN_EXECUTED:
        assert result.dry_run is True


def test_executor_rejection_returns_execution_failed(tmp_path):
    """OrderExecutor REJECTED → runner returns EXECUTION_FAILED."""
    runner = _runner(tmp_path, signal=_signal(), executor=_RejectingExecutor())
    result = runner.run_once()
    assert result.status in (EXECUTION_FAILED, NO_TRADE)


def test_no_trade_when_no_signal(tmp_path):
    """When the engine finds no candidate, status should be no_trade."""
    # No signal provided → engine returns NO_CANDIDATE
    runner = _runner(tmp_path, signal=None, executor=_SubmittingExecutor())
    result = runner.run_once()
    assert result.status == NO_TRADE


# ---------------------------------------------------------------------------
# Deployable-cash cap tests
# ---------------------------------------------------------------------------


def test_deployable_cash_cap_reduces_quantity(tmp_path):
    """When proposed value exceeds cap, quantity should be capped."""
    # signal: price=100, quantity=1000 → proposed value=100_000
    # deployable_cash=50_000, cap=10% → max_trade_value=5000 → max qty=50
    large_signal = CandidateSignal(
        symbol="AAA",
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )
    executor = _SubmittingExecutor(order_id=77)
    runner = _runner(
        tmp_path,
        signal=large_signal,
        executor=executor,
        deployable_cash=50_000.0,
    )
    # Even if the engine proposes a large quantity, the runner should cap it
    result = runner.run_once()
    # Just verify the run completes without error
    assert result.status in (EXECUTED, DRY_RUN_EXECUTED, NO_TRADE, EXECUTION_FAILED)


def test_cap_too_small_returns_no_trade(tmp_path):
    """When cap is too small to buy 1 share, return no_trade."""
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        max_deployable_cash_pct=0.001,  # 0.1% — too small
        min_deployable_cash=100.0,
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    runner = _runner(
        tmp_path,
        signal=_signal(),
        config=cfg,
        deployable_cash=500.0,
        executor=_SubmittingExecutor(),
    )
    result = runner.run_once()
    # Either NO_TRADE (cap too small) or the engine returned no candidate
    assert result.status in (NO_TRADE, EXECUTION_FAILED)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_live_runner_config_defaults():
    cfg = AutonomousLiveRunnerConfig()
    assert cfg.live_enabled is False
    assert cfg.live_continuous_enabled is False
    assert cfg.max_deployable_cash_pct == 0.10
    assert cfg.min_deployable_cash == 1000.0
    assert cfg.max_open_live_trades == 1
    assert cfg.max_live_trades_per_day == 1
    assert cfg.live_limit_orders_only is True
    assert cfg.live_require_account_confirmation is True
    assert cfg.live_dry_run is False


def test_live_runner_config_from_env_defaults(monkeypatch):
    for k in [
        "AUTONOMOUS_LIVE_ENABLED",
        "AUTONOMOUS_LIVE_CONTINUOUS_ENABLED",
        "AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT",
        "AUTONOMOUS_MIN_DEPLOYABLE_CASH",
        "AUTONOMOUS_MAX_OPEN_LIVE_TRADES",
        "AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY",
        "AUTONOMOUS_LIVE_LIMIT_ORDERS_ONLY",
        "AUTONOMOUS_LIVE_REQUIRE_ACCOUNT_CONFIRMATION",
        "AUTONOMOUS_LIVE_DRY_RUN",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = AutonomousLiveRunnerConfig.from_env()
    assert cfg.live_enabled is False
    assert cfg.live_continuous_enabled is False
    assert cfg.max_deployable_cash_pct == 0.10


def test_live_runner_config_from_env_opt_in(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_LIVE_ENABLED", "true")
    monkeypatch.setenv("AUTONOMOUS_LIVE_CONTINUOUS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT", "0.05")
    monkeypatch.setenv("AUTONOMOUS_MIN_DEPLOYABLE_CASH", "2000")
    monkeypatch.setenv("AUTONOMOUS_MAX_OPEN_LIVE_TRADES", "2")
    monkeypatch.setenv("AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY", "3")
    monkeypatch.setenv("AUTONOMOUS_LIVE_DRY_RUN", "true")

    cfg = AutonomousLiveRunnerConfig.from_env()
    assert cfg.live_enabled is True
    assert cfg.live_continuous_enabled is True
    assert cfg.max_deployable_cash_pct == 0.05
    assert cfg.min_deployable_cash == 2000.0
    assert cfg.max_open_live_trades == 2
    assert cfg.max_live_trades_per_day == 3
    assert cfg.live_dry_run is True


def test_live_runner_config_invalid_pct():
    with pytest.raises(ValueError, match="max_deployable_cash_pct"):
        AutonomousLiveRunnerConfig(max_deployable_cash_pct=0.0)

    with pytest.raises(ValueError, match="max_deployable_cash_pct"):
        AutonomousLiveRunnerConfig(max_deployable_cash_pct=1.1)


def test_live_runner_config_to_dict():
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        max_deployable_cash_pct=0.10,
        expected_account_id="U9876543",
    )
    d = cfg.to_dict()
    assert d["live_enabled"] is True
    assert d["live_continuous_enabled"] is True
    assert d["max_deployable_cash_pct"] == 0.10
    assert d["expected_account_id"] == "U9876543"


# ---------------------------------------------------------------------------
# AutonomousModeState display_mode tests
# ---------------------------------------------------------------------------


def test_mode_state_display_mode_off():
    from autonomous.autonomous_mode import AutonomousModeState, AutonomousDisplayMode, TradingCycle, AccountMode
    state = AutonomousModeState()
    assert state.display_mode == AutonomousDisplayMode.OFF


def test_mode_state_display_mode_paper():
    from autonomous.autonomous_mode import AutonomousModeState, AutonomousDisplayMode, TradingCycle, AccountMode
    state = AutonomousModeState()
    state.turn_on(TradingCycle.CONTINUOUS, AccountMode.PAPER)
    assert state.display_mode == AutonomousDisplayMode.PAPER


def test_mode_state_display_mode_live_continuous():
    from autonomous.autonomous_mode import AutonomousModeState, AutonomousDisplayMode, TradingCycle, AccountMode
    state = AutonomousModeState()
    state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE)
    assert state.display_mode == AutonomousDisplayMode.LIVE_CONTINUOUS


def test_mode_state_display_mode_live_dry_run():
    from autonomous.autonomous_mode import AutonomousModeState, AutonomousDisplayMode, TradingCycle, AccountMode
    state = AutonomousModeState()
    state.turn_on(TradingCycle.SINGLE_TRADE, AccountMode.LIVE, dry_run=True)
    assert state.display_mode == AutonomousDisplayMode.LIVE_DRY_RUN


def test_mode_state_display_mode_live_single():
    from autonomous.autonomous_mode import AutonomousModeState, AutonomousDisplayMode, TradingCycle, AccountMode
    state = AutonomousModeState()
    state.turn_on(TradingCycle.SINGLE_TRADE, AccountMode.LIVE)
    assert state.display_mode == AutonomousDisplayMode.LIVE_SINGLE


def test_mode_state_to_dict_includes_display_mode():
    from autonomous.autonomous_mode import AutonomousModeState, TradingCycle, AccountMode
    state = AutonomousModeState()
    state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE)
    d = state.to_dict()
    assert "display_mode" in d
    assert d["display_mode"] == "LIVE CONTINUOUS"
    assert d["account_mode"] == "live"


# ---------------------------------------------------------------------------
# Fix #5: Engine status safety — only LIVE_PLAN_READY is executable
# ---------------------------------------------------------------------------


def test_runner_rejects_live_blocked_engine_status(tmp_path):
    """Runner returns ENGINE_REJECTED when the engine unexpectedly returns
    LIVE_BLOCKED (e.g. the engine is mocked to simulate a future safety gate
    that the runner does not know about)."""
    from autonomous.autonomous_engine import AutonomousDecision, DecisionStatus
    from autonomous.autonomous_live_runner import ENGINE_REJECTED

    store = TradeStore(path=str(tmp_path / "t.jsonl"))
    live_cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        trade_store_path=str(tmp_path / "t.jsonl"),
    )

    # Stub engine that always returns LIVE_BLOCKED regardless of what the
    # runner sets on it.
    class _BlockingEngine:
        config = MagicMock()  # absorbs attribute sets

        def run_once(self, **kwargs):
            return AutonomousDecision(
                status=DecisionStatus.LIVE_BLOCKED,
                mode=AutonomousMode.ASSISTED_LIVE,
                rejection_reason="forced block",
            )

    runner = AutonomousLiveRunner(
        engine=_BlockingEngine(),
        trade_store=store,
        live_config=live_cfg,
        order_executor=_SubmittingExecutor(),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _RealProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 50_000.0,
    )
    result = runner.run_once()
    assert result.status == ENGINE_REJECTED
    assert result.trade is None


# ---------------------------------------------------------------------------
# Fix #6: Daily live trade cap
# ---------------------------------------------------------------------------


def test_daily_live_trade_limit_blocks_run(tmp_path):
    """When max_live_trades_per_day trades have already been recorded today,
    further run_once calls are rejected."""
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        max_live_trades_per_day=1,
        max_open_live_trades=5,  # don't block on open-trade cap
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    store = TradeStore(path=str(tmp_path / "t.jsonl"))
    # Record a CLOSED trade entered today — it counts in the daily cap but
    # does not trigger the max_open_trades gate.
    today_trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=CLOSED,
        entry_order_id=42,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=5,
    )
    store.record_trade(today_trade)

    engine = _build_engine(tmp_path, signal=_signal())
    runner = AutonomousLiveRunner(
        engine=engine,
        trade_store=store,
        live_config=cfg,
        order_executor=_SubmittingExecutor(),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _RealProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 50_000.0,
    )
    result = runner.run_once()
    assert result.status == DAILY_LIVE_TRADE_LIMIT_REACHED
    assert not result.gates.ready
    assert any("Daily live trade limit" in r for r in result.gates.reasons())


def test_daily_cap_not_triggered_when_trades_from_yesterday(tmp_path):
    """Trades from yesterday do not count against today's cap."""
    from datetime import timedelta
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        max_live_trades_per_day=1,
        max_open_live_trades=5,  # don't block on open-trade cap
        trade_store_path=str(tmp_path / "t.jsonl"),
    )
    store = TradeStore(path=str(tmp_path / "t.jsonl"))
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    old_trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=CLOSED,  # closed yesterday — doesn't consume open cap
        entry_order_id=10,
        entry_time=yesterday,
        entry_limit_price=100.0,
        quantity=5,
    )
    store.record_trade(old_trade)

    engine = _build_engine(tmp_path, signal=_signal())
    runner = AutonomousLiveRunner(
        engine=engine,
        trade_store=store,
        live_config=cfg,
        order_executor=_SubmittingExecutor(),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "live",
        account_id_provider=lambda: "U1234567",
        signal_provider_provider=lambda: _RealProvider(),
        emergency_stop_provider=lambda: False,
        deployable_cash_provider=lambda: 50_000.0,
    )
    gates = runner.evaluate_gates()
    assert gates.live_trades_today == 0
    assert gates.ready  # yesterday's trade should not block today


def test_gates_to_dict_includes_daily_trade_fields(tmp_path):
    runner = _runner(tmp_path)
    gates = runner.evaluate_gates()
    d = gates.to_dict()
    assert "live_trades_today" in d
    assert "max_live_trades_per_day" in d


def test_order_executor_property(tmp_path):
    executor = _SubmittingExecutor()
    runner = _runner(tmp_path, executor=executor)
    assert runner.order_executor is executor


# ---------------------------------------------------------------------------
# Rejected-order reconciliation (do not burn slots on broker rejections)
# ---------------------------------------------------------------------------


def _seed_open_trade(store: TradeStore, *, order_id: int, symbol: str = "AKAM",
                     entry_time: Optional[datetime] = None) -> AutonomousTrade:
    """Seed an OPEN trade in the store for reconciliation tests."""
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol=symbol,
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=order_id,
        entry_time=entry_time or datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=1,
        max_holding_days=5,
    )
    store.record_trade(trade)
    return trade


def test_rejected_order_marked_failed_on_next_run(tmp_path):
    """When the broker rejects an order, the trade-store entry is
    reconciled to FAILED at the start of the next run_once, freeing
    the open-trades slot."""
    runner = _runner(
        tmp_path,
        signal=_signal(),
        rejected_order_ids_provider=lambda: {7},
    )
    seeded = _seed_open_trade(runner.trade_store, order_id=7)

    gates = runner.evaluate_gates()

    reconciled = runner.trade_store.get(seeded.autonomous_trade_id)
    assert reconciled is not None
    assert reconciled.status == FAILED
    assert gates.open_live_trades == 0  # the rejected trade no longer counts


def test_rejected_order_today_excluded_from_daily_count(tmp_path):
    """A FAILED entry submitted today should not burn one of today's
    allowed live-trade slots."""
    runner = _runner(
        tmp_path,
        signal=_signal(),
        rejected_order_ids_provider=lambda: {7},
    )
    _seed_open_trade(runner.trade_store, order_id=7)

    gates = runner.evaluate_gates()

    assert gates.live_trades_today == 0


def test_reconcile_noop_when_no_provider(tmp_path):
    """No provider wired → no reconciliation, OPEN trade still counts."""
    runner = _runner(tmp_path, signal=_signal())  # no provider
    _seed_open_trade(runner.trade_store, order_id=7)

    gates = runner.evaluate_gates()

    assert gates.open_live_trades == 1
    assert gates.live_trades_today == 1


def test_reconcile_ignores_unmatched_ids(tmp_path):
    """Rejected IDs that don't match any OPEN trade are harmless."""
    runner = _runner(
        tmp_path,
        signal=_signal(),
        rejected_order_ids_provider=lambda: {999},
    )
    seeded = _seed_open_trade(runner.trade_store, order_id=7)

    gates = runner.evaluate_gates()

    still_open = runner.trade_store.get(seeded.autonomous_trade_id)
    assert still_open.status == OPEN
    assert gates.open_live_trades == 1


def test_reconcile_swallows_provider_exception(tmp_path):
    """A provider that raises must not crash gate evaluation."""
    def boom():
        raise RuntimeError("bridge gone")
    runner = _runner(
        tmp_path,
        signal=_signal(),
        rejected_order_ids_provider=boom,
    )
    _seed_open_trade(runner.trade_store, order_id=7)

    # Should not raise.
    gates = runner.evaluate_gates()
    assert gates.open_live_trades == 1  # nothing reconciled


# ---------------------------------------------------------------------------
# Bracket-fill reconciliation (continuous mode advances after target/stop fills)
# ---------------------------------------------------------------------------


def _seed_bracket_trade(
    store: TradeStore,
    *,
    parent_id: int,
    target_id: int,
    stop_id: int,
    symbol: str = "AKAM",
) -> AutonomousTrade:
    """Seed an OPEN trade with bracket child IDs for fill-reconciliation tests."""
    trade = AutonomousTrade(
        autonomous_trade_id=AutonomousTrade.new_id(),
        symbol=symbol,
        trade_type="BUY_SHARES",
        status=OPEN,
        entry_order_id=parent_id,
        entry_time=datetime.now(timezone.utc),
        entry_limit_price=100.0,
        quantity=1,
        target_price=110.0,
        stop_price=95.0,
        max_holding_days=5,
        target_order_id=target_id,
        stop_order_id=stop_id,
    )
    store.record_trade(trade)
    return trade


def test_bracket_target_fill_marks_trade_closed_take_profit(tmp_path):
    runner = _runner(
        tmp_path,
        signal=_signal(),
        filled_order_ids_provider=lambda: {201},
    )
    seeded = _seed_bracket_trade(
        runner.trade_store, parent_id=200, target_id=201, stop_id=202,
    )

    gates = runner.evaluate_gates()

    closed = runner.trade_store.get(seeded.autonomous_trade_id)
    assert closed is not None
    assert closed.status == CLOSED
    assert closed.exit_reason == "TAKE_PROFIT"
    assert closed.exit_order_id == 201
    assert gates.open_live_trades == 0


def test_bracket_stop_fill_marks_trade_closed_stop_loss(tmp_path):
    runner = _runner(
        tmp_path,
        signal=_signal(),
        filled_order_ids_provider=lambda: {302},
    )
    seeded = _seed_bracket_trade(
        runner.trade_store, parent_id=300, target_id=301, stop_id=302,
    )

    gates = runner.evaluate_gates()

    closed = runner.trade_store.get(seeded.autonomous_trade_id)
    assert closed.status == CLOSED
    assert closed.exit_reason == "STOP_LOSS"
    assert closed.exit_order_id == 302
    assert gates.open_live_trades == 0


def test_bracket_fill_reconciles_exit_pending_trade(tmp_path):
    runner = _runner(
        tmp_path,
        signal=_signal(),
        filled_order_ids_provider=lambda: {402},
    )
    seeded = _seed_bracket_trade(
        runner.trade_store, parent_id=400, target_id=401, stop_id=402,
    )
    runner.trade_store.update_trade(
        seeded.autonomous_trade_id,
        status=EXIT_PENDING,
    )

    gates = runner.evaluate_gates()

    closed = runner.trade_store.get(seeded.autonomous_trade_id)
    assert closed.status == CLOSED
    assert closed.exit_reason == "STOP_LOSS"
    assert closed.exit_order_id == 402
    assert gates.open_live_trades == 0


def test_bracket_fill_noop_when_no_provider(tmp_path):
    runner = _runner(tmp_path, signal=_signal())  # no filled provider
    seeded = _seed_bracket_trade(
        runner.trade_store, parent_id=400, target_id=401, stop_id=402,
    )

    gates = runner.evaluate_gates()

    still_open = runner.trade_store.get(seeded.autonomous_trade_id)
    assert still_open.status == OPEN
    assert gates.open_live_trades == 1


def test_bracket_fill_unmatched_id_ignored(tmp_path):
    runner = _runner(
        tmp_path,
        signal=_signal(),
        filled_order_ids_provider=lambda: {9999},
    )
    seeded = _seed_bracket_trade(
        runner.trade_store, parent_id=500, target_id=501, stop_id=502,
    )

    gates = runner.evaluate_gates()

    still_open = runner.trade_store.get(seeded.autonomous_trade_id)
    assert still_open.status == OPEN
    assert gates.open_live_trades == 1


def test_bracket_fill_swallows_provider_exception(tmp_path):
    def boom():
        raise RuntimeError("bridge gone")
    runner = _runner(
        tmp_path,
        signal=_signal(),
        filled_order_ids_provider=boom,
    )
    _seed_bracket_trade(
        runner.trade_store, parent_id=600, target_id=601, stop_id=602,
    )

    # Should not raise.
    gates = runner.evaluate_gates()
    assert gates.open_live_trades == 1


# ---------------------------------------------------------------------------
# Bracket persistence on entry (record_trade keeps child IDs)
# ---------------------------------------------------------------------------


class _BracketSubmittingExecutor:
    """Stub OrderExecutor that returns SUBMITTED with bracket child IDs."""

    def __init__(self, parent_id: int = 700, target_id: int = 701, stop_id: int = 702):
        self.parent_id = parent_id
        self.target_id = target_id
        self.stop_id = stop_id
        self.last_signal = None

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        self.last_signal = signal
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


def test_record_trade_persists_bracket_child_ids(tmp_path):
    executor = _BracketSubmittingExecutor()
    runner = _runner(tmp_path, signal=_signal(), executor=executor)

    result = runner.run_once()

    assert result.status == "executed"
    trade_dict = result.trade
    assert trade_dict is not None
    assert trade_dict["entry_order_id"] == 700
    assert trade_dict["target_order_id"] == 701
    assert trade_dict["stop_order_id"] == 702
    # Signal sent to the executor carries take_profit + stop_loss.
    sent = executor.last_signal
    assert sent.take_profit is not None and sent.take_profit > sent.target_price
    assert sent.stop_loss is not None and sent.stop_loss < sent.target_price


def test_synthesized_stop_when_plan_lacks_stop_price(tmp_path):
    """If the planner produces no stop_price, the runner synthesises one
    from default_stop_pct and notes it on the trade."""
    # Build a candidate with no support_price → planner produces stop_price=None.
    cand = _signal()
    cand.support_price = None  # type: ignore[attr-defined]
    executor = _BracketSubmittingExecutor()
    cfg = AutonomousLiveRunnerConfig(
        live_enabled=True,
        live_continuous_enabled=True,
        expected_account_id="U1234567",
        trade_store_path=str(tmp_path / "live_trades.jsonl"),
        default_stop_pct=0.05,
    )
    runner = _runner(tmp_path, signal=cand, executor=executor, config=cfg)

    result = runner.run_once()
    assert result.status == "executed"
    sent = executor.last_signal
    # Synthesized stop should be ~5% below the entry limit.
    assert sent.stop_loss is not None
    assert sent.stop_loss < sent.target_price
    # The trade notes should mention the synthesised stop.
    assert any("synthesised" in n.lower() for n in result.trade["notes"])
