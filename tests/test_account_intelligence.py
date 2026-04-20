"""Tests for the eight Account Intelligence modules and API endpoints.

Covers:
  1. AccountHealthAnalyzer
  2. CashManagementEngine
  3. OpportunityDetector
  4. PerformanceBenchmarker
  5. RiskIntelligenceEngine
  6. ReportGenerator
  7. MultiAccountManager
  8. ExecutionQualityAnalyzer
  9. API endpoint smoke tests
"""

import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ====================================================================
# 1. Account Health Analyzer
# ====================================================================

class TestAccountHealthAnalyzer:
    """Tests for data/account_health.py."""

    def _make_analyzer(self, **kw):
        from data.account_health import AccountHealthAnalyzer
        return AccountHealthAnalyzer(**kw)

    def test_healthy_account_scores_high(self):
        analyzer = self._make_analyzer()
        score = analyzer.compute_health_score(
            equity=200_000,
            cash_balance=40_000,
            margin_used=10_000,
            margin_available=90_000,
            peak_equity=200_000,
            positions=[
                {"market_value": 30_000},
                {"market_value": 25_000},
                {"market_value": 25_000},
                {"market_value": 40_000},
                {"market_value": 40_000},
            ],
        )
        assert score.overall_score >= 70
        assert score.grade.value in ("EXCELLENT", "GOOD")
        assert not score.warnings

    def test_critical_margin_scores_low(self):
        analyzer = self._make_analyzer()
        score = analyzer.compute_health_score(
            equity=100_000,
            cash_balance=2_000,
            margin_used=95_000,
            margin_available=5_000,
            peak_equity=150_000,
            positions=[{"market_value": 98_000}],
        )
        assert score.overall_score < 50
        assert any("margin" in w.lower() or "CRITICAL" in w for w in score.warnings)

    def test_no_positions_neutral_diversification(self):
        analyzer = self._make_analyzer()
        score = analyzer.compute_health_score(
            equity=100_000,
            cash_balance=100_000,
            margin_used=0,
            margin_available=100_000,
            peak_equity=100_000,
            positions=[],
        )
        assert score.components["diversification"] == 50.0

    def test_drawdown_warning(self):
        analyzer = self._make_analyzer(max_drawdown_pct=0.15)
        score = analyzer.compute_health_score(
            equity=80_000,
            cash_balance=20_000,
            margin_used=0,
            margin_available=80_000,
            peak_equity=100_000,
            positions=[{"market_value": 60_000}],
        )
        assert any("drawdown" in w.lower() for w in score.warnings)

    def test_to_dict_fields(self):
        analyzer = self._make_analyzer()
        score = analyzer.compute_health_score(
            equity=100_000, cash_balance=50_000, margin_used=0,
            margin_available=100_000, peak_equity=100_000,
            positions=[{"market_value": 50_000}],
        )
        d = score.to_dict()
        assert "overall_score" in d
        assert "grade" in d
        assert "components" in d
        assert "warnings" in d

    def test_cagr_positive(self):
        from data.account_health import AccountHealthAnalyzer
        cagr = AccountHealthAnalyzer.compute_cagr(100_000, 150_000, 365)
        assert abs(cagr - 0.5) < 0.01

    def test_cagr_zero_days(self):
        from data.account_health import AccountHealthAnalyzer
        assert AccountHealthAnalyzer.compute_cagr(100_000, 150_000, 0) == 0.0

    def test_margin_utilization_properties(self):
        from data.account_health import MarginUtilization
        m = MarginUtilization(margin_used=80_000, margin_available=20_000)
        assert abs(m.utilization_pct - 0.80) < 0.01
        assert m.is_warning
        assert not m.is_critical

    def test_buying_power_adequacy(self):
        from data.account_health import BuyingPowerAnalysis
        bp = BuyingPowerAnalysis(
            current_buying_power=50_000,
            required_buying_power=10_000,
        )
        assert bp.is_adequate
        assert bp.adequacy_ratio == 5.0

    def test_history_tracking(self):
        analyzer = self._make_analyzer()
        analyzer.compute_health_score(
            equity=100_000, cash_balance=50_000, margin_used=0,
            margin_available=100_000, peak_equity=100_000,
            positions=[],
        )
        assert len(analyzer.history) == 1
        assert analyzer.get_summary()["overall_score"] >= 0

    def test_grade_boundaries(self):
        from data.account_health import AccountHealthAnalyzer, HealthGrade
        assert AccountHealthAnalyzer._grade_from_score(90) == HealthGrade.EXCELLENT
        assert AccountHealthAnalyzer._grade_from_score(75) == HealthGrade.GOOD
        assert AccountHealthAnalyzer._grade_from_score(55) == HealthGrade.FAIR
        assert AccountHealthAnalyzer._grade_from_score(35) == HealthGrade.POOR
        assert AccountHealthAnalyzer._grade_from_score(10) == HealthGrade.CRITICAL


