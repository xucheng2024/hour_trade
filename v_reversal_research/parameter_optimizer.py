#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V-Pattern Parameter Optimizer
V-shaped pattern parameter optimizer - optimizes detection parameters based on historical data
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from v_pattern_detector import VPatternDetector, VPattern
from v_strategy_backtester import VReversalBacktester, BacktestResult

logger = logging.getLogger(__name__)

@dataclass
class OptimalParams:
    """Optimized parameters"""
    symbol: str
    min_depth_pct: float
    max_depth_pct: float
    min_recovery_pct: float
    max_total_time: int
    max_recovery_time: int
    train_score: float
    train_patterns: int
    train_trades: int
    train_win_rate: float
    train_total_return: float

@dataclass
class ValidationResult:
    """Validation results"""
    symbol: str
    optimal_params: OptimalParams
    test_score: float
    test_patterns: int
    test_trades: int
    test_win_rate: float
    test_total_return: float
    test_sharpe_ratio: float
    consistency_ratio: float  # Test/training performance ratio

class VPatternParameterOptimizer:
    """V-shaped pattern parameter optimizer"""
    
    def __init__(self, 
                 test_months: int = 3,           # Test period 3 months
                 min_train_months: int = 6,      # Minimum training period 6 months
                 max_workers: int = 4):          # Parallel worker threads
        """
        Initialize parameter optimizer
        
        Args:
            test_months: Test period months
            min_train_months: Minimum training period months
            max_workers: Parallel processing threads
        """
        self.test_months = test_months
        self.min_train_months = min_train_months
        self.max_workers = max_workers
        
        # Define parameter optimization ranges
        self.param_grid = {
            'min_depth_pct': [0.02, 0.03, 0.04, 0.05],           # 2%-5%
            'max_depth_pct': [0.15, 0.20, 0.25, 0.30],           # 15%-30%
            'min_recovery_pct': [0.60, 0.70, 0.80, 0.90],        # 60%-90%
            'max_total_time': [24, 36, 48, 60],                  # 24-60 hours
            'max_recovery_time': [12, 18, 24, 30]                # 12-30 hours
        }
        
        logger.info(f"Parameter Optimizer initialized:")
        logger.info(f"  Test period: {test_months} months")
        logger.info(f"  Min training period: {min_train_months} months")
        logger.info(f"  Parameter combinations: {self._count_param_combinations()}")
        logger.info(f"  Max workers: {max_workers}")
    
    def _count_param_combinations(self) -> int:
        """Calculate total parameter combinations"""
        count = 1
        for values in self.param_grid.values():
            count *= len(values)
        return count
    
    def split_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split training and test data
        
        Args:
            df: Complete data
            
        Returns:
            (training data, test data)
        """
        if 'timestamp' not in df.columns:
            raise ValueError("DataFrame must contain 'timestamp' column")
        
        # Ensure time format
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Sort by time
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Calculate split point
        latest_time = df['timestamp'].max()
        split_time = latest_time - pd.Timedelta(days=self.test_months * 30)
        
        train_df = df[df['timestamp'] < split_time].copy()
        test_df = df[df['timestamp'] >= split_time].copy()
        
        # Validate data amount
        train_months = (train_df['timestamp'].max() - train_df['timestamp'].min()).days / 30
        test_months = (test_df['timestamp'].max() - test_df['timestamp'].min()).days / 30
        
        if train_months < self.min_train_months:
            raise ValueError(f"Insufficient training data: {train_months:.1f} months < {self.min_train_months}")
        
        logger.info(f"Data split: Train {len(train_df)} records ({train_months:.1f}m), "
                   f"Test {len(test_df)} records ({test_months:.1f}m)")
        
        return train_df, test_df
    
    def _evaluate_params(self, params: Dict, train_df: pd.DataFrame) -> Tuple[float, int, int, float, float]:
        """
        Evaluate parameter combination performance on training data
        
        Args:
            params: Parameter dictionary
            train_df: Training data
            
        Returns:
            (score, pattern count, trade count, win rate, total return)
        """
        try:
            # Create detector
            detector = VPatternDetector(
                min_depth_pct=params['min_depth_pct'],
                max_depth_pct=params['max_depth_pct'],
                min_recovery_pct=params['min_recovery_pct'],
                max_total_time=params['max_total_time'],
                max_recovery_time=params['max_recovery_time']
            )
            
            # Detect patterns
            patterns = detector.detect_patterns(train_df)
            
            if len(patterns) == 0:
                return 0.0, 0, 0, 0.0, 0.0
            
            # Backtest
            backtester = VReversalBacktester(holding_hours=20, min_pattern_quality=0.1)
            result = backtester.backtest_symbol(train_df, patterns)
            
            if result.total_trades == 0:
                return 0.0, len(patterns), 0, 0.0, 0.0
            
            # Calculate comprehensive score
            # Comprehensive score based on win rate, average return, trade count
            win_rate_score = result.win_rate
            return_score = max(0, result.avg_return_per_trade / 0.05)  # 5% is full score
            frequency_score = min(1.0, result.total_trades / 20)  # 20 trades is full score
            
            # Comprehensive score
            score = win_rate_score * 0.4 + return_score * 0.4 + frequency_score * 0.2
            
            return score, len(patterns), result.total_trades, result.win_rate, result.total_return
            
        except Exception as e:
            logger.warning(f"Error evaluating params {params}: {e}")
            return 0.0, 0, 0, 0.0, 0.0
    
    def optimize_single_symbol(self, symbol: str, df: pd.DataFrame) -> Optional[OptimalParams]:
        """
        Optimize parameters for a single cryptocurrency
        
        Args:
            symbol: Cryptocurrency symbol
            df: Price data
            
        Returns:
            Optimal parameters or None
        """
        logger.info(f"Optimizing parameters for {symbol}...")
        
        try:
            # Split data
            train_df, test_df = self.split_data(df)
            
            # Generate all parameter combinations
            param_names = list(self.param_grid.keys())
            param_values = list(self.param_grid.values())
            param_combinations = list(itertools.product(*param_values))
            
            logger.info(f"Testing {len(param_combinations)} parameter combinations for {symbol}")
            
            best_score = 0.0
            best_params = None
            best_stats = None
            
            # Test parameter combinations one by one
            for i, combination in enumerate(param_combinations):
                params = dict(zip(param_names, combination))
                
                # Add constraint checks
                if params['min_depth_pct'] >= params['max_depth_pct']:
                    continue
                if params['max_recovery_time'] > params['max_total_time']:
                    continue
                
                score, patterns, trades, win_rate, total_return = self._evaluate_params(params, train_df)
                
                if score > best_score:
                    best_score = score
                    best_params = params
                    best_stats = (patterns, trades, win_rate, total_return)
                
                if (i + 1) % 50 == 0:
                    logger.info(f"  {symbol}: Tested {i+1}/{len(param_combinations)} combinations, "
                               f"best score: {best_score:.3f}")
            
            if best_params is None:
                logger.warning(f"No valid parameters found for {symbol}")
                return None
            
            patterns, trades, win_rate, total_return = best_stats
            
            optimal_params = OptimalParams(
                symbol=symbol,
                min_depth_pct=best_params['min_depth_pct'],
                max_depth_pct=best_params['max_depth_pct'],
                min_recovery_pct=best_params['min_recovery_pct'],
                max_total_time=best_params['max_total_time'],
                max_recovery_time=best_params['max_recovery_time'],
                train_score=best_score,
                train_patterns=patterns,
                train_trades=trades,
                train_win_rate=win_rate,
                train_total_return=total_return
            )
            
            logger.info(f"✅ {symbol} optimization complete: "
                       f"Score {best_score:.3f}, "
                       f"Patterns {patterns}, "
                       f"Trades {trades}, "
                       f"Win rate {win_rate:.1%}")
            
            return optimal_params
            
        except Exception as e:
            logger.error(f"Error optimizing {symbol}: {e}")
            return None
    
    def validate_optimized_params(self, optimal_params: OptimalParams, df: pd.DataFrame) -> Optional[ValidationResult]:
        """
        Validate optimized parameters on test data
        
        Args:
            optimal_params: Optimized parameters
            df: Complete data
            
        Returns:
            Validation result or None
        """
        try:
            # Split data
            train_df, test_df = self.split_data(df)
            
            # Create detector with optimized parameters
            detector = VPatternDetector(
                min_depth_pct=optimal_params.min_depth_pct,
                max_depth_pct=optimal_params.max_depth_pct,
                min_recovery_pct=optimal_params.min_recovery_pct,
                max_total_time=optimal_params.max_total_time,
                max_recovery_time=optimal_params.max_recovery_time
            )
            
            # Detect patterns on test data
            test_patterns = detector.detect_patterns(test_df)
            
            if len(test_patterns) == 0:
                logger.warning(f"No patterns detected in test data for {optimal_params.symbol}")
                return None
            
            # Backtest
            backtester = VReversalBacktester(holding_hours=20, min_pattern_quality=0.1)
            test_result = backtester.backtest_symbol(test_df, test_patterns)
            
            if test_result.total_trades == 0:
                logger.warning(f"No trades executed in test data for {optimal_params.symbol}")
                return None
            
            # Calculate test score
            win_rate_score = test_result.win_rate
            return_score = max(0, test_result.avg_return_per_trade / 0.05)
            frequency_score = min(1.0, test_result.total_trades / 20)
            test_score = win_rate_score * 0.4 + return_score * 0.4 + frequency_score * 0.2
            
            # Calculate consistency ratio
            consistency_ratio = test_score / optimal_params.train_score if optimal_params.train_score > 0 else 0
            
            validation_result = ValidationResult(
                symbol=optimal_params.symbol,
                optimal_params=optimal_params,
                test_score=test_score,
                test_patterns=len(test_patterns),
                test_trades=test_result.total_trades,
                test_win_rate=test_result.win_rate,
                test_total_return=test_result.total_return,
                test_sharpe_ratio=test_result.sharpe_ratio,
                consistency_ratio=consistency_ratio
            )
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating {optimal_params.symbol}: {e}")
            return None
    
    def optimize_multiple_symbols(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, OptimalParams]:
        """
        Optimize parameters for multiple cryptocurrencies
        
        Args:
            data_dict: Cryptocurrency data dictionary
            
        Returns:
            Optimization results dictionary
        """
        logger.info(f"Starting parameter optimization for {len(data_dict)} symbols")
        
        optimized_params = {}
        
        for symbol, df in data_dict.items():
            optimal_params = self.optimize_single_symbol(symbol, df)
            if optimal_params:
                optimized_params[symbol] = optimal_params
        
        logger.info(f"✅ Parameter optimization completed for {len(optimized_params)}/{len(data_dict)} symbols")
        return optimized_params
    
    def run_full_optimization_and_validation(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, ValidationResult]:
        """
        Run complete optimization and validation process
        
        Args:
            data_dict: Cryptocurrency data dictionary
            
        Returns:
            Validation results dictionary
        """
        logger.info(f"🚀 Starting full optimization and validation for {len(data_dict)} symbols")
        
        # 1. Parameter optimization
        optimized_params = self.optimize_multiple_symbols(data_dict)
        
        if not optimized_params:
            logger.error("No parameters optimized successfully")
            return {}
        
        # 2. Validation
        logger.info(f"📊 Validating optimized parameters on test data...")
        validation_results = {}
        
        for symbol, params in optimized_params.items():
            if symbol in data_dict:
                validation_result = self.validate_optimized_params(params, data_dict[symbol])
                if validation_result:
                    validation_results[symbol] = validation_result
        
        logger.info(f"✅ Validation completed for {len(validation_results)}/{len(optimized_params)} symbols")
        return validation_results
    
    def save_optimization_results(self, validation_results: Dict[str, ValidationResult], 
                                filename: Optional[str] = None) -> str:
        """Save optimization results"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"v_pattern_optimization_{timestamp}.json"
        
        # Prepare serializable results
        serializable_results = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_months": self.test_months,
                "min_train_months": self.min_train_months,
                "total_symbols": len(validation_results),
                "param_grid": self.param_grid
            },
            "results": {}
        }
        
        for symbol, result in validation_results.items():
            serializable_results["results"][symbol] = {
                "optimal_parameters": {
                    "min_depth_pct": result.optimal_params.min_depth_pct,
                    "max_depth_pct": result.optimal_params.max_depth_pct,
                    "min_recovery_pct": result.optimal_params.min_recovery_pct,
                    "max_total_time": result.optimal_params.max_total_time,
                    "max_recovery_time": result.optimal_params.max_recovery_time
                },
                "training_performance": {
                    "score": result.optimal_params.train_score,
                    "patterns": result.optimal_params.train_patterns,
                    "trades": result.optimal_params.train_trades,
                    "win_rate": result.optimal_params.train_win_rate,
                    "total_return": result.optimal_params.train_total_return
                },
                "test_performance": {
                    "score": result.test_score,
                    "patterns": result.test_patterns,
                    "trades": result.test_trades,
                    "win_rate": result.test_win_rate,
                    "total_return": result.test_total_return,
                    "sharpe_ratio": result.test_sharpe_ratio,
                    "consistency_ratio": result.consistency_ratio
                }
            }
        
        # Save to data directory
        import os
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(parent_dir, 'data')
        results_path = os.path.join(data_dir, filename)
        
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Optimization results saved to: {results_path}")
        return results_path


