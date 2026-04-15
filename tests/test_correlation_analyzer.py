"""
Validation Tests for Correlation Analysis & Portfolio Concentration

Tests all correlation and concentration features including:
- HHI calculation and concentration metrics
- Correlation matrix calculation
- Sector/industry exposure tracking
- Diversification scoring
- High correlation pair detection
- New position impact analysis

Author: Trading Bot Development Team
Date: November 21, 2025
"""

from datetime import datetime
from risk.correlation_analyzer import (
    CorrelationAnalyzer,
    PositionInfo,
)
import numpy as np


def test_concentration_metrics():
    """Test HHI and concentration calculations"""
    print("\n" + "=" * 70)
    print("TEST 1: Concentration Metrics")
    print("=" * 70)
    
    analyzer = CorrelationAnalyzer()
    
    # Test 1: Equal weights (well diversified)
    positions = [
        PositionInfo("AAPL", 100, 10000, 0.10),
        PositionInfo("MSFT", 100, 10000, 0.10),
        PositionInfo("GOOGL", 100, 10000, 0.10),
        PositionInfo("AMZN", 100, 10000, 0.10),
        PositionInfo("TSLA", 100, 10000, 0.10),
        PositionInfo("META", 100, 10000, 0.10),
        PositionInfo("NVDA", 100, 10000, 0.10),
        PositionInfo("AMD", 100, 10000, 0.10),
        PositionInfo("NFLX", 100, 10000, 0.10),
        PositionInfo("INTC", 100, 10000, 0.10),
    ]
    
    metrics1 = analyzer.analyze(positions)
    
    print(f"\n✓ Equal Weights Test (10 positions @ 10% each):")
    print(f"  HHI: {metrics1.herfindahl_index:.3f}")
    print(f"  Top 1: {metrics1.top_position_pct:.1%}")
    print(f"  Top 3: {metrics1.top_3_positions_pct:.1%}")
    print(f"  Top 5: {metrics1.top_5_positions_pct:.1%}")
    print(f"  Effective Positions: {metrics1.effective_positions:.1f}")
    print(f"  Diversification Score: {metrics1.diversification_score:.0f}/100")
    print(f"  Is Concentrated: {metrics1.is_concentrated}")
    
    assert abs(metrics1.herfindahl_index - 0.10) < 0.01  # 1/10 = 0.10
    assert abs(metrics1.top_position_pct - 0.10) < 0.01
    assert abs(metrics1.top_3_positions_pct - 0.30) < 0.01
    assert abs(metrics1.effective_positions - 10.0) < 0.5
    assert metrics1.is_concentrated == False
    assert metrics1.diversification_score >= 80
    
    # Test 2: Concentrated portfolio
    positions2 = [
        PositionInfo("AAPL", 500, 50000, 0.50),
        PositionInfo("MSFT", 200, 20000, 0.20),
        PositionInfo("GOOGL", 150, 15000, 0.15),
        PositionInfo("AMZN", 100, 10000, 0.10),
        PositionInfo("TSLA", 50, 5000, 0.05),
    ]
    
    metrics2 = analyzer.analyze(positions2)
    
    print(f"\n✓ Concentrated Portfolio Test:")
    print(f"  HHI: {metrics2.herfindahl_index:.3f}")
    print(f"  Top 1: {metrics2.top_position_pct:.1%}")
    print(f"  Top 3: {metrics2.top_3_positions_pct:.1%}")
    print(f"  Effective Positions: {metrics2.effective_positions:.1f}")
    print(f"  Diversification Score: {metrics2.diversification_score:.0f}/100")
    print(f"  Is Concentrated: {metrics2.is_concentrated}")
    
    expected_hhi = 0.50**2 + 0.20**2 + 0.15**2 + 0.10**2 + 0.05**2  # 0.355
    assert abs(metrics2.herfindahl_index - expected_hhi) < 0.01
    assert abs(metrics2.top_position_pct - 0.50) < 0.01
    assert abs(metrics2.top_3_positions_pct - 0.85) < 0.01
    assert metrics2.is_concentrated == True  # HHI > 0.25
    assert metrics2.diversification_score <= 65  # Concentrated portfolio
    
    # Test 3: Single position (maximum concentration)
    positions3 = [
        PositionInfo("AAPL", 1000, 100000, 1.0),
    ]
    
    metrics3 = analyzer.analyze(positions3)
    
    print(f"\n✓ Single Position Test:")
    print(f"  HHI: {metrics3.herfindahl_index:.3f}")
    print(f"  Effective Positions: {metrics3.effective_positions:.1f}")
    print(f"  Diversification Score: {metrics3.diversification_score:.0f}/100")
    
    assert metrics3.herfindahl_index == 1.0
    assert metrics3.effective_positions == 1.0
    assert metrics3.is_concentrated == True
    
    print("\n✅ Concentration Metrics PASSED")
    # Test passed