# ====================================================================
# 2. Cash Management Engine
# ====================================================================

class TestCashManagementEngine:
    """Tests for data/cash_management.py."""

    def _make_engine(self, **kw):
        from data.cash_management import CashManagementEngine
        return CashManagementEngine(**kw)

    def test_adequate_cash(self):
        engine = self._make_engine()
        result = engine.analyze(cash_balance=20_000, equity=100_000)
        assert result.is_adequate
        assert result.deficit == 0
        assert result.excess_cash > 0

    def test_deficit_detected(self):
        engine = self._make_engine()
        result = engine.analyze(cash_balance=2_000, equity=100_000)
        assert not result.is_adequate
        assert result.deficit > 0
        assert any("deficit" in r.lower() for r in result.recommendations)

    def test_idle_cash_detection(self):
        engine = self._make_engine()
        old_date = datetime.utcnow() - timedelta(days=30)
        result = engine.analyze(cash_balance=50_000, equity=100_000, last_trade_date=old_date)
        assert result.idle_days >= 30
        assert result.idle_cash > 0

    def test_reserve_policies(self):
        from data.cash_management import CashReserveConfig, ReservePolicy
        c = CashReserveConfig(policy=ReservePolicy.CONSERVATIVE)
        assert c.reserve_pct == 0.20
        a = CashReserveConfig(policy=ReservePolicy.AGGRESSIVE)
        assert a.reserve_pct == 0.05

    def test_expected_flow_scheduling(self):
        engine = self._make_engine()
        future = datetime.utcnow() + timedelta(days=5)
        engine.add_expected_flow(future, 1000, "Dividend AAPL", category="dividend")
        flows = engine.get_forecast(days=10)
        assert len(flows) == 1
        assert flows[0].amount == 1000

    def test_forecast_balance(self):
        engine = self._make_engine()
        future = datetime.utcnow() + timedelta(days=3)
        engine.add_expected_flow(future, 5000, "Deposit")
        projection = engine.forecast_balance(current_cash=10_000, days=7)
        # Should have 8 entries (day 0 through day 7)
        assert len(projection) == 8
        # Final balance should include the flow
        assert projection[-1][1] >= 15_000

    def test_to_dict_fields(self):
        engine = self._make_engine()
        result = engine.analyze(cash_balance=10_000, equity=100_000)
        d = result.to_dict()
        assert "cash_balance" in d
        assert "target_reserve" in d
        assert "recommendations" in d

    def test_large_cash_recommendation(self):
        engine = self._make_engine()
        result = engine.analyze(cash_balance=80_000, equity=100_000)
        assert any("opportunity cost" in r.lower() for r in result.recommendations)


# ====================================================================
# 3. Opportunity Detector
# ====================================================================

