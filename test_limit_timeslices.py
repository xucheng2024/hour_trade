#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Limit Strategy on Multiple Time Slices
Apply the found limit to different time slices to find cryptocurrencies
that perform well across all time periods
"""

import sys
import os
import json
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from scipy import stats

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
        'total_return': total_return,
        'total_return_rate': (total_return - 1.0) * 100,
        'annualized_return': annualized_return
    }

def test_symbol_timeslices(instId: str, limit_percent: float,
                           buy_fee: float = 0.001, sell_fee: float = 0.001,
                           num_slices: int = 6, min_slice_days: int = 30,
                           min_trades_per_slice: int = 5) -> Optional[Dict]:
    """
    Test symbol with limit on multiple time slices
    
    Args:
        instId: Symbol to test
        limit_percent: Limit percentage to use
        buy_fee: Buy fee rate
        sell_fee: Sell fee rate
        num_slices: Number of time slices to split data into
        min_slice_days: Minimum days per slice
        min_trades_per_slice: Minimum trades per slice
    
    Returns:
        Dictionary with results for each slice
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
        if n < num_slices * min_slice_days * 24:  # Need sufficient data
            return None
        
        # Calculate slice boundaries
        slice_size = n // num_slices
        slices = []
        
        for i in range(num_slices):
            start_idx = i * slice_size
            end_idx = (i + 1) * slice_size if i < num_slices - 1 else n - 1
            
            # Ensure minimum slice size
            if (end_idx - start_idx) < min_slice_days * 24:
                continue
            
            start_time = datetime.fromtimestamp(timestamps[start_idx] / 1000)
            end_time = datetime.fromtimestamp(timestamps[end_idx - 1] / 1000)
            days = (end_idx - start_idx) / 24.0
            
            slices.append({
                'slice_idx': i,
                'start_idx': start_idx,
                'end_idx': end_idx,
                'start_time': start_time,
                'end_time': end_time,
                'days': days
            })
        
        # Test each slice
        slice_results = []
        for slice_info in slices:
            return_rates, return_multipliers = calculate_trades_vectorized(
                open_prices, low_prices, close_prices, timestamps,
                limit_percent, buy_fee, sell_fee,
                slice_info['start_idx'], slice_info['end_idx']
            )
            
            if len(return_rates) < min_trades_per_slice:
                slice_result = {
                    'slice_idx': slice_info['slice_idx'],
                    'start_time': slice_info['start_time'].isoformat(),
                    'end_time': slice_info['end_time'].isoformat(),
                    'days': slice_info['days'],
                    'total_trades': len(return_rates),
                    'total_return_rate': None,
                    'win_rate': None,
                    'avg_return': None,
                    'valid': False
                }
            else:
                result = analyze_returns_vectorized(return_rates, return_multipliers, slice_info['days'])
                slice_result = {
                    'slice_idx': slice_info['slice_idx'],
                    'start_time': slice_info['start_time'].isoformat(),
                    'end_time': slice_info['end_time'].isoformat(),
                    'days': slice_info['days'],
                    'total_trades': result['total_trades'],
                    'total_return_rate': result['total_return_rate'],
                    'win_rate': result['win_rate'],
                    'avg_return': result['avg_return'],
                    'median_return': result['median_return'],
                    'total_return': result['total_return'],
                    'valid': True
                }
            
            slice_results.append(slice_result)
        
        # Calculate aggregate statistics
        valid_slices = [s for s in slice_results if s['valid']]
        if len(valid_slices) < 3:  # Need at least 3 valid slices
            return None
        
        valid_returns = np.array([s['total_return_rate'] for s in valid_slices])
        valid_win_rates = np.array([s['win_rate'] for s in valid_slices])
        
        # Calculate consistency metrics
        positive_slices = np.sum(valid_returns > 0)
        consistency = positive_slices / len(valid_slices) * 100  # % of slices with positive returns
        
        mean_return = np.mean(valid_returns)
        median_return = np.median(valid_returns)
        std_return = np.std(valid_returns)
        
        # Coefficient of variation (lower is better - more consistent)
        cv = std_return / abs(mean_return) if mean_return != 0 else np.inf
        
        # Sharpe-like metric (mean / std, higher is better)
        sharpe_like = mean_return / std_return if std_return > 0 else 0
        
        return {
            'instId': instId,
            'limit_percent': limit_percent,
            'num_slices': num_slices,
            'valid_slices': len(valid_slices),
            'slice_results': slice_results,
            'aggregate': {
                'mean_return': float(mean_return),
                'median_return': float(median_return),
                'std_return': float(std_return),
                'consistency': float(consistency),
                'positive_slices': int(positive_slices),
                'coefficient_of_variation': float(cv),
                'sharpe_like': float(sharpe_like),
                'mean_win_rate': float(np.mean(valid_win_rates)),
                'total_trades': int(sum(s['total_trades'] for s in valid_slices))
            }
        }
        
    except Exception as e:
        print(f"Error processing {instId}: {e}")
        return None

