# TWS Robot - Deployment Guide

## Overview

This guide covers running TWS Robot with your Interactive Brokers accounts:
- **Paper Account (DU2746208, port 7497)**: For testing and 30-day validation
- **Live Account (U6801816, port 7496)**: For production trading after validation

---

## Prerequisites

- ✅ TWS (Trader Workstation) installed and running
- ✅ Paper trading account active in TWS (port 7497)
- ✅ Python 3.12+ virtual environment activated
- ✅ All dependencies installed: `pip install -r requirements.txt`
- ✅ All 647 tests passing: `pytest`
- ✅ `.env` file configured

---

## Quick Start - Paper Trading (30-Day Validation)

### 1. Verify TWS Running

```powershell
# TWS should be running with:
# - API enabled (Configure → API → Settings)
# - Socket port 7497 (paper trading)
# - Paper account DU2746208 logged in
```

### 2. Check Your .env Configuration

```powershell
# Verify .env has paper account settings:
notepad .env

# Should contain:
# TRADING_ENV=paper
# PAPER_HOST=127.0.0.1
# PAPER_PORT=7497
# PAPER_ACCOUNT=DU2746208
```

### 3. Initialize Database

```powershell
# Activate virtual environment
.\Scripts\Activate.ps1

# Initialize database schema
python init_database.py
```

### 4. Run Tests

```powershell
# Validate everything works
pytest --tb=short

# Expected: 647/647 tests passing (100%)
```

### 5. Start TWS Robot

```powershell
# Run main application
python tws_client.py

# Or use your preferred entry point
# python main.py
```

### 6. Monitor Operation

```powershell
# Check logs
Get-Content .\logs\*.log -Tail 50

# Monitor TWS connection in TWS window
# Verify strategies executing (if implemented)
```

---

## 30-Day Validation Period

### Daily Checks (10-15 min/day)

```powershell
# 1. Verify system running
Get-Process python

# 2. Check logs for errors
Get-Content .\logs\*.log -Tail 100

# 3. Monitor TWS connection
# - Check TWS window for connection status
# - Verify no error messages

# 4. Review performance (if strategies active)
# - Check positions in TWS
# - Review trade history
```

### Weekly Checks (30-60 min/week)

- Review performance metrics:
  - Sharpe Ratio (target > 1.0)
  - Max Drawdown (target < 10%)
  - Win Rate (target > 50%)
- Backup database: `.\deployment_scripts\backup_database.ps1`
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

**Validation Period:** November 24 - December 24, 2025

---

## Switching to Live Trading

⚠️ **ONLY PROCEED AFTER SUCCESSFUL 30-DAY VALIDATION** ⚠️

### Before Going Live

1. **Review Validation Results**
   - Confirm all success criteria met
   - Review all trades and decisions
   - Document lessons learned

2. **Verify Live Account Setup**
   - Live account U6801816 active in TWS
   - TWS configured for live trading (port 7496)
   - Risk controls in place
   - Emergency procedures documented

3. **Update Configuration**

```powershell
# Edit .env
notepad .env

# Change these settings:
# TRADING_ENV=live
# LIVE_HOST=127.0.0.1
# LIVE_PORT=7496        # ← Change from 7497 to 7496
# LIVE_ACCOUNT=U6801816

# ⚠️ CRITICAL: Verify risk limits are appropriate for live capital
```

4. **Start with Small Capital**
   - Begin with minimal position sizes
   - Gradually increase as confidence grows
   - Monitor closely for first week

5. **Launch Live Trading**

```powershell
# Restart TWS with live account (port 7496)
# Run full test suite
pytest

# Start TWS Robot
python tws_client.py

# Monitor closely!
```

---

## Daily Operations

### Starting the System

```powershell
# 1. Start TWS (paper or live)
# 2. Activate Python environment
.\Scripts\Activate.ps1

# 3. Start TWS Robot
python tws_client.py
```

### Stopping the System

```powershell
# Graceful shutdown: Press Ctrl+C in terminal
# Or close TWS Robot window

# Always verify:
# - All positions closed (if end of day)
# - No pending orders
# - Logs saved
```

### Emergency Stop

```powershell
# If something goes wrong:
# 1. Press Ctrl+C to stop Python application
# 2. In TWS: Manually close all positions
# 3. Review logs to understand what happened
# 4. Fix issue before restarting
```

### Database Backup

```powershell
# Manual backup
.\scripts\backup_database.ps1

# Automatic: Runs daily via backup script
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

### Key Performance Indicators

```sql
-- Query database for metrics (if implemented)
SELECT 
    strategy_name,
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
    AVG(pnl) as avg_pnl,
    SUM(pnl) as total_pnl
FROM trades
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY strategy_name;
```

### Log Files

```powershell
# View recent logs
Get-Content .\logs\*.log -Tail 100

# Search for errors
Select-String -Path .\logs\*.log -Pattern "ERROR"

# Monitor live logs
Get-Content .\logs\*.log -Wait -Tail 50
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

```powershell
# Check Python processes
Get-Process python

# Kill stuck Python processes
Stop-Process -Name python -Force

# View environment variables
Get-Content .env

# Test database connection
python -c "from data.database import Database; db = Database(); print('Connected!')"

# Run specific test
pytest tests/test_connection.py -v

# Check TWS API status
python quick_connection_test.py
```

---

## Summary

**Paper Trading (Now → Dec 24, 2025):**
- Port: 7497
- Account: DU2746208
- Goal: 30-day validation
- Focus: Verify system stability and performance

**Live Trading (After Dec 24, 2025):**
- Port: 7496
- Account: U6801816
- Prerequisites: Successful 30-day validation
- Approach: Start small, scale gradually

Good luck with your trading! 🚀📈
