# TWS Robot - Your Automated Trading Assistant

**Turn your trading ideas into automated strategies - test them, refine them, deploy them.**

---

## 📚 Documentation Navigation

**You are here:** User Guide - Learn how to use TWS Robot  
**Next steps:** [Examples Guide](EXAMPLES_GUIDE.md) - See working code examples  
**Reference:** [Quick Reference](QUICK_REFERENCE.md) - Commands cheat sheet

**Other guides:**
- [README](README.md) - Quick start and installation
- [Technical Specs](TECHNICAL_SPECS.md) - Architecture for developers
- [Debugging Guide](docs/runbooks/debugging-strategies.md) - Troubleshooting help

---

## 🎯 What is TWS Robot?

TWS Robot is your **automated trading assistant** that connects to your Interactive Brokers account and executes trading strategies for you - while you sleep, work, or live your life.

### Why Use TWS Robot?

**The Problem:**
- You have a trading strategy in mind, but executing it manually is exhausting
- You miss trades because you can't watch the market 24/7
- Your emotions get in the way of following your plan
- You want to test strategies before risking real money

**The Solution - TWS Robot:**
- ✅ **Tests your strategy** on historical data to see if it would have worked
- ✅ **Executes trades automatically** based on your rules
- ✅ **Manages risk** so you don't blow up your account
- ✅ **Tracks performance** so you know what's working
- ✅ **Paper trades first** so you can validate before going live

---

## 🚀 Your First 30 Minutes with TWS Robot

### Goal: Run your first backtest and see if a strategy would have made money

**Step 1: Install (5 minutes)**
```bash
# Download TWS Robot
git clone https://github.com/evanlow/tws_robot.git
cd tws_robot

# Set up Python environment
python -m venv .
.\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
```

**Step 2: Test a Strategy on Historical Data (10 minutes)**

Let's test a classic "Moving Average Crossover" strategy on Apple stock:

```bash
python example_backtest_complete.py
```

**What just happened?**
- TWS Robot tested a strategy on 1 year of Apple stock data
- It showed you: Would you have made money? How much? What was the risk?

**Example Output:**
```
📊 Backtest Results:
Strategy: Moving Average Cross (20/50 day)
Symbol: AAPL
Period: 2023-01-01 to 2024-01-01

💰 Performance:
Total Return: +18.3%
Sharpe Ratio: 1.45 (Good!)
Max Drawdown: -8.2% (Manageable)
Win Rate: 58.3%
Number of Trades: 24

✅ This strategy would have made money!
```

**Step 3: Customize and Compare (15 minutes)**

Now test different strategy settings to find what works best:

```bash
python example_profile_comparison.py
```

This compares:
- **Conservative profile** (smaller positions, tight stops)
- **Balanced profile** (moderate risk)
- **Aggressive profile** (larger positions, wider stops)

See which risk level matches your comfort zone!

---

## 📚 Understanding the Strategies

### 🏗️ Two Types of Strategies

TWS Robot has two strategy locations for different purposes:

**1. Backtest Strategies** (`backtest/strategy_templates.py`)
- **Purpose:** Historical testing and research
- **Available:** MovingAverageCrossStrategy, MeanReversionStrategy, MomentumStrategy
- **Use for:** Testing ideas on past data before committing real capital
- **Examples:** `quick_start.py`, `example_backtest_complete.py`, `example_strategy_templates.py`

**2. Live Trading Strategies** (`strategies/` folder)
- **Purpose:** Paper trading and live trading with Interactive Brokers
- **Available:** BollingerBandsStrategy
- **Use for:** Real-time trading with actual TWS connection
- **Note:** Only deploy strategies here after thorough backtesting

---

### Strategy #1: Moving Average Crossover *(Backtest Only)*
**When to use:** When you believe a stock is trending (going up or down clearly)

