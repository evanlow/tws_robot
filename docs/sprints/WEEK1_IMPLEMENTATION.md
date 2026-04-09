# TWS Robot v2.0 - Week 1 Implementation Guide
## Foundation & Core Infrastructure Setup

**Sprint Goal:** Establish modular architecture and core components  
**Duration:** Week 1 of 7-week project  
**Focus:** Migration from monolithic to modular design  
**Last Updated:** November 17, 2025

---

## ⚠️ PROGRESS UPDATE (November 17, 2025)

### **Current Status: 60% Complete** ✅

We have made significant progress on Week 1 objectives with several core modules already implemented and working. The remaining work focuses on architectural refactoring and database integration.

### ✅ **Completed Components:**

1. **✅ Enhanced TWS Connection** (`enhanced_connection.py`)
   - Auto-reconnection with exponential backoff
   - Connection health monitoring and status tracking
   - Graceful disconnection handling
   - Thread-safe operations
   - Proper API call sequencing (nextValidId fix implemented)

2. **✅ API Rate Limiting** (`api_rate_limiter.py`)
   - 50 requests/second limit per IB specifications
   - Historical data request tracking and deduplication
   - Thread-safe request management
   - Compliance with TWS API pacing rules

3. **✅ Order Management System** (`order_manager.py`)
   - Complete order lifecycle tracking
   - Bracket order support (entry + profit target + stop loss)
   - Position management and monitoring
   - Order status tracking and validation
   - Comprehensive order record keeping

4. **✅ Contract Builder** (`contract_builder.py`)
   - Stock, options, and futures contract creation
   - OCC option symbol parsing
   - Contract normalization for data requests
   - Validation and error handling

5. **✅ Configuration Management** (`env_config.py` + `.env`)
   - Environment-based configuration (paper/live)
   - Secure `.env` file loading
   - Account masking for security
   - Easy environment switching

6. **✅ Market Status Integration** (`market_status.py`)
   - Real-time US stock market status checking
   - Trading hours detection with timezone handling
   - Holiday calendar integration
   - After-hours trading warnings

7. **✅ Main Application** (`tws_client.py`)
   - Portfolio tracking with real-time P&L
   - Real-time market data streaming
   - Historical data collection (OHLC)
   - Options contract detection and handling
   - Graceful shutdown with Ctrl+C handling
   - Working connection with proper event sequencing

8. **✅ Connection Diagnostics** (Multiple test utilities)
   - Socket connection testing
   - Client ID validation
   - Connection timeout handling
   - Detailed error reporting and troubleshooting

### 🔄 **In Progress / Remaining Tasks:**

1. **🔄 Event Bus Architecture** (HIGH PRIORITY)
   - Need to implement `core/event_bus.py`
   - Event-driven communication between modules
   - Pub/sub pattern for loose coupling
   - Event history and middleware support

2. **🔄 Database Integration** (HIGH PRIORITY)
   - PostgreSQL setup and configuration
   - SQLAlchemy models implementation
   - Database manager and connection pooling
   - Initial schema migration

3. **🔄 Modular Refactoring** (HIGH PRIORITY)
   - Extract components from monolithic `tws_client.py`
   - Create proper `core/` directory structure
   - Move modules into organized packages
   - Maintain backward compatibility during transition

4. **🔄 Testing Framework** (MEDIUM PRIORITY)
   - pytest configuration
   - Unit tests for existing modules
   - Integration test suite
   - Test coverage reporting

5. **🔄 Strategy Base Classes** (MEDIUM PRIORITY)
   - Abstract base strategy framework
   - Strategy lifecycle management
   - Signal generation interface
   - Strategy registration system

### ⏱️ **Timeline Adjustment:**

**Original Plan:** 7 days (Day 1-7)  
**Current Status:** ~4 days of work completed  
**Remaining:** ~3 days to complete Week 1 objectives

**Next 3 Days Focus:**
- **Day 1:** Event bus implementation + database setup
- **Day 2:** Modular refactoring (extract into core/)
- **Day 3:** Testing framework + strategy base classes

