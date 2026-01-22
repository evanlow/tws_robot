# TWS Robot - Quick Reference Cheat Sheet

**Your go-to guide for common commands and workflows.**

---

## 🚀 Quick Commands

### Getting Started
```bash
# Activate environment (ALWAYS do this first!)
.\Scripts\Activate.ps1  # Windows
source bin/activate     # Mac/Linux

# Your first backtest
python quick_start.py

# Find a strategy for your stock
python strategy_selector.py
```

### Testing Strategies
```bash
# Compare all strategies
python example_strategy_templates.py

# Compare risk profiles (Conservative vs. Aggressive)
python example_profile_comparison.py

# Full backtest with analytics
python example_backtest_complete.py
```

### Trading
```bash
# Check your IBKR account status
python check_account.py          # Paper account (default)
python check_account.py paper    # Paper account
python check_account.py live     # Live account

# Paper trading (ALWAYS start here!)
python tws_client.py --env paper --timeout 30

# Check market status
python market_status.py

# Live trading (BE CAREFUL!)
python tws_client.py --env live --timeout 60
```

---

## 📊 Strategy Quick Guide

| Strategy | When to Use | Best Stocks | Config |
|----------|-------------|-------------|--------|
| **Moving Average** | Clear trends up/down | AAPL, MSFT, NVDA | `fast_period=20, slow_period=50` |
| **Mean Reversion** | Choppy, range-bound | KO, PG, JNJ | `period=20, std_dev=2.0` |
| **Momentum** | Strong trends, volatile | TSLA, growth stocks | `period=14, threshold=0.02` |

### Quick Decision Tree

```
Is the stock trending clearly?
├─ YES → Try Moving Average Crossover
└─ NO (choppy) → Try Mean Reversion

Is the stock very volatile?
├─ YES → Try Momentum
└─ NO → Try Moving Average or Mean Reversion

What type of stock?
├─ Blue chip (AAPL, MSFT) → Moving Average
├─ Dividend stock (KO, PG) → Mean Reversion
└─ Growth stock (NVDA, TSLA) → Momentum
```

---

## 🛡️ Risk Profile Quick Reference

| Profile | Position Size | Stop Loss | Best For |
|---------|---------------|-----------|----------|
| **Conservative** | 2-3% | 5% | Retirement, low risk tolerance |
| **Balanced** | 5% | 10% | Active traders, moderate risk |
| **Aggressive** | 10% | 15% | Experienced, high risk tolerance |

**How to use:**
```python
from backtest.profiles import (
    create_conservative_profile,
    create_balanced_profile,
    create_aggressive_profile
)

profile = create_balanced_profile()  # Change this to your preference
```

---

## 📈 Understanding Your Results

### Metrics at a Glance

| Metric | Excellent | Good | Fair | Poor |
|--------|-----------|------|------|------|
| **Total Return** | >20% | 10-20% | 5-10% | <5% |
| **Sharpe Ratio** | >2.0 | 1.0-2.0 | 0.5-1.0 | <0.5 |
| **Max Drawdown** | <10% | 10-15% | 15-20% | >20% |
| **Win Rate** | >60% | 50-60% | 40-50% | <40% |

### Quick Assessment

**Strategy is working if:**
- ✅ Total return beats S&P 500 (~10% annually)
- ✅ Sharpe ratio > 1.0
- ✅ Max drawdown < 15%
- ✅ Win rate > 45%

**Stop trading if:**
- ❌ 5+ consecutive losses
- ❌ Drawdown > 10%
- ❌ 2 months of losses
- ❌ Sharpe ratio < 0.5

---

## ⚠️ Safety Checklist

### Before Paper Trading
- [ ] Backtested on at least 1 year of data
- [ ] Sharpe ratio > 1.0
- [ ] Max drawdown < 20%
- [ ] Understand WHY the strategy works
- [ ] Know your stop loss points

### Before Live Trading
- [ ] Paper traded successfully for 30+ days
- [ ] Paper trading beat buy-and-hold
- [ ] Risk controls tested and working
- [ ] Emergency shutdown procedure practiced
- [ ] Starting with small position sizes (1-2%)
- [ ] Can afford to lose this money

### Daily Monitoring (5 minutes)
- [ ] Check positions and P&L
- [ ] Verify no unusual errors
- [ ] Confirm strategy still executing
- [ ] Review any alerts

### Weekly Review (30 minutes)
- [ ] Calculate week's return
- [ ] Compare to expectations
- [ ] Check if strategy still working on recent data
- [ ] Adjust position sizes if needed

