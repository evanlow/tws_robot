"""Account Intelligence API.

Exposes the eight account-intelligence modules through JSON endpoints:

  /api/intelligence/health         — account health score
  /api/intelligence/cash           — cash management analysis
  /api/intelligence/opportunities  — opportunity detection
  /api/intelligence/benchmark      — performance vs. benchmarks
  /api/intelligence/risk           — Monte Carlo, stress tests, liquidity
  /api/intelligence/reports        — report generation and alerts
  /api/intelligence/multi-account  — multi-account aggregate view
  /api/intelligence/execution      — execution quality metrics
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_account_intelligence", __name__, url_prefix="/api/intelligence")


# ====================================================================
# Helpers
# ====================================================================

def _get_account_data():
    """Pull live account data from ServiceManager."""
    svc = get_services()
    summary = svc.account_summary or {}
    positions = list((svc.positions or {}).values())
    return svc, summary, positions


def _safe(fn):
    """Wrap a route handler so uncaught errors return a 500 JSON body."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.exception("Intelligence API error in %s", fn.__name__)
            return jsonify({"error": str(exc)}), 500

    return wrapper


# ====================================================================
# 1. Account Health
# ====================================================================

@bp.route("/health", methods=["GET"])
@_safe
def account_health():
    """GET /api/intelligence/health — composite health score."""
    from data.account_health import AccountHealthAnalyzer

    svc, summary, positions = _get_account_data()

    equity = summary.get("equity", 0)
    cash = summary.get("cash_balance", 0)
    margin_used = summary.get("margin_used", 0)
    margin_avail = summary.get("margin_available", 0)
    peak_equity = getattr(svc.risk_manager, "peak_equity", equity)

    pos_dicts = []
    for p in positions:
        mv = abs(p.get("market_value", 0) or p.get("quantity", 0) * p.get("current_price", 0))
        pos_dicts.append({"market_value": mv, "symbol": p.get("symbol", "?")})

    analyzer = AccountHealthAnalyzer(initial_capital=equity or 100_000)
    score = analyzer.compute_health_score(
        equity=equity,
        cash_balance=cash,
        margin_used=margin_used,
        margin_available=margin_avail,
        peak_equity=peak_equity,
        positions=pos_dicts,
    )
    return jsonify(score.to_dict())


# ====================================================================
# 2. Cash Management
# ====================================================================

@bp.route("/cash", methods=["GET"])
@_safe
def cash_management():
    """GET /api/intelligence/cash — cash reserve & flow analysis."""
    from data.cash_management import CashManagementEngine, CashReserveConfig, ReservePolicy

    svc, summary, _ = _get_account_data()

    policy_name = request.args.get("policy", "MODERATE").upper()
    try:
        policy = ReservePolicy(policy_name)
    except ValueError:
        policy = ReservePolicy.MODERATE

    config = CashReserveConfig(policy=policy)
    engine = CashManagementEngine(config=config)

    cash = summary.get("cash_balance", 0)
    equity = summary.get("equity", 0)

    analysis = engine.analyze(cash_balance=cash, equity=equity)
    return jsonify(analysis.to_dict())


# ====================================================================
# 3. Opportunity Detection
# ====================================================================

@bp.route("/opportunities", methods=["GET"])
@_safe
def opportunities():
    """GET /api/intelligence/opportunities — scan for portfolio opportunities."""
    from data.opportunity_detector import OpportunityDetector

    svc, summary, positions = _get_account_data()

    equity = summary.get("equity", 0)
    pos_dicts = []
    for p in positions:
        mv = abs(p.get("market_value", 0) or p.get("quantity", 0) * p.get("current_price", 0))
        pos_dicts.append({
            "symbol": p.get("symbol", "?"),
            "market_value": mv,
            "sector": p.get("sector", "Unknown"),
        })

    detector = OpportunityDetector()
    opps = detector.scan(positions=pos_dicts, equity=equity)
    return jsonify({
        "opportunities": [o.to_dict() for o in opps],
        "summary": detector.get_summary(),
    })


# ====================================================================
# 4. Benchmark Comparison
# ====================================================================

@bp.route("/benchmark", methods=["GET"])
@_safe
def benchmark():
    """GET /api/intelligence/benchmark — portfolio vs. benchmark returns."""
    from data.performance_benchmarking import PerformanceBenchmarker

    svc, summary, _ = _get_account_data()

    benchmarker = PerformanceBenchmarker(
        initial_capital=summary.get("equity", 100_000),
    )

    period = int(request.args.get("period_days", 30))
    bench_name = request.args.get("benchmark", "SPY")

    comparison = benchmarker.compare_to_benchmark(benchmark=bench_name, period_days=period)
    fee_drag = benchmarker.compute_fee_drag(period_days=period)

    return jsonify({
        "comparison": comparison.to_dict(),
        "fee_drag": fee_drag.to_dict(),
        "summary": benchmarker.get_summary(),
    })


# ====================================================================
# 5. Risk Intelligence
# ====================================================================