class TestOpportunityDetector:
    """Tests for data/opportunity_detector.py."""

    def _make_detector(self, **kw):
        from data.opportunity_detector import OpportunityDetector
        return OpportunityDetector(**kw)

    def test_overweight_position_detected(self):
        detector = self._make_detector(max_single_position_pct=0.20)
        positions = [
            {"symbol": "AAPL", "market_value": 50_000, "sector": "Technology"},
            {"symbol": "GOOG", "market_value": 10_000, "sector": "Technology"},
        ]
        suggestions = detector.generate_rebalance_suggestions(positions, equity=60_000)
        sell_aapl = [s for s in suggestions if s.symbol == "AAPL" and s.action == "SELL"]
        assert len(sell_aapl) >= 1

    def test_sector_gaps(self):
        detector = self._make_detector()
        positions = [
            {"symbol": "AAPL", "market_value": 100_000, "sector": "Technology"},
        ]
        gaps = detector.analyze_sector_gaps(positions, equity=100_000)
        tech = [g for g in gaps if g.sector == "Technology"]
        assert len(tech) == 1
        assert tech[0].is_overweight

    def test_dividend_screening(self):
        detector = self._make_detector(min_dividend_yield=0.03)
        candidates = [
            {"symbol": "T", "dividend_yield": 0.06, "payout_ratio": 0.70, "sector": "Communication"},
            {"symbol": "AAPL", "dividend_yield": 0.005, "payout_ratio": 0.15, "sector": "Technology"},
        ]
        opps = detector.screen_dividend_opportunities(candidates)
        assert len(opps) == 1
        assert opps[0].symbol == "T"

    def test_full_scan(self):
        detector = self._make_detector()
        positions = [
            {"symbol": "AAPL", "market_value": 40_000, "sector": "Technology"},
            {"symbol": "JPM", "market_value": 30_000, "sector": "Financials"},
        ]
        opps = detector.scan(positions=positions, equity=100_000)
        assert isinstance(opps, list)
        # Should detect sector gaps at minimum
        assert len(opps) > 0

    def test_empty_portfolio(self):
        detector = self._make_detector()
        opps = detector.scan(positions=[], equity=0)
        assert isinstance(opps, list)

    def test_sector_allocation_to_dict(self):
        from data.opportunity_detector import SectorAllocation
        sa = SectorAllocation(sector="Tech", target_pct=0.25, actual_pct=0.40)
        d = sa.to_dict()
        assert d["status"] == "overweight"

    # -- New tests for enhanced opportunity detection --

    def test_sector_gap_includes_etf_symbol(self):
        """Sector gap opportunities should include a concrete ETF symbol."""
        from data.opportunity_detector import OpportunityType
        detector = self._make_detector()
        positions = [
            {"symbol": "AAPL", "market_value": 100_000, "sector": "Technology"},
        ]
        opps = detector.scan(positions=positions, equity=100_000)
        sector_gaps = [o for o in opps if o.opportunity_type == OpportunityType.SECTOR_GAP]
        assert len(sector_gaps) > 0
        # At least one gap should have an ETF symbol
        with_etf = [o for o in sector_gaps if o.symbol]
        assert len(with_etf) > 0
        # Suggested action should mention a dollar amount or ETF
        for o in with_etf:
            assert "$" in o.suggested_action or o.symbol in o.suggested_action

    def test_sector_gap_includes_dollar_impact(self):
        """Sector gap opportunities should include potential_impact in dollars."""
        from data.opportunity_detector import OpportunityType
        detector = self._make_detector()
        positions = [
            {"symbol": "AAPL", "market_value": 100_000, "sector": "Technology"},
        ]
        opps = detector.scan(positions=positions, equity=100_000)
        sector_gaps = [o for o in opps if o.opportunity_type == OpportunityType.SECTOR_GAP]
        for o in sector_gaps:
            assert o.potential_impact >= 0

    def test_concentration_risk_detected(self):
        """Concentration risk should be detected when top N positions dominate."""
        from data.opportunity_detector import OpportunityType
        detector = self._make_detector(concentration_top_n=2, concentration_warn_pct=0.70)
        positions = [
            {"symbol": "AAPL", "market_value": 50_000, "sector": "Technology"},
            {"symbol": "GOOG", "market_value": 30_000, "sector": "Technology"},
            {"symbol": "JPM", "market_value": 10_000, "sector": "Financials"},
            {"symbol": "XOM", "market_value": 10_000, "sector": "Energy"},
        ]
        opps = detector.scan(positions=positions, equity=100_000)
        conc = [o for o in opps if o.opportunity_type == OpportunityType.CONCENTRATION]
        assert len(conc) == 1
        assert "AAPL" in conc[0].symbol
        assert "GOOG" in conc[0].symbol
        assert conc[0].metadata["top_pct"] >= 0.70

    def test_no_concentration_risk_when_well_diversified(self):
        """No concentration warning when portfolio is well-diversified."""
        from data.opportunity_detector import OpportunityType
        detector = self._make_detector(concentration_top_n=3, concentration_warn_pct=0.80)
        positions = [
            {"symbol": "AAPL", "market_value": 20_000, "sector": "Technology"},
            {"symbol": "GOOG", "market_value": 20_000, "sector": "Technology"},
            {"symbol": "JPM", "market_value": 20_000, "sector": "Financials"},
            {"symbol": "XOM", "market_value": 20_000, "sector": "Energy"},
            {"symbol": "JNJ", "market_value": 20_000, "sector": "Healthcare"},
        ]
        opps = detector.scan(positions=positions, equity=100_000)
        conc = [o for o in opps if o.opportunity_type == OpportunityType.CONCENTRATION]
        assert len(conc) == 0

    def test_rebalance_no_naive_equal_weight(self):
        """Rebalance should NOT produce naive equal-weight BUY suggestions."""
        detector = self._make_detector(max_single_position_pct=0.30)
        positions = [
            {"symbol": "AAPL", "market_value": 20_000, "sector": "Technology"},
            {"symbol": "GOOG", "market_value": 15_000, "sector": "Technology"},
            {"symbol": "JPM", "market_value": 10_000, "sector": "Financials"},
        ]
        suggestions = detector.generate_rebalance_suggestions(positions, equity=100_000)
        # None of these exceed 30%, so no rebalance suggestions
        assert len(suggestions) == 0

    def test_plain_summary_empty_portfolio(self):
        """Plain summary for empty portfolio should suggest starting with an ETF."""
        detector = self._make_detector()
        summary = detector.generate_plain_summary([], equity=0)
        assert "SPY" in summary or "VTI" in summary

    def test_plain_summary_concentrated_portfolio(self):
        """Plain summary should flag concentration."""
        detector = self._make_detector()
        positions = [
            {"symbol": "AAPL", "market_value": 90_000, "sector": "Technology"},
            {"symbol": "JPM", "market_value": 10_000, "sector": "Financials"},
        ]
        summary = detector.generate_plain_summary(positions, equity=100_000)
        assert "Technology" in summary
        assert "2 position" in summary

    def test_summary_includes_high_urgency_count(self):
        """Summary dict should include high_urgency_count."""
        from data.opportunity_detector import OpportunityType
        detector = self._make_detector()
        positions = [
            {"symbol": "AAPL", "market_value": 100_000, "sector": "Unknown"},
        ]
        detector.scan(positions=positions, equity=100_000)
        summary = detector.get_summary()
        assert "high_urgency_count" in summary
        assert isinstance(summary["high_urgency_count"], int)

    def test_overweight_sector_high_urgency(self):
        """Overweight sector >30pp should be HIGH urgency."""
        from data.opportunity_detector import OpportunityType, Urgency
        detector = self._make_detector()
        positions = [
            {"symbol": "AAPL", "market_value": 100_000, "sector": "Unknown"},
        ]
        opps = detector.scan(positions=positions, equity=100_000)
        overweight = [o for o in opps if o.opportunity_type == OpportunityType.OVERWEIGHT]
        # Unknown is 100% actual, 0% target → 100pp overweight
        assert len(overweight) > 0
        assert overweight[0].urgency == Urgency.HIGH

    def test_opportunity_to_dict_has_urgency_key(self):
        """Opportunity.to_dict() should have 'urgency' key, not 'priority'."""
        from data.opportunity_detector import Opportunity, OpportunityType, Urgency
        opp = Opportunity(
            opportunity_type=OpportunityType.SECTOR_GAP,
            symbol="XLK",
            description="Test",
            urgency=Urgency.HIGH,
        )
        d = opp.to_dict()
        assert "urgency" in d
        assert d["urgency"] == "HIGH"

    def test_dividend_screening_handles_none_yield(self):
        """Dividend screening should handle None dividend_yield gracefully."""
        detector = self._make_detector(min_dividend_yield=0.02)
        candidates = [
            {"symbol": "SLV", "dividend_yield": None, "sector": "Materials"},
            {"symbol": "T", "dividend_yield": 0.06, "payout_ratio": 0.70, "sector": "Communication"},
        ]
        opps = detector.screen_dividend_opportunities(candidates)
        assert len(opps) == 1
        assert opps[0].symbol == "T"

    def test_etf_symbol_for_known_sectors(self):
        """ETF mapping should return symbols for all default target sectors."""
        from data.opportunity_detector import SECTOR_ETF_MAP
        detector = self._make_detector()
        for sector in detector.DEFAULT_SECTOR_TARGETS:
            etf = detector._etf_symbol_for_sector(sector)
            assert etf, f"No ETF mapped for sector {sector}"
            assert etf in [e["symbol"] for e in SECTOR_ETF_MAP[sector]]