def test_correlation_calculation():
    """Test correlation matrix calculation"""
    print("\n" + "=" * 70)
    print("TEST 2: Correlation Calculation")
    print("=" * 70)
    
    analyzer = CorrelationAnalyzer()
    
    # Generate correlated returns
    np.random.seed(42)
    base_returns = np.random.randn(100) * 0.02
    
    # AAPL and MSFT: high correlation (0.9)
    aapl_returns = base_returns + np.random.randn(100) * 0.005
    msft_returns = base_returns + np.random.randn(100) * 0.005
    
    # GOOGL: moderate correlation (0.6)
    googl_returns = base_returns * 0.6 + np.random.randn(100) * 0.01
    
    # TSLA: low correlation (independent)
    tsla_returns = np.random.randn(100) * 0.03
    
    positions = [
        PositionInfo("AAPL", 100, 25000, 0.25, returns=aapl_returns.tolist()),
        PositionInfo("MSFT", 100, 25000, 0.25, returns=msft_returns.tolist()),
        PositionInfo("GOOGL", 100, 25000, 0.25, returns=googl_returns.tolist()),
        PositionInfo("TSLA", 100, 25000, 0.25, returns=tsla_returns.tolist()),
    ]
    
    metrics = analyzer.analyze(positions)
    
    print(f"\n✓ Correlation Matrix Calculated:")
    print(f"  Avg Correlation: {metrics.avg_correlation:.2f}")
    print(f"  Max Correlation: {metrics.max_correlation:.2f}")
    print(f"  High Corr Pairs: {metrics.high_correlation_pairs}")
    print(f"  Has High Correlations: {metrics.has_high_correlations}")
    
    # Check specific correlations
    aapl_msft_corr = analyzer.get_correlation("AAPL", "MSFT")
    print(f"\n✓ AAPL-MSFT Correlation: {aapl_msft_corr:.2f}")
    assert aapl_msft_corr is not None
    assert aapl_msft_corr > 0.8  # Should be highly correlated
    
    aapl_tsla_corr = analyzer.get_correlation("AAPL", "TSLA")
    print(f"✓ AAPL-TSLA Correlation: {aapl_tsla_corr:.2f}")
    assert aapl_tsla_corr is not None
    assert abs(aapl_tsla_corr) < 0.5  # Should be low correlation
    
    # Test high correlation pairs
    high_pairs = analyzer.get_high_correlation_pairs(positions, threshold=0.7)
    print(f"\n✓ High Correlation Pairs (>0.7):")
    for pair in high_pairs:
        print(f"  {pair.symbol1}-{pair.symbol2}: {pair.correlation:.2f} "
              f"(weight: {pair.combined_weight:.1%}, risk: {pair.risk_level})")
    
    assert len(high_pairs) >= 1  # At least AAPL-MSFT
    assert high_pairs[0].correlation > 0.8
    
    print("\n✅ Correlation Calculation PASSED")
    # Test passed
def test_sector_industry_tracking():
    """Test sector and industry exposure tracking"""
    print("\n" + "=" * 70)
    print("TEST 3: Sector & Industry Tracking")
    print("=" * 70)
    
    analyzer = CorrelationAnalyzer()
    
    positions = [
        PositionInfo("AAPL", 100, 30000, 0.30, "Technology", "Consumer Electronics"),
        PositionInfo("MSFT", 100, 25000, 0.25, "Technology", "Software"),
        PositionInfo("GOOGL", 100, 20000, 0.20, "Technology", "Internet Services"),
        PositionInfo("JPM", 100, 15000, 0.15, "Financial", "Banking"),
        PositionInfo("GS", 100, 10000, 0.10, "Financial", "Investment Banking"),
    ]
    
    metrics = analyzer.analyze(positions)
    
    print(f"\n✓ Sector Concentration:")
    for sector, weight in sorted(metrics.sector_concentration.items(), 
                                  key=lambda x: x[1], reverse=True):
        print(f"  {sector}: {weight:.1%}")
    
    print(f"\n✓ Industry Concentration:")
    for industry, weight in sorted(metrics.industry_concentration.items(),
                                    key=lambda x: x[1], reverse=True):
        print(f"  {industry}: {weight:.1%}")
    
    print(f"\n✓ Risk Flags:")
    print(f"  Top Sector: {metrics.top_sector_pct:.1%}")
    print(f"  Top Industry: {metrics.top_industry_pct:.1%}")
    print(f"  Sector Risk: {metrics.sector_risk}")
    
    # Validate calculations
    assert abs(metrics.sector_concentration["Technology"] - 0.75) < 0.01
    assert abs(metrics.sector_concentration["Financial"] - 0.25) < 0.01
    assert abs(metrics.top_sector_pct - 0.75) < 0.01
    assert metrics.sector_risk == True  # Tech > 50%
    
    assert abs(metrics.industry_concentration["Consumer Electronics"] - 0.30) < 0.01
    assert abs(metrics.industry_concentration["Software"] - 0.25) < 0.01
    
    print("\n✅ Sector & Industry Tracking PASSED")
    # Test passed
