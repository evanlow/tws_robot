# TWS Robot v2.0 - Week 1 Implementation Guide
## Foundation & Core Infrastructure Setup

**Sprint Goal:** Establish modular architecture and core components  
**Duration:** Week 1 of 7-week project  
**Focus:** Migration from monolithic to modular design  

---

## 📋 Week 1 Deliverables Checklist

### **Day 1-2: Project Setup & Structure**
- [ ] Create new project structure with modular directories
- [ ] Set up development environment with proper tooling
- [ ] Initialize Git repository with branching strategy
- [ ] Create configuration management system
- [ ] Set up testing framework

### **Day 3-4: Core Infrastructure**
- [ ] Extract TWS connection logic into reusable module
- [ ] Implement event-driven architecture foundation
- [ ] Create database connection and basic schema
- [ ] Build configuration loader with environment support
- [ ] Implement logging and error handling framework

### **Day 5-7: Migration & Integration**
- [ ] Migrate existing functionality to new structure
- [ ] Create data pipeline for market data processing
- [ ] Implement basic strategy framework
- [ ] Set up development database
- [ ] Create migration scripts from legacy system

---

## 🏗️ Implementation Plan

### **Step 1: Create New Project Structure**

```bash
# Project structure to create
tws_robot_v2/
├── 📁 core/                    # Core system components
│   ├── __init__.py
│   ├── connection.py           # TWS connection management
│   ├── event_bus.py           # Event-driven architecture
│   ├── data_pipeline.py       # Market data processing
│   └── order_manager.py       # Order execution & tracking
├── 📁 strategies/             # Trading strategy implementations
│   ├── __init__.py
│   ├── base_strategy.py       # Abstract strategy framework
│   └── mean_reversion.py      # Migrated Bollinger Bands
├── 📁 risk/                   # Risk management (basic for now)
│   ├── __init__.py
│   └── risk_manager.py        # Basic risk monitoring
├── 📁 data/                   # Data management
│   ├── __init__.py
│   ├── database.py            # Database connection
│   └── models.py              # Database models
├── 📁 config/                 # Configuration management
│   ├── __init__.py
│   ├── settings.py            # Configuration loader
│   ├── database.yaml          # Database configuration
│   └── strategies.yaml        # Strategy parameters
├── 📁 tests/                  # Testing framework
│   ├── __init__.py
│   ├── test_connection.py     # Connection tests
│   └── test_strategies.py     # Strategy tests
├── 📁 scripts/                # Utility scripts
│   ├── migrate_legacy.py      # Migration from v1
│   └── setup_dev_env.py       # Development setup
├── main.py                    # Application entry point
├── requirements-dev.txt       # Development dependencies
└── pytest.ini                # Test configuration
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