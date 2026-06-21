# Autonomous Basket Planner

This is Sprint 3 of the intraday trading-intelligence roadmap.

The goal is to move from a single best-candidate trade to an opt-in top-N basket
when multiple high-quality candidates are available.

## Operator responsibility

Basket mode is **disabled by default**.  It is the operator's responsibility to
validate the behaviour in recommend-only and paper mode before enabling it in
assisted-live mode.

The implementation does not artificially restrict baskets to paper mode.  When
operators opt in, the same basket plan can flow through:

- recommend-only
- paper execution
- assisted-live execution

Assisted-live still requires all existing live gates, confirmation, live account
verification, emergency-stop checks, limit-order routing, OrderExecutor safety
checks, and available live trade slots.

## Config

```python
basket_enabled = False
basket_max_size = 3
basket_total_deployable_cash_pct = 0.005
basket_single_position_deployable_cash_pct = 0.002
basket_max_same_sector_positions = 1
basket_risk_allocator_enabled = True
max_basket_risk_equity_pct = 0.002
basket_risk_allocation_mode = "equal_risk"
basket_min_leg_risk_dollars = 20.0
```

## Behaviour

When `basket_enabled=True`:

1. The engine scans and ranks candidates as before.
2. `BasketPlanner` walks the ranked list.
3. It selects up to `basket_max_size` candidates.
4. It applies same-sector caps.
5. It applies per-leg and total basket deployable-cash caps.
6. It applies the basket-level stop-risk allocator.
7. It emits:
   - `selected_basket`
   - `trade_plans`
   - `basket_plan`

For backward compatibility, `selected` and `trade_plan` continue to point to the
first basket leg.

## Basket-level risk allocation

When `basket_risk_allocator_enabled=True`, the planner applies one shared
stop-risk budget after preliminary leg planning:

```text
max basket risk dollars = account equity * max_basket_risk_equity_pct
allocated leg risk = max basket risk dollars / planned leg count
planned leg risk = (limit_price - stop_price) * quantity
```

The allocator is conservative:

- it only supports `BUY_SHARES` legs with a valid stop below entry;
- it can reduce a leg quantity to fit the allocated risk;
- it can reject a leg when one share would exceed the allocated risk;
- it never increases a leg beyond the existing TradePlanner/PositionSizer
  output;
- it does not change order submission, live gates, or broker execution paths.

`basket_plan.risk_allocation` records:

- total basket risk budget;
- total planned stop-risk;
- budget usage;
- per-leg allocated risk;
- per-leg planned risk;
- resize/rejection reasons.

Each adjusted `TradePlan.sizing` also receives a `basket_risk` diagnostic block.
If basket risk is the binding cap, `binding_cap` becomes `basket_risk_cap`.

## Paper execution

In `PAPER_EXECUTE`, the engine submits all basket legs sequentially through the
paper adapter.  Each leg is a limit BUY_SHARES order.

## Assisted-live execution

The live runner now supports basket decisions.  Before submitting any basket:

- live runner gates must pass;
- available open-trade slots must cover the number of basket legs;
- available daily trade slots must cover the number of basket legs;
- every leg still routes through `OrderExecutor`;
- every leg is recorded in `TradeStore` separately;
- every leg keeps its own target/stop bracket metadata when available.

If the basket has more legs than available live slots, the runner returns
`NO_TRADE` rather than partially executing the basket.

## Why this matters

A basket reduces single-stock false-positive risk when several candidates share
the same strong confirmation signal.  It also creates the foundation for later:

- expected-R ranking;
- sector-aware allocation;
- volatility sizing;
- fractional Kelly allocation;
- strategy-arm learning.

## Current limitations

This first version is intentionally simple:

- no correlation matrix yet;
- no Kelly weighting yet;
- no volatility weighting yet;
- no liquidity weighting yet;
- no sector ETF confirmation yet;
- sequential execution only.
- equal-risk allocation only.

Future phases should improve weighting and execution quality once sufficient
evidence exists.
