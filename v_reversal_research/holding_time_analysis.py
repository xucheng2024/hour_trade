#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Holding Time Analysis for V-Pattern Strategy
V-shaped reversal strategy holding time analysis
"""

import os
import sys
import logging
import time
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import VReversalDataLoader
from profit_maximizer import VectorizedProfitMaximizer, MaxProfitParams

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_holding_time_impact(symbols: List[str] = None, total_months: int = 6, test_months: int = 3):
    """
    Analyze the impact of different holding times on returns
    """
    print("📊 V-Pattern Strategy: Holding Time Impact Analysis")
    print("=" * 70)
    print("🎯 Focus: Optimal holding time after purchase")
    print("⏰ Test range: 6 hours to 72 hours")
    print()
    
    # 1. Load data
    print("📊 Loading data...")
    data_loader = VReversalDataLoader()
    
    if symbols is None:
        symbols = ['BTC-USDT', 'ETH-USDT']
    
    data_dict = data_loader.load_multiple_symbols(symbols, months=total_months)
    
    if not data_dict:
        print("❌ No data loaded")
        return None
    
    print(f"✅ Loaded data for {len(data_dict)} symbols")
    
    # 2. Run optimization
    print("\n⚡ Starting holding time optimization...")
    maximizer = VectorizedProfitMaximizer(test_months=test_months)
    
    start_time = time.time()
    results = maximizer.optimize_multiple_symbols(data_dict)
    optimization_time = time.time() - start_time
    
    if not results:
        print("❌ No successful optimizations")
        return None
    
    print(f"✅ Optimization completed in {optimization_time:.1f}s")
    
    # 3. Analyze holding time impact
    analyze_holding_time_patterns(results)
    
    # 4. Save detailed results
    save_holding_analysis(results, maximizer)
    
    return results

def analyze_holding_time_patterns(results: Dict[str, MaxProfitParams]):
    """Analyze holding time patterns"""
    print(f"\n⏰ Holding Time Analysis Results")
    print("=" * 80)
    
    for symbol, result in results.items():
        print(f"\n💰 {symbol} - Optimal Holding Configuration:")
        print(f"  🕐 Optimal holding time: {result.holding_hours} hours")
        print(f"  📈 Test return: {result.test_return:.2%}")
        print(f"  🎯 Win rate: {result.test_win_rate:.1%}")
        print(f"  📊 Number of trades: {result.test_trades}")
        print(f"  ⚖️ Profit factor: {result.profit_factor:.2f}")
        
        # Analyze the reasonableness of holding time
        analyze_holding_logic(symbol, result)

def analyze_holding_logic(symbol: str, result: MaxProfitParams):
    """Analyze holding time logic"""
    holding_hours = result.holding_hours
    
    print(f"  🧠 Holding time analysis:")
    
    if holding_hours <= 8:
        print(f"    ⚡ Ultra-short strategy ({holding_hours}h) - Quick in and out, suitable for high-frequency trading")
        risk_level = "Low risk"
    elif holding_hours <= 24:
        print(f"    🎯 Short-term strategy ({holding_hours}h) - Intraday trading, avoiding overnight risk") 
        risk_level = "Medium risk"
    elif holding_hours <= 48:
        print(f"    📈 Medium-term strategy ({holding_hours}h) - Cross-day holding, capturing larger trends")
        risk_level = "Medium-high risk"
    else:
        print(f"    🏔️ Long-term strategy ({holding_hours}h) - Multi-day holding, trend following")
        risk_level = "High risk"
    
    print(f"    🛡️ Risk level: {risk_level}")
    
    # Calculate theoretical annual return
    if result.test_trades > 0:
        avg_days_per_trade = holding_hours / 24
        trades_per_year = 365 / avg_days_per_trade
        single_trade_return = result.test_return / result.test_trades
        theoretical_annual = single_trade_return * trades_per_year
        print(f"    📊 Theoretical annual: {theoretical_annual:.1%} (based on average single trade return)")

def compare_holding_strategies(results: Dict[str, MaxProfitParams]):
    """Compare different holding strategies"""
    print(f"\n📊 Holding Strategy Comparison")
    print("=" * 80)
    
    # Group by holding time
    strategies = {
        'Ultra Short (≤8h)': [],
        'Short (9-24h)': [],
        'Medium (25-48h)': [],
        'Long (>48h)': []
    }
    
    for symbol, result in results.items():
        hours = result.holding_hours
        if hours <= 8:
            strategies['Ultra Short (≤8h)'].append((symbol, result))
        elif hours <= 24:
            strategies['Short (9-24h)'].append((symbol, result))
        elif hours <= 48:
            strategies['Medium (25-48h)'].append((symbol, result))
        else:
            strategies['Long (>48h)'].append((symbol, result))
    
    for strategy_name, strategy_results in strategies.items():
        if not strategy_results:
            continue
            
        print(f"\n🎯 {strategy_name}:")
        avg_return = np.mean([r[1].test_return for r in strategy_results])
        avg_win_rate = np.mean([r[1].test_win_rate for r in strategy_results])
        avg_trades = np.mean([r[1].test_trades for r in strategy_results])
        
        print(f"  📈 Average return: {avg_return:.2%}")
        print(f"  🎯 Average win rate: {avg_win_rate:.1%}")
        print(f"  📊 Average trades: {avg_trades:.0f}")
        
        for symbol, result in strategy_results:
            print(f"    {symbol}: {result.holding_hours}h, {result.test_return:.1%}")

def save_holding_analysis(results: Dict[str, MaxProfitParams], maximizer: VectorizedProfitMaximizer):
    """Save holding time analysis results"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"holding_time_analysis_{timestamp}.json"
    
    # Prepare analysis data
    analysis_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "analysis_type": "holding_time_optimization",
            "focus": "optimal_holding_duration",
            "holding_range": "6-72 hours"
        },
        "summary": {
            "total_symbols": len(results),
            "avg_optimal_hours": np.mean([r.holding_hours for r in results.values()]),
            "holding_distribution": {}
        },
        "detailed_results": {}
    }
    
    # Statistics of holding time distribution
    holding_times = [r.holding_hours for r in results.values()]
    unique_times, counts = np.unique(holding_times, return_counts=True)
    
    for time_val, count in zip(unique_times, counts):
        analysis_data["summary"]["holding_distribution"][f"{time_val}h"] = int(count)
    
    # Detailed results
    for symbol, result in results.items():
        analysis_data["detailed_results"][symbol] = {
            "optimal_holding_hours": int(result.holding_hours),
            "test_return": float(result.test_return),
            "win_rate": float(result.test_win_rate),
            "trades": int(result.test_trades),
            "profit_factor": float(result.profit_factor),
            "max_drawdown": float(result.max_drawdown),
            "trading_params": {
                "stop_loss_pct": float(result.stop_loss_pct),
                "take_profit_pct": float(result.take_profit_pct)
            }
        }
    
    # Save file
    import json
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(parent_dir, 'data')
    results_path = os.path.join(data_dir, filename)
    
    with open(results_path, 'w') as f:
        json.dump(analysis_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Holding time analysis saved to: {results_path}")
    return results_path

def print_holding_time_insights():
    """Print holding time optimization insights"""
    print(f"\n💡 Holding Time Optimization Insights")
    print("=" * 80)
    print("🔍 Key findings:")
    print("  1. Too short holding time (<6h): May miss trend development")
    print("  2. Too long holding time (>72h): Bears more market risk")
    print("  3. Optimal holding time depends on:")
    print("     - Cryptocurrency volatility characteristics")
    print("     - Market environment")
    print("     - Stop loss and take profit settings")
    print("     - Trading frequency requirements")
    print()
    print("🎯 Strategy recommendations:")
    print("  • Ultra-short (6-8h): Suitable for high volatility periods, quick in and out")
    print("  • Short-term (12-24h): Balance risk and return, complete within day")
    print("  • Medium-term (24-48h): Capture larger trends, suitable when trend is clear")
    print("  • Long-term (48h+): Only use when strong trend is confirmed")

def main():
    """Main function"""
    print("⏰ V-Pattern Holding Time Optimizer")
    print("=" * 60)
    print("🎯 Specifically optimizes the best holding time after purchase")
    print()
    
    try:
        # Run holding time analysis
        results = analyze_holding_time_impact()
        
        if results:
            # Comparative analysis
            compare_holding_strategies(results)
            
            # Print insights
            print_holding_time_insights()
            
            print(f"\n🎉 Holding time optimization completed!")
            print(f"💡 Now you know the optimal holding time for each cryptocurrency!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
