#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vectorized Profit Optimizer
Find optimal p (high/open ratio) and v (volume ratio) parameters for all cryptocurrencies
Requirements: Maximum compound return AND median return > 1.01
"""

import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.data.data_manager import load_crypto_list
from src.strategies.historical_data_loader import get_historical_data_loader

warnings.filterwarnings("ignore", category=RuntimeWarning)

class VectorizedProfitOptimizer:
    """Vectorized optimizer for finding optimal p and v parameters"""
    
    def __init__(self):
        self.data_loader = get_historical_data_loader()
        self.buy_fee = 0.001
        self.sell_fee = 0.001
        
    def optimize_all_cryptos(self, cryptos: List[str] = None, 
                           p_range: Tuple[float, float] = (0.01, 0.10),
                           v_range: Tuple[float, float] = (1.1, 3.0),
                           p_step: float = 0.005,
                           v_step: float = 0.1,
                           min_median_return: float = 1.01) -> Dict[str, Any]:
        """
        Optimize parameters for all cryptocurrencies using vectorized operations
        
        Args:
            cryptos: List of cryptocurrencies to optimize
            p_range: Range for high/open ratio (min, max)
            v_range: Range for volume ratio (min, max)
            p_step: Step size for p parameter
            v_step: Step size for v parameter
            min_median_return: Minimum median return requirement
        """
        if cryptos is None:
            cryptos = load_crypto_list()
        
        print(f"🚀 Starting vectorized optimization for {len(cryptos)} cryptocurrencies")
        print(f"📊 Parameter ranges: p={p_range}, v={v_range}")
        print(f"📊 Step sizes: p={p_step}, v={v_step}")
        print(f"📊 Min median return: {min_median_return}")
        
        # Generate parameter combinations
        p_values = np.arange(p_range[0], p_range[1] + p_step, p_step)
        v_values = np.arange(v_range[0], v_range[1] + v_step, v_step)
        
        print(f"📊 Testing {len(p_values)} p values × {len(v_values)} v values = {len(p_values) * len(v_values)} combinations")
        
        results = {
            'optimization_info': {
                'total_cryptos': len(cryptos),
                'p_range': p_range,
                'v_range': v_range,
                'p_step': p_step,
                'v_step': v_step,
                'p_values': p_values.tolist(),
                'v_values': v_values.tolist(),
                'min_median_return': min_median_return,
                'analysis_date': datetime.now().isoformat()
            },
            'crypto_results': {},
            'optimal_parameters': {},
            'summary': {}
        }
        
        successful_optimizations = 0
        
        # Process each cryptocurrency
        for i, crypto in enumerate(cryptos, 1):
            print(f"\n📈 Optimizing {i}/{len(cryptos)}: {crypto}")
            
            try:
                crypto_result = self._optimize_single_crypto(
                    crypto, p_values, v_values, min_median_return
                )
                if crypto_result:
                    results['crypto_results'][crypto] = crypto_result
                    successful_optimizations += 1
                    
                    # Store optimal parameters
                    if crypto_result['optimal_params']:
                        results['optimal_parameters'][crypto] = {
                            'p': crypto_result['optimal_params']['p'],
                            'v': crypto_result['optimal_params']['v'],
                            'compound_return': crypto_result['optimal_params']['compound_return'],
                            'median_return': crypto_result['optimal_params']['median_return'],
                            'total_trades': crypto_result['optimal_params']['total_trades'],
                            'win_rate': crypto_result['optimal_params']['win_rate']
                        }
                        
                        optimal = crypto_result['optimal_params']
                        p_range = optimal.get('parameter_ranges', {}).get('p_range', {})
                        v_range = optimal.get('parameter_ranges', {}).get('v_range', {})
                        
                        print(f"  ✅ Optimal: p={optimal['p']:.1%}, v={optimal['v']:.1f}x, "
                              f"compound={optimal['compound_return']:.2f}, median={optimal['median_return']:.3f}")
                        
                        if p_range and v_range:
                            print(f"      📊 P range: {p_range.get('min', 0):.1%} - {p_range.get('max', 0):.1%} "
                                  f"({p_range.get('count', 0)} values), "
                                  f"V range: {v_range.get('min', 0):.1f}x - {v_range.get('max', 0):.1f}x "
                                  f"({v_range.get('count', 0)} values)")
                            print(f"      📊 Near-optimal combinations: {optimal.get('near_optimal_combinations', 0)}")
                    else:
                        print(f"  ⚠️  No valid parameters found")
                        
            except Exception as e:
                print(f"  ❌ Error optimizing {crypto}: {e}")
                results['crypto_results'][crypto] = {'error': str(e)}
        
        # Generate summary
        results['summary'] = self._generate_optimization_summary(results['optimal_parameters'])
        results['optimization_info']['successful_optimizations'] = successful_optimizations
        
        print(f"\n✅ Optimization completed: {successful_optimizations}/{len(cryptos)} cryptocurrencies optimized successfully")
        
        return results
    
    def _optimize_single_crypto(self, crypto: str, p_values: np.ndarray, 
                               v_values: np.ndarray, min_median_return: float) -> Dict[str, Any]:
        """Optimize parameters for a single cryptocurrency using vectorized operations"""
        
        # Load data
        data = self.data_loader.get_dataframe_with_dates(crypto, 0, 0, "1D")
        if data is None or len(data) == 0:
            return None
        
        # Preprocess data
        data = self._preprocess_data(data)
        if len(data) == 0:
            return None
        
        # Vectorized optimization
        results_matrix = self._vectorized_optimization(data, p_values, v_values, min_median_return)
        
        # Find optimal parameters
        optimal_params = self._find_optimal_params(results_matrix, p_values, v_values)
        
        return {
            'crypto': crypto,
            'total_days': len(data),
            'p_values': p_values.tolist(),
            'v_values': v_values.tolist(),
            'results_matrix': results_matrix.tolist(),
            'optimal_params': optimal_params,
            'analysis_date': datetime.now().isoformat()
        }
    
    def _preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Preprocess data for vectorized operations"""
        # Calculate metrics
        data['high_open_ratio'] = (data['high'] - data['open']) / data['open']
        data['volume_ratio'] = data['volume'] / data['volume'].shift(1)
        data['volume_ratio'] = data['volume_ratio'].fillna(1.0)
        
        # Calculate buy/sell prices with fees
        data['buy_price'] = data['open'] * (1 + self.buy_fee)
        data['sell_price'] = data['close'] * (1 - self.sell_fee)
        data['profit_ratio'] = data['sell_price'] / data['buy_price']
        
        # Remove invalid data
        data = data.dropna()
        data = data[data['volume_ratio'] > 0]
        
        return data
    
    def _vectorized_optimization(self, data: pd.DataFrame, p_values: np.ndarray, 
                                v_values: np.ndarray, min_median_return: float) -> np.ndarray:
        """Perform vectorized optimization for all parameter combinations"""
        
        n_p = len(p_values)
        n_v = len(v_values)
        
        # Initialize results matrix: [p_idx, v_idx, compound_return, median_return, total_trades, win_rate]
        results = np.zeros((n_p, n_v, 6))
        
        # Vectorized operations for each parameter combination
        for i, p in enumerate(p_values):
            for j, v in enumerate(v_values):
                # Find trades that meet criteria
                mask = (data['high_open_ratio'] >= p) & (data['volume_ratio'] >= v)
                
                if mask.sum() == 0:
                    # No trades found
                    results[i, j] = [0, 0, 0, 0, 0, 0]
                    continue
                
                # Get profit ratios for valid trades
                profit_ratios = data.loc[mask, 'profit_ratio'].values
                
                # Calculate metrics
                total_trades = len(profit_ratios)
                compound_return = np.prod(profit_ratios)
                median_return = np.median(profit_ratios)
                win_rate = np.mean(profit_ratios > 1.0) * 100
                
                # Check if meets minimum median return requirement
                if median_return >= min_median_return:
                    results[i, j] = [compound_return, median_return, total_trades, win_rate, p, v]
                else:
                    # Doesn't meet minimum requirement
                    results[i, j] = [0, 0, total_trades, win_rate, p, v]
        
        return results
    
    def _find_optimal_params(self, results_matrix: np.ndarray, p_values: np.ndarray, 
                            v_values: np.ndarray) -> Optional[Dict[str, Any]]:
        """Find optimal parameters and parameter ranges from results matrix"""
        
        # Get compound returns (first column)
        compound_returns = results_matrix[:, :, 0]
        
        # Find maximum compound return
        max_compound = np.max(compound_returns)
        
        if max_compound <= 0:
            return None
        
        # Find all positions with maximum compound return (within 1% tolerance)
        tolerance = 0.01  # 1% tolerance for "near optimal"
        near_optimal_mask = compound_returns >= max_compound * (1 - tolerance)
        near_optimal_positions = np.where(near_optimal_mask)
        
        if len(near_optimal_positions[0]) == 0:
            return None
        
        # Extract all near-optimal parameter combinations
        p_indices = near_optimal_positions[0]
        v_indices = near_optimal_positions[1]
        
        # Get parameter ranges
        p_range = [float(p_values[p_idx]) for p_idx in p_indices]
        v_range = [float(v_values[v_idx]) for v_idx in v_indices]
        
        # Find the "best" single parameter combination (highest median return among optimal)
        best_idx = 0
        best_median = 0
        for i, (p_idx, v_idx) in enumerate(zip(p_indices, v_indices)):
            median_return = results_matrix[p_idx, v_idx, 1]
            if median_return > best_median:
                best_median = median_return
                best_idx = i
        
        best_p_idx = p_indices[best_idx]
        best_v_idx = v_indices[best_idx]
        best_result = results_matrix[best_p_idx, best_v_idx]
        
        return {
            'p': float(best_result[4]),
            'v': float(best_result[5]),
            'compound_return': float(best_result[0]),
            'median_return': float(best_result[1]),
            'total_trades': int(best_result[2]),
            'win_rate': float(best_result[3]),
            'parameter_ranges': {
                'p_range': {
                    'min': float(min(p_range)),
                    'max': float(max(p_range)),
                    'values': sorted(list(set(p_range))),
                    'count': len(set(p_range))
                },
                'v_range': {
                    'min': float(min(v_range)),
                    'max': float(max(v_range)),
                    'values': sorted(list(set(v_range))),
                    'count': len(set(v_range))
                }
            },
            'near_optimal_combinations': len(p_indices),
            'tolerance_used': tolerance
        }
    
    def _generate_optimization_summary(self, optimal_parameters: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics from optimization results"""
        
        if not optimal_parameters:
            return {'error': 'No optimal parameters found'}
        
        # Extract all optimal parameters and their ranges
        p_values = [params['p'] for params in optimal_parameters.values()]
        v_values = [params['v'] for params in optimal_parameters.values()]
        compound_returns = [params['compound_return'] for params in optimal_parameters.values()]
        median_returns = [params['median_return'] for params in optimal_parameters.values()]
        total_trades = [params['total_trades'] for params in optimal_parameters.values()]
        win_rates = [params['win_rate'] for params in optimal_parameters.values()]
        
        # Extract parameter ranges
        p_ranges = [params.get('parameter_ranges', {}).get('p_range', {}) for params in optimal_parameters.values()]
        v_ranges = [params.get('parameter_ranges', {}).get('v_range', {}) for params in optimal_parameters.values()]
        
        # Calculate range statistics
        p_min_values = [r.get('min', params['p']) for r, params in zip(p_ranges, optimal_parameters.values())]
        p_max_values = [r.get('max', params['p']) for r, params in zip(p_ranges, optimal_parameters.values())]
        v_min_values = [r.get('min', params['v']) for r, params in zip(v_ranges, optimal_parameters.values())]
        v_max_values = [r.get('max', params['v']) for r, params in zip(v_ranges, optimal_parameters.values())]
        
        # Calculate statistics
        summary = {
            'total_cryptos_optimized': len(optimal_parameters),
            'parameter_statistics': {
                'p_values': {
                    'mean': float(np.mean(p_values)),
                    'std': float(np.std(p_values)),
                    'min': float(np.min(p_values)),
                    'max': float(np.max(p_values)),
                    'median': float(np.median(p_values))
                },
                'v_values': {
                    'mean': float(np.mean(v_values)),
                    'std': float(np.std(v_values)),
                    'min': float(np.min(v_values)),
                    'max': float(np.max(v_values)),
                    'median': float(np.median(v_values))
                },
                'p_ranges': {
                    'min_values': {
                        'mean': float(np.mean(p_min_values)),
                        'std': float(np.std(p_min_values)),
                        'min': float(np.min(p_min_values)),
                        'max': float(np.max(p_min_values)),
                        'median': float(np.median(p_min_values))
                    },
                    'max_values': {
                        'mean': float(np.mean(p_max_values)),
                        'std': float(np.std(p_max_values)),
                        'min': float(np.min(p_max_values)),
                        'max': float(np.max(p_max_values)),
                        'median': float(np.median(p_max_values))
                    }
                },
                'v_ranges': {
                    'min_values': {
                        'mean': float(np.mean(v_min_values)),
                        'std': float(np.std(v_min_values)),
                        'min': float(np.min(v_min_values)),
                        'max': float(np.max(v_min_values)),
                        'median': float(np.median(v_min_values))
                    },
                    'max_values': {
                        'mean': float(np.mean(v_max_values)),
                        'std': float(np.std(v_max_values)),
                        'min': float(np.min(v_max_values)),
                        'max': float(np.max(v_max_values)),
                        'median': float(np.median(v_max_values))
                    }
                }
            },
            'performance_statistics': {
                'compound_returns': {
                    'mean': float(np.mean(compound_returns)),
                    'std': float(np.std(compound_returns)),
                    'min': float(np.min(compound_returns)),
                    'max': float(np.max(compound_returns)),
                    'median': float(np.median(compound_returns))
                },
                'median_returns': {
                    'mean': float(np.mean(median_returns)),
                    'std': float(np.std(median_returns)),
                    'min': float(np.min(median_returns)),
                    'max': float(np.max(median_returns))
                },
                'total_trades': {
                    'mean': float(np.mean(total_trades)),
                    'std': float(np.std(total_trades)),
                    'min': int(np.min(total_trades)),
                    'max': int(np.max(total_trades)),
                    'median': float(np.median(total_trades))
                },
                'win_rates': {
                    'mean': float(np.mean(win_rates)),
                    'std': float(np.std(win_rates)),
                    'min': float(np.min(win_rates)),
                    'max': float(np.max(win_rates)),
                    'median': float(np.median(win_rates))
                }
            },
            'top_performers': self._get_top_performers(optimal_parameters)
        }
        
        return summary
    
    def _get_top_performers(self, optimal_parameters: Dict[str, Dict[str, Any]], 
                           top_n: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Get top performing cryptocurrencies by different metrics"""
        
        # Sort by compound return
        sorted_by_compound = sorted(
            optimal_parameters.items(), 
            key=lambda x: x[1]['compound_return'], 
            reverse=True
        )[:top_n]
        
        # Sort by median return
        sorted_by_median = sorted(
            optimal_parameters.items(), 
            key=lambda x: x[1]['median_return'], 
            reverse=True
        )[:top_n]
        
        # Sort by total trades
        sorted_by_trades = sorted(
            optimal_parameters.items(), 
            key=lambda x: x[1]['total_trades'], 
            reverse=True
        )[:top_n]
        
        return {
            'by_compound_return': [
                {'crypto': crypto, **params} for crypto, params in sorted_by_compound
            ],
            'by_median_return': [
                {'crypto': crypto, **params} for crypto, params in sorted_by_median
            ],
            'by_total_trades': [
                {'crypto': crypto, **params} for crypto, params in sorted_by_trades
            ]
        }
    
    def save_results(self, results: Dict[str, Any], filename: str = None) -> str:
        """Save optimization results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"vectorized_optimization_{timestamp}.json"
        
        filepath = os.path.join('data', filename)
        os.makedirs('data', exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"💾 Results saved to: {filepath}")
        return filepath

def main():
    """Main function"""
    print("🚀 Starting Vectorized Profit Optimization")
    print("=" * 60)
    
    # Initialize optimizer
    optimizer = VectorizedProfitOptimizer()
    
    # Load crypto list
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found in the list")
        return
    
    # For demonstration, use first 20 cryptos (you can change this)
    test_cryptos = cryptos[:20]
    print(f"🧪 Optimizing first {len(test_cryptos)} cryptocurrencies")
    
    # Define optimization parameters
    p_range = (0.01, 0.08)  # 1% to 8% high/open ratio
    v_range = (1.1, 1.1)    # Fixed at 1.1x volume ratio (simplified)
    p_step = 0.01           # 1% steps for p
    v_step = 0.1            # 0.1 steps for v
    min_median_return = 1.01  # Minimum 1% median return
    
    # Run optimization
    results = optimizer.optimize_all_cryptos(
        cryptos=test_cryptos,
        p_range=p_range,
        v_range=v_range,
        p_step=p_step,
        v_step=v_step,
        min_median_return=min_median_return
    )
    
    # Save results
    filepath = optimizer.save_results(results)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 OPTIMIZATION SUMMARY")
    print("=" * 60)
    
    summary = results['summary']
    if 'error' in summary:
        print(f"❌ {summary['error']}")
        return
    
    print(f"✅ Successfully optimized: {summary['total_cryptos_optimized']} cryptocurrencies")
    
    # Parameter statistics
    p_stats = summary['parameter_statistics']['p_values']
    v_stats = summary['parameter_statistics']['v_values']
    p_range_stats = summary['parameter_statistics']['p_ranges']
    v_range_stats = summary['parameter_statistics']['v_ranges']
    
    print(f"\n📊 Optimal Parameter Statistics:")
    print(f"  P (High/Open ratio): {p_stats['mean']:.1%} ± {p_stats['std']:.1%} (range: {p_stats['min']:.1%} - {p_stats['max']:.1%})")
    print(f"  V (Volume ratio): {v_stats['mean']:.1f} ± {v_stats['std']:.1f} (range: {v_stats['min']:.1f} - {v_stats['max']:.1f})")
    
    print(f"\n📊 Parameter Range Statistics:")
    print(f"  P Range (Min): {p_range_stats['min_values']['mean']:.1%} ± {p_range_stats['min_values']['std']:.1%} (range: {p_range_stats['min_values']['min']:.1%} - {p_range_stats['min_values']['max']:.1%})")
    print(f"  P Range (Max): {p_range_stats['max_values']['mean']:.1%} ± {p_range_stats['max_values']['std']:.1%} (range: {p_range_stats['max_values']['min']:.1%} - {p_range_stats['max_values']['max']:.1%})")
    print(f"  V Range (Min): {v_range_stats['min_values']['mean']:.1f} ± {v_range_stats['min_values']['std']:.1f} (range: {v_range_stats['min_values']['min']:.1f} - {v_range_stats['min_values']['max']:.1f})")
    print(f"  V Range (Max): {v_range_stats['max_values']['mean']:.1f} ± {v_range_stats['max_values']['std']:.1f} (range: {v_range_stats['max_values']['min']:.1f} - {v_range_stats['max_values']['max']:.1f})")
    
    # Performance statistics
    perf_stats = summary['performance_statistics']
    compound_stats = perf_stats['compound_returns']
    median_stats = perf_stats['median_returns']
    trade_stats = perf_stats['total_trades']
    win_stats = perf_stats['win_rates']
    
    print(f"\n📈 Performance Statistics:")
    print(f"  Compound Returns: {compound_stats['mean']:.2f} ± {compound_stats['std']:.2f} (range: {compound_stats['min']:.2f} - {compound_stats['max']:.2f})")
    print(f"  Median Returns: {median_stats['mean']:.3f} ± {median_stats['std']:.3f} (range: {median_stats['min']:.3f} - {median_stats['max']:.3f})")
    print(f"  Total Trades: {trade_stats['mean']:.0f} ± {trade_stats['std']:.0f} (range: {trade_stats['min']} - {trade_stats['max']})")
    print(f"  Win Rates: {win_stats['mean']:.1f}% ± {win_stats['std']:.1f}% (range: {win_stats['min']:.1f}% - {win_stats['max']:.1f}%)")
    
    # Top performers
    top_performers = summary['top_performers']
    
    print(f"\n🏆 Top 5 Performers by Compound Return:")
    for i, performer in enumerate(top_performers['by_compound_return'][:5], 1):
        print(f"  {i}. {performer['crypto']}: p={performer['p']:.1%}, v={performer['v']:.1f}x, "
              f"compound={performer['compound_return']:.2f}, median={performer['median_return']:.3f}")
    
    print(f"\n📄 Detailed results saved to: {filepath}")
    print("✅ Vectorized optimization completed!")

if __name__ == "__main__":
    main()
