# TWS Robot v2.0 - Technical Design Document
## Detailed Implementation Specifications

**Document Version:** 1.0  
**Last Updated:** November 13, 2025  
**Technical Owner:** Development Team  

---

## 🏛️ System Architecture Deep Dive

### **Core Design Principles**
1. **Event-Driven Architecture**: All components communicate via events
2. **Microservices Pattern**: Loosely coupled, independently deployable modules
3. **SOLID Principles**: Single responsibility, open/closed, dependency inversion
4. **Domain-Driven Design**: Clear boundaries between trading, risk, and analytics
5. **Fail-Fast Philosophy**: Early error detection with graceful degradation

### **Event Bus Architecture**
```python
# Central event system for decoupled communication
class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)
        self._middleware = []
    
    def subscribe(self, event_type: str, handler: Callable):
        """Register event handler"""
        self._handlers[event_type].append(handler)
    
    def publish(self, event: Event):
        """Distribute event to all subscribers"""
        for middleware in self._middleware:
            event = middleware(event)
        
        for handler in self._handlers[event.type]:
            try:
                handler(event)
            except Exception as e:
                self.publish(ErrorEvent(
                    error=e, 
                    source_event=event,
                    timestamp=datetime.now()
                ))
```

### **Event Types**
```python
@dataclass
class MarketDataEvent(Event):
    symbol: str
    price: float
    volume: int
    timestamp: datetime

@dataclass
class SignalEvent(Event):
    strategy_id: str
    symbol: str
    signal_type: str  # BUY/SELL/HOLD
    confidence: float
    metadata: dict

@dataclass
class TradeEvent(Event):
    order_id: str
    symbol: str
    quantity: int
    price: float
    side: str
    status: str  # FILLED/PARTIAL/CANCELLED

@dataclass
class RiskEvent(Event):
    risk_type: str  # POSITION_LIMIT/DRAWDOWN/CORRELATION
    severity: str   # WARNING/CRITICAL
    action: str     # REDUCE/STOP/ALERT
    details: dict
```

---

## 📊 Database Design & Data Flow

### **Complete Database Schema**
```sql
-- Strategy Management
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    class_name VARCHAR(100) NOT NULL,
    config JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'INACTIVE',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50),
    CONSTRAINT valid_status CHECK (status IN ('ACTIVE', 'INACTIVE', 'PAUSED', 'ERROR'))
);

-- Trade Execution
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    strategy_id INTEGER REFERENCES strategies(id),
    symbol VARCHAR(20) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL,
    quantity INTEGER NOT NULL,
    price DECIMAL(10,4),
    stop_price DECIMAL(10,4),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    parent_order_id VARCHAR(50),
    CONSTRAINT valid_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT valid_status CHECK (status IN ('PENDING', 'SUBMITTED', 'FILLED', 'CANCELLED', 'REJECTED'))
);

CREATE TABLE fills (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) REFERENCES orders(order_id),
    fill_id VARCHAR(50) UNIQUE NOT NULL,
    quantity INTEGER NOT NULL,
    price DECIMAL(10,4) NOT NULL,
    commission DECIMAL(8,4) NOT NULL,
    filled_at TIMESTAMP DEFAULT NOW(),
    execution_venue VARCHAR(20)
);

-- Portfolio Tracking
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    avg_cost DECIMAL(10,4) NOT NULL,
    unrealized_pnl DECIMAL(15,2),
    realized_pnl DECIMAL(15,2),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol)
);

CREATE TABLE portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    total_value DECIMAL(15,2) NOT NULL,
    cash DECIMAL(15,2) NOT NULL,
    margin_used DECIMAL(15,2),
    day_pnl DECIMAL(15,2),
    unrealized_pnl DECIMAL(15,2),
    positions JSONB,
    risk_metrics JSONB
);

-- Performance Analytics
CREATE TABLE strategy_performance (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER REFERENCES strategies(id),
    date DATE NOT NULL,
    total_pnl DECIMAL(15,2),
    trade_count INTEGER DEFAULT 0,
    win_rate DECIMAL(5,4),
    sharpe_ratio DECIMAL(8,4),
    sortino_ratio DECIMAL(8,4),
    max_drawdown DECIMAL(8,4),
    calmar_ratio DECIMAL(8,4),
    volatility DECIMAL(8,4),
    UNIQUE(strategy_id, date)
);

-- Risk Management
CREATE TABLE risk_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    symbol VARCHAR(20),
    strategy_id INTEGER REFERENCES strategies(id),
    description TEXT,
    action_taken VARCHAR(100),
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_severity CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL'))
);

-- Market Data
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open_price DECIMAL(10,4),
    high_price DECIMAL(10,4),
    low_price DECIMAL(10,4),
    close_price DECIMAL(10,4),
    volume BIGINT,
    vwap DECIMAL(10,4),
    UNIQUE(symbol, timestamp)
);

-- System Configuration
CREATE TABLE system_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(50)
);

-- Audit Trail
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation VARCHAR(10) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by VARCHAR(50),
    changed_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_operation CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE'))
);

-- Indexes for Performance
CREATE INDEX idx_orders_strategy_symbol ON orders(strategy_id, symbol);
CREATE INDEX idx_orders_status_created ON orders(status, created_at);
CREATE INDEX idx_fills_order_time ON fills(order_id, filled_at);
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_portfolio_timestamp ON portfolio_snapshots(timestamp);
CREATE INDEX idx_performance_strategy_date ON strategy_performance(strategy_id, date);
CREATE INDEX idx_risk_events_type_time ON risk_events(event_type, created_at);
CREATE INDEX idx_market_data_symbol_time ON market_data(symbol, timestamp);
```

