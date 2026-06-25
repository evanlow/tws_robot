"""Engine-level tests for the commission-aware profitability gate."""

from pathlib import Path

from autonomous import (
    AutonomousMode,
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    CandidateSignal,
    DecisionStatus,
    StaticSignalProvider,
)
from autonomous.audit import AuditLogger
from data.cash_availability import CashAvailabilityAnalyzer


def _make_engine(tmp_path: Path, *, signals, account, config):
    scanner = CandidateScanner(
        signal_provider=StaticSignalProvider(signals),
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": "X", "sub_industry": ""}
            for s in signals
        ],
    )
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: account,
        positions_provider=lambda: {},
        config=config,
        audit_logger=AuditLogger(log_dir=str(tmp_path)),
    )


def _config(tmp_path: Path, **kw):
    params = {
        "emergency_stop_file": str(tmp_path / "EMERGENCY_STOP"),
        "audit_log_dir": str(tmp_path),
        "risk_per_trade_sizing_enabled": False,
        "volatility_sizing_enabled": False,
        "drawdown_governor_enabled": False,
    }
    params.update(kw)
    return AutonomousTradingConfig(**params)


def _kr_signal():
    # 58.08 entry with a 58.73 resistance target reproduces the issue example.
    return CandidateSignal(
        symbol="KR",
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=58.08,
        support_price=56.0,
        resistance_price=58.73,
    )


def test_gate_rejects_uneconomic_two_share_trade(tmp_path):
    """A 2-share KR plan is rejected because round-trip commission exceeds the
    expected gross profit."""

    cfg = _config(
        tmp_path,
        commission_aware_sizing_enabled=True,
        estimated_commission_per_order=1.09,
        min_net_profit_usd=0.0,
    )
    engine = _make_engine(
        tmp_path,
        signals=[_kr_signal()],
        # Sized so the 10% deployable-cash cap affords exactly 2 shares.
        account={"cash_balance": 1500, "equity": 1500},
        config=cfg,
    )

    decision = engine.run_once()

    assert decision.trade_plan["quantity"] == 2
    assert decision.status is DecisionStatus.UNECONOMIC_AFTER_COMMISSION
    assert "below minimum" in decision.rejection_reason
    assert decision.profitability is not None
    assert decision.profitability["approved"] is False
    evals = decision.profitability["evaluations"]
    assert evals[0]["net_profit"] == round(-0.88, 4)
    assert evals[0]["min_quantity_for_profit"] == 4

    # Rejection must be recorded in the audit log.
    log_files = list(tmp_path.glob("autonomous_trading_*.jsonl"))
    assert log_files, "audit log must be written on rejection"
    content = log_files[0].read_text()
    assert "uneconomic_after_commission" in content


def test_gate_allows_economical_larger_trade(tmp_path):
    """The same price move is accepted when the position is large enough to
    clear commissions."""

    cfg = _config(
        tmp_path,
        commission_aware_sizing_enabled=True,
        estimated_commission_per_order=1.09,
        min_net_profit_usd=0.0,
    )
    engine = _make_engine(
        tmp_path,
        signals=[_kr_signal()],
        # Large account → 10% deployable-cash cap affords many shares.
        account={"cash_balance": 1_000_000, "equity": 1_000_000},
        config=cfg,
    )

    decision = engine.run_once()

    assert decision.trade_plan["quantity"] >= 4
    assert decision.status is DecisionStatus.RECOMMENDED
    assert decision.profitability["approved"] is True
    assert decision.profitability["evaluations"][0]["net_profit"] > 0


def test_gate_disabled_by_default_leaves_decision_untouched(tmp_path):
    """With the gate disabled (default) the uneconomic 2-share trade still
    flows through unchanged and no profitability payload is attached."""

    cfg = _config(tmp_path)  # commission_aware_sizing_enabled defaults False
    engine = _make_engine(
        tmp_path,
        signals=[_kr_signal()],
        account={"cash_balance": 1500, "equity": 1500},
        config=cfg,
    )

    decision = engine.run_once()

    assert decision.trade_plan["quantity"] == 2
    assert decision.status is DecisionStatus.RECOMMENDED
    assert decision.profitability is None


def test_gate_does_not_alter_existing_safety_gates(tmp_path):
    """Emergency stop still short-circuits before the profitability gate."""

    stop_file = tmp_path / "EMERGENCY_STOP"
    stop_file.write_text("halt")
    cfg = _config(
        tmp_path,
        emergency_stop_file=str(stop_file),
        commission_aware_sizing_enabled=True,
        estimated_commission_per_order=1.09,
    )
    engine = _make_engine(
        tmp_path,
        signals=[_kr_signal()],
        account={"cash_balance": 1500, "equity": 1500},
        config=cfg,
    )

    decision = engine.run_once()

    assert decision.status is DecisionStatus.EMERGENCY_STOP
    assert decision.profitability is None
