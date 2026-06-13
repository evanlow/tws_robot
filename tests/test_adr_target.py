"""Tests for ADR-based dynamic intraday target pricing.

Covers:
- ADR calculation (calculate_adr)
- ADR target price derivation (compute_adr_target_price)
- Caps/floors enforcement
- Missing/invalid ADR data handling
- Resistance cap behaviour
- TradePlanner integration with adr_intraday mode
- Fallback to resistance/percent when ADR unavailable
- TechnicalAnalysisSignalProvider ADR computation during scanning
"""

import pytest

from autonomous.adr_calculator import ADRResult, calculate_adr, compute_adr_target_price
from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.trade_planner import TradePlanner, TradePlan


# ---------------------------------------------------------------------------
# ADR Calculator: calculate_adr
# ---------------------------------------------------------------------------


class TestCalculateADR:
    """Tests for calculate_adr()."""

    def test_basic_adr_calculation(self):
        """ADR is the average of (high - low) over recent bars."""
        bars = [
            {"high": 103.0, "low": 100.0},  # range = 3
            {"high": 105.0, "low": 101.0},  # range = 4
            {"high": 104.0, "low": 102.0},  # range = 2
            {"high": 106.0, "low": 101.0},  # range = 5
            {"high": 104.0, "low": 100.0},  # range = 4
        ]
        result = calculate_adr(bars, reference_price=102.0, lookback_days=14)
        assert result.valid is True
        assert result.adr == pytest.approx(3.6, abs=0.01)  # (3+4+2+5+4)/5
        assert result.adr_pct == pytest.approx(3.6 / 102.0, abs=0.0001)
        assert result.lookback_days_used == 5

    def test_uses_only_last_n_bars(self):
        """Only the last lookback_days bars are used."""
        bars = [
            {"high": 200.0, "low": 100.0},  # range = 100 (should be excluded)
            {"high": 103.0, "low": 100.0},  # range = 3
            {"high": 105.0, "low": 102.0},  # range = 3
            {"high": 104.0, "low": 101.0},  # range = 3
            {"high": 106.0, "low": 103.0},  # range = 3
            {"high": 104.0, "low": 101.0},  # range = 3
        ]
        result = calculate_adr(bars, reference_price=102.0, lookback_days=5)
        assert result.valid is True
        assert result.adr == pytest.approx(3.0, abs=0.01)
        assert result.lookback_days_used == 5

    def test_insufficient_bars_returns_invalid(self):
        """Returns invalid when fewer bars than min_bars_required."""
        bars = [
            {"high": 103.0, "low": 100.0},
            {"high": 105.0, "low": 101.0},
        ]
        result = calculate_adr(bars, reference_price=100.0, lookback_days=14, min_bars_required=5)
        assert result.valid is False
        assert result.adr == 0.0
        assert result.lookback_days_used == 2

    def test_empty_bars_returns_invalid(self):
        result = calculate_adr([], reference_price=100.0)
        assert result.valid is False

    def test_zero_reference_price_returns_invalid(self):
        bars = [{"high": 103.0, "low": 100.0}] * 10
        result = calculate_adr(bars, reference_price=0.0)
        assert result.valid is False

    def test_negative_reference_price_returns_invalid(self):
        bars = [{"high": 103.0, "low": 100.0}] * 10
        result = calculate_adr(bars, reference_price=-50.0)
        assert result.valid is False

    def test_skips_bars_with_invalid_data(self):
        """Bars with None, NaN, or invalid high/low are skipped."""
        bars = [
            {"high": 103.0, "low": 100.0},  # valid
            {"high": None, "low": 100.0},    # invalid
            {"high": 105.0, "low": None},    # invalid
            {"high": "abc", "low": 100.0},   # invalid
            {"high": 104.0, "low": 101.0},   # valid
            {"high": float("inf"), "low": 100.0},  # invalid
            {"high": 106.0, "low": 103.0},   # valid
            {"high": 104.0, "low": 101.0},   # valid
            {"high": 103.0, "low": 100.0},   # valid
        ]
        result = calculate_adr(bars, reference_price=102.0, lookback_days=14, min_bars_required=5)
        assert result.valid is True
        assert result.lookback_days_used == 5

    def test_skips_bars_where_high_less_than_low(self):
        bars = [
            {"high": 100.0, "low": 103.0},  # invalid: high < low
            {"high": 103.0, "low": 100.0},  # valid
            {"high": 105.0, "low": 102.0},  # valid
            {"high": 104.0, "low": 101.0},  # valid
            {"high": 106.0, "low": 103.0},  # valid
            {"high": 104.0, "low": 101.0},  # valid
        ]
        result = calculate_adr(bars, reference_price=102.0, lookback_days=14, min_bars_required=5)
        assert result.valid is True
        assert result.lookback_days_used == 5

    def test_to_dict(self):
        result = ADRResult(adr=3.5678, adr_pct=0.034567, lookback_days_used=14, valid=True)
        d = result.to_dict()
        assert d["adr"] == 3.5678
        assert d["adr_pct"] == 0.034567
        assert d["lookback_days_used"] == 14
        assert d["valid"] is True


