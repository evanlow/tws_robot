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
