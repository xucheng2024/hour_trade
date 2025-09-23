#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vectorized Profit Maximizer for V-Pattern Strategy
Vectorized V-shaped reversal strategy profit maximizer
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
import itertools
import warnings

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

@dataclass
class MaxProfitParams:
    """Profit maximization parameters"""
    symbol: str
    # V-pattern detection parameters
    min_depth_pct: float
    max_depth_pct: float
    min_recovery_pct: float
    max_total_time: int
    max_recovery_time: int
    # Trading parameters
    stop_loss_pct: float
    take_profit_pct: float
    holding_hours: int
    # Performance metrics
    train_return: float
    test_return: float
    train_win_rate: float
    test_win_rate: float
    train_trades: int
    test_trades: int
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float

def find_local_extremes_fast(prices: np.ndarray, window: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """Fast local extremum finding"""
    peaks = []
    troughs = []
    
    for i in range(window, len(prices) - window):
        # Check for local highs
        if all(prices[i] >= prices[i-j] for j in range(1, window+1)) and \
           all(prices[i] >= prices[i+j] for j in range(1, window+1)):
            peaks.append(i)
        
        # Check for local lows
        if all(prices[i] <= prices[i-j] for j in range(1, window+1)) and \
           all(prices[i] <= prices[i+j] for j in range(1, window+1)):
            troughs.append(i)
    
    return np.array(peaks), np.array(troughs)

def vectorized_v_detection_fast(prices: np.ndarray, 
                               min_depth: float,
                               max_depth: float,
                               min_recovery: float,
                               max_total_time: int,
                               max_recovery_time: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fast vectorized V-pattern detection"""
    peaks, troughs = find_local_extremes_fast(prices)
    
    patterns_start = []
    patterns_bottom = []
    patterns_recovery = []
    
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
            
            if not (min_depth <= depth_pct <= max_depth):
                continue
            
            recovery_threshold = bottom_price + (start_price - bottom_price) * min_recovery
            
            # Vectorized search for recovery point
            recovery_end = min(trough_idx + max_recovery_time, len(prices))
            recovery_slice = prices[trough_idx+1:recovery_end]
            
            recovery_hits = recovery_slice >= recovery_threshold
            if recovery_hits.any():
                recovery_idx = trough_idx + 1 + np.argmax(recovery_hits)
                
                patterns_start.append(peak_idx)
                patterns_bottom.append(trough_idx)
                patterns_recovery.append(recovery_idx)
                break
    
    return (np.array(patterns_start), np.array(patterns_bottom), np.array(patterns_recovery))

def vectorized_advanced_backtest(prices: np.ndarray,
                                entry_indices: np.ndarray,
                                stop_loss_pct: float,
                                take_profit_pct: float,
                                holding_hours: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized advanced backtesting with stop loss and take profit
    
    Returns:
        (returns, exit_reasons, holding_times)
    """
    n_trades = len(entry_indices)
    returns = np.zeros(n_trades)
    exit_reasons = np.zeros(n_trades, dtype=int)  # 0=time, 1=SL, 2=TP
    holding_times = np.zeros(n_trades)
    
    for i, entry_idx in enumerate(entry_indices):
        if entry_idx >= len(prices) - 1:
            continue
            
        entry_price = prices[entry_idx]
        max_exit_idx = min(entry_idx + holding_hours, len(prices) - 1)
        
        # Calculate stop loss and take profit prices
        sl_price = entry_price * (1 - stop_loss_pct)
        tp_price = entry_price * (1 + take_profit_pct)
        
        # Check prices during holding period
        exit_idx = max_exit_idx
        exit_reason = 0  # Default time exit
        
        for j in range(entry_idx + 1, max_exit_idx + 1):
            low = prices[j] if j < len(prices) else prices[-1]
            high = prices[j] if j < len(prices) else prices[-1]
            
            # Check stop loss
            if low <= sl_price:
                exit_idx = j
                exit_reason = 1  # Stop loss
                break
            
            # Check take profit
            if high >= tp_price:
                exit_idx = j
                exit_reason = 2  # Take profit
                break
        
        # Calculate returns
        if exit_reason == 1:  # Stop loss
            exit_price = sl_price
        elif exit_reason == 2:  # Take profit
            exit_price = tp_price
        else:  # Time exit
            exit_price = prices[exit_idx] if exit_idx < len(prices) else prices[-1]
        
        returns[i] = (exit_price - entry_price) / entry_price
        exit_reasons[i] = exit_reason
        holding_times[i] = exit_idx - entry_idx
    
    return returns, exit_reasons, holding_times

class VectorizedProfitMaximizer:
    """Vectorized profit maximizer"""
    
    def __init__(self, test_months: int = 3):
        """Initialize profit maximizer"""
        self.test_months = test_months
        
        # Extended parameter grid - focused on profit maximization, especially optimizing holding time
        self.param_ranges = {
            # V-pattern detection parameters
            'min_depth_pct': np.array([0.02, 0.03, 0.05]),
            'max_depth_pct': np.array([0.10, 0.15, 0.20, 0.25]),
            'min_recovery_pct': np.array([0.60, 0.70, 0.80]),
            'max_total_time': np.array([24, 36, 48]),
            'max_recovery_time': np.array([12, 18, 24]),
            
            # Profit maximization parameters
            'stop_loss_pct': np.array([0.03, 0.05, 0.08, 0.10]),      # 3%-10% stop loss
            'take_profit_pct': np.array([0.08, 0.12, 0.15, 0.20, 0.25]), # 8%-25% take profit
            'holding_hours': np.array([6, 8, 12, 16, 20, 24, 30, 36, 48, 72])  # 6-72 hours holding (key optimization)
        }
        
        total_combinations = np.prod([len(v) for v in self.param_ranges.values()])
        logger.info(f"Profit Maximizer initialized with {total_combinations} parameter combinations")
    
    def split_data_by_time(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Split training and test data by time"""
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        latest_time = df['timestamp'].max()
        split_time = latest_time - pd.Timedelta(days=self.test_months * 30)
        
        train_df = df[df['timestamp'] < split_time].copy()
        test_df = df[df['timestamp'] >= split_time].copy()
        
        return train_df, test_df
    
    def calculate_performance_metrics(self, returns: np.ndarray, exit_reasons: np.ndarray) -> Dict:
        """Calculate detailed performance metrics"""
        if len(returns) == 0:
            return {
                'total_return': 0.0,
                'win_rate': 0.0,
                'avg_return': 0.0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'profit_factor': 0.0,
                'sl_rate': 0.0,
                'tp_rate': 0.0
            }
        
        # Basic metrics
        total_return = np.prod(1 + returns) - 1
        win_rate = np.mean(returns > 0)
        avg_return = np.mean(returns)
        
        # Maximum drawdown
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        # Sharpe ratio
        sharpe_ratio = avg_return / np.std(returns) if np.std(returns) > 0 else 0
        
        # Profit factor
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        profit_factor = (np.sum(wins) / abs(np.sum(losses))) if len(losses) > 0 and np.sum(losses) != 0 else float('inf')
        
        # Exit method statistics
        sl_rate = np.mean(exit_reasons == 1)  # Stop loss rate
        tp_rate = np.mean(exit_reasons == 2)  # Take profit rate
        
        return {
            'total_return': total_return,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'profit_factor': profit_factor,
            'sl_rate': sl_rate,
            'tp_rate': tp_rate
        }
    
    def evaluate_parameter_set(self, params: Dict, prices: np.ndarray) -> float:
        """Evaluate profit potential of a single parameter set"""
        try:
            # V-pattern detection
            starts, bottoms, recoveries = vectorized_v_detection_fast(
                prices,
                params['min_depth_pct'],
                params['max_depth_pct'],
                params['min_recovery_pct'],
                params['max_total_time'],
                params['max_recovery_time']
            )
            
            if len(starts) == 0:
                return 0.0
            
            # Advanced backtesting
            entry_indices = recoveries + 1
            valid_entries = entry_indices[entry_indices < len(prices) - params['holding_hours']]
            
            if len(valid_entries) < 3:  # At least 3 trades needed
                return 0.0
            
            returns, exit_reasons, holding_times = vectorized_advanced_backtest(
                prices, valid_entries,
                params['stop_loss_pct'],
                params['take_profit_pct'],
                params['holding_hours']
            )
            
            # Deduct trading fees
            returns = returns - 0.002  # 0.2% bilateral fees
            
            metrics = self.calculate_performance_metrics(returns, exit_reasons)
            
            # Comprehensive scoring - focused on profit maximization
            profit_score = metrics['total_return'] * 0.4
            consistency_score = metrics['win_rate'] * 0.2
            risk_score = max(0, 1 + metrics['max_drawdown']) * 0.2  # Lower drawdown is better
            sharpe_score = min(metrics['sharpe_ratio'] / 3.0, 1.0) * 0.2  # Sharpe ratio normalization
            
            return profit_score + consistency_score + risk_score + sharpe_score
            
        except Exception as e:
            logger.warning(f"Error evaluating params: {e}")
            return 0.0
    
    def optimize_for_max_profit(self, symbol: str, df: pd.DataFrame) -> Optional[MaxProfitParams]:
        """Optimize profit maximization parameters for a single cryptocurrency"""
        logger.info(f"🚀 Optimizing for maximum profit: {symbol}")
        
        try:
            # Split data
            train_df, test_df = self.split_data_by_time(df)
            
            if len(train_df) < 1000 or len(test_df) < 500:
                logger.warning(f"Insufficient data for {symbol}")
                return None
            
            train_prices = train_df['close'].values.astype(np.float64)
            test_prices = test_df['close'].values.astype(np.float64)
            
            logger.info(f"  Train: {len(train_prices)} points, Test: {len(test_prices)} points")
            
            # Generate parameter combinations
            param_names = list(self.param_ranges.keys())
            param_values = list(self.param_ranges.values())
            
            best_score = 0.0
            best_params = None
            best_metrics = None
            
            # Use batch processing to avoid memory issues
            batch_size = 1000
            total_combinations = np.prod([len(v) for v in param_values])
            
            logger.info(f"  Testing {total_combinations} parameter combinations...")
            
            combination_count = 0
            for combo_batch in self._generate_param_batches(param_names, param_values, batch_size):
                for params in combo_batch:
                    # Basic constraint checks
                    if (params['min_depth_pct'] >= params['max_depth_pct'] or
                        params['max_recovery_time'] > params['max_total_time'] or
                        params['stop_loss_pct'] >= params['take_profit_pct']):
                        continue
                    
                    score = self.evaluate_parameter_set(params, train_prices)
                    combination_count += 1
                    
                    if score > best_score:
                        best_score = score
                        best_params = params.copy()
                        
                        # Calculate detailed metrics for recording
                        best_metrics = self._get_detailed_metrics(params, train_prices, test_prices)
                
                if combination_count % 1000 == 0:
                    logger.info(f"    Tested {combination_count} combinations, best score: {best_score:.4f}")
            
            if best_params is None:
                logger.warning(f"No valid parameters found for {symbol}")
                return None
            
            logger.info(f"✅ {symbol} optimization complete: score {best_score:.4f}")
            
            # Build result
            result = MaxProfitParams(
                symbol=symbol,
                min_depth_pct=best_params['min_depth_pct'],
                max_depth_pct=best_params['max_depth_pct'],
                min_recovery_pct=best_params['min_recovery_pct'],
                max_total_time=best_params['max_total_time'],
                max_recovery_time=best_params['max_recovery_time'],
                stop_loss_pct=best_params['stop_loss_pct'],
                take_profit_pct=best_params['take_profit_pct'],
                holding_hours=best_params['holding_hours'],
                **best_metrics
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error optimizing {symbol}: {e}")
            return None
    
    def _generate_param_batches(self, param_names: List, param_values: List, batch_size: int):
        """Generate parameter combinations in batches"""
        combinations = itertools.product(*param_values)
        
        batch = []
        for combo in combinations:
            params = dict(zip(param_names, combo))
            batch.append(params)
            
            if len(batch) >= batch_size:
                yield batch
                batch = []
        
        if batch:
            yield batch
    
    def _get_detailed_metrics(self, params: Dict, train_prices: np.ndarray, test_prices: np.ndarray) -> Dict:
        """Get detailed training and test metrics"""
        # Training metrics
        train_metrics = self._calculate_metrics_for_prices(params, train_prices)
        
        # Test metrics  
        test_metrics = self._calculate_metrics_for_prices(params, test_prices)
        
        return {
            'train_return': train_metrics['total_return'],
            'test_return': test_metrics['total_return'],
            'train_win_rate': train_metrics['win_rate'],
            'test_win_rate': test_metrics['win_rate'],
            'train_trades': train_metrics['trades'],
            'test_trades': test_metrics['trades'],
            'max_drawdown': test_metrics['max_drawdown'],
            'sharpe_ratio': test_metrics['sharpe_ratio'],
            'profit_factor': test_metrics['profit_factor']
        }
    
    def _calculate_metrics_for_prices(self, params: Dict, prices: np.ndarray) -> Dict:
        """Calculate metrics for given price data"""
        starts, bottoms, recoveries = vectorized_v_detection_fast(
            prices,
            params['min_depth_pct'],
            params['max_depth_pct'], 
            params['min_recovery_pct'],
            params['max_total_time'],
            params['max_recovery_time']
        )
        
        if len(starts) == 0:
            return {'total_return': 0, 'win_rate': 0, 'trades': 0, 'max_drawdown': 0, 'sharpe_ratio': 0, 'profit_factor': 0}
        
        entry_indices = recoveries + 1
        valid_entries = entry_indices[entry_indices < len(prices) - params['holding_hours']]
        
        if len(valid_entries) == 0:
            return {'total_return': 0, 'win_rate': 0, 'trades': 0, 'max_drawdown': 0, 'sharpe_ratio': 0, 'profit_factor': 0}
        
        returns, exit_reasons, _ = vectorized_advanced_backtest(
            prices, valid_entries,
            params['stop_loss_pct'],
            params['take_profit_pct'],
            params['holding_hours']
        )
        
        returns = returns - 0.002  # Trading fees
        
        metrics = self.calculate_performance_metrics(returns, exit_reasons)
        metrics['trades'] = len(returns)
        
        return metrics
    
    def optimize_multiple_symbols(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, MaxProfitParams]:
        """Optimize profit maximization parameters for multiple cryptocurrencies"""
        logger.info(f"🚀 Starting profit maximization for {len(data_dict)} symbols")
        
        results = {}
        
        for symbol, df in data_dict.items():
            result = self.optimize_for_max_profit(symbol, df)
            if result:
                results[symbol] = result
        
        logger.info(f"✅ Profit maximization completed: {len(results)}/{len(data_dict)} successful")
        return results
    
    def save_results(self, results: Dict[str, MaxProfitParams], filename: Optional[str] = None) -> str:
        """Save optimization results"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"profit_maximization_{timestamp}.json"
        
        # Prepare serializable results
        serializable_results = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_months": self.test_months,
                "total_symbols": len(results),
                "optimization_type": "profit_maximization"
            },
            "results": {}
        }
        
        for symbol, result in results.items():
            serializable_results["results"][symbol] = {
                "symbol": result.symbol,
                "v_detection_params": {
                    "min_depth_pct": float(result.min_depth_pct),
                    "max_depth_pct": float(result.max_depth_pct),
                    "min_recovery_pct": float(result.min_recovery_pct),
                    "max_total_time": int(result.max_total_time),
                    "max_recovery_time": int(result.max_recovery_time)
                },
                "trading_params": {
                    "stop_loss_pct": float(result.stop_loss_pct),
                    "take_profit_pct": float(result.take_profit_pct),
                    "holding_hours": int(result.holding_hours)
                },
                "performance": {
                    "train_return": float(result.train_return),
                    "test_return": float(result.test_return),
                    "train_win_rate": float(result.train_win_rate),
                    "test_win_rate": float(result.test_win_rate),
                    "train_trades": int(result.train_trades),
                    "test_trades": int(result.test_trades),
                    "max_drawdown": float(result.max_drawdown),
                    "sharpe_ratio": float(result.sharpe_ratio),
                    "profit_factor": float(result.profit_factor)
                }
            }
        
        # Save file
        import os, json
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(parent_dir, 'data')
        results_path = os.path.join(data_dir, filename)
        
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Results saved to: {results_path}")
        return results_path


def print_profit_maximization_results(results: Dict[str, MaxProfitParams]):
    """Print profit maximization results"""
    if not results:
        print("❌ No optimization results")
        return
    
    print(f"\n💰 Profit Maximization Results")
    print("=" * 120)
    print(f"{'Symbol':<12} {'Test Return':<11} {'Win Rate':<9} {'Trades':<7} {'SL%':<6} "
          f"{'TP%':<6} {'Hours':<6} {'Sharpe':<7} {'Profit Factor':<12}")
    print("-" * 120)
    
    for symbol, result in results.items():
        print(f"{symbol:<12} {result.test_return:>10.2%} {result.test_win_rate:>8.1%} "
              f"{result.test_trades:>6} {result.stop_loss_pct:>5.1%} "
              f"{result.take_profit_pct:>5.1%} {result.holding_hours:>5} "
              f"{result.sharpe_ratio:>6.2f} {result.profit_factor:>11.2f}")
    
    # Summary statistics
    avg_return = np.mean([r.test_return for r in results.values()])
    avg_win_rate = np.mean([r.test_win_rate for r in results.values()])
    total_trades = sum([r.test_trades for r in results.values()])
    
    print("-" * 120)
    print(f"{'AVERAGE':<12} {avg_return:>10.2%} {avg_win_rate:>8.1%} {total_trades:>6} "
          f"{'--':>5} {'--':>5} {'--':>5} {'--':>6} {'--':>11}")


if __name__ == "__main__":
    # Test profit maximizer
    logging.basicConfig(level=logging.INFO)
    
    print("💰 Testing Vectorized Profit Maximizer")
    
    # Can load actual data for testing here
