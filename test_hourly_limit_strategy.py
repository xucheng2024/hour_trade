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

def analyze_trades(trades: List[Dict]) -> Dict:
    """Analyze trades and calculate statistics"""
    if len(trades) == 0:
        return {}
    
    return_rates = np.array([t['return_rate'] for t in trades])
    return_multipliers = np.array([t['return_multiplier'] for t in trades])
    
    total_return = np.prod(return_multipliers)
    avg_return = np.mean(return_rates)
    median_return = np.median(return_rates)
    std_return = np.std(return_rates)
    
    profitable_trades = np.sum(return_rates > 0)
    losing_trades = np.sum(return_rates <= 0)
    win_rate = profitable_trades / len(trades) * 100
    
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
        'return_rates': return_rates,
        'return_multipliers': return_multipliers
    }

def test_hourly_limit_strategy(instId: str, limit_percent: float = 99.0, 
                               buy_fee: float = 0.001, sell_fee: float = 0.001,
                               start_idx: int = 0, end_idx: int = 0) -> Dict:
    """
    Test hourly limit strategy: Buy at limit price, sell at next hour's close
    
    Args:
        instId: Instrument ID (e.g., 'BTC-USDT')
        limit_percent: Limit price as percentage of open price (e.g., 99.0 means 99% of open)
        buy_fee: Buy fee rate (0.001 = 0.1%)
        sell_fee: Sell fee rate (0.001 = 0.1%)
        start_hour: Start hour offset (0 = all data)
        end_hour: End hour offset (0 = all data)
    
    Returns:
        Dictionary with strategy results
    """
    data_loader = get_historical_data_loader()
    
    # Load hourly data
    print(f"\n{'='*70}")
    print(f"Testing Hourly Limit Strategy for {instId}")
    print(f"{'='*70}")
    print(f"Limit Price: {limit_percent}% of open price")
    print(f"Buy Fee: {buy_fee*100:.3f}%, Sell Fee: {sell_fee*100:.3f}%")
    print(f"{'='*70}\n")
    
    # Load all hourly data
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
    
    # Determine data range
    n = len(close_prices)
    start_idx = start_hour if start_hour > 0 else 0
    end_idx = end_hour if end_hour > 0 else n - 1
    
    # We need at least 2 hours (buy hour + sell hour)
    if end_idx - start_idx < 2:
        print(f"❌ Not enough data: need at least 2 hours, got {end_idx - start_idx}")
        return {}
    
    # Limit to valid range
    end_idx = min(end_idx, n - 2)  # Leave room for next hour
    
    print(f"📊 Analyzing hours {start_idx} to {end_idx} (total: {end_idx - start_idx + 1} hours)\n")
    
    # Track trades
    trades = []
    total_return = 1.0
    profitable_trades = 0
    losing_trades = 0
    
    # For each hour, try to buy at limit price, sell at next hour's close
    for i in range(start_idx, end_idx):
        # Calculate limit buy price (as percentage of open)
        limit_buy_price = open_prices[i] * (limit_percent / 100.0)
        
        # Check if we can buy (low price <= limit price)
        if low_prices[i] > limit_buy_price:
            # Cannot buy - price didn't drop to limit
            continue
        
        # We can buy at limit price
        buy_price = limit_buy_price
        buy_time = datetime.fromtimestamp(timestamps[i] / 1000)
        
        # Sell at next hour's close
        sell_price = close_prices[i + 1]
        sell_time = datetime.fromtimestamp(timestamps[i + 1] / 1000)
        
        # Calculate return with fees
        # Buy: we pay buy_price * (1 + buy_fee)
        # Sell: we receive sell_price * (1 - sell_fee)
        effective_buy_price = buy_price * (1 + buy_fee)
        effective_sell_price = sell_price * (1 - sell_fee)
        
        # Return rate
        return_rate = (effective_sell_price / effective_buy_price) - 1.0
        return_multiplier = effective_sell_price / effective_buy_price
        
        # Track trade
        trade = {
            'buy_time': buy_time,
            'sell_time': sell_time,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'effective_buy': effective_buy_price,
            'effective_sell': effective_sell_price,
            'return_rate': return_rate,
            'return_multiplier': return_multiplier
        }
        trades.append(trade)
        
        # Update total return (compound)
        total_return *= return_multiplier
        
        if return_rate > 0:
            profitable_trades += 1
        else:
            losing_trades += 1
    
    # Calculate statistics
    if len(trades) == 0:
        print(f"❌ No trades executed with limit price {limit_percent}%")
        return {}
    
    return_rates = [t['return_rate'] for t in trades]
    return_multipliers = [t['return_multiplier'] for t in trades]
    
    avg_return = np.mean(return_rates)
    median_return = np.median(return_rates)
    total_return_rate = (total_return - 1.0) * 100
    win_rate = profitable_trades / len(trades) * 100
    
    # Calculate annualized return (assuming 24 trades per day)
    hours_tested = end_idx - start_idx + 1
    days_tested = hours_tested / 24.0
    annualized_return = ((total_return ** (365.0 / days_tested)) - 1.0) * 100 if days_tested > 0 else 0
    
    # Print results
    print(f"{'='*70}")
    print(f"STRATEGY RESULTS")
    print(f"{'='*70}")
    print(f"Total Trades: {len(trades)}")
    print(f"Profitable Trades: {profitable_trades} ({win_rate:.2f}%)")
    print(f"Losing Trades: {losing_trades} ({100-win_rate:.2f}%)")
    print(f"\nReturn Statistics:")
    print(f"  Average Return per Trade: {avg_return*100:.3f}%")
    print(f"  Median Return per Trade: {median_return*100:.3f}%")
    print(f"  Total Compound Return: {total_return_rate:.2f}%")
    print(f"  Total Return Multiplier: {total_return:.4f}x")
    print(f"\nTime Period:")
    print(f"  Hours Tested: {hours_tested}")
    print(f"  Days Tested: {days_tested:.2f}")
    print(f"  Annualized Return: {annualized_return:.2f}%")
    print(f"\nFirst Trade: {trades[0]['buy_time']}")
    print(f"Last Trade: {trades[-1]['sell_time']}")
    print(f"{'='*70}\n")
    
    # Show sample trades
    print(f"Sample Trades (first 5):")
    print(f"{'='*70}")
    for i, trade in enumerate(trades[:5]):
        print(f"Trade {i+1}:")
        print(f"  Buy:  {trade['buy_time'].strftime('%Y-%m-%d %H:%M')} @ {trade['buy_price']:.4f} (limit: {limit_percent}%)")
        print(f"  Sell: {trade['sell_time'].strftime('%Y-%m-%d %H:%M')} @ {trade['sell_price']:.4f}")
        print(f"  Return: {trade['return_rate']*100:+.3f}% (multiplier: {trade['return_multiplier']:.4f}x)")
        print()
    
    return {
        'instId': instId,
        'limit_percent': limit_percent,
        'total_trades': len(trades),
        'profitable_trades': profitable_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'median_return': median_return,
        'total_return': total_return,
        'total_return_rate': total_return_rate,
        'annualized_return': annualized_return,
        'trades': trades
    }

