# Fit-for-Trading Status

This document defines what TWS Robot means by **fit for trading**.  The phrase
is intentionally narrow: it means the system is fit for a **small, monitored,
single-trade live experiment**, not fit to manage meaningful capital.

## Status endpoint

The dashboard/backend exposes a read-only status matrix:

```text
GET /api/trading-readiness/status
```

The endpoint does not place orders.  It reports the current readiness of five
operating modes:

| Mode | Meaning | Target status |
|---|---|---|
| `recommend_only` | Scan and propose without execution | `YES` |
| `paper_execution` | Submit autonomous orders to paper account | `YES` when paper is connected and a real signal provider is ready |
| `live_dry_run` | Rehearse the full live lifecycle without TWS order submission | `YES` before any actual-live test |
| `actual_live_single_trade` | One small live BUY-shares trade with broker-side bracket exit | `YES` only for the first-live experiment |
| `actual_live_continuous` | Repeated actual-live cycles | `BLOCKED` by default |
| `capital_growth_50k` | Autonomous management of meaningful capital | `BLOCKED` by default |

## First-live experiment gates

`actual_live_single_trade` is marked `YES` only when all of these are true:

1. TWS/Gateway is connected in live mode.
2. A live account ID has been detected.
3. Live account data is ready.
4. `AUTONOMOUS_LIVE_ENABLED=true`.
5. Emergency stop is inactive.
6. A real signal provider is wired; the fallback `StaticSignalProvider` is not accepted.
7. Deployable cash is above the configured minimum.
8. The persistent TWS bridge is connected.
9. `live_limit_orders_only=true`.
10. `buy_shares_only=true`.
11. `max_open_live_trades == 1`.
12. `max_live_trades_per_day == 1`.
13. The calculated maximum trade value is not above the first-live cap.

The first-live cap defaults to:

```text
FIT_FOR_TRADING_MAX_SINGLE_TRADE_VALUE=300
```

The live-runner default deployable-cash percentage has also been tightened to
0.5%:

```text
AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT=0.005
```

For a USD 50,000 account, the default maximum live experiment order value is
approximately USD 250 before share rounding.

## Continuous and meaningful-capital gates

Continuous actual-live trading remains policy-blocked unless explicitly enabled:

```text
FIT_FOR_TRADING_ALLOW_CONTINUOUS_EXPERIMENT=true
```

Even then, continuous mode must still pass live gates and requires an explicit
`AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY` greater than `1`.

Autonomous management of meaningful capital remains policy-blocked unless a
future operator deliberately enables:

```text
FIT_FOR_TRADING_ALLOW_CAPITAL_GROWTH=true
```

That flag should not be used until live dry-runs, multiple single-trade live
experiments, bracket-exit reconciliation, audit review, and emergency procedures
are proven.

## Dry-run guard

The web application installs a runtime guard for live dry-run reconciliation.
When the executor is in dry-run mode and no TWS adapter is attached, portfolio
reconciliation is allowed to proceed because no order can be submitted.  When the
executor is not in dry-run mode and no adapter is attached, reconciliation fails
closed instead of raising an exception.

This makes live dry-run a reliable rehearsal path while preserving fail-closed
behaviour for real execution.
