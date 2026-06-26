"""Smoke-suite inventory for safety-critical TWS Robot paths.

The smoke marker is applied during collection from this manifest so the suite
can be run with ``pytest -m smoke`` without repeating a long file list in
scripts, CI jobs, or PR notes.
"""

from __future__ import annotations


SMOKE_TEST_MODULES = {
    # Original operator-facing smoke coverage.
    "test_safety_regression.py",
    "test_web_api.py",
    "test_portfolio_analysis.py",
    "test_auth.py",
    "test_config_security.py",
    "test_order_executor.py",
    "test_tws_bridge.py",
    "test_fx_research.py",

    # Autonomous trading API, engine, runner, and dashboard safety paths.
    "test_api_autonomous.py",
    "test_api_autonomous_evidence.py",
    "test_api_autonomous_live.py",
    "test_api_autonomous_runner.py",
    "test_api_trading_readiness.py",
    "test_assisted_live_stop_requirement.py",
    "test_autonomous_dashboard.py",
    "test_autonomous_engine.py",
    "test_autonomous_engine_basket.py",
    "test_autonomous_engine_evidence.py",
    "test_autonomous_engine_vix_gate.py",
    "test_autonomous_exit_manager.py",
    "test_autonomous_live_runner.py",
    "test_autonomous_live_runner_basket.py",
    "test_autonomous_paper_adapter.py",
    "test_autonomous_runner.py",
    "test_autonomous_trade_store.py",
    "test_controlled_live_trading.py",
    "test_live_dry_run_guard.py",

    # Order lifecycle, broker-state, recovery, market-data, and replay guards.
    "test_basket_planner.py",
    "test_broker_fill_ingestor.py",
    "test_continuous_supervisor.py",
    "test_idempotency.py",
    "test_market_data_health.py",
    "test_market_data_provider.py",
    "test_order_lifecycle.py",
    "test_recovery_manager.py",
    "test_replay_engine.py",

    # Trade planning, evidence learning, risk lifecycle, and promotion gates.
    "test_adaptive_edge_estimator.py",
    "test_capital_promotion.py",
    "test_emergency_controls.py",
    "test_evidence_aware_sizer.py",
    "test_evidence_calibrator.py",
    "test_evidence_learning_summary.py",
    "test_risk_lifecycle.py",
    "test_setup_eligibility.py",
    "test_setup_registry.py",
    "test_trade_evidence_store.py",
    "test_trade_planner.py",
    "test_trade_planner_evidence_sizing.py",
    "test_trade_planner_execution_quality.py",
    "test_trade_planner_fractional_drawdown.py",
    "test_trade_planner_sizing.py",
}