@bp.route("/risk", methods=["GET"])
@_safe
def risk_intelligence():
    """GET /api/intelligence/risk — Monte Carlo, stress tests, liquidity."""
    from data.risk_intelligence import RiskIntelligenceEngine, StressScenario

    svc, summary, positions = _get_account_data()

    engine = RiskIntelligenceEngine()

    pos_dicts = []
    for p in positions:
        mv = abs(p.get("market_value", 0) or p.get("quantity", 0) * p.get("current_price", 0))
        pos_dicts.append({
            "symbol": p.get("symbol", "?"),
            "market_value": mv,
            "beta": p.get("beta", 1.0),
            "quantity": abs(p.get("quantity", 0)),
            "current_price": p.get("current_price", 0),
            "avg_daily_volume": p.get("avg_daily_volume", 1_000_000),
        })

    # Monte Carlo (use empty returns if no history)
    daily_returns = getattr(svc.risk_manager, "daily_returns", [])
    mc = engine.run_monte_carlo(daily_returns=daily_returns)

    # Stress tests
    stress = engine.run_all_stress_tests(pos_dicts)

    # Liquidity
    liquidity = engine.analyze_liquidity(pos_dicts)

    return jsonify({
        "monte_carlo": mc.to_dict(),
        "stress_tests": [s.to_dict() for s in stress],
        "liquidity": [l.to_dict() for l in liquidity],
    })


# ====================================================================
# 6. Reports & Alerts
# ====================================================================

@bp.route("/reports", methods=["GET"])
@_safe
def reports():
    """GET /api/intelligence/reports — generate a summary report."""
    from monitoring.report_generator import ReportGenerator, ReportPeriod

    period_str = request.args.get("period", "DAILY").upper()
    try:
        period = ReportPeriod(period_str)
    except ValueError:
        period = ReportPeriod.DAILY

    generator = ReportGenerator()
    generator.add_default_rules()

    report = generator.generate_report(period=period)
    return jsonify(report.to_dict())


@bp.route("/alerts", methods=["GET"])
@_safe
def alerts():
    """GET /api/intelligence/alerts — recent threshold alerts."""
    from monitoring.report_generator import ReportGenerator

    generator = ReportGenerator()
    return jsonify({
        "alerts": [a.to_dict() for a in generator.get_recent_alerts()],
        "summary": generator.get_summary(),
    })


# ====================================================================
# 7. Multi-Account
# ====================================================================

@bp.route("/multi-account", methods=["GET"])
@_safe
def multi_account():
    """GET /api/intelligence/multi-account — aggregate multi-account view."""
    from data.multi_account import MultiAccountManager, AccountSnapshot

    svc, summary, positions = _get_account_data()

    manager = MultiAccountManager()

    # Register current account as single entry
    account_id = summary.get("account_id", "default")
    snap = AccountSnapshot(
        account_id=account_id,
        label="Primary",
        equity=summary.get("equity", 0),
        cash_balance=summary.get("cash_balance", 0),
        margin_used=summary.get("margin_used", 0),
        margin_available=summary.get("margin_available", 0),
        unrealized_pnl=summary.get("unrealized_pnl", 0),
        realized_pnl=summary.get("realized_pnl", 0),
        position_count=len(positions),
        positions=[{
            "symbol": p.get("symbol", "?"),
            "market_value": abs(p.get("market_value", 0)),
        } for p in positions],
    )
    manager.update_account(snap)

    aggregate = manager.get_aggregate_view()
    risk = manager.analyze_cross_account_risk()

    return jsonify({
        "aggregate": aggregate.to_dict(),
        "cross_account_risk": risk.to_dict(),
    })


# ====================================================================
# 8. Execution Quality
# ====================================================================

@bp.route("/execution", methods=["GET"])
@_safe
def execution_quality():
    """GET /api/intelligence/execution — order execution quality metrics."""
    from execution.execution_quality import ExecutionQualityAnalyzer

    analyzer = ExecutionQualityAnalyzer()
    period = request.args.get("period_days")
    period_days = int(period) if period else None

    summary = analyzer.get_summary(period_days=period_days)
    return jsonify(summary.to_dict())


# ====================================================================
# Master endpoint: all intelligence in one call
# ====================================================================

@bp.route("/summary", methods=["GET"])
@_safe
def intelligence_summary():
    """GET /api/intelligence/summary — high-level summary from all modules."""
    from data.account_health import AccountHealthAnalyzer
    from data.cash_management import CashManagementEngine
    from data.opportunity_detector import OpportunityDetector
    from data.risk_intelligence import RiskIntelligenceEngine
    from execution.execution_quality import ExecutionQualityAnalyzer

    svc, summary, positions = _get_account_data()
    equity = summary.get("equity", 0)
    cash = summary.get("cash_balance", 0)
    margin_used = summary.get("margin_used", 0)
    margin_avail = summary.get("margin_available", 0)
    peak_equity = getattr(svc.risk_manager, "peak_equity", equity)

    pos_dicts = [{
        "market_value": abs(p.get("market_value", 0) or p.get("quantity", 0) * p.get("current_price", 0)),
        "symbol": p.get("symbol", "?"),
        "sector": p.get("sector", "Unknown"),
    } for p in positions]

    # Health
    health_analyzer = AccountHealthAnalyzer(initial_capital=equity or 100_000)
    health = health_analyzer.compute_health_score(
        equity=equity, cash_balance=cash, margin_used=margin_used,
        margin_available=margin_avail, peak_equity=peak_equity, positions=pos_dicts,
    )

    # Cash
    cash_engine = CashManagementEngine()
    cash_analysis = cash_engine.analyze(cash_balance=cash, equity=equity)

    # Opportunities
    detector = OpportunityDetector()
    opps = detector.scan(positions=pos_dicts, equity=equity)

    return jsonify({
        "health": health.to_dict(),
        "cash": {"is_adequate": cash_analysis.is_adequate, "cash_pct": round(cash_analysis.cash_pct * 100, 2)},
        "opportunities_count": len(opps),
        "modules_available": [
            "health", "cash", "opportunities", "benchmark",
            "risk", "reports", "multi-account", "execution",
        ],
    })
