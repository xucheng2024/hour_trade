#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rolling Window Strategy Optimizer for OKX Trading
Extends StrategyOptimizer with rolling time window optimization capabilities
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import numpy as np

from .strategy_optimizer import StrategyOptimizer

# Configure logging
logger = logging.getLogger(__name__)

class RollingWindowOptimizer(StrategyOptimizer):
    """Rolling window strategy optimizer - extends base optimizer with time window analysis"""
    
    def __init__(self, buy_fee: float = 0.001, sell_fee: float = 0.001):
        super().__init__(buy_fee, sell_fee)
    
    def optimize_with_rolling_windows(self, instId: str, start: int, end: int,
                                    date_dict: Dict[str, Any], bar: str,
                                    strategy_type: str = "1d",
                                    window_size: str = "3m",
                                    step_size: str = "1m") -> Optional[Dict[str, Any]]:
        """
        Optimize strategy using rolling time windows
        
        Args:
            instId: Instrument ID
            start: Start timestamp (0 for all data)
            end: End timestamp (0 for all data)
            date_dict: Dictionary to store results
            bar: Timeframe (1d, 1h, 15m)
            strategy_type: Strategy type (1d, 1h)
            window_size: Size of each time window ('1m', '3m', '6m', '1y')
            step_size: Step size between windows ('1m', '3m', '6m', '1y')
            
        Returns:
            Dictionary with rolling window optimization results
        """
        logger.info(f"🔄 Starting rolling window optimization for {instId}")
        logger.info(f"   Window size: {window_size}, Step size: {step_size}")
        
        # Get all historical data
        data = self.data_loader.get_hist_candle_data(instId, start, end, bar)
        if data is None or len(data) == 0:
            logger.warning(f"No data available for {instId}")
            return None
        
        # Convert timestamps to datetime for easier manipulation
        timestamps = data[:, 8].astype(np.int64)
        datetime_index = np.array([datetime.fromtimestamp(ts/1000) for ts in timestamps])
        
        # Calculate window and step sizes in days
        window_days = self._period_to_days(window_size)
        step_days = self._period_to_days(step_size)
        
        # Find the earliest and latest dates
        earliest_date = np.min(datetime_index)
        latest_date = np.max(datetime_index)
        
        logger.info(f"📅 Data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}")
        
        # Generate rolling windows
        windows = self._generate_rolling_windows(earliest_date, latest_date, window_days, step_days)
        
        if not windows:
            logger.warning(f"No valid windows generated for {instId}")
            return None
        
        logger.info(f"📊 Generated {len(windows)} rolling windows")
        
        # Analyze each window
        window_results = []
        for i, (window_start, window_end) in enumerate(windows):
            logger.info(f"🔍 Analyzing window {i+1}/{len(windows)}: {window_start.strftime('%Y-%m-%d')} to {window_end.strftime('%Y-%m-%d')}")
            
            # Filter data for this window
            window_mask = (datetime_index >= window_start) & (datetime_index <= window_end)
            window_data = data[window_mask]
            
            if len(window_data) < 50:  # Minimum data requirement
                logger.info(f"   ⚠️  Window {i+1} has insufficient data ({len(window_data)} points), skipping")
                continue
            
            # Create a copy of the original data for this window
            window_data_copy = window_data.copy()
            
            # Optimize strategy for this window using parent class method
            try:
                window_result = self._optimize_window(instId, window_data_copy, bar, strategy_type, i+1)
                if window_result:
                    window_results.append(window_result)
                    logger.info(f"   ✅ Window {i+1} optimization successful")
                else:
                    logger.info(f"   ❌ Window {i+1} optimization failed")
            except Exception as e:
                logger.error(f"   ❌ Window {i+1} optimization error: {e}")
                continue
        
        if not window_results:
            logger.warning(f"No successful window optimizations for {instId}")
            return None
        
        # Analyze results across all windows
        analysis_result = self._analyze_window_results(instId, window_results, window_size, step_size)
        
        # Store results in date_dict
        date_dict[instId] = analysis_result
        
        logger.info(f"✅ Rolling window optimization completed for {instId}")
        return date_dict
    
    def _period_to_days(self, period: str) -> int:
        """Convert period string to days"""
        if period == '1m':
            return 30
        elif period == '3m':
            return 90
        elif period == '6m':
            return 180
        elif period == '1y':
            return 365
        else:
            logger.warning(f"Invalid period: {period}. Using 3m (90 days) as default.")
            return 90
    
    def _generate_rolling_windows(self, start_date: datetime, end_date: datetime,
                                window_days: int, step_days: int) -> List[Tuple[datetime, datetime]]:
        """Generate rolling time windows"""
        windows = []
        current_start = start_date
        
        while current_start + timedelta(days=window_days) <= end_date:
            current_end = current_start + timedelta(days=window_days)
            windows.append((current_start, current_end))
            current_start += timedelta(days=step_days)
        
        return windows
    
    def _optimize_window(self, instId: str, window_data: np.ndarray, bar: str,
                        strategy_type: str, window_num: int) -> Optional[Dict[str, Any]]:
        """Optimize strategy for a single time window"""
        try:
            # Get strategy configuration
            config = self._get_strategy_config(strategy_type)
            
            # Extract price data
            datetime_index = window_data[:, 8].astype(np.int64).astype('datetime64[ms]').astype(datetime)
            open_prices = window_data[:, 1].astype(np.float64)
            high_prices = window_data[:, 2].astype(np.float64)
            low_prices = window_data[:, 3].astype(np.float64)
            close_prices = window_data[:, 4].astype(np.float64)
            
            # Validate data
            if len(close_prices) < config['min_trades'] + config['data_offset']:
                return None
            
            # Calculate effective data length
            n = len(close_prices) - config['data_offset']
            if n < config['min_trades']:
                return None
            
            # Calculate earnings matrix for this window
            earn_matrix = self._calculate_earnings_matrix_fully_vectorized(
                datetime_index, low_prices, open_prices, close_prices,
                n, config['min_trades'], config
            )
            
            # Find best parameters for this window
            best_params = self._find_best_parameters(earn_matrix, config['limit_range'][0])
            if best_params is None:
                return None
            
            return {
                'window_num': window_num,
                'data_points': len(close_prices),
                'effective_points': n,
                'best_limit': best_params[0],
                'best_duration': best_params[1],
                'max_returns': best_params[2],
                'window_start': datetime_index[0].strftime('%Y-%m-%d'),
                'window_end': datetime_index[-1].strftime('%Y-%m-%d')
            }
            
        except Exception as e:
            logger.error(f"Window {window_num} optimization error: {e}")
            return None
    
    def _analyze_window_results(self, instId: str, window_results: List[Dict[str, Any]],
                              window_size: str, step_size: str) -> Dict[str, Any]:
        """Analyze results across all windows"""
        
        # Extract key metrics
        limits = [r['best_limit'] for r in window_results]
        durations = [r['best_duration'] for r in window_results]
        returns = [r['max_returns'] for r in window_results]
        
        # Calculate statistics
        avg_limit = np.mean(limits)
        avg_duration = np.mean(durations)
        avg_returns = np.mean(returns)
        
        std_limit = np.std(limits)
        std_duration = np.std(durations)
        std_returns = np.std(returns)
        
        # Find most common parameters (mode)
        limit_counts = {}
        duration_counts = {}
        
        for limit in limits:
            limit_counts[limit] = limit_counts.get(limit, 0) + 1
        
        for duration in durations:
            duration_counts[duration] = duration_counts.get(duration, 0) + 1
        
        most_common_limit = max(limit_counts.items(), key=lambda x: x[1])[0]
        most_common_duration = max(duration_counts.items(), key=lambda x: x[1])[0]
        
        # Calculate parameter stability (lower std = more stable)
        limit_stability = 1 / (1 + std_limit)  # Normalized stability score
        duration_stability = 1 / (1 + std_duration)
        
        # Overall stability score
        overall_stability = (limit_stability + duration_stability) / 2
        
        # Create analysis result
        result = {
            'optimization_method': 'rolling_window',
            'window_size': window_size,
            'step_size': step_size,
            'total_windows': len(window_results),
            'successful_windows': len(window_results),
            'success_rate': 100.0,
            
            # Parameter statistics
            'limit_stats': {
                'average': round(avg_limit, 2),
                'std_dev': round(std_limit, 2),
                'most_common': most_common_limit,
                'stability_score': round(limit_stability, 3)
            },
            'duration_stats': {
                'average': round(avg_duration, 2),
                'std_dev': round(std_duration, 2),
                'most_common': most_common_duration,
                'stability_score': round(duration_stability, 3)
            },
            'returns_stats': {
                'average': round(avg_returns, 3),
                'std_dev': round(std_returns, 3),
                'min': round(min(returns), 3),
                'max': round(max(returns), 3)
            },
            
            # Overall assessment
            'overall_stability': round(overall_stability, 3),
            'recommended_limit': most_common_limit,
            'recommended_duration': most_common_duration,
            'expected_returns': round(avg_returns, 3),
            
            # Detailed window results
            'window_details': window_results
        }
        
        # Add recommendations
        if overall_stability > 0.7:
            result['recommendation'] = 'HIGH_STABILITY'
            result['recommendation_text'] = 'Parameters are very stable across time windows'
        elif overall_stability > 0.5:
            result['recommendation'] = 'MEDIUM_STABILITY'
            result['recommendation_text'] = 'Parameters show moderate stability'
        else:
            result['recommendation'] = 'LOW_STABILITY'
            result['recommendation_text'] = 'Parameters vary significantly across time windows'
        
        return result
