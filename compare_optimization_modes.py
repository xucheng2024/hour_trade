#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare Optimization Modes: Monthly vs Sliding Window
"""

import os
import sys
import time
from typing import Dict, List, Any

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.strategies.rolling_window_optimizer import RollingWindowOptimizer
from src.strategies.sliding_window_optimizer import SlidingWindowOptimizer
from src.data.data_manager import load_crypto_list

def test_monthly_optimization(crypto: str, investment: float = 100.0) -> Dict[str, Any]:
    """Test monthly optimization mode"""
    try:
        print(f"   📅 Monthly Mode: 3-month optimization windows")
        
        optimizer = RollingWindowOptimizer(buy_fee=0.001, sell_fee=0.001)
        
        start_time = time.time()
        date_dict = {}
        result = optimizer.optimize_with_rolling_windows(
            instId=crypto,
            start=0,
            end=0,
            date_dict=date_dict,
            bar="1d",
            strategy_type="1d",
            window_size="3m",
            step_size="1m"
        )
        end_time = time.time()
        
        if not result or crypto not in result:
            return None
            
        crypto_result = result[crypto]
        
        return {
            'method': 'Monthly Optimization',
            'crypto': crypto,
            'execution_time': end_time - start_time,
            'total_trading_points': int(crypto_result.get('total_trading_points', 0)),
            'expected_returns': float(crypto_result.get('expected_returns', 1.0)),
            'overall_stability': float(crypto_result.get('overall_stability', 0.0)),
            'best_limit': crypto_result.get('best_limit', '0'),
            'best_duration': crypto_result.get('best_duration', '0'),
            'trade_count': int(crypto_result.get('trade_count', 0)),
            'trades_per_month': float(crypto_result.get('trades_per_month', 0.0))
        }
        
    except Exception as e:
        print(f"   ❌ Monthly optimization error: {e}")
        return None

def test_sliding_window_optimization(crypto: str, investment: float = 100.0) -> Dict[str, Any]:
    """Test sliding window optimization mode"""
    try:
        print(f"   ⚡ Sliding Window: Daily 30-day optimization")
        
        optimizer = SlidingWindowOptimizer(buy_fee=0.001, sell_fee=0.001, window_days=30)
        
        start_time = time.time()
        date_dict = {}
        result = optimizer.optimize_with_sliding_windows(
            instId=crypto,
            start=0,
            end=0,
            date_dict=date_dict,
            bar="1d",
            strategy_type="1d"
        )
        end_time = time.time()
        
        if not result or crypto not in result:
            return None
            
        crypto_result = result[crypto]
        
        return {
            'method': 'Sliding Window',
            'crypto': crypto,
            'execution_time': end_time - start_time,
            'total_trading_points': int(crypto_result.get('total_trading_points', 0)),
            'expected_returns': float(crypto_result.get('expected_returns', 1.0)),
            'overall_stability': float(crypto_result.get('overall_stability', 0.0)),
            'best_limit': crypto_result.get('best_limit', '0'),
            'best_duration': crypto_result.get('best_duration', '0'),
            'trade_count': int(crypto_result.get('trade_count', 0)),
            'trades_per_month': float(crypto_result.get('trades_per_month', 0.0))
        }
        
    except Exception as e:
        print(f"   ❌ Sliding window error: {e}")
        return None

def run_optimization_mode_comparison():
    """Run comparison between monthly and sliding window optimization modes"""
    print("🏆 OPTIMIZATION MODES COMPARISON: Monthly vs Sliding Window")
    print("=" * 70)
    
    # Load crypto list
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found")
        return
    
    # Test with first 5 cryptos for demonstration
    test_cryptos = cryptos[:5]
    print(f"🔍 Testing {len(test_cryptos)} cryptocurrencies")
    print()
    
    results = {
        'monthly': [],
        'sliding_window': [],
        'summary': {
            'monthly_total_return': 0,
            'sliding_total_return': 0,
            'monthly_stability': 0,
            'sliding_stability': 0,
            'monthly_trading_points': 0,
            'sliding_trading_points': 0,
            'monthly_execution_time': 0,
            'sliding_execution_time': 0
        }
    }
    
    # Test each crypto
    for i, crypto in enumerate(test_cryptos, 1):
        print(f"📈 Testing {i}/{len(test_cryptos)}: {crypto}")
        
        # Test monthly optimization
        monthly_result = test_monthly_optimization(crypto)
        if monthly_result:
            results['monthly'].append(monthly_result)
            results['summary']['monthly_total_return'] += monthly_result['expected_returns']
            results['summary']['monthly_stability'] += monthly_result['overall_stability']
            results['summary']['monthly_trading_points'] += monthly_result['total_trading_points']
            results['summary']['monthly_execution_time'] += monthly_result['execution_time']
        
        # Test sliding window optimization
        sliding_result = test_sliding_window_optimization(crypto)
        if sliding_result:
            results['sliding_window'].append(sliding_result)
            results['summary']['sliding_total_return'] += sliding_result['expected_returns']
            results['summary']['sliding_stability'] += sliding_result['overall_stability']
            results['summary']['sliding_trading_points'] += sliding_result['total_trading_points']
            results['summary']['sliding_execution_time'] += sliding_result['execution_time']
        
        print()
    
    # Calculate averages
    monthly_count = len(results['monthly'])
    sliding_count = len(results['sliding_window'])
    
    if monthly_count > 0:
        monthly_avg_return = results['summary']['monthly_total_return'] / monthly_count
        monthly_avg_stability = results['summary']['monthly_stability'] / monthly_count
        monthly_avg_execution = results['summary']['monthly_execution_time'] / monthly_count
    
    if sliding_count > 0:
        sliding_avg_return = results['summary']['sliding_total_return'] / sliding_count
        sliding_avg_stability = results['summary']['sliding_stability'] / sliding_count
        sliding_avg_execution = results['summary']['sliding_execution_time'] / sliding_count
    
    # Print results
    print("=" * 70)
    print("📊 OPTIMIZATION MODES COMPARISON RESULTS")
    print("=" * 70)
    
    print(f"{'Mode':<20} | {'Count':<6} | {'Avg Return':<12} | {'Stability':<10} | {'Trading Points':<15} | {'Exec Time':<10}")
    print("-" * 90)
    
    if monthly_count > 0:
        print(f"{'Monthly':<20} | {monthly_count:<6} | {monthly_avg_return:>10.3f} | {monthly_avg_stability:>8.3f} | {results['summary']['monthly_trading_points']:>13} | {monthly_avg_execution:>8.2f}s")
    
    if sliding_count > 0:
        print(f"{'Sliding Window':<20} | {sliding_count:<6} | {sliding_avg_return:>10.3f} | {sliding_avg_stability:>8.3f} | {results['summary']['sliding_trading_points']:>13} | {sliding_avg_execution:>8.2f}s")
    
    print()
    
    # Detailed comparison
    print("🔍 DETAILED COMPARISON:")
    print("=" * 50)
    
    for i, crypto in enumerate(test_cryptos):
        if i < len(results['monthly']) and i < len(results['sliding_window']):
            monthly = results['monthly'][i]
            sliding = results['sliding_window'][i]
            
            return_diff = sliding['expected_returns'] - monthly['expected_returns']
            stability_diff = sliding['overall_stability'] - monthly['overall_stability']
            
            print(f"{crypto}:")
            print(f"  📈 Return: Sliding {sliding['expected_returns']:.3f} vs Monthly {monthly['expected_returns']:.3f} = {return_diff:+.3f}")
            print(f"  🔒 Stability: Sliding {sliding['overall_stability']:.3f} vs Monthly {monthly['overall_stability']:.3f} = {stability_diff:+.3f}")
            print(f"  🔄 Trading Points: Sliding {sliding['total_trading_points']} vs Monthly {monthly['total_trading_points']}")
    
    print()
    
    # Performance analysis
    if monthly_count > 0 and sliding_count > 0:
        return_diff = sliding_avg_return - monthly_avg_return
        stability_diff = sliding_avg_stability - monthly_avg_stability
        
        print(f"🏆 PERFORMANCE ANALYSIS:")
        print("=" * 40)
        print(f"📈 Returns: Sliding Window {'beats' if return_diff > 0 else 'loses to'} Monthly by {abs(return_diff):.3f}")
        print(f"🔒 Stability: Sliding Window {'more stable' if stability_diff > 0 else 'less stable'} by {abs(stability_diff):.3f}")
        print(f"⚡ Speed: Sliding Window {'faster' if sliding_avg_execution < monthly_avg_execution else 'slower'} by {abs(sliding_avg_execution - monthly_avg_execution):.2f}s")
        
        if return_diff > 0:
            improvement_pct = (return_diff / monthly_avg_return) * 100
            print(f"✅ Sliding Window is {improvement_pct:.1f}% better in returns!")
        else:
            decline_pct = (abs(return_diff) / sliding_avg_return) * 100
            print(f"❌ Monthly is {decline_pct:.1f}% better in returns!")
    
    print("\n" + "=" * 70)
    print("🎯 KEY INSIGHTS")
    print("=" * 70)
    print("Monthly Optimization:")
    print("  ✅ Less computation, more stable parameters")
    print("  ❌ Less frequent updates, may miss short-term opportunities")
    print()
    print("Sliding Window:")
    print("  ✅ Daily updates, more adaptive to market changes")
    print("  ❌ More computation, parameters may be less stable")
    print()
    print("Expected Trade-off:")
    print("  📈 Sliding Window should have higher returns due to daily adaptation")
    print("  🔒 Monthly should have more stable parameters due to longer optimization periods")

if __name__ == "__main__":
    run_optimization_mode_comparison()