# ---------------------------------------------------------------------------
# ADR Target Price: compute_adr_target_price
# ---------------------------------------------------------------------------


class TestComputeADRTargetPrice:
    """Tests for compute_adr_target_price()."""

    def test_basic_target_calculation(self):
        """Standard ADR target: entry + (adr * fraction), clamped."""
        # entry=100, adr=3.0, fraction=0.50 → move=1.50 → 1.5% → target=101.50
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=3.0,
            target_fraction=0.50,
            min_target_pct=0.005,
            max_target_pct=0.03,
        )
        assert target == 101.50

    def test_max_target_cap_applied(self):
        """Target is capped at max_target_pct."""
        # entry=100, adr=10.0, fraction=0.50 → move=5.0 → 5% > max 3%
        # capped at 3% → target=103.00
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=10.0,
            target_fraction=0.50,
            min_target_pct=0.005,
            max_target_pct=0.03,
        )
        assert target == 103.00

    def test_min_target_floor_applied(self):
        """Target is floored at min_target_pct."""
        # entry=100, adr=0.5, fraction=0.50 → move=0.25 → 0.25% < min 0.5%
        # floored at 0.5% → target=100.50
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=0.5,
            target_fraction=0.50,
            min_target_pct=0.005,
            max_target_pct=0.03,
        )
        assert target == 100.50

    def test_resistance_cap_applied(self):
        """Target is capped at resistance when respect_resistance_cap=True."""
        # entry=100, adr=4.0, fraction=0.50 → move=2.0 → 2% → target=102.00
        # But resistance at 101.50, so capped at 101.50
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=4.0,
            target_fraction=0.50,
            min_target_pct=0.005,
            max_target_pct=0.03,
            resistance_price=101.50,
            respect_resistance_cap=True,
        )
        assert target == 101.50

    def test_resistance_cap_ignored_when_disabled(self):
        """Target ignores resistance when respect_resistance_cap=False."""
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=4.0,
            target_fraction=0.50,
            min_target_pct=0.005,
            max_target_pct=0.03,
            resistance_price=101.50,
            respect_resistance_cap=False,
        )
        assert target == 102.00

    def test_resistance_below_entry_ignored(self):
        """Resistance below entry price is ignored (not useful as cap)."""
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=4.0,
            target_fraction=0.50,
            min_target_pct=0.005,
            max_target_pct=0.03,
            resistance_price=98.0,
            respect_resistance_cap=True,
        )
        assert target == 102.00

    def test_resistance_cap_never_below_entry(self):
        """Even with resistance cap, target never falls to or below entry."""
        # Resistance just barely above entry: target uses min floor
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=4.0,
            target_fraction=0.50,
            min_target_pct=0.005,
            max_target_pct=0.03,
            resistance_price=100.01,
            respect_resistance_cap=True,
        )
        # Resistance is 100.01 which is above entry, target capped there
        # But min_target_pct check: 100.01 > 100.0, so it passes
        assert target == 100.01

    def test_zero_entry_price_returns_none(self):
        result = compute_adr_target_price(entry_price=0.0, adr=3.0)
        assert result is None

    def test_zero_adr_returns_none(self):
        result = compute_adr_target_price(entry_price=100.0, adr=0.0)
        assert result is None

    def test_negative_fraction_returns_none(self):
        result = compute_adr_target_price(entry_price=100.0, adr=3.0, target_fraction=-0.5)
        assert result is None

    def test_zero_fraction_returns_none(self):
        result = compute_adr_target_price(entry_price=100.0, adr=3.0, target_fraction=0.0)
        assert result is None

    def test_target_always_above_entry(self):
        """Target price is always above entry price for valid inputs."""
        target = compute_adr_target_price(
            entry_price=100.0,
            adr=0.001,
            target_fraction=0.01,
            min_target_pct=0.005,
            max_target_pct=0.03,
        )
        assert target is not None
        assert target > 100.0


# ---------------------------------------------------------------------------
# TradePlanner integration: adr_intraday mode
# ---------------------------------------------------------------------------


