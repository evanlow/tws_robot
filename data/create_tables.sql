-- TWS Robot Trading System Database Schema
-- MySQL Version
-- Created: November 17, 2025

-- ============================================================================
-- Strategy Table: Strategy configuration and tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS strategies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT FALSE,
    started_at DATETIME,
    stopped_at DATETIME,
    config JSON,
    total_trades INT DEFAULT 0,
    winning_trades INT DEFAULT 0,
    losing_trades INT DEFAULT 0,
    total_pnl FLOAT DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_is_active (is_active),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- Trades Table: Completed trade records with P&L
-- ============================================================================
CREATE TABLE IF NOT EXISTS trades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id INT NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    entry_time DATETIME NOT NULL,
    entry_price FLOAT NOT NULL,
    entry_order_id INT,
    exit_time DATETIME,
    exit_price FLOAT,
    exit_order_id INT,
    quantity INT NOT NULL,
    side ENUM('LONG', 'SHORT') NOT NULL,
    gross_pnl FLOAT,
    commission FLOAT DEFAULT 0.0,
    net_pnl FLOAT,
    pnl_percentage FLOAT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    notes TEXT,
    extra_data JSON,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    INDEX idx_symbol (symbol),
    INDEX idx_entry_time (entry_time),
    INDEX idx_strategy_id (strategy_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- Positions Table: Current and historical positions
-- ============================================================================
CREATE TABLE IF NOT EXISTS positions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id INT NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity INT NOT NULL,
    side ENUM('LONG', 'SHORT') NOT NULL,
    avg_entry_price FLOAT NOT NULL,
    current_price FLOAT,
    is_open BOOLEAN DEFAULT TRUE,
    opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME,
    unrealized_pnl FLOAT DEFAULT 0.0,
    realized_pnl FLOAT DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    extra_data JSON,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    INDEX idx_is_open (is_open),
    INDEX idx_opened_at (opened_at),
    INDEX idx_symbol (symbol),
    INDEX idx_strategy_id (strategy_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- Orders Table: Order lifecycle tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id INT,
    ib_order_id INT NOT NULL UNIQUE,
    perm_id INT,
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    quantity INT NOT NULL,
    limit_price FLOAT,
    stop_price FLOAT,
    status ENUM('PENDING', 'SUBMITTED', 'ACCEPTED', 'FILLED', 'PARTIALLY_FILLED', 'CANCELLED', 'REJECTED') DEFAULT 'PENDING',
    filled_quantity INT DEFAULT 0,
    remaining_quantity INT,
    avg_fill_price FLOAT,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    filled_at DATETIME,
    cancelled_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    extra_data JSON,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE SET NULL,
    INDEX idx_ib_order_id (ib_order_id),
    INDEX idx_symbol (symbol),
    INDEX idx_status (status),
    INDEX idx_submitted_at (submitted_at),
    INDEX idx_strategy_id (strategy_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- Market Data Table: Historical OHLCV data
-- ============================================================================
CREATE TABLE IF NOT EXISTS market_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp DATETIME NOT NULL,
    open FLOAT NOT NULL,
    high FLOAT NOT NULL,
    low FLOAT NOT NULL,
    close FLOAT NOT NULL,
    volume INT NOT NULL,
    bar_size VARCHAR(20) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_symbol (symbol),
    INDEX idx_timestamp (timestamp),
    INDEX idx_symbol_timestamp (symbol, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- Performance Metrics Table: Daily and cumulative performance
-- ============================================================================
CREATE TABLE IF NOT EXISTS performance_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id INT,
    date DATETIME NOT NULL,
    daily_pnl FLOAT DEFAULT 0.0,
    daily_return FLOAT DEFAULT 0.0,
    trades_count INT DEFAULT 0,
    cumulative_pnl FLOAT DEFAULT 0.0,
    cumulative_return FLOAT DEFAULT 0.0,
    win_rate FLOAT DEFAULT 0.0,
    sharpe_ratio FLOAT,
    max_drawdown FLOAT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    INDEX idx_date (date),
    INDEX idx_strategy_id (strategy_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- Insert Default Strategy for Manual Trading
-- ============================================================================
INSERT INTO strategies (name, description, is_active, config)
VALUES (
    'Manual Trading',
    'Default strategy for manual trades',
    TRUE,
    '{"type": "manual", "risk_per_trade": 0.02}'
)
ON DUPLICATE KEY UPDATE name=name;

-- ============================================================================
-- Verification Queries
-- ============================================================================
-- Show all tables
SHOW TABLES;

-- Show table structures
DESCRIBE strategies;
DESCRIBE trades;
DESCRIBE positions;
DESCRIBE orders;
DESCRIBE market_data;
DESCRIBE performance_metrics;

-- ============================================================================
-- Portfolio Analytics Tables (for SQLite — auto-created by portfolio_persistence.py)
-- ============================================================================
-- These tables are managed by data/portfolio_persistence.py using raw SQL
-- for SQLite compatibility. The DDL below is the reference schema:
--
-- CREATE TABLE IF NOT EXISTS portfolio_snapshots (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     timestamp TEXT NOT NULL,
--     total_equity REAL DEFAULT 0.0,
--     cash REAL DEFAULT 0.0,
--     positions_json TEXT,
--     strategy_mix_json TEXT,
--     analysis_json TEXT,
--     created_at TEXT DEFAULT (datetime('now'))
-- );
--
-- CREATE TABLE IF NOT EXISTS stock_analyses (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     symbol TEXT NOT NULL,
--     analysis_date TEXT NOT NULL,
--     fundamentals_json TEXT,
--     technical_json TEXT,
--     ai_analysis_json TEXT,
--     verdict TEXT,
--     created_at TEXT DEFAULT (datetime('now'))
-- );
--
-- CREATE TABLE IF NOT EXISTS fundamentals_cache (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     symbol TEXT NOT NULL,
--     data_json TEXT NOT NULL,
--     fetched_at TEXT NOT NULL,
--     created_at TEXT DEFAULT (datetime('now'))
-- );