---

## 🔧 Configuration Quick Reference

### Environment Variables (.env file)

```env
# Switch between paper and live
TRADING_ENV=paper           # or 'live'

# Paper Trading (default IB ports)
PAPER_HOST=127.0.0.1
PAPER_PORT=7497
PAPER_CLIENT_ID=0
PAPER_ACCOUNT=DU2746208     # Your paper account

# Live Trading
LIVE_HOST=127.0.0.1
LIVE_PORT=7496              # Different port for live!
LIVE_CLIENT_ID=1
LIVE_ACCOUNT=U12345678      # Your live account
```

### TWS Setup Checklist
- [ ] TWS or IB Gateway running
- [ ] API enabled: File → Global Config → API → Settings
- [ ] Socket port correct (7497=paper, 7496=live)
- [ ] "Enable ActiveX and Socket Clients" checked
- [ ] 127.0.0.1 added to trusted IPs

---

## 🐛 Troubleshooting Quick Fixes

### "Connection failed"
```bash
# Check TWS is running
# Verify correct port in .env (7497 for paper, 7496 for live)
# Restart TWS and try again
python tws_client.py --show-config  # Verify settings
```

### "No historical data"
```bash
# Download sample data
python download_real_data.py

# Or check data/ folder exists
ls data/historical/
```

### "Module not found" errors
```bash
# Make sure you're in virtual environment
python -c "import sys; print(sys.executable)"
# Should show: .../tws_robot/Scripts/python.exe

# If not, activate it
.\Scripts\Activate.ps1
```

### "Tests failing"
```bash
# Run tests to see what's wrong
pytest -v

# If packages missing
pip install -r requirements.txt

# If still failing, check you're in venv
```

---

## 📚 Documentation Quick Links

| Need to... | Read this... |
|------------|-------------|
| Understand strategies | [USER_GUIDE.md](USER_GUIDE.md) - Strategy section |
| Learn risk management | [USER_GUIDE.md](USER_GUIDE.md) - Risk section |
| Set up TWS connection | [README.md](README.md) - Installation section |
| Add a new strategy | [docs/runbooks/adding-new-strategy.md](docs/runbooks/adding-new-strategy.md) |
| Debug issues | [docs/runbooks/debugging-strategies.md](docs/runbooks/debugging-strategies.md) |
| Emergency procedures | [docs/runbooks/emergency-procedures.md](docs/runbooks/emergency-procedures.md) |
| System architecture | [docs/architecture/overview.md](docs/architecture/overview.md) |

---

## 💡 Pro Tips

### Testing
- Test on at least 1 year of historical data
- Test on multiple stocks (3-5 minimum)
- Test different market conditions (bull, bear, sideways)
- Compare to simple buy-and-hold benchmark

### Risk Management
- Never risk more than 1-2% per trade
- Use stop losses on every position
- Diversify across 3-5 positions
- Keep 20-30% cash for opportunities

### Monitoring
- Check daily (even if just 1 minute)
- Review weekly performance vs. plan
- Re-backtest monthly on recent data
- Be ready to stop a failing strategy quickly

### Going Live
- Start with 25% of intended capital
- Use 1% position sizes initially
- Paper trade in parallel for comparison
- Scale up slowly over 3-6 months

---

## 🚨 Emergency Commands

### Stop Everything NOW
```bash
# In Python/terminal: Ctrl+C (immediately stops)

# Or if that doesn't work:
# Windows: Close TWS/IB Gateway
# This disconnects all API clients
```

### Check What's Running
```bash
# Show current positions
# (In TWS: Portfolio tab)

# Check recent trades
# (In TWS: Trades tab)
```

### Manual Override
```bash
# Close all positions manually in TWS
# Go to: Portfolio → Right-click position → Close Position

# Or use Liquidate All button (nuclear option!)
```

---

## 📞 Need Help?

**Before asking for help, try:**
1. Read error message carefully
2. Check this cheat sheet
3. Review [USER_GUIDE.md](USER_GUIDE.md)
4. Search existing GitHub issues

**When asking for help, include:**
- What you were trying to do
- Exact command you ran
- Full error message
- Your configuration (hide account IDs!)

**Never share:**
- Your account numbers
- Your API keys
- Your `.env` file

---

**Happy Trading! 🚀**

*Remember: Slow and steady wins the race. Test thoroughly, start small, and scale gradually.*
