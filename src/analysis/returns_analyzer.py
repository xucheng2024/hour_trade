#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Returns Analysis for Cryptocurrencies
Analyze daily and hourly returns for all cryptocurrencies in the list using strategy optimizer
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
import numpy as np

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.strategies.strategy_optimizer import get_strategy_optimizer
from src.data.data_manager import load_crypto_list

def analyze_daily_returns() -> Dict[str, Any]:
    """
    Analyze daily returns for all cryptocurrencies using all available historical data
    
    Returns:
        Dictionary with analysis results
    """
    
    print(f"📊 Analyzing daily returns using all available historical data")
    
    # Load cryptocurrency list
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found in the list")
        return {}
    
    print(f"🔍 Found {len(cryptos)} cryptocurrencies to analyze")
    
    # Initialize strategy optimizer with relaxed constraints
    class RelaxedStrategyOptimizer:
        def __init__(self, buy_fee=0.001, sell_fee=0.001):
            from strategies.strategy_optimizer import StrategyOptimizer
            self.base_optimizer = StrategyOptimizer(buy_fee, sell_fee)
            
        def optimize_1d_strategy(self, instId, start, end, date_dict, bar):
            # Override the config with relaxed parameters
            original_method = self.base_optimizer._get_strategy_config
            
            def relaxed_config(strategy_type):
                if strategy_type == "1d":
                    return {
                        'limit_range': (60, 95),
                        'duration_range': 30,
                        'min_trades': 10,        # Minimum successful trades required
                        'min_avg_earn': 1.005,   # Minimum average return: 0.5%
                        'data_offset': 20,       # Skip first 20 data points
                        'time_window': 48,       # 48 hours time window
                        'hour_mask': None,       # Any hour
                        'minute_mask': 0,
                        'second_mask': 0,
                        'buy_fee': 0.001,
                        'sell_fee': 0.001
                    }
                return original_method(strategy_type)
            
            self.base_optimizer._get_strategy_config = relaxed_config
            result = self.base_optimizer.optimize_1d_strategy(instId, start, end, date_dict, bar)
            self.base_optimizer._get_strategy_config = original_method
            return result
    
    optimizer = RelaxedStrategyOptimizer()
    
    # Results storage
    results = {
        'analysis_period': {
            'description': 'All available historical data',
            'timestamp': datetime.now().isoformat()
        },
        'cryptocurrencies': {},
        'summary': {
            'total_analyzed': 0,
            'successful_analysis': 0,
            'failed_analysis': 0,
            'best_performers': [],
            'worst_performers': []
        }
    }
    
    # Analyze each cryptocurrency
    for i, crypto in enumerate(cryptos, 1):
        print(f"\n📈 Analyzing {i}/{len(cryptos)}: {crypto}")
        
        try:
            # Analyze with 1-day strategy using all available data
            # Set start and end to 0 to use all data
            date_dict = {}
            result = optimizer.optimize_1d_strategy(
                instId=crypto,
                start=0,  # Start from beginning
                end=0,    # End at latest data
                date_dict=date_dict,
                bar='1d'
            )
            
            if result and crypto in result:
                crypto_result = result[crypto]
                results['cryptocurrencies'][crypto] = {
                    'best_limit': crypto_result.get('best_limit', 'N/A'),
                    'best_duration': crypto_result.get('best_duration', 'N/A'),
                    'max_returns': crypto_result.get('max_returns', 'N/A'),
                    'status': 'success'
                }
                results['summary']['successful_analysis'] += 1
                print(f"  ✅ Success: Limit={crypto_result.get('best_limit')}%, "
                      f"Duration={crypto_result.get('best_duration')}, "
                      f"Returns={crypto_result.get('max_returns')}")
            else:
                results['cryptocurrencies'][crypto] = {
                    'status': 'no_data',
                    'error': 'Insufficient data or no valid trades found'
                }
                results['summary']['failed_analysis'] += 1
                print(f"  ⚠️  No data or insufficient trades")
                
        except Exception as e:
            results['cryptocurrencies'][crypto] = {
                'status': 'error',
                'error': str(e)
            }
            results['summary']['failed_analysis'] += 1
            print(f"  ❌ Error: {e}")
        
        results['summary']['total_analyzed'] += 1
    
    # Generate summary statistics
    _generate_summary_statistics(results)
    
    # Save results
    _save_results(results)
    
    return results