### **Data Migration Strategy**
```python
# Migration script from current system to v2.0
class LegacyDataMigrator:
    def __init__(self, legacy_data_path: str, new_db_connection: str):
        self.legacy_path = legacy_data_path
        self.db = DatabaseManager(new_db_connection)
    
    def migrate_portfolio_data(self):
        """Migrate existing portfolio positions"""
        # Read current positions from tws_client.py output
        # Create initial position records
        # Set up baseline portfolio snapshot
    
    def migrate_configuration(self):
        """Migrate .env and config files to database"""
        # Convert .env files to system_config table
        # Migrate strategy parameters
        # Set up risk limits
    
    def create_initial_strategy(self):
        """Create strategy record for existing Bollinger Bands"""
        # Register existing trading logic as strategy
        # Set up parameters and configuration
        # Mark as active if currently running
```

---

## 🎯 Strategy Framework Implementation

### **Base Strategy Class**
```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass
class Signal:
    symbol: str
    signal_type: SignalType
    confidence: float  # 0.0 to 1.0
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = None

class BaseStrategy(ABC):
    def __init__(self, config: Dict[str, Any], event_bus: EventBus):
        self.config = config
        self.event_bus = event_bus
        self.positions = {}
        self.market_data = {}
        self.is_active = False
        
        # Subscribe to relevant events
        self.event_bus.subscribe('market_data', self.on_market_data)
        self.event_bus.subscribe('trade_filled', self.on_trade_filled)
        self.event_bus.subscribe('risk_event', self.on_risk_event)
    
    @abstractmethod
    def generate_signals(self) -> List[Signal]:
        """Generate trading signals based on current market data"""
        pass
    
    @abstractmethod
    def on_market_data(self, event: MarketDataEvent):
        """Handle incoming market data"""
        pass
    
    def on_trade_filled(self, event: TradeEvent):
        """Handle trade execution confirmation"""
        if event.order_id in self.pending_orders:
            # Update position tracking
            self.update_position(event)
            self.pending_orders.remove(event.order_id)
    
    def on_risk_event(self, event: RiskEvent):
        """Handle risk management events"""
        if event.severity == 'CRITICAL':
            self.emergency_stop()
    
    def update_config(self, new_config: Dict[str, Any]):
        """Hot-reload strategy parameters"""
        self.config.update(new_config)
        self.on_config_updated()
    
    @abstractmethod
    def on_config_updated(self):
        """Handle configuration changes"""
        pass
    
    def emergency_stop(self):
        """Emergency stop - close all positions"""
        self.is_active = False
        for symbol, position in self.positions.items():
            if position.quantity != 0:
                self.event_bus.publish(
                    OrderEvent(
                        symbol=symbol,
                        side='SELL' if position.quantity > 0 else 'BUY',
                        quantity=abs(position.quantity),
                        order_type='MARKET',
                        urgency='EMERGENCY'
                    )
                )
```