# ====================================================================
# 4. Performance Benchmarking
# ====================================================================

class TestPerformanceBenchmarker:
    """Tests for data/performance_benchmarking.py."""

    def _make_benchmarker(self, **kw):
        from data.performance_benchmarking import PerformanceBenchmarker
        return PerformanceBenchmarker(**kw)

    def _populate_history(self, b, days=30, start_val=100_000, daily_return=0.001):
        now = datetime.utcnow()
        val = start_val
        bench_val = 100.0
        for i in range(days):
            dt = now - timedelta(days=days - i)
            b.record_portfolio_value(dt, val)
            b.record_benchmark_value("SPY", dt, bench_val)
            val *= (1 + daily_return)
            bench_val *= (1 + daily_return * 0.8)

    def test_compare_with_history(self):
        b = self._make_benchmarker()
        self._populate_history(b)
        comp = b.compare_to_benchmark("SPY", period_days=30)
        assert comp.alpha >= 0  # portfolio beats benchmark (higher return)
        assert comp.benchmark == "SPY"

    def test_compare_no_history(self):
        b = self._make_benchmarker()
        comp = b.compare_to_benchmark("SPY", period_days=30)
        assert comp.portfolio_return_pct == 0.0

    def test_fee_drag(self):
        b = self._make_benchmarker()
        self._populate_history(b)
        b.record_trade_fee("AAPL", commission=5.0, fees=1.0, slippage=2.0)
        drag = b.compute_fee_drag(period_days=30)
        assert drag.total_commissions == 5.0
        assert drag.fee_drag_pct > 0

    def test_tax_lot_tracking(self):
        b = self._make_benchmarker()
        lot = b.add_tax_lot("AAPL", 100, 150.0, datetime.utcnow() - timedelta(days=400))
        assert lot.symbol == "AAPL"
        lots = b.get_tax_lots("AAPL")
        assert len(lots) == 1

    def test_wash_sale_alert(self):
        b = self._make_benchmarker()
        alert = b.check_wash_sale("AAPL", datetime.utcnow(), sale_price=140, cost_basis=150, quantity=100)
        assert alert is not None
        assert alert.loss_amount < 0

    def test_no_wash_sale_on_profit(self):
        b = self._make_benchmarker()
        alert = b.check_wash_sale("AAPL", datetime.utcnow(), sale_price=160, cost_basis=150, quantity=100)
        assert alert is None

    def test_unrealized_tax_summary(self):
        b = self._make_benchmarker()
        b.add_tax_lot("AAPL", 100, 150.0, datetime.utcnow() - timedelta(days=400))
        b.add_tax_lot("GOOG", 50, 100.0, datetime.utcnow() - timedelta(days=30))
        summary = b.get_unrealized_tax_summary({"AAPL": 170, "GOOG": 110})
        assert summary["total_unrealized"] > 0
        assert summary["total_lots"] == 2

    def test_benchmark_comparison_to_dict(self):
        from data.performance_benchmarking import BenchmarkComparison
        comp = BenchmarkComparison(
            benchmark="SPY", period_days=30,
            portfolio_return_pct=0.05, benchmark_return_pct=0.03,
        )
        d = comp.to_dict()
        assert d["alpha_pct"] == 0.02


