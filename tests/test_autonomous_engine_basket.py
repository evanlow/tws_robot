from datetime import datetime, timezone

from autonomous.autonomous_config import AutonomousMode, AutonomousTradingConfig
from autonomous.autonomous_engine import AutonomousTradingEngine, DecisionStatus
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.market_data_provider import (
    IBKR_MARKET_DATA_TYPE_LIVE,
    IBKR_SOURCE,
)
from data.cash_availability import CashAvailabilityAnalyzer


def _live_quote_extras(price: float = 100.0) -> dict:
    """Healthy IBKR live-quote snapshot so the market-data health guard allows
    assisted-live planning for each basket leg."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "bid": round(price - 0.05, 2),
        "ask": round(price + 0.05, 2),
        "quote_last": price,
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


class _PaperAdapter:
    def __init__(self):
        self.calls = []

    def buy(self, symbol, quantity, order_type, limit_price):
        self.calls.append({
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "limit_price": limit_price,
        })
        return 1000 + len(self.calls)


def _signal(symbol, sector, price=100.0, extras=None):
    return CandidateSignal(
        symbol=symbol,
        strength_score=100,
        signal_label="Confirmed Rebound",
        company_name=f"{symbol} Corp",
        sector=sector,
        last_price=price,
        support_price=95.0,
        resistance_price=110.0,
        volume_ok=True,
        trend_ok=True,
        extras=extras if extras is not None else {},
    )


def _engine(config, paper_adapter=None):
    signals = [
        _signal("AAA", "Tech", extras=_live_quote_extras()),
        _signal("BBB", "Health", extras=_live_quote_extras()),
        _signal("CCC", "Finance", extras=_live_quote_extras()),
    ]
    scanner = CandidateScanner(
        signal_provider=_Provider(signals),
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": s.sector, "sub_industry": ""}
            for s in signals
        ],
    )
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {
            "cash_balance": 100_000,
            "available_funds": 100_000,
            "buying_power": 100_000,
            "equity": 100_000,
        },
        positions_provider=lambda: {},
        orders_provider=lambda: [],
        config=config,
        paper_adapter=paper_adapter,
        spy_price_provider=lambda: {
            "open": 500.0,
            "current": 505.0,
            "vix_open": 16.0,
            "vix_current": 15.5,
        },
    )


def _basket_config(mode=AutonomousMode.RECOMMEND_ONLY, **kwargs):
    return AutonomousTradingConfig(
        mode=mode,
        basket_enabled=True,
        basket_max_size=3,
        basket_total_deployable_cash_pct=0.006,
        basket_single_position_deployable_cash_pct=0.002,
        basket_max_same_sector_positions=1,
        max_trades_per_day=5,
        require_user_confirmation=False,
        **kwargs,
    )


def test_engine_recommend_only_returns_basket_plan(tmp_path):
    cfg = _basket_config(audit_log_dir=str(tmp_path))
    engine = _engine(cfg)

    decision = engine.run_once()

    assert decision.status == DecisionStatus.RECOMMENDED
    assert len(decision.trade_plans) == 3
    assert decision.basket_plan is not None
    assert decision.trade_plan == decision.trade_plans[0]
    assert "basket mode" in " ".join(decision.notes)
    assert decision.basket_plan["risk_allocation"]["enabled"] is True
    assert decision.basket_plan["risk_allocation"]["total_planned_risk_dollars"] <= 200.0


def test_engine_evidence_record_includes_basket_risk_allocation(tmp_path):
    import json

    cfg = _basket_config(audit_log_dir=str(tmp_path))
    engine = _engine(cfg)

    decision = engine.run_once()

    assert decision.status == DecisionStatus.RECOMMENDED
    evidence_files = list(tmp_path.glob("autonomous_evidence_*.jsonl"))
    assert evidence_files
    record = json.loads(evidence_files[0].read_text(encoding="utf-8").strip())
    allocation = record["basket_plan"]["risk_allocation"]
    assert allocation["enabled"] is True
    assert allocation["allocation_mode"] == "equal_risk"
    assert allocation["total_planned_risk_dollars"] <= allocation["max_basket_risk_dollars"]
    assert record["basket_planned_risk"]


def test_engine_paper_executes_all_basket_legs(tmp_path):
    adapter = _PaperAdapter()
    cfg = _basket_config(mode=AutonomousMode.PAPER_EXECUTE, audit_log_dir=str(tmp_path))
    engine = _engine(cfg, paper_adapter=adapter)

    decision = engine.run_once(confirm=True)

    assert decision.status == DecisionStatus.PAPER_EXECUTED
    assert len(adapter.calls) == 3
    assert decision.order_ids == [1001, 1002, 1003]


def test_engine_assisted_live_returns_basket_live_plan_ready(tmp_path):
    cfg = _basket_config(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        market_data_health_guard_enabled=False,
        audit_log_dir=str(tmp_path),
    )
    engine = _engine(cfg)

    decision = engine.run_once(confirm=True)

    assert decision.status == DecisionStatus.LIVE_PLAN_READY
    assert len(decision.trade_plans) == 3
    assert decision.basket_plan is not None
