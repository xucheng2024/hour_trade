#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch Test Hourly Limit Strategy with Vectorized Optimization
Tests all cryptocurrencies with time window split using matrix operations for speed
"""

import sys
import os
import json
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from scipy import stats
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from strategies.historical_data_loader import get_historical_data_loader

def calculate_trades_vectorized(open_prices: np.ndarray, low_prices: np.ndarray,
                               close_prices: np.ndarray, timestamps: np.ndarray,
                               limit_percent: float, buy_fee: float, sell_fee: float,
                               start_idx: int, end_idx: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate trades using vectorized operations (much faster)
    Returns: (return_rates, return_multipliers) arrays
    """
    end_idx = min(end_idx, len(close_prices) - 2)
    
    if start_idx >= end_idx:
        return np.array([]), np.array([])
    
    # Vectorized limit price calculation
    limit_buy_prices = open_prices[start_idx:end_idx] * (limit_percent / 100.0)
    
    # Vectorized check: can we buy? (low price <= limit price)
    can_buy_mask = low_prices[start_idx:end_idx] <= limit_buy_prices
    
    if not np.any(can_buy_mask):
        return np.array([]), np.array([])
    
    # Get indices where we can buy
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

def find_best_limit_vectorized(open_prices: np.ndarray, low_prices: np.ndarray,
                               close_prices: np.ndarray, timestamps: np.ndarray,
                               train_start: int, train_end: int,
                               buy_fee: float, sell_fee: float,
                               limit_range: Tuple[float, float] = (90.0, 99.9),
                               step: float = 0.5, min_trades: int = 20) -> Optional[Dict]:
    """
    Find best limit using vectorized operations (much faster)
    """
    limit_percents = np.arange(limit_range[0], limit_range[1] + step, step)
    
    best_limit = None
    best_total_return = -np.inf
    best_result = None
    
    # Process all limit percentages in batches for efficiency
    for limit_pct in limit_percents:
        return_rates, return_multipliers = calculate_trades_vectorized(
            open_prices, low_prices, close_prices, timestamps,
            limit_pct, buy_fee, sell_fee, train_start, train_end
        )
        
        if len(return_rates) < min_trades:
            continue
        
        total_return = np.prod(return_multipliers)
        
        if total_return > best_total_return:
            best_total_return = total_return
            best_limit = limit_pct
            
            train_days = (train_end - train_start) / 24.0
            result = analyze_returns_vectorized(return_rates, return_multipliers, train_days)
            result['limit_percent'] = limit_pct
            result['return_rates'] = return_rates  # Save for statistical test
            best_result = result
    
    return best_result