**How it works:**
- Calculates two moving averages: a fast one (20 days) and slow one (50 days)
- **BUY signal:** When fast MA crosses above slow MA (trend is turning up)
- **SELL signal:** When fast MA crosses below slow MA (trend is turning down)

**Best for:** Stocks with clear trends (AAPL, MSFT, NVDA)  
**Avoid using:** Stocks that bounce around with no clear direction  
**Status:** 📊 Available for historical backtesting only (not yet enabled for live trading)

**Try it:** The example scripts already use this strategy - just run them!
```bash
# Test this strategy on historical data
python example_backtest_complete.py

# Compare with other strategies
python example_strategy_templates.py
```

**For developers:** Here's how to use it in your own code:
```python
from backtest.strategy_templates import MovingAverageCrossStrategy, MACrossConfig
from backtest.strategy import StrategyConfig

# Set up with $10,000
config = StrategyConfig(initial_capital=10000)
ma_config = MACrossConfig(fast_period=20, slow_period=50)

strategy = MovingAverageCrossStrategy(config, ma_config)
```

### Strategy #2: Mean Reversion *(Backtest Only)*
**When to use:** When you believe a stock that moves away from average will bounce back

**How it works:**
- Calculates average price and standard deviation
- **BUY signal:** When price drops 2 standard deviations below average (oversold)
- **SELL signal:** When price returns to average (take profit)

**Best for:** Stable stocks that don't trend much (utilities, large-cap value stocks)  
**Avoid using:** Stocks that break out to new highs/lows regularly  
**Status:** 📊 Available for historical backtesting only (not yet enabled for live trading)

**Try it:** The example scripts already use this strategy - just run them!
```bash
# Test this strategy on historical data
python example_strategy_templates.py

# Compare different risk profiles
python example_profile_comparison.py
```

**For developers:** Here's how to use it in your own code:
```python
from backtest.strategy_templates import MeanReversionStrategy

config = StrategyConfig(initial_capital=10000)
strategy = MeanReversionStrategy(config)
```

### Strategy #3: Momentum
**When to use:** When you want to ride strong trends (winners keep winning)

**How it works:**
- Measures rate of price change over recent period
- **BUY signal:** When momentum is strongly positive and accelerating
- **SELL signal:** When momentum slows down or turns negative

**Best for:** Growth stocks, tech stocks, trending markets
**Avoid using:** Choppy or declining markets

**Try it:** The example scripts already use this strategy - just run them!
```bash
# Test this strategy on historical data
python example_strategy_templates.py

# Find best strategy for your stock
python strategy_selector.py
```

**For developers:** Here's how to use it in your own code:
```python
from backtest.strategy_templates import MomentumStrategy

config = StrategyConfig(initial_capital=10000)
strategy = MomentumStrategy(config)
```

---

## 🛡️ Risk Management: Don't Blow Up Your Account

TWS Robot includes built-in safety features that you can configure:

### Risk Profiles

Choose your comfort level:

| Profile | Position Size | Stop Loss | Best For |
|---------|--------------|-----------|----------|
| **Conservative** | 2-3% per trade | Tight (5%) | Retirement accounts, low risk tolerance |
| **Balanced** | 5% per trade | Moderate (10%) | Active traders, moderate risk |
| **Aggressive** | 10% per trade | Wide (15%) | Experienced traders, high risk tolerance |

**How to use profiles:**
```python
from backtest.profiles import create_conservative_profile, create_balanced_profile

# Use conservative settings (safer)
profile = create_conservative_profile()

# Or use balanced settings
profile = create_balanced_profile()
```

### Circuit Breakers (Automatic Shutdown)

TWS Robot will **automatically stop trading** if:
- Daily loss exceeds 2% of your account
- Total drawdown exceeds 15%
- Consecutive losses exceed threshold

**This protects you from catastrophic losses.**

---

## 📈 Your TWS Robot Routine

### Weekly Routine (Recommended)

**Monday Morning:**
1. Review last week's performance
2. Check if strategy is still working (markets change!)
3. Adjust position sizes if needed