---

## 📋 Week 1 Deliverables Checklist (UPDATED)

### **✅ Completed: Project Setup & Core Components**
- [x] ~~Create new project structure with modular directories~~ (Partial - needs core/ refactor)
- [x] Set up development environment with proper tooling
- [x] Initialize Git repository with branching strategy
- [x] Create configuration management system (`env_config.py` + `.env`)
- [x] Enhanced TWS connection with health monitoring
- [x] API rate limiting per IB specifications
- [x] Order management with lifecycle tracking
- [x] Contract builder for multi-asset support
- [x] Market status integration
- [x] Connection diagnostic utilities

### **🔄 In Progress: Core Infrastructure**
- [ ] Implement event-driven architecture foundation (event_bus.py)
- [ ] Create database connection and basic schema
- [ ] Refactor into modular `core/` directory structure
- [ ] Implement logging and error handling framework
- [ ] Set up testing framework (pytest)

### **⏳ Remaining: Migration & Integration**
- [ ] Extract functionality from tws_client.py into modules
- [ ] Create base strategy framework
- [ ] Set up development database (PostgreSQL)
- [ ] Write comprehensive unit tests
- [ ] Create integration test suite

---

## 🏗️ Implementation Plan

### **Step 1: Target Project Structure**

```bash
# Current structure with planned refactoring
tws_robot/
├── 📁 core/                    # Core system components (TO CREATE)
│   ├── __init__.py
│   ├── connection.py           # Move from enhanced_connection.py ✅
│   ├── event_bus.py           # NEW - Event-driven architecture ❌
│   ├── data_pipeline.py       # Extract from tws_client.py ⏳
│   ├── order_manager.py       # Move from order_manager.py ✅
│   ├── rate_limiter.py        # Move from api_rate_limiter.py ✅
│   └── contract_builder.py    # Move from contract_builder.py ✅
├── 📁 strategies/             # Trading strategy implementations (TO CREATE)
│   ├── __init__.py
│   ├── base_strategy.py       # Abstract strategy framework ❌
│   └── mean_reversion.py      # Extract from trading_bot_template.py ⏳
├── 📁 risk/                   # Risk management (TO CREATE)
│   ├── __init__.py
│   └── risk_manager.py        # Basic risk monitoring ❌
├── 📁 data/                   # Data management (TO CREATE)
│   ├── __init__.py
│   ├── database.py            # Database connection ❌
│   └── models.py              # SQLAlchemy models ❌
├── 📁 config/                 # Configuration management (PARTIAL)
│   ├── __init__.py
│   ├── settings.py            # Enhanced version of env_config.py ⏳
│   ├── database.yaml          # Database configuration ❌
│   └── strategies.yaml        # Strategy parameters ❌
├── 📁 tests/                  # Testing framework (TO CREATE)
│   ├── __init__.py
│   ├── test_connection.py     # Connection tests ❌
│   ├── test_rate_limiter.py   # Rate limiter tests ❌
│   ├── test_order_manager.py  # Order manager tests ❌
│   └── test_strategies.py     # Strategy tests ❌
├── 📁 scripts/                # Utility scripts (TO CREATE)
│   ├── migrate_legacy.py      # Migration script ❌
│   └── setup_database.py      # Database setup ❌
│
├── 📄 EXISTING FILES (Working):
│   ├── tws_client.py          # Main app (needs refactoring) ✅
│   ├── enhanced_connection.py # To move to core/ ✅
│   ├── api_rate_limiter.py    # To move to core/ ✅
│   ├── order_manager.py       # To move to core/ ✅
│   ├── contract_builder.py    # To move to core/ ✅
│   ├── env_config.py          # To evolve into config/settings.py ✅
│   ├── market_status.py       # Keep as utility ✅
│   ├── connection_test.py     # Connection diagnostic ✅
│   ├── debug_connection.py    # Debugging utility ✅
│   └── quick_connection_test.py # Quick test utility ✅
│
├── main.py                    # NEW - Application entry point ❌
├── requirements.txt           # Dependencies ✅
├── requirements-dev.txt       # NEW - Dev dependencies ❌
├── pytest.ini                # NEW - Test configuration ❌
└── .env                       # Environment config ✅

Legend:
✅ = Implemented and working
⏳ = Partially implemented / needs refactoring
❌ = Not yet implemented
```

