#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Momentum-Volume Exhaustion Buy Strategy
Captures rebound opportunities after price drops when selling pressure is weakening
"""

import logging
import threading
import time
from collections import deque
# datetime not used in this file
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Strategy parameters (fixed, conservative values)
N = 5  # Short window
M = 10  # Long window
TH_P = 0.6  # Momentum decay threshold
TH_V = 0.7  # Volume decay threshold

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
        self.min_history_required = M

    def update_price_volume(self, instId: str, price: float, volume: float):
        """Update price and volume history for a crypto

        Args:
            instId: Instrument ID
            price: Current price
            volume: Current volume (from candle only, 0.0 to skip volume update)

        Note:
            - Saves last M+1 = 11 data points
            - Price: updated from both ticker (frequent) and candle (accurate)
            - Volume: only updated from candle (volume=0.0 means skip volume update)
        """
        with self.lock:
            if instId not in self.price_history:
                self.price_history[instId] = deque(maxlen=M + 1)
                self.volume_history[instId] = deque(maxlen=M + 1)

            timestamp = time.time()
            # Always update price
            self.price_history[instId].append((timestamp, price))

            # ✅ FIX: Truly skip volume update when volume=0.0 (don't append to history)
            # Only update volume if provided (volume > 0 means it's from candle)
            if volume > 0:
                self.volume_history[instId].append((timestamp, volume))
            # else: Skip volume update completely when volume=0.0
            # This ensures volume history only contains actual candle data

            # deque automatically maintains maxlen, but log when we have enough data
            history_len = len(self.price_history[instId])
            if history_len == M + 1:
                logger.debug(
                    f"📊 {instId} History full: {history_len} points "
                    f"(ready for calculation)"
                )

    def calculate_momentum_ratio(self, instId: str) -> Optional[float]:
        """Calculate short vs long momentum ratio

        Returns:
            Ratio of short momentum to long momentum, or None if insufficient data
        """
        with self.lock:
            if instId not in self.price_history:
                return None

            price_data = list(self.price_history[instId])
            if len(price_data) < M + 1:
                return None

            # Calculate returns (absolute price changes)
            # We have M+1 prices, which gives us M returns
            returns = []
            for i in range(1, len(price_data)):
                prev_price = price_data[i - 1][1]
                curr_price = price_data[i][1]
                returns.append(abs(curr_price - prev_price))

            if len(returns) < M:
                return None

            # Short momentum: average of last N returns (most recent N periods)
            short_momentum = sum(returns[-N:]) / N if N > 0 else 0.0

            # Long momentum: average of first (M-N) returns (older periods)
            # This compares recent N periods vs earlier (M-N) periods
            if len(returns) >= M:
                # Use first (M-N) = 5 returns for long momentum
                long_momentum = (
                    sum(returns[: (M - N)]) / (M - N) if (M - N) > 0 else 0.0
                )
            else:
                return None  # Not enough data

            if long_momentum == 0:
                return None

            return short_momentum / long_momentum

    def calculate_volume_ratio(self, instId: str) -> Optional[float]:
        """Calculate short vs long volume ratio

        Returns:
            Ratio of short volume to long volume, or None if insufficient data
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

            # Short volume: average of last N volumes (most recent N periods)
            short_volume = sum(volumes[-N:]) / N if N > 0 else 0.0

            # Long volume: average of first (M-N) volumes (older periods)
            # This compares recent N periods vs earlier (M-N) periods
            if len(volumes) >= M + 1:
                # Use first (M-N) = 5 volumes for long volume
                long_volume = sum(volumes[: (M - N)]) / (M - N) if (M - N) > 0 else 0.0
            else:
                return None  # Not enough data

            if long_volume == 0:
                return None

            return short_volume / long_volume

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
        momentum_ratio = self.calculate_momentum_ratio(instId)
        volume_ratio = self.calculate_volume_ratio(instId)

        # Block if momentum or volume is increasing (ratio > 1.0)
        if momentum_ratio is not None and momentum_ratio > 1.0:
            logger.debug(
                f"🚫 {instId} BLOCKED: momentum ratio {momentum_ratio:.3f} > 1.0"
            )
            return True

        if volume_ratio is not None and volume_ratio > 1.0:
            logger.debug(f"🚫 {instId} BLOCKED: volume ratio {volume_ratio:.3f} > 1.0")
            return True

        return False

    def check_buy_signal(
        self, instId: str, current_price: float
    ) -> Tuple[bool, Optional[float]]:
        """Check if buy signal is triggered

        Args:
            instId: Instrument ID
            current_price: Current price

        Returns:
            Tuple of (should_buy, buy_percentage)
            buy_percentage: Percentage of total amount to buy (0.30, 0.20, etc.)
        """
        # Check if we have enough history
        with self.lock:
            if instId not in self.price_history:
                return False, None

            price_data = list(self.price_history[instId])
            history_len = len(price_data)
            if history_len < self.min_history_required:
                logger.debug(
                    f"⏳ {instId} Insufficient history: {history_len}/{self.min_history_required} points"
                )
                return False, None

        # Check if in downtrend
        if not self.is_in_downtrend(instId):
            return False, None

        # Check if buy should be blocked
        if self.should_block_buy(instId):
            return False, None

        # Calculate ratios
        momentum_ratio = self.calculate_momentum_ratio(instId)
        volume_ratio = self.calculate_volume_ratio(instId)

        if momentum_ratio is None or volume_ratio is None:
            return False, None

        # Check buy conditions
        momentum_exhausted = momentum_ratio < TH_P
        volume_exhausted = volume_ratio < TH_V

        if not (momentum_exhausted and volume_exhausted):
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

            logger.warning(
                f"🎯 {instId} BUY SIGNAL: momentum={momentum_ratio:.3f} "
                f"(<{TH_P}), volume={volume_ratio:.3f} (<{TH_V}), "
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