**Daily (5 minutes):**
1. Glance at dashboard to confirm system is running
2. Check for any alerts or unusual activity

**Monthly:**
1. Run backtests on recent data
2. Compare strategy performance vs. buy-and-hold
3. Decide: Keep running, adjust, or pause

### Commands You'll Use

```bash
# Check your IBKR account status and positions
python check_account.py          # Paper account (default)
python check_account.py live     # Live account

# Check if your strategy would work on recent data
python example_backtest_complete.py

# Compare different risk profiles
python example_profile_comparison.py

# Test strategy on paper trading (fake money)
python tws_client.py --env paper

# Go live (real money!) - only after paper trading success
python tws_client.py --env live
```

---

## ⚠️ Critical Rules for Success

### The Golden Rules

1. **ALWAYS test strategies on historical data first**
   - If it didn't work in the past, it probably won't work now
   
2. **ALWAYS paper trade for at least 30 days**
   - Prove the strategy works in real-time before risking real money
   
3. **NEVER risk more than 1-2% per trade**
   - Professional traders risk 0.5-2% per trade
   - This means you can be wrong 20+ times and still survive
   
4. **NEVER trade strategies you don't understand**
   - If you can't explain the strategy to a friend, don't use it
   
5. **NEVER set it and forget it**
   - Check your system daily (even if just a quick glance)
   - Markets change, strategies stop working

### Warning Signs (Stop Trading Immediately)

Stop trading if you see:
- ❌ 5+ consecutive losses
- ❌ Drawdown exceeding 10%
- ❌ Win rate drops below 40%
- ❌ Sharpe ratio drops below 0.5

**When in doubt, STOP and reassess.**

---

## 🎓 Learning Path

### Week 1: Learn the Basics
- [ ] Run your first backtest
- [ ] Understand what each strategy does
- [ ] Compare risk profiles
- [ ] Read about Sharpe ratio, drawdown, win rate

### Week 2: Get Hands-On
- [ ] Test strategies on different stocks
- [ ] Modify strategy parameters (periods, thresholds)
- [ ] Run paper trading for 1 week
- [ ] Track paper trading results

### Week 3: Optimize
- [ ] Find best strategy for your stocks
- [ ] Choose risk profile that matches your comfort
- [ ] Set up monitoring alerts
- [ ] Practice emergency shutdown

### Week 4: Go Live (If Ready)
- [ ] Paper trading shows consistent profits for 30 days
- [ ] You understand why the strategy works
- [ ] You've tested emergency procedures
- [ ] **Start with small position sizes (1% per trade)**

---

## 🆘 Common Questions

### "How much money can I make?"

**Realistic expectations:**
- Good algorithmic strategy: 10-20% annual return
- Great strategy: 20-30% annual return
- **Anything claiming 50%+ is probably too risky or unrealistic**

**Remember:**
- S&P 500 returns ~10% per year on average
- If you beat that consistently, you're doing great!
- The goal is consistent, sustainable returns - not get-rich-quick

### "Which strategy should I use?"

**Start with Moving Average Crossover** because:
- It's the simplest to understand
- It works on trending stocks
- It's been tested for decades
- Good for learning

**After you're comfortable, try:**
- Mean Reversion for stable stocks
- Momentum for growth stocks

### "How much money do I need to start?"

