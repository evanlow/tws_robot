import json

from autonomous import AutonomousMode, AutonomousTradingConfig
from autonomous.autonomous_engine import AutonomousTradingEngine, DecisionStatus
from autonomous.candidate_scanner import CandidateScanner, CandidateSignal
from autonomous.evidence_store import SCHEMA_VERSION
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
    assert record["schema_version"] == SCHEMA_VERSION
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
    assert record["candidate_counts"] == {"shortlist": 0, "rejected": 0, "basket_legs": 0}
    assert record["market_gate"]["classification"] == "Bearish / Not Suitable"


def _engine_with_config(tmp_path, **config_kwargs):
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
            **config_kwargs,
        ),
        spy_price_provider=lambda: {
            "open": 500.0,
            "current": 505.0,
            "vix_open": 16.0,
            "vix_current": 15.5,
        },
    )


def test_check_risk_lifecycle_skips_io_when_guard_disabled(tmp_path):
    """_check_risk_lifecycle must not read evidence files when guard is disabled."""
    engine = _engine_with_config(tmp_path, risk_lifecycle_guard_enabled=False)
    # evidence dir doesn't exist — any attempt to read files would fail or return
    # unexpected results; the guard disabled path must not touch it
    called = []
    _orig = engine.evidence.recent_outcomes
    engine.evidence.recent_outcomes = lambda *a, **kw: called.append(True) or []

    decision = engine.run_once()

    assert not called, "recent_outcomes should not be called when guard is disabled"
    assert decision.risk_lifecycle == {"allowed": True, "reason": "risk lifecycle guard disabled"}


def test_check_risk_lifecycle_uses_recent_outcomes_not_recent(tmp_path):
    """_check_risk_lifecycle must use recent_outcomes() so rejection records
    written to the evidence store do not evict outcome records from the window."""
    import json as _json
    from datetime import datetime, timedelta, timezone as _tz

    engine = _engine_with_config(tmp_path, risk_lifecycle_guard_enabled=True)

    # Inject many rejection (autonomous_decision) records so that a plain
    # recent() call would be saturated before returning any outcome records.
    when = datetime.now(_tz.utc)
    evidence_path = engine.evidence._path_for(when)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("w", encoding="utf-8") as fh:
        for i in range(20):
            fh.write(_json.dumps({
                "schema_version": 3,
                "evidence_type": "autonomous_decision",
                "timestamp": (when - timedelta(minutes=i)).isoformat(),
                "symbol": "ZZZ",
                "status": "risk_rejected",
            }) + "\n")
        # One valid outcome record at the end
        fh.write(_json.dumps({
            "schema_version": 3,
            "evidence_type": "autonomous_outcome",
            "timestamp": (when - timedelta(hours=1)).isoformat(),
            "symbol": "AAA",
            "outcome": {"realized": True, "realized_r_multiple": -1.0, "realized_pnl": -100.0},
        }) + "\n")

    outcomes = engine.evidence.recent_outcomes(limit=5)
    assert len(outcomes) == 1
    assert outcomes[0]["symbol"] == "AAA"
