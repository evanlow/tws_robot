"""
Strategy Selector - Find the Right Strategy for Your Stock

This interactive tool helps you choose which strategy to use based on
the stock's characteristics.

Run this: python strategy_selector.py
"""

import sys
from datetime import datetime, timedelta
from typing import Dict, List
import statistics


def print_header():
    """Print welcome header"""
    print("\n" + "=" * 70)
    print("🎯 TWS ROBOT - STRATEGY SELECTOR")
    print("=" * 70)
    print()
    print("This tool helps you choose the best strategy for your stock.")
    print("Answer a few questions and we'll recommend a strategy!")
    print()


def get_stock_symbol() -> str:
    """Get stock symbol from user"""
    while True:
        symbol = input("📊 What stock do you want to trade? (e.g., AAPL, MSFT): ").strip().upper()
        if symbol:
            return symbol
        print("   ⚠️  Please enter a stock symbol")


def analyze_stock_behavior() -> Dict[str, str]:
    """Ask questions about stock behavior"""
    print("\n" + "-" * 70)
    print("Let's understand this stock's behavior...")
    print("-" * 70)
    print()
    
    questions = {}
    
    # Question 1: Trending or Choppy
    print("1. How does this stock typically move?")
    print("   a) Clear trends up or down (smooth movements)")
    print("   b) Bounces around without clear direction (choppy)")
    print("   c) Not sure")
    
    answer = input("\n   Your answer (a/b/c): ").strip().lower()
    if answer == 'a':
        questions['movement'] = 'trending'
    elif answer == 'b':
        questions['movement'] = 'choppy'
    else:
        questions['movement'] = 'unknown'
    
    print()
    
    # Question 2: Volatility
    print("2. How volatile is this stock?")
    print("   a) Very stable (moves slowly, small daily changes)")
    print("   b) Moderate (normal daily movements)")
    print("   c) Very volatile (big swings, gap ups/downs)")
    
    answer = input("\n   Your answer (a/b/c): ").strip().lower()
    if answer == 'a':
        questions['volatility'] = 'low'
    elif answer == 'b':
        questions['volatility'] = 'medium'
    elif answer == 'c':
        questions['volatility'] = 'high'
    else:
        questions['volatility'] = 'unknown'
    
    print()
    
    # Question 3: Stock Type
    print("3. What type of stock is this?")
    print("   a) Large, stable company (Apple, Microsoft, Coca-Cola)")
    print("   b) Growth/tech stock (Tesla, NVIDIA, startups)")
    print("   c) Small or speculative stock")
    
    answer = input("\n   Your answer (a/b/c): ").strip().lower()
    if answer == 'a':
        questions['type'] = 'bluechip'
    elif answer == 'b':
        questions['type'] = 'growth'
    elif answer == 'c':
        questions['type'] = 'speculative'
    else:
        questions['type'] = 'unknown'
    
    return questions