### **Step 2: Core Module Implementation**

#### **A. TWS Connection Module (`core/connection.py`)**
```python
# Extract and enhance connection logic from tws_client.py
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import threading
import queue
from typing import Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import logging

@dataclass
class ConnectionConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    timeout: int = 10

class ConnectionStatus(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"

class TWS_Connection(EWrapper, EClient):
    def __init__(self, config: ConnectionConfig, event_bus=None):
        EClient.__init__(self, self)
        self.config = config
        self.event_bus = event_bus
        self.status = ConnectionStatus.DISCONNECTED
        self.msg_queue = queue.Queue()
        self.logger = logging.getLogger(__name__)
        
        # Connection management
        self.connection_thread = None
        self.is_running = False
        
    def connect_tws(self) -> bool:
        """Establish connection to TWS"""
        try:
            self.status = ConnectionStatus.CONNECTING
            self.connect(
                self.config.host, 
                self.config.port, 
                self.config.client_id
            )
            
            # Start message processing thread
            self.connection_thread = threading.Thread(
                target=self.run, 
                daemon=True
            )
            self.connection_thread.start()
            
            # Wait for connection confirmation
            self.wait_for_connection()
            return True
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.status = ConnectionStatus.ERROR
            return False
    
    def wait_for_connection(self, timeout: int = 10):
        """Wait for connection to be established"""
        import time
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if self.isConnected():
                self.status = ConnectionStatus.CONNECTED
                self.logger.info("TWS connection established")
                return True
            time.sleep(0.1)
        
        self.status = ConnectionStatus.ERROR
        raise TimeoutError("Connection timeout")
    
    def disconnect_tws(self):
        """Safely disconnect from TWS"""
        self.is_running = False
        self.disconnect()
        if self.connection_thread and self.connection_thread.is_alive():
            self.connection_thread.join(timeout=5)
        self.status = ConnectionStatus.DISCONNECTED
        self.logger.info("TWS disconnected")
    
    # Event handlers (to be called by event bus)
    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.next_order_id = orderId
        if self.event_bus:
            self.event_bus.publish({
                'type': 'connection_ready',
                'order_id': orderId
            })
    
    def error(self, reqId, errorCode, errorString, **kwargs):
        super().error(reqId, errorCode, errorString)
        error_data = {
            'type': 'error',
            'req_id': reqId,
            'error_code': errorCode,
            'error_string': errorString
        }
        
        if self.event_bus:
            self.event_bus.publish(error_data)
        
        self.logger.error(f"TWS Error {errorCode}: {errorString}")
```

#### **B. Event Bus System (`core/event_bus.py`)**
```python
# Event-driven architecture for loose coupling
from typing import Dict, List, Callable, Any
from collections import defaultdict
import logging
from datetime import datetime
import json
import asyncio

class Event:
    def __init__(self, event_type: str, data: Dict[str, Any], 
                 timestamp: datetime = None):
        self.type = event_type
        self.data = data
        self.timestamp = timestamp or datetime.now()
        self.id = f"{self.type}_{int(self.timestamp.timestamp() * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type,
            'data': self.data,
            'timestamp': self.timestamp.isoformat()
        }

class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._middleware: List[Callable] = []
        self.logger = logging.getLogger(__name__)
        self._event_history: List[Event] = []
        
    def subscribe(self, event_type: str, handler: Callable[[Event], None]):
        """Subscribe to events of specific type"""
        self._handlers[event_type].append(handler)
        self.logger.debug(f"Handler registered for event type: {event_type}")
    
    def unsubscribe(self, event_type: str, handler: Callable):
        """Unsubscribe from events"""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
    
    def publish(self, event: Event):
        """Publish event to all subscribers"""
        # Store event in history
        self._event_history.append(event)
        if len(self._event_history) > 10000:  # Keep last 10k events
            self._event_history = self._event_history[-5000:]
        
        # Apply middleware
        for middleware in self._middleware:
            event = middleware(event)
        
        # Notify handlers
        for handler in self._handlers[event.type]:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(f"Error in event handler: {e}")
                # Publish error event
                self.publish(Event(
                    'handler_error',
                    {
                        'original_event': event.to_dict(),
                        'error': str(e),
                        'handler': handler.__name__
                    }
                ))
    
    def add_middleware(self, middleware: Callable[[Event], Event]):
        """Add middleware for event processing"""
        self._middleware.append(middleware)
    
    def get_event_history(self, event_type: str = None, 
                         limit: int = 100) -> List[Event]:
        """Get recent events, optionally filtered by type"""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]

# Create global event bus instance
event_bus = EventBus()
```