def test_diversification_scoring():
    """Test diversification score calculation"""
    print("\n" + "=" * 70)
    print("TEST 4: Diversification Scoring")
    print("=" * 70)
    
    analyzer = CorrelationAnalyzer()
    
    # Test 1: Well diversified portfolio
    positions1 = [
        PositionInfo("AAPL", 100, 8000, 0.08, "Technology", "Consumer Electronics"),
        PositionInfo("MSFT", 100, 8000, 0.08, "Technology", "Software"),
        PositionInfo("JPM", 100, 8000, 0.08, "Financial", "Banking"),
        PositionInfo("JNJ", 100, 8000, 0.08, "Healthcare", "Pharma"),
        PositionInfo("XOM", 100, 8000, 0.08, "Energy", "Oil & Gas"),
        PositionInfo("PG", 100, 8000, 0.08, "Consumer", "Consumer Goods"),
        PositionInfo("DIS", 100, 8000, 0.08, "Communication", "Entertainment"),
        PositionInfo("HD", 100, 8000, 0.08, "Consumer", "Retail"),
        PositionInfo("BA", 100, 8000, 0.08, "Industrials", "Aerospace"),
        PositionInfo("CAT", 100, 8500, 0.085, "Industrials", "Machinery"),
        PositionInfo("NEE", 100, 8500, 0.085, "Utilities", "Electric"),
        PositionInfo("VZ", 100, 9000, 0.09, "Communication", "Telecom"),
    ]
    
    metrics1 = analyzer.analyze(positions1)
    
    print(f"\n✓ Well Diversified Portfolio:")
    print(f"  Positions: {metrics1.num_positions}")
    print(f"  HHI: {metrics1.herfindahl_index:.3f}")
    print(f"  Top Position: {metrics1.top_position_pct:.1%}")
    print(f"  Top Sector: {metrics1.top_sector_pct:.1%}")
    print(f"  Diversification Score: {metrics1.diversification_score:.0f}/100")
    print(f"  Effective Positions: {metrics1.effective_positions:.1f}")
    
    assert metrics1.diversification_score > 80
    assert metrics1.is_concentrated == False
    assert metrics1.sector_risk == False
    
    # Test 2: Poorly diversified portfolio
    positions2 = [
        PositionInfo("AAPL", 500, 60000, 0.60, "Technology", "Consumer Electronics"),
        PositionInfo("MSFT", 200, 40000, 0.40, "Technology", "Software"),
    ]
    
    metrics2 = analyzer.analyze(positions2)
    
    print(f"\n✓ Poorly Diversified Portfolio:")
    print(f"  Positions: {metrics2.num_positions}")
    print(f"  HHI: {metrics2.herfindahl_index:.3f}")
    print(f"  Top Position: {metrics2.top_position_pct:.1%}")
    print(f"  Top Sector: {metrics2.top_sector_pct:.1%}")
    print(f"  Diversification Score: {metrics2.diversification_score:.0f}/100")
    print(f"  Effective Positions: {metrics2.effective_positions:.1f}")
    
    assert metrics2.diversification_score < 40
    assert metrics2.is_concentrated == True
    assert metrics2.sector_risk == True
    
    print("\n✅ Diversification Scoring PASSED")
    # Test passed
