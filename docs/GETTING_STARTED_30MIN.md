# Your First 30 Minutes with TWS Robot

**Goal:** Go from zero to exploring the web dashboard and running your first backtest in 30 minutes.

---

## ⏱️ Time Budget

- **Minutes 0-5:** Installation
- **Minutes 5-10:** Launch the web dashboard and explore
- **Minutes 10-15:** Choose your strategy
- **Minutes 15-25:** Run your first backtest
- **Minutes 25-30:** Understand your results

Let's go! 🚀

---

## Minutes 0-5: Installation ✓

### Step 1: Get the Code
```bash
# Clone the repository
git clone https://github.com/evanlow/tws_robot.git
cd tws_robot
```

### Step 2: Set Up Python Environment
```bash
# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\Activate.ps1  # Windows PowerShell
source venv/bin/activate      # Mac/Linux
```

### Step 3: Install Dependencies
```bash
# Install required packages (takes 2-3 minutes)
pip install -r requirements.txt
```

**✅ Checkpoint:** You should see "Successfully installed..." messages.

---

## Minutes 5-10: Launch the Web Dashboard

### Start the Dashboard

```bash
python scripts/run_web.py
```

Open your browser to **http://127.0.0.1:5000**. You'll see the TWS Robot dashboard!

### What You'll See

The web dashboard gives you a bird's-eye view of everything:
- **Top Status Bar** — Connection status, equity, daily P&L, risk level, and an **Emergency Stop** button
- **Navigation Menu** — Dashboard, Strategies, Backtest, Positions, Risk, Logs, Settings
- **Dashboard Page** — Active strategies, portfolio overview, recent trades, and alerts

> 💡 **Don't worry** if it shows "Disconnected" — you don't need TWS connected for backtesting!

### TWS Robot Has 2 Modes