#### **C. Configuration Management (`config/settings.py`)**
```python
# Centralized configuration with environment support
import os
import yaml
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "tws_robot_dev"
    username: str = "postgres"
    password: str = ""
    
    @property
    def url(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class TWS_Config:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    timeout: int = 10

@dataclass
class RiskConfig:
    max_daily_loss: float = 0.02  # 2%
    max_position_size: float = 0.05  # 5%
    max_portfolio_heat: float = 0.20  # 20%
    
@dataclass
class SystemConfig:
    environment: str = "development"
    log_level: str = "INFO"
    data_retention_days: int = 365
    backup_enabled: bool = True

@dataclass
class Settings:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    tws: TWS_Config = field(default_factory=TWS_Config)
    risk: RiskConfig = field(default_factory=RiskConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    
    @classmethod
    def load(cls, config_dir: str = "config") -> "Settings":
        """Load configuration from files and environment"""
        settings = cls()
        config_path = Path(config_dir)
        
        # Load from YAML files
        for yaml_file in config_path.glob("*.yaml"):
            with open(yaml_file, 'r') as f:
                config_data = yaml.safe_load(f)
                settings._update_from_dict(config_data)
        
        # Override with environment variables
        settings._update_from_env()
        
        return settings
    
    def _update_from_dict(self, data: Dict[str, Any]):
        """Update settings from dictionary"""
        for section, values in data.items():
            if hasattr(self, section):
                section_obj = getattr(self, section)
                for key, value in values.items():
                    if hasattr(section_obj, key):
                        setattr(section_obj, key, value)
    
    def _update_from_env(self):
        """Update settings from environment variables"""
        # Database
        if os.getenv('DB_HOST'):
            self.database.host = os.getenv('DB_HOST')
        if os.getenv('DB_PORT'):
            self.database.port = int(os.getenv('DB_PORT'))
        if os.getenv('DB_NAME'):
            self.database.database = os.getenv('DB_NAME')
        if os.getenv('DB_USER'):
            self.database.username = os.getenv('DB_USER')
        if os.getenv('DB_PASSWORD'):
            self.database.password = os.getenv('DB_PASSWORD')
        
        # TWS
        if os.getenv('TWS_HOST'):
            self.tws.host = os.getenv('TWS_HOST')
        if os.getenv('TWS_PORT'):
            self.tws.port = int(os.getenv('TWS_PORT'))
        if os.getenv('TWS_CLIENT_ID'):
            self.tws.client_id = int(os.getenv('TWS_CLIENT_ID'))
        
        # System
        if os.getenv('ENVIRONMENT'):
            self.system.environment = os.getenv('ENVIRONMENT')
        if os.getenv('LOG_LEVEL'):
            self.system.log_level = os.getenv('LOG_LEVEL')

# Global settings instance
settings = Settings.load()
```

### **Step 3: Database Setup**

