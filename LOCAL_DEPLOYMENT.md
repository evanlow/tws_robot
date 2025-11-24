# Local Production Deployment - Quick Start Guide

## 🎯 Overview

This guide walks you through deploying TWS Robot on your local Windows machine for the **30-day paper trading validation period**.

**Prerequisites:**
- ✅ Windows machine with TWS installed and running
- ✅ Python 3.12+ with virtual environment
- ✅ Docker Desktop installed and running
- ✅ All 647 tests passing

---

## 📋 Step-by-Step Deployment

### **Step 1: Verify Prerequisites** (5 min)

```powershell
# Check Docker is running
docker --version
docker ps

# Check TWS is running (should see TWS window)
# Verify TWS API is enabled:
# - TWS → Configure → API → Settings
# - "Enable ActiveX and Socket Clients" = checked
# - Socket port = 7497 (for paper trading)
# - Trusted IP addresses includes 127.0.0.1

# Verify Python environment
python --version  # Should be 3.12+
```

---

### **Step 2: Configure Production Environment** (10 min)

```powershell
# 1. Copy environment template
Copy-Item .env.production.example .env.production

# 2. Edit .env.production (already pre-configured for local deployment)
# Review and adjust if needed:
#   - TWS_PORT=7497 (paper trading)
#   - IB_ACCOUNT=DU2746208 (your account)
#   - Database password (optional, default is fine for local)

notepad .env.production
```

**Key Settings to Verify:**
```bash
TWS_HOST=127.0.0.1
TWS_PORT=7497              # Paper trading port
IB_ACCOUNT=DU2746208       # Your IB paper account
PAPER_TRADING=true         # Keep true for 30-day validation
EMERGENCY_STOP=false       # Set true to halt all trading
```

---

### **Step 3: Start Infrastructure Services** (5 min)

```powershell
# Start PostgreSQL and Redis in Docker
docker-compose -f docker-compose.local.yml up -d

# Verify services are running
docker ps
# Should see: tws-robot-postgres and tws-robot-redis

# Check database health
docker exec tws-robot-postgres pg_isready -U tws_user -d tws_robot_prod
# Should output: accepting connections
```

**Troubleshooting:**
- If PostgreSQL won't start: Check port 5432 isn't already in use
- If Redis won't start: Check port 6379 isn't already in use
- View logs: `docker logs tws-robot-postgres` or `docker logs tws-robot-redis`

---

### **Step 4: Initialize Database** (2 min)

```powershell
# Activate virtual environment
.\Scripts\Activate.ps1

# Initialize database schema
python init_database.py

# Verify database tables created
docker exec tws-robot-postgres psql -U tws_user -d tws_robot_prod -c "\dt"
```

---

### **Step 5: Run Production Validation Tests** (2 min)

```powershell
# Run all tests to verify production environment
pytest --tb=no -q

# Expected: 647/647 tests passing (100%)
```

**If tests fail:**
- Review error messages
- Check TWS is running and API is enabled
- Verify database connection
- Check all environment variables in .env.production

---

### **Step 6: Start TWS Robot Production** (1 min)

**Option A: Using the startup script (recommended)**
```powershell
.\scripts\start_production.ps1
```

**Option B: Manual start**
```powershell
.\Scripts\Activate.ps1
python production_main.py
```

**What you should see:**
```
========================================
  TWS Robot Production - Starting
========================================
✓ Production configuration loaded
Environment: production
Paper Trading: true
TWS Connection: 127.0.0.1:7497
IB Account: DU2746208
========================================
  TWS Robot Production - Running
========================================
Press Ctrl+C to stop gracefully
```

---

### **Step 7: Verify Everything is Working** (10 min)

**7.1 Check TWS Connection:**
```powershell
# In another terminal, check logs
Get-Content .\logs\tws_robot_*.log -Tail 50
```

**7.2 Monitor Database:**
```powershell
# Optional: Start pgAdmin for database management
docker-compose -f docker-compose.local.yml --profile tools up -d pgadmin

# Access pgAdmin at: http://localhost:5050
# Login: admin@tws-robot.local / admin
```

**7.3 Verify Paper Trading:**
- Check TWS window for API connection indicator
- Verify account shows paper trading balance
- Monitor for any error messages

---

## 🎯 30-Day Validation Period Starts Now!

Your production deployment is complete. The **30-day validation clock** has started.

### **What Happens During Validation:**

**Daily Monitoring:**
- Check system is running: `Get-Process python`
- Review logs: `Get-Content .\logs\tws_robot_*.log -Tail 100`
- Monitor TWS connection status
- Verify strategies are executing