def test_diversification_suggestions():
    """Test diversification suggestion generation"""
    print("\n" + "=" * 70)
    print("TEST 5: Diversification Suggestions")
    print("=" * 70)
    
    analyzer = CorrelationAnalyzer()
    
    # Concentrated portfolio with sector risk
    positions = [
        PositionInfo("AAPL", 400, 40000, 0.40, "Technology", "Consumer Electronics"),
        PositionInfo("MSFT", 300, 30000, 0.30, "Technology", "Software"),
        PositionInfo("GOOGL", 200, 20000, 0.20, "Technology", "Internet"),
        PositionInfo("AMZN", 100, 10000, 0.10, "Technology", "E-commerce"),
    ]
    
    metrics = analyzer.analyze(positions)
    suggestions = analyzer.get_diversification_suggestions(metrics)
    
    print(f"\n✓ Portfolio Analysis:")
    print(f"  HHI: {metrics.herfindahl_index:.3f}")
    print(f"  Top Position: {metrics.top_position_pct:.1%}")
    print(f"  Top Sector: {metrics.top_sector_pct:.1%}")
    print(f"  Diversification Score: {metrics.diversification_score:.0f}/100")
    
    print(f"\n✓ Suggestions ({len(suggestions)}):")
    for i, suggestion in enumerate(suggestions, 1):
        print(f"  {i}. {suggestion}")
    
    # Validate suggestions
    assert len(suggestions) > 0
    assert any("concentrated" in s.lower() for s in suggestions)
    assert any("sector" in s.lower() for s in suggestions)
    
    # Test well-diversified portfolio
    positions_good = [
        PositionInfo(f"SYM{i}", 100, 10000, 0.10, f"Sector{i%5}", f"Industry{i}")
        for i in range(10)
    ]
    
    metrics_good = analyzer.analyze(positions_good)
    suggestions_good = analyzer.get_diversification_suggestions(metrics_good)
    
    print(f"\n✓ Well-Diversified Portfolio Suggestions:")
    for suggestion in suggestions_good:
        print(f"  • {suggestion}")
    
    assert any("well diversified" in s.lower() for s in suggestions_good)
    
    print("\n✅ Diversification Suggestions PASSED")
    # Test passed
def test_new_position_impact():
    """Test new position impact analysis"""
    print("\n" + "=" * 70)
    print("TEST 6: New Position Impact Analysis")
    print("=" * 70)
    
    analyzer = CorrelationAnalyzer()
    
    # Existing positions
    current = [
        PositionInfo("AAPL", 100, 25000, 0.25, "Technology", "Consumer Electronics"),
        PositionInfo("MSFT", 100, 25000, 0.25, "Technology", "Software"),
        PositionInfo("JPM", 100, 25000, 0.25, "Financial", "Banking"),
        PositionInfo("JNJ", 100, 25000, 0.25, "Healthcare", "Pharma"),
    ]
    
    # Test 1: Good addition (diversifying)
    new_pos1 = PositionInfo("XOM", 100, 20000, 0.20, "Energy", "Oil & Gas")
    approved1, reason1, metrics1 = analyzer.check_new_position_impact(current, new_pos1)
    
    print(f"\n✓ Test 1: Adding Energy Stock (Diversifying)")
    print(f"  Approved: {approved1}")
    print(f"  Reason: {reason1}")
    print(f"  New HHI: {metrics1.herfindahl_index:.3f}")
    print(f"  New Div Score: {metrics1.diversification_score:.0f}")
    
    assert approved1 == True
    
    # Test 2: Bad addition (too large)
    new_pos2 = PositionInfo("GOOGL", 500, 50000, 0.50, "Technology", "Internet")
    approved2, reason2, metrics2 = analyzer.check_new_position_impact(current, new_pos2)
    
    print(f"\n✓ Test 2: Adding Large Tech Position (Concentrating)")
    print(f"  Approved: {approved2}")
    print(f"  Reason: {reason2}")
    print(f"  New HHI: {metrics2.herfindahl_index:.3f}")
    print(f"  New Tech Sector: {metrics2.sector_concentration.get('Technology', 0):.1%}")
    
    assert approved2 == False
    assert "too large" in reason2.lower() or "concentration" in reason2.lower()
    
    # Test 3: Bad addition (increases sector concentration)
    new_pos3 = PositionInfo("NVDA", 100, 20000, 0.20, "Technology", "Semiconductors")
    approved3, reason3, metrics3 = analyzer.check_new_position_impact(current, new_pos3)
    
    print(f"\n✓ Test 3: Adding Another Tech Stock (Sector Risk)")
    print(f"  Approved: {approved3}")
    print(f"  Reason: {reason3}")
    print(f"  New Tech Sector: {metrics3.sector_concentration.get('Technology', 0):.1%}")
    print(f"  Sector Risk: {metrics3.sector_risk}")
    
    assert approved3 == False
    assert "sector" in reason3.lower()
    
    print("\n✅ New Position Impact Analysis PASSED")
    # Test passed
