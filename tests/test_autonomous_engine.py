"""Tests for autonomous.autonomous_engine.AutonomousTradingEngine."""

import json
from datetime import datetime, timezone
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
from autonomous.market_data_provider import (
    IBKR_MARKET_DATA_TYPE_LIVE,
    IBKR_SOURCE,
)
from data.cash_availability import CashAvailabilityAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _live_quote_extras() -> dict:
    """Healthy IBKR live-quote snapshot so the market-data health guard allows
    assisted-live planning.  Mirrors the production signal-provider payload."""
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
    spy_price_provider=None,
    cash_fx_rate_provider=None,
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
        spy_price_provider=spy_price_provider,
        cash_fx_rate_provider=cash_fx_rate_provider,
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


def test_sgd_base_cash_is_standardized_to_usd(tmp_path):
    cfg = AutonomousTradingConfig(
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal(last_price=50.0)],
        account={"cash_balance": 50_000, "equity": 100_000},
        config=cfg,
        cash_fx_rate_provider=lambda: 1.25,
    )
    engine.cash_analyzer.config.account_base_currency = "SGD"

    d = engine.run_once()

    assert d.deployable_cash == pytest.approx(36_000.0)
    assert d.cash_snapshot["cash_balance_currency"] == "SGD"
    assert d.cash_snapshot["cash_balance_usd"] == pytest.approx(40_000.0)
    assert d.cash_snapshot["manual_cash_buffer_usd"] == pytest.approx(4_000.0)


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


def test_spy_bearish_gate_blocks_before_scan(tmp_path):
    class _ExplodingProvider:
        def analyze(self, symbol):  # pragma: no cover - should not be called
            raise AssertionError("candidate scan must not run when SPY is bearish")

    scanner = CandidateScanner(
        signal_provider=_ExplodingProvider(),
        symbols=[{"symbol": "AAA", "security": "AAA", "sector": "X", "sub_industry": ""}],
    )
    cfg = AutonomousTradingConfig(
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {"cash_balance": 100_000, "equity": 100_000},
        positions_provider=lambda: {},
        config=cfg,
        spy_price_provider=lambda: {"open": 500.0, "current": 499.0},
        audit_logger=AuditLogger(log_dir=str(tmp_path)),
    )
    d = engine.run_once()
    assert d.status is DecisionStatus.MARKET_NOT_SUITABLE
    assert d.shortlist == []
    assert "market regime" in d.rejection_reason
    assert "SPY is not bullish intraday" in d.market_gate.get("reasons", [])
    assert d.market_gate["classification"] == "Bearish / Not Suitable"


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
    assert d.trade_plan["quantity"] > 0
    assert d.trade_plan["required_cash"] == pytest.approx(
        d.trade_plan["quantity"] * d.trade_plan["limit_price"]
    )
    assert d.trade_plan["required_cash"] <= (d.deployable_cash * 0.10) + 1e-9


def test_trade_sizing_uses_ten_percent_of_deployable_cash(tmp_path):
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA", last_price=100.0)],
        account={"cash_balance": 50_000, "equity": 1_000_000},
    )
    d = engine.run_once()
    assert d.status is DecisionStatus.RECOMMENDED
    # lower of 10% equity (100k) and 10% deployable cash after reserves.
    assert d.trade_plan["quantity"] == int((d.deployable_cash * 0.10) // 100.0)
    assert d.trade_plan["required_cash"] == d.trade_plan["quantity"] * 100.0


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
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA", extras=_live_quote_extras())],
        config=cfg,
    )
    d = engine.run_once(confirm=True)
    assert d.status is DecisionStatus.LIVE_BLOCKED


def test_live_execution_with_flag_but_no_confirm_requires_confirmation(tmp_path):
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(
        tmp_path,
        signals=[_make_signal("AAA", extras=_live_quote_extras())],
        config=cfg,
    )
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


def test_live_execution_returns_live_plan_ready_when_allow_live_true_and_confirmed(
    tmp_path,
):
    """ASSISTED_LIVE with allow_live_execution=True and confirm=True returns
    LIVE_PLAN_READY so the runner knows the plan is safe to execute via OrderExecutor."""
    cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        require_user_confirmation=True,
        max_trades_per_day=5,
        emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"),
        audit_log_dir=str(tmp_path),
    )
    engine = _make_engine(tmp_path, signals=[_make_signal("AAA", extras=_live_quote_extras())], config=cfg)
    d = engine.run_once(confirm=True)
    assert d.status is DecisionStatus.LIVE_PLAN_READY
    assert d.trade_plan is not None
    assert "live_plan_ready" in (d.notes[0] if d.notes else "")
