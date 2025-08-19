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
        Optimize strategy using rolling time windows for forward-looking trading
        
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
            Dictionary with rolling window optimization results for forward-looking trading
        """
        logger.info(f"🔄 Starting rolling window optimization for {instId}")
        logger.info(f"   Window size: {window_size}, Step size: {step_size}")
        logger.info(f"   Strategy: Forward-looking trading using past data to optimize future parameters")
        
        # Get all historical data
        data = self.data_loader.get_hist_candle_data(instId, start, end, bar)
        if data is None or len(data) == 0:
            logger.warning(f"No data available for {instId}")
            return None
        
        # Convert timestamps to datetime for easier manipulation
        timestamps = data[:, 0].astype(np.int64)  # Column 0 is timestamp, not column 8
        
        # Debug: Check timestamp values
        logger.info(f"🔍 Debug: First timestamp: {timestamps[0]}, Last timestamp: {timestamps[-1]}")
        logger.info(f"🔍 Debug: Timestamp type: {type(timestamps[0])}, Shape: {timestamps.shape}")
        
        # Handle different timestamp formats
        try:
            # Try milliseconds first (most common)
            if timestamps[0] > 1e12:  # Likely milliseconds
                datetime_index = np.array([datetime.fromtimestamp(ts/1000) for ts in timestamps])
                logger.info(f"🔍 Using millisecond timestamp conversion")
            else:  # Likely seconds
                datetime_index = np.array([datetime.fromtimestamp(ts) for ts in timestamps])
                logger.info(f"🔍 Using second timestamp conversion")
        except Exception as e:
            logger.error(f"Timestamp conversion error: {e}")
            # Fallback: try to parse as string or other format
            try:
                datetime_index = np.array([datetime.fromisoformat(str(ts)) for ts in timestamps])
                logger.info(f"🔍 Using string timestamp conversion")
            except Exception as e2:
                logger.error(f"All timestamp conversion methods failed: {e2}")
                return None
        
        # Calculate window and step sizes in days
        window_days = self._period_to_days(window_size)
        step_days = self._period_to_days(step_size)
        
        # Find the earliest and latest dates
        earliest_date = np.min(datetime_index)
        latest_date = np.max(datetime_index)
        
        logger.info(f"📅 Data range: {earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')}")
        
        # Generate trading time points (starting from window_size after earliest date)
        trading_points = self._generate_trading_points(earliest_date, latest_date, window_days, step_days)
        
        if not trading_points:
            logger.warning(f"No valid trading points generated for {instId}")
            return None
        
        logger.info(f"📊 Generated {len(trading_points)} trading time points")
        logger.info(f"   Note: First {window_size} of data used only for parameter optimization")
        
        # Analyze each trading point
        trading_results = []
        for i, (trading_date, optimization_start, optimization_end) in enumerate(trading_points):
            logger.info(f"🔍 Analyzing trading point {i+1}/{len(trading_points)}: {trading_date.strftime('%Y-%m-%d')}")
            logger.info(f"   Optimization window: {optimization_start.strftime('%Y-%m-%d')} to {optimization_end.strftime('%Y-%m-%d')}")
            
            # Filter data for optimization window (past data only)
            optimization_mask = (datetime_index >= optimization_start) & (datetime_index <= optimization_end)
            optimization_data = data[optimization_mask]
            
            if len(optimization_data) < 50:  # Minimum data requirement
                logger.info(f"   ⚠️  Trading point {i+1} has insufficient optimization data ({len(optimization_data)} points), skipping")
                continue
            
            # Optimize strategy for this optimization window
            try:
                trading_result = self._optimize_trading_point(
                    instId, optimization_data, bar, strategy_type, i+1,
                    trading_date, optimization_start, optimization_end
                )
                if trading_result:
                    trading_results.append(trading_result)
                    logger.info(f"   ✅ Trading point {i+1} optimization successful")
                else:
                    logger.info(f"   ❌ Trading point {i+1} optimization failed")
            except Exception as e:
                logger.error(f"   ❌ Trading point {i+1} optimization error: {e}")
                continue
        
        if not trading_results:
            logger.warning(f"No successful trading point optimizations for {instId}")
            return None
        
        # Analyze results across all trading points
        analysis_result = self._analyze_trading_results(instId, trading_results, window_size, step_size)
        
        # Store results in date_dict
        date_dict[instId] = analysis_result
        
        # Also add the traditional format fields for compatibility
        date_dict[instId].update({
            'best_limit': str(analysis_result['recommended_limit']),
            'best_duration': str(analysis_result['recommended_duration']),
            'max_returns': str(analysis_result['expected_returns']),
            'trade_count': str(analysis_result['total_trading_points']),
            'trades_per_month': str(round(analysis_result['total_trading_points'] / 12, 2))  # Convert to monthly frequency
        })
        
        logger.info(f"✅ Rolling window optimization completed for {instId}")
        logger.info(f"   Ready for forward-looking trading with optimized parameters")
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
    
    def _generate_trading_points(self, earliest_date: datetime, latest_date: datetime,
                                window_days: int, step_days: int) -> List[Tuple[datetime, datetime, datetime]]:
        """Generate trading time points for rolling monthly optimization"""
        trading_points = []
        
        # For rolling monthly backtest: generate multiple trading points
        # Each month uses the previous 3 months for optimization
        if (latest_date - earliest_date).days >= window_days + 90:  # Need at least window_days + 3 months
            current_date = earliest_date + timedelta(days=window_days)  # Start from month 4
            
            while current_date <= latest_date:
                # Optimization window: previous 3 months
                optimization_end = current_date - timedelta(days=1)
                optimization_start = optimization_end - timedelta(days=window_days) + timedelta(days=1)
                
                # Trading period: current month
                trading_date = current_date
                
                trading_points.append((trading_date, optimization_start, optimization_end))
                
                # Move to next month
                current_date += timedelta(days=30)
            
            logger.info(f"📊 Generated {len(trading_points)} trading points for {window_days}-day rolling monthly optimization")
            if trading_points:
                logger.info(f"   First optimization: {trading_points[0][1].strftime('%Y-%m-%d')} to {trading_points[0][2].strftime('%Y-%m-%d')}")
                logger.info(f"   Last optimization: {trading_points[-1][1].strftime('%Y-%m-%d')} to {trading_points[-1][2].strftime('%Y-%m-%d')}")
                logger.info(f"   Logic: Each month uses previous {window_days//30} months to optimize for current month")
        else:
            logger.warning(f"Insufficient data for {window_days}-day rolling monthly optimization")
        
        return trading_points
    
    def _optimize_trading_point(self, instId: str, optimization_data: np.ndarray, bar: str,
                                strategy_type: str, trading_point_num: int,
                                trading_date: datetime, optimization_start: datetime, optimization_end: datetime) -> Optional[Dict[str, Any]]:
        """Optimize strategy for a single trading point (forward-looking)"""
        try:
            # Get strategy configuration
            config = self._get_strategy_config(strategy_type)
            
            # Extract price data for the optimization window
            datetime_index = optimization_data[:, 8].astype(np.int64).astype('datetime64[ms]').astype(datetime)
            open_prices = optimization_data[:, 1].astype(np.float64)
            high_prices = optimization_data[:, 2].astype(np.float64)
            low_prices = optimization_data[:, 3].astype(np.float64)
            close_prices = optimization_data[:, 4].astype(np.float64)
            
            # Validate data
            if len(close_prices) < config['min_trades'] + config['data_offset']:
                return None
            
            # Calculate effective data length
            n = len(close_prices) - config['data_offset']
            if n < config['min_trades']:
                return None
            
            # Calculate earnings matrix for this optimization window
            earn_matrix = self._calculate_earnings_matrix_fully_vectorized(
                datetime_index, low_prices, open_prices, close_prices,
                n, config['min_trades'], config
            )
            
            # Find best parameters for this optimization window
            best_params = self._find_best_parameters(earn_matrix, config['limit_range'][0])
            if best_params is None:
                return None
            
            return {
                'trading_point_num': trading_point_num,
                'trading_date': trading_date.strftime('%Y-%m-%d'),
                'optimization_start': optimization_start.strftime('%Y-%m-%d'),
                'optimization_end': optimization_end.strftime('%Y-%m-%d'),
                'data_points': len(close_prices),
                'effective_points': n,
                'best_limit': best_params[0],
                'best_duration': best_params[1],
                'max_returns': best_params[2]
            }
            
        except Exception as e:
            logger.error(f"Trading point {trading_point_num} optimization error: {e}")
            return None
    
    def _analyze_trading_results(self, instId: str, trading_results: List[Dict[str, Any]],
                               window_size: str, step_size: str) -> Dict[str, Any]:
        """Analyze results across all trading points for forward-looking trading"""
        
        # Extract key metrics
        limits = [r['best_limit'] for r in trading_results]
        durations = [r['best_duration'] for r in trading_results]
        returns = [r['max_returns'] for r in trading_results]
        
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
            'optimization_method': 'rolling_window_forward_looking',
            'window_size': window_size,
            'step_size': step_size,
            'total_trading_points': len(trading_results),
            'successful_trading_points': len(trading_results),
            'success_rate': 100.0,
            'trading_start_date': trading_results[0]['trading_date'] if trading_results else None,
            'trading_end_date': trading_results[-1]['trading_date'] if trading_results else None,
            
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
            
            # Trading strategy info
            'trading_strategy': f"Use past {window_size} data to optimize parameters for next {step_size} trading period",
            'data_usage': f"First {window_size} of data used only for parameter optimization, trading starts from {trading_results[0]['trading_date'] if trading_results else 'N/A'}",
            
            # Detailed trading point results
            'trading_point_details': trading_results
        }
        
        # Add recommendations
        if overall_stability > 0.7:
            result['recommendation'] = 'HIGH_STABILITY'
            result['recommendation_text'] = 'Parameters are very stable across trading points - reliable for forward-looking trading'
        elif overall_stability > 0.5:
            result['recommendation'] = 'MEDIUM_STABILITY'
            result['recommendation_text'] = 'Parameters show moderate stability - consider regular re-optimization'
        else:
            result['recommendation'] = 'LOW_STABILITY'
            result['recommendation_text'] = 'Parameters vary significantly - high risk, frequent re-optimization needed'
        
        return result