**📊 Mode 1: Backtesting** (what you'll do today)
- Test strategies on historical data
- See if they would have made money
- Zero risk, learn how strategies work
- **No TWS/Interactive Brokers required**

**🤖 Mode 2: Live Trading** (future)
- Execute real trades through Interactive Brokers
- Requires TWS running and account setup
- Start with paper trading, then real money

**Today's focus:** Backtesting. You'll test a strategy on Apple stock to see if it would have made money in 2023.

### What Strategies Are Available?

| Strategy | When It Works Best | Your Stock Type |
|----------|-------------------|-----------------|
| **Moving Average** | Clear trends up/down | AAPL, MSFT, NVDA |
| **Mean Reversion** | Choppy, range-bound | KO, PG, JNJ |
| **Momentum** | Strong trends, volatile | TSLA, growth stocks |

**Think about a stock you're interested in.** Is it trending or choppy? Volatile or stable?

---

## Minutes 10-15: Choose Your Strategy

### Option A: Let TWS Robot Decide (Recommended)

```bash
# Interactive strategy selector
python scripts/strategy_selector.py
```

**You'll answer:**
- What stock? (e.g., `AAPL`)
- Risk tolerance? (Conservative/Moderate/Aggressive)
- Market outlook? (Trending/Range-bound)

**Output:** Recommended strategy with explanation.

### Option B: Run the Default

If you want to jump straight in:
```bash
# Test Moving Average on AAPL
python scripts/quick_start.py
```

This tests a Moving Average strategy on AAPL from 2022-2023.

**Choose one and run it!**

---

## Minutes 15-25: Run Your First Backtest

### What's Happening?

When you run the backtest, TWS Robot:
1. Loads historical price data for your stock
2. Simulates trading day-by-day
3. Executes buy/sell signals based on strategy rules
4. Tracks all trades and portfolio value
5. Calculates performance metrics

### What You'll See

```
Running backtest...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:08

Strategy: Moving Average Crossover
Period: 2022-01-01 to 2023-12-31
Symbol: AAPL
Initial Capital: $100,000

Results:
═══════════════════════════════════════════════
Total Return:        +18.7%
Sharpe Ratio:        1.52
Max Drawdown:        -8.1%
Win Rate:            56.7%
Total Trades:        28
Winning Trades:      16
Losing Trades:       12
Average Win:         +$2,340
Average Loss:        -$980
Profit Factor:       2.39
═══════════════════════════════════════════════

✅ Strategy would have been profitable!

Final Portfolio Value: $118,700
Benchmark (Buy & Hold): $115,200
Strategy Beat Benchmark: +$3,500 (+3.0%)
```

**✅ Checkpoint:** Did you see results? Great! Now let's understand them.

---

## Minutes 25-30: Understand Your Results

### What Do These Numbers Mean?

**Total Return: +18.7%**
- Your $100,000 became $118,700
- That's an 18.7% gain in 2 years
- Compare to S&P 500: ~15% in 2023 (you beat it!)

**Sharpe Ratio: 1.52**
- Measures risk-adjusted returns
- **> 1.0 = Good** (you have 1.52 ✓)
- **> 2.0 = Excellent**
- **< 0.5 = Poor**
- Higher is better - means good returns without crazy risk

**Max Drawdown: -8.1%**
- Worst peak-to-trough loss
- Your account dropped 8.1% at one point
- **< 10% = Good** (you're at 8.1% ✓)
- **< 15% = Acceptable**
- **> 20% = Risky**
- Lower is better - shows you didn't lose too much during bad times

**Win Rate: 56.7%**
- 56.7% of your trades were profitable
- **> 50% = Positive** (you're at 56.7% ✓)
- **> 60% = Great**
- Don't obsess over this - a 40% win rate with big wins can be better than 60% win rate with small wins

**Total Trades: 28**
- You made 28 trades over 2 years (~1 per month)
- Not too many (overtrading), not too few (missing opportunities)

**Profit Factor: 2.39**
- For every $1 you lost, you made $2.39
- **> 1.5 = Good** (you have 2.39 ✓)
- **> 2.0 = Excellent** (you did it!)

### Is This Good?

**Your Results:**
- ✅ Beat buy-and-hold by 3%
- ✅ Sharpe > 1.0 (good risk-adjusted returns)
- ✅ Drawdown < 10% (controlled risk)
- ✅ Win rate > 50% (more winners than losers)
- ✅ Profit factor > 2.0 (big wins, small losses)

**Verdict: This is a SOLID strategy!** 🎉

### What Made It Work?

Look at the trades breakdown:
- **Average Win:** $2,340
- **Average Loss:** $980

The strategy:
1. Cuts losses quickly (average loss only $980)
2. Lets winners run (average win $2,340 - 2.4x bigger!)
3. Wins slightly more often (56.7%)

**This is the holy grail:** Small losses, big wins, consistent execution.

---

## 🎉 Congratulations! You've Completed the Basics

**In 30 minutes, you:**
- ✅ Installed TWS Robot
- ✅ Learned about backtesting vs live trading
- ✅ Chose and ran a strategy
- ✅ Interpreted professional performance metrics
- ✅ Determined if a strategy is worth pursuing

---

## 🚀 What's Next?

### Immediate Next Steps (Next 30 Minutes)

**1. Test on Different Stocks**
```bash
# Edit scripts/quick_start.py to change symbol
# Change 'AAPL' to 'MSFT', 'GOOGL', etc.
python scripts/quick_start.py
```

**Does the strategy work on multiple stocks?** If yes, that's more confidence!

**2. Test Different Time Periods**
```bash
# Edit dates in scripts/quick_start.py
# Try 2021, 2020, bull market vs bear market
```

**Does it work in different market conditions?** That's the real test.

**3. Compare Strategies**
```bash
# Test all 3 strategies side-by-side
python examples/example_strategy_templates.py
```

**Which strategy works best for your stock?**

### This Week

**Days 1-2:** Test multiple stocks and time periods
**Days 3-4:** Compare different strategies
**Days 5-7:** Pick the best strategy and understand why it works

**Read:** [USER_GUIDE.md](USER_GUIDE.md) for deep strategy explanations

### Next Week

**If results are consistently good:**
- Learn about risk profiles (Conservative/Moderate/Aggressive)
- Run `python examples/example_profile_comparison.py`
- Choose risk level that matches your comfort

**Read:** [EXAMPLES_GUIDE.md](EXAMPLES_GUIDE.md) for all example scripts

### Week 3-4

**If you want to paper trade:**
1. **Follow the [TWS Connection Guide](TWS_CONNECTION_GUIDE.md)** — step-by-step instructions to install TWS, configure the API, and connect
2. Set up Interactive Brokers paper account (free)
3. Install TWS (Trader Workstation)
4. Connect TWS Robot to paper trading
5. Let it trade with fake money

**Read:** [TWS Connection Guide](TWS_CONNECTION_GUIDE.md) for complete setup, then [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for 30-day validation

### Month 2+

**If paper trading goes well:**
- Start with 25% of intended capital
- Use 1% position sizes initially
- Monitor daily
- Scale up slowly over 3-6 months

**Read:** Risk management sections in [USER_GUIDE.md](USER_GUIDE.md)

---

## 💡 Pro Tips from 30 Minutes of Experience

### What You Learned

1. **Backtesting is fast** - 2 years of trading in 8 seconds
2. **Good strategies are consistent** - Work across stocks and time periods
3. **Risk-adjusted returns matter** - Not just total return, but how you got there
4. **Small losses, big wins** - The secret to profitable trading

### Common Mistakes to Avoid

**❌ Don't:** Pick a strategy because it has the highest return
**✅ Do:** Pick a strategy with good Sharpe ratio and low drawdown

**❌ Don't:** Test on only one stock or time period
**✅ Do:** Test on 5+ stocks and 2+ years

**❌ Don't:** Rush to live trading
**✅ Do:** Paper trade for 30+ days first

**❌ Don't:** Risk more than 1-2% per trade
**✅ Do:** Use position sizing and stop losses

---

## 🆘 Troubleshooting

### "No module named 'backtest'"
```bash
# Make sure virtual environment is activated
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # Mac/Linux

# Reinstall if needed
pip install -r requirements.txt
```

### "No data available"
```bash
# Download historical data
python scripts/download_real_data.py AAPL MSFT GOOGL
```

### "Script hangs or runs forever"
- Press `Ctrl+C` to stop
- Check if you have enough RAM (needs ~500MB)
- Try fewer symbols or shorter time period

### Still stuck?
1. Read error message carefully (usually tells you what's wrong)
2. Check [QUICK_REFERENCE.md](QUICK_REFERENCE.md) troubleshooting section
3. See [Debugging Guide](runbooks/debugging-strategies.md)

---

## 📚 Key Documentation for Your Journey

**Right now:** You are here! 🎯
- [README.md](README.md) - Project overview

**Today/this week:**
- [USER_GUIDE.md](USER_GUIDE.md) - Understand strategies deeply
- [EXAMPLES_GUIDE.md](EXAMPLES_GUIDE.md) - All example scripts explained

**When ready to trade:**
- [TWS Connection Guide](TWS_CONNECTION_GUIDE.md) - Connect to Interactive Brokers
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Command cheat sheet
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 30-day validation

**For developers:**
- [API_REFERENCE.md](API_REFERENCE.md) - Build custom strategies
- [Architecture Docs](architecture/) - System design

---

## 🎯 Success Criteria

**You'll know you're ready for next steps when:**

**Ready for different stocks:**
- [ ] Tested strategy on 5+ different stocks
- [ ] Understand why some stocks work better than others
- [ ] Can explain the strategy to a friend

**Ready for paper trading:**
- [ ] Sharpe ratio > 1.0 consistently
- [ ] Max drawdown < 15% consistently
- [ ] Works across 2+ years of data
- [ ] Works in bull AND bear markets
- [ ] You understand WHY the strategy works

**Ready for live trading:**
- [ ] Paper traded successfully for 30+ days
- [ ] Paper results match backtest expectations
- [ ] You've practiced emergency stop procedures
- [ ] You can afford to lose this money
- [ ] You're not emotionally attached to the outcome

---

## 🏆 You're Off to a Great Start!

**Remember:**
- Slow and steady wins the race
- Test thoroughly before risking real money
- Every successful trader started exactly where you are now
- The best strategy is the one you can stick with

**Welcome to algorithmic trading! 🚀**

---

**Next:** [USER_GUIDE.md](USER_GUIDE.md) to learn strategy details  
**Help:** [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for quick commands  
**Questions:** Check [Debugging Guide](runbooks/debugging-strategies.md)
