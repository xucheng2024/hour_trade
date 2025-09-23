#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vectorized V-Pattern Parameter Optimizer
Vectorized V-shaped pattern parameter optimizer - high performance version
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

@dataclass
class OptimizedParams:
    """Optimized parameters"""
    symbol: str
    min_depth_pct: float
    max_depth_pct: float
    min_recovery_pct: float
    max_total_time: int
    max_recovery_time: int
    train_score: float
    test_score: float
    train_patterns: int
    test_patterns: int
    train_win_rate: float
    test_win_rate: float
    train_return: float
    test_return: float
    consistency_ratio: float

def find_local_peaks_and_troughs(prices: np.ndarray, window: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """
    Find local peaks and troughs
    
    Returns:
        (peak_indices, trough_indices)
    """
    # Use scipy signal.find_peaks
    try:
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(prices, distance=window)
        troughs, _ = find_peaks(-prices, distance=window)
    except ImportError:
        # If no scipy, use simple method
        peaks = []
        troughs = []
        
        for i in range(window, len(prices) - window):
            # Check local peaks
            if all(prices[i] >= prices[i-j] for j in range(1, window+1)) and \
               all(prices[i] >= prices[i+j] for j in range(1, window+1)):
                peaks.append(i)
            
            # Check local troughs
            if all(prices[i] <= prices[i-j] for j in range(1, window+1)) and \
               all(prices[i] <= prices[i+j] for j in range(1, window+1)):
                troughs.append(i)
        
        peaks = np.array(peaks)
        troughs = np.array(troughs)
    
    return peaks, troughs

def vectorized_pattern_detection(prices: np.ndarray, 
                                min_depth_pct: float,
                                max_depth_pct: float,
                                min_recovery_pct: float,
                                max_total_time: int,
                                max_recovery_time: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized V-shaped pattern detection
    
    Returns:
        (start_indices, bottom_indices, recovery_indices)
    """
    # Find local peaks and troughs
    peaks, troughs = find_local_peaks_and_troughs(prices)
    
    patterns_start = []
    patterns_bottom = []
    patterns_recovery = []
    
    # For each peak, find subsequent V-shaped patterns
    for peak_idx in peaks:
        if peak_idx >= len(prices) - max_total_time:
            continue
            
        start_price = prices[peak_idx]
        
        # Find troughs after this peak
        valid_troughs = troughs[(troughs > peak_idx) & 
                               (troughs <= peak_idx + max_total_time)]
        
        for trough_idx in valid_troughs:
            bottom_price = prices[trough_idx]
            depth_pct = (start_price - bottom_price) / start_price
            
            # Check if depth meets requirements
            if not (min_depth_pct <= depth_pct <= max_depth_pct):
                continue
            
            recovery_threshold = bottom_price + (start_price - bottom_price) * min_recovery_pct
            
            # Find recovery point
            recovery_end = min(trough_idx + max_recovery_time, len(prices))
            recovery_slice = prices[trough_idx+1:recovery_end]
            
            # Vectorized recovery check
            recovery_hits = recovery_slice >= recovery_threshold
            if recovery_hits.any():
                recovery_idx = trough_idx + 1 + np.argmax(recovery_hits)
                
                patterns_start.append(peak_idx)
                patterns_bottom.append(trough_idx)
                patterns_recovery.append(recovery_idx)
                break  # Stop after finding first recovery point
    
    return (np.array(patterns_start), np.array(patterns_bottom), np.array(patterns_recovery))

def vectorized_backtest(prices: np.ndarray,
                       entry_indices: np.ndarray,
                       holding_hours: int) -> np.ndarray:
    """
    Vectorized backtesting
    
    Returns:
        returns array
    """
    # Vectorized exit index calculation
    exit_indices = np.minimum(entry_indices + holding_hours, len(prices) - 1)
    
    # Vectorized return calculation
    entry_prices = prices[entry_indices]
    exit_prices = prices[exit_indices]
    
    returns = (exit_prices - entry_prices) / entry_prices
    
    return returns

class VectorizedParameterOptimizer:
    """Vectorized parameter optimizer"""
    
    def __init__(self, test_months: int = 3):
        """
        Initialize optimizer
        
        Args:
            test_months: Test period months
        """
        self.test_months = test_months
        
        # Optimized parameter grid - reduce combinations while maintaining coverage
        self.param_ranges = {
            'min_depth_pct': np.array([0.02, 0.03, 0.05]),
            'max_depth_pct': np.array([0.15, 0.20, 0.25]),
            'min_recovery_pct': np.array([0.60, 0.70, 0.80]),
            'max_total_time': np.array([24, 36, 48]),
            'max_recovery_time': np.array([12, 18, 24])
        }
        
        total_combinations = np.prod([len(v) for v in self.param_ranges.values()])
        logger.info(f"Vectorized optimizer initialized with {total_combinations} parameter combinations")
    
    def prepare_data(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, pd.Timestamp]:
        """Prepare data for vectorized computation"""
        # Ensure time sorting
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Extract prices and timestamps
        prices = df['close'].values.astype(np.float64)
        timestamps = df['timestamp'].values
        split_time = df['timestamp'].max() - pd.Timedelta(days=self.test_months * 30)
        
        return prices, timestamps, split_time
    
    def split_data_indices(self, timestamps: np.ndarray, split_time: pd.Timestamp) -> Tuple[np.ndarray, np.ndarray]:
        """Split training and test data indices"""
        # Convert timestamps to same type for comparison
        if isinstance(timestamps[0], pd.Timestamp):
            train_indices = np.where(timestamps < split_time)[0]
            test_indices = np.where(timestamps >= split_time)[0]
        else:
            # Convert to pandas timestamps for comparison
            timestamps_pd = pd.to_datetime(timestamps)
            train_indices = np.where(timestamps_pd < split_time)[0]
            test_indices = np.where(timestamps_pd >= split_time)[0]
        
        return train_indices, test_indices
    
    def optimize_single_symbol_vectorized(self, symbol: str, df: pd.DataFrame) -> Optional[OptimizedParams]:
        """
        Vectorized single cryptocurrency parameter optimization
        
        Args:
            symbol: Cryptocurrency symbol
            df: Price data
            
        Returns:
            Optimized parameters
        """
        logger.info(f"🚀 Vectorized optimization for {symbol}")
        
        try:
            # Prepare data
            prices, timestamps, split_time = self.prepare_data(df)
            train_indices, test_indices = self.split_data_indices(timestamps, split_time)
            
            if len(train_indices) < 1000 or len(test_indices) < 500:
                logger.warning(f"Insufficient data for {symbol}")
                return None
            
            train_prices = prices[train_indices]
            test_prices = prices[test_indices]
            
            logger.info(f"  Train: {len(train_prices)} points, Test: {len(test_prices)} points")
            
            best_score = 0.0
            best_params = None
            best_stats = None
            
            # Vectorized parameter search
            param_combinations = 0
            
            for min_depth in self.param_ranges['min_depth_pct']:
                for max_depth in self.param_ranges['max_depth_pct']:
                    if min_depth >= max_depth:
                        continue
                    
                    for min_recovery in self.param_ranges['min_recovery_pct']:
                        for max_total_time in self.param_ranges['max_total_time']:
                            for max_recovery_time in self.param_ranges['max_recovery_time']:
                                if max_recovery_time > max_total_time:
                                    continue
                                
                                param_combinations += 1
                                
                                # Training phase detection
                                train_starts, train_bottoms, train_recoveries = vectorized_pattern_detection(
                                    train_prices,
                                    min_depth, max_depth, min_recovery,
                                    int(max_total_time), int(max_recovery_time)
                                )
                                
                                if len(train_starts) == 0:
                                    continue
                                
                                # Training phase backtesting
                                entry_indices = train_recoveries + 1  # Enter next hour after recovery
                                valid_entries = entry_indices[entry_indices < len(train_prices) - 20]
                                
                                if len(valid_entries) == 0:
                                    continue
                                
                                train_returns = vectorized_backtest(train_prices, valid_entries, 20)
                                train_returns = train_returns - 0.002  # Deduct trading fees
                                
                                # Calculate training metrics
                                train_win_rate = np.mean(train_returns > 0)
                                train_avg_return = np.mean(train_returns)
                                train_total_return = np.prod(1 + train_returns) - 1
                                
                                # Calculate training score
                                if len(train_returns) < 5:  # At least 5 trades
                                    continue
                                
                                score = (train_win_rate * 0.5 + 
                                        min(train_avg_return / 0.02, 1.0) * 0.3 +
                                        min(len(train_returns) / 15, 1.0) * 0.2)
                                
                                if score > best_score:
                                    best_score = score
                                    best_params = {
                                        'min_depth_pct': min_depth,
                                        'max_depth_pct': max_depth,
                                        'min_recovery_pct': min_recovery,
                                        'max_total_time': int(max_total_time),
                                        'max_recovery_time': int(max_recovery_time)
                                    }
                                    best_stats = {
                                        'train_patterns': len(train_starts),
                                        'train_trades': len(train_returns),
                                        'train_win_rate': train_win_rate,
                                        'train_avg_return': train_avg_return,
                                        'train_total_return': train_total_return
                                    }
            
            if best_params is None:
                logger.warning(f"No valid parameters found for {symbol}")
                return None
            
            logger.info(f"  Tested {param_combinations} combinations, best score: {best_score:.3f}")
            
            # Validate on test data
            test_starts, test_bottoms, test_recoveries = vectorized_pattern_detection(
                test_prices,
                best_params['min_depth_pct'],
                best_params['max_depth_pct'],
                best_params['min_recovery_pct'],
                best_params['max_total_time'],
                best_params['max_recovery_time']
            )
            
            if len(test_starts) == 0:
                logger.warning(f"No test patterns for {symbol}")
                return None
            
            # Test phase backtesting
            test_entry_indices = test_recoveries + 1
            test_valid_entries = test_entry_indices[test_entry_indices < len(test_prices) - 20]
            
            if len(test_valid_entries) == 0:
                logger.warning(f"No valid test trades for {symbol}")
                return None
            
            test_returns = vectorized_backtest(test_prices, test_valid_entries, 20)
            test_returns = test_returns - 0.002  # Deduct trading fees
            
            # Calculate test metrics
            test_win_rate = np.mean(test_returns > 0)
            test_avg_return = np.mean(test_returns)
            test_total_return = np.prod(1 + test_returns) - 1
            
            test_score = (test_win_rate * 0.5 + 
                         min(test_avg_return / 0.02, 1.0) * 0.3 +
                         min(len(test_returns) / 15, 1.0) * 0.2)
            
            consistency_ratio = test_score / best_score if best_score > 0 else 0
            
            result = OptimizedParams(
                symbol=symbol,
                min_depth_pct=best_params['min_depth_pct'],
                max_depth_pct=best_params['max_depth_pct'],
                min_recovery_pct=best_params['min_recovery_pct'],
                max_total_time=best_params['max_total_time'],
                max_recovery_time=best_params['max_recovery_time'],
                train_score=best_score,
                test_score=test_score,
                train_patterns=best_stats['train_patterns'],
                test_patterns=len(test_starts),
                train_win_rate=best_stats['train_win_rate'],
                test_win_rate=test_win_rate,
                train_return=best_stats['train_total_return'],
                test_return=test_total_return,
                consistency_ratio=consistency_ratio
            )
            
            logger.info(f"✅ {symbol}: Train {best_stats['train_trades']} trades "
                       f"({best_stats['train_win_rate']:.1%} win, {best_stats['train_total_return']:.1%} return), "
                       f"Test {len(test_returns)} trades "
                       f"({test_win_rate:.1%} win, {test_total_return:.1%} return)")
            
            return result
            
        except Exception as e:
            logger.error(f"Error optimizing {symbol}: {e}")
            return None
    
    def optimize_multiple_symbols(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, OptimizedParams]:
        """Optimize multiple cryptocurrencies"""
        logger.info(f"🚀 Starting vectorized optimization for {len(data_dict)} symbols")
        
        results = {}
        
        for symbol, df in data_dict.items():
            result = self.optimize_single_symbol_vectorized(symbol, df)
            if result:
                results[symbol] = result
        
        logger.info(f"✅ Vectorized optimization completed: {len(results)}/{len(data_dict)} successful")
        return results
    
    def save_results(self, results: Dict[str, OptimizedParams], filename: Optional[str] = None) -> str:
        """Save optimization results"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vectorized_optimization_{timestamp}.json"
        
        # Prepare serializable results
        serializable_results = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_months": self.test_months,
                "total_symbols": len(results),
                "optimization_type": "vectorized"
            },
            "results": {}
        }
        
        for symbol, result in results.items():
            serializable_results["results"][symbol] = {
                "symbol": result.symbol,
                "optimal_parameters": {
                    "min_depth_pct": result.min_depth_pct,
                    "max_depth_pct": result.max_depth_pct,
                    "min_recovery_pct": result.min_recovery_pct,
                    "max_total_time": result.max_total_time,
                    "max_recovery_time": result.max_recovery_time
                },
                "performance": {
                    "train_score": result.train_score,
                    "test_score": result.test_score,
                    "train_patterns": result.train_patterns,
                    "test_patterns": result.test_patterns,
                    "train_win_rate": result.train_win_rate,
                    "test_win_rate": result.test_win_rate,
                    "train_return": result.train_return,
                    "test_return": result.test_return,
                    "consistency_ratio": result.consistency_ratio
                }
            }
        
        # Save to data directory
        import os
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(parent_dir, 'data')
        results_path = os.path.join(data_dir, filename)
        
        import json
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Results saved to: {results_path}")
        return results_path


