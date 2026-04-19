# TWS Robot - Web API Reference

**REST API documentation for the TWS Robot web dashboard.**

---

## 📚 Documentation Navigation

**You are here:** Web API Reference - Dashboard API documentation  
**Developer docs:** [API Reference](API_REFERENCE.md) - Python APIs for strategies  
**Start here:** [README](../README.md) - Installation and overview  
**Learn concepts:** [User Guide](USER_GUIDE.md) - How strategies work

---

## 📚 Table of Contents

1. [Overview](#overview)
2. [Connection Management API](#connection-management-api)
3. [Account & Portfolio API](#account--portfolio-api)
4. [Orders API](#orders-api)
5. [Data API](#data-api)
6. [Market Data API](#market-data-api)
7. [Strategies API](#strategies-api)
8. [Backtest API](#backtest-api)
9. [Emergency Controls API](#emergency-controls-api)
10. [Events & Monitoring API](#events--monitoring-api)
11. [System API](#system-api)
12. [AI Assistant APIs](#ai-assistant-apis)

---

## Overview

The TWS Robot web dashboard provides a comprehensive REST API for managing trading operations, monitoring positions, and controlling strategies. All endpoints return JSON responses.

**Base URL:** `http://localhost:5000`

**Response Format:**
```json
{
  "status": "success|error",
  "data": { ... },
  "error": "error message (if applicable)"
}
```

---

## Connection Management API

### `GET /api/connection/status`

Get current TWS connection status.

**Response:**
```json
{
  "connected": true,
  "environment": "paper",
  "info": {
    "host": "127.0.0.1",
    "port": 7497,
    "client_id": 1,
    "account": "DU12345"
  }
}
```

### `POST /api/connection/connect`

Connect to Interactive Brokers TWS or IB Gateway.

**Request Body:**
```json
{
  "environment": "paper"  // or "live"
}
```

**Response:**
```json
{
  "status": "connected",
  "environment": "paper",
  "host": "127.0.0.1",
  "port": 7497
}
```

**Error Responses:**
- `409 Conflict` - Already connected
- `400 Bad Request` - Invalid environment or configuration error

### `POST /api/connection/disconnect`

Disconnect from TWS.

**Response:**
```json
{
  "status": "disconnected"
}
```

**Error Responses:**
- `409 Conflict` - Not connected

---

## Account & Portfolio API

### `GET /api/account/summary`

Get comprehensive account summary including equity, P&L, risk status, and buying power.

**Response:**
```json
{
  "connected": true,
  "environment": "paper",
  "equity": 105000.00,
  "peak_equity": 110000.00,
  "daily_pnl_pct": 2.43,
  "daily_pnl_dollar": 2500.00,
  "drawdown_pct": 4.55,
  "stock_drawdown_pct": 3.21,
  "premium_retention_pct": 0.85,
  "short_options_premium_collected": 2500.00,
  "short_options_current_liability": 2125.00,
  "risk_status": "NORMAL",
  "emergency_stop": false,
  "buying_power": 200000.00,
  "cash_balance": 50000.00,
  "unrealized_pnl": 1500.00,
  "limits": {
    "max_drawdown_pct": 15.0,
    "daily_loss_limit_pct": 5.0
  }
}
```

**Field Descriptions:**
- `connected` - Whether connected to TWS/IB Gateway
- `environment` - `"paper"` or `"live"`
- `equity` - Current account equity (NAV)
- `peak_equity` - Highest equity reached today
- `daily_pnl_pct` - Daily P&L as percentage of starting equity
- `daily_pnl_dollar` - Daily P&L in dollars (calculated: current_equity - daily_start_equity)
- `drawdown_pct` - Current drawdown from peak as percentage (total portfolio)
- `stock_drawdown_pct` - Drawdown from peak for stock/long-only positions (excludes short option mark-to-market fluctuations)
- `premium_retention_pct` - Fraction of collected premium retained for short options (0-1, where 1.0 = 100% retained)
- `short_options_premium_collected` - Total premium collected from short option positions
- `short_options_current_liability` - Current mark-to-market liability of short option positions
- `risk_status` - Risk status: `"NORMAL"`, `"WARNING"`, or `"CRITICAL"`
- `emergency_stop` - Whether emergency stop is active (triggered by stock_drawdown_pct, not total drawdown)
- `buying_power` - Available buying power
- `cash_balance` - Cash balance
- `unrealized_pnl` - Total unrealized P&L across all positions (calculated: sum of all position unrealized P&L)
- `limits` - Configured risk limits

**Strategy-Aware Risk Tracking:**

The API now provides separate tracking for stock-only positions vs. short options:

- **Stock Drawdown** (`stock_drawdown_pct`): Tracks drawdown for long stock positions only, excluding short option mark-to-market. This prevents false emergency stops from short option premium fluctuations when the underlying stock strategy is performing well.

- **Premium Retention** (`premium_retention_pct`): Monitors how much of the collected premium from short options you're retaining. Formula: `1 - (current_liability / premium_collected)`. A value of 0.85 means you're retaining 85% of collected premium (15% has been given back to mark-to-market).

- **Emergency Stops**: Triggered based on `stock_drawdown_pct` (not total `drawdown_pct`), ensuring risk limits focus on the actual trading strategy performance rather than expected option premium variations.

**Use Case Example:**

You sell covered calls (short options) against long stock positions. The stock rises, increasing your stock equity, but the short calls also increase in value (negative mark-to-market). Traditional drawdown tracking would show a loss from the calls, potentially triggering false emergency stops. Stock-aware tracking separates these:

- Stock equity up 5% → `stock_drawdown_pct` improving
- Short calls liability up 20% → `premium_retention_pct` down to 0.80
- Emergency stops won't trigger unless stock positions actually decline

### `GET /api/account/positions`

Get all open positions.

**Response:**
```json
{
  "positions": {
    "AAPL": {
      "quantity": 100,
      "entry_price": 145.00,
      "current_price": 150.00,
      "market_value": 15000.00,
      "unrealized_pnl": 500.00,
      "unrealized_pnl_pct": 3.45,
      "realized_pnl": 0.00,
      "side": "LONG"
    },
    "TSLA": {
      "quantity": -50,
      "entry_price": 210.00,
      "current_price": 200.00,
      "market_value": -10000.00,
      "unrealized_pnl": 500.00,
      "unrealized_pnl_pct": 4.76,
      "realized_pnl": 0.00,
      "side": "SHORT"
    }
  }
}
```

### `GET /api/account/symbol-names`

Resolve ticker symbols to human-readable company names.

**NEW in v1.7 (PR #24)** - Company Name Display

**Query Parameters:**
- `symbols` (optional): Comma-separated list of ticker symbols to resolve (e.g., `AAPL,MSFT,GOOGL`)
  - When omitted, defaults to all stock symbols currently in the portfolio
  - Maximum 50 symbols per request (rate limited)

**Response:**
```json
{
  "names": {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc."
  }
}
```

**Error Response (400 - Too Many Symbols):**
```json
{
  "error": "Too many symbols (max 50)"
}
```

**Behavior:**
- Filters out option symbols automatically when using portfolio default
- Only returns names that are successfully resolved (silently skips failures)
- Uses cached fundamental data when available for faster response
- Returns empty object if no symbols provided or all resolutions fail

**Example Usage:**
```javascript
// Get names for specific symbols
fetch('/api/account/symbol-names?symbols=AAPL,TSLA')
  .then(r => r.json())
  .then(data => {
    console.log(data.names);  // {"AAPL": "Apple Inc.", "TSLA": "Tesla, Inc."}
  });

// Get names for all portfolio stocks
fetch('/api/account/symbol-names')
  .then(r => r.json())
  .then(data => {
    // Automatically resolves all stock positions in portfolio
    Object.entries(data.names).forEach(([symbol, name]) => {
      console.log(`${symbol}: ${name}`);
    });
  });
```

**Use Cases:**
- Display company names alongside ticker symbols in UI tables
- Add tooltips/hovers showing full company names
- Improve readability of position lists and reports
- Help users quickly identify holdings without memorizing tickers

### `GET /api/account/portfolio-analysis`

Get comprehensive portfolio analysis including concentration metrics, sector exposure, drawdown tracking, and P&L attribution.

**NEW in v1.6 (PR #14)** - Portfolio Analysis Dashboard

**Response:**
```json
{
  "allocation": [
    {
      "symbol": "AAPL",
      "market_value": 15000.00,
      "weight": 0.48,
      "unrealized_pnl": 500.00
    },
    {
      "symbol": "MSFT",
      "market_value": 10000.00,
      "weight": 0.32,
      "unrealized_pnl": -200.00
    }
  ],
  "total_value": 31000.00,
  "concentration": {
    "herfindahl_index": 0.31,
    "top_position_pct": 0.48,
    "top_3_positions_pct": 0.85,
    "top_5_positions_pct": 0.95
  },
  "diversification": {
    "score": 68.5,
    "effective_positions": 3.2
  },
  "sector_exposure": {
    "Technology": 0.65,
    "Healthcare": 0.25,
    "Finance": 0.10
  },
  "risk_flags": {
    "is_concentrated": true,
    "has_high_correlations": false,
    "sector_risk": true
  },
  "drawdown": {
    "current_pct": 0.045,
    "peak_equity": 110000.00,
    "current_equity": 105000.00
  },
  "attribution": {
    "by_symbol": [
      {"name": "AAPL", "pnl": 1250.00},
      {"name": "MSFT", "pnl": 850.00},
      {"name": "TSLA", "pnl": -300.00}
    ],
    "by_strategy": [
      {"name": "momentum", "pnl": 2100.00},
      {"name": "mean_reversion", "pnl": -200.00}
    ],
    "win_rate": 0.625,
    "total_pnl": 1800.00
  },
  "suggestions": [
    "Portfolio is concentrated (HHI=0.31). Consider adding 2-3 more positions.",
    "Technology sector exposure (65%) exceeds diversification threshold. Reduce to <50%.",
    "Top position (AAPL) represents 48% of portfolio. Reduce to <25% for better risk management."
  ]
}
```

**Field Descriptions:**

**Allocation:**
- `allocation` - Array of position breakdowns
- `symbol` - Ticker symbol
- `market_value` - Absolute market value (uses abs() for short positions)
- `weight` - Position weight in portfolio (0.0 to 1.0, based on gross market values)
- `unrealized_pnl` - Unrealized profit/loss for the position
- `total_value` - Total gross market value of all positions

**Concentration Metrics:**
- `herfindahl_index` - HHI concentration measure (0=perfectly diversified, 1=fully concentrated)
  - Values > 0.25 indicate concentration risk
  - Formula: sum of squared weights
- `top_position_pct` - Largest single position as % of portfolio
- `top_3_positions_pct` - Top 3 positions combined weight
- `top_5_positions_pct` - Top 5 positions combined weight

**Diversification:**
- `score` - Overall diversification score (0-100, where 100=well diversified)
  - Considers number of positions, weight distribution, and correlations
- `effective_positions` - Effective number of independent positions
  - Accounts for correlation and concentration
  - E.g., 10 positions with 0.8 correlation act like ~3 effective positions

**Sector Exposure:**
- Mapping of sector names to portfolio weights
- Sum of all sector weights should equal ~1.0
- Helps identify sector concentration risks

**Risk Flags:**
- `is_concentrated` - True if HHI > 0.25
- `has_high_correlations` - True if any position pair has correlation > 0.8
- `sector_risk` - True if any single sector exceeds 50% of portfolio

**Drawdown:**
- `current_pct` - Current drawdown from peak (0.0 to 1.0)
  - Clamped to [0, 1] range to handle edge cases
- `peak_equity` - Highest equity reached
- `current_equity` - Current account equity

**Attribution:**
- `by_symbol` - P&L breakdown by ticker symbol (from closed trades)
- `by_strategy` - P&L breakdown by strategy name (from closed trades)
- `win_rate` - Percentage of profitable trades (0.0 to 1.0)
- `total_pnl` - Total P&L from all closed trades analyzed

**Suggestions:**
- Array of actionable recommendations for improving portfolio diversification
- Generated based on concentration, correlation, and sector exposure analysis

**Use Cases:**

1. **Portfolio Health Dashboard:**
   ```javascript
   fetch('/api/account/portfolio-analysis')
     .then(res => res.json())
     .then(data => {
       if (data.risk_flags.is_concentrated) {
         console.warn('Portfolio concentration detected!');
         data.suggestions.forEach(s => console.log('💡', s));
       }
     });
   ```

2. **Risk Monitoring:**
   - Check HHI regularly (target: < 0.25 for diversified portfolio)
   - Monitor top position (target: < 25% of portfolio)
   - Review sector exposure (target: no sector > 50%)

3. **Performance Review:**
   - Identify top/bottom performers by symbol
   - Compare strategy effectiveness via attribution
   - Track win rate trends

**Notes:**

- Uses absolute (gross) market values for weights, so short positions contribute positively to concentration
- Drawdown is clamped to [0.0, 1.0] to handle edge cases (e.g., equity exceeding peak)
- Attribution only includes closed trades with complete data (entry_time, exit_time, pnl, strategy)
- Sector/industry data depends on position metadata; positions without sector info are excluded
- For large portfolios (100+ positions), calculation may take 1-2 seconds

### `GET /api/account/portfolio-insights`

**NEW in v1.7 (PR #17)** - AI-Powered Portfolio Intelligence

Get enhanced portfolio analysis with AI-powered strategy deduction, allocation intelligence, and actionable recommendations.

**Query Parameters:**
- `ai` (optional, default: `true`) - Enable/disable AI narrative and recommendations

**Response:**
```json
{
  "positions_enriched": [
    {
      "symbol": "AAPL",
      "quantity": 100,
      "market_value": 17500.00,
      "unrealized_pnl": 2500.00,
      "unrealized_pnl_pct": 16.7,
      "deduced_strategy": "buy_and_hold",
      "strategy_confidence": 0.85,
      "holding_days": 120.5,
      "position_type": "core",
      "risk_level": "moderate"
    },
    {
      "symbol": "TSLA",
      "quantity": 50,
      "market_value": 12500.00,
      "unrealized_pnl": 1200.00,
      "unrealized_pnl_pct": 10.6,
      "deduced_strategy": "momentum",
      "strategy_confidence": 0.72,
      "holding_days": 12.3,
      "position_type": "satellite",
      "risk_level": "high"
    }
  ],
  "strategy_mix": {
    "buy_and_hold": 0.50,
    "momentum": 0.30,
    "income": 0.15,
    "value": 0.05
  },
  "multi_leg_strategies": [
    {
      "strategy": "covered_call",
      "underlying": "GOOG",
      "legs": ["GOOG", "GOOG 260515C00200000"],
      "description": "Covered call on GOOG: the short call(s) (strike=200.0, expiry=260515) are backed by the long stock position. The short call risk is capped because the trader owns the underlying shares and can deliver them if assigned. This is an intentional income / exit strategy, not a naked risk."
    }
  ],
  "ai_narrative": "Your portfolio demonstrates a balanced core-satellite approach with 50% in long-term buy-and-hold positions and 30% in momentum plays. The allocation is well-diversified across strategies, though tech sector concentration at 45% warrants attention.",
  "ai_recommendations": [
    "Consider reducing momentum allocation from 30% to 20% to decrease portfolio volatility",
    "Tech sector exposure (45%) exceeds recommended 30% threshold - consider adding positions in other sectors",
    "TSLA position (momentum, 12.5% of portfolio) could benefit from a trailing stop at -8% to protect gains"
  ],
  "ai_risk_assessment": "Moderate risk profile with slight aggressive tilt due to momentum allocation. Well-positioned for continued bull market but vulnerable to sharp corrections.",
  "ai_strategy_mix": "Core-satellite structure: 50% defensive buy-and-hold core with 50% tactical satellite positions for alpha generation",
  "total_value": 35000.00,
  "position_count": 8,
  "timestamp": "2026-04-18T12:30:00Z"
}
```

**Field Descriptions:**

**Positions Enriched:**
Each position includes original fields plus:
- `deduced_strategy` - Inferred strategy type (`"momentum"`, `"buy_and_hold"`, `"mean_reversion"`, `"value"`, `"income"`, `"speculative"`, `"hedging"`, `"unknown"`)
- `strategy_confidence` - Confidence score for strategy classification (0.0-1.0)
- `holding_days` - Number of days position has been held
- `position_type` - `"core"` (long-term, large allocation) or `"satellite"` (tactical, smaller)
- `risk_level` - `"low"`, `"moderate"`, or `"high"` based on volatility and position size

**Strategy Mix:**
- Breakdown of portfolio by deduced strategy as % weights
- Helps understand overall portfolio approach (value vs. growth vs. momentum)

**Multi-Leg Strategies:**
- Array of detected multi-leg option strategies (covered calls, protective puts, collars)
- Each entry includes:
  - `strategy` - Type of multi-leg strategy detected
  - `underlying` - The underlying stock symbol
  - `legs` - Array of all position symbols that form this strategy
  - `description` - Detailed explanation of the strategy structure
- Important: Positions identified as part of multi-leg strategies are classified by their combined strategy (e.g., `covered_call`) rather than being evaluated in isolation
- Empty array `[]` when no multi-leg strategies are detected

**AI Fields (when `ai=true`):**
- `ai_narrative` - Natural language summary of portfolio composition and approach
- `ai_recommendations` - Array of actionable suggestions for improving portfolio
- `ai_risk_assessment` - Overall risk evaluation with context
- `ai_strategy_mix` - High-level description of portfolio strategy structure

**When AI Disabled (`ai=false`):**
- AI fields return `null`
- Strategy deduction still works (rule-based classification)
- Significantly faster response time

**Strategy Classification Logic:**

| Strategy | Detection Heuristics |
|----------|---------------------|
| `momentum` | Short-term holding (< 5 days) + positive P&L momentum |
| `mean_reversion` | Short-term (< 5 days) + negative entry momentum |
| `buy_and_hold` | Long-term holding (> 90 days) |
| `value` | Medium/long-term + favorable valuation (low P/E, P/B) |
| `income` | Dividend-paying stocks, income focus |
| `speculative` | High volatility, rapid position changes |
| `hedging` | Protective positions (puts, inverse ETFs) |
| `covered_call` | **NEW** Long stock + short call(s) on same underlying (income/exit strategy) |
| `protective_put` | **NEW** Long stock + long put(s) on same underlying (downside protection) |
| `collar` | **NEW** Long stock + short call + long put (capped upside and downside) |
| `unknown` | Insufficient data to classify |

**Use Cases:**

```javascript
// Get portfolio insights with AI
fetch('/api/account/portfolio-insights')
  .then(res => res.json())
  .then(data => {
    // Display strategy mix
    console.log('Strategy Mix:', data.strategy_mix);
    
    // Show AI recommendations
    data.ai_recommendations.forEach(rec => {
      console.log('💡', rec);
    });
    
    // Alert on high-risk positions
    data.positions_enriched
      .filter(p => p.risk_level === 'high')
      .forEach(p => console.warn(`⚠️ High risk: ${p.symbol}`));
  });

// Fast check without AI (for polling/monitoring)
fetch('/api/account/portfolio-insights?ai=false')
  .then(res => res.json())
  .then(data => {
    // Still get strategy deduction, just no AI narrative
    console.log(data.strategy_mix);
  });
```

**Dashboard Integration:**

**NEW in v1.7.1 (PR #18)** - AI narrative automatically displayed on main dashboard.

When you have open positions, the main dashboard automatically fetches and displays:
- **AI Portfolio Narrative**: Overview of your portfolio approach and composition
- **AI Recommendations**: Actionable suggestions for improvement

The narrative is loaded asynchronously from this endpoint and appears in a dedicated section below your positions list. If AI is disabled or unavailable, a message directs you to enable AI features in Settings.

### `GET /api/account/stock-deep-dive/<symbol>`

**NEW in v1.7 (PR #17)** - On-Demand Stock Analysis

Get comprehensive deep-dive analysis for a specific portfolio holding, combining fundamentals, technicals, and AI-powered insights.

**Path Parameters:**
- `symbol` - Stock ticker symbol (must be in current portfolio)

**Query Parameters:**
- `ai` (optional, default: `true`) - Enable/disable AI analysis
- `cache` (optional, default: `true`) - Use cached analysis if available (24-hour TTL)

**Response:**
```json
{
  "symbol": "AAPL",
  "position": {
    "symbol": "AAPL",
    "quantity": 100,
    "entry_price": 150.00,
    "current_price": 175.00,
    "market_value": 17500.00,
    "unrealized_pnl": 2500.00,
    "unrealized_pnl_pct": 16.7,
    "holding_days": 45.2,
    "portfolio_weight": 0.35
  },
  "fundamentals": {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "market_cap": 2800000000000,
    "pe_trailing": 28.5,
    "pe_forward": 25.3,
    "peg_ratio": 2.1,
    "price_to_book": 45.2,
    "dividend_yield": 0.0045,
    "profit_margin": 0.26,
    "roe": 1.47,
    "revenue_growth": 0.11,
    "analyst_target_mean": 185.00,
    "recommendation": "buy"
  },
  "technicals": {
    "current_price": 175.00,
    "sma_50": 168.50,
    "sma_200": 155.20,
    "rsi_14": 62.3,
    "weeks_52_high": 185.00,
    "weeks_52_low": 140.00,
    "distance_from_high_pct": -5.4,
    "distance_from_low_pct": 25.0
  },
  "ai_analysis": "AAPL demonstrates strong momentum with price trading above both 50-day (168.50) and 200-day (155.20) moving averages, indicating bullish trend structure. RSI at 62.3 shows healthy momentum without overbought conditions.\n\nValuation appears fair with forward P/E of 25.3 slightly below sector average. The stock has appreciated 16.7% since entry 45 days ago, approaching analyst consensus target of $185 (52-week high).\n\nRecommendation: Hold current position. Consider taking partial profits (25-30% of position) if price reaches $182-185 resistance zone. Set trailing stop at $165 (-5.7%) to protect gains. Strong fundamentals support continued holding for long-term investors.",
  "timestamp": "2026-04-18T12:45:00Z",
  "from_cache": false
}
```

**Error Response (symbol not in portfolio):**
```json
{
  "error": "MSFT is not in the current portfolio",
  "available_symbols": ["AAPL", "GOOG", "TSLA", "NVDA"]
}
```

**Field Descriptions:**

**Position:**
- Complete position data with portfolio context
- `portfolio_weight` - Position size as % of total portfolio value

**Fundamentals:**
- Company info (name, sector, industry)
- Valuation ratios (P/E, PEG, P/B, P/S)
- Profitability metrics (margins, ROE)
- Growth rates
- Analyst consensus and recommendations
- Fetched from yfinance, cached for 24 hours

**Technicals:**
- Moving averages (50-day, 200-day SMA)
- Momentum indicators (14-period RSI)
- 52-week range and distance from extremes
- Calculated from historical price data

**AI Analysis (when `ai=true`):**
- Comprehensive narrative combining all data points
- Trend analysis and momentum assessment
- Valuation commentary
- Specific entry/exit recommendations
- Risk management suggestions (stop loss, profit targets)

**Caching:**
- Analysis results cached for 24 hours
- `from_cache: true` indicates cached response
- Use `cache=false` to force fresh analysis
- Cache speeds up repeated requests (< 50ms vs. 2-3 seconds)

**Use Cases:**

```javascript
// Get fresh deep-dive analysis
fetch('/api/account/stock-deep-dive/AAPL')
  .then(res => res.json())
  .then(data => {
    console.log(`${data.symbol} Analysis:`);
    console.log(data.ai_analysis);
    
    // Check if overvalued
    if (data.fundamentals.pe_trailing > 30) {
      console.warn('High P/E - may be overvalued');
    }
    
    // Check technical strength
    const { current_price, sma_200 } = data.technicals;
    if (current_price > sma_200) {
      console.log('✅ Above 200-day MA - bullish trend');
    }
  });

// Fast cached lookup (for display refresh)
fetch('/api/account/stock-deep-dive/AAPL?cache=true')
  .then(res => res.json())
  .then(data => {
    if (data.from_cache) {
      console.log('Using cached analysis');
    }
  });

// Without AI for faster response
fetch('/api/account/stock-deep-dive/AAPL?ai=false')
  .then(res => res.json())
  .then(data => {
    // Still get fundamentals and technicals
    console.log(data.fundamentals);
    console.log(data.technicals);
  });
```

### `POST /api/account/portfolio-snapshot`

**NEW in v1.7 (PR #17)** - Save Portfolio Snapshot

Save the current portfolio state as a snapshot for historical tracking and analysis.

**Request Body:** None (uses current portfolio state)

**Response:**
```json
{
  "snapshot_id": 42,
  "snapshot_date": "2026-04-18T12:50:00Z",
  "position_count": 8,
  "total_value": 35000.00,
  "message": "Portfolio snapshot saved successfully"
}
```

**Use Case:**
```javascript
// Save daily snapshot
fetch('/api/account/portfolio-snapshot', { method: 'POST' })
  .then(res => res.json())
  .then(data => {
    console.log(`Snapshot #${data.snapshot_id} saved`);
    console.log(`Portfolio value: $${data.total_value.toFixed(2)}`);
  });

// Automated daily snapshot
setInterval(() => {
  fetch('/api/account/portfolio-snapshot', { method: 'POST' });
}, 24 * 60 * 60 * 1000);  // Once per day
```

**Stored Data:**
- All current positions with quantities, prices, P&L
- Account summary (equity, cash, buying power)
- Strategy analysis (if available)
- Timestamp for historical tracking

### `GET /api/account/portfolio-snapshots`

**NEW in v1.7 (PR #17)** - Retrieve Portfolio History

Get recent portfolio snapshots for historical analysis and tracking.

**Query Parameters:**
- `limit` (optional, default: `10`) - Maximum number of snapshots to return

**Response:**
```json
{
  "snapshots": [
    {
      "snapshot_id": 42,
      "snapshot_date": "2026-04-18T12:00:00Z",
      "position_count": 8,
      "total_value": 35000.00,
      "total_equity": 52000.00,
      "cash_balance": 17000.00
    },
    {
      "snapshot_id": 41,
      "snapshot_date": "2026-04-17T12:00:00Z",
      "position_count": 7,
      "total_value": 33500.00,
      "total_equity": 50500.00,
      "cash_balance": 17000.00
    }
  ],
  "count": 2
}
```

**Use Case:**
```javascript
// Get last 30 days of snapshots
fetch('/api/account/portfolio-snapshots?limit=30')
  .then(res => res.json())
  .then(data => {
    // Track portfolio value over time
    const values = data.snapshots.map(s => ({
      date: s.snapshot_date,
      value: s.total_value
    }));
    
    // Calculate growth
    const oldest = values[values.length - 1];
    const newest = values[0];
    const growth = ((newest.value - oldest.value) / oldest.value) * 100;
    console.log(`30-day growth: ${growth.toFixed(2)}%`);
  });
```

### `GET /api/account/stock-analysis-history/<symbol>`

**NEW in v1.7 (PR #17)** - Stock Analysis History

Get historical deep-dive analyses for a specific symbol to track how analysis/sentiment has evolved.

**Path Parameters:**
- `symbol` - Stock ticker symbol

**Query Parameters:**
- `limit` (optional, default: `5`) - Maximum number of historical analyses to return

**Response:**
```json
{
  "symbol": "AAPL",
  "history": [
    {
      "analysis_id": 15,
      "analysis_date": "2026-04-18T12:45:00Z",
      "ai_analysis": "AAPL demonstrates strong momentum...",
      "fundamentals_snapshot": {
        "pe_trailing": 28.5,
        "analyst_target_mean": 185.00
      },
      "technical_snapshot": {
        "current_price": 175.00,
        "rsi_14": 62.3
      }
    },
    {
      "analysis_id": 12,
      "analysis_date": "2026-04-10T14:30:00Z",
      "ai_analysis": "AAPL consolidating near $170...",
      "fundamentals_snapshot": {
        "pe_trailing": 29.1,
        "analyst_target_mean": 180.00
      },
      "technical_snapshot": {
        "current_price": 170.00,
        "rsi_14": 55.8
      }
    }
  ],
  "count": 2
}
```

**Use Case:**
```javascript
// Track how analysis has changed over time
fetch('/api/account/stock-analysis-history/AAPL?limit=10')
  .then(res => res.json())
  .then(data => {
    console.log(`${data.symbol} Analysis History:`);
    data.history.forEach(h => {
      console.log(`\n${h.analysis_date}:`);
      console.log(h.ai_analysis.substring(0, 200) + '...');
    });
    
    // Track price evolution
    const prices = data.history.map(h => 
      h.technical_snapshot.current_price
    );
    console.log('Price trend:', prices);
  });
```

---

## Orders API

### `GET /api/orders`

Get all orders (pending, filled, and cancelled).

**Response:**
```json
{
  "orders": [
    {
      "id": "ord_123",
      "symbol": "AAPL",
      "action": "BUY",
      "quantity": 100,
      "order_type": "LIMIT",
      "limit_price": 148.00,
      "status": "SUBMITTED",
      "filled_quantity": 0,
      "avg_fill_price": 0.00,
      "submitted_at": "2026-04-15T10:30:00Z"
    }
  ]
}
```

### `POST /api/orders`

Submit a new order.

**Request Body:**
```json
{
  "symbol": "AAPL",
  "action": "BUY",
  "quantity": 100,
  "order_type": "LIMIT",
  "limit_price": 148.00
}
```

**Response:**
```json
{
  "order_id": "ord_124",
  "status": "SUBMITTED"
}
```

### `DELETE /api/orders/{order_id}`

Cancel an order.

**Response:**
```json
{
  "status": "cancelled",
  "order_id": "ord_123"
}
```

---

## Data API

### `GET /api/data/market/{symbol}`

Get current market data for a symbol.

**Response:**
```json
{
  "symbol": "AAPL",
  "last_price": 150.25,
  "bid": 150.20,
  "ask": 150.30,
  "volume": 45000000,
  "timestamp": "2026-04-15T15:45:00Z"
}
```

### `GET /api/data/historical/{symbol}`

Get historical bars.

**Query Parameters:**
- `period` - Time period (e.g., "1d", "5d", "1mo")
- `interval` - Bar interval (e.g., "1m", "5m", "1h", "1d")

**Response:**
```json
{
  "symbol": "AAPL",
  "bars": [
    {
      "timestamp": "2026-04-15T09:30:00Z",
      "open": 149.50,
      "high": 150.75,
      "low": 149.25,
      "close": 150.25,
      "volume": 1250000
    }
  ]
}
```

---

## Market Data API

### `GET /api/market/overview`

Get latest global market overview with index snapshots.

**Description:**
Returns real-time data for major market indices (S&P 500, Dow, Nasdaq, VIX, FTSE, DAX, Nikkei, etc.) with 5-minute caching. Automatically triggers background refresh when data is stale.

**Response:**
```json
{
  "snapshots": [
    {
      "symbol": "^GSPC",
      "name": "S&P 500",
      "region": "US",
      "price": 5234.18,
      "change": 12.45,
      "change_pct": 0.24,
      "day_high": 5245.67,
      "day_low": 5220.34,
      "prev_close": 5221.73,
      "volume": null,
      "timestamp": "2026-04-17T14:30:00+00:00",
      "market_date": "2026-04-17"
    },
    {
      "symbol": "^VIX",
      "name": "VIX",
      "region": "US",
      "price": 15.23,
      "change": -0.45,
      "change_pct": -2.87,
      "day_high": 15.89,
      "day_low": 15.10,
      "prev_close": 15.68,
      "volume": null,
      "timestamp": "2026-04-17T14:30:00+00:00",
      "market_date": "2026-04-17"
    }
  ],
  "sparklines": {
    "^GSPC": [5180.23, 5195.67, 5210.45, 5220.12, 5234.18],
    "^VIX": [16.45, 15.89, 15.67, 15.34, 15.23]
  },
  "market_status": {
    "US": "open",
    "Europe": "closed",
    "Asia": "closed"
  },
  "last_updated": "2026-04-17T14:30:00+00:00"
}
```

**Response Fields:**
- `snapshots` - Array of index snapshots with latest prices
  - `symbol` - Index ticker symbol (e.g., "^GSPC", "^DJI")
  - `name` - Display name (e.g., "S&P 500")
  - `region` - Market region: "US", "Europe", or "Asia"
  - `price` - Current/latest price
  - `change` - Absolute price change from previous close
  - `change_pct` - Percentage change from previous close
  - `day_high` - Day's high price
  - `day_low` - Day's low price
  - `prev_close` - Previous close price
  - `volume` - Trading volume (often null for indices)
  - `timestamp` - When this snapshot was captured
  - `market_date` - Market date for this data
- `sparklines` - Historical prices for 5-day trend visualization (symbol → array of closes)
- `market_status` - Current market open/closed status by region
- `last_updated` - Timestamp of most recent data refresh

**Tracked Indices:**
- **US:** S&P 500 (^GSPC), Dow Jones (^DJI), Nasdaq (^IXIC), Russell 2000 (^RUT), VIX (^VIX)
- **Europe:** FTSE 100 (^FTSE), DAX (^GDAXI), Euro Stoxx 50 (^STOXX50E), CAC 40 (^FCHI)
- **Asia:** Nikkei 225 (^N225), Hang Seng (^HSI), Shanghai Composite (000001.SS), KOSPI (^KS11), ASX 200 (^AXJO)

**Caching:**
Data is cached for 5 minutes. When stale, a background refresh is triggered automatically so subsequent requests receive fresh data.

### `POST /api/market/refresh`

Manually trigger market data refresh from Yahoo Finance.

**Description:**
Synchronous call that fetches fresh data immediately and returns the updated overview. Use this when you need guaranteed fresh data without waiting for the auto-refresh cycle.

**Response:**
Same format as `GET /api/market/overview`

**Note:** This endpoint blocks until the fetch completes (typically 2-5 seconds).

---

## Strategies API

### `GET /api/strategies/`

List all active strategies.

**Response:**
```json
{
  "strategies": [
    {
      "id": "strat_1",
      "name": "Bollinger Bands",
      "status": "RUNNING",
      "symbols": ["AAPL", "MSFT"],
      "positions_count": 2,
      "daily_pnl": 1250.00,
      "started_at": "2026-04-15T09:00:00Z"
    }
  ]
}
```

### `POST /api/strategies/`

Start a new strategy.

**Request Body:**
```json
{
  "name": "My Strategy",
  "strategy_type": "bollinger_bands",
  "symbols": ["AAPL", "MSFT", "GOOGL"],
  "parameters": {
    "period": 20,
    "std_dev": 2.0
  }
}
```

**Response:**
```json
{
  "strategy_id": "strat_2",
  "status": "RUNNING"
}
```

### `DELETE /api/strategies/{strategy_id}`

Stop a strategy.

**Response:**
```json
{
  "status": "stopped",
  "strategy_id": "strat_1"
}
```

### `GET /api/strategies/{strategy_id}/performance`

Get strategy performance metrics.

**Response:**
```json
{
  "strategy_id": "strat_1",
  "total_pnl": 5250.00,
  "total_return_pct": 5.25,
  "sharpe_ratio": 1.85,
  "max_drawdown": -2.5,
  "win_rate": 0.65,
  "trades_count": 45,
  "avg_trade_pnl": 116.67
}
```

### `GET /api/strategies/inferred`

**Auto-detect trading strategies from current positions.**

Analyzes your active positions and identifies potential trading strategies:
- Long/short equity positions
- Covered calls and protective puts
- Bull/bear call/put spreads
- Iron condors, straddles, strangles
- Multi-leg option strategies

Each inferred strategy includes profit targets, stop losses, and confidence scores.

**Response:**
```json
{
  "inferred": [
    {
      "id": "inferred_AAPL_covered_call_1",
      "strategy_type": "CoveredCall",
      "description": "Covered call on AAPL: Long 100 shares, Short 1x 200C",
      "confidence": 0.95,
      "symbols": ["AAPL"],
      "positions": [
        {
          "symbol": "AAPL",
          "quantity": 100,
          "side": "LONG",
          "sec_type": "STK"
        },
        {
          "symbol": "AAPL250620C200",
          "quantity": -1,
          "side": "SHORT",
          "sec_type": "OPT"
        }
      ],
      "targets": {
        "profit_target_price": 200.0,
        "max_profit": 5000.0,
        "trailing_stop_pct": 0.05
      }
    },
    {
      "id": "inferred_SPY_iron_condor_1",
      "strategy_type": "IronCondor",
      "description": "Iron condor on SPY",
      "confidence": 0.90,
      "symbols": ["SPY"],
      "positions": [
        {"symbol": "SPY250620C450", "quantity": -1, "side": "SHORT"},
        {"symbol": "SPY250620C460", "quantity": 1, "side": "LONG"},
        {"symbol": "SPY250620P400", "quantity": -1, "side": "SHORT"},
        {"symbol": "SPY250620P390", "quantity": 1, "side": "LONG"}
      ],
      "targets": {
        "max_profit": 600.0,
        "max_loss": 400.0
      }
    }
  ]
}
```

**Field Descriptions:**

- `id` - Unique identifier for this inferred strategy (used for dismissing)
- `strategy_type` - Detected strategy pattern:
  - Equity: `LongEquity`, `ShortEquity`
  - Covered strategies: `CoveredCall`, `ProtectivePut`
  - Spreads: `BullCallSpread`, `BearPutSpread`, `BullPutSpread`, `BearCallSpread`
  - Complex: `IronCondor`, `Straddle`, `Strangle`
  - Options: `LongCall`, `ShortCall`, `LongPut`, `ShortPut`, `LongOption`, `ShortOption`
- `description` - Human-readable description of the strategy
- `confidence` - Detection confidence (0.0 to 1.0, where 1.0 = certain match)
- `symbols` - List of underlying symbols involved
- `positions` - Array of positions that make up this strategy
- `targets` - Profit targets, stop losses, and risk metrics:
  - `profit_target_price` - Target exit price (for equity/covered calls)
  - `stop_loss_price` - Stop loss price (for equity/protective puts)
  - `trailing_stop_pct` - Trailing stop percentage (e.g., 0.05 = 5%)
  - `max_profit` - Maximum theoretical profit (for defined-risk strategies)
  - `max_loss` - Maximum theoretical loss (for defined-risk strategies)
  - `spread_width` - Width between strikes (for spreads)

**Use Cases:**

1. **Portfolio Visualization:**
   ```javascript
   // Display detected strategies in dashboard
   fetch('/api/strategies/inferred')
     .then(res => res.json())
     .then(data => {
       data.inferred.forEach(strategy => {
         console.log(`Found: ${strategy.strategy_type} on ${strategy.symbols.join(', ')}`);
         console.log(`Confidence: ${(strategy.confidence * 100).toFixed(0)}%`);
       });
     });
   ```

2. **Risk Management:**
   ```javascript
   // Check for undefined-risk positions
   const riskyStrategies = data.inferred.filter(s => 
     s.strategy_type === 'ShortCall' && !s.targets.max_loss
   );
   if (riskyStrategies.length > 0) {
     alert('⚠️ You have naked short calls with unlimited risk!');
   }
   ```

### `POST /api/strategies/inferred/{inferred_id}/dismiss`

Dismiss an auto-detected strategy so it no longer appears in the list.

Useful for hiding strategies you've reviewed and don't want to see again.

**Path Parameters:**
- `inferred_id` - The ID from the inferred strategy (e.g., `"inferred_AAPL_covered_call_1"`)

**Response:**
```json
{
  "status": "dismissed",
  "id": "inferred_AAPL_covered_call_1"
}
```

**Error Responses:**
- `404 Not Found` - Inferred strategy ID not found in current positions

**Example:**
```javascript
// Dismiss a strategy the user has already reviewed
fetch('/api/strategies/inferred/inferred_AAPL_covered_call_1/dismiss', {
  method: 'POST'
})
.then(res => res.json())
.then(data => console.log(`Dismissed: ${data.id}`));
```

### `POST /api/strategies/inferred/reset`

Reset all dismissed inferred strategies.

Clears the dismissed list so all detected strategies will appear again.

**Response:**
```json
{
  "status": "reset"
}
```

**Example:**
```javascript
// Clear all dismissed strategies
fetch('/api/strategies/inferred/reset', {
  method: 'POST'
})
.then(res => res.json())
.then(() => {
  // Refresh the inferred strategies list
  window.location.reload();
});
```

---

## Backtest API

### `POST /api/backtest/run`

Run a backtest.

**Request Body:**
```json
{
  "strategy_name": "Bollinger Bands",
  "strategy_type": "bollinger_bands",
  "symbols": ["AAPL", "MSFT"],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "initial_capital": 100000.00,
  "parameters": {
    "period": 20,
    "std_dev": 2.0
  }
}
```

**Response:**
```json
{
  "run_id": "bt_123",
  "status": "queued"
}
```

### `GET /api/backtest/runs`

List all backtest runs.

**Response:**
```json
{
  "runs": [
    {
      "run_id": "bt_123",
      "strategy_name": "Bollinger Bands",
      "status": "complete",
      "created": "2026-04-15T10:00:00Z",
      "completed": "2026-04-15T10:05:23Z",
      "final_equity": 112500.00,
      "total_return": 12.5
    }
  ]
}
```

### `GET /api/backtest/runs/{run_id}`

Get backtest results.

**Response:**
```json
{
  "run_id": "bt_123",
  "status": "complete",
  "strategy_name": "Bollinger Bands",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "initial_capital": 100000.00,
  "final_equity": 112500.00,
  "total_return": 12.5,
  "sharpe_ratio": 1.92,
  "max_drawdown": -8.5,
  "trades": [
    {
      "date": "2025-01-15",
      "symbol": "AAPL",
      "action": "BUY",
      "quantity": 100,
      "price": 145.00
    }
  ],
  "daily_equity": [
    {"date": "2025-01-01", "equity": 100000.00},
    {"date": "2025-01-02", "equity": 100250.00}
  ]
}
```

---

## Emergency Controls API

### `POST /api/emergency/stop`

Emergency stop all strategies.

**Response:**
```json
{
  "status": "all_strategies_stopped",
  "strategies_stopped": 3,
  "timestamp": "2026-04-15T15:45:00Z"
}
```

### `POST /api/emergency/liquidate`

Liquidate all positions immediately.

**Response:**
```json
{
  "status": "liquidation_initiated",
  "positions_closed": 5,
  "timestamp": "2026-04-15T15:45:00Z"
}
```

### `POST /api/emergency/pause`

Pause all trading (stop entries, keep positions).

**Response:**
```json
{
  "status": "trading_paused",
  "timestamp": "2026-04-15T15:45:00Z"
}
```

### `POST /api/emergency/resume`

Resume normal trading.

**Response:**
```json
{
  "status": "trading_resumed",
  "timestamp": "2026-04-15T15:45:00Z"
}
```

---

## Events & Monitoring API

### `GET /api/events/stream`

Server-Sent Events (SSE) endpoint for real-time updates.

**Event Types:**
- `account_update` - Account balance/equity changes
- `portfolio_update` - Position changes
- `order_update` - Order status changes
- `trade_execution` - Trade fills
- `strategy_update` - Strategy status changes
- `alert` - Risk alerts and notifications
- `connection_lost` - TWS connection lost
- `connection_established` - TWS connection established

**Response (SSE Stream):**
```
event: account_update
data: {"equity": 105250.00, "daily_pnl": 1250.00}

event: trade_execution
data: {"symbol": "AAPL", "action": "BUY", "quantity": 100, "price": 150.25}
```

### `GET /api/events/alerts`

Get recent alerts.

**Response:**
```json
{
  "alerts": [
    {
      "id": "alert_1",
      "level": "WARNING",
      "type": "RISK_LIMIT",
      "message": "Daily loss limit approaching: -1.8%",
      "timestamp": "2026-04-15T14:30:00Z",
      "dismissed": false
    }
  ]
}
```

### `DELETE /api/events/alerts/{alert_id}`

Dismiss an alert.

**Response:**
```json
{
  "status": "dismissed",
  "alert_id": "alert_1"
}
```

---

## System API

### `GET /api/system/health`

Get system health status.

**Response:**
```json
{
  "status": "ok",
  "uptime_seconds": 86400,
  "connected": true,
  "strategies_running": 3,
  "last_heartbeat": "2026-04-15T15:45:00Z"
}
```

### `GET /api/system/config`

Get system configuration.

**Response:**
```json
{
  "environment": "paper",
  "max_positions": 10,
  "max_position_size_pct": 10.0,
  "daily_loss_limit_pct": 2.0,
  "risk_controls_enabled": true
}
```

---

## AI Assistant APIs

### `POST /ai/chat`

Send a message to the AI trading assistant.

**Request Body:**
```json
{
  "message": "What's the current performance of my portfolio?",
  "context": {
    "positions": { ... },
    "account_summary": { ... }
  }
}
```

**Response:**
```json
{
  "response": "Your portfolio is up $2,500 today (2.43%). You have 5 open positions...",
  "suggestions": [
    "Consider taking profits on AAPL (+8.5%)",
    "TSLA approaching support level"
  ]
}
```

### `POST /ai/strategy/suggest-params`

Get AI-suggested strategy parameters.

**Request Body:**
```json
{
  "strategy_type": "bollinger_bands",
  "symbols": ["AAPL", "MSFT"],
  "risk_profile": "moderate"
}
```

**Response:**
```json
{
  "suggested_params": {
    "period": 20,
    "std_dev": 2.0,
    "position_size_pct": 5.0
  },
  "reasoning": "Based on recent volatility patterns..."
}
```

### `POST /ai/strategy/explain-signal`

Get AI explanation of a trading signal.

**Request Body:**
```json
{
  "symbol": "AAPL",
  "signal_type": "BUY",
  "indicators": {
    "price": 150.25,
    "bb_upper": 152.00,
    "bb_lower": 148.00
  }
}
```

**Response:**
```json
{
  "explanation": "Price touched lower Bollinger Band at $148, indicating oversold condition...",
  "confidence": "HIGH",
  "risk_factors": [
    "Market volatility elevated",
    "Earnings announcement in 3 days"
  ]
}
```

---

## TWSBridge Module

The `TWSBridge` class manages the connection between the web application and Interactive Brokers TWS/Gateway API.

### Usage Example

```python
from core.tws_bridge import TWSBridge
from web.services import ServiceManager

# Initialize service manager
service_manager = ServiceManager()

# Configure connection
config = {
    "host": "127.0.0.1",
    "port": 7497,
    "client_id": 1,
    "account": "DU12345"
}

# Create and connect bridge
bridge = TWSBridge(service_manager, config)
connected = bridge.connect(timeout=10)

if connected:
    print(f"Connected to TWS: {bridge.is_connected}")
    # Bridge automatically forwards:
    # - Account updates → service_manager.update_account_summary()
    # - Portfolio updates → service_manager.update_position()
    # - Events → service_manager.event_bus.publish()
```

### Key Features

- **Automatic Data Forwarding**: Forwards TWS callbacks to ServiceManager
- **Connection Management**: Handles connect/disconnect with timeout
- **Account Updates**: Real-time equity, cash, buying power
- **Portfolio Updates**: Position changes, P&L tracking
- **Event Publishing**: Publishes events to EventBus for real-time monitoring
- **Error Handling**: Graceful handling of connection errors

### ServiceManager Integration

The ServiceManager acts as the central hub for the web dashboard:

```python
from web.services import get_services

# Get singleton instance
services = get_services()

# Connection state
services.connected  # bool
services.connection_env  # "paper" or "live"
services.connection_info  # dict with host, port, etc.

# Account data
services.get_account_summary()  # equity, cash, buying power
services.get_positions()  # dict of positions by symbol
services.get_orders()  # list of orders

# Alerts
services.get_alerts()  # list of alerts
services.add_alert(alert_dict)
services.dismiss_alert(alert_id)

# TWS connection
services.connect_tws(env, config, timeout=10)
services.disconnect_tws()

# Backtest management
services.store_backtest_run(run_id, data)
services.list_backtest_runs()
services.get_backtest_run(run_id)
```

---

## Error Handling

All API endpoints follow consistent error response format:

```json
{
  "error": "Description of the error",
  "code": "ERROR_CODE",
  "details": { ... }
}
```

**Common HTTP Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid request parameters
- `404 Not Found` - Resource not found
- `409 Conflict` - Operation conflict (e.g., already connected)
- `500 Internal Server Error` - Server error

---

## Rate Limiting

API endpoints are designed for dashboard usage and have reasonable rate limits:

- Connection operations: 10 requests/minute
- Data queries: 100 requests/minute
- Order submissions: 60 requests/minute
- Event stream: No limit (SSE)

---

## WebSocket Events

For real-time updates, connect to the SSE endpoint:

```javascript
const eventSource = new EventSource('/api/events/stream');

eventSource.addEventListener('account_update', (event) => {
  const data = JSON.parse(event.data);
  console.log('Account updated:', data);
});

eventSource.addEventListener('trade_execution', (event) => {
  const data = JSON.parse(event.data);
  console.log('Trade executed:', data);
});
```

---

## Testing

All API endpoints are thoroughly tested. See [tests/test_web_api.py](../tests/test_web_api.py) for comprehensive test coverage.

Run web API tests:
```bash
pytest tests/test_web_api.py -v
```

---

## See Also

- [API Reference](API_REFERENCE.md) - Python API for strategy development
- [User Guide](USER_GUIDE.md) - Dashboard usage guide
- [Deployment Guide](DEPLOYMENT_GUIDE.md) - Production deployment