#### **Database Models (`data/models.py`)**
```python
# SQLAlchemy models for core entities
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Strategy(Base):
    __tablename__ = 'strategies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    class_name = Column(String(100), nullable=False)
    config = Column(JSON, nullable=False)
    status = Column(String(20), default='INACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    orders = relationship("Order", back_populates="strategy")

class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(String(50), unique=True, nullable=False)
    strategy_id = Column(Integer, ForeignKey('strategies.id'))
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)  # BUY/SELL
    quantity = Column(Integer, nullable=False)
    price = Column(Float)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    filled_at = Column(DateTime)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="orders")

class Position(Base):
    __tablename__ = 'positions'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False)
    quantity = Column(Integer, nullable=False)
    avg_cost = Column(Float, nullable=False)
    unrealized_pnl = Column(Float)
    realized_pnl = Column(Float)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MarketData(Base):
    __tablename__ = 'market_data'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    price = Column(Float, nullable=False)
    volume = Column(Integer)
    bid = Column(Float)
    ask = Column(Float)
```

### **Step 4: Migration Script**

#### **Legacy Migration (`scripts/migrate_legacy.py`)**
```python
#!/usr/bin/env python3
# Migration script from v1 to v2 architecture

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import settings
from data.database import DatabaseManager
from data.models import Strategy, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LegacyMigrator:
    def __init__(self):
        self.db = DatabaseManager(settings.database.url)
        
    def migrate_configuration(self):
        """Migrate .env configuration to database"""
        logger.info("Migrating configuration...")
        
        # Read existing .env files
        env_files = ['.env', '.env.paper', '.env.live']
        config_data = {}
        
        for env_file in env_files:
            if Path(env_file).exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            config_data[key] = value
        
        # Store in system_config table (to be created)
        logger.info(f"Migrated {len(config_data)} configuration items")
    
    def migrate_strategy_config(self):
        """Create initial strategy record for existing Bollinger Bands"""
        logger.info("Creating strategy record for existing system...")
        
        with self.db.get_session() as session:
            # Check if strategy already exists
            existing = session.query(Strategy).filter_by(name="BollingerBands_Legacy").first()
            if existing:
                logger.info("Legacy strategy already migrated")
                return
            
            # Create strategy record
            strategy = Strategy(
                name="BollingerBands_Legacy",
                class_name="strategies.mean_reversion.MeanReversionStrategy",
                config={
                    "lookback_period": 20,
                    "std_dev_threshold": 2.0,
                    "position_size": 0.02,
                    "symbols": ["AAPL"],  # Default from legacy system
                    "migrated_from": "trading_bot_template.py",
                    "migration_date": datetime.now().isoformat()
                },
                status="INACTIVE"  # Start as inactive for safety
            )
            
            session.add(strategy)
            session.commit()
            
            logger.info(f"Created strategy record with ID: {strategy.id}")
    
    def create_initial_portfolio_snapshot(self):
        """Create initial portfolio snapshot if we have position data"""
        logger.info("Creating initial portfolio snapshot...")
        
        # This would read current positions from tws_client.py output
        # For now, create empty snapshot
        # Implementation depends on current data format
        
    def run_migration(self):
        """Run complete migration process"""
        logger.info("Starting legacy migration...")
        
        try:
            # Create database tables
            self.db.create_tables()
            
            # Run migrations
            self.migrate_configuration()
            self.migrate_strategy_config()
            self.create_initial_portfolio_snapshot()
            
            logger.info("Migration completed successfully!")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

if __name__ == "__main__":
    migrator = LegacyMigrator()
    migrator.run_migration()
```

---

## 🎯 Immediate Next Steps (Priority Order)

### **Priority 1: Event Bus Implementation** (Day 1 - Morning)
```bash
# Create core directory and event bus
mkdir core
touch core/__init__.py

# Implement event bus as shown in code examples below
# This is foundational for decoupling modules
```

**Why First:** Event bus enables loose coupling between all other modules. Once implemented, we can refactor tws_client.py to use events instead of direct calls.

### **Priority 2: Database Setup** (Day 1 - Afternoon)
```bash
# Install PostgreSQL dependencies
pip install psycopg2-binary sqlalchemy alembic

# Create database directories
mkdir data
touch data/{__init__.py,database.py,models.py}

# Set up local PostgreSQL database
# See database setup section below
```

**Why Second:** Database is needed for trade tracking, strategy configuration, and performance metrics. Foundation for persistence layer.