# ====================================================================
# 5. Risk Intelligence Engine
# ====================================================================

class TestRiskIntelligenceEngine:
    """Tests for data/risk_intelligence.py."""

    def _make_engine(self, **kw):
        from data.risk_intelligence import RiskIntelligenceEngine
        return RiskIntelligenceEngine(**kw)

    def test_monte_carlo_with_returns(self):
        engine = self._make_engine(seed=42)
        returns = [0.001, -0.002, 0.003, 0.001, -0.001, 0.002, 0.0, -0.001, 0.002, 0.001]
        result = engine.run_monte_carlo(returns, horizon_days=10, simulations=500)
        assert result.simulations == 500
        assert result.horizon_days == 10
        assert result.var_95 >= 0  # VaR should be positive (represents a loss)
        assert result.probability_of_loss < 1.0

    def test_monte_carlo_empty_returns(self):
        engine = self._make_engine()
        result = engine.run_monte_carlo([], horizon_days=10, simulations=100)
        assert result.mean_return == 0.0
        assert result.var_95 == 0.0

    def test_stress_test_single_scenario(self):
        from data.risk_intelligence import StressScenario
        engine = self._make_engine()
        positions = [
            {"symbol": "AAPL", "market_value": 50_000, "beta": 1.2},
            {"symbol": "JNJ", "market_value": 30_000, "beta": 0.6},
        ]
        result = engine.run_stress_test(positions, StressScenario.MARKET_CRASH_2008)
        assert result.estimated_loss > 0
        assert result.portfolio_value_after < result.portfolio_value_before
        assert result.worst_position in ("AAPL", "JNJ")

    def test_stress_test_all_scenarios(self):
        engine = self._make_engine()
        positions = [{"symbol": "SPY", "market_value": 100_000, "beta": 1.0}]
        results = engine.run_all_stress_tests(positions)
        assert len(results) >= 4  # At least the non-CUSTOM scenarios

    def test_liquidity_analysis(self):
        engine = self._make_engine()
        positions = [
            {"symbol": "AAPL", "quantity": 100, "current_price": 150, "avg_daily_volume": 50_000_000},
            {"symbol": "TINY", "quantity": 10_000, "current_price": 5, "avg_daily_volume": 1_000},
        ]
        profiles = engine.analyze_liquidity(positions)
        assert len(profiles) == 2
        aapl = [p for p in profiles if p.symbol == "AAPL"][0]
        tiny = [p for p in profiles if p.symbol == "TINY"][0]
        assert aapl.liquidity_score > tiny.liquidity_score
        assert tiny.is_illiquid

    def test_monte_carlo_to_dict(self):
        engine = self._make_engine(seed=42)
        result = engine.run_monte_carlo([0.01, -0.01, 0.005], horizon_days=5, simulations=100)
        d = result.to_dict()
        assert "var_95_pct" in d
        assert "cvar_95_pct" in d

    def test_custom_stress_scenario(self):
        from data.risk_intelligence import StressScenario
        engine = self._make_engine()
        positions = [{"symbol": "SPY", "market_value": 100_000, "beta": 1.0}]
        result = engine.run_stress_test(positions, StressScenario.CUSTOM, custom_shock=-0.15)
        assert result.shock_pct == -0.15
        assert result.estimated_loss > 0