def test_symbol_vectorized(instId: str, train_ratio: float = 0.7,
                           buy_fee: float = 0.001, sell_fee: float = 0.001,
                           limit_range: Tuple[float, float] = (90.0, 99.9),
                           step: float = 0.5, min_trades: int = 20) -> Optional[Dict]:
    """
    Test single symbol with vectorized operations
    Returns result dict or None if failed
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
        if n < 1000:  # Need sufficient data
            return None
        
        # Split data
        split_idx = int(n * train_ratio)
        train_start = 0
        train_end = split_idx
        test_start = split_idx
        test_end = n - 1
        
        train_days = (train_end - train_start) / 24.0
        test_days = (test_end - test_start) / 24.0
        
        # Find best limit on training set
        train_result = find_best_limit_vectorized(
            open_prices, low_prices, close_prices, timestamps,
            train_start, train_end, buy_fee, sell_fee,
            limit_range, step, min_trades
        )
        
        if train_result is None:
            return None
        
        best_limit = train_result['limit_percent']
        
        # Test on test set
        test_return_rates, test_return_multipliers = calculate_trades_vectorized(
            open_prices, low_prices, close_prices, timestamps,
            best_limit, buy_fee, sell_fee, test_start, test_end
        )
        
        if len(test_return_rates) == 0:
            return None
        
        test_result = analyze_returns_vectorized(test_return_rates, test_return_multipliers, test_days)
        
        # Statistical significance test on training
        train_sig = None
        if len(train_result.get('return_rates', [])) >= min_trades:
            train_return_rates = train_result.get('return_rates', [])
            if len(train_return_rates) >= min_trades:
                t_stat, p_value = stats.ttest_1samp(train_return_rates, 0.0, alternative='greater')
                train_sig = {
                    't_statistic': t_stat,
                    'p_value': p_value,
                    'significant_95': p_value < 0.05,
                    'significant_99': p_value < 0.01
                }
        
        # Statistical significance test on test
        test_sig = None
        if len(test_return_rates) >= min_trades:
            t_stat, p_value = stats.ttest_1samp(test_return_rates, 0.0, alternative='greater')
            test_sig = {
                't_statistic': t_stat,
                'p_value': p_value,
                'significant_95': p_value < 0.05,
                'significant_99': p_value < 0.01
            }
        
        performance_drop = train_result['total_return_rate'] - test_result['total_return_rate']
        
        return {
            'instId': instId,
            'best_limit': best_limit,
            'train_result': train_result,
            'test_result': test_result,
            'train_significance': train_sig,
            'test_significance': test_sig,
            'performance_drop': performance_drop,
            'train_days': train_days,
            'test_days': test_days
        }
        
    except Exception as e:
        print(f"Error processing {instId}: {e}")
        return None

def batch_test_all_cryptos(crypto_list: List[str], train_ratio: float = 0.7,
                           buy_fee: float = 0.001, sell_fee: float = 0.001,
                           limit_range: Tuple[float, float] = (90.0, 99.9),
                           step: float = 0.5, min_trades: int = 20,
                           max_workers: int = None) -> Dict[str, Dict]:
    """
    Batch test all cryptocurrencies with parallel processing
    """
    if max_workers is None:
        max_workers = min(multiprocessing.cpu_count(), 8)
    
    print(f"\n{'='*70}")
    print(f"Batch Testing Hourly Limit Strategy (Vectorized)")
    print(f"{'='*70}")
    print(f"Total Symbols: {len(crypto_list)}")
    print(f"Train/Test Split: {train_ratio*100:.0f}% / {(1-train_ratio)*100:.0f}%")
    print(f"Max Workers: {max_workers}")
    print(f"Limit Range: {limit_range[0]:.1f}% - {limit_range[1]:.1f}% (step: {step})")
    print(f"{'='*70}\n")
    
    results = {}
    completed = 0
    failed = 0
    
    # Process symbols in parallel
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_symbol = {
            executor.submit(test_symbol_vectorized, symbol, train_ratio, buy_fee, sell_fee,
                          limit_range, step, min_trades): symbol
            for symbol in crypto_list
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                result = future.result()
                if result:
                    results[symbol] = result
                    completed += 1
                    print(f"✅ {symbol}: limit={result['best_limit']:.2f}%, "
                          f"train_return={result['train_result']['total_return_rate']:.2f}%, "
                          f"test_return={result['test_result']['total_return_rate']:.2f}%")
                else:
                    failed += 1
                    print(f"❌ {symbol}: Failed (insufficient data or no valid limit)")
            except Exception as e:
                failed += 1
                print(f"❌ {symbol}: Error - {e}")
            
            # Progress update
            if (completed + failed) % 10 == 0:
                print(f"Progress: {completed + failed}/{len(crypto_list)} "
                      f"(completed: {completed}, failed: {failed})")
    
    print(f"\n{'='*70}")
    print(f"Batch Test Complete")
    print(f"{'='*70}")
    print(f"Total: {len(crypto_list)}")
    print(f"Successful: {completed}")
    print(f"Failed: {failed}")
    print(f"{'='*70}\n")
    
    return results

def save_results(results: Dict[str, Dict], output_file: str = "hourly_limit_batch_results.json"):
    """Save results to JSON file"""
    # Convert numpy types to Python native types for JSON serialization
    def convert_numpy(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: convert_numpy(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy(item) for item in obj]
        return obj
    
    serializable_results = convert_numpy(results)
    
    with open(output_file, 'w') as f:
        json.dump(serializable_results, f, indent=2, default=str)
    
    print(f"✅ Results saved to {output_file}")

def print_summary(results: Dict[str, Dict]):
    """Print summary statistics"""
    if not results:
        print("No results to summarize")
        return
    
    # Collect statistics
    train_returns = []
    test_returns = []
    best_limits = []
    win_rates_train = []
    win_rates_test = []
    significant_train = 0
    significant_test = 0
    
    for symbol, result in results.items():
        train_returns.append(result['train_result']['total_return_rate'])
        test_returns.append(result['test_result']['total_return_rate'])
        best_limits.append(result['best_limit'])
        win_rates_train.append(result['train_result']['win_rate'])
        win_rates_test.append(result['test_result']['win_rate'])
        
        if result.get('train_significance') and result['train_significance'].get('significant_95'):
            significant_train += 1
        if result.get('test_significance') and result['test_significance'].get('significant_95'):
            significant_test += 1
    
    train_returns = np.array(train_returns)
    test_returns = np.array(test_returns)
    best_limits = np.array(best_limits)
    
    print(f"\n{'='*70}")
    print(f"SUMMARY STATISTICS")
    print(f"{'='*70}")
    print(f"Total Symbols Tested: {len(results)}")
    print(f"\nTrain Set:")
    print(f"  Mean Return: {np.mean(train_returns):.2f}%")
    print(f"  Median Return: {np.median(train_returns):.2f}%")
    print(f"  Std Return: {np.std(train_returns):.2f}%")
    print(f"  Positive Returns: {np.sum(train_returns > 0)} ({np.sum(train_returns > 0)/len(train_returns)*100:.1f}%)")
    print(f"  Statistically Significant (95%): {significant_train} ({significant_train/len(results)*100:.1f}%)")
    print(f"\nTest Set:")
    print(f"  Mean Return: {np.mean(test_returns):.2f}%")
    print(f"  Median Return: {np.median(test_returns):.2f}%")
    print(f"  Std Return: {np.std(test_returns):.2f}%")
    print(f"  Positive Returns: {np.sum(test_returns > 0)} ({np.sum(test_returns > 0)/len(test_returns)*100:.1f}%)")
    print(f"  Statistically Significant (95%): {significant_test} ({significant_test/len(results)*100:.1f}%)")
    print(f"\nBest Limits:")
    print(f"  Mean: {np.mean(best_limits):.2f}%")
    print(f"  Median: {np.median(best_limits):.2f}%")
    print(f"  Range: {np.min(best_limits):.2f}% - {np.max(best_limits):.2f}%")
    print(f"{'='*70}\n")
    
    # Top performers
    sorted_by_test = sorted(results.items(), key=lambda x: x[1]['test_result']['total_return_rate'], reverse=True)
    print(f"\n{'='*70}")
    print(f"TOP 10 PERFORMERS (by Test Return)")
    print(f"{'='*70}")
    print(f"{'Symbol':<15} {'Limit':<10} {'Train Return':<15} {'Test Return':<15} {'Win Rate':<12}")
    print(f"{'-'*70}")
    for symbol, result in sorted_by_test[:10]:
        print(f"{symbol:<15} {result['best_limit']:>7.2f}%  "
              f"{result['train_result']['total_return_rate']:>12.2f}%  "
              f"{result['test_result']['total_return_rate']:>12.2f}%  "
              f"{result['test_result']['win_rate']:>9.2f}%")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch test hourly limit strategy (vectorized)')
    parser.add_argument('--crypto-list', type=str, default='src/config/cryptos_selected.json',
                       help='Path to crypto list JSON file')
    parser.add_argument('--train-ratio', type=float, default=0.7, help='Train ratio')
    parser.add_argument('--buy-fee', type=float, default=0.001, help='Buy fee rate')
    parser.add_argument('--sell-fee', type=float, default=0.001, help='Sell fee rate')
    parser.add_argument('--limit-min', type=float, default=90.0, help='Min limit percentage')
    parser.add_argument('--limit-max', type=float, default=99.9, help='Max limit percentage')
    parser.add_argument('--limit-step', type=float, default=0.5, help='Limit search step')
    parser.add_argument('--min-trades', type=int, default=20, help='Minimum trades required')
    parser.add_argument('--max-workers', type=int, default=None, help='Max parallel workers')
    parser.add_argument('--output', type=str, default='hourly_limit_batch_results.json',
                       help='Output JSON file')
    
    args = parser.parse_args()
    
    # Load crypto list
    with open(args.crypto_list, 'r') as f:
        crypto_list = json.load(f)
    
    # Run batch test
    results = batch_test_all_cryptos(
        crypto_list,
        train_ratio=args.train_ratio,
        buy_fee=args.buy_fee,
        sell_fee=args.sell_fee,
        limit_range=(args.limit_min, args.limit_max),
        step=args.limit_step,
        min_trades=args.min_trades,
        max_workers=args.max_workers
    )
    
    # Save results
    if results:
        save_results(results, args.output)
        print_summary(results)
    else:
        print("No results to save")
