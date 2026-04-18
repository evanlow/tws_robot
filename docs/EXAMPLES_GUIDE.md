# TWS Robot - Examples Guide

**Detailed explanations of what each example script does and when to use it.**

---

## 🎯 Purpose of This Guide

Each example script in TWS Robot demonstrates specific functionality. This guide explains:
- **What happens** when you run the script
- **What you'll see** in the output
- **When to use it** in your workflow
- **Common issues** and how to resolve them

---

## 📚 Documentation Navigation

**You are here:** Examples Guide - Detailed script explanations  
**New user?** [Your First 30 Minutes](GETTING_STARTED_30MIN.md) - Complete beginner tutorial ⭐  
**Start here:** [README](../README.md) - Installation and quick start  
**Learn concepts:** [User Guide](USER_GUIDE.md) - Strategy explanations  
**Quick lookup:** [Quick Reference](QUICK_REFERENCE.md) - Commands cheat sheet

**Need help?**
- [API Reference](API_REFERENCE.md) - Developer documentation
- [Contributing](CONTRIBUTING.md) - How to contribute
- [Debugging Guide](runbooks/debugging-strategies.md) - Troubleshooting
- [Architecture Docs](architecture/overview.md) - System design

---

## 🔗 Connection and Account Management

### `check_account.py`

**Purpose:** Connect to your IBKR account and display current status, positions, and account values.

**Usage:**
```bash
python scripts/check_account.py          # Check paper account (default)
python scripts/check_account.py paper    # Check paper account (explicit)
python scripts/check_account.py live     # Check live account
```

**What You'll See:**
```
======================================================================
IBKR ACCOUNT STATUS CHECK
======================================================================
Time: 2026-01-23 15:30:45

Environment: LIVE
Connecting to: 127.0.0.1:7496
Account: U6801816

Connecting...
[OK] Connected to TWS/Gateway
Downloading account data...

======================================================================
ACCOUNT STATUS FOR: U6801816
======================================================================

Account Values:
  TotalCashBalance         : $23,076.43
  CashBalance              : $23,076.43
  AvailableFunds           : $15,234.56
  BuyingPower              : $60,938.24
  GrossPositionValue       : $20,035.18
  UnrealizedPnL            : $11,230.66
  RealizedPnL              : $0.00
  Cushion                  : $0.90

Current Positions (6):
----------------------------------------------------------------------
  Symbol: SPY, Position: 50 shares
  Symbol: QQQ, Position: 30 shares
  Symbol: AAPL, Position: 100 shares
  ...

======================================================================
STATUS CHECK COMPLETE
======================================================================
```

**What This Tells You:**
- **TotalCashBalance**: Cash available in account
- **UnrealizedPnL**: Current profit/loss on open positions (positive means up)
- **Cushion**: Margin health (0.90 = 90% cushion, very healthy)
- **Current Positions**: What you currently own

**Use This When:**
- Starting your trading day (quick status check)
- Verifying connection to TWS before running strategies
- Checking position sizes before deploying new trades
- Monitoring account health (margin, cushion)

**Requirements:**
- TWS or IB Gateway must be running
- Paper account: TWS on port 7497
- Live account: TWS on port 7496
- API connections enabled in TWS settings

---

## 📊 Profile Comparison Examples

### `example_profile_comparison.py`

**Purpose:** Compare different risk profiles (conservative, moderate, aggressive) to determine which settings match your risk tolerance and goals.

#### What Happens When You Run It:

The script runs **6 sequential examples**, pausing between each for you to review results:

#### Example 1: Basic Comparison
**What it does:**
- Tests SimpleMomentumStrategy on AAPL, MSFT, GOOGL
- Compares all three standard profiles (conservative, moderate, aggressive)
- Shows performance for 2023 with $100,000 initial capital

**Output you'll see:**
```
Comparing 3 profiles...
Strategy: SimpleMomentumStrategy
Period: 2023-01-01 to 2023-12-31
Symbols: AAPL, MSFT, GOOGL
Initial Capital: $100,000.00

Profile Performance:
┌──────────────┬──────────┬────────┬──────────┬──────────┐
│ Profile      │ Return   │ Sharpe │ Drawdown │ Win Rate │
├──────────────┼──────────┼────────┼──────────┼──────────┤
│ Conservative │ +12.3%   │ 1.45   │ -5.2%    │ 58.3%    │
│ Moderate     │ +18.7%   │ 1.52   │ -8.1%    │ 56.7%    │
│ Aggressive   │ +23.4%   │ 1.38   │ -12.4%   │ 54.2%    │
└──────────────┴──────────┴────────┴──────────┴──────────┘

✅ Best Overall Profile: moderate
```

**What this tells you:**
- **Conservative**: Lower returns but safer (smaller drawdown)
- **Moderate**: Best risk-adjusted returns (highest Sharpe)
- **Aggressive**: Highest returns but more volatile

**Use this when:** You're deciding which risk profile matches your comfort level.

---