### **Priority 3: Modular Refactoring** (Day 2)
```bash
# Move existing modules into core/
mv enhanced_connection.py core/connection.py
mv api_rate_limiter.py core/rate_limiter.py
mv order_manager.py core/order_manager.py
mv contract_builder.py core/contract_builder.py

# Update imports in tws_client.py
# Extract data pipeline logic
# Create strategy base classes
```

**Why Third:** Once event bus and database are ready, we can properly refactor the monolithic tws_client.py into clean modules that communicate via events and persist to database.

### **Priority 4: Testing Framework** (Day 3)
```bash
# Install testing dependencies
pip install pytest pytest-cov pytest-asyncio

# Set up test structure
mkdir tests
touch pytest.ini
touch tests/{__init__.py,test_connection.py,test_event_bus.py}

# Write and run initial tests
pytest tests/ -v --cov=core
```

**Why Fourth:** With modules properly structured and decoupled, we can write comprehensive tests to ensure reliability before adding more features.

---

## 🧪 Week 1 Testing Strategy

### **Test Setup (`pytest.ini`)**
```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
```

### **Sample Tests (`tests/test_connection.py`)**
```python
import pytest
from unittest.mock import Mock, patch
from core.connection import TWS_Connection, ConnectionConfig, ConnectionStatus

class TestTWSConnection:
    def test_connection_config(self):
        config = ConnectionConfig(host="localhost", port=7497, client_id=1)
        assert config.host == "localhost"
        assert config.port == 7497
        assert config.client_id == 1
    
    def test_connection_initialization(self):
        config = ConnectionConfig()
        connection = TWS_Connection(config)
        assert connection.status == ConnectionStatus.DISCONNECTED
        assert connection.config == config
    
    @patch('core.connection.EClient.connect')
    def test_connect_success(self, mock_connect):
        config = ConnectionConfig()
        connection = TWS_Connection(config)
        
        # Mock successful connection
        mock_connect.return_value = True
        connection.isConnected = Mock(return_value=True)
        
        result = connection.connect_tws()
        assert result == True
        assert connection.status == ConnectionStatus.CONNECTED
```

---

## 📝 Week 1 Daily Tasks

### **Day 1: Project Structure & Setup**
```bash
# Commands to run on Day 1

# 1. Create new project structure
mkdir -p tws_robot_v2/{core,strategies,risk,data,config,tests,scripts}
touch tws_robot_v2/{core,strategies,risk,data,config,tests}/__init__.py

# 2. Set up Python environment
python -m venv tws_robot_v2_env
source tws_robot_v2_env/bin/activate  # On Windows: tws_robot_v2_env\Scripts\activate
pip install -r requirements-dev.txt

# 3. Initialize Git repository
git init
git add .
git commit -m "Initial project structure"

# 4. Create development configuration
cp config/database.yaml.example config/database.yaml
cp config/strategies.yaml.example config/strategies.yaml
```

### **Day 2: Configuration & Testing Setup**
- Implement configuration management system
- Set up testing framework with pytest
- Create development database
- Write initial unit tests

### **Day 3: Core Infrastructure**
- Implement TWS connection module
- Create event bus system
- Set up basic logging framework
- Test connection functionality

### **Day 4: Data Layer**
- Set up SQLAlchemy models
- Create database manager
- Implement basic data pipeline
- Test database connectivity

### **Day 5: Migration**
- Create migration script
- Extract existing TWS client logic
- Migrate configuration to new system
- Test migration process

### **Day 6: Strategy Framework**
- Implement base strategy class
- Create strategy registration system
- Migrate Bollinger Bands strategy
- Test strategy loading

### **Day 7: Integration & Testing**
- Integration testing
- End-to-end functionality test
- Performance benchmarking
- Documentation updates

---

This Week 1 guide provides a concrete roadmap for transforming the existing TWS Robot into a professional modular architecture. Each day has specific deliverables that build toward the foundation needed for the remaining 6 weeks.

Would you like me to start implementing any of these specific files to kick off Week 1?