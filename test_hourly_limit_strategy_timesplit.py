#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hourly Limit Strategy Test with Time Window Split
Test strategy: Buy at limit price in one hour, sell at next hour's close
Uses train/test split to avoid overfitting and includes statistical significance testing
"""

import sys
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from scipy import stats

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from strategies.historical_data_loader import get_historical_data_loader

def calculate_trades(open_prices: np.ndarray, high_prices: np.ndarray, 
                    low_prices: np.ndarray, close_prices: np.ndarray,
                    timestamps: np.ndarray, limit_percent: float,
                    buy_fee: float, sell_fee: float,
                    start_idx: int, end_idx: int) -> List[Dict]:
    """
    Calculate trades for given data range
    Returns list of trade dictionaries
    """
    trades = []
    end_idx = min(end_idx, len(close_prices) - 2)  # Leave room for next hour
    
    for i in range(start_idx, end_idx):
        limit_buy_price = open_prices[i] * (limit_percent / 100.0)
        
        # Check if we can buy (low price <= limit price)
        if low_prices[i] > limit_buy_price:
            continue
        
        buy_price = limit_buy_price
        sell_price = close_prices[i + 1]
        
        # Calculate return with fees
        effective_buy_price = buy_price * (1 + buy_fee)
        effective_sell_price = sell_price * (1 - sell_fee)
        return_rate = (effective_sell_price / effective_buy_price) - 1.0
        return_multiplier = effective_sell_price / effective_buy_price
        
        trade = {
            'buy_time': datetime.fromtimestamp(timestamps[i] / 1000),
            'sell_time': datetime.fromtimestamp(timestamps[i + 1] / 1000),
            'buy_price': buy_price,
            'sell_price': sell_price,
            'return_rate': return_rate,
            'return_multiplier': return_multiplier
        }
        trades.append(trade)
    
    return trades

def analyze_trades(trades: List[Dict], days_tested: float = None) -> Dict:
    """Analyze trades and calculate statistics"""
    if len(trades) == 0:
        return {}
    
    return_rates = np.array([t['return_rate'] for t in trades])
    return_multipliers = np.array([t['return_multiplier'] for t in trades])
    
    total_return = np.prod(return_multipliers)
    avg_return = np.mean(return_rates)
    median_return = np.median(return_rates)
    std_return = np.std(return_rates, ddof=1)  # Sample standard deviation
    
    profitable_trades = np.sum(return_rates > 0)
    losing_trades = np.sum(return_rates <= 0)
    win_rate = profitable_trades / len(trades) * 100
    
    # Calculate annualized return if days_tested provided
    annualized_return = None
    if days_tested and days_tested > 0:
        annualized_return = ((total_return ** (365.0 / days_tested)) - 1.0) * 100
    
    return {
        'total_trades': len(trades),
        'profitable_trades': profitable_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'median_return': median_return,
        'std_return': std_return,
        'total_return': total_return,
        'total_return_rate': (total_return - 1.0) * 100,
        'annualized_return': annualized_return,
        'return_rates': return_rates,
        'return_multipliers': return_multipliers,
        'trades': trades
    }

def statistical_significance_test(return_rates: np.ndarray, min_trades: int = 30) -> Dict:
    """
    Test statistical significance of returns
    H0: mean return <= 0 (strategy is not profitable)
    H1: mean return > 0 (strategy is profitable)
    """
    if len(return_rates) < min_trades:
        return {
            'significant': False,
            'reason': f'Insufficient trades: {len(return_rates)} < {min_trades}'
        }
    
    # One-sample t-test: test if mean return is significantly greater than 0
    t_stat, p_value = stats.ttest_1samp(return_rates, 0.0, alternative='greater')
    
    # Standard significance levels
    significant_95 = p_value < 0.05
    significant_99 = p_value < 0.01
    
    return {
        't_statistic': t_stat,
        'p_value': p_value,
        'significant_95': significant_95,
        'significant_99': significant_99,
        'significant': significant_95,
        'n': len(return_rates)
    }

def find_best_limit_train(open_prices: np.ndarray, high_prices: np.ndarray,
                          low_prices: np.ndarray, close_prices: np.ndarray,
                          timestamps: np.ndarray, train_start: int, train_end: int,
                          buy_fee: float, sell_fee: float,
                          limit_range: Tuple[float, float] = (90.0, 99.9),
                          step: float = 0.5, min_trades: int = 20) -> Optional[Dict]:
    """
    Find best limit percentage on training set
    """
    best_result = None
    best_limit = None
    best_total_return = -np.inf
    
    limit_percents = np.arange(limit_range[0], limit_range[1] + step, step)
    
    print(f"🔍 Searching for best limit in training set...")
    print(f"   Testing {len(limit_percents)} limit percentages: {limit_range[0]:.1f}% - {limit_range[1]:.1f}%\n")
    
    for limit_pct in limit_percents:
        trades = calculate_trades(open_prices, high_prices, low_prices, close_prices,
                                 timestamps, limit_pct, buy_fee, sell_fee,
                                 train_start, train_end)
        
        if len(trades) < min_trades:
            continue
        
        result = analyze_trades(trades)
        total_return = result['total_return']
        
        if total_return > best_total_return:
            best_total_return = total_return
            best_limit = limit_pct
            best_result = result
            best_result['limit_percent'] = limit_pct
    
    if best_limit is None:
        print(f"❌ No valid limit found (minimum {min_trades} trades required)")
        return None
    
    return best_result

def test_with_timesplit(instId: str, train_ratio: float = 0.7,
                       buy_fee: float = 0.001, sell_fee: float = 0.001,
                       limit_range: Tuple[float, float] = (90.0, 99.9),
                       step: float = 0.5, min_trades: int = 20) -> Dict:
    """
    Test hourly limit strategy with time window split (train/test)
    
    Args:
        instId: Instrument ID
        train_ratio: Ratio of data to use for training (default: 0.7 = 70%)
        buy_fee: Buy fee rate
        sell_fee: Sell fee rate
        limit_range: Range of limit percentages to test (min, max)
        step: Step size for limit percentage search
        min_trades: Minimum number of trades required
    
    Returns:
        Dictionary with train/test results
    """
    data_loader = get_historical_data_loader()
    
    print(f"\n{'='*70}")
    print(f"Hourly Limit Strategy Test with Time Window Split")
    print(f"{'='*70}")
    print(f"Symbol: {instId}")
    print(f"Train/Test Split: {train_ratio*100:.0f}% / {(1-train_ratio)*100:.0f}%")
    print(f"Buy Fee: {buy_fee*100:.3f}%, Sell Fee: {sell_fee*100:.3f}%")
    print(f"{'='*70}\n")
    
    # Load hourly data
    data = data_loader.get_hist_candle_data(instId, 0, 0, "1H")
    if data is None or len(data) == 0:
        print(f"❌ No data available for {instId}")
        return {}
    
    print(f"✅ Loaded {len(data)} hours of data")
    
    # Parse data
    timestamps = data[:, 0].astype(np.int64)
    open_prices = data[:, 1].astype(np.float64)
    high_prices = data[:, 2].astype(np.float64)
    low_prices = data[:, 3].astype(np.float64)
    close_prices = data[:, 4].astype(np.float64)
    
    n = len(close_prices)
    
    # Split data into train and test sets
    split_idx = int(n * train_ratio)
    train_start = 0
    train_end = split_idx
    test_start = split_idx
    test_end = n - 1
    
    train_hours = train_end - train_start
    test_hours = test_end - test_start
    train_days = train_hours / 24.0
    test_days = test_hours / 24.0
    
    train_start_time = datetime.fromtimestamp(timestamps[train_start] / 1000)
    train_end_time = datetime.fromtimestamp(timestamps[train_end - 1] / 1000)
    test_start_time = datetime.fromtimestamp(timestamps[test_start] / 1000)
    test_end_time = datetime.fromtimestamp(timestamps[test_end - 1] / 1000)
    
    print(f"📊 Data Split:")
    print(f"   Train: {train_start_time.strftime('%Y-%m-%d')} to {train_end_time.strftime('%Y-%m-%d')} ({train_hours} hours, {train_days:.1f} days)")
    print(f"   Test:  {test_start_time.strftime('%Y-%m-%d')} to {test_end_time.strftime('%Y-%m-%d')} ({test_hours} hours, {test_days:.1f} days)\n")
    
    # Step 1: Find best limit on training set
    train_result = find_best_limit_train(open_prices, high_prices, low_prices, close_prices,
                                        timestamps, train_start, train_end,
                                        buy_fee, sell_fee, limit_range, step, min_trades)
    
    if train_result is None:
        print("❌ Failed to find optimal limit on training set")
        return {}
    
    best_limit = train_result['limit_percent']
    
    print(f"✅ Best limit found on training set: {best_limit:.2f}%\n")
    print(f"{'='*70}")
    print(f"TRAINING SET RESULTS")
    print(f"{'='*70}")
    print(f"Best Limit: {best_limit:.2f}%")
    print(f"Total Trades: {train_result['total_trades']}")
    print(f"Win Rate: {train_result['win_rate']:.2f}%")
    print(f"Total Return: {train_result['total_return_rate']:.2f}% ({train_result['total_return']:.4f}x)")
    if train_result['annualized_return']:
        print(f"Annualized Return: {train_result['annualized_return']:.2f}%")
    print(f"Average Return per Trade: {train_result['avg_return']*100:.3f}%")
    print(f"Median Return per Trade: {train_result['median_return']*100:.3f}%")
    
    # Statistical significance test on training set
    train_sig = statistical_significance_test(train_result['return_rates'], min_trades)
    print(f"\nStatistical Significance (Training):")
    print(f"   t-statistic: {train_sig['t_statistic']:.4f}")
    print(f"   p-value: {train_sig['p_value']:.6f}")
    print(f"   Significant at 95%: {'✅ YES' if train_sig['significant_95'] else '❌ NO'}")
    print(f"   Significant at 99%: {'✅ YES' if train_sig['significant_99'] else '❌ NO'}")
    print(f"{'='*70}\n")
    
    # Step 2: Test on test set with the best limit from training
    print(f"🧪 Testing on TEST SET with limit {best_limit:.2f}%...\n")
    
    test_trades = calculate_trades(open_prices, high_prices, low_prices, close_prices,
                                  timestamps, best_limit, buy_fee, sell_fee,
                                  test_start, test_end)
    
    test_result = analyze_trades(test_trades, test_days)
    
    if test_result['total_trades'] == 0:
        print("❌ No trades executed on test set")
        return {}
    
    print(f"{'='*70}")
    print(f"TEST SET RESULTS")
    print(f"{'='*70}")
    print(f"Limit Used: {best_limit:.2f}% (from training set)")
    print(f"Total Trades: {test_result['total_trades']}")
    print(f"Win Rate: {test_result['win_rate']:.2f}%")
    print(f"Total Return: {test_result['total_return_rate']:.2f}% ({test_result['total_return']:.4f}x)")
    if test_result['annualized_return']:
        print(f"Annualized Return: {test_result['annualized_return']:.2f}%")
    print(f"Average Return per Trade: {test_result['avg_return']*100:.3f}%")
    print(f"Median Return per Trade: {test_result['median_return']*100:.3f}%")
    
    # Statistical significance test on test set
    test_sig = statistical_significance_test(test_result['return_rates'], min_trades)
    print(f"\nStatistical Significance (Test):")
    if 't_statistic' in test_sig:
        print(f"   t-statistic: {test_sig['t_statistic']:.4f}")
        print(f"   p-value: {test_sig['p_value']:.6f}")
        print(f"   Significant at 95%: {'✅ YES' if test_sig['significant_95'] else '❌ NO'}")
        print(f"   Significant at 99%: {'✅ YES' if test_sig['significant_99'] else '❌ NO'}")
    else:
        print(f"   {test_sig.get('reason', 'Insufficient data for statistical test')}")
    print(f"{'='*70}\n")
    
    # Compare train vs test
    print(f"{'='*70}")
    print(f"TRAIN vs TEST COMPARISON")
    print(f"{'='*70}")
    print(f"{'Metric':<25} {'Train':<20} {'Test':<20}")
    print(f"{'-'*70}")
    print(f"{'Best Limit (%)':<25} {best_limit:<20.2f} {best_limit:<20.2f}")
    print(f"{'Total Trades':<25} {train_result['total_trades']:<20} {test_result['total_trades']:<20}")
    print(f"{'Win Rate (%)':<25} {train_result['win_rate']:<20.2f} {test_result['win_rate']:<20.2f}")
    print(f"{'Total Return (%)':<25} {train_result['total_return_rate']:<20.2f} {test_result['total_return_rate']:<20.2f}")
    print(f"{'Avg Return/Trade (%)':<25} {train_result['avg_return']*100:<20.3f} {test_result['avg_return']*100:<20.3f}")
    print(f"{'Median Return/Trade (%)':<25} {train_result['median_return']*100:<20.3f} {test_result['median_return']*100:<20.3f}")
    print(f"{'-'*70}")
    
    # Calculate overfitting indicator (performance drop from train to test)
    performance_drop = train_result['total_return_rate'] - test_result['total_return_rate']
    print(f"Performance Drop (Train→Test): {performance_drop:.2f}%")
    
    if abs(performance_drop) < 20:  # Less than 20% drop is reasonable
        print(f"✅ Performance drop is reasonable (no severe overfitting)")
    elif performance_drop > 50:
        print(f"⚠️  Large performance drop - possible overfitting")
    elif performance_drop < -20:
        print(f"✅ Test performance better than train (unusual but positive)")
    
    print(f"{'='*70}\n")
    
    return {
        'instId': instId,
        'train_ratio': train_ratio,
        'best_limit': best_limit,
        'train_result': train_result,
        'test_result': test_result,
        'train_significance': train_sig,
        'test_significance': test_sig,
        'performance_drop': performance_drop
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test hourly limit strategy with time split')
    parser.add_argument('--symbol', type=str, default='BTC-USDT', help='Symbol to test')
    parser.add_argument('--train-ratio', type=float, default=0.7, help='Train ratio (default: 0.7)')
    parser.add_argument('--buy-fee', type=float, default=0.001, help='Buy fee rate')
    parser.add_argument('--sell-fee', type=float, default=0.001, help='Sell fee rate')
    parser.add_argument('--limit-min', type=float, default=90.0, help='Min limit percentage')
    parser.add_argument('--limit-max', type=float, default=99.9, help='Max limit percentage')
    parser.add_argument('--limit-step', type=float, default=0.5, help='Limit search step')
    parser.add_argument('--min-trades', type=int, default=20, help='Minimum trades required')
    
    args = parser.parse_args()
    
    test_with_timesplit(
        args.symbol,
        train_ratio=args.train_ratio,
        buy_fee=args.buy_fee,
        sell_fee=args.sell_fee,
        limit_range=(args.limit_min, args.limit_max),
        step=args.limit_step,
        min_trades=args.min_trades
    )