#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Momentum-Volume Exhaustion Buy Strategy (Optimized)
Captures rebound opportunities after price drops when selling pressure is weakening

Optimizations:
1. Unified time scale: Only use 1H candle data (M=10 = true 10-hour window)
2. Directional momentum: Use log_return (short-term mean vs long-term mean)
3. Relative thresholds: Use z-score instead of fixed 0.6/0.7
4. Practical fallback: Allow "momentum trigger + price drop" when signals sparse
"""

import logging
import math
import threading
import time
from collections import deque
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Strategy parameters
N = 5  # Short window (hours)
M = 10  # Long window (hours) - true 10-hour window when using 1H candles

# Relative threshold parameters (replaces fixed TH_P=0.6, TH_V=0.7)
MOMENTUM_Z_SCORE_THRESHOLD = -1.0  # Short momentum < long_mean - 1.0*std
VOLUME_Z_SCORE_THRESHOLD = -1.0  # Short volume < long_mean - 1.0*std
MOMENTUM_RELATIVE_THRESHOLD = 0.6  # Fallback: short/long < 0.6 if volatility too low
VOLUME_RELATIVE_THRESHOLD = 0.7  # Fallback: short/long < 0.7 if volatility too low

# Price drop condition for sparse signals
MIN_PRICE_DROP_PCT = 0.02  # Minimum 2% price drop from M periods ago

# Buy allocation strategy
FIRST_BUY_PCT = 0.30  # 30% on first trigger
SUBSEQUENT_BUY_PCT = 0.20  # 20% on subsequent triggers
MAX_BUY_PCT = 0.70  # Maximum 70% total


class MomentumVolumeStrategy:
    """Momentum-Volume Exhaustion Buy Strategy"""

    def __init__(self):
        # Price and volume history for each crypto
        # Format: instId -> deque of (timestamp, price, volume)
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}

        # Track buy positions for each crypto
        # Format: instId -> {
        #   'total_buy_pct': float,  # Total percentage bought (0.0 to 0.70)
        #   'last_buy_time': float,   # Timestamp of last buy
        #   'buy_prices': [float],    # List of buy prices
        #   'buy_sizes': [float],     # List of buy sizes
        #   'ordIds': [str]           # List of order IDs
        # }
        self.positions: Dict[str, Dict] = {}

        # Lock for thread safety
        self.lock = threading.Lock()

        # Minimum history required before strategy can trigger
        # Need M+1 candles to calculate M returns
        self.min_history_required = M + 1

    def update_price_volume(self, instId: str, price: float, volume: float):
        """Update price and volume history for a crypto (1H candle only)

        Args:
            instId: Instrument ID
            price: Current price (from 1H candle close)
            volume: Current volume (from 1H candle, must be > 0)

        Note:
            - OPTIMIZATION: Only accepts data from 1H candles (volume > 0 required)
            - This ensures M=10 represents a true 10-hour window
            - Both price and volume updated together from same candle
            - Saves last M+1 = 11 data points
        """
        with self.lock:
            if instId not in self.price_history:
                self.price_history[instId] = deque(maxlen=M + 1)
                self.volume_history[instId] = deque(maxlen=M + 1)

            # OPTIMIZATION: Only update when volume > 0 (ensures 1H candle data)
            if volume <= 0:
                logger.debug(
                    f"⏭️ {instId} Skipping update: volume={volume} (not from 1H candle)"
                )
                return

            timestamp = time.time()
            # Update both price and volume together (from same 1H candle)
            self.price_history[instId].append((timestamp, price))
            self.volume_history[instId].append((timestamp, volume))

            # deque automatically maintains maxlen, but log when we have enough data
            history_len = len(self.price_history[instId])
            if history_len == M + 1:
                logger.debug(
                    f"📊 {instId} History full: {history_len} 1H candles "
                    f"(true {M}-hour window ready)"
                )

    def calculate_momentum_stats(self, instId: str) -> Optional[Dict]:
        """Calculate momentum statistics with directional returns

        Returns:
            Dict with:
            - short_mean: mean of short-term returns (last N periods)
            - long_mean: mean of long-term returns (first M-N periods)
            - long_std: std of long-term returns
            - short_returns: list of short-term returns
            - long_returns: list of long-term returns
            Or None if insufficient data
        """
        with self.lock:
            if instId not in self.price_history:
                return None

            price_data = list(self.price_history[instId])
            if len(price_data) < M + 1:
                return None

            # OPTIMIZATION: Calculate directional returns (log returns)
            # log_return = ln(P_t / P_{t-1}) ≈ (P_t - P_{t-1}) / P_{t-1}
            returns = []
            for i in range(1, len(price_data)):
                prev_price = price_data[i - 1][1]
                curr_price = price_data[i][1]
                if prev_price > 0:
                    # Use log return (directional, handles scale better)
                    log_return = math.log(curr_price / prev_price)
                    returns.append(log_return)
                else:
                    return None

            if len(returns) < M:
                return None

            # Short-term returns: last N periods
            short_returns = returns[-N:] if len(returns) >= N else []
            # Long-term returns: first (M-N) periods
            long_returns = returns[: (M - N)] if len(returns) >= M else []

            if len(short_returns) == 0 or len(long_returns) == 0:
                return None

            # Calculate statistics
            short_mean = sum(short_returns) / len(short_returns)
            long_mean = sum(long_returns) / len(long_returns)

            # Calculate standard deviation of long-term returns
            long_variance = sum((r - long_mean) ** 2 for r in long_returns) / len(
                long_returns
            )
            long_std = math.sqrt(long_variance) if long_variance > 0 else 0.0

            return {
                "short_mean": short_mean,
                "long_mean": long_mean,
                "long_std": long_std,
                "short_returns": short_returns,
                "long_returns": long_returns,
            }

    def calculate_momentum_ratio(self, instId: str) -> Optional[float]:
        """Calculate short vs long momentum ratio (backward compatibility)

        Returns:
            Ratio of short momentum to long momentum, or None if insufficient data
        """
        stats = self.calculate_momentum_stats(instId)
        if stats is None:
            return None

        short_mean = abs(stats["short_mean"])
        long_mean = abs(stats["long_mean"])

        if long_mean == 0:
            return None

        return short_mean / long_mean

    def calculate_volume_stats(self, instId: str) -> Optional[Dict]:
        """Calculate volume statistics

        Returns:
            Dict with:
            - short_mean: mean of short-term volumes
            - long_mean: mean of long-term volumes
            - long_std: std of long-term volumes
            Or None if insufficient data
        """
        with self.lock:
            if instId not in self.volume_history:
                return None

            volume_data = list(self.volume_history[instId])
            if len(volume_data) < M + 1:
                return None

            # Extract volumes
            volumes = [v[1] for v in volume_data]

            if len(volumes) < M + 1:
                return None

            # Short-term volumes: last N periods
            short_volumes = volumes[-N:] if len(volumes) >= N else []
            # Long-term volumes: first (M-N) periods
            long_volumes = volumes[: (M - N)] if len(volumes) >= M else []

            if len(short_volumes) == 0 or len(long_volumes) == 0:
                return None

            # Calculate statistics
            short_mean = sum(short_volumes) / len(short_volumes)
            long_mean = sum(long_volumes) / len(long_volumes)

            # Calculate standard deviation of long-term volumes
            long_variance = sum((v - long_mean) ** 2 for v in long_volumes) / len(
                long_volumes
            )
            long_std = math.sqrt(long_variance) if long_variance > 0 else 0.0

            return {
                "short_mean": short_mean,
                "long_mean": long_mean,
                "long_std": long_std,
            }

    def calculate_volume_ratio(self, instId: str) -> Optional[float]:
        """Calculate short vs long volume ratio (backward compatibility)

        Returns:
            Ratio of short volume to long volume, or None if insufficient data
        """
        stats = self.calculate_volume_stats(instId)
        if stats is None:
            return None

        if stats["long_mean"] == 0:
            return None

        return stats["short_mean"] / stats["long_mean"]

    def is_in_downtrend(self, instId: str) -> bool:
        """Check if price is in downtrend (P_t < P_{t-M})

        Returns:
            True if current price is below price M periods ago
            Compares most recent price (index -1) with oldest price (index 0)
        """
        with self.lock:
            if instId not in self.price_history:
                return False

            price_data = list(self.price_history[instId])
            if len(price_data) < M + 1:
                return False

            # Compare most recent price with oldest price in history
            current_price = price_data[-1][1]  # Latest price
            old_price = price_data[0][1]  # Price M periods ago

            is_downtrend = current_price < old_price
            if is_downtrend:
                drop_pct = ((old_price - current_price) / old_price) * 100
                logger.debug(
                    f"📉 {instId} Downtrend: {current_price:.6f} < {old_price:.6f} "
                    f"({drop_pct:.2f}% drop)"
                )

            return is_downtrend

    def should_block_buy(self, instId: str) -> bool:
        """Check if buy should be blocked (momentum or volume increasing)

        Returns:
            True if buy should be blocked
        """
        momentum_stats = self.calculate_momentum_stats(instId)
        volume_stats = self.calculate_volume_stats(instId)

        # Block if short-term momentum is positive and above long-term mean
        if momentum_stats is not None:
            short_mean = momentum_stats["short_mean"]
            long_mean = momentum_stats["long_mean"]
            # Block if short momentum is positive and above long-term mean
            if short_mean > 0 and short_mean > long_mean:
                logger.debug(
                    f"🚫 {instId} BLOCKED: short momentum {short_mean:.6f} > "
                    f"long mean {long_mean:.6f} (uptrend)"
                )
                return True

        # Block if volume is increasing
        if volume_stats is not None:
            if volume_stats["short_mean"] > volume_stats["long_mean"]:
                logger.debug(
                    f"🚫 {instId} BLOCKED: short volume "
                    f"{volume_stats['short_mean']:.2f} > "
                    f"long volume {volume_stats['long_mean']:.2f}"
                )
                return True

        return False

    def check_buy_signal(
        self, instId: str, current_price: float
    ) -> Tuple[bool, Optional[float]]:
        """Check if buy signal is triggered (optimized with relative thresholds)

        Args:
            instId: Instrument ID
            current_price: Current price

        Returns:
            Tuple of (should_buy, buy_percentage)
            buy_percentage: Percentage of total amount to buy (0.30, 0.20, etc.)
        """
        # Check if we have enough history
        # Need M+1 candles to calculate M returns
        with self.lock:
            if instId not in self.price_history:
                return False, None

            price_data = list(self.price_history[instId])
            history_len = len(price_data)
            if history_len < M + 1:
                logger.debug(
                    f"⏳ {instId} Insufficient history: "
                    f"{history_len}/{M + 1} 1H candles "
                    f"(need {M + 1} to calculate {M} returns)"
                )
                return False, None

        # Check if in downtrend
        if not self.is_in_downtrend(instId):
            return False, None

        # Check if buy should be blocked
        if self.should_block_buy(instId):
            return False, None

        # Calculate statistics
        momentum_stats = self.calculate_momentum_stats(instId)
        volume_stats = self.calculate_volume_stats(instId)

        if momentum_stats is None or volume_stats is None:
            return False, None

        # OPTIMIZATION: Use z-score for relative threshold
        # Check momentum exhaustion using z-score
        long_momentum_mean = momentum_stats["long_mean"]
        long_momentum_std = momentum_stats["long_std"]
        short_momentum_mean = momentum_stats["short_mean"]

        momentum_exhausted = False
        momentum_z_score = None
        momentum_ratio = None
        if long_momentum_std > 0:
            # Use z-score: (short_mean - long_mean) / long_std
            momentum_z_score = (
                short_momentum_mean - long_momentum_mean
            ) / long_momentum_std
            momentum_exhausted = momentum_z_score < MOMENTUM_Z_SCORE_THRESHOLD
        else:
            # Fallback to relative threshold if volatility too low
            momentum_ratio = self.calculate_momentum_ratio(instId)
            if momentum_ratio is not None:
                momentum_exhausted = momentum_ratio < MOMENTUM_RELATIVE_THRESHOLD

        # Check volume exhaustion using z-score
        long_volume_mean = volume_stats["long_mean"]
        long_volume_std = volume_stats["long_std"]
        short_volume_mean = volume_stats["short_mean"]

        volume_exhausted = False
        volume_z_score = None
        volume_ratio = None
        if long_volume_std > 0:
            # Use z-score
            volume_z_score = (short_volume_mean - long_volume_mean) / long_volume_std
            volume_exhausted = volume_z_score < VOLUME_Z_SCORE_THRESHOLD
        else:
            # Fallback to relative threshold if volatility too low
            volume_ratio = self.calculate_volume_ratio(instId)
            if volume_ratio is not None:
                volume_exhausted = volume_ratio < VOLUME_RELATIVE_THRESHOLD

        # OPTIMIZATION: Practical fallback for sparse signals
        # If momentum exhausted but volume not, allow if price drop is significant
        price_drop_condition = False
        price_drop_pct = None
        if momentum_exhausted and not volume_exhausted:
            # Check if price has dropped significantly
            with self.lock:
                price_data = list(self.price_history[instId])
                if len(price_data) >= M + 1:
                    old_price = price_data[0][1]  # Price M periods ago
                    price_drop_pct = (old_price - current_price) / old_price
                    price_drop_condition = price_drop_pct >= MIN_PRICE_DROP_PCT

        # Buy signal: (momentum exhausted AND volume exhausted) OR
        #             (momentum exhausted AND significant price drop)
        buy_triggered = (momentum_exhausted and volume_exhausted) or (
            momentum_exhausted and price_drop_condition
        )

        if not buy_triggered:
            return False, None

        # Determine buy percentage based on current position
        with self.lock:
            position = self.positions.get(instId, {})
            total_buy_pct = position.get("total_buy_pct", 0.0)

            # Check if we've already reached max
            if total_buy_pct >= MAX_BUY_PCT:
                logger.debug(f"⏸️ {instId} Already at max position: {total_buy_pct:.2%}")
                return False, None

            # Calculate next buy percentage
            if total_buy_pct == 0.0:
                # First buy: 30%
                buy_pct = FIRST_BUY_PCT
            else:
                # Subsequent buys: 20% each
                buy_pct = SUBSEQUENT_BUY_PCT

            # Ensure we don't exceed max
            if total_buy_pct + buy_pct > MAX_BUY_PCT:
                buy_pct = MAX_BUY_PCT - total_buy_pct

            # Log with detailed information
            if momentum_ratio is None:
                momentum_ratio = self.calculate_momentum_ratio(instId)
            if volume_ratio is None:
                volume_ratio = self.calculate_volume_ratio(instId)

            signal_type = (
                "full" if (momentum_exhausted and volume_exhausted) else "momentum+drop"
            )

            # Format z-scores for logging
            momentum_z_str = (
                f"{momentum_z_score:.3f}" if momentum_z_score is not None else "N/A"
            )
            volume_z_str = (
                f"{volume_z_score:.3f}" if volume_z_score is not None else "N/A"
            )
            momentum_ratio_str = (
                f"{momentum_ratio:.3f}" if momentum_ratio is not None else "N/A"
            )
            volume_ratio_str = (
                f"{volume_ratio:.3f}" if volume_ratio is not None else "N/A"
            )
            price_drop_str = (
                f"{price_drop_pct*100:.2f}%" if price_drop_pct is not None else "N/A"
            )

            logger.warning(
                f"🎯 {instId} BUY SIGNAL ({signal_type}): "
                f"momentum_z={momentum_z_str}, volume_z={volume_z_str}, "
                f"momentum_ratio={momentum_ratio_str}, "
                f"volume_ratio={volume_ratio_str}, "
                f"price_drop={price_drop_str}, "
                f"buy_pct={buy_pct:.1%}, total_pct={total_buy_pct:.1%}"
            )

            return True, buy_pct

    def record_buy(self, instId: str, buy_price: float, buy_size: float, ordId: str):
        """Record a buy order

        Args:
            instId: Instrument ID
            buy_price: Buy price
            buy_size: Buy size
            ordId: Order ID
        """
        with self.lock:
            if instId not in self.positions:
                self.positions[instId] = {
                    "total_buy_pct": 0.0,
                    "last_buy_time": 0.0,
                    "buy_prices": [],
                    "buy_sizes": [],
                    "ordIds": [],
                }

            position = self.positions[instId]

            # Calculate buy percentage (approximate, based on amount)
            # This is a simplified calculation - in practice, you'd track actual amounts
            # Note: buy_amount calculation removed as it's not used
            # We'll track this as a percentage increment
            # For simplicity, we'll assume each buy is the calculated percentage
            if len(position["buy_prices"]) == 0:
                position["total_buy_pct"] = FIRST_BUY_PCT
            else:
                position["total_buy_pct"] = min(
                    position["total_buy_pct"] + SUBSEQUENT_BUY_PCT, MAX_BUY_PCT
                )

            position["last_buy_time"] = time.time()
            position["buy_prices"].append(buy_price)
            position["buy_sizes"].append(buy_size)
            position["ordIds"].append(ordId)

            logger.info(
                f"📝 {instId} Recorded buy: price={buy_price:.6f}, "
                f"size={buy_size:.6f}, total_pct={position['total_buy_pct']:.1%}"
            )

    def reset_position(self, instId: str):
        """Reset position for a crypto (e.g., after sell or removal)

        Args:
            instId: Instrument ID
        """
        with self.lock:
            if instId in self.positions:
                del self.positions[instId]
            if instId in self.price_history:
                del self.price_history[instId]
            if instId in self.volume_history:
                del self.volume_history[instId]
            logger.info(f"🔄 {instId} Position reset")

    def get_position_info(self, instId: str) -> Optional[Dict]:
        """Get current position information

        Args:
            instId: Instrument ID

        Returns:
            Position dict or None if no position
        """
        with self.lock:
            if instId in self.positions:
                return self.positions[instId].copy()
            return None
