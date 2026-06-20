# Autonomous Trading Evidence Foundation

This is Sprint 1 of the trading-intelligence roadmap.

The goal is to record a durable, schema-versioned evidence trail for every
autonomous decision so future components can estimate edge, build baskets,
apply fractional Kelly, run drawdown governors, and compare strategy variants.

## Why this is separate from audit logs

The existing audit log is operational: it answers what happened and supports
safety traceability.

The evidence store is analytical: it answers what can be learned.

Both are append-only JSONL files, but evidence records are normalized around
strategy learning fields such as:

- signal bucket
- market regime
- selected candidate
- trade plan
- planned risk
- candidate counts
- rejected candidates
- eventual outcome placeholder

## Files

Evidence records are date-rotated:

```text
logs/autonomous_evidence_YYYYMMDD.jsonl
```

Each line is one JSON record.

## API

A read-only endpoint returns recent records, newest first:

```text
GET /api/autonomous/evidence?limit=100
```

Response:

```json
{
  "count": 1,
  "records": [
    {
      "schema_version": 1,
      "evidence_type": "autonomous_decision",
      "status": "recommended",
      "symbol": "AAPL"
    }
  ]
}
```

## Current schema highlights

```json
{
  "schema_version": 1,
  "evidence_type": "autonomous_decision",
  "timestamp": "2026-06-20T00:00:00+00:00",
  "engine": "AutonomousTradingEngine",
  "status": "recommended",
  "mode": "recommend_only",
  "symbol": "AAPL",
  "strategy_bucket": {
    "signal_label": "Confirmed Rebound",
    "strength_score": 100,
    "quality_label": "Strong",
    "momentum_label": "Confirmed Rebound",
    "sector": "Technology",
    "market_classification": "Bullish / Volatility Acceptable",
    "spy_bullish": true,
    "vix_level_regime": "normal",
    "vix_direction_regime": "falling"
  },
  "planned_risk": {
    "entry_price": 100.0,
    "target_price": 108.0,
    "stop_price": 96.0,
    "risk_per_share": 4.0,
    "planned_dollar_risk": 40.0,
    "planned_r_multiple": 2.0
  },
  "candidate_counts": {
    "shortlist": 1,
    "rejected": 499
  },
  "outcome": {
    "realized": false,
    "exit_price": null,
    "realized_pnl": null,
    "realized_r_multiple": null,
    "exit_reason": null
  }
}
```

## How it is written

`AutonomousTradingEngine._emit()` now writes both:

1. the existing audit record, and
2. a normalized evidence record through `TradeEvidenceStore`.

Evidence-writing failures are logged defensively and must never break trading.

## What this enables next

This evidence foundation supports later roadmap phases:

- support/resistance validation
- edge estimation
- expected-R ranking
- basket construction
- risk-per-trade sizing
- fractional Kelly sizing
- drawdown governor
- strategy-arm learning
- walk-forward validation

## Current limitation

The `outcome` section is initially a placeholder.  Future work should connect
open/closed trade reconciliation and exit-manager results back to the evidence
record so each planned trade can be evaluated against actual realized P&L and
R-multiple.
