"""Tests for :class:`AutonomousPaperRunner`."""

from __future__ import annotations

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
from autonomous.autonomous_runner import (
    AutonomousPaperRunner,
    EXECUTED,
    EMERGENCY_STOP_ACTIVE,
    MAX_OPEN_TRADES,
    NO_TRADE,
    NOT_CONNECTED,
    NOT_PAPER_MODE,
    PAPER_ADAPTER_NOT_READY,
    RUNNER_DISABLED,
    SIGNAL_PROVIDER_NOT_READY,
)
from autonomous.runner_config import AutonomousRunnerConfig
from autonomous.trade_store import TradeStore
from data.cash_availability import CashAvailabilityAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _ReadyAdapter:
    def __init__(self):
        self.calls = []

    def is_ready(self):
        return True

    def buy(self, **kw):
        self.calls.append(kw)
        return 1234


class _NotReadyAdapter:
    def is_ready(self):
        return False

    def buy(self, **kw):  # pragma: no cover - never called
        raise RuntimeError("not ready")


def _build_engine(tmp_path, adapter, *, signal=None):
    signals = []
    if signal is not None:
        signals.append(signal)
    provider = StaticSignalProvider(signals)
    scanner = CandidateScanner(
        signal_provider=provider,
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": "X", "sub_industry": ""}
            for s in signals
        ],
    )
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.PAPER_EXECUTE,
        require_user_confirmation=True,  # runner supplies confirm=True itself
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
        paper_adapter=adapter,
        audit_logger=AuditLogger(log_dir=str(tmp_path)),
    )


def _signal():
    return CandidateSignal(
        symbol="AAA",
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )


def _runner(
    tmp_path,
    *,
    adapter=None,
    signal=None,
    connected=True,
    env="paper",
    emergency=False,
    provider=None,
    config=None,
    engine_adapter=None,
):
    adapter = adapter if adapter is not None else _ReadyAdapter()
    engine_adapter = engine_adapter if engine_adapter is not None else adapter
    engine = _build_engine(tmp_path, engine_adapter, signal=signal)
    store = TradeStore(path=str(tmp_path / "trades.jsonl"))
    cfg = config or AutonomousRunnerConfig(
        runner_enabled=True, trade_store_path=str(tmp_path / "trades.jsonl")
    )
    # default provider is a class that's not StaticSignalProvider
    if provider is None:
        class _RealProvider:
            pass
        provider = _RealProvider()
    return AutonomousPaperRunner(
        engine=engine,
        trade_store=store,
        runner_config=cfg,
        connected_provider=lambda: connected,
        connection_env_provider=lambda: env,
        paper_adapter_provider=lambda: adapter,
        signal_provider_provider=lambda: provider,
        emergency_stop_provider=lambda: emergency,
    )


# ---------------------------------------------------------------------------
# Gate tests
# ---------------------------------------------------------------------------


def test_not_connected_blocks_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), connected=False)
    result = runner.run_once()
    assert result.status == NOT_CONNECTED
    assert not result.gates.ready


def test_live_mode_blocks_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), env="live")
    result = runner.run_once()
    assert result.status == NOT_PAPER_MODE


def test_paper_but_no_adapter_blocks_run(tmp_path):
    adapter = _NotReadyAdapter()
    runner = _runner(tmp_path, signal=_signal(), adapter=adapter)
    result = runner.run_once()
    assert result.status == PAPER_ADAPTER_NOT_READY


def test_emergency_stop_blocks_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), emergency=True)
    result = runner.run_once()
    assert result.status == EMERGENCY_STOP_ACTIVE


def test_signal_provider_not_ready_blocks_run(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), provider=StaticSignalProvider())
    result = runner.run_once()
    assert result.status == SIGNAL_PROVIDER_NOT_READY


def test_runner_disabled_by_default(tmp_path):
    # default AutonomousRunnerConfig has runner_enabled=False
    runner = _runner(
        tmp_path,
        signal=_signal(),
        config=AutonomousRunnerConfig(
            trade_store_path=str(tmp_path / "trades.jsonl")
        ),
    )
    result = runner.run_once()
    assert result.status == RUNNER_DISABLED


def test_max_open_trades_blocks_new_entry(tmp_path):
    # Pre-record an open trade so the open-trade count is at the limit.
    cfg = AutonomousRunnerConfig(
        runner_enabled=True,
        max_open_autonomous_trades=1,
        trade_store_path=str(tmp_path / "trades.jsonl"),
    )
    runner = _runner(tmp_path, signal=_signal(), config=cfg)
    # Run once successfully so an open trade is recorded.
    first = runner.run_once()
    assert first.status == EXECUTED
    # Second run should be blocked.
    second = runner.run_once()
    assert second.status == MAX_OPEN_TRADES


# ---------------------------------------------------------------------------
# Successful run + persistence
# ---------------------------------------------------------------------------


def test_successful_run_records_trade(tmp_path):
    runner = _runner(tmp_path, signal=_signal())
    result = runner.run_once()
    assert result.status == EXECUTED
    assert result.trade is not None
    assert result.trade["symbol"] == "AAA"
    # Trade is persisted in the store.
    open_trades = runner.trade_store.list_open()
    assert len(open_trades) == 1
    assert open_trades[0].symbol == "AAA"
    assert open_trades[0].entry_order_id == 1234


def test_gates_payload_lists_failure_reasons(tmp_path):
    runner = _runner(tmp_path, signal=_signal(), connected=False, env=None)
    gates = runner.evaluate_gates()
    payload = gates.to_dict()
    assert payload["ready"] is False
    assert any("connected" in r.lower() or "paper" in r.lower() for r in payload["reasons"])


def test_uneconomic_after_commission_maps_to_no_trade(tmp_path):
    from autonomous.autonomous_engine import AutonomousDecision, DecisionStatus

    class _UneconomicEngine:
        config = AutonomousTradingConfig(mode=AutonomousMode.PAPER_EXECUTE)

        def run_once(self, **kwargs):
            return AutonomousDecision(
                status=DecisionStatus.UNECONOMIC_AFTER_COMMISSION,
                mode=AutonomousMode.PAPER_EXECUTE,
                rejection_reason="uneconomic after commission — below minimum net profit",
            )

    runner = AutonomousPaperRunner(
        engine=_UneconomicEngine(),
        trade_store=TradeStore(path=str(tmp_path / "t.jsonl")),
        runner_config=AutonomousRunnerConfig(
            runner_enabled=True,
            trade_store_path=str(tmp_path / "t.jsonl"),
        ),
        connected_provider=lambda: True,
        connection_env_provider=lambda: "paper",
        paper_adapter_provider=lambda: _ReadyAdapter(),
        signal_provider_provider=lambda: object(),
        emergency_stop_provider=lambda: False,
    )

    result = runner.run_once()
    assert result.status == NO_TRADE
    assert "uneconomic after commission" in (result.rejection_reason or "")
