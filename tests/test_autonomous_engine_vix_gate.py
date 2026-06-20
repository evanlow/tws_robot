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
            last_price=100.0,
            volume_ok=True,
            trend_ok=True,
        )


def _engine(*, market_payload, config=None):
    scanner = CandidateScanner(
        signal_provider=_Provider(),
        symbols=[{"symbol": "AAA", "security": "AAA", "sector": "Tech", "sub_industry": ""}],
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
        config=config or AutonomousTradingConfig(mode=AutonomousMode.RECOMMEND_ONLY),
        spy_price_provider=lambda: market_payload,
    )


def test_engine_blocks_trade_when_vix_stress_even_if_spy_bullish(tmp_path):
    config = AutonomousTradingConfig(
        mode=AutonomousMode.RECOMMEND_ONLY,
        audit_log_dir=str(tmp_path),
    )
    engine = _engine(
        market_payload={
            "open": 500.0,
            "current": 505.0,
            "vix_open": 28.0,
            "vix_current": 31.0,
        },
        config=config,
    )

    decision = engine.run_once()

    assert decision.status == DecisionStatus.MARKET_NOT_SUITABLE
    assert decision.market_gate["bullish"] is True
    assert decision.market_gate["trade_allowed"] is False
    assert decision.market_gate["vix"]["level_regime"] == "block"


def test_engine_applies_vix_size_multiplier_to_deployable_cash(tmp_path):
    config = AutonomousTradingConfig(
        mode=AutonomousMode.RECOMMEND_ONLY,
        audit_log_dir=str(tmp_path),
        max_new_position_pct=0.10,
    )
    engine = _engine(
        market_payload={
            "open": 500.0,
            "current": 505.0,
            "vix_open": 17.0,
            "vix_current": 17.6,
        },
        config=config,
    )

    decision = engine.run_once()

    assert decision.status == DecisionStatus.RECOMMENDED
    assert decision.market_gate["trade_allowed"] is True
    assert decision.market_gate["size_multiplier"] == 0.5
    assert decision.deployable_cash == 4_500.0
    assert decision.trade_plan["quantity"] == 4
    assert decision.cash_snapshot["market_regime_adjustment"]["size_multiplier"] == 0.5


def test_engine_keeps_legacy_spy_only_provider_working(tmp_path):
    config = AutonomousTradingConfig(
        mode=AutonomousMode.RECOMMEND_ONLY,
        audit_log_dir=str(tmp_path),
    )
    engine = _engine(
        market_payload={"open": 500.0, "current": 505.0},
        config=config,
    )

    decision = engine.run_once()

    assert decision.status == DecisionStatus.RECOMMENDED
    assert decision.market_gate["vix"]["available"] is False
    assert decision.market_gate["trade_allowed"] is True


def test_engine_rejects_when_zero_size_multiplier_is_returned(tmp_path):
    """A gate with trade_allowed=True but size_multiplier=0.0 must not place a full-size trade.

    When a provider (e.g. a legacy or custom one) returns size_multiplier=0.0
    for a regime that nominally allows trading, the engine should apply the
    multiplier (0.0 * deployable_cash = 0), fail the min_deployable_cash check,
    and return NO_DEPLOYABLE_CASH instead of executing at full size.
    """
    config = AutonomousTradingConfig(
        mode=AutonomousMode.RECOMMEND_ONLY,
        audit_log_dir=str(tmp_path),
        apply_market_regime_size_multiplier=True,
    )
    engine = _engine(
        market_payload={"open": 500.0, "current": 505.0},
        config=config,
    )

    # Inject a gate that says trading is allowed but requests zero position size.
    engine._check_spy_gate = lambda: {
        "symbol": "SPY",
        "open": 500.0,
        "current": 505.0,
        "bullish": True,
        "trade_allowed": True,
        "size_multiplier": 0.0,
        "classification": "Bullish / Volatility Caution",
        "reasons": [],
        "warnings": ["zero size multiplier injected by test"],
        "vix": {"available": False, "guard_enabled": True},
    }

    decision = engine.run_once()

    assert decision.status == DecisionStatus.NO_DEPLOYABLE_CASH