# ====================================================================
# 6. Report Generator
# ====================================================================

class TestReportGenerator:
    """Tests for monitoring/report_generator.py."""

    def _make_generator(self):
        from monitoring.report_generator import ReportGenerator
        return ReportGenerator()

    def test_add_default_rules(self):
        gen = self._make_generator()
        gen.add_default_rules()
        assert len(gen._rules) >= 4

    def test_evaluate_metrics_triggers_alert(self):
        from monitoring.report_generator import AlertRule, AlertSeverity
        gen = self._make_generator()
        gen.add_rule(AlertRule(
            name="test_dd",
            metric="drawdown_pct",
            threshold=0.10,
            comparison="gte",
            severity=AlertSeverity.WARNING,
        ))
        alerts = gen.evaluate_metrics({"drawdown_pct": 0.15})
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.WARNING

    def test_cooldown_prevents_spam(self):
        from monitoring.report_generator import AlertRule, AlertSeverity
        gen = self._make_generator()
        gen.add_rule(AlertRule(
            name="test_cd",
            metric="value",
            threshold=100,
            comparison="gt",
            severity=AlertSeverity.INFO,
            cooldown_minutes=60,
        ))
        a1 = gen.evaluate_metrics({"value": 150})
        a2 = gen.evaluate_metrics({"value": 200})
        assert len(a1) == 1
        assert len(a2) == 0  # cooldown active

    def test_generate_daily_report(self):
        from monitoring.report_generator import ReportPeriod
        gen = self._make_generator()
        gen.push_snapshot({
            "equity": 100_000,
            "daily_pnl": 500,
            "drawdown_pct": 0.02,
            "timestamp": datetime.utcnow().isoformat(),
        })
        report = gen.generate_report(period=ReportPeriod.DAILY)
        assert report.period == ReportPeriod.DAILY
        assert len(report.sections) >= 3

    def test_remove_rule(self):
        gen = self._make_generator()
        gen.add_default_rules()
        count_before = len(gen._rules)
        gen.remove_rule("high_drawdown")
        assert len(gen._rules) == count_before - 1

    def test_notification_callback(self):
        from monitoring.report_generator import AlertRule, AlertSeverity
        gen = self._make_generator()
        received = []
        gen.register_callback(lambda alert: received.append(alert))
        gen.add_rule(AlertRule(
            name="test_cb",
            metric="x",
            threshold=0,
            comparison="gt",
            severity=AlertSeverity.INFO,
        ))
        gen.evaluate_metrics({"x": 1})
        assert len(received) == 1

    def test_report_to_dict(self):
        gen = self._make_generator()
        report = gen.generate_report()
        d = report.to_dict()
        assert "period" in d
        assert "sections" in d

    def test_get_notifications(self):
        from monitoring.report_generator import AlertRule, AlertSeverity
        gen = self._make_generator()
        gen.add_rule(AlertRule(
            name="n", metric="v", threshold=0, comparison="gt",
            severity=AlertSeverity.INFO,
        ))
        gen.evaluate_metrics({"v": 1})
        notifs = gen.get_notifications()
        assert len(notifs) >= 1

    def test_alert_rule_message_template(self):
        from monitoring.report_generator import AlertRule, AlertSeverity
        gen = self._make_generator()
        gen.add_rule(AlertRule(
            name="tmpl", metric="dd", threshold=0.1, comparison="gte",
            severity=AlertSeverity.WARNING,
            message_template="DD at {value:.1%}",
        ))
        alerts = gen.evaluate_metrics({"dd": 0.15})
        assert "15.0%" in alerts[0].message


