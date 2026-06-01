"""Tests for autonomous.autonomous_engine.AutonomousTradingEngine."""

import json
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_signal(symbol="AAA", strength=120, label="Confirmed Rebound", **kw):
    return CandidateSignal(
        symbol=symbol,
        strength_score=strength,
        signal_label=label,
        last_price=kw.pop("last_price", 100.0),
        support_price=kw.pop("support_price", 95.0),
        resistance_price=kw.pop("resistance_price", 110.0),
        **kw,
    )


def _make_engine(
    tmp_path: Path,
    *,
    signals=None,
    account=None,
    positions=None,
    config=None,
    paper_adapter=None,
    risk_manager=None,
    symbols=None,
):
    provider = StaticSignalProvider(signals or [])
    scanner = CandidateScanner(
        signal_provider=provider,
        symbols=symbols or [
            {"symbol": s.symbol, "security": s.symbol, "sector": "X", "sub_industry": ""}
            for s in (signals or [])
        ],
    )
    audit = AuditLogger(log_dir=str(tmp_path))
    cfg = config or AutonomousTradingConfig(
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: account or {"cash_balance": 100_000, "equity": 100_000},
        positions_provider=lambda: positions or {},
        config=cfg,
        risk_manager=risk_manager,
        paper_adapter=paper_adapter,
        audit_logger=audit,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_emergency_stop_blocks_execution(tmp_path):
    stop_file = tmp_path / "EMERGENCY_STOP"
    stop_file.write_text("halt")
    cfg = AutonomousTradingConfig(
        emergency_stop_file=str(stop_file),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(tmp_path, signals=[_make_signal()], config=cfg)
    d = engine.run_once()
    assert d.status is DecisionStatus.EMERGENCY_STOP
    # Audit log written even on emergency-stop rejection.
    log_files = list(tmp_path.glob("autonomous_trading_*.jsonl"))
    assert log_files, "audit log must be written on rejection"


def test_no_deployable_cash_returns_no_trade(tmp_path):
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal()],
        # No cash at all → CashAvailabilityAnalyzer reports 0 deployable.
        account={"cash_balance": 0, "equity": 0},
    )
    d = engine.run_once()
    assert d.status is DecisionStatus.NO_DEPLOYABLE_CASH


def test_no_matching_candidate_returns_no_candidate(tmp_path):
    engine = _make_engine(
        tmp_path,
        signals=[
            _make_signal("AAA", strength=50, label="Early Rebound"),
        ],
    )
    d = engine.run_once()
    assert d.status is DecisionStatus.NO_CANDIDATE
    assert d.deployable_cash > 0


def test_recommend_only_never_places_orders(tmp_path):
    placed = []

    class _Adapter:
        def buy(self, **kw):
            placed.append(kw)
            return 42

    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA"), _make_signal("BBB", strength=150)],
        paper_adapter=_Adapter(),
    )
    d = engine.run_once()
    assert d.status is DecisionStatus.RECOMMENDED
    assert placed == []
    # Best candidate is the highest-strength one.
    assert d.selected["candidate"]["symbol"] == "BBB"
    assert d.trade_plan["trade_type"] == "BUY_SHARES"


def test_paper_execute_places_order_with_confirm(tmp_path):
    placed = []

    class _Adapter:
        def buy(self, **kw):
            placed.append(kw)
            return 7

    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.PAPER_EXECUTE,
        require_user_confirmation=True,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA")],
        paper_adapter=_Adapter(),
        config=cfg,
    )
    # Without confirm: must not execute.
    d = engine.run_once(confirm=False)
    assert d.status is DecisionStatus.CONFIRMATION_REQUIRED
    assert placed == []
    # With confirm: must place via adapter.
    d = engine.run_once(confirm=True)
    assert d.status is DecisionStatus.PAPER_EXECUTED
    assert d.order_id == 7
    assert placed and placed[0]["symbol"] == "AAA"
    assert placed[0]["order_type"] == "LIMIT"
    assert placed[0]["limit_price"] == d.trade_plan["limit_price"]


def test_live_execution_blocked_unless_explicitly_enabled(tmp_path):
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=False,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(tmp_path, signals=[_make_signal("AAA")], config=cfg)
    d = engine.run_once(confirm=True)
    assert d.status is DecisionStatus.LIVE_BLOCKED


def test_live_execution_with_flag_but_no_confirm_requires_confirmation(tmp_path):
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(tmp_path, signals=[_make_signal("AAA")], config=cfg)
    d = engine.run_once(confirm=False)
    assert d.status is DecisionStatus.CONFIRMATION_REQUIRED


def test_existing_short_put_reduces_deployable_cash(tmp_path):
    # A short put on UNDR strike 50 ⇒ ~$5k reserve.  With only $6k cash we
    # should end up well below the default 10k floor → no trade.
    positions = {
        "UNDR  261218P00050000": {
            "quantity": -1,
            "sec_type": "OPT",
            "side": "SHORT",
            "market_value": 0,
            "entry_price": 1.0,
            "current_price": 1.0,
        }
    }
    cfg = AutonomousTradingConfig(
        min_deployable_cash=10_000,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA")],
        account={"cash_balance": 6_000, "equity": 6_000},
        positions=positions,
        config=cfg,
    )
    d = engine.run_once()
    assert d.status is DecisionStatus.NO_DEPLOYABLE_CASH
    assert d.cash_snapshot["reserved_cash_short_puts"] >= 5_000


def test_audit_log_records_every_decision(tmp_path):
    engine = _make_engine(tmp_path, signals=[_make_signal("AAA")])
    engine.run_once()
    log_file = next(tmp_path.glob("autonomous_trading_*.jsonl"))
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["decision"]["status"] == "recommended"
    assert parsed["config"]["mode"] == "recommend_only"
    assert "deployable_cash" in parsed["decision"]


def test_risk_manager_rejection_blocks_recommendation(tmp_path):
    class _RM:
        emergency_stop_active = False

        def check_trade_risk(self, **kw):
            return False, "max position exceeded"

    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.PAPER_EXECUTE,
        require_user_confirmation=False,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    placed = []

    class _Adapter:
        def buy(self, **kw):
            placed.append(kw)
            return 1

    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA")],
        config=cfg,
        risk_manager=_RM(),
        paper_adapter=_Adapter(),
    )
    d = engine.run_once(confirm=True)
    assert d.status is DecisionStatus.RISK_REJECTED
    assert placed == []


def test_max_trades_per_day_blocks_second_execution(tmp_path):
    placed = []

    class _Adapter:
        def buy(self, **kw):
            placed.append(kw)
            return len(placed)

    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.PAPER_EXECUTE,
        require_user_confirmation=False,
        max_trades_per_day=1,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA")],
        paper_adapter=_Adapter(),
        config=cfg,
    )

    first = engine.run_once(confirm=True)
    assert first.status is DecisionStatus.PAPER_EXECUTED
    assert len(placed) == 1

    second = engine.run_once(confirm=True)
    assert second.status is DecisionStatus.DAILY_LIMIT_REACHED
    assert len(placed) == 1  # adapter NOT called a second time


def test_live_execution_remains_blocked_even_when_allow_live_true_and_confirmed(
    tmp_path,
):
    """MVP live path is a deliberate blocked stub even when fully enabled."""
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        require_user_confirmation=True,
        max_trades_per_day=5,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(tmp_path, signals=[_make_signal("AAA")], config=cfg)
    d = engine.run_once(confirm=True)
    assert d.status is DecisionStatus.LIVE_BLOCKED
    assert "not implemented" in (d.rejection_reason or "")