def test_multiple_limits(instId: str, limit_percents: List[float] = [95.0, 97.0, 99.0, 99.5, 99.9]):
    """Test multiple limit percentages"""
    print(f"\n{'='*70}")
    print(f"Testing Multiple Limit Percentages for {instId}")
    print(f"{'='*70}\n")
    
    results = []
    for limit_pct in limit_percents:
        result = test_hourly_limit_strategy(instId, limit_percent=limit_pct)
        if result:
            results.append({
                'limit_percent': limit_pct,
                'total_trades': result['total_trades'],
                'win_rate': result['win_rate'],
                'total_return_rate': result['total_return_rate'],
                'total_return': result['total_return'],
                'annualized_return': result['annualized_return']
            })
    
    # Print comparison
    if results:
        print(f"\n{'='*70}")
        print(f"COMPARISON OF LIMIT PERCENTAGES")
        print(f"{'='*70}")
        print(f"{'Limit %':<10} {'Trades':<10} {'Win Rate':<12} {'Total Return':<15} {'Annualized':<12}")
        print(f"{'-'*70}")
        for r in results:
            print(f"{r['limit_percent']:>6.1f}%  {r['total_trades']:>8}  {r['win_rate']:>8.2f}%  {r['total_return_rate']:>11.2f}%  {r['annualized_return']:>10.2f}%")
        print(f"{'='*70}\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test hourly limit strategy')
    parser.add_argument('--symbol', type=str, default='BTC-USDT', help='Symbol to test (default: BTC-USDT)')
    parser.add_argument('--limit', type=float, default=99.0, help='Limit price percentage (default: 99.0)')
    parser.add_argument('--buy-fee', type=float, default=0.001, help='Buy fee rate (default: 0.001)')
    parser.add_argument('--sell-fee', type=float, default=0.001, help='Sell fee rate (default: 0.001)')
    parser.add_argument('--compare', action='store_true', help='Compare multiple limit percentages')
    
    args = parser.parse_args()
    
    if args.compare:
        test_multiple_limits(args.symbol)
    else:
        test_hourly_limit_strategy(
            args.symbol,
            limit_percent=args.limit,
            buy_fee=args.buy_fee,
            sell_fee=args.sell_fee
        )