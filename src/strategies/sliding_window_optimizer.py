#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sliding Window Strategy Optimizer
Daily optimization using past 30 days of data for each trading day
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.strategies.strategy_optimizer import StrategyOptimizer
from src.strategies.historical_data_loader import HistoricalDataLoader

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SlidingWindowOptimizer(StrategyOptimizer):
    """Sliding window optimizer that optimizes parameters daily using past 30 days"""
    
    def __init__(self, buy_fee: float = 0.001, sell_fee: float = 0.001, 
                 window_days: int = 30):
        """
        Initialize sliding window optimizer
        
        Args:
            buy_fee: Buy fee per trade
            sell_fee: Sell fee per trade  
            window_days: Number of days to look back for optimization (default: 30)
        """
        super().__init__(buy_fee=buy_fee, sell_fee=sell_fee)
        self.window_days = window_days
        self.data_loader = HistoricalDataLoader()
        
    def optimize_with_sliding_windows(self, instId: str, start: int, end: int,
                                     date_dict: Dict[str, Any], bar: str = "1d",
                                     strategy_type: str = "1d") -> Optional[Dict[str, Any]]:
        """
        Optimize strategy parameters using sliding window approach
        
        Args:
            instId: Cryptocurrency symbol
            start: Start timestamp (0 for all data)
            end: End timestamp (0 for latest data)
            date_dict: Dictionary to store results
            bar: Time bar (1d for daily)
            strategy_type: Strategy type (1d for daily)
            
        Returns:
            Dictionary with optimization results
        """
        try:
            logger.info(f"🔄 Starting sliding window optimization for {instId}")
            logger.info(f"    Window size: {self.window_days} days")
            logger.info(f"    Strategy: Daily optimization using past {self.window_days} days")
            
            # Get historical data
            data = self.data_loader.get_hist_candle_data(instId, start, end, bar)
            if data is None or len(data) == 0:
                logger.error(f"No data available for {instId}")
                return None
                
            # Convert timestamps
            timestamps = data[:, 0].astype(np.int64)
            
            # Debug timestamp info
            first_ts = timestamps[0]
            last_ts = timestamps[-1]
            logger.info(f"🔍 Debug: First timestamp: {first_ts}, Last timestamp: {last_ts}")
            logger.info(f"🔍 Debug: Timestamp type: {type(first_ts)}, Shape: {timestamps.shape}")
            
            # Determine timestamp conversion
            if first_ts > 1e12:  # Milliseconds
                logger.info("🔍 Using millisecond timestamp conversion")
                first_date = datetime.fromtimestamp(first_ts / 1000)
                last_date = datetime.fromtimestamp(last_ts / 1000)
            else:  # Seconds
                logger.info("🔍 Using second timestamp conversion")
                first_date = datetime.fromtimestamp(first_ts)
                last_date = datetime.fromtimestamp(last_ts)
            
            # Ensure correct date order (earliest to latest)
            if first_date > last_date:
                first_date, last_date = last_date, first_date
                logger.info("🔄 Swapped dates to ensure correct chronological order")
                
            logger.info(f"📅 Data range: {first_date.strftime('%Y-%m-%d')} to {last_date.strftime('%Y-%m-%d')}")
            
            # Generate sliding window trading points
            trading_points = self._generate_sliding_trading_points(first_date, last_date)
            
            if not trading_points:
                logger.warning(f"No valid trading points generated for {instId}")
                return None
                
            logger.info(f"📊 Generated {len(trading_points)} trading time points")
            logger.info(f"    Note: Each day uses past {self.window_days} days for optimization")
            
            # Optimize for each trading point
            successful_optimizations = 0
            total_returns = []
            parameter_stability = []
            
            for i, (trading_date, optimization_start, optimization_end) in enumerate(trading_points, 1):
                logger.info(f"🔍 Analyzing trading point {i}/{len(trading_points)}: {trading_date.strftime('%Y-%m-%d')}")
                logger.info(f"    Optimization window: {optimization_start.strftime('%Y-%m-%d')} to {optimization_end.strftime('%Y-%m-%d')}")
                
                # Optimize for this trading point
                result = self._optimize_trading_point(
                    instId, data, timestamps, trading_date, 
                    optimization_start, optimization_end, bar, strategy_type
                )
                
                if result:
                    successful_optimizations += 1
                    total_returns.append(result['max_returns'])
                    parameter_stability.append(result['stability'])
                    logger.info(f"    ✅ Trading point {i} optimization successful")
                else:
                    logger.warning(f"    ❌ Trading point {i} optimization failed")
            
            if successful_optimizations == 0:
                logger.error(f"No successful optimizations for {instId}")
                return None
                
            # Calculate overall metrics
            overall_stability = np.mean(parameter_stability) if parameter_stability else 0.0
            expected_returns = np.mean(total_returns) if total_returns else 1.0
            
            # Store results
            date_dict[instId] = {
                'sliding_window_days': self.window_days,
                'total_trading_points': len(trading_points),
                'successful_optimizations': successful_optimizations,
                'expected_returns': expected_returns,
                'overall_stability': overall_stability,
                'daily_returns': total_returns,
                'parameter_stability': parameter_stability,
                'best_limit': str(int(np.mean([r.get('best_limit', 70) for r in [r for r in [r] if r]]))),
                'best_duration': str(int(np.mean([r.get('best_duration', 10) for r in [r for r in [r] if r]]))),
                'max_returns': str(expected_returns),
                'trade_count': str(successful_optimizations),
                'trades_per_month': str(round(successful_optimizations / (len(trading_points) / 30), 2))
            }
            
            logger.info(f"✅ Sliding window optimization completed for {instId}")
            logger.info(f"    Ready for daily trading with optimized parameters")
            
            return date_dict
            
        except Exception as e:
            logger.error(f"Error in sliding window optimization for {instId}: {e}")
            return None
    
    def _generate_sliding_trading_points(self, earliest_date: datetime, latest_date: datetime) -> List[Tuple[datetime, datetime, datetime]]:
        """
        Generate sliding window trading points - daily optimization
        
        Args:
            earliest_date: Earliest available data date
            latest_date: Latest available data date
            
        Returns:
            List of (trading_date, optimization_start, optimization_end) tuples
        """
        trading_points = []
        
        # Need at least window_days + 1 day for optimization + trading
        if (latest_date - earliest_date).days >= self.window_days + 1:
            # Start from the first day we can optimize (earliest_date + window_days)
            current_trading_date = earliest_date + timedelta(days=self.window_days)
            
            while current_trading_date <= latest_date:
                # Optimization window: past window_days before current trading date
                optimization_end = current_trading_date - timedelta(days=1)
                optimization_start = optimization_end - timedelta(days=self.window_days) + timedelta(days=1)
                
                trading_points.append((current_trading_date, optimization_start, optimization_end))
                
                # Move to next day
                current_trading_date += timedelta(days=1)
            
            logger.info(f"📊 Generated {len(trading_points)} daily trading points for {self.window_days}-day sliding window")
            if trading_points:
                logger.info(f"   First optimization: {trading_points[0][1].strftime('%Y-%m-%d')} to {trading_points[0][2].strftime('%Y-%m-%d')}")
                logger.info(f"   Last optimization: {trading_points[-1][1].strftime('%Y-%m-%d')} to {trading_points[-1][2].strftime('%Y-%m-%d')}")
                logger.info(f"   Logic: Each day uses previous {self.window_days} days to optimize for current day")
        else:
            logger.warning(f"Insufficient data for {self.window_days}-day sliding window optimization")
        
        return trading_points
    
    def _optimize_trading_point(self, instId: str, data: np.ndarray, timestamps: np.ndarray,
                               trading_date: datetime, optimization_start: datetime, 
                               optimization_end: datetime, bar: str, strategy_type: str) -> Optional[Dict[str, Any]]:
        """
        Optimize parameters for a specific trading point
        
        Args:
            instId: Cryptocurrency symbol
            data: Historical candlestick data
            timestamps: Timestamp array
            trading_date: Date for trading
            optimization_start: Start of optimization window
            optimization_end: End of optimization window
            bar: Time bar
            strategy_type: Strategy type
            
        Returns:
            Optimization result dictionary
        """
        try:
            # Convert dates to timestamps for data filtering
            if timestamps[0] > 1e12:  # Milliseconds
                opt_start_ts = int(optimization_start.timestamp() * 1000)
                opt_end_ts = int(optimization_end.timestamp() * 1000)
            else:  # Seconds
                opt_start_ts = int(optimization_start.timestamp())
                opt_end_ts = int(optimization_end.timestamp())
            
            # Filter data for optimization window
            mask = (timestamps >= opt_start_ts) & (timestamps <= opt_end_ts)
            optimization_data = data[mask]
            
            if len(optimization_data) == 0:
                logger.warning(f"No data in optimization window for {trading_date.strftime('%Y-%m-%d')}")
                return None
            
            logger.info(f"⏰ Time filtering: {len(optimization_data)} valid time points out of {len(data)}")
            
            # Calculate earnings matrix
            # Use default config for limit and duration ranges
            config = {
                'limit_range': (60, 95),
                'duration_range': (1, 30)
            }
            logger.info(f"💰 Calculating earnings matrix: {config['limit_range'][1] - config['limit_range'][0]} limit ratios × {config['duration_range'][1] - config['duration_range'][0]} durations")
            
            earn_matrix = self._calculate_earnings_matrix(
                optimization_data, None, None, None
            )
            
            if earn_matrix is None or np.all(earn_matrix == 0):
                logger.warning(f"No valid earnings calculated for {trading_date.strftime('%Y-%m-%d')}")
                return None
            
            # Find best parameters
            best_params = self._find_best_parameters(earn_matrix)
            if best_params is None:
                return None
            
            best_limit, best_duration, max_returns = best_params
            
            # Calculate stability (how much parameters vary)
            stability = self._calculate_parameter_stability(earn_matrix, best_limit, best_duration)
            
            return {
                'best_limit': best_limit,
                'best_duration': best_duration,
                'max_returns': max_returns,
                'stability': stability,
                'trading_date': trading_date,
                'optimization_start': optimization_start,
                'optimization_end': optimization_end
            }
            
        except Exception as e:
            logger.error(f"Error optimizing trading point {trading_date.strftime('%Y-%m-%d')}: {e}")
            return None
    
    def _calculate_parameter_stability(self, earn_matrix: np.ndarray, best_limit_idx: int, best_duration_idx: int) -> float:
        """
        Calculate parameter stability based on earnings matrix
        
        Args:
            earn_matrix: Earnings matrix
            best_limit_idx: Best limit ratio index
            best_duration_idx: Best duration index
            
        Returns:
            Stability score (lower = more stable)
        """
        try:
            # Get earnings around the best parameters
            limit_range = max(1, min(3, earn_matrix.shape[0] // 10))
            duration_range = max(1, min(3, earn_matrix.shape[1] // 10))
            
            start_limit = max(0, best_limit_idx - limit_range)
            end_limit = min(earn_matrix.shape[0], best_limit_idx + limit_range + 1)
            start_duration = max(0, best_duration_idx - duration_range)
            end_duration = min(earn_matrix.shape[1], best_duration_idx + duration_range + 1)
            
            # Calculate variance in the neighborhood
            neighborhood = earn_matrix[start_limit:end_limit, start_duration:end_duration]
            if neighborhood.size > 0:
                variance = np.var(neighborhood)
                stability = 1.0 / (1.0 + variance)  # Higher variance = lower stability
                return stability
            
            return 0.5  # Default stability
            
        except Exception as e:
            logger.warning(f"Error calculating stability: {e}")
            return 0.5