def _generate_summary_statistics(results: Dict[str, Any]) -> None:
    """Generate summary statistics from analysis results"""
    
    successful_cryptos = []
    for crypto, data in results['cryptocurrencies'].items():
        if data['status'] == 'success':
            try:
                returns = float(data['max_returns'])
                successful_cryptos.append((crypto, returns))
            except (ValueError, TypeError):
                continue
    
    if successful_cryptos:
        # Sort by returns (descending)
        successful_cryptos.sort(key=lambda x: x[1], reverse=True)
        
        # Top performers
        results['summary']['best_performers'] = [
            {'crypto': crypto, 'returns': returns} 
            for crypto, returns in successful_cryptos[:10]
        ]
        
        # Worst performers
        results['summary']['worst_performers'] = [
            {'crypto': crypto, 'returns': returns} 
            for crypto, returns in successful_cryptos[-10:]
        ]
        
        # Calculate geometric mean returns for compound growth effects
        returns_array = np.array([returns for _, returns in successful_cryptos])
        geometric_mean_returns = np.power(np.prod(returns_array), 1/len(returns_array))
        results['summary']['geometric_mean_returns'] = float(geometric_mean_returns)
        results['summary']['arithmetic_mean_returns'] = float(np.mean(returns_array))
        
        print(f"\n📊 Summary Statistics:")
        print(f"  Total analyzed: {results['summary']['total_analyzed']}")
        print(f"  Successful: {results['summary']['successful_analysis']}")
        print(f"  Failed: {results['summary']['failed_analysis']}")
        print(f"  Geometric mean returns: {geometric_mean_returns:.4f}")
        print(f"  Arithmetic mean returns: {np.mean(returns_array):.4f}")
        
        print(f"\n🏆 Top 5 Performers:")
        for i, performer in enumerate(results['summary']['best_performers'][:5], 1):
            print(f"  {i}. {performer['crypto']}: {performer['returns']:.4f}")
        
        print(f"\n📉 Bottom 5 Performers:")
        for i, performer in enumerate(results['summary']['worst_performers'][-5:], 1):
            print(f"  {i}. {performer['crypto']}: {performer['returns']:.4f}")

