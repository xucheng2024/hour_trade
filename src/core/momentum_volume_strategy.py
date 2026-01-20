#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Momentum-Volume Exhaustion Buy Strategy (Optimized)
Captures rebound opportunities after price drops when selling pressure is weakening

Optimizations:
1. Unified time scale: Only use 1H candle data (M=48 = true 48-hour window)
2. Directional momentum: Use log_return (short-term mean vs long-term mean)
3. Relative thresholds: Use z-score with sufficient samples (~42 for long window)
4. Practical fallback: Allow "momentum trigger + price drop" when signals sparse
5. Priority A: Long window increased to 48h for stable z-score calculation
6. Priority B: Sell pressure exhaustion (red K volume ratio) instead of total volume
7. Priority C: Volatility filter (realized_vol in 60%-90% percentile)
8. Priority D: Scoring system instead of hard AND conditions
"""

import logging
import math
import threading
import time
from collections import deque
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Strategy parameters - Priority A: Sufficient samples for stable z-score
N = 6  # Short window (6 hours)
M = 48  # Long window (48 hours) - provides ~42 samples for long-term stats

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
        # Format: instId -> deque of (timestamp, open, close, volume, is_red)
        # is_red: True if close < open (red/negative candle)
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.candle_data: Dict[str, deque] = (
            {}
        )  # Store full candle data (open, close, volume, is_red)

        # Volatility history for filter (Priority C)
        # Format: instId -> deque of realized_vol (24h rolling)
        self.volatility_history: Dict[str, deque] = {}

        # Track buy positions for each crypto
        # Format: instId -> {
        #   'total_buy_pct': float,  # Total percentage bought (0.0 to 0.70)
        #   'last_buy_time': float,   # Timestamp of last buy
        #   'buy_prices': [float],    # List of buy prices
        #   'buy_sizes': [float],     # List of buy sizes
        #   'ordIds': [str]           # List of order IDs
        # }
        self.positions: Dict[str, Dict] = {}

        # Lock for thread safety (RLock allows re-entrant locking)
        self.lock = threading.RLock()

        # Minimum history required before strategy can trigger
        # Need M+1 candles to calculate M returns
        self.min_history_required = M + 1

        # Priority C: Volatility filter parameters
        # Use 300 candles max (OKX limit), need 24 extra for 24h rolling calc
        # So volatility history = 300 - 24 = 276 hours (~11.5 days)
        self.VOL_PERCENTILE_LOW = 0.60  # 60th percentile
        self.VOL_PERCENTILE_HIGH = 0.90  # 90th percentile
        self.VOL_HISTORY_HOURS = 276  # 276 hours = 300 candles - 24 (for rolling calc)

        # Priority D: Scoring system parameters
        self.SCORE_WEIGHTS = {
            "momentum": 1.0,  # w1
            "volume": 1.0,  # w2
            "drop": 1.0,  # w3
        }
        self.SCORE_THRESHOLD_FIRST = -2.5  # First buy threshold
        self.SCORE_THRESHOLD_ADD = -3.2  # Add position threshold
        self.MIN_HOURS_BETWEEN_BUYS = 2  # Minimum hours between additional buys

        # Track if we've received at least one confirmed 1H candle after startup
        # This prevents immediate buys right after history initialization
        self.first_candle_confirmed: Dict[str, bool] = {}

    def initialize_history(
        self, instId: str, candles: list, logger_instance=None
    ) -> bool:
        """Initialize history from historical candle data

        Args:
            instId: Instrument ID
            candles: List of candle data from OKX API
                    Format: [[ts, open, high, low, close, vol, volCcy, ...], ...]
                    Data is ordered from newest to oldest
            logger_instance: Optional logger instance

        Returns:
            True if initialization successful, False otherwise

        Note:
            - Expects candles in reverse chronological order (newest first)
            - Only uses the most recent M+1 candles
            - Each candle should have at least: [ts, open, high, low, close, vol, ...]
        """
        if logger_instance is None:
            logger_instance = logger

            if not candles or len(candles) == 0:
                logger_instance.warning(
                    f"⚠️ {instId} No historical candles provided " f"for initialization"
                )
                return False

        try:
            with self.lock:
                # Initialize deques if not exists
                if instId not in self.price_history:
                    self.price_history[instId] = deque(maxlen=M + 1)
                    self.volume_history[instId] = deque(maxlen=M + 1)
                    self.candle_data[instId] = deque(maxlen=M + 1)
                    self.volatility_history[instId] = deque(
                        maxlen=self.VOL_HISTORY_HOURS
                    )

                # Process candles (newest first, reverse for chronological)
                # Take only the most recent M+1 candles
                candles_to_use = candles[: M + 1]
                # Reverse to get chronological order (oldest first)
                candles_to_use.reverse()

                count = 0
                for candle in candles_to_use:
                    if len(candle) < 6:
                        continue

                    # Extract data: [ts, open, high, low, close, vol, volCcy, ...]
                    ts_ms = int(candle[0])  # timestamp in milliseconds
                    open_price = float(candle[1])  # open price
                    close_price = float(candle[4])  # close price
                    volume = float(candle[5])  # base volume
                    vol_ccy = (
                        float(candle[6]) if len(candle) > 6 else volume
                    )  # quote volume

                    # Use volCcy (quote currency volume) if available, otherwise base volume
                    volume_to_use = vol_ccy if vol_ccy > 0 else volume
                    is_red = close_price < open_price  # Priority B: Red K check

                    if volume_to_use > 0 and close_price > 0:
                        # Convert timestamp from milliseconds to seconds
                        timestamp = ts_ms / 1000.0
                        self.price_history[instId].append((timestamp, close_price))
                        self.volume_history[instId].append((timestamp, volume_to_use))
                        # Priority B: Store full candle data for sell pressure analysis
                        self.candle_data[instId].append(
                            (timestamp, open_price, close_price, volume_to_use, is_red)
                        )
                        count += 1

                if count > 0:
                    history_len = len(self.price_history[instId])
                    logger_instance.info(
                        f"✅ {instId} Initialized with {count} "
                        f"historical 1H candles "
                        f"(ready: {history_len}/{M + 1})"
                    )
                    return True
                else:
                    logger_instance.warning(
                        f"⚠️ {instId} Failed to initialize: " f"no valid candles"
                    )
                    return False

        except Exception as e:
            logger_instance.error(f"❌ {instId} Error initializing history: {e}")
            return False

    def backfill_volatility_history(
        self, instId: str, candles: list, logger_instance=None
    ) -> bool:
        """Backfill volatility history from historical candle data
        Fills volatility_history with 24h rolling realized volatility

        Args:
            instId: Instrument ID
            candles: List of candle data from OKX API (newest first)
                    Format: [[ts, open, high, low, close, vol, volCcy, ...], ...]
                    Should contain at least VOL_HISTORY_HOURS candles
            logger_instance: Optional logger instance

        Returns:
            True if backfill successful, False otherwise

        Note:
            - Calculates 24h rolling realized volatility for each candle
            - Fills volatility_history deque with historical volatility values
        """
        if logger_instance is None:
            logger_instance = logger

        # Need VOL_HISTORY_HOURS + 24 candles (24 extra for first 24h volatility calc)
        min_candles_needed = self.VOL_HISTORY_HOURS + 24
        if not candles or len(candles) < min_candles_needed:
            logger_instance.warning(
                f"⚠️ {instId} Insufficient candles for volatility backfill: "
                f"{len(candles)} < {min_candles_needed}"
            )
            return False

        try:
            with self.lock:
                if instId not in self.volatility_history:
                    self.volatility_history[instId] = deque(
                        maxlen=self.VOL_HISTORY_HOURS
                    )

                # Process candles from oldest to newest (reverse for chronological order)
                candles_reversed = list(reversed(candles))
                prices = []

                # Extract close prices
                for candle in candles_reversed:
                    if len(candle) < 5:
                        continue
                    close_price = float(candle[4])  # close price
                    if close_price > 0:
                        prices.append(close_price)

                if len(prices) < 24:  # Need at least 24 hours for 24h volatility
                    logger_instance.warning(
                        f"⚠️ {instId} Insufficient prices for volatility calculation: "
                        f"{len(prices)} < 24"
                    )
                    return False

                # Calculate 24h rolling realized volatility
                # For each hour, calculate std(log_return) over previous 24 hours
                volatility_values = []

                for i in range(24, len(prices)):
                    # Get last 24 prices
                    window_prices = prices[i - 24 : i + 1]  # 25 prices = 24 returns

                    # Calculate log returns
                    returns = []
                    for j in range(1, len(window_prices)):
                        prev_price = window_prices[j - 1]
                        curr_price = window_prices[j]
                        if prev_price > 0:
                            log_return = math.log(curr_price / prev_price)
                            returns.append(log_return)

                    if len(returns) < 2:
                        continue

                    # Calculate standard deviation
                    mean_return = sum(returns) / len(returns)
                    variance = sum((r - mean_return) ** 2 for r in returns) / len(
                        returns
                    )
                    realized_vol = math.sqrt(variance) if variance > 0 else 0.0

                    volatility_values.append(realized_vol)

                # Fill volatility_history with calculated values
                # We need to reverse back to match chronological order
                for vol in volatility_values:
                    self.volatility_history[instId].append(vol)

                filled_count = len(self.volatility_history[instId])
                logger_instance.info(
                    f"✅ {instId} Volatility history backfilled: "
                    f"{filled_count}/{self.VOL_HISTORY_HOURS} hours"
                )
                return True

        except Exception as e:
            logger_instance.error(
                f"❌ {instId} Error backfilling volatility history: {e}"
            )
            return False

    def update_price_volume(
        self,
        instId: str,
        price: float,
        volume: float,
        open_price: Optional[float] = None,
    ):
        """Update price and volume history for a crypto (1H candle only)

        Args:
            instId: Instrument ID
            price: Current price (from 1H candle close)
            volume: Current volume (from 1H candle, must be > 0)
            open_price: Optional open price (for Priority B: sell pressure analysis)

        Note:
            - OPTIMIZATION: Only accepts data from 1H candles (volume > 0 required)
            - Priority B: If open_price provided, tracks red K volume for sell pressure
            - Saves last M+1 = 49 data points (M=48)
        """
        with self.lock:
            if instId not in self.price_history:
                self.price_history[instId] = deque(maxlen=M + 1)
                self.volume_history[instId] = deque(maxlen=M + 1)
                self.candle_data[instId] = deque(maxlen=M + 1)
                self.volatility_history[instId] = deque(maxlen=self.VOL_HISTORY_HOURS)

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

            # Priority B: Store full candle data for sell pressure analysis
            if open_price is not None:
                is_red = price < open_price  # Red K (close < open)
                self.candle_data[instId].append(
                    (timestamp, open_price, price, volume, is_red)
                )
            else:
                # Fallback: assume green K if no open price
                self.candle_data[instId].append(
                    (timestamp, price, price, volume, False)
                )

            # Priority C: Update volatility history (24h rolling)
            # Note: _calculate_24h_realized_volatility() will acquire lock,
            # but we use RLock so same thread can re-enter
            realized_vol = self._calculate_24h_realized_volatility(instId)
            if realized_vol is not None:
                self.volatility_history[instId].append(realized_vol)

    def mark_first_candle_confirmed(self, instId: str):
        """Mark that we've received the first confirmed 1H candle for this crypto
        This allows buy signals to be triggered after the first complete hour
        """
        with self.lock:
            self.first_candle_confirmed[instId] = True

            # Log history status if available (safe check to avoid KeyError)
            if instId in self.price_history:
                history_len = len(self.price_history[instId])
                if history_len == M + 1:
                    logger.debug(
                        f"📊 {instId} History full: {history_len} 1H candles "
                        f"(true {M}-hour window ready)"
                    )
                else:
                    logger.debug(
                        f"📊 {instId} First candle confirmed, "
                        f"history: {history_len}/{M + 1} candles"
                    )
            else:
                logger.debug(
                    f"📊 {instId} First candle confirmed "
                    f"(history not initialized yet)"
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

    def calculate_sell_pressure_stats(self, instId: str) -> Optional[Dict]:
        """Priority B: Calculate sell pressure exhaustion statistics
        Uses red K (down candle) volume instead of total volume

        Returns:
            Dict with:
            - short_mean: mean of short-term red K volumes
            - long_mean: mean of long-term red K volumes
            - long_std: std of long-term red K volumes
            - short_red_vol: list of short-term red K volumes
            - long_red_vol: list of long-term red K volumes
            Or None if insufficient data
        """
        with self.lock:
            if instId not in self.candle_data:
                return None

            candle_data = list(self.candle_data[instId])
            if len(candle_data) < M + 1:
                return None

            # Extract red K volumes (is_red = True)
            red_volumes = []
            for candle in candle_data:
                timestamp, open_price, close_price, volume, is_red = candle
                if is_red:  # Only count red K (close < open)
                    red_volumes.append((timestamp, volume))

            if len(red_volumes) < 3:  # Need at least some red Ks
                return None

            # Get volumes only
            volumes = [v[1] for v in red_volumes]

            # Short-term red volumes: last N periods
            short_red_vol = volumes[-N:] if len(volumes) >= N else volumes
            # Long-term red volumes: first (M-N) periods
            long_red_vol = volumes[: (M - N)] if len(volumes) >= M else []

            if len(short_red_vol) == 0 or len(long_red_vol) == 0:
                return None

            # Calculate statistics
            short_mean = sum(short_red_vol) / len(short_red_vol)
            long_mean = sum(long_red_vol) / len(long_red_vol)

            # Calculate standard deviation
            long_variance = sum((v - long_mean) ** 2 for v in long_red_vol) / len(
                long_red_vol
            )
            long_std = math.sqrt(long_variance) if long_variance > 0 else 0.0

            return {
                "short_mean": short_mean,
                "long_mean": long_mean,
                "long_std": long_std,
                "short_red_vol": short_red_vol,
                "long_red_vol": long_red_vol,
            }

    def _calculate_24h_realized_volatility(self, instId: str) -> Optional[float]:
        """Priority C: Calculate 24h realized volatility
        std(log_return) over last 24 hours

        Returns:
            Realized volatility (std of log returns) or None
        """
        with self.lock:
            if instId not in self.price_history:
                return None

            price_data = list(self.price_history[instId])
            if len(price_data) < 24:  # Need at least 24 hours
                return None

            # Get last 24 hours
            recent_prices = price_data[-24:]

            # Calculate log returns
            returns = []
            for i in range(1, len(recent_prices)):
                prev_price = recent_prices[i - 1][1]
                curr_price = recent_prices[i][1]
                if prev_price > 0:
                    log_return = math.log(curr_price / prev_price)
                    returns.append(log_return)

            if len(returns) < 2:
                return None

            # Calculate standard deviation
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            realized_vol = math.sqrt(variance)

            return realized_vol

    def _check_volatility_filter(self, instId: str) -> bool:
        """Priority C: Check if volatility is in acceptable range (60%-90% percentile)

        Returns:
            True if volatility filter passes, False otherwise
        """
        with self.lock:
            if instId not in self.volatility_history:
                logger.debug(
                    f"🚫 {instId} Volatility filter: No history yet, blocking buy"
                )
                return False  # Block if no history yet

            vol_history = list(self.volatility_history[instId])
            # Need at least 276 hours of volatility history
            if len(vol_history) < self.VOL_HISTORY_HOURS:
                logger.debug(
                    f"🚫 {instId} Volatility filter: Insufficient history "
                    f"({len(vol_history)}/{self.VOL_HISTORY_HOURS}), blocking buy"
                )
                return False  # Block if insufficient history

            current_vol = vol_history[-1] if vol_history else None
            if current_vol is None:
                logger.debug(
                    f"🚫 {instId} Volatility filter: No current volatility, blocking buy"
                )
                return False

            # Calculate percentiles
            sorted_vols = sorted(vol_history[:-1])  # Exclude current
            percentile_60 = sorted_vols[int(len(sorted_vols) * 0.60)]
            percentile_90 = sorted_vols[int(len(sorted_vols) * 0.90)]

            # Check if current volatility is in acceptable range
            in_range = percentile_60 <= current_vol <= percentile_90

            if not in_range:
                logger.debug(
                    f"🚫 {instId} Volatility filter: {current_vol:.6f} not in range "
                    f"[{percentile_60:.6f}, {percentile_90:.6f}]"
                )
            else:
                logger.debug(
                    f"✅ {instId} Volatility filter: {current_vol:.6f} in range "
                    f"[{percentile_60:.6f}, {percentile_90:.6f}]"
                )

            return in_range

    def is_in_downtrend(
        self, instId: str, current_price: Optional[float] = None
    ) -> bool:
        """Check if price is in downtrend (P_t < P_{t-M})

        Args:
            instId: Instrument ID
            current_price: Optional current price to use instead of last confirmed price
                          (useful for intra-hour checks)

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

            # Use provided current_price if available (for intra-hour checks),
            # otherwise use last confirmed price from history
            if current_price is not None:
                price_to_compare = current_price
            else:
                price_to_compare = price_data[-1][1]  # Latest confirmed price

            old_price = price_data[0][1]  # Price M periods ago

            is_downtrend = price_to_compare < old_price
            if is_downtrend:
                drop_pct = ((old_price - price_to_compare) / old_price) * 100
                price_source = "current" if current_price is not None else "confirmed"
                logger.debug(
                    f"📉 {instId} Downtrend ({price_source}): {price_to_compare:.6f} < {old_price:.6f} "
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

        # Check if in downtrend (use current_price for intra-hour checks)
        in_downtrend = self.is_in_downtrend(instId, current_price=current_price)
        if not in_downtrend:
            logger.debug(
                f"⏭️ {instId} Not in downtrend (current_price={current_price:.6f})"
            )
            return False, None

        # Check if we've received at least one confirmed 1H candle for this crypto
        # This prevents immediate buys right after history initialization
        with self.lock:
            if not self.first_candle_confirmed.get(instId, False):
                logger.debug(
                    f"⏸️ {instId} First confirmed 1H candle not received yet, "
                    f"blocking buy to avoid immediate triggers after history init"
                )
                return False, None

        # Check if buy should be blocked
        should_block = self.should_block_buy(instId)
        if should_block:
            logger.debug(f"🚫 {instId} Buy blocked by should_block_buy check")
            return False, None

        # Calculate statistics
        momentum_stats = self.calculate_momentum_stats(instId)
        volume_stats = self.calculate_volume_stats(instId)

        if momentum_stats is None or volume_stats is None:
            logger.debug(
                f"⏭️ {instId} Insufficient stats: "
                f"momentum={momentum_stats is not None}, "
                f"volume={volume_stats is not None}"
            )
            return False, None

        # Priority D: Calculate scores for scoring system
        # Calculate momentum z-score
        long_momentum_mean = momentum_stats["long_mean"]
        long_momentum_std = momentum_stats["long_std"]
        short_momentum_mean = momentum_stats["short_mean"]

        momentum_z_score = None
        momentum_ratio = None
        if long_momentum_std > 0:
            # Use z-score: (short_mean - long_mean) / long_std
            momentum_z_score = (
                short_momentum_mean - long_momentum_mean
            ) / long_momentum_std
        else:
            # Fallback to relative threshold if volatility too low
            momentum_ratio = self.calculate_momentum_ratio(instId)

        # Priority B: Check sell pressure exhaustion using red K volume
        sell_pressure_stats = self.calculate_sell_pressure_stats(instId)
        volume_z_score = None
        volume_ratio = None

        if sell_pressure_stats is not None:
            long_volume_mean = sell_pressure_stats["long_mean"]
            long_volume_std = sell_pressure_stats["long_std"]
            short_volume_mean = sell_pressure_stats["short_mean"]

            if long_volume_std > 0:
                # Use z-score for red K volume
                volume_z_score = (
                    short_volume_mean - long_volume_mean
                ) / long_volume_std
            else:
                # Fallback to relative threshold
                if long_volume_mean > 0:
                    volume_ratio = short_volume_mean / long_volume_mean
        else:
            # Fallback to total volume if no red K data
            volume_stats = self.calculate_volume_stats(instId)
            if volume_stats is not None:
                long_volume_mean = volume_stats["long_mean"]
                long_volume_std = volume_stats["long_std"]
                short_volume_mean = volume_stats["short_mean"]

                if long_volume_std > 0:
                    volume_z_score = (
                        short_volume_mean - long_volume_mean
                    ) / long_volume_std
                else:
                    volume_ratio = self.calculate_volume_ratio(instId)

        # Priority C: Check volatility filter
        volatility_passed = self._check_volatility_filter(instId)
        if not volatility_passed:
            logger.debug(
                f"🚫 {instId} Volatility filter blocked buy signal "
                f"(current_price={current_price:.6f})"
            )
            return False, None
        else:
            logger.debug(
                f"✅ {instId} Volatility filter passed "
                f"(current_price={current_price:.6f})"
            )

        # Calculate price drop
        price_drop_pct = None
        with self.lock:
            price_data = list(self.price_history[instId])
            if len(price_data) >= M + 1:
                old_price = price_data[0][1]  # Price M periods ago
                price_drop_pct = (old_price - current_price) / old_price

        # Priority D: Scoring system instead of hard AND conditions
        # score_mom = clamp(z_mom, -3, 3) (越负越好)
        score_mom = 0.0
        if momentum_z_score is not None:
            score_mom = max(-3.0, min(3.0, momentum_z_score))
        elif momentum_ratio is not None:
            # Convert ratio to approximate z-score
            # Lower ratio = lower score (more negative)
            score_mom = -1.0 if momentum_ratio < 0.6 else 0.0

        # score_vol = clamp(z_vol, -3, 3) (越负越好)
        score_vol = 0.0
        if volume_z_score is not None:
            score_vol = max(-3.0, min(3.0, volume_z_score))
        elif volume_ratio is not None:
            # Convert ratio to approximate z-score
            score_vol = -1.0 if volume_ratio < 0.7 else 0.0

        # score_drop = -drop_pct / 0.02 (跌得越多越好，上限封顶)
        score_drop = 0.0
        if price_drop_pct is not None and price_drop_pct > 0:
            score_drop = -min(price_drop_pct / 0.02, 3.0)  # Cap at -3.0

        # Total score: S = w1*score_mom + w2*score_vol + w3*score_drop
        total_score = (
            self.SCORE_WEIGHTS["momentum"] * score_mom
            + self.SCORE_WEIGHTS["volume"] * score_vol
            + self.SCORE_WEIGHTS["drop"] * score_drop
        )

        # Priority D: Scoring thresholds
        # S <= -2.5: Allow entry (first 30%)
        # S <= -3.2 and time since last buy >= X hours: Allow add (20%)
        with self.lock:
            position = self.positions.get(instId, {})
            total_buy_pct = position.get("total_buy_pct", 0.0)
            last_buy_time = position.get("last_buy_time", 0.0)
            hours_since_last_buy = (
                (time.time() - last_buy_time) / 3600.0 if last_buy_time > 0 else 999
            )

            if total_buy_pct == 0.0:
                # First buy: S <= -2.5
                buy_triggered = total_score <= self.SCORE_THRESHOLD_FIRST
            else:
                # Additional buy: S <= -3.2 and >= X hours since last buy
                buy_triggered = (
                    total_score <= self.SCORE_THRESHOLD_ADD
                    and hours_since_last_buy >= self.MIN_HOURS_BETWEEN_BUYS
                )

        if not buy_triggered:
            logger.debug(
                f"⏭️ {instId} Score {total_score:.2f} not meeting threshold "
                f"(first: {total_buy_pct==0.0}, needed: "
                f"{self.SCORE_THRESHOLD_FIRST if total_buy_pct==0.0 else self.SCORE_THRESHOLD_ADD}, "
                f"hours_since: {hours_since_last_buy:.1f}, "
                f"scores: mom={score_mom:.2f}, vol={score_vol:.2f}, drop={score_drop:.2f})"
            )
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

            # Log with detailed information (Priority D: scoring system)
            if momentum_ratio is None:
                momentum_ratio = self.calculate_momentum_ratio(instId)
            if volume_ratio is None and sell_pressure_stats is None:
                volume_ratio = self.calculate_volume_ratio(instId)

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

            # Get current volatility for logging
            # Note: We're already inside a with self.lock block above,
            # so we can directly access volatility_history without re-acquiring lock
            realized_vol = None
            if instId in self.volatility_history:
                vol_list = list(self.volatility_history[instId])
                if vol_list:
                    realized_vol = vol_list[-1]

            vol_str = f"{realized_vol:.6f}" if realized_vol is not None else "N/A"

            logger.warning(
                f"🎯 {instId} BUY SIGNAL (score={total_score:.2f}): "
                f"scores[mom={score_mom:.2f}, vol={score_vol:.2f}, drop={score_drop:.2f}], "
                f"momentum_z={momentum_z_str}, volume_z={volume_z_str}, "
                f"momentum_ratio={momentum_ratio_str}, volume_ratio={volume_ratio_str}, "
                f"price_drop={price_drop_str}, realized_vol={vol_str}, "
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
            if instId in self.candle_data:
                del self.candle_data[instId]
            # Keep volatility history for future use (Priority C)
            # if instId in self.volatility_history:
            #     del self.volatility_history[instId]
            # Reset first candle confirmed flag so we wait for next confirmation
            if instId in self.first_candle_confirmed:
                del self.first_candle_confirmed[instId]
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