#### Example 2: Two-Profile Detailed Comparison
**What it does:**
- Deep comparison of conservative vs aggressive profiles
- Shows exact differences for each metric
- Tests on SPY and QQQ (index ETFs)

**Output you'll see:**
```
CONSERVATIVE vs AGGRESSIVE
════════════════════════════════════════════════════════════

Sharpe Ratio:
  Conservative: 1.4500
  Aggressive:   1.3800
  Difference:   +0.0700
  Winner: conservative

Total Return:
  Conservative: 0.1230
  Aggressive:   0.2340
  Difference:   -0.1110
  Winner: aggressive

Max Drawdown:
  Conservative: -0.0520
  Aggressive:   -0.1240
  Difference:   +0.0720
  Winner: conservative

Win Rate:
  Conservative: 0.5830
  Aggressive:   0.5420
  Difference:   +0.0410
  Winner: conservative
```

**What this tells you:**
- Conservative wins on risk metrics (Sharpe, drawdown, win rate)
- Aggressive wins on absolute returns
- You need to choose: safety vs. higher returns

**Use this when:** You're torn between two profiles and need detailed comparison.

---

#### Example 3: Optimization Insights
**What it does:**
- Analyzes all three profiles
- Provides actionable recommendations

**Output you'll see:**
```
OPTIMIZATION INSIGHTS
════════════════════════════════════════════════════════════

1. Moderate profile offers best risk-adjusted returns (Sharpe: 1.52)
2. Conservative profile has lowest drawdown (-5.2%) - best for risk-averse
3. Aggressive profile has highest returns (+23.4%) but 2.4x drawdown
4. Win rates are similar across profiles (54-58%) - strategy is consistent
5. Consider moderate profile for balanced approach
```

**Use this when:** You want guidance on which profile to choose.

---

#### Example 4: Custom Profile Comparison
**What it does:**
- Creates two custom profiles: ultra_conservative and high_growth
- Compares them against standard profiles
- Shows how to define custom risk parameters

**Custom profiles created:**
```python
ultra_conservative = {
    'max_position_size_pct': 0.05,     # Only 5% per position
    'max_portfolio_risk_pct': 0.005,   # 0.5% max portfolio risk
    'max_total_exposure_pct': 0.40,    # Only 40% invested
    'stop_loss_pct': 0.01,             # Tight 1% stops
    'take_profit_pct': 0.02            # Take profit at 2%
}

high_growth = {
    'max_position_size_pct': 0.30,     # 30% per position
    'max_portfolio_risk_pct': 0.04,    # 4% max portfolio risk
    'max_total_exposure_pct': 0.95,    # 95% invested
    'stop_loss_pct': 0.06,             # Wider 6% stops
    'take_profit_pct': 0.15            # Take profit at 15%
}
```

**Output shows all 5 profiles compared.**

**Use this when:** 
- Standard profiles don't match your needs
- You want very specific risk parameters
- You're experienced and know exactly what you want

---

#### Example 5: Interpreting Rankings
**What it does:**
- Explains the ranking system (1=best, N=worst)
- Shows rankings for each profile across 4 metrics

**Output you'll see:**
```
Ranking System Explanation:
• Rankings are assigned from 1 (best) to N (worst)
• Four key metrics are ranked:
  - Sharpe Ratio (risk-adjusted returns)
  - Total Return (absolute performance)
  - Max Drawdown (downside risk)
  - Win Rate (consistency)

CONSERVATIVE:
  Sharpe Rank:    1  ⭐ Best risk-adjusted
  Return Rank:    3  ❌ Lowest returns
  Drawdown Rank:  1  ⭐ Safest
  Win Rate Rank:  1  ⭐ Most consistent
  Average Rank:   1.50

MODERATE:
  Sharpe Rank:    2
  Return Rank:    2
  Drawdown Rank:  2
  Win Rate Rank:  2
  Average Rank:   2.00

AGGRESSIVE:
  Sharpe Rank:    3
  Return Rank:    1  ⭐ Highest returns
  Drawdown Rank:  3  ❌ Most risky
  Win Rate Rank:  3
  Average Rank:   2.50

Best profile has the lowest average rank
```

**What this tells you:**
- Lower average rank = more balanced performance
- Profiles can excel at some metrics while failing at others
- Choose based on which metrics matter most to you

**Use this when:** You want to understand relative performance across metrics.

---

#### Example 6: Summary Statistics
**What it does:**
- Shows mean and standard deviation across all profiles
- Helps understand if profile choice matters significantly

**Output you'll see:**
```
Summary Statistics:
────────────────────────────────────────────────────────────
Sharpe Mean: 1.4167
Sharpe Std: 0.0624
Return Mean: 0.1813
Return Std: 0.0464
Drawdown Mean: -0.0853
Drawdown Std: 0.0298
Win Rate Mean: 0.5633
Win Rate Std: 0.0174

Interpretation:
────────────────────────────────────────────────────────────
• Low Sharpe variability - Similar risk-adjusted performance
• Low return variability - Conservative approach may be sufficient
```