def print_vectorized_results(results: Dict[str, OptimizedParams]):
    """Print vectorized optimization results"""
    if not results:
        print("❌ No optimization results")
        return
    
    print(f"\n⚡ Vectorized V-Pattern Optimization Results")
    print("=" * 90)
    print(f"{'Symbol':<12} {'Train Score':<11} {'Test Score':<10} {'Consistency':<11} "
          f"{'Test Win%':<9} {'Test Return':<11}")
    print("-" * 90)
    
    for symbol, result in results.items():
        print(f"{symbol:<12} {result.train_score:>10.3f} {result.test_score:>9.3f} "
              f"{result.consistency_ratio:>10.2f} {result.test_win_rate:>8.1%} "
              f"{result.test_return:>10.2%}")
    
    # Summary statistics
    avg_consistency = np.mean([r.consistency_ratio for r in results.values()])
    avg_test_win_rate = np.mean([r.test_win_rate for r in results.values()])
    avg_test_return = np.mean([r.test_return for r in results.values()])
    
    print("-" * 90)
    print(f"{'AVERAGE':<12} {'--':>10} {'--':>9} {avg_consistency:>10.2f} "
          f"{avg_test_win_rate:>8.1%} {avg_test_return:>10.2%}")
    
    print(f"\n📊 Summary:")
    print(f"  Average consistency ratio: {avg_consistency:.2f}")
    print(f"  Average test win rate: {avg_test_win_rate:.1%}")
    print(f"  Average test return: {avg_test_return:.2%}")


if __name__ == "__main__":
    # Test vectorized optimizer
    logging.basicConfig(level=logging.INFO)
    
    print("⚡ Testing Vectorized V-Pattern Optimizer")
    
    # Can load actual data for testing here
    # from data_loader import VReversalDataLoader
    # 
    # loader = VReversalDataLoader()
    # data = loader.load_multiple_symbols(['BTC-USDT', 'ETH-USDT'], months=6)
    # 
    # optimizer = VectorizedParameterOptimizer()
    # results = optimizer.optimize_multiple_symbols(data)
    # print_vectorized_results(results)
