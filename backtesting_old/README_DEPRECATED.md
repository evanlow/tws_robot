# DEPRECATED - Legacy Backtesting Module

⚠️ **This directory contains deprecated/legacy code and should not be used for new development.**

## Status: ARCHIVED (November 22, 2025)

This `backtesting_old/` directory was renamed from `backtesting/` to avoid confusion with the new production-ready `backtest/` module.

## Why Deprecated?

The **`backtest/` module** (Week 4) is now the official, production-ready backtesting system with:
- ✅ 138/138 tests passing (100% coverage)
- ✅ Complete strategy framework with templates
- ✅ Risk management profiles
- ✅ Performance analytics
- ✅ Full documentation

## What's in This Directory?

Legacy backtesting code from earlier development:
- `backtest_engine.py` - Old engine (replaced by `backtest/engine.py`)
- `historical_data.py` - Old data manager (replaced by `backtest/data_manager.py`)
- `performance_analytics.py` - Old analytics (replaced by `backtest/performance.py`)
- `risk_manager.py` - Old risk manager (replaced by risk profiles)

## Migration Path

**Old files using this:**
- `optimize_strategy.py` (legacy, not maintained)
- `run_backtest.py` (legacy, not maintained)
- `tests/test_risk_manager.py` (legacy tests, superseded by Week 4 tests)
- `tests/test_performance_analytics.py` (legacy tests, superseded)

**Use instead:**
- All new development should use `backtest/` module
- See `WEEK4_DOCUMENTATION.md` for complete API docs
- See `example_week4_integration.py` for usage examples
- See `test_with_real_data.py` for real data testing

## Can This Be Deleted?

Yes, after confirming no active dependencies. The legacy files (`optimize_strategy.py`, `run_backtest.py`) are not part of the core system and can be rewritten if needed.

## Reference

- Production Module: `backtest/`
- Documentation: `WEEK4_DOCUMENTATION.md`
- Tests: `test_backtest_*.py`, `test_profiles.py`, `test_strategy_templates.py`
- Examples: `example_week4_integration.py`, `test_with_real_data.py`
