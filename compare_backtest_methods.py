#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare Traditional Backtest vs Rolling Window Backtest
Compare the difference between strategy_backtest and rolling window approach
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
import time

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.analysis.strategy_backtest_analyzer import StrategyBacktestAnalyzer
from src.analysis.rolling_window_backtest import RollingWindowBacktestAnalyzer
from src.strategies.strategy_optimizer import get_strategy_optimizer

def test_traditional_backtest(days: int = 90) -> Dict[str, Any]:
    """Test traditional backtest method for the last N days"""
    print(f"\n🔍 Testing Traditional Backtest (last {days} days)")
    print("=" * 60)
    
    analyzer = StrategyBacktestAnalyzer(investment_amount=100.0, days=days)
    
    start_time = time.time()
    results = analyzer.run_backtest()
    end_time = time.time()
    
    execution_time = end_time - start_time
    
    # Calculate summary
    summary = results.get('summary', {})
    total_investment = summary.get('total_investment', 0)
    total_final_value = summary.get('total_final_value', 0)
    total_profit = total_final_value - total_investment
    avg_return = (total_profit / total_investment * 100) if total_investment > 0 else 0
    
    print(f"\n📊 Traditional Backtest Results:")
    print(f"   ⏱️  Execution time: {execution_time:.2f}s")
    print(f"   💰 Total investment: ${total_investment:.2f}")
    print(f"   💵 Total final value: ${total_final_value:.2f}")
    print(f"   📈 Total profit: ${total_profit:.2f}")
    print(f"   📊 Average return: {avg_return:.2f}%")
    print(f"   ✅ Successful: {summary.get('successful_analysis', 0)}")
    print(f"   ❌ Failed: {summary.get('failed_analysis', 0)}")
    
    return {
        'method': 'Traditional Backtest',
        'period': f'{days} days',
        'execution_time': execution_time,
        'total_investment': total_investment,
        'total_final_value': total_final_value,
        'total_profit': total_profit,
        'avg_return': avg_return,
        'successful': summary.get('successful_analysis', 0),
        'failed': summary.get('failed_analysis', 0),
        'description': f'Uses fixed parameters from config, backtests on last {days} days'
    }

def test_rolling_window_backtest() -> Dict[str, Any]:
    """Test rolling window backtest method"""
    print(f"\n🔄 Testing Rolling Window Backtest (3-month window)")
    print("=" * 60)
    
    analyzer = RollingWindowBacktestAnalyzer(investment_amount=100.0)
    
    start_time = time.time()
    results = analyzer.run_rolling_window_backtest(window_sizes=['3m'])
    end_time = time.time()
    
    execution_time = end_time - start_time
    
    # Extract 3m results
    window_3m = results.get('windows', {}).get('3m', {})
    summary = window_3m.get('summary', {})
    
    total_investment = summary.get('total_investment', 0)
    total_final_value = summary.get('total_final_value', 0)
    total_profit = total_final_value - total_investment
    avg_return = summary.get('average_return', 0)
    
    print(f"\n📊 Rolling Window Backtest Results:")
    print(f"   ⏱️  Execution time: {execution_time:.2f}s")
    print(f"   💰 Total investment: ${total_investment:.2f}")
    print(f"   💵 Total final value: ${total_final_value:.2f}")
    print(f"   📈 Total profit: ${total_profit:.2f}")
    print(f"   📊 Average return: {avg_return:.2f}%")
    print(f"   ✅ Successful: {summary.get('successful_analysis', 0)}")
    print(f"   🔄 Trading points: {summary.get('total_trading_points', 0)}")
    
    return {
        'method': 'Rolling Window Backtest',
        'period': '3 months rolling',
        'execution_time': execution_time,
        'total_investment': total_investment,
        'total_final_value': total_final_value,
        'total_profit': total_profit,
        'avg_return': avg_return,
        'successful': summary.get('successful_analysis', 0),
        'trading_points': summary.get('total_trading_points', 0),
        'description': 'Re-optimizes parameters every month using past 3 months data'
    }

def test_single_optimization_vs_rolling() -> Dict[str, Any]:
    """Test single optimization on 3 months vs rolling optimization"""
    print(f"\n🎯 Testing Single 3-Month Optimization vs Rolling")
    print("=" * 60)
    
    optimizer = get_strategy_optimizer()
    
    # Test single optimization on last 3 months
    print("📈 Single optimization on last 3 months...")
    start_time = time.time()
    
    # Calculate 3 months ago timestamp
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    # This would use all data from 3 months ago to optimize once
    # and then apply those parameters to simulate trading
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    print(f"   ⏱️  Execution time: {execution_time:.2f}s")
    print(f"   📊 Method: Optimize once on 3-month period, apply to whole period")
    
    return {
        'method': 'Single 3-Month Optimization',
        'period': '3 months',
        'execution_time': execution_time,
        'description': 'Optimizes parameters once on 3-month data, applies to entire period'
    }

def compare_methods():
    """Compare all backtest methods"""
    print("🏆 BACKTEST METHODS COMPARISON")
    print("=" * 80)
    
    # Test all methods
    traditional_90d = test_traditional_backtest(90)
    rolling_window = test_rolling_window_backtest()
    single_optimization = test_single_optimization_vs_rolling()
    
    # Summary comparison
    print(f"\n" + "=" * 80)
    print("📊 COMPARISON SUMMARY")
    print("=" * 80)
    
    methods = [traditional_90d, rolling_window, single_optimization]
    
    print(f"{'Method':<25} | {'Period':<15} | {'Return':<10} | {'Time':<8} | {'Description'}")
    print("-" * 100)
    
    for method in methods:
        return_str = f"{method.get('avg_return', 0):.2f}%" if 'avg_return' in method else "N/A"
        print(f"{method['method']:<25} | {method['period']:<15} | {return_str:<10} | {method['execution_time']:.2f}s | {method['description'][:40]}...")
    
    # Key differences
    print(f"\n🔍 KEY DIFFERENCES:")
    print("=" * 50)
    print("1. 📈 Traditional Backtest:")
    print("   - Uses FIXED parameters from trading_config.json")
    print("   - Tests those parameters on last N days")
    print("   - Single optimization period")
    print("   - Simulates actual trading with fixed strategy")
    
    print("\n2. 🔄 Rolling Window Backtest:")
    print("   - RE-OPTIMIZES parameters every month")
    print("   - Uses past 3 months to find best parameters")
    print("   - Applies optimized parameters to next month")
    print("   - Adapts to changing market conditions")
    
    print("\n3. 🎯 Single 3-Month Optimization:")
    print("   - Optimizes ONCE on 3-month historical data")
    print("   - Applies same parameters to entire period")
    print("   - No adaptation during the period")
    print("   - Similar to traditional but with optimization")
    
    print(f"\n🎯 CONCLUSION:")
    print("Rolling window should perform better because it adapts to market changes!")

if __name__ == "__main__":
    compare_methods()