def _save_results(results: Dict[str, Any]) -> None:
    """Save analysis results to file"""
    
    # Create data directory if it doesn't exist
    data_dir = 'data'
    os.makedirs(data_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"daily_returns_analysis_{timestamp}.json"
    filepath = os.path.join(data_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n💾 Results saved to: {filepath}")
    except Exception as e:
        print(f"\n❌ Error saving results: {e}")

def analyze_hourly_returns() -> Dict[str, Any]:
    """
    Analyze hourly returns for all cryptocurrencies using all available historical data
    
    Returns:
        Dictionary with analysis results
    """
    
    print(f"📊 Analyzing hourly returns using all available historical data")
    
    # Load cryptocurrency list
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found in the list")
        return {}
    
    print(f"🔍 Found {len(cryptos)} cryptocurrencies to analyze")
    
    # Initialize strategy optimizer with relaxed constraints (same as daily)
    class RelaxedStrategyOptimizer:
        def __init__(self, buy_fee=0.001, sell_fee=0.001):
            from strategies.strategy_optimizer import StrategyOptimizer
            self.base_optimizer = StrategyOptimizer(buy_fee, sell_fee)
            
        def optimize_1h_strategy(self, instId, start, end, date_dict, bar):
            # Override the config with relaxed parameters for hourly
            original_method = self.base_optimizer._get_strategy_config
            
            def relaxed_config(strategy_type):
                if strategy_type == "1h":
                    return {
                        'limit_range': (50, 99),  # Extended range for more opportunities
                        'duration_range': 720,      # Extended to 720 hours (30*24) to match daily strategy's 30 days
                        'min_trades': 10,          # Reduced to 10 for more strategy opportunities
                        'min_avg_earn': 1.002,    # Reduced to 0.2% for more opportunities
                        'data_offset': 50,         # Further reduced for maximum data points
                        'time_window': 168,        # Extended to 168 hours (1 week) to capture weekly patterns
                        'hour_mask': None,         # Any hour
                        'minute_mask': None,       # Any minute
                        'second_mask': None,       # Any second
                        'buy_fee': 0.001,
                        'sell_fee': 0.001
                    }
                return original_method(strategy_type)
            
            self.base_optimizer._get_strategy_config = relaxed_config
            result = self.base_optimizer.optimize_1h_strategy(instId, start, end, date_dict, bar)
            self.base_optimizer._get_strategy_config = original_method
            return result
    
    optimizer = RelaxedStrategyOptimizer()
    
    # Results storage
    results = {
        'analysis_period': {
            'description': 'Hourly analysis - all available historical data',
            'timestamp': datetime.now().isoformat(),
            'timeframe': '1H'
        },
        'cryptocurrencies': {},
        'summary': {
            'total_analyzed': 0,
            'successful_analysis': 0,
            'failed_analysis': 0,
            'best_performers': [],
            'worst_performers': []
        }
    }
    
    # Analyze each cryptocurrency
    for i, crypto in enumerate(cryptos, 1):
        print(f"\n📈 Analyzing {i}/{len(cryptos)}: {crypto}")
        
        try:
            # Analyze with 1-hour strategy using all available data
            result = optimizer.optimize_1h_strategy(
                instId=crypto,
                start=0,  # Start from beginning
                end=0,    # End at latest data
                date_dict={},
                bar='1H'
            )
            
            if result and crypto in result:
                crypto_result = result[crypto]
                results['cryptocurrencies'][crypto] = {
                    'status': 'success',
                    'best_limit': crypto_result.get('best_limit', 'N/A'),
                    'best_duration': crypto_result.get('best_duration', 'N/A'),
                    'max_returns': crypto_result.get('max_returns', 0)
                }
                results['summary']['successful_analysis'] += 1
                max_returns = crypto_result.get('max_returns', 0)
                if isinstance(max_returns, (int, float)):
                    returns_str = f"{max_returns:.4f}"
                else:
                    returns_str = str(max_returns)
                print(f"  ✅ Success: Limit={crypto_result.get('best_limit', 'N/A')}%, "
                      f"Duration={crypto_result.get('best_duration', 'N/A')}, "
                      f"Returns={returns_str}")
            else:
                results['cryptocurrencies'][crypto] = {
                    'status': 'no_valid_params',
                    'error': 'No valid parameters found'
                }
                results['summary']['failed_analysis'] += 1
                print(f"  ⚠️  No valid parameters found")
                
        except Exception as e:
            results['cryptocurrencies'][crypto] = {
                'status': 'error',
                'error': str(e)
            }
            results['summary']['failed_analysis'] += 1
            print(f"  ❌ Error: {e}")
        
        results['summary']['total_analyzed'] += 1
    
    # Generate summary statistics
    _generate_summary_statistics(results)
    
    # Save results
    _save_hourly_results(results)
    
    return results

def _save_hourly_results(results: Dict[str, Any]) -> None:
    """Save hourly analysis results to file"""
    
    # Create data directory if it doesn't exist
    data_dir = 'data'
    os.makedirs(data_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"hourly_returns_analysis_{timestamp}.json"
    filepath = os.path.join(data_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n💾 Results saved to: {filepath}")
    except Exception as e:
        print(f"\n❌ Error saving results: {e}")

def main():
    """Main function"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'hourly':
        print("🚀 Starting Hourly Returns Analysis")
        print("=" * 50)
        results = analyze_hourly_returns()
        print("\n" + "=" * 50)
        print("✅ Hourly Returns Analysis Completed!")
    else:
        print("🚀 Starting Daily Returns Analysis")
        print("=" * 50)
        results = analyze_daily_returns()
        print("\n" + "=" * 50)
        print("✅ Daily Returns Analysis Completed!")
    
    return results

if __name__ == "__main__":
    main()