# ====================================================================
# 7. Multi-Account Manager
# ====================================================================

class TestMultiAccountManager:
    """Tests for data/multi_account.py."""

    def _make_manager(self, **kw):
        from data.multi_account import MultiAccountManager
        return MultiAccountManager(**kw)

    def _make_snapshot(self, acct_id, equity, **kw):
        from data.multi_account import AccountSnapshot
        return AccountSnapshot(account_id=acct_id, equity=equity, **kw)

    def test_add_and_list_accounts(self):
        mgr = self._make_manager()
        mgr.update_account(self._make_snapshot("A1", 100_000))
        mgr.update_account(self._make_snapshot("A2", 50_000))
        assert len(mgr.list_accounts()) == 2

    def test_aggregate_view(self):
        mgr = self._make_manager()
        mgr.update_account(self._make_snapshot("A1", 100_000, cash_balance=20_000))
        mgr.update_account(self._make_snapshot("A2", 50_000, cash_balance=10_000))
        agg = mgr.get_aggregate_view()
        assert agg.total_equity == 150_000
        assert agg.total_cash == 30_000
        assert agg.account_count == 2
        assert agg.largest_account == "A1"

    def test_cross_account_duplicate_detection(self):
        mgr = self._make_manager()
        mgr.update_account(self._make_snapshot(
            "A1", 100_000,
            positions=[{"symbol": "AAPL", "market_value": 50_000}],
        ))
        mgr.update_account(self._make_snapshot(
            "A2", 50_000,
            positions=[{"symbol": "AAPL", "market_value": 30_000}],
        ))
        risk = mgr.analyze_cross_account_risk()
        assert "AAPL" in risk.duplicate_symbols

    def test_concentration_warning(self):
        mgr = self._make_manager(concentration_limit=0.15)
        mgr.update_account(self._make_snapshot(
            "A1", 100_000,
            positions=[{"symbol": "TSLA", "market_value": 80_000}],
        ))
        risk = mgr.analyze_cross_account_risk()
        assert "TSLA" in risk.over_concentrated_symbols
        assert len(risk.warnings) > 0

    def test_remove_account(self):
        mgr = self._make_manager()
        mgr.update_account(self._make_snapshot("A1", 100_000))
        assert mgr.remove_account("A1")
        assert not mgr.remove_account("A1")
        assert len(mgr.list_accounts()) == 0

    def test_empty_aggregate(self):
        mgr = self._make_manager()
        agg = mgr.get_aggregate_view()
        assert agg.total_equity == 0
        assert agg.account_count == 0

    def test_account_history(self):
        mgr = self._make_manager()
        mgr.update_account(self._make_snapshot("A1", 100_000))
        mgr.update_account(self._make_snapshot("A1", 101_000))
        history = mgr.get_account_history("A1")
        assert len(history) == 2

    def test_aggregate_to_dict(self):
        mgr = self._make_manager()
        mgr.update_account(self._make_snapshot("A1", 100_000))
        d = mgr.get_aggregate_view().to_dict()
        assert "total_equity" in d
        assert "accounts" in d


# ====================================================================
# 8. Execution Quality Analyzer
# ====================================================================