**Minimum recommended:**
- Paper trading: $0 (it's fake money!)
- Live trading: $5,000-$10,000

**Why?**
- You need enough to diversify across 2-3 positions
- Interactive Brokers has a $100 minimum per trade
- Smaller accounts get eaten up by commissions

### "What if the strategy stops working?"

**Strategies DO stop working** as markets change. This is normal.

**What to do:**
1. Check if markets have changed (trending vs. choppy)
2. Run new backtests on recent data
3. Consider adjusting parameters
4. If nothing works, pause and reassess

**Rule of thumb:** If a strategy loses money for 2 months straight, stop using it.

### "Can I run multiple strategies at once?"

**Yes!** In fact, this is recommended:
- Diversify your approach
- Some strategies work in trending markets, others in choppy markets
- Reduces reliance on one approach

**Example portfolio:**
- 50% Moving Average Crossover (trends)
- 30% Mean Reversion (bounces)
- 20% Momentum (growth)

### "Do I need to be a programmer?"

**No, but it helps!**

**You CAN use TWS Robot if you:**
- Can copy/paste commands into a terminal
- Can edit simple configuration files
- Can read performance reports

**You CANNOT (yet) if you:**
- Want a point-and-click GUI interface (we don't have that yet)
- Want to avoid any coding (you'll need to run Python scripts)

**Future plans:** We're working on a web dashboard to make this easier!

---

## � Understanding the Example Scripts

### `example_profile_comparison.py`

**What it does:** Runs 6 comprehensive examples comparing different risk profiles (conservative, moderate, aggressive) to help you find the best risk settings for your strategy.

**When you run it:**

1. **Example 1 - Basic Comparison**: Tests all three standard risk profiles on AAPL, MSFT, GOOGL for 2023, showing which performed best overall.

2. **Example 2 - Two-Profile Details**: Deep dive comparing conservative vs aggressive profiles on SPY and QQQ, showing metric-by-metric differences.

3. **Example 3 - Optimization Insights**: Provides actionable recommendations based on comparison results.

4. **Example 4 - Custom Profiles**: Demonstrates creating custom risk profiles (ultra_conservative, high_growth) and comparing them.

5. **Example 5 - Ranking System**: Explains how profiles are ranked (1=best, N=worst) across four metrics: Sharpe ratio, returns, drawdown, and win rate.

6. **Example 6 - Summary Statistics**: Shows mean and standard deviation across profiles to understand performance distribution.

**Important Notes:**
- Script pauses between examples (press Enter to continue)
- **Requires market data connection** - will show error messages if data unavailable
- Best used after you understand basic backtesting
- Helps answer: "Should I use conservative or aggressive settings?"

**Example output:**
```
✅ Best Overall Profile: moderate
Average Sharpe: 1.24
Return Std Dev: 0.08 (Low variability - similar performance)
```

### `example_backtest_complete.py`

**What it does:** Complete end-to-end backtest demonstration showing how to test a strategy on historical data.

**When you run it:** Executes a full backtest with performance metrics, trade analysis, and visual reports.

**Use this when:** You want to see if a strategy would have made money historically.

### `example_strategy_templates.py`

**What it does:** Shows all available pre-built strategies and how to use them.

**When you run it:** Demonstrates each strategy template with example code and parameter options.

**Use this when:** You're choosing which strategy to implement.

---

## �🛠️ Next Steps

### Ready to Get Started?

1. **Read the Quick Start (30 minutes)** - See if a strategy would have made money
2. **Choose Your Strategy** - Moving Average is easiest to start
3. **Pick a Risk Profile** - Conservative is safest
4. **Start Paper Trading** - Run for 30 days minimum
5. **Track and Learn** - Keep a trading journal
6. **Go Live Carefully** - Start with 1% position sizes

### Need Help?

- 📖 **Read the Docs:** Full technical docs in `/docs` folder
- 🐛 **Found a Bug?** Open an issue on GitHub
- 💡 **Have an Idea?** We love suggestions!

### Join the Community

*[Link to Discord/Forum/Community]* (if available)

---

## 🚨 Final Warning

**Algorithmic trading is not a guaranteed way to make money.**

- You can lose money (sometimes a lot)
- Past performance doesn't predict future results
- Start small, learn, and scale gradually
- Never trade with money you can't afford to lose

**But done right:**
- It's a systematic way to trade
- It removes emotion from decisions
- It lets you test ideas objectively
- It can be a valuable tool in your investing toolkit

---

**Ready? Let's trade smarter, not harder. 🚀**
