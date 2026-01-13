#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Limit Strategy on Recent 3 Months Data
Apply high-consistency limits to recent 3 months and calculate returns
"""

import sys
import os
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from strategies.historical_data_loader import get_historical_data_loader

def calculate_trades_vectorized(open_prices: np.ndarray, low_prices: np.ndarray,
                               close_prices: np.ndarray, timestamps: np.ndarray,
                               limit_percent: float, buy_fee: float, sell_fee: float,
                               start_idx: int, end_idx: int) -> Tuple[np.ndarray, np.ndarray]:
    """Calculate trades using vectorized operations"""
    end_idx = min(end_idx, len(close_prices) - 2)
    
    if start_idx >= end_idx:
        return np.array([]), np.array([])
    
    # Vectorized limit price calculation
    limit_buy_prices = open_prices[start_idx:end_idx] * (limit_percent / 100.0)
    
    # Vectorized check: can we buy?
    can_buy_mask = low_prices[start_idx:end_idx] <= limit_buy_prices
    
    if not np.any(can_buy_mask):
        return np.array([]), np.array([])
    
    buy_indices = np.arange(start_idx, end_idx)[can_buy_mask]
    
    if len(buy_indices) == 0:
        return np.array([]), np.array([])
    
    # Vectorized price calculations
    buy_prices = limit_buy_prices[can_buy_mask]
    sell_prices = close_prices[buy_indices + 1]
    
    # Vectorized fee calculations
    effective_buy_prices = buy_prices * (1 + buy_fee)
    effective_sell_prices = sell_prices * (1 - sell_fee)
    
    # Vectorized return calculations
    return_rates = (effective_sell_prices / effective_buy_prices) - 1.0
    return_multipliers = effective_sell_prices / effective_buy_prices
    
    return return_rates, return_multipliers

def analyze_returns_vectorized(return_rates: np.ndarray, return_multipliers: np.ndarray,
                               days_tested: float = None) -> Dict:
    """Analyze returns using vectorized operations"""
    if len(return_rates) == 0:
        return {}
    
    total_return = np.prod(return_multipliers)
    avg_return = np.mean(return_rates)
    median_return = np.median(return_rates)
    std_return = np.std(return_rates, ddof=1)
    
    profitable_count = np.sum(return_rates > 0)
    losing_count = np.sum(return_rates <= 0)
    win_rate = profitable_count / len(return_rates) * 100
    
    annualized_return = None
    if days_tested and days_tested > 0:
        annualized_return = ((total_return ** (365.0 / days_tested)) - 1.0) * 100
    
    return {
        'total_trades': len(return_rates),
        'profitable_trades': int(profitable_count),
        'losing_trades': int(losing_count),
        'win_rate': win_rate,
        'avg_return': avg_return,
        'median_return': median_return,
        'std_return': std_return,
        'total_return': total_return,
        'total_return_rate': (total_return - 1.0) * 100,
        'annualized_return': annualized_return
    }

def test_recent_3months(instId: str, limit_percent: float,
                       buy_fee: float = 0.001, sell_fee: float = 0.001,
                       months: int = 3) -> Optional[Dict]:
    """
    Test symbol with limit on recent N months data
    
    Args:
        instId: Symbol to test
        limit_percent: Limit percentage to use
        buy_fee: Buy fee rate
        sell_fee: Sell fee rate
        months: Number of months to test (default: 3)
    
    Returns:
        Dictionary with results
    """
    try:
        data_loader = get_historical_data_loader()
        
        # Load hourly data
        data = data_loader.get_hist_candle_data(instId, 0, 0, "1H")
        if data is None or len(data) == 0:
            return None
        
        # Parse data
        timestamps = data[:, 0].astype(np.int64)
        open_prices = data[:, 1].astype(np.float64)
        low_prices = data[:, 3].astype(np.float64)
        close_prices = data[:, 4].astype(np.float64)
        
        n = len(close_prices)
        if n == 0:
            return None
        
        # Get recent N months data (approximately)
        hours_per_month = 30 * 24  # 30 days * 24 hours
        hours_to_use = months * hours_per_month
        
        if n < hours_to_use:
            # Use all available data
            start_idx = 0
            end_idx = n - 1
            actual_months = n / hours_per_month
        else:
            # Use recent N months
            start_idx = n - hours_to_use
            end_idx = n - 1
            actual_months = months
        
        start_time = datetime.fromtimestamp(timestamps[start_idx] / 1000)
        end_time = datetime.fromtimestamp(timestamps[end_idx] / 1000)
        days = (end_idx - start_idx) / 24.0
        
        # Calculate trades
        return_rates, return_multipliers = calculate_trades_vectorized(
            open_prices, low_prices, close_prices, timestamps,
            limit_percent, buy_fee, sell_fee,
            start_idx, end_idx
        )
        
        if len(return_rates) == 0:
            return {
                'instId': instId,
                'limit_percent': limit_percent,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'days': days,
                'total_trades': 0,
                'total_return_rate': None,
                'valid': False
            }
        
        result = analyze_returns_vectorized(return_rates, return_multipliers, days)
        
        return {
            'instId': instId,
            'limit_percent': limit_percent,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'days': days,
            'actual_months': actual_months,
            'total_trades': result['total_trades'],
            'total_return_rate': result['total_return_rate'],
            'win_rate': result['win_rate'],
            'avg_return': result['avg_return'],
            'median_return': result['median_return'],
            'total_return': result['total_return'],
            'annualized_return': result['annualized_return'],
            'valid': True
        }
        
    except Exception as e:
        print(f"Error processing {instId}: {e}")
        return None

def batch_test_recent_3months(timeslice_results_file: str,
                              min_consistency: float = 90.0,
                              min_mean_return: float = 10.0,
                              buy_fee: float = 0.001,
                              sell_fee: float = 0.001,
                              months: int = 3) -> Dict[str, Dict]:
    """
    Batch test high-consistency symbols on recent 3 months
    
    Args:
        timeslice_results_file: Path to timeslice results JSON file
        min_consistency: Minimum consistency threshold
        min_mean_return: Minimum mean return threshold
        buy_fee: Buy fee rate
        sell_fee: Sell fee rate
        months: Number of months to test
    
    Returns:
        Dictionary with recent 3 months results
    """
    # Load timeslice results
    with open(timeslice_results_file, 'r') as f:
        timeslice_results = json.load(f)
    
    # Filter high-consistency symbols
    high_consistency_symbols = []
    for symbol, result in timeslice_results.items():
        agg = result['aggregate']
        if (agg['consistency'] >= min_consistency and 
            agg['mean_return'] >= min_mean_return and
            agg['mean_return'] < 500):  # Filter extreme outliers
            high_consistency_symbols.append({
                'symbol': symbol,
                'limit': result['limit_percent'],
                'consistency': agg['consistency'],
                'mean_return': agg['mean_return']
            })
    
    # Sort by consistency and return
    high_consistency_symbols.sort(key=lambda x: (x['consistency'], x['mean_return']), reverse=True)
    
    print(f"\n{'='*70}")
    print(f"Testing High-Consistency Symbols on Recent {months} Months")
    print(f"{'='*70}")
    print(f"Criteria: Consistency >= {min_consistency}%, Mean Return >= {min_mean_return}%")
    print(f"Total Symbols to Test: {len(high_consistency_symbols)}")
    print(f"{'='*70}\n")
    
    results = {}
    completed = 0
    failed = 0
    
    for item in high_consistency_symbols:
        symbol = item['symbol']
        limit = item['limit']
        
        result = test_recent_3months(symbol, limit, buy_fee, sell_fee, months)
        
        if result and result.get('valid'):
            results[symbol] = result
            completed += 1
            print(f"✅ {symbol}: limit={limit:.1f}%, "
                  f"trades={result['total_trades']}, "
                  f"return={result['total_return_rate']:.2f}%, "
                  f"win_rate={result['win_rate']:.1f}%")
        else:
            failed += 1
            if result and not result.get('valid'):
                print(f"❌ {symbol}: No trades in recent {months} months")
            else:
                print(f"❌ {symbol}: Failed (insufficient data)")
        
        if (completed + failed) % 20 == 0:
            print(f"Progress: {completed + failed}/{len(high_consistency_symbols)} "
                  f"(completed: {completed}, failed: {failed})")
    
    print(f"\n{'='*70}")
    print(f"Recent {months} Months Test Complete")
    print(f"{'='*70}")
    print(f"Total: {len(high_consistency_symbols)}")
    print(f"Successful: {completed}")
    print(f"Failed: {failed}")
    print(f"{'='*70}\n")
    
    return results

def print_summary(results: Dict[str, Dict]):
    """Print summary statistics"""
    if not results:
        print("No results to summarize")
        return
    
    # Collect statistics
    returns = np.array([r['total_return_rate'] for r in results.values() if r.get('valid')])
    win_rates = np.array([r['win_rate'] for r in results.values() if r.get('valid')])
    trades = np.array([r['total_trades'] for r in results.values() if r.get('valid')])
    
    print(f"\n{'='*70}")
    print(f"SUMMARY - RECENT 3 MONTHS PERFORMANCE")
    print(f"{'='*70}")
    print(f"Total Symbols Tested: {len(results)}")
    print(f"Symbols with Valid Results: {len(returns)}")
    print(f"\nReturn Statistics:")
    print(f"  Mean Return: {np.mean(returns):.2f}%")
    print(f"  Median Return: {np.median(returns):.2f}%")
    print(f"  Std Dev: {np.std(returns):.2f}%")
    print(f"  Positive Returns: {np.sum(returns > 0)} ({np.sum(returns > 0)/len(returns)*100:.1f}%)")
    print(f"\nWin Rate Statistics:")
    print(f"  Mean Win Rate: {np.mean(win_rates):.2f}%")
    print(f"  Median Win Rate: {np.median(win_rates):.2f}%")
    print(f"\nTrade Statistics:")
    print(f"  Mean Trades: {np.mean(trades):.1f}")
    print(f"  Median Trades: {np.median(trades):.1f}")
    print(f"{'='*70}\n")
    
    # Top performers
    sorted_results = sorted(results.items(), 
                           key=lambda x: x[1].get('total_return_rate', -999) if x[1].get('valid') else -999,
                           reverse=True)
    
    print(f"{'='*70}")
    print(f"TOP 30 PERFORMERS (Recent 3 Months)")
    print(f"{'='*70}")
    print(f"{'Symbol':<15} {'Limit':<8} {'Trades':<8} {'Return %':<12} {'Win Rate':<10} {'Avg Return':<12}")
    print('-'*70)
    
    for symbol, result in sorted_results[:30]:
        if result.get('valid'):
            print(f"{symbol:<15} {result['limit_percent']:>6.1f}%  "
                  f"{result['total_trades']:>6}  "
                  f"{result['total_return_rate']:>9.2f}%  "
                  f"{result['win_rate']:>7.1f}%  "
                  f"{result['avg_return']*100:>9.2f}%")
    
    print(f"{'='*70}\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test limit strategy on recent 3 months')
    parser.add_argument('--timeslice-results', type=str, default='limit_timeslices_results.json',
                       help='Path to timeslice results JSON file')
    parser.add_argument('--min-consistency', type=float, default=90.0,
                       help='Minimum consistency threshold')
    parser.add_argument('--min-mean-return', type=float, default=10.0,
                       help='Minimum mean return threshold')
    parser.add_argument('--buy-fee', type=float, default=0.001, help='Buy fee rate')
    parser.add_argument('--sell-fee', type=float, default=0.001, help='Sell fee rate')
    parser.add_argument('--months', type=int, default=3, help='Number of months to test')
    parser.add_argument('--output', type=str, default='recent_3months_results.json',
                       help='Output JSON file')
    
    args = parser.parse_args()
    
    # Run batch test
    results = batch_test_recent_3months(
        args.timeslice_results,
        min_consistency=args.min_consistency,
        min_mean_return=args.min_mean_return,
        buy_fee=args.buy_fee,
        sell_fee=args.sell_fee,
        months=args.months
    )
    
    # Save results
    if results:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"✅ Results saved to {args.output}")
        
        # Print summary
        print_summary(results)
    else:
        print("No results to save")