**Weekly Tasks:**
- Review performance metrics (Sharpe ratio, drawdown, win rate)
- Check database backups: `.\scripts\backup_database.ps1`
- Verify risk limits are being enforced
- Document any issues or observations

**Validation Gates (Must Meet for Live Trading):**
- ✅ 30+ days continuous operation
- ✅ Sharpe Ratio > 1.0
- ✅ Max Drawdown < 10%
- ✅ Win Rate > 50%
- ✅ Zero risk limit violations
- ✅ No system crashes or data loss

---

## 🛠️ Daily Operations

### **Start Production:**
```powershell
.\scripts\start_production.ps1
```

### **Stop Production (Graceful Shutdown):**
```powershell
# Press Ctrl+C in the running terminal, OR:
.\scripts\stop_production.ps1
```

### **Emergency Stop (Immediate Halt):**
```powershell
# Edit .env.production, set:
EMERGENCY_STOP=true

# Or press Ctrl+C and restart
```

### **Backup Database:**
```powershell
.\scripts\backup_database.ps1
```

### **View Logs:**
```powershell
# Real-time tail
Get-Content .\logs\tws_robot_*.log -Wait -Tail 50

# Search for errors
Get-Content .\logs\tws_robot_*.log | Select-String -Pattern "ERROR"
```

### **Check System Status:**
```powershell
# Check if running
Get-Process python

# Check Docker services
docker ps

# Check database
docker exec tws-robot-postgres pg_isready -U tws_user -d tws_robot_prod
```

---

## 🔍 Troubleshooting

### **Issue: TWS Connection Fails**
```powershell
# Verify TWS is running and API enabled
# Check TWS logs
# Verify port 7497 in .env.production
# Test connection: python -c "import socket; socket.create_connection(('127.0.0.1', 7497), timeout=5)"
```

### **Issue: Database Connection Fails**
```powershell
# Check PostgreSQL is running
docker ps | Select-String postgres

# Check database logs
docker logs tws-robot-postgres

# Test connection
docker exec tws-robot-postgres psql -U tws_user -d tws_robot_prod -c "SELECT 1;"
```

### **Issue: Tests Failing**
```powershell
# Run tests with full output
pytest -vv

# Run specific test
pytest tests/test_specific.py -vv

# Check test logs
Get-Content .\logs\pytest.log
```

---

## 📊 Monitoring & Metrics

### **Performance Metrics Location:**
- Database: `tws_robot_prod` → `strategy_metrics` table
- Logs: `./logs/tws_robot_YYYYMMDD.log`
- Backups: `./backups/`

### **Key Metrics to Track:**
- Daily P&L
- Sharpe Ratio (target: > 1.0)
- Max Drawdown (target: < 10%)
- Win Rate (target: > 50%)
- Number of trades
- Risk limit violations (target: 0)

### **Query Metrics from Database:**
```powershell
docker exec tws-robot-postgres psql -U tws_user -d tws_robot_prod -c "
SELECT 
    strategy_name,
    total_trades,
    win_rate,
    sharpe_ratio,
    max_drawdown,
    total_pnl
FROM strategy_metrics
ORDER BY created_at DESC
LIMIT 10;
"
```

---

## 🚀 After 30-Day Validation

Once validation period is complete and all gates pass:

1. Review `SPRINT_PLAN.md` for live trading checklist
2. Switch `PAPER_TRADING=false` in `.env.production`
3. Change `TWS_PORT=7496` (live trading port)
4. Run final test suite
5. Begin with small capital allocation
6. Gradually increase allocation as confidence grows

---

## 📝 Next Steps

Your local production deployment is complete! 

**Immediate:**
- ✅ System is running in production mode
- ✅ 30-day validation clock has started
- ✅ Monitor daily and track metrics

**Future (After Validation):**
- Deploy to AWS (we'll guide you through this later)
- Scale to multiple strategies
- Increase capital allocation
- Add advanced monitoring

**For AWS Deployment Later:**
- Create separate deployment guide
- Use AWS RDS for PostgreSQL
- Use AWS ElastiCache for Redis
- Deploy application to EC2 or ECS
- Set up CloudWatch monitoring
- Configure AWS Secrets Manager

---

## 🆘 Support

If you encounter issues:
1. Check logs: `Get-Content .\logs\tws_robot_*.log -Tail 100`
2. Review `DEPLOYMENT_GUIDE.md` troubleshooting section
3. Check Docker services: `docker ps`
4. Verify TWS API settings
5. Run diagnostic tests: `pytest -vv`

---

**Deployment Date:** November 24, 2025  
**Validation End Date:** ~December 24, 2025  
**Status:** ✅ DEPLOYED - 30-Day Validation In Progress