def batch_test_timeslices(results_file: str, num_slices: int = 6,
                         min_trades_per_slice: int = 5,
                         buy_fee: float = 0.001, sell_fee: float = 0.001) -> Dict[str, Dict]:
    """
    Batch test all symbols with time slices
    
    Args:
        results_file: Path to JSON file with limit results
        num_slices: Number of time slices
        min_trades_per_slice: Minimum trades per slice
        buy_fee: Buy fee rate
        sell_fee: Sell fee rate
    
    Returns:
        Dictionary with timeslice results for each symbol
    """
    # Load limit results
    with open(results_file, 'r') as f:
        limit_results = json.load(f)
    
    print(f"\n{'='*70}")
    print(f"Testing Limit Strategy on Multiple Time Slices")
    print(f"{'='*70}")
    print(f"Total Symbols: {len(limit_results)}")
    print(f"Number of Slices: {num_slices}")
    print(f"Min Trades per Slice: {min_trades_per_slice}")
    print(f"{'='*70}\n")
    
    timeslice_results = {}
    completed = 0
    failed = 0
    
    for symbol, result in limit_results.items():
        limit_percent = result['best_limit']
        
        slice_result = test_symbol_timeslices(
            symbol, limit_percent, buy_fee, sell_fee,
            num_slices, min_trades_per_slice=min_trades_per_slice
        )
        
        if slice_result:
            timeslice_results[symbol] = slice_result
            completed += 1
            
            consistency = slice_result['aggregate']['consistency']
            mean_return = slice_result['aggregate']['mean_return']
            
            print(f"✅ {symbol}: limit={limit_percent:.1f}%, "
                  f"slices={slice_result['valid_slices']}/{num_slices}, "
                  f"consistency={consistency:.1f}%, mean_return={mean_return:.2f}%")
        else:
            failed += 1
            print(f"❌ {symbol}: Failed (insufficient data)")
        
        if (completed + failed) % 20 == 0:
            print(f"Progress: {completed + failed}/{len(limit_results)} "
                  f"(completed: {completed}, failed: {failed})")
    
    print(f"\n{'='*70}")
    print(f"Time Slice Test Complete")
    print(f"{'='*70}")
    print(f"Total: {len(limit_results)}")
    print(f"Successful: {completed}")
    print(f"Failed: {failed}")
    print(f"{'='*70}\n")
    
    return timeslice_results

def find_best_consistent_symbols(timeslice_results: Dict[str, Dict],
                                min_consistency: float = 80.0,
                                min_mean_return: float = 5.0) -> List[Tuple[str, Dict]]:
    """
    Find symbols that perform well across all time slices
    
    Args:
        timeslice_results: Results from batch_test_timeslices
        min_consistency: Minimum consistency (\% of positive slices)
        min_mean_return: Minimum mean return across slices
    
    Returns:
        List of (symbol, aggregate_stats) tuples sorted by consistency and return
    """
    candidates = []
    
    for symbol, result in timeslice_results.items():
        agg = result['aggregate']
        
        if (agg['consistency'] >= min_consistency and 
            agg['mean_return'] >= min_mean_return):
            candidates.append((symbol, agg))
    
    # Sort by consistency first, then by mean return
    candidates.sort(key=lambda x: (x[1]['consistency'], x[1]['mean_return']), reverse=True)
    
    return candidates