### **Advanced Strategy Implementation**
```python
class MeanReversionStrategy(BaseStrategy):
    def __init__(self, config: Dict[str, Any], event_bus: EventBus):
        super().__init__(config, event_bus)
        
        # Strategy-specific parameters
        self.lookback_period = config.get('lookback_period', 20)
        self.std_dev_threshold = config.get('std_dev_threshold', 2.0)
        self.position_size = config.get('position_size', 0.02)  # 2% of portfolio
        
        # Technical indicators
        self.price_history = defaultdict(deque)
        self.bollinger_bands = {}
    
    def generate_signals(self) -> List[Signal]:
        signals = []
        
        for symbol, prices in self.price_history.items():
            if len(prices) < self.lookback_period:
                continue
            
            # Calculate Bollinger Bands
            prices_array = np.array(prices)
            sma = np.mean(prices_array)
            std_dev = np.std(prices_array)
            
            upper_band = sma + (self.std_dev_threshold * std_dev)
            lower_band = sma - (self.std_dev_threshold * std_dev)
            current_price = prices[-1]
            
            self.bollinger_bands[symbol] = {
                'sma': sma,
                'upper': upper_band,
                'lower': lower_band,
                'current': current_price
            }
            
            # Generate signals
            if current_price <= lower_band:
                # Oversold - potential buy signal
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    confidence=min((lower_band - current_price) / std_dev, 1.0),
                    price_target=sma,
                    stop_loss=current_price * 0.98,
                    metadata={
                        'entry_reason': 'oversold',
                        'bollinger_position': 'below_lower_band',
                        'std_dev_distance': (lower_band - current_price) / std_dev
                    }
                ))
            
            elif current_price >= upper_band:
                # Overbought - potential sell signal
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    confidence=min((current_price - upper_band) / std_dev, 1.0),
                    price_target=sma,
                    stop_loss=current_price * 1.02,
                    metadata={
                        'entry_reason': 'overbought',
                        'bollinger_position': 'above_upper_band',
                        'std_dev_distance': (current_price - upper_band) / std_dev
                    }
                ))
        
        return signals
    
    def on_market_data(self, event: MarketDataEvent):
        # Update price history
        self.price_history[event.symbol].append(event.price)
        
        # Maintain lookback window
        if len(self.price_history[event.symbol]) > self.lookback_period:
            self.price_history[event.symbol].popleft()
        
        # Store current market data
        self.market_data[event.symbol] = event
        
        # Generate signals if we have enough data
        if len(self.price_history[event.symbol]) >= self.lookback_period:
            signals = self.generate_signals()
            for signal in signals:
                self.event_bus.publish(SignalEvent(
                    strategy_id=self.config['id'],
                    symbol=signal.symbol,
                    signal_type=signal.signal_type.value,
                    confidence=signal.confidence,
                    metadata=signal.metadata
                ))
    
    def on_config_updated(self):
        """Handle parameter updates"""
        self.lookback_period = self.config.get('lookback_period', 20)
        self.std_dev_threshold = self.config.get('std_dev_threshold', 2.0)
        self.position_size = self.config.get('position_size', 0.02)
        
        # Clear history to rebuild with new parameters
        self.price_history.clear()
        self.bollinger_bands.clear()
```

