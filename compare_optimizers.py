#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare Traditional vs Rolling Window Strategy Optimizers
Test both optimizers on the same cryptocurrencies for comparison
"""

import sys
import os
import time

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from strategies.strategy_optimizer import StrategyOptimizer
from strategies.rolling_window_optimizer import RollingWindowOptimizer
from data.data_manager import load_crypto_list

def test_traditional_optimizer(cryptos, limit=3):
    """Test traditional optimizer on limited cryptocurrencies"""
    print("🔍 Testing Traditional Strategy Optimizer")
    print("=" * 50)
    
    optimizer = StrategyOptimizer(buy_fee=0.001, sell_fee=0.001)
    results = {}
    
    for i, crypto in enumerate(cryptos[:limit], 1):
        print(f"\n📈 Testing {i}/{limit}: {crypto}")
        
        try:
            start_time = time.time()
            date_dict = {}
            result = optimizer.optimize_1d_strategy(
                instId=crypto,
                start=0,
                end=0,
                date_dict=date_dict,
                bar="1d"
            )
            end_time = time.time()
            
            if result and crypto in result:
                crypto_result = result[crypto]
                results[crypto] = {
                    'method': 'traditional',
                    'best_limit': int(crypto_result.get('best_limit', 0)),
                    'best_duration': int(crypto_result.get('best_duration', 0)),
                    'max_returns': float(crypto_result.get('max_returns', 0)),
                    'trade_count': int(crypto_result.get('trade_count', 0)),
                    'trades_per_month': float(crypto_result.get('trades_per_month', 0)),
                    'execution_time': round(end_time - start_time, 2)
                }
                print(f"  ✅ Success: Limit={results[crypto]['best_limit']}%, Duration={results[crypto]['best_duration']}")
                print(f"  📈 Returns: {results[crypto]['max_returns']:.3f}")
                print(f"  📊 Trades: {results[crypto]['trade_count']} total, {results[crypto]['trades_per_month']:.1f}/month")
                print(f"  ⏱️  Time: {results[crypto]['execution_time']}s")
            else:
                print(f"  ❌ Failed")
                results[crypto] = {'method': 'traditional', 'status': 'failed'}
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[crypto] = {'method': 'traditional', 'status': 'error', 'error': str(e)}
    
    return results

def test_rolling_window_optimizer(cryptos, limit=3, window_size="3m"):
    """Test rolling window optimizer on limited cryptocurrencies"""
    print(f"\n🔄 Testing Rolling Window Strategy Optimizer (Window: {window_size})")
    print("=" * 50)
    
    optimizer = RollingWindowOptimizer(buy_fee=0.001, sell_fee=0.001)
    results = {}
    
    for i, crypto in enumerate(cryptos[:limit], 1):
        print(f"\n📈 Testing {i}/{limit}: {crypto}")
        
        try:
            start_time = time.time()
            date_dict = {}
            result = optimizer.optimize_with_rolling_windows(
                instId=crypto,
                start=0,
                end=0,
                date_dict=date_dict,
                bar="1d",
                strategy_type="1d",
                window_size=window_size,
                step_size="1m"
            )
            end_time = time.time()
            
            if result and crypto in result:
                crypto_result = result[crypto]
                results[crypto] = {
                    'method': 'rolling_window',
                    'best_limit': crypto_result.get('recommended_limit', 0),
                    'best_duration': crypto_result.get('recommended_duration', 0),
                    'expected_returns': crypto_result.get('expected_returns', 0),
                    'total_trading_points': crypto_result.get('total_trading_points', 0),
                    'overall_stability': crypto_result.get('overall_stability', 0),
                    'execution_time': round(end_time - start_time, 2)
                }
                print(f"  ✅ Success: Limit={crypto_result.get('recommended_limit', 0)}%, Duration={crypto_result.get('recommended_duration', 0)}")
                print(f"  📈 Expected Returns: {crypto_result.get('expected_returns', 0):.3f}")
                print(f"  📊 Trading Points: {crypto_result.get('total_trading_points', 0)}")
                print(f"  🔒 Stability: {crypto_result.get('overall_stability', 0):.3f}")
                print(f"  ⏱️  Time: {results[crypto]['execution_time']}s")
            else:
                print(f"  ❌ Failed")
                results[crypto] = {'method': 'rolling_window', 'status': 'failed'}
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[crypto] = {'method': 'rolling_window', 'status': 'error', 'error': str(e)}
    
    return results

def compare_results(traditional_results, rolling_results):
    """Compare results from both optimizers"""
    print("\n📊 Comparison Results")
    print("=" * 50)
    
    common_cryptos = set(traditional_results.keys()) & set(rolling_results.keys())
    
    if not common_cryptos:
        print("❌ No common cryptocurrencies to compare")
        return
    
    print(f"🔍 Comparing {len(common_cryptos)} cryptocurrencies:")
    print()
    
    for crypto in common_cryptos:
        trad = traditional_results[crypto]
        roll = rolling_results[crypto]
        
        if 'status' in trad or 'status' in roll:
            print(f"📈 {crypto}: Cannot compare (one method failed)")
            continue
            
        print(f"📈 {crypto}:")
        print(f"  Traditional: Limit={trad['best_limit']}%, Duration={trad['best_duration']}, Returns={trad['max_returns']:.3f}")
        print(f"  Rolling:    Limit={roll['best_limit']}%, Duration={roll['best_duration']}, Returns={roll['expected_returns']:.3f}")
        
        # Compare parameters
        limit_diff = abs(trad['best_limit'] - roll['best_limit'])
        duration_diff = abs(trad['best_duration'] - roll['best_duration'])
        returns_diff = abs(trad['max_returns'] - roll['expected_returns'])
        
        print(f"  Differences: Limit ±{limit_diff}%, Duration ±{duration_diff}, Returns ±{returns_diff:.3f}")
        
        # Compare execution time
        time_diff = roll['execution_time'] - trad['execution_time']
        print(f"  Performance: Rolling window {'slower' if time_diff > 0 else 'faster'} by {abs(time_diff):.2f}s")
        print()

def main():
    """Main function to compare different optimizers"""
    print("🚀 Strategy Optimizer Comparison Tool")
    print("=" * 50)
    
    # Load crypto list
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found!")
        return
    
    print(f"📊 Found {len(cryptos)} cryptocurrencies")
    
    # Set test limit directly
    test_limit = 29
    print(f"\n🧪 Testing with {test_limit} cryptocurrencies...")
    
    # Test traditional optimizer
    print("\n🔍 Testing Traditional Optimizer...")
    traditional_results = test_traditional_optimizer(cryptos, test_limit)
    
    # Test rolling window optimizer with 1m window
    print("\n🔄 Testing Rolling Window Optimizer (1m)...")
    rolling_1m_results = test_rolling_window_optimizer(cryptos, test_limit, "1m")
    
    # Test rolling window optimizer with 3m window
    print("\n🔄 Testing Rolling Window Optimizer (3m)...")
    rolling_3m_results = test_rolling_window_optimizer(cryptos, test_limit, "3m")
    
    # Test rolling window optimizer with 6m window
    print("\n🔄 Testing Rolling Window Optimizer (6m)...")
    rolling_6m_results = test_rolling_window_optimizer(cryptos, test_limit, "6m")
    
    # Compare all results
    print("\n" + "=" * 50)
    print("📊 Traditional vs 1m Rolling Window")
    print("=" * 50)
    compare_results(traditional_results, rolling_1m_results)
    
    print("\n" + "=" * 50)
    print("📊 Traditional vs 3m Rolling Window")
    print("=" * 50)
    compare_results(traditional_results, rolling_3m_results)
    
    print("\n" + "=" * 50)
    print("📊 Traditional vs 6m Rolling Window")
    print("=" * 50)
    compare_results(traditional_results, rolling_6m_results)
    
    print("\n" + "=" * 50)
    print("📊 Rolling Window Comparison (1m vs 3m vs 6m)")
    print("=" * 50)
    compare_rolling_windows(rolling_1m_results, rolling_3m_results, rolling_6m_results)
    
    print("\n" + "=" * 50)
    print("🏆 Best Performing Method Summary")
    print("=" * 50)
    print_best_performance_summary(traditional_results, rolling_1m_results, rolling_3m_results, rolling_6m_results)
    
    print("\n✅ Comparison completed!")

def compare_rolling_windows(rolling_1m_results, rolling_3m_results, rolling_6m_results):
    """Compare different rolling window sizes"""
    print("Window Size | Avg Returns | Avg Trade Count | Avg Stability | Avg Time")
    print("-" * 70)
    
    # Calculate averages for each method
    methods = [
        ("1m", rolling_1m_results),
        ("3m", rolling_3m_results),
        ("6m", rolling_6m_results)
    ]
    
    for window_size, results in methods:
        if not results:
            print(f"{window_size:>10} | {'N/A':>12} | {'N/A':>15} | {'N/A':>14} | {'N/A':>9}")
            continue
            
        # Filter out failed results
        valid_results = [r for r in results.values() if r and 'max_returns' in r]
        
        if not valid_results:
            print(f"{window_size:>10} | {'N/A':>12} | {'N/A':>15} | {'N/A':>14} | {'N/A':>9}")
            continue
            
        avg_returns = sum(r['max_returns'] for r in valid_results) / len(valid_results)
        avg_trades = sum(r['trade_count'] for r in valid_results) / len(valid_results)
        avg_stability = sum(r.get('stability', 0) for r in valid_results) / len(valid_results)
        avg_time = sum(r['execution_time'] for r in valid_results) / len(valid_results)
        
        print(f"{window_size:>10} | {avg_returns:>11.3f} | {avg_trades:>14.1f} | {avg_stability:>13.1f} | {avg_time:>8.2f}s")

def print_best_performance_summary(traditional_results, rolling_1m_results, rolling_3m_results, rolling_6m_results):
    """Print summary of best performing method for each crypto"""
    print("Crypto | Best Method | Returns | Trade Count | Stability")
    print("-" * 60)
    
    # Get all unique cryptos
    all_cryptos = set()
    if traditional_results:
        all_cryptos.update(traditional_results.keys())
    if rolling_1m_results:
        all_cryptos.update(rolling_1m_results.keys())
    if rolling_3m_results:
        all_cryptos.update(rolling_3m_results.keys())
    if rolling_6m_results:
        all_cryptos.update(rolling_6m_results.keys())
    
    for crypto in sorted(all_cryptos):
        # Find best method for this crypto
        best_method = None
        best_returns = -float('inf')
        best_trades = 0
        best_stability = 0
        
        methods = [
            ("Traditional", traditional_results.get(crypto)),
            ("1m Rolling", rolling_1m_results.get(crypto)),
            ("3m Rolling", rolling_3m_results.get(crypto)),
            ("6m Rolling", rolling_6m_results.get(crypto))
        ]
        
        for method_name, result in methods:
            if result and 'max_returns' in result and result['max_returns'] > best_returns:
                best_method = method_name
                best_returns = result['max_returns']
                best_trades = result['trade_count']
                best_stability = result.get('stability', 0)
        
        if best_method:
            print(f"{crypto:>6} | {best_method:>12} | {best_returns:>7.3f} | {best_trades:>11} | {best_stability:>9.1f}")
        else:
            print(f"{crypto:>6} | {'N/A':>12} | {'N/A':>7} | {'N/A':>11} | {'N/A':>9}")
    
    print("\n💡 Key Insights:")
    print("• Traditional: Best historical returns, may overfit")
    print("• 1m Rolling: Most adaptive, frequent re-optimization")
    print("• 3m Rolling: Balanced approach, moderate stability")
    print("• 6m Rolling: Most stable, less adaptive")

if __name__ == "__main__":
    main()