def print_summary(timeslice_results: Dict[str, Dict],
                 min_consistency: float = 80.0,
                 min_mean_return: float = 5.0):
    """Print summary statistics"""
    if not timeslice_results:
        print("No results to summarize")
        return
    
    # Find best consistent symbols
    candidates = find_best_consistent_symbols(timeslice_results, min_consistency, min_mean_return)
    
    print(f"\n{'='*70}")
    print(f"SUMMARY - SYMBOLS PERFORMING WELL ACROSS ALL TIME SLICES")
    print(f"{'='*70}")
    print(f"Filter Criteria:")
    print(f"  Min Consistency: {min_consistency:.1f}%")
    print(f"  Min Mean Return: {min_mean_return:.1f}%")
    print(f"\nFound {len(candidates)} symbols meeting criteria\n")
    
    if candidates:
        print(f"{'='*70}")
        print(f"TOP 30 MOST CONSISTENT PERFORMERS")
        print(f"{'='*70}")
        print(f"{'Symbol':<15} {'Limit':<8} {'Slices':<8} {'Consistency':<12} "
              f"{'Mean Ret':<12} {'Median Ret':<12} {'Std Dev':<10} {'CV':<8} {'Sharpe':<8}")
        print('-'*105)
        
        for symbol, agg in candidates[:30]:
            symbol_result = timeslice_results[symbol]
            limit = symbol_result['limit_percent']
            valid_slices = symbol_result['valid_slices']
            
            print(f"{symbol:<15} {limit:>6.1f}%  {valid_slices:>6}  "
                  f"{agg['consistency']:>9.1f}%  {agg['mean_return']:>9.2f}%  "
                  f"{agg['median_return']:>9.2f}%  {agg['std_return']:>8.2f}%  "
                  f"{agg['coefficient_of_variation']:>6.2f}  {agg['sharpe_like']:>6.2f}")
        
        print(f"{'='*70}\n")
    
    # Overall statistics
    all_consistencies = [r['aggregate']['consistency'] for r in timeslice_results.values()]
    all_mean_returns = [r['aggregate']['mean_return'] for r in timeslice_results.values()]
    
    print(f"\n{'='*70}")
    print(f"OVERALL STATISTICS")
    print(f"{'='*70}")
    print(f"Total Symbols: {len(timeslice_results)}")
    print(f"\nConsistency Statistics:")
    print(f"  Mean: {np.mean(all_consistencies):.2f}%")
    print(f"  Median: {np.median(all_consistencies):.2f}%")
    print(f"  Std Dev: {np.std(all_consistencies):.2f}%")
    print(f"\nMean Return Statistics:")
    print(f"  Mean: {np.mean(all_mean_returns):.2f}%")
    print(f"  Median: {np.median(all_mean_returns):.2f}%")
    print(f"  Std Dev: {np.std(all_mean_returns):.2f}%")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test limit strategy on time slices')
    parser.add_argument('--results-file', type=str, default='hourly_limit_batch_results.json',
                       help='Path to limit results JSON file')
    parser.add_argument('--num-slices', type=int, default=6, help='Number of time slices')
    parser.add_argument('--min-trades-per-slice', type=int, default=5,
                       help='Minimum trades per slice')
    parser.add_argument('--buy-fee', type=float, default=0.001, help='Buy fee rate')
    parser.add_argument('--sell-fee', type=float, default=0.001, help='Sell fee rate')
    parser.add_argument('--min-consistency', type=float, default=80.0,
                       help='Minimum consistency for filtering')
    parser.add_argument('--min-mean-return', type=float, default=5.0,
                       help='Minimum mean return for filtering')
    parser.add_argument('--output', type=str, default='limit_timeslices_results.json',
                       help='Output JSON file')
    
    args = parser.parse_args()
    
    # Run batch test
    results = batch_test_timeslices(
        args.results_file,
        num_slices=args.num_slices,
        min_trades_per_slice=args.min_trades_per_slice,
        buy_fee=args.buy_fee,
        sell_fee=args.sell_fee
    )
    
    # Save results
    if results:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"✅ Results saved to {args.output}")
        
        # Print summary
        print_summary(results, args.min_consistency, args.min_mean_return)
    else:
        print("No results to save")
