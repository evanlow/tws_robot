# TWS Robot - Local Deployment Guide

## Overview

This guide covers running TWS Robot locally with your Interactive Brokers accounts:
- **Paper Account (port 7497)**: For testing and 30-day validation
- **Live Account (port 7496)**: For production trading after validation

> 💡 **Tip:** The **web dashboard** is the recommended way to use TWS Robot. See [Web Dashboard](#web-dashboard) section.

---

## Prerequisites

- ✅ TWS (Trader Workstation) installed and running
- ✅ Paper trading account active in TWS (port 7497)
- ✅ Python 3.8+ with virtual environment activated
- ✅ All dependencies installed: `pip install -r requirements.txt`
- ✅ All tests passing: `pytest`
- ✅ `.env` file configured (copy from `.env.example`)

---

## Web Dashboard

The **recommended way** to use TWS Robot day-to-day is through the web dashboard:

```bash
# Start the web dashboard
python scripts/run_web.py

# Open in your browser: http://127.0.0.1:5000
```

From the dashboard you can:
- View connection status, equity, and P&L at a glance
- Start, stop, and monitor trading strategies
- Run backtests and review results
- Monitor risk levels and emergency stop with one click
- Browse logs and configure settings
- Use the AI assistant for strategy analysis and recommendations (requires OpenAI API key)

---

## Quick Start - Paper Trading (30-Day Validation)

### 1. Verify TWS Running

TWS should be running with:
- API enabled: **Edit → Global Configuration → API → Settings**
- Enable "**Enable ActiveX and Socket Clients**"
- Socket port: **7497** (paper trading)
- Your paper account logged in

### 2. Configure Your .env File

```bash
# Copy the template
cp .env.example .env

# Edit with your details (use any text editor)
```

Your `.env` should contain:
```env
TRADING_ENV=paper
PAPER_HOST=127.0.0.1
PAPER_PORT=7497
PAPER_ACCOUNT=YOUR_PAPER_ACCOUNT_ID    # Replace with your paper account ID
```

### 3. Initialize Database

```bash
# Activate virtual environment
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate       # Mac/Linux

# Initialize database schema
python scripts/init_database.py
```

### 4. Run Tests

```bash
# Validate everything works
pytest --tb=short
```

### 5. Start TWS Robot

**Option A: Web Dashboard (Recommended)**
```bash
python scripts/run_web.py
# Open http://127.0.0.1:5000
```

**Option B: Terminal**
```bash
# Run with paper account (default)
python tws_client.py

# Or explicitly specify paper
python tws_client.py --env paper

# Show current configuration
python tws_client.py --show-config
```

### 6. Monitor Operation

**From the web dashboard:** The Dashboard page shows connection status, positions, and alerts.

**From the terminal:**
```bash
# View recent logs (Windows)
type logs\*.log | more

# View recent logs (Mac/Linux)
tail -50 logs/*.log
```

---

## 30-Day Validation Period

### Daily Checks (5-10 min/day)

**From the web dashboard (recommended):**
1. Open http://127.0.0.1:5000
2. Check the Dashboard page for connection status and alerts
3. Review the Positions page for open trades
4. Glance at the Risk page for any warnings

**From the terminal:**
```bash
# Check if system is running
# Windows: tasklist | findstr python
# Mac/Linux: ps aux | grep python

# Check logs for errors (Windows)
findstr "ERROR" logs\*.log

# Check logs for errors (Mac/Linux)
grep "ERROR" logs/*.log
```

### Weekly Checks (30-60 min/week)

- Review performance metrics:
  - Sharpe Ratio (target > 1.0)
  - Max Drawdown (target < 10%)
  - Win Rate (target > 50%)
- Backup database regularly
- Document any issues or observations
- Verify risk limits are being enforced

### Validation Success Criteria

After 30 days, verify:
- ✅ **30+ days** continuous operation
- ✅ **Sharpe Ratio** > 1.0
- ✅ **Max Drawdown** < 10%
- ✅ **Win Rate** > 50%
- ✅ **Zero** risk limit violations
- ✅ **No** system crashes

---

## Switching to Live Trading

⚠️ **ONLY PROCEED AFTER SUCCESSFUL 30-DAY VALIDATION** ⚠️

### Before Going Live

1. **Review Validation Results**
   - Confirm all success criteria met
   - Review all trades and decisions
   - Document lessons learned

2. **Verify Live Account Setup**
   - Live account active in TWS
   - TWS configured for live trading (port 7496)
   - Risk controls in place
   - Emergency procedures documented

3. **Update Configuration**

```bash
# Edit your .env file
```

Your `.env` should contain:
```env
LIVE_HOST=127.0.0.1
LIVE_PORT=7496
LIVE_ACCOUNT=YOUR_LIVE_ACCOUNT_ID    # Replace with your live account ID

# ⚠️ CRITICAL: Verify risk limits are appropriate for live capital
```

4. **Start with Small Capital**
   - Begin with minimal position sizes
   - Gradually increase as confidence grows
   - Monitor closely for first week

5. **Launch Live Trading**

```bash
# Restart TWS with live account (port 7496)
# Run full test suite
pytest

# Option A: Web Dashboard (Recommended)
python scripts/run_web.py
# Open http://127.0.0.1:5000 and connect via Settings

# Option B: Terminal
python tws_client.py --env live

# Monitor closely!
```

---

## Daily Operations

### Starting the System

```bash
# 1. Start TWS (paper port 7497 or live port 7496)

# 2. Activate Python environment
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate       # Mac/Linux

# 3. Start TWS Robot (Web Dashboard - Recommended)
python scripts/run_web.py

# Or via terminal:
python tws_client.py --env paper   # Paper trading
python tws_client.py --env live    # Live trading
```

### Stopping the System

```bash
# From web dashboard: Click 🚨 EMERGENCY STOP in the top bar
# From terminal: Press Ctrl+C for graceful shutdown

# Always verify:
# - All positions closed (if end of day)
# - No pending orders
# - Logs saved
```

### Emergency Stop

```bash
# 1. From web dashboard: Click 🚨 EMERGENCY STOP button
# 2. From terminal: Press Ctrl+C to stop Python application
# 3. In TWS: Manually close all positions
# 4. Review logs to understand what happened
# 5. Fix issue before restarting
```

### Database Backup

```bash
# Windows
copy strategy_lifecycle.db strategy_lifecycle.db.backup

# Mac/Linux
cp strategy_lifecycle.db strategy_lifecycle.db.backup
```

---

## Troubleshooting

### TWS Connection Issues

**Problem:** Can't connect to TWS

**Solutions:**
1. Verify TWS is running
2. Check API settings enabled (Configure → API → Settings)
3. Verify port number (7497 paper, 7496 live)
4. Check trusted IP includes 127.0.0.1
5. Restart TWS and try again

### Database Connection Issues

**Problem:** Can't connect to database

**Solutions:**
1. Verify DATABASE_URL in .env is correct
2. Check database server is running
3. Verify credentials are correct
4. Run `python init_database.py` to reinitialize
5. Check firewall isn't blocking connection

### Tests Failing

**Problem:** Tests not passing

**Solutions:**
1. Check TWS is running for API tests
2. Verify database is accessible
3. Run with verbose output: `pytest -v`
4. Check specific failing test: `pytest tests/test_xxx.py -v`
5. Review logs for error details

### Performance Issues

**Problem:** System running slow

**Solutions:**
1. Check system resources (CPU, memory)
2. Review logs for excessive API calls
3. Verify database query performance
4. Check for memory leaks
5. Consider optimizing strategies

---

## Monitoring & Metrics

### Web Dashboard Monitoring (Recommended)

Open http://127.0.0.1:5000 and use:
- **Dashboard** — Real-time equity, P&L, strategy status
- **Strategies** — Strategy management and performance
- **Positions** — Open positions and trade history
- **Risk** — Risk levels, drawdown, circuit breaker status
- **Logs** — Browse application logs
- **AI Chat** — Ask the AI assistant about strategies and trading decisions

### Terminal Monitoring

```bash
# View recent logs (Windows)
type logs\*.log | more

# View recent logs (Mac/Linux)
tail -50 logs/*.log

# Search for errors (Windows)
findstr "ERROR" logs\*.log

# Search for errors (Mac/Linux)
grep "ERROR" logs/*.log
```

---

## Future: AWS Deployment

After successful local validation, you can deploy to AWS for:
- **24/7 operation** (no local machine needed)
- **Managed infrastructure** (RDS, ElastiCache)
- **Enhanced monitoring** (CloudWatch)
- **Automated backups** (S3)
- **Scalability** (if needed)

AWS deployment guide will be created when ready.

---

## Support

### Getting Help

1. Check logs for error details
2. Review this troubleshooting section
3. Check TWS API documentation
4. Review code documentation and docstrings
5. Search project issues on GitHub

### Useful Commands

```bash
# Start the web dashboard
python scripts/run_web.py

# View environment variables
cat .env

# Test database connection
python -c "from data.database import Database; db = Database(); print('Connected!')"

# Run specific test
pytest tests/test_connection.py -v

# Check TWS API status
python scripts/quick_connection_test.py
```

---

## Summary

**Paper Trading:**
- Port: 7497
- Goal: 30-day validation
- Focus: Verify system stability and performance

**Live Trading (After Validation):**
- Port: 7496
- Prerequisites: Successful 30-day validation
- Approach: Start small, scale gradually

**Web Dashboard:**
- Launch: `python scripts/run_web.py`
- URL: http://127.0.0.1:5000
- Features: Dashboard, strategies, backtest, positions, risk, logs, settings

Good luck with your trading! 🚀📈
