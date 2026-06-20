import json

from autonomous import AutonomousMode, AutonomousTradingConfig
from autonomous.autonomous_engine import AutonomousTradingEngine, DecisionStatus
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from data.cash_availability import CashAvailabilityAnalyzer


class _Provider:
    def analyze(self, symbol):
        return CandidateSignal(
            symbol=symbol,
            strength_score=100,
            signal_label="Confirmed Rebound",
            company_name="AAA Corp",
            sector="Technology",
            last_price=100.0,
            support_price=96.0,
            resistance_price=108.0,
            volume_ok=True,
            trend_ok=True,
            extras={
                "quality_label": "Strong",
                "momentum_label": "Confirmed Rebound",
            },
        )


def _engine(tmp_path):
    scanner = CandidateScanner(
        signal_provider=_Provider(),
        symbols=[{"symbol": "AAA", "security": "AAA Corp", "sector": "Technology", "sub_industry": ""}],
    )
    return AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {
            "cash_balance": 10_000.0,
            "available_funds": 10_000.0,
            "buying_power": 10_000.0,
            "equity": 100_000.0,
        },
        positions_provider=lambda: {},
        orders_provider=lambda: [],
        config=AutonomousTradingConfig(
            mode=AutonomousMode.RECOMMEND_ONLY,
            audit_log_dir=str(tmp_path),
            max_new_position_pct=0.10,
        ),
        spy_price_provider=lambda: {
            "open": 500.0,
            "current": 505.0,
            "vix_open": 16.0,
            "vix_current": 15.5,
        },
    )


def test_engine_writes_evidence_record_for_recommended_trade(tmp_path):
    engine = _engine(tmp_path)

    decision = engine.run_once()

    assert decision.status == DecisionStatus.RECOMMENDED
    evidence_files = list(tmp_path.glob("autonomous_evidence_*.jsonl"))
    assert evidence_files
    record = json.loads(evidence_files[0].read_text(encoding="utf-8").strip())
    assert record["schema_version"] == 1
    assert record["status"] == "recommended"
    assert record["symbol"] == "AAA"
    assert record["strategy_bucket"]["quality_label"] == "Strong"
    assert record["market_gate"]["trade_allowed"] is True
    assert record["planned_risk"]["risk_per_share"] == 6.88
    assert record["candidate_counts"]["shortlist"] == 1
    assert record["outcome"]["realized"] is False


def test_engine_writes_evidence_record_for_no_trade(tmp_path):
    engine = _engine(tmp_path)
    engine._check_spy_gate = lambda: {
        "symbol": "SPY",
        "open": 500.0,
        "current": 495.0,
        "bullish": False,
        "trade_allowed": False,
        "size_multiplier": 0.0,
        "classification": "Bearish / Not Suitable",
        "reasons": ["SPY is not bullish intraday"],
        "vix": {"available": True, "level_regime": "normal"},
    }

    decision = engine.run_once()

    assert decision.status == DecisionStatus.MARKET_NOT_SUITABLE
    evidence_files = list(tmp_path.glob("autonomous_evidence_*.jsonl"))
    assert evidence_files
    record = json.loads(evidence_files[0].read_text(encoding="utf-8").strip())
    assert record["status"] == "market_not_suitable"
    assert record["symbol"] is None
    assert record["candidate_counts"] == {"shortlist": 0, "rejected": 0}
    assert record["market_gate"]["classification"] == "Bearish / Not Suitable"