def _make_candidate(
    symbol="AAPL",
    last_price=100.0,
    resistance_price=None,
    support_price=95.0,
    extras=None,
):
    return CandidateSignal(
        symbol=symbol,
        strength_score=100,
        signal_label="Confirmed Rebound",
        last_price=last_price,
        support_price=support_price,
        resistance_price=resistance_price,
        extras=extras or {},
    )


class TestTradePlannerADRMode:
    """TradePlanner with exit_target_mode=adr_intraday."""

    def test_adr_intraday_target_used_when_available(self):
        """When ADR data is in extras, adr_intraday mode uses it."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            adr_target_fraction=0.50,
            adr_min_target_pct=0.005,
            adr_max_target_pct=0.03,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(
            last_price=100.0,
            extras={"adr": 3.0, "adr_pct": 0.03, "adr_valid": True},
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 101.50
        assert plan.target_mode == "adr_intraday"
        assert plan.adr == 3.0
        assert plan.adr_pct == 0.03
        assert plan.adr_target_fraction == 0.50

    def test_adr_target_with_resistance_cap(self):
        """ADR target is capped at resistance when configured."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            adr_target_fraction=0.50,
            adr_min_target_pct=0.005,
            adr_max_target_pct=0.03,
            adr_respect_resistance_cap=True,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(
            last_price=100.0,
            resistance_price=101.00,
            extras={"adr": 4.0, "adr_pct": 0.04, "adr_valid": True},
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 101.00  # capped at resistance

    def test_adr_target_ignores_resistance_when_disabled(self):
        """ADR target ignores resistance when adr_respect_resistance_cap=False."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            adr_target_fraction=0.50,
            adr_min_target_pct=0.005,
            adr_max_target_pct=0.03,
            adr_respect_resistance_cap=False,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(
            last_price=100.0,
            resistance_price=101.00,
            extras={"adr": 4.0, "adr_pct": 0.04, "adr_valid": True},
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 102.00  # not capped

    def test_adr_fallback_to_resistance_when_adr_unavailable(self):
        """Falls back to resistance target when ADR data missing."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            take_profit_pct=0.08,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(
            last_price=100.0,
            resistance_price=110.0,
            extras={},  # no ADR data
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 110.0
        assert plan.target_mode == "resistance_fallback"

    def test_adr_fallback_to_percent_when_no_resistance(self):
        """Falls back to percent target when neither ADR nor resistance."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            take_profit_pct=0.05,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(
            last_price=100.0,
            resistance_price=None,
            extras={},  # no ADR
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 105.0
        assert plan.target_mode == "percent_fallback"

    def test_adr_fallback_when_adr_valid_false(self):
        """Falls back when adr_valid=False in extras."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            take_profit_pct=0.05,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(
            last_price=100.0,
            resistance_price=None,
            extras={"adr": 0.0, "adr_pct": 0.0, "adr_valid": False},
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 105.0
        assert plan.target_mode == "percent_fallback"

    def test_percent_mode(self):
        """exit_target_mode=percent uses take_profit_pct."""
        config = AutonomousTradingConfig(
            exit_target_mode="percent",
            take_profit_pct=0.04,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(last_price=100.0, resistance_price=110.0)
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 104.0
        assert plan.target_mode == "percent"

    def test_resistance_mode_default(self):
        """Default resistance mode uses candidate resistance_price."""
        config = AutonomousTradingConfig(exit_target_mode="resistance")
        planner = TradePlanner(config)
        candidate = _make_candidate(last_price=100.0, resistance_price=112.0)
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price == 112.0
        assert plan.target_mode == "resistance"

    def test_resistance_mode_no_resistance_returns_none_target(self):
        """Resistance mode with no resistance → target=None."""
        config = AutonomousTradingConfig(exit_target_mode="resistance")
        planner = TradePlanner(config)
        candidate = _make_candidate(last_price=100.0, resistance_price=None)
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price is None
        assert plan.target_mode == "resistance"

    def test_adr_metadata_in_trade_plan_to_dict(self):
        """ADR metadata appears in TradePlan.to_dict() output."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            adr_target_fraction=0.50,
        )
        planner = TradePlanner(config)
        candidate = _make_candidate(
            last_price=100.0,
            extras={"adr": 3.0, "adr_pct": 0.03, "adr_valid": True},
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        d = plan.to_dict()
        assert d["target_mode"] == "adr_intraday"
        assert d["adr"] == 3.0
        assert d["adr_pct"] == 0.03
        assert d["adr_target_fraction"] == 0.50
        assert d["target_price"] == 101.50

    def test_target_never_below_entry_for_buy(self):
        """Intraday target price is never <= entry price for BUY_SHARES."""
        config = AutonomousTradingConfig(
            exit_target_mode="adr_intraday",
            adr_target_fraction=0.50,
            adr_min_target_pct=0.005,
        )
        planner = TradePlanner(config)
        # Very small ADR - floor should apply
        candidate = _make_candidate(
            last_price=100.0,
            extras={"adr": 0.001, "adr_pct": 0.00001, "adr_valid": True},
        )
        plan = planner.plan(candidate, deployable_cash=50000, equity=100000)
        assert plan is not None
        assert plan.target_price > 100.0


# ---------------------------------------------------------------------------
# TechnicalAnalysisSignalProvider ADR computation
# ---------------------------------------------------------------------------


class TestSignalProviderADR:
    """TechnicalAnalysisSignalProvider computes ADR during scanning."""

    def test_adr_computed_when_lookback_days_set(self):
        """Provider computes ADR and stores in extras during analyze()."""
        daily_bars = [
            {"high": 103.0, "low": 100.0},
            {"high": 105.0, "low": 101.0},
            {"high": 104.0, "low": 102.0},
            {"high": 106.0, "low": 101.0},
            {"high": 104.0, "low": 100.0},
        ]

        def mock_fetcher(symbol, period="1y", interval="1d"):
            return daily_bars

        from autonomous.technical_analysis_signal_provider import (
            TechnicalAnalysisSignalProvider,
        )

        rows = [
            {
                "symbol": "AAPL",
                "current_price": 102.0,
                "momentum_label": "Confirmed Rebound",
                "quality_label": "Strong",
                "quality_score": 85,
            }
        ]
        provider = TechnicalAnalysisSignalProvider(
            rows_loader=lambda: rows,
            refresh_on_first_call=False,
            adr_lookback_days=14,
            price_history_fetcher=mock_fetcher,
        )
        signal = provider.analyze("AAPL")
        assert signal is not None
        assert signal.extras["adr_valid"] is True
        assert signal.extras["adr"] == pytest.approx(3.6, abs=0.01)
        assert signal.extras["adr_pct"] == pytest.approx(3.6 / 102.0, abs=0.001)
        assert signal.extras["adr_lookback_days_used"] == 5

    def test_adr_not_computed_when_lookback_zero(self):
        """Provider skips ADR when adr_lookback_days=0."""
        from autonomous.technical_analysis_signal_provider import (
            TechnicalAnalysisSignalProvider,
        )

        rows = [
            {
                "symbol": "AAPL",
                "current_price": 102.0,
                "momentum_label": "Confirmed Rebound",
                "quality_label": "Strong",
            }
        ]
        provider = TechnicalAnalysisSignalProvider(
            rows_loader=lambda: rows,
            refresh_on_first_call=False,
            adr_lookback_days=0,
        )
        signal = provider.analyze("AAPL")
        assert signal is not None
        assert "adr" not in signal.extras

    def test_adr_graceful_on_fetch_failure(self):
        """Provider continues without ADR when price fetch fails."""
        def failing_fetcher(symbol, period="1y", interval="1d"):
            raise ConnectionError("Network unavailable")

        from autonomous.technical_analysis_signal_provider import (
            TechnicalAnalysisSignalProvider,
        )

        rows = [
            {
                "symbol": "AAPL",
                "current_price": 102.0,
                "momentum_label": "Confirmed Rebound",
                "quality_label": "Strong",
            }
        ]
        provider = TechnicalAnalysisSignalProvider(
            rows_loader=lambda: rows,
            refresh_on_first_call=False,
            adr_lookback_days=14,
            price_history_fetcher=failing_fetcher,
        )
        signal = provider.analyze("AAPL")
        assert signal is not None
        # ADR not in extras because fetch failed
        assert "adr" not in signal.extras

    def test_adr_graceful_on_insufficient_bars(self):
        """Provider continues without ADR when too few bars returned."""
        def few_bars_fetcher(symbol, period="1y", interval="1d"):
            return [{"high": 103.0, "low": 100.0}]  # only 1 bar

        from autonomous.technical_analysis_signal_provider import (
            TechnicalAnalysisSignalProvider,
        )

        rows = [
            {
                "symbol": "AAPL",
                "current_price": 102.0,
                "momentum_label": "Confirmed Rebound",
                "quality_label": "Strong",
            }
        ]
        provider = TechnicalAnalysisSignalProvider(
            rows_loader=lambda: rows,
            refresh_on_first_call=False,
            adr_lookback_days=14,
            price_history_fetcher=few_bars_fetcher,
        )
        signal = provider.analyze("AAPL")
        assert signal is not None
        # ADR not populated because insufficient bars
        assert "adr" not in signal.extras