---

## ⚡ Performance & Monitoring

### **Real-Time Performance Metrics**
```python
class PerformanceCalculator:
    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate
        self.returns_cache = defaultdict(deque)
        
    def calculate_sharpe_ratio(self, returns: List[float], 
                              period: str = 'daily') -> float:
        """Calculate annualized Sharpe ratio"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = [r - (self.risk_free_rate / 252) for r in returns]
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns)
        
        if std_excess == 0:
            return 0.0
        
        # Annualize based on period
        periods_per_year = {'daily': 252, 'hourly': 252*6.5, 'minute': 252*6.5*60}
        scaling_factor = np.sqrt(periods_per_year.get(period, 252))
        
        return (mean_excess / std_excess) * scaling_factor
    
    def calculate_sortino_ratio(self, returns: List[float]) -> float:
        """Calculate Sortino ratio (downside deviation)"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = [r - (self.risk_free_rate / 252) for r in returns]
        downside_returns = [min(0, r) for r in excess_returns]
        
        mean_excess = np.mean(excess_returns)
        downside_dev = np.std(downside_returns)
        
        if downside_dev == 0:
            return float('inf') if mean_excess > 0 else 0.0
        
        return (mean_excess / downside_dev) * np.sqrt(252)
    
    def calculate_max_drawdown(self, portfolio_values: List[float]) -> float:
        """Calculate maximum drawdown"""
        if len(portfolio_values) < 2:
            return 0.0
        
        peak = portfolio_values[0]
        max_dd = 0.0
        
        for value in portfolio_values[1:]:
            if value > peak:
                peak = value
            else:
                drawdown = (peak - value) / peak
                max_dd = max(max_dd, drawdown)
        
        return max_dd
    
    def calculate_calmar_ratio(self, returns: List[float], 
                              portfolio_values: List[float]) -> float:
        """Calculate Calmar ratio (annual return / max drawdown)"""
        if len(returns) < 252:  # Need at least 1 year of data
            return 0.0
        
        annual_return = np.mean(returns) * 252
        max_dd = self.calculate_max_drawdown(portfolio_values)
        
        if max_dd == 0:
            return float('inf') if annual_return > 0 else 0.0
        
        return annual_return / max_dd
```

### **Real-Time Monitoring Dashboard**
```python
# FastAPI endpoints for real-time data
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, data: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(data))
            except Exception:
                # Handle disconnected clients
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.websocket("/ws/portfolio")
async def websocket_portfolio(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Real-time portfolio updates
            portfolio_data = {
                'total_value': get_current_portfolio_value(),
                'day_pnl': get_daily_pnl(),
                'positions': get_current_positions(),
                'risk_metrics': calculate_risk_metrics(),
                'timestamp': datetime.now().isoformat()
            }
            await websocket.send_text(json.dumps(portfolio_data))
            await asyncio.sleep(1)  # Update every second
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/strategies/{strategy_id}/performance")
async def get_strategy_performance(strategy_id: int):
    """Get detailed strategy performance metrics"""
    performance_data = {
        'strategy_id': strategy_id,
        'total_trades': get_trade_count(strategy_id),
        'win_rate': calculate_win_rate(strategy_id),
        'sharpe_ratio': calculate_sharpe_ratio(strategy_id),
        'sortino_ratio': calculate_sortino_ratio(strategy_id),
        'max_drawdown': calculate_max_drawdown(strategy_id),
        'calmar_ratio': calculate_calmar_ratio(strategy_id),
        'current_positions': get_strategy_positions(strategy_id),
        'recent_trades': get_recent_trades(strategy_id, limit=20)
    }
    return performance_data
```

---

This technical specification provides the detailed implementation roadmap for each component. The modular architecture ensures scalability while the comprehensive testing and monitoring systems provide production-grade reliability.

Would you like me to create specific implementation files for any of these components, or shall I develop the deployment and DevOps documentation next?