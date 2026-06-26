# Test Coverage Analysis

**Date:** June 26, 2026

This document summarizes the current coverage posture after the autonomous and
evidence-learning work moved TWS Robot's safety-critical surface beyond the
older backtest/profile-comparison focus.

## Current Status

The historical ProfileComparator integration gap has been addressed:

- `backtest/profile_comparison.py` now builds a `StrategyConfig` from the risk
  profile and passes that config to real strategy classes.
- `tests/test_profile_comparison.py` includes integration coverage for
  `MomentumStrategy`, `MovingAverageCrossStrategy`, and
  `MeanReversionStrategy`.

The remaining coverage priorities are broader and safety-focused.

## Critical Coverage Requirements

The default pytest coverage configuration must include the current core
packages:

- `core`
- `data`
- `ai`
- `strategies`
- `backtest`
- `risk`
- `execution`
- `monitoring`
- `strategy`
- `autonomous`
- `web`

`autonomous` is safety-critical because it contains scan/rank/plan/execute
logic, assisted-live gates, evidence learning, recovery, replay, broker
protection, idempotency, and capital-promotion advisory logic.

## Smoke Coverage Requirements

The smoke suite is marker-based:

```bash
python tests/run_all_smoke.py
pytest -m smoke
```

The maintained smoke inventory lives in:

```text
tests/smoke_manifest.py
```

Smoke coverage should include:

- emergency-stop and order-blocking regressions;
- authentication and config-security gates;
- core order execution and TWS bridge safety paths;
- autonomous API, dashboard, engine, runner, and live-runner paths;
- paper/live mode separation and dry-run guards;
- basket risk allocation;
- order lifecycle, broker fill ingestion, idempotency, recovery, and replay;
- quote freshness and market-data health guards;
- trade planning and sizing caps;
- evidence learning, setup eligibility, risk lifecycle, and capital promotion;
- operator-facing portfolio and FX research smoke coverage.

## Documentation Coverage Requirements

Documentation checks should cover more than file presence. For safety-critical
features, docs should state:

- what changed;
- which order paths are affected;
- whether live behavior changed;
- whether defaults remain safe;
- which tests and smoke tests cover the behavior;
- known limitations and required manual checks.

The following docs are canonical for autonomous/evidence-learning behavior:

- `docs/AUTONOMOUS_TRADING_SYSTEM_SPEC.md`
- `docs/AUTONOMOUS_IMPLEMENTATION_TRACKER.md`
- `docs/AUTONOMOUS_EVIDENCE_LEARNING_SPEC.md`
- `docs/AUTONOMOUS_EVIDENCE_LEARNING_TRACKER.md`
- `docs/WEB_API_REFERENCE.md`
- `docs/TESTING.md`

## Known Limitations

- Example scripts are syntax-checked but are not comprehensively executed as
  smoke tests because several examples expect market data or longer-running
  backtest inputs.
- Some live-trading readiness checks remain intentionally manual because IBKR
  account permissions, TWS/Gateway settings, and market-data subscriptions must
  be verified by an operator.
- The smoke suite is intentionally broader than a minimal "app starts" check;
  if runtime becomes too high, split it by marker expressions rather than
  removing safety-critical modules from the manifest.