def recommend_strategy(questions: Dict[str, str]) -> Dict[str, any]:
    """Recommend strategy based on answers"""
    
    recommendations = []
    
    # Moving Average Crossover
    ma_score = 0
    if questions['movement'] == 'trending':
        ma_score += 3
    if questions['volatility'] in ['medium', 'high']:
        ma_score += 2
    if questions['type'] in ['bluechip', 'growth']:
        ma_score += 2
    
    recommendations.append({
        'name': 'Moving Average Crossover',
        'score': ma_score,
        'max_score': 7,
        'why': [
            "Works best in trending markets",
            "Filters out noise in volatile stocks",
            "Classic strategy for large-cap stocks"
        ],
        'config': "MACrossConfig(fast_period=20, slow_period=50)",
        'best_for': "AAPL, MSFT, NVDA, TSLA (when trending)"
    })
    
    # Mean Reversion
    mr_score = 0
    if questions['movement'] == 'choppy':
        mr_score += 3
    if questions['volatility'] == 'medium':
        mr_score += 2
    if questions['type'] == 'bluechip':
        mr_score += 2
    
    recommendations.append({
        'name': 'Mean Reversion (Bollinger Bands)',
        'score': mr_score,
        'max_score': 7,
        'why': [
            "Profits from price bouncing back to average",
            "Works in choppy, range-bound markets",
            "Good for stable, predictable stocks"
        ],
        'config': "MeanReversionConfig(period=20, std_dev=2.0)",
        'best_for': "KO, PG, JNJ, WMT (stable dividend stocks)"
    })
    
    # Momentum
    mom_score = 0
    if questions['movement'] == 'trending':
        mom_score += 2
    if questions['volatility'] == 'high':
        mom_score += 3
    if questions['type'] in ['growth', 'speculative']:
        mom_score += 2
    
    recommendations.append({
        'name': 'Momentum',
        'score': mom_score,
        'max_score': 7,
        'why': [
            "Rides strong trends",
            "Works with high volatility",
            "Good for growth stocks"
        ],
        'config': "MomentumConfig(period=14, threshold=0.02)",
        'best_for': "NVDA, TSLA, growth stocks, crypto-related"
    })
    
    # Sort by score
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    
    return recommendations


def print_recommendations(symbol: str, recommendations: List[Dict]):
    """Print strategy recommendations"""
    print("\n" + "=" * 70)
    print(f"📊 RECOMMENDATIONS FOR {symbol}")
    print("=" * 70)
    
    for i, rec in enumerate(recommendations, 1):
        percentage = (rec['score'] / rec['max_score']) * 100
        
        print(f"\n{i}. {rec['name']}")
        print(f"   Match Score: {rec['score']}/{rec['max_score']} ({percentage:.0f}%)")
        
        if percentage >= 70:
            print("   ✅ HIGHLY RECOMMENDED")
        elif percentage >= 50:
            print("   ⚠️  WORTH TRYING")
        else:
            print("   ❌ NOT RECOMMENDED")
        
        print()
        print("   Why this might work:")
        for reason in rec['why']:
            print(f"   • {reason}")
        
        print()
        print(f"   Similar stocks: {rec['best_for']}")
        print()
        print("   How to use:")
        print(f"   ```python")
        print(f"   from backtest.strategy_templates import {rec['name'].replace(' ', '')}")
        print(f"   strategy = {rec['name'].replace(' ', '')}(config, {rec['config']})")
        print(f"   ```")
        
        if i < len(recommendations):
            print("\n" + "-" * 70)


def suggest_next_steps(symbol: str, top_strategy: str):
    """Suggest what to do next"""
    print("\n" + "=" * 70)
    print("🎓 NEXT STEPS")
    print("=" * 70)
    print()
    print(f"1. Test {top_strategy} on {symbol}:")
    print(f"   python example_backtest_complete.py")
    print()
    print("2. Compare all three strategies:")
    print("   python example_strategy_templates.py")
    print()
    print("3. Try different risk profiles:")
    print("   python example_profile_comparison.py")
    print()
    print("4. Once you find a winner, paper trade it:")
    print("   python tws_client.py --env paper")
    print()


def ask_another():
    """Ask if user wants to analyze another stock"""
    print("\n" + "-" * 70)
    answer = input("Analyze another stock? (y/n): ").strip().lower()
    return answer == 'y'


def main():
    """Main entry point"""
    while True:
        print_header()
        
        # Get stock symbol
        symbol = get_stock_symbol()
        
        # Analyze stock behavior
        questions = analyze_stock_behavior()
        
        # Get recommendations
        recommendations = recommend_strategy(questions)
        
        # Print recommendations
        print_recommendations(symbol, recommendations)
        
        # Suggest next steps
        top_strategy = recommendations[0]['name']
        suggest_next_steps(symbol, top_strategy)
        
        # Ask if user wants to continue
        if not ask_another():
            break
    
    print("\n" + "=" * 70)
    print("Happy Trading! 🚀")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