def print_optimization_summary(validation_results: Dict[str, ValidationResult]):
    """Print optimization results summary"""
    if not validation_results:
        print("❌ No optimization results")
        return
    
    print(f"\n🎯 V-Pattern Parameter Optimization Results")
    print("=" * 100)
    print(f"{'Symbol':<12} {'Train Score':<11} {'Test Score':<10} {'Consistency':<11} "
          f"{'Test Win%':<9} {'Test Return':<11} {'Test Trades':<11}")
    print("-" * 100)
    
    for symbol, result in validation_results.items():
        print(f"{symbol:<12} {result.optimal_params.train_score:>10.3f} "
              f"{result.test_score:>9.3f} {result.consistency_ratio:>10.2f} "
              f"{result.test_win_rate:>8.1%} {result.test_total_return:>10.2%} "
              f"{result.test_trades:>10}")
    
    # Summary statistics
    all_results = list(validation_results.values())
    avg_train_score = np.mean([r.optimal_params.train_score for r in all_results])
    avg_test_score = np.mean([r.test_score for r in all_results])
    avg_consistency = np.mean([r.consistency_ratio for r in all_results])
    avg_test_win_rate = np.mean([r.test_win_rate for r in all_results])
    avg_test_return = np.mean([r.test_total_return for r in all_results])
    total_test_trades = sum([r.test_trades for r in all_results])
    
    print("-" * 100)
    print(f"{'AVERAGE':<12} {avg_train_score:>10.3f} {avg_test_score:>9.3f} "
          f"{avg_consistency:>10.2f} {avg_test_win_rate:>8.1%} "
          f"{avg_test_return:>10.2%} {total_test_trades:>10}")


if __name__ == "__main__":
    # Test parameter optimizer
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Testing V-Pattern Parameter Optimizer")
    
    # Can load actual data for testing here
    # from data_loader import VReversalDataLoader
    # 
    # loader = VReversalDataLoader()
    # data = loader.load_multiple_symbols(['BTC-USDT', 'ETH-USDT'], months=9)
    # 
    # optimizer = VPatternParameterOptimizer()
    # results = optimizer.run_full_optimization_and_validation(data)
    # print_optimization_summary(results)