def test_metrics_summary():
    """Test metrics summary generation"""
    print("\n" + "=" * 70)
    print("TEST 7: Metrics Summary")
    print("=" * 70)
    
    analyzer = CorrelationAnalyzer()
    
    positions = [
        PositionInfo("AAPL", 100, 25000, 0.25, "Technology", "Consumer Electronics"),
        PositionInfo("MSFT", 100, 25000, 0.25, "Technology", "Software"),
        PositionInfo("JPM", 100, 25000, 0.25, "Financial", "Banking"),
        PositionInfo("JNJ", 100, 25000, 0.25, "Healthcare", "Pharma"),
    ]
    
    metrics = analyzer.analyze(positions)
    summary = analyzer.get_metrics_summary(metrics)
    
    print(f"\n✓ Metrics Summary:")
    print(f"  Timestamp: {summary['timestamp']}")
    print(f"  Positions: {summary['num_positions']}")
    print(f"  Total Value: ${summary['total_value']:,.0f}")
    
    print(f"\n✓ Concentration:")
    for key, val in summary['concentration'].items():
        if isinstance(val, bool):
            print(f"  {key}: {val}")
        elif isinstance(val, float):
            if val < 1.0:
                print(f"  {key}: {val:.1%}")
            else:
                print(f"  {key}: {val:.3f}")
    
    print(f"\n✓ Correlation:")
    for key, val in summary['correlation'].items():
        print(f"  {key}: {val}")
    
    print(f"\n✓ Diversification:")
    for key, val in summary['diversification'].items():
        print(f"  {key}: {val:.1f}")
    
    print(f"\n✓ Sector Exposure:")
    for sector, weight in summary['sector_exposure'].items():
        print(f"  {sector}: {weight:.1%}")
    
    print(f"\n✓ Risk Flags:")
    for flag, value in summary['risk_flags'].items():
        print(f"  {flag}: {value}")
    
    # Validate summary structure
    assert 'concentration' in summary
    assert 'correlation' in summary
    assert 'diversification' in summary
    assert 'sector_exposure' in summary
    assert 'risk_flags' in summary
    
    assert summary['num_positions'] == 4
    assert summary['concentration']['herfindahl_index'] > 0
    assert summary['diversification']['score'] > 0
    
    print("\n✅ Metrics Summary PASSED")
    # Test passed
def run_all_tests():
    """Run all correlation analyzer validation tests"""
    print("\n" + "=" * 70)
    print("WEEK 3 DAY 4: Correlation Analysis & Portfolio Concentration")
    print("=" * 70)
    
    tests = [
        test_concentration_metrics,
        test_correlation_calculation,
        test_sector_industry_tracking,
        test_diversification_scoring,
        test_diversification_suggestions,
        test_new_position_impact,
        test_metrics_summary,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except AssertionError as e:
            print(f"\n❌ TEST FAILED: {str(e)}")
            results.append(False)
        except Exception as e:
            print(f"\n❌ TEST ERROR: {str(e)}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 70)
    if all(results):
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\n✅ Correlation analyzer working correctly")
        print("✅ Concentration metrics validated (HHI, top N)")
        print("✅ Correlation matrix calculation functional")
        print("✅ Sector/industry tracking operational")
        print("✅ Diversification scoring accurate")
        print("✅ Impact analysis working")
        print("✅ Metrics summary generation functional")
        
        print("\n📊 Correlation Analysis Summary:")
        print("  • HHI concentration index (0=diversified, 1=concentrated)")
        print("  • Correlation matrix with pairwise analysis")
        print("  • Sector/industry exposure tracking")
        print("  • Diversification score (0-100)")
        print("  • High correlation pair detection")
        print("  • New position impact pre-analysis")
        print("  • Actionable diversification suggestions")
        
        print("\n✅ Ready for Week 3 Day 5: Real-time Monitoring")
        # Test passed
    else:
        print("❌ SOME TESTS FAILED")
        print("=" * 70)
        failed = sum(1 for r in results if not r)
        print(f"\n{len(results) - failed}/{len(results)} tests passed")
        # Return statement removed - test functions should not return values
        # 
        return False


if __name__ == "__main__":
    run_all_tests()