class TestExecutionQualityAnalyzer:
    """Tests for execution/execution_quality.py."""

    def _make_analyzer(self):
        from execution.execution_quality import ExecutionQualityAnalyzer
        return ExecutionQualityAnalyzer()

    def test_record_fill(self):
        a = self._make_analyzer()
        rec = a.record_fill(
            order_id="O1", symbol="AAPL", side="BUY",
            quantity=100, limit_price=150, fill_price=150.05,
            vwap=150.02, market_price=150.0,
        )
        assert abs(rec.slippage - 0.05) < 1e-6  # adverse for BUY
        assert rec.slippage_bps > 0

    def test_sell_slippage(self):
        a = self._make_analyzer()
        rec = a.record_fill(
            order_id="O2", symbol="GOOG", side="SELL",
            quantity=50, limit_price=100, fill_price=99.95,
            market_price=100.0,
        )
        assert abs(rec.slippage - 0.05) < 1e-6  # adverse for SELL

    def test_fill_quality_excellent(self):
        a = self._make_analyzer()
        rec = a.record_fill(
            order_id="O3", symbol="SPY", side="BUY",
            quantity=200, limit_price=450, fill_price=449.90,
            vwap=450.0, market_price=450.0,
        )
        from execution.execution_quality import FillQuality
        assert rec.fill_quality == FillQuality.EXCELLENT

    def test_record_rejection(self):
        a = self._make_analyzer()
        rej = a.record_rejection("O4", "AAPL", "Insufficient buying power")
        assert rej.reason == "Insufficient buying power"

    def test_summary_with_fills_and_rejections(self):
        a = self._make_analyzer()
        a.record_fill("O1", "AAPL", "BUY", 100, 150, 150.02, market_price=150.0)
        a.record_fill("O2", "GOOG", "BUY", 50, 100, 100.01, market_price=100.0)
        a.record_rejection("O3", "TSLA", "Risk limit exceeded")
        summary = a.get_summary()
        assert summary.total_fills == 2
        assert summary.total_rejections == 1
        assert summary.fill_rate < 1.0
        assert "Risk limit exceeded" in summary.top_rejection_reasons

    def test_symbol_analysis(self):
        a = self._make_analyzer()
        a.record_fill("O1", "AAPL", "BUY", 100, 150, 150.02, market_price=150.0)
        a.record_fill("O2", "GOOG", "BUY", 50, 100, 100.01, market_price=100.0)
        summary = a.get_symbol_analysis("AAPL")
        assert summary.total_fills == 1

    def test_empty_summary(self):
        a = self._make_analyzer()
        summary = a.get_summary()
        assert summary.total_fills == 0
        assert summary.fill_rate == 1.0

    def test_execution_record_to_dict(self):
        a = self._make_analyzer()
        rec = a.record_fill("O1", "AAPL", "BUY", 100, 150, 150.05,
                            vwap=150.02, market_price=150.0, fill_time_ms=25.5)
        d = rec.to_dict()
        assert "slippage_bps" in d
        assert "fill_quality" in d
        assert d["fill_time_ms"] == 25.5

    def test_period_filter(self):
        a = self._make_analyzer()
        old = datetime.utcnow() - timedelta(days=60)
        a.record_fill("O1", "AAPL", "BUY", 100, 150, 150.02,
                       market_price=150.0, timestamp=old)
        a.record_fill("O2", "GOOG", "BUY", 50, 100, 100.01,
                       market_price=100.0)  # recent
        summary = a.get_summary(period_days=7)
        assert summary.total_fills == 1  # only the recent one

    def test_median_slippage(self):
        a = self._make_analyzer()
        for i in range(5):
            a.record_fill(f"O{i}", "SPY", "BUY", 100, 450, 450 + i * 0.01,
                          market_price=450.0)
        summary = a.get_summary()
        assert summary.median_slippage_bps > 0


# ====================================================================
# 9. API Endpoint Smoke Tests
# ====================================================================

class TestIntelligenceAPI:
    """Smoke tests for /api/intelligence/* endpoints."""

    @pytest.fixture()
    def client(self):
        from web import create_app
        app = create_app({"TESTING": True})
        with app.test_client() as c:
            yield c

    def test_health_endpoint(self, client):
        resp = client.get("/api/intelligence/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "overall_score" in data

    def test_cash_endpoint(self, client):
        resp = client.get("/api/intelligence/cash")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "cash_balance" in data

    def test_opportunities_endpoint(self, client):
        resp = client.get("/api/intelligence/opportunities")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "opportunities" in data

    def test_benchmark_endpoint(self, client):
        resp = client.get("/api/intelligence/benchmark")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "comparison" in data

    def test_risk_endpoint(self, client):
        resp = client.get("/api/intelligence/risk")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "monte_carlo" in data
        assert "stress_tests" in data

    def test_reports_endpoint(self, client):
        resp = client.get("/api/intelligence/reports")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "period" in data

    def test_alerts_endpoint(self, client):
        resp = client.get("/api/intelligence/alerts")
        assert resp.status_code == 200

    def test_multi_account_endpoint(self, client):
        resp = client.get("/api/intelligence/multi-account")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "aggregate" in data

    def test_execution_endpoint(self, client):
        resp = client.get("/api/intelligence/execution")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_fills" in data

    def test_summary_endpoint(self, client):
        resp = client.get("/api/intelligence/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "health" in data
        assert "modules_available" in data

    def test_cash_with_policy_param(self, client):
        resp = client.get("/api/intelligence/cash?policy=CONSERVATIVE")
        assert resp.status_code == 200

    def test_risk_endpoint_returns_liquidity(self, client):
        resp = client.get("/api/intelligence/risk")
        data = resp.get_json()
        assert "liquidity" in data

    def test_reports_weekly(self, client):
        resp = client.get("/api/intelligence/reports?period=WEEKLY")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["period"] == "WEEKLY"