**What this tells you:**
- **High Std Dev** = Profile choice matters significantly
- **Low Std Dev** = Profiles perform similarly; choose based on risk tolerance
- Helps decide if you need to optimize profile or if any will work

**Use this when:** You want statistical understanding of profile differences.

---

### 🚨 Common Issues with Profile Comparison

#### Issue 1: "This example requires real market data to run"

**Cause:** Script cannot connect to market data source or data is unavailable.

**Solution:**
1. Ensure TWS/Gateway is running
2. Check connection settings in config files
3. Verify you have historical data for the symbols
4. Try simpler symbols (SPY, QQQ) instead of individual stocks

#### Issue 2: Script runs but shows no differences

**Cause:** Strategy doesn't respond to profile differences.

**Solution:**
- Some strategies are position-size independent
- Try different strategy templates
- Use symbols with higher volatility

#### Issue 3: All profiles show losses

**Cause:** Strategy doesn't work for the time period/symbols tested.

**Solution:**
- This is valuable information! The strategy isn't suitable
- Try different time periods
- Try different symbols
- Consider different strategy templates

---

## 📈 Backtest Examples

### `example_backtest_complete.py`

**Purpose:** Run a complete backtest to see if a strategy would have made money on historical data.

**What happens when you run it:**
1. Loads historical price data for specified symbols
2. Executes strategy rules on each bar of data
3. Tracks all trades, positions, and portfolio value
4. Calculates performance metrics
5. Generates detailed reports

**Output includes:**
- Total return percentage
- Sharpe ratio (risk-adjusted returns)
- Maximum drawdown (worst peak-to-trough loss)
- Win rate (percentage of profitable trades)
- Number of trades executed
- Trade-by-trade breakdown

**Use this when:**
- Testing if a strategy would have worked historically
- Optimizing strategy parameters
- Comparing strategy performance across time periods

---

## 🎨 Strategy Template Examples

### `example_strategy_templates.py`

**Purpose:** Learn about all available pre-built strategies and how to use them.

**What happens when you run it:**
- Shows each strategy template
- Explains when to use each strategy
- Demonstrates configuration options
- Provides example code for each

**Strategies covered:**
1. **Moving Average Crossover**: Trend-following strategy
2. **Mean Reversion**: Buy oversold, sell overbought
3. **Momentum**: Ride strong trends

**Use this when:**
- Choosing which strategy to implement
- Learning about strategy parameters
- Understanding strategy logic

---

## 🔬 Performance Analytics Examples

### `example_performance_analytics.py`

**Purpose:** Deep dive into performance analysis tools.

**What happens when you run it:**
- Calculates advanced metrics (Sortino ratio, Calmar ratio, etc.)
- Generates equity curves
- Shows monthly/yearly returns breakdown
- Analyzes trade distribution

**Use this when:**
- You need detailed performance analysis
- Preparing reports for investors
- Optimizing strategy performance

---

## 🔄 Integration Examples

### `example_week4_integration.py`

**Purpose:** Shows how all components work together.

**What happens when you run it:**
- Demonstrates integration between strategy, risk manager, and execution
- Shows proper workflow from backtest to live trading
- Includes monitoring and reporting

**Use this when:**
- Building your own custom trading system
- Understanding the complete architecture
- Debugging integration issues

---

## 💡 Tips for Using Examples

### 1. Start Simple
Begin with `example_backtest_complete.py` before moving to comparisons.

### 2. Modify and Experiment
Copy example files and modify parameters to learn how they affect results.

### 3. Take Notes
Keep a journal of what you learn from each example run.

### 4. Compare Symbols
Run same example on different stocks to see how strategy performs.

### 5. Test Time Periods
Try different date ranges to understand strategy stability.

---

## 🎓 Recommended Learning Path

**Week 1:**
1. Run `example_backtest_complete.py` - understand backtesting
2. Run `example_strategy_templates.py` - learn strategies
3. Experiment with different symbols and time periods

**Week 2:**
1. Run `example_profile_comparison.py` - choose risk profile
2. Run `example_performance_analytics.py` - deep metrics
3. Compare results across strategies

**Week 3:**
1. Modify example files with your own parameters
2. Test on your watchlist symbols
3. Document what works and what doesn't

**Week 4:**
1. Run `example_week4_integration.py` - full integration
2. Start paper trading with best strategy/profile combination
3. Monitor and refine

---

## 📞 Need Help?

**If examples don't run:**
1. Check Python environment is activated
2. Verify all dependencies installed: `pip install -r requirements.txt`
3. Ensure TWS/Gateway is running (if using real data)
4. Check error messages carefully - they usually indicate the issue

**If results seem wrong:**
1. Verify data quality (check for gaps or errors)
2. Confirm strategy parameters make sense
3. Check date ranges are valid
4. Compare with known benchmarks (SPY buy-and-hold)

---

**Remember:** Examples are learning tools. Spend time understanding what they show you before moving to live trading!
