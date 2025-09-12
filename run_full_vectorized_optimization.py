#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run Full Vectorized Optimization for All Cryptocurrencies
"""

import sys
import os
from vectorized_profit_optimizer import VectorizedProfitOptimizer
from src.data.data_manager import load_crypto_list

def main():
    """Run full vectorized optimization for all cryptocurrencies"""
    print("🚀 Starting Full Vectorized Optimization for All Cryptocurrencies")
    print("=" * 70)
    
    # Load all cryptocurrencies
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found in the list")
        return
    
    print(f"📊 Found {len(cryptos)} cryptocurrencies to optimize")
    
    # Initialize optimizer
    optimizer = VectorizedProfitOptimizer()
    
    # Define optimization parameters (more granular for full run)
    p_range = (0.01, 0.08)  # 1% to 8% high/open ratio
    v_range = (1.1, 2.0)    # 1.1x to 2.0x volume ratio (reduced range for faster processing)
    p_step = 0.01           # 1% steps for p
    v_step = 0.1            # 0.1 steps for v
    min_median_return = 1.01  # Minimum 1% median return
    
    print(f"🔍 Parameter ranges: p={p_range}, v={v_range}")
    print(f"🔍 Step sizes: p={p_step}, v={v_step}")
    print(f"🔍 Min median return: {min_median_return}")
    
    # Calculate total operations
    p_values = list(range(int(p_range[0]*100), int(p_range[1]*100)+1, int(p_step*100)))
    v_values = [round(v, 1) for v in [v_range[0] + i*v_step for i in range(int((v_range[1]-v_range[0])/v_step)+1)]]
    total_combinations = len(p_values) * len(v_values)
    total_operations = len(cryptos) * total_combinations
    
    print(f"📊 Testing {len(p_values)} p values × {len(v_values)} v values = {total_combinations} combinations per crypto")
    print(f"📊 Total operations: {len(cryptos)} cryptos × {total_combinations} combinations = {total_operations:,}")
    
    # Ask for confirmation
    response = input(f"\n⚠️  This will process {total_operations:,} operations. Continue? (y/N): ")
    if response.lower() != 'y':
        print("❌ Optimization cancelled by user")
        return
    
    # Run optimization for all cryptocurrencies
    results = optimizer.optimize_all_cryptos(
        cryptos=cryptos,
        p_range=p_range,
        v_range=v_range,
        p_step=p_step,
        v_step=v_step,
        min_median_return=min_median_return
    )
    
    # Save results
    filepath = optimizer.save_results(results)
    
    # Print comprehensive summary
    print("\n" + "=" * 70)
    print("📊 FULL OPTIMIZATION SUMMARY")
    print("=" * 70)
    
    summary = results['summary']
    if 'error' in summary:
        print(f"❌ {summary['error']}")
        return
    
    print(f"✅ Successfully optimized: {summary['total_cryptos_optimized']} cryptocurrencies")
    
    # Parameter statistics
    p_stats = summary['parameter_statistics']['p_values']
    v_stats = summary['parameter_statistics']['v_values']
    
    print(f"\n📊 Optimal Parameter Statistics:")
    print(f"  P (High/Open ratio): {p_stats['mean']:.1%} ± {p_stats['std']:.1%} (range: {p_stats['min']:.1%} - {p_stats['max']:.1%})")
    print(f"  V (Volume ratio): {v_stats['mean']:.1f} ± {v_stats['std']:.1f} (range: {v_stats['min']:.1f} - {v_stats['max']:.1f})")
    
    # Performance statistics
    perf_stats = summary['performance_statistics']
    compound_stats = perf_stats['compound_returns']
    median_stats = perf_stats['median_returns']
    trade_stats = perf_stats['total_trades']
    win_stats = perf_stats['win_rates']
    
    print(f"\n📈 Performance Statistics:")
    print(f"  Compound Returns: {compound_stats['mean']:.2f} ± {compound_stats['std']:.2f}")
    print(f"    Range: {compound_stats['min']:.2f} - {compound_stats['max']:.2f}")
    print(f"  Median Returns: {median_stats['mean']:.3f} ± {median_stats['std']:.3f}")
    print(f"    Range: {median_stats['min']:.3f} - {median_stats['max']:.3f}")
    print(f"  Total Trades: {trade_stats['mean']:.0f} ± {trade_stats['std']:.0f}")
    print(f"    Range: {trade_stats['min']} - {trade_stats['max']}")
    print(f"  Win Rates: {win_stats['mean']:.1f}% ± {win_stats['std']:.1f}%")
    print(f"    Range: {win_stats['min']:.1f}% - {win_stats['max']:.1f}%")
    
    # Top performers
    top_performers = summary['top_performers']
    
    print(f"\n🏆 Top 10 Performers by Compound Return:")
    for i, performer in enumerate(top_performers['by_compound_return'][:10], 1):
        print(f"  {i:2d}. {performer['crypto']:<12}: p={performer['p']:.1%}, v={performer['v']:.1f}x, "
              f"compound={performer['compound_return']:.0f}, median={performer['median_return']:.3f}, "
              f"trades={performer['total_trades']}, win={performer['win_rate']:.1f}%")
    
    print(f"\n🏆 Top 10 Performers by Median Return:")
    for i, performer in enumerate(top_performers['by_median_return'][:10], 1):
        print(f"  {i:2d}. {performer['crypto']:<12}: p={performer['p']:.1%}, v={performer['v']:.1f}x, "
              f"compound={performer['compound_return']:.0f}, median={performer['median_return']:.3f}, "
              f"trades={performer['total_trades']}, win={performer['win_rate']:.1f}%")
    
    print(f"\n🏆 Top 10 Performers by Total Trades:")
    for i, performer in enumerate(top_performers['by_total_trades'][:10], 1):
        print(f"  {i:2d}. {performer['crypto']:<12}: p={performer['p']:.1%}, v={performer['v']:.1f}x, "
              f"compound={performer['compound_return']:.0f}, median={performer['median_return']:.3f}, "
              f"trades={performer['total_trades']}, win={performer['win_rate']:.1f}%")
    
    # Parameter distribution analysis
    print(f"\n📊 Parameter Distribution Analysis:")
    optimal_params = results['optimal_parameters']
    
    # Count parameter combinations
    param_combinations = {}
    for crypto, params in optimal_params.items():
        key = f"p={params['p']:.1%}, v={params['v']:.1f}x"
        param_combinations[key] = param_combinations.get(key, 0) + 1
    
    # Sort by frequency
    sorted_combinations = sorted(param_combinations.items(), key=lambda x: x[1], reverse=True)
    
    print(f"  Most common parameter combinations:")
    for i, (combo, count) in enumerate(sorted_combinations[:10], 1):
        print(f"    {i:2d}. {combo}: {count} cryptos")
    
    print(f"\n📄 Detailed results saved to: {filepath}")
    print("✅ Full vectorized optimization completed!")

if __name__ == "__main__":
    main()
