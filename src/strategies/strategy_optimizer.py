#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy Optimizer for OKX Trading
Strategy parameter optimizer, responsible for optimizing buy price and holding time combinations
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Literal
import numpy as np

from .historical_data_loader import get_historical_data_loader

# Configure logging
logger = logging.getLogger(__name__)

class StrategyOptimizer:
    """Strategy optimizer, responsible for optimizing trading strategy parameter combinations"""
    
    def __init__(self, buy_fee: float = 0.001, sell_fee: float = 0.001):
        self.data_loader = get_historical_data_loader()
        self.custom_fees = {
            'buy_fee': buy_fee,
            'sell_fee': sell_fee
        }
        
        # Initialize strategy configurations as instance variables
        self.strategy_configs = {
            "1d": {
                'limit_range': (60, 95),
                'duration_range': 30,
                'min_trades': 30,        # Minimum 30 trades for statistical significance
                'min_avg_earn': 1.005, # Minimum 0.5% return requirement (was 1.01 = 1%!)
                'data_offset': 50,       # Reduced for daily data (was 200)
                'buy_fee': self.custom_fees['buy_fee'],   # Use custom buy fee
                'sell_fee': self.custom_fees['sell_fee']  # Use custom sell fee
            }
        }
    
    def set_trading_fees(self, buy_fee: float, sell_fee: float):
        """Set custom trading fees for strategy optimization"""
        self.custom_fees['buy_fee'] = buy_fee
        self.custom_fees['sell_fee'] = sell_fee
        logger.info(f"Updated trading fees: buy={buy_fee:.3f}, sell={sell_fee:.3f}")
    
    def set_strategy_parameters(self, strategy_type: str, 
                               limit_range: tuple = None, 
                               duration_range: int = None,
                               min_trades: int = None,
                               min_avg_earn: float = None):
        """Set custom strategy parameters for optimization
        
        Args:
            strategy_type: Strategy type ("1d")
            limit_range: Custom limit range tuple (min, max) e.g., (70, 90)
            duration_range: Custom duration range (max days)
            min_trades: Minimum number of trades required
            min_avg_earn: Minimum average earnings requirement
        """
        if strategy_type not in ["1d"]:
            logger.error(f"Invalid strategy type: {strategy_type}. Must be '1d'")
            return
            
        # Get current config from instance variable
        current_config = self.strategy_configs[strategy_type]
        
        # Update parameters if provided
        if limit_range is not None:
            if len(limit_range) == 2 and 0 < limit_range[0] < limit_range[1] <= 100:
                current_config['limit_range'] = limit_range
                logger.info(f"✅ Updated {strategy_type} limit_range: {limit_range}")
            else:
                logger.error(f"❌ Invalid limit_range: {limit_range}. Must be (min, max) where 0 < min < max <= 100")
                
        if duration_range is not None:
            if duration_range > 0:
                current_config['duration_range'] = duration_range
                logger.info(f"✅ Updated {strategy_type} duration_range: {duration_range}")
            else:
                logger.error(f"❌ Invalid duration_range: {duration_range}. Must be > 0")
                
        if min_trades is not None:
            if min_trades > 0:
                current_config['min_trades'] = min_trades
                logger.info(f"✅ Updated {strategy_type} min_trades: {min_trades}")
            else:
                logger.error(f"❌ Invalid min_trades: {min_trades}. Must be > 0")
                
        if min_avg_earn is not None:
            if min_avg_earn > 1.0:
                current_config['min_avg_earn'] = min_avg_earn
                logger.info(f"✅ Updated {strategy_type} min_avg_earn: {min_avg_earn}")
            else:
                logger.error(f"❌ Invalid min_avg_earn: {min_avg_earn}. Must be > 1.0")
    
    def get_strategy_parameters(self, strategy_type: str) -> Dict[str, Any]:
        """Get current strategy parameters
        
        Args:
            strategy_type: Strategy type ("1d")
            
        Returns:
            Dictionary with current strategy parameters
        """
        if strategy_type not in ["1d"]:
            logger.error(f"Invalid strategy type: {strategy_type}. Must be '1d'")
            return {}
            
        config = self._get_strategy_config(strategy_type)
        return {
            'limit_range': config['limit_range'],
            'duration_range': config['duration_range'],
            'min_trades': config['min_trades'],
            'min_avg_earn': config['min_avg_earn']
        }
    
    def reset_strategy_parameters(self, strategy_type: str):
        """Reset strategy parameters to default values
        
        Args:
            strategy_type: Strategy type ("1d")
        """
        if strategy_type not in ["1d"]:
            logger.error(f"Invalid strategy type: {strategy_type}. Must be '1d'")
            return
            
        # Reset to default configuration
        default_configs = {
            "1d": {
                'limit_range': (60, 95),
                'duration_range': 30,
                'min_trades': 30,
                'min_avg_earn': 1.005,
                'data_offset': 50,
                'buy_fee': self.custom_fees['buy_fee'],
                'sell_fee': self.custom_fees['sell_fee']
            }
        }
        
        # Update the config with default values
        config = self.strategy_configs[strategy_type]
        config.update(default_configs[strategy_type])
        logger.info(f"✅ Reset {strategy_type} strategy parameters to defaults")
    
    def set_all_strategy_parameters(self, 
                                   limit_range: tuple = None, 
                                   duration_range: int = None,
                                   min_trades: int = None,
                                   min_avg_earn: float = None):
        """Set parameters for daily strategy
        
        Args:
            limit_range: Custom limit range tuple (min, max) e.g., (70, 90)
            duration_range: Custom duration range (max days)
            min_trades: Minimum number of trades required
            min_avg_earn: Minimum average earnings requirement
        """
        logger.info("🔄 Setting parameters for daily strategy...")
        
        # Set for 1d strategy
        self.set_strategy_parameters("1d", limit_range, duration_range, min_trades, min_avg_earn)
        
        logger.info("✅ Parameters set for daily strategy")
    
    def print_strategy_parameters(self, strategy_type: str = None):
        """Print current strategy parameters
        
        Args:
            strategy_type: Strategy type ("1d", or None for default)
        """
        if strategy_type is None:
            # Print daily strategy
            print("📊 Current Strategy Parameters:")
            print("=" * 50)
            self.print_strategy_parameters("1d")
            return
            
        if strategy_type not in ["1d"]:
            logger.error(f"Invalid strategy type: {strategy_type}. Must be '1d'")
            return
            
        config = self._get_strategy_config(strategy_type)
        print(f"🔧 {strategy_type.upper()} Strategy Parameters:")
        print(f"   Limit Range: {config['limit_range'][0]}% - {config['limit_range'][1]}%")
        print(f"   Duration Range: 1 - {config['duration_range']} days")
        print(f"   Min Trades: {config['min_trades']}")
        print(f"   Min Avg Earnings: {config['min_avg_earn']:.3f}x")
    
    def get_trading_fees(self) -> Dict[str, float]:
        """Get current trading fee configuration"""
        return self.custom_fees.copy()
    
    def optimize_strategy(self, instId: str, start: int, end: int, 
                         date_dict: Dict[str, Any], bar: str, 
                         strategy_type: Literal["1d"] = "1d") -> Optional[Dict[str, Any]]:
        """Optimize strategy parameters - daily strategy optimization"""
        data = self.data_loader.get_hist_candle_data(instId, start, end, bar)
        if data is None or len(data) == 0:
            logger.warning(f"No data available for {instId}")
            return None

        # Data preprocessing - vectorized operations with validation
        try:
            # Convert timestamps to datetime objects
            # For daily data, we need to handle the case where we only have date information
            timestamps = data[:, 0].astype(np.int64)
            
            # Daily data - convert to date objects (no time components)
            datetime_index = np.array([datetime.fromtimestamp(ts / 1000).date() for ts in timestamps])
            logger.info(f"📅 Daily data detected for {instId} - converting to date objects")
            open_prices = data[:, 1].astype(np.float64)  # Column 1: open
            high_prices = data[:, 2].astype(np.float64)  # Column 2: high
            low_prices = data[:, 3].astype(np.float64)  # Column 3: low
            close_prices = data[:, 4].astype(np.float64) # Column 4: close
            
            # Validate price data sanity
            if np.any(open_prices <= 0) or np.any(high_prices <= 0) or np.any(low_prices <= 0) or np.any(close_prices <= 0):
                logger.error(f"Invalid price data for {instId}: prices must be positive")
                return None
                
            if np.any(high_prices < low_prices) or np.any(high_prices < open_prices) or np.any(high_prices < close_prices):
                logger.error(f"Invalid price relationships for {instId}: high must be >= low, open, close")
                return None
                
            if np.any(low_prices > open_prices) or np.any(low_prices > close_prices):
                logger.error(f"Invalid price relationships for {instId}: low must be <= open, close")
                return None
            
            # Check for extreme price values that might cause calculation errors
            max_price = np.max([np.max(open_prices), np.max(high_prices), np.max(low_prices), np.max(close_prices)])
            min_price = np.min([np.min(open_prices), np.min(high_prices), np.min(low_prices), np.min(close_prices)])
            
            if max_price > 1e8 or min_price < 1e-8:
                logger.warning(f"Extreme price values for {instId}: min={min_price}, max={max_price}")
                
        except Exception as e:
            logger.error(f"Data preprocessing error for {instId}: {e}")
            return None

        # Strategy-specific configuration
        config = self._get_strategy_config(strategy_type)
        
        # Calculate effective data length and minimum trade count
        n = len(close_prices) - config['data_offset']
        logger.info(f"📊 {instId}: Total data={len(close_prices)}, offset={config['data_offset']}, effective={n}")
        if n < config['min_trades']:
            logger.warning(f"Insufficient data for {instId}: {n} < {config['min_trades']}")
            return None
            
        min_occurrences = config['min_trades']  # Simplified: use min_trades directly
        logger.info(f"📊 {instId}: Required min_trades={min_occurrences}")

        # Fully vectorized earnings calculation
        try:
            earn_matrix = self._calculate_earnings_matrix_fully_vectorized(
                datetime_index, low_prices, open_prices, close_prices, 
                n, min_occurrences, config
            )
        except Exception as e:
            logger.error(f"Earnings calculation error for {instId}: {e}")
            return None

        # Find best parameter combination
        logger.info(f"🔍 Finding best parameters from earnings matrix shape: {earn_matrix.shape}")
        best_params = self._find_best_parameters(earn_matrix, config['limit_range'][0])
        if best_params is None:
            logger.warning(f"❌ No valid parameters found for {instId} - all earnings <= 0")
            return None
        else:
            logger.info(f"✅ Found best parameters for {instId}: limit={best_params[0]}%, duration={best_params[1]}, returns={best_params[2]}")

        # Update result dictionary
        self._update_result_dict(date_dict, instId, best_params, earn_matrix, config['limit_range'][0], datetime_index)
        return date_dict
    
    def optimize_1d_strategy(self, instId: str, start: int, end: int, 
                            date_dict: Dict[str, Any], bar: str) -> Optional[Dict[str, Any]]:
        """Optimize 1-day strategy parameters - returns best limit ratio and holding time"""
        return self.optimize_strategy(instId, start, end, date_dict, bar, "1d")
    

    
    def _get_strategy_config(self, strategy_type: str) -> Dict[str, Any]:
        """Get configuration for specific strategy type"""
        return self.strategy_configs[strategy_type]
    
    def _calculate_earnings_matrix_fully_vectorized(self, datetime_index: np.ndarray, 
                                                  low_prices: np.ndarray, 
                                                  open_prices: np.ndarray,
                                                  close_prices: np.ndarray, 
                                                  n: int, min_occurrences: int,
                                                  config: Dict[str, Any]) -> np.ndarray:
        """Calculate earnings matrix using fully vectorized operations for maximum performance"""
        limit_range = config['limit_range']
        duration_range = config['duration_range']
        min_avg_earn = config['min_avg_earn']
        
        # Vectorized time filtering - much faster than list comprehension
        valid_time_mask = self._create_time_mask_vectorized(datetime_index[:n], config)
        valid_time_indices = np.where(valid_time_mask)[0]
        
        logger.info(f"⏰ Time filtering: {len(valid_time_indices)} valid time points out of {n}")
        
        if len(valid_time_indices) < min_occurrences:
            logger.warning(f"❌ Not enough valid time points: {len(valid_time_indices)} < {min_occurrences}")
            return np.zeros((limit_range[1] - limit_range[0] + 1, duration_range))
        
        # Pre-calculate all possible buy prices efficiently using broadcasting
        # Ensure we include the upper bound of the range
        limit_ratios = np.arange(limit_range[0], limit_range[1] + 1)
        
        # Calculate earnings matrix using vectorized operations
        earn_matrix = np.zeros((len(limit_ratios), duration_range))
        logger.info(f"💰 Calculating earnings matrix: {len(limit_ratios)} limit ratios × {duration_range} durations")
        
        # Process in batches to balance memory usage and performance
        batch_size = 10  # Process 10 limit ratios at a time
        total_valid_trades = 0
        for batch_start in range(0, len(limit_ratios), batch_size):
            batch_end = min(batch_start + batch_size, len(limit_ratios))
            batch_ratios = limit_ratios[batch_start:batch_end]
            
            # Calculate buy prices for this batch
            buy_prices_batch = (batch_ratios[:, np.newaxis] * open_prices[:n]) / 100
            
            # Vectorized trade finding and earnings calculation for this batch
            batch_earnings = self._calculate_batch_earnings_vectorized(
                valid_time_indices, low_prices[:n], buy_prices_batch, 
                close_prices[:n], duration_range, min_avg_earn
            )
            
            earn_matrix[batch_start:batch_end, :] = batch_earnings
            
            # Count non-zero earnings as a proxy for valid trades
            batch_valid = np.count_nonzero(batch_earnings)
            total_valid_trades += batch_valid
            logger.info(f"💰 Batch {batch_start//batch_size + 1}: {batch_valid} valid earnings calculated")
        
        logger.info(f"💰 Total valid earnings: {total_valid_trades}")
        logger.info(f"💰 Earnings matrix max: {np.max(earn_matrix)}, min: {np.min(earn_matrix)}")
        
        return earn_matrix
    
    def _create_time_mask_vectorized(self, datetime_array: np.ndarray, config: Dict[str, Any]) -> np.ndarray:
        """Create time mask using vectorized operations for better performance"""
        
        # Daily data - all days are valid trading days
        # Return all True to allow trading on any day
        logger.debug(f"📅 Daily data detected - all {len(datetime_array)} days are valid trading days")
        return np.ones(len(datetime_array), dtype=bool)
    
    def _calculate_batch_earnings_vectorized(self, valid_time_indices: np.ndarray, 
                                           low_prices: np.ndarray, 
                                           buy_prices_batch: np.ndarray,
                                           close_prices: np.ndarray, 
                                           duration_range: int,
                                           min_avg_earn: float) -> np.ndarray:
        """Calculate earnings for a batch of limit ratios using fully vectorized operations"""
        batch_size = buy_prices_batch.shape[0]
        earn_matrix = np.zeros((batch_size, duration_range))
        
        # Vectorized trade finding for all limit ratios in batch
        for ratio_idx in range(batch_size):
            buy_prices = buy_prices_batch[ratio_idx]
            
            # Find valid trades using vectorized operations
            valid_trades = self._find_valid_trades_optimized(
                valid_time_indices, low_prices, buy_prices
            )
            
            if len(valid_trades) == 0:
                logger.debug(f"🔍 No valid trades found for ratio {ratio_idx + 60}%")
                continue
            else:
                logger.debug(f"🔍 Found {len(valid_trades)} valid trades for ratio {ratio_idx + 60}%")
            
            # Calculate earnings for all durations at once
            earnings = self._calculate_duration_earnings_vectorized(
                valid_trades, buy_prices, close_prices, duration_range, 
                min_avg_earn
            )
            
            earn_matrix[ratio_idx, :] = earnings
        
        return earn_matrix
    
    def _find_valid_trades_optimized(self, valid_time_indices: np.ndarray, 
                                   low_prices: np.ndarray, buy_prices: np.ndarray) -> list:
        """Find valid trading opportunities for daily trading"""
        if len(valid_time_indices) == 0:
            return []
        
        valid_trades = []
        
        # For daily trading: check if we can buy at the limit price on any given day
        # We check if the low price of the day is below our buy price
        for i in valid_time_indices:
            buy_price = buy_prices[i]
            
            # Can we buy on this day? (low price <= buy price)
            if low_prices[i] <= buy_price:
                valid_trades.append((i, 0))  # 0 means buy at the start of the day
        
        logger.debug(f"🔍 Found {len(valid_trades)} valid trades out of {len(valid_time_indices)} checked days")
        
        return valid_trades
    

    
    def _calculate_duration_earnings_vectorized(self, valid_trades: list, 
                                             buy_prices: np.ndarray, 
                                             close_prices: np.ndarray, 
                                             duration_range: int,
                                             min_avg_earn: float) -> np.ndarray:
        """Calculate earnings for all durations using optimized vectorized operations"""
        if not valid_trades:
            return np.zeros(duration_range)
        
        # Pre-allocate arrays for better memory efficiency
        earnings_matrix = np.zeros((len(valid_trades), duration_range))
        
        # Vectorized calculation for all trades and durations
        for trade_idx, (start_idx, buy_timing) in enumerate(valid_trades):
            # Calculate all durations for this trade at once
            # For daily trading: sell after 0, 1, 2, 3... days (0 = same day)
            end_indices = start_idx + np.arange(0, duration_range)
            
            # Filter valid end indices
            valid_mask = end_indices < len(close_prices)
            if not np.any(valid_mask):
                continue
            
            # Vectorized price calculations
            buy_price = buy_prices[start_idx]
            sell_prices = close_prices[end_indices[valid_mask]]
            durations = np.arange(duration_range)[valid_mask]
            
            # Correct fee calculation for trading
            # Step 1: Buy with fee - we get less shares due to buy fee
            # effective_buy_price = buy_price / (1 - buy_fee) 
            # Step 2: Sell with fee - we get less money due to sell fee
            # net_sell_price = sell_price * (1 - sell_fee)
            # Step 3: Calculate return = net_sell_price / effective_buy_price - 1
            
            buy_fee = self.custom_fees['buy_fee']
            sell_fee = self.custom_fees['sell_fee']
            
            # Correct fee calculation
            effective_buy_price = buy_price / (1 - buy_fee)  # We pay more due to buy fee
            net_sell_price = sell_prices * (1 - sell_fee)   # We receive less due to sell fee
            raw_returns = net_sell_price / effective_buy_price - 1
            
            # Use corrected returns directly
            corrected_returns = raw_returns
            
            # Debug earnings calculation
            if trade_idx < 3:  # Only log first few trades
                logger.debug(f"💰 Trade {trade_idx}: buy_price={buy_price:.2f}, sell_prices={sell_prices[:3]}, raw_returns={raw_returns[:3]}, corrected_returns={corrected_returns[:3]}")
            
            # Convert corrected returns to earnings multipliers (1 + return_rate)
            # Round individual earnings to 3 decimal places
            earn_rates = np.round(1 + corrected_returns, 3)
            earnings_matrix[trade_idx, valid_mask] = earn_rates
        
        # Apply filtering and calculate compound returns INCLUDING losses
        valid_earnings = earnings_matrix > 0  # All trades with valid earnings (including losses)
        
        logger.debug(f"💰 Earnings matrix shape: {earnings_matrix.shape}")
        logger.debug(f"💰 Earnings matrix sample: {earnings_matrix[:3, :5] if earnings_matrix.size > 0 else 'empty'}")
        logger.debug(f"💰 Valid earnings count: {np.count_nonzero(valid_earnings)}")
        
        if not np.any(valid_earnings):
            logger.debug(f"💰 No valid earnings found, returning zeros")
            return np.zeros(duration_range)
        
        # Calculate total compound returns for each duration INCLUDING LOSSES - this is the realistic metric
        # Total compound returns represent the cumulative growth when reinvesting all profits AND accounting for losses
        # For example: if you have trades with 1.1x, 0.9x, 1.2x returns:
        # Total compound return = 1.1 × 0.9 × 1.2 = 1.188 (18.8% total growth despite one loss)
        total_returns = np.zeros(duration_range)
        for duration_idx in range(duration_range):
            duration_earnings = earnings_matrix[:, duration_idx]
            valid_mask = duration_earnings > 0  # All valid trades (including losses)
            if np.any(valid_mask):
                # Calculate total compound return (product of ALL earnings including losses)
                all_earnings = duration_earnings[valid_mask]
                total_compound_return = np.prod(all_earnings)
                total_returns[duration_idx] = total_compound_return
                
                profit_count = np.sum(all_earnings > 1.0)
                loss_count = np.sum(all_earnings <= 1.0)
                logger.debug(f"💰 Duration {duration_idx}: Total compound return={total_compound_return:.4f} from {len(all_earnings)} trades ({profit_count} profits, {loss_count} losses)")
            else:
                total_returns[duration_idx] = 0.0
        
        # Apply minimum total return filter
        valid_mask = total_returns >= min_avg_earn
        logger.debug(f"💰 min_avg_earn filter: {min_avg_earn}, total_returns range: [{np.min(total_returns):.4f}, {np.max(total_returns):.4f}]")
        logger.debug(f"💰 Passed min_avg_earn filter: {np.count_nonzero(valid_mask)} out of {len(valid_mask)}")
        
        # Use total compound returns for final results - this represents actual cumulative growth
        filtered_returns = np.where(valid_mask, total_returns, 0.0)
        
        # Apply proper rounding: round to 2 decimal places for compound returns
        # np.round() already does proper rounding (0.5 rounds up, 0.4 rounds down)
        rounded_returns = np.round(filtered_returns, 2)
        
        logger.debug(f"💰 Using TOTAL COMPOUND RETURNS for final results - representing actual cumulative growth")
        logger.debug(f"💰 Returns rounded to 2 decimal places with proper rounding: range [{np.min(rounded_returns):.2f}, {np.max(rounded_returns):.2f}]")
        return rounded_returns
    
    def _find_best_parameters(self, earn_matrix: np.ndarray, limit_offset: int) -> Optional[Tuple[int, int, float]]:
        """Find best parameter combination from returns matrix
        
        Returns the best limit and duration combination with:
        1. Returns rounded to 2 decimal places
        2. When returns are equal, prefer shorter duration
        """
        max_returns = np.max(earn_matrix)
        if max_returns <= 0:
            return None
        
        # Round returns to 2 decimal places with proper rounding for consistent comparison
        # np.round() applies proper rounding: 0.5 rounds up, 0.4 rounds down
        earn_matrix_rounded = np.round(earn_matrix, 2)
        max_returns_rounded = np.max(earn_matrix_rounded)
        
        # Find all positions with maximum returns (rounded)
        max_positions = np.where(earn_matrix_rounded == max_returns_rounded)
        max_limit_indices = max_positions[0]
        max_duration_indices = max_positions[1]
        
        if len(max_limit_indices) == 1:
            # Only one maximum position
            best_limit_idx = max_limit_indices[0]
            best_duration_idx = max_duration_indices[0]
        else:
            # Multiple positions with same returns, need to choose best combination
            logger.info(f"🔍 Multiple parameter combinations with same returns ({max_returns_rounded:.2f}), "
                       f"applying selection strategy...")
            
            # Strategy: First prefer shorter duration, then prefer lower limit (more conservative)
            # This ensures we get the most conservative (safe) strategy when performance is equal
            
            # Step 1: Find the shortest duration(s)
            min_duration = np.min(max_duration_indices)
            shortest_duration_mask = (max_duration_indices == min_duration)
            shortest_duration_indices = np.where(shortest_duration_mask)[0]
            
            if len(shortest_duration_indices) == 1:
                # Only one position with shortest duration
                best_idx = shortest_duration_indices[0]
                best_limit_idx = max_limit_indices[best_idx]
                best_duration_idx = max_duration_indices[best_idx]
                
                logger.info(f"🔍 Single shortest duration found: limit={limit_offset + best_limit_idx}%, duration={best_duration_idx}")
            else:
                # Multiple positions with same duration, prefer lower limit (more conservative)
                shortest_duration_limit_indices = max_limit_indices[shortest_duration_mask]
                best_limit_idx = np.min(shortest_duration_limit_indices)  # Choose lowest limit
                best_duration_idx = min_duration
                
                logger.info(f"🔍 Multiple positions with same duration ({best_duration_idx}), "
                           f"selected lowest limit: limit={best_limit_idx}% (most conservative)")
        
        best_limit = limit_offset + best_limit_idx
        best_duration = best_duration_idx
        best_returns = earn_matrix[best_limit_idx, best_duration_idx]  # Use original precision for return
        
        logger.info(f"🔍 Best parameters: limit={best_limit}%, duration={best_duration}, "
                   f"returns={best_returns:.4f} (rounded: {max_returns_rounded:.2f})")
        
        return best_limit, best_duration, best_returns
    
    def _update_result_dict(self, date_dict: Dict[str, Any], instId: str, 
                           best_params: Tuple[int, int, float], earn_matrix: np.ndarray, limit_offset: int, 
                           datetime_index: np.ndarray) -> None:
        """Update result dictionary"""
        best_limit, best_duration, max_returns = best_params
        
        if instId not in date_dict:
            date_dict[instId] = {}

        # Calculate trade count and monthly frequency for best parameters
        best_limit_idx = best_limit - limit_offset
        best_duration_idx = best_duration
        
        # Count valid trades for the best parameter combination
        duration_earnings = earn_matrix[:, best_duration_idx]
        trade_count = np.sum(duration_earnings > 0)  # Count non-zero earnings (actual trades)
        
        # Calculate trades per month based on data length
        # Each data point represents 1 day, so total days = len(datetime_index)
        total_days = len(datetime_index)
        trades_per_month = (trade_count / total_days) * 30
        
        # Format returns: compound returns to 2 decimal places
        max_returns_formatted = f"{max_returns:.2f}"
        
        date_dict[instId] = {
            'best_limit': str(best_limit),
            'best_duration': str(best_duration),
            'max_returns': max_returns_formatted,
            'trade_count': str(trade_count),
            'trades_per_month': f"{trades_per_month:.2f}"
        }
        
        logger.info(f"{instId}: Best limit={best_limit}%, duration={best_duration}, "
                   f"max_returns={max_returns:.2f}, "
                   f"trades={trade_count}, monthly={trades_per_month:.2f}")


# Singleton instance
_strategy_optimizer = None

def get_strategy_optimizer(buy_fee: float = 0.001, sell_fee: float = 0.001) -> StrategyOptimizer:
    """Get singleton strategy optimizer instance with optional custom fees"""
    global _strategy_optimizer
    if _strategy_optimizer is None:
        _strategy_optimizer = StrategyOptimizer(buy_fee, sell_fee)
    return _strategy_optimizer

def reset_strategy_optimizer():
    """Reset the singleton strategy optimizer instance (useful for testing different configurations)"""
    global _strategy_optimizer
    _strategy_optimizer = None
    logger.info("Strategy optimizer singleton instance reset")
