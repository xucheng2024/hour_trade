#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Buy Strategy
Buys only when price is stable (no accelerated drop)
Waits for stability before buying when triggered
"""

import logging
import threading
import time
from collections import deque
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Accelerated drop thresholds
DROP_1S_THRESHOLD = -0.0015  # -0.15% in 1 second
DROP_3S_THRESHOLD = -0.0030  # -0.30% in 3 seconds

# Stability check parameters
STABILITY_CHECK_SECONDS = 5  # Check stability for 5 seconds
STABLE_DROP_THRESHOLD = -0.0005  # -0.05% per second considered stable


class StableBuyStrategy:
    """Stable Buy Strategy - waits for price stability before buying"""

    def __init__(self):
        # Price history for each crypto
        # Format: instId -> deque of (timestamp, price)
        # Keep at least 3 seconds of history
        self.price_history: Dict[str, deque] = {}

        # Track pending buy signals (waiting for stability)
        # Format: instId -> {
        #   'trigger_time': float,
        #   'trigger_price': float,
        #   'limit_price': float,
        #   'stable_count': int,  # Number of consecutive stable checks
        #   'last_check_time': float
        # }
        self.pending_signals: Dict[str, Dict] = {}

        # Lock for thread safety (use RLock to allow re-entrant locking)
        self.lock = threading.RLock()

        # Minimum history required (3 seconds)
        self.min_history_seconds = 3

    def update_price(self, instId: str, price: float):
        """Update price history for a crypto

        Args:
            instId: Instrument ID
            price: Current price
        """
        with self.lock:
            if instId not in self.price_history:
                # Keep 10 seconds of history (at 1 update per second average)
                self.price_history[instId] = deque(maxlen=10)

            timestamp = time.time()
            self.price_history[instId].append((timestamp, price))

    def _get_price_at_time(self, instId: str, seconds_ago: float) -> Optional[float]:
        """Get price at specified seconds ago

        Args:
            instId: Instrument ID
            seconds_ago: How many seconds ago (e.g., 1.0 for 1 second ago)

        Returns:
            Price at that time, or None if not available
        """
        with self.lock:
            if instId not in self.price_history:
                return None

            history = list(self.price_history[instId])
            if len(history) < 2:
                return None

            current_time = time.time()
            target_time = current_time - seconds_ago

            # Find closest price to target_time
            for i in range(len(history) - 1, -1, -1):
                timestamp, price = history[i]
                if timestamp <= target_time:
                    return price

            # If no price found before target_time, use oldest available
            if history:
                return history[0][1]

            return None

    def is_accelerated_drop(self, instId: str) -> bool:
        """Check if price is in accelerated drop

        Returns:
            True if accelerated drop detected (should block buy)
        """
        with self.lock:
            if instId not in self.price_history:
                return False

            history = list(self.price_history[instId])
            if len(history) < 2:
                return False

            current_time = time.time()
            current_price = history[-1][1]

            # Check 1 second drop
            price_1s_ago = self._get_price_at_time(instId, 1.0)
            if price_1s_ago and price_1s_ago > 0:
                drop_1s = (current_price - price_1s_ago) / price_1s_ago
                if drop_1s <= DROP_1S_THRESHOLD:
                    logger.debug(
                        f"🚫 {instId} Accelerated drop detected (1s): "
                        f"{drop_1s*100:.3f}% <= {DROP_1S_THRESHOLD*100:.3f}%"
                    )
                    return True

            # Check 3 second drop
            price_3s_ago = self._get_price_at_time(instId, 3.0)
            if price_3s_ago and price_3s_ago > 0:
                drop_3s = (current_price - price_3s_ago) / price_3s_ago
                if drop_3s <= DROP_3S_THRESHOLD:
                    logger.debug(
                        f"🚫 {instId} Accelerated drop detected (3s): "
                        f"{drop_3s*100:.3f}% <= {DROP_3S_THRESHOLD*100:.3f}%"
                    )
                    return True

            return False

    def register_buy_signal(self, instId: str, limit_price: float) -> bool:
        """Register a buy signal and start stability check

        Args:
            instId: Instrument ID
            limit_price: Limit price for buy

        Returns:
            True if signal registered, False if already registered or in accelerated drop
        """
        with self.lock:
            # Check if already in accelerated drop
            if self.is_accelerated_drop(instId):
                logger.debug(f"🚫 {instId} Buy signal blocked: accelerated drop")
                return False

            # Check if already have pending signal
            if instId in self.pending_signals:
                logger.debug(
                    f"⏳ {instId} Buy signal already pending, waiting for stability"
                )
                return False

            # Get current price
            if instId not in self.price_history:
                logger.debug(
                    f"⏳ {instId} No price history yet, cannot register signal"
                )
                return False

            current_price = (
                self.price_history[instId][-1][1]
                if self.price_history[instId]
                else None
            )
            if current_price is None:
                return False

            # Register new signal
            self.pending_signals[instId] = {
                "trigger_time": time.time(),
                "trigger_price": current_price,
                "limit_price": limit_price,
                "stable_count": 0,
                "last_check_time": time.time(),
            }

            logger.warning(
                f"📝 {instId} Buy signal registered, waiting for stability "
                f"(limit={limit_price:.6f}, current={current_price:.6f})"
            )
            return True

    def check_stability(self, instId: str) -> Optional[float]:
        """Check if price is stable and ready to buy

        Args:
            instId: Instrument ID

        Returns:
            Limit price if stable and ready to buy, None otherwise
        """
        with self.lock:
            if instId not in self.pending_signals:
                return None

            signal = self.pending_signals[instId]
            current_time = time.time()

            # Check if still in accelerated drop
            if self.is_accelerated_drop(instId):
                # Reset stable count
                signal["stable_count"] = 0
                signal["last_check_time"] = current_time
                logger.debug(
                    f"⏸️ {instId} Still in accelerated drop, resetting stability check"
                )
                return None

            # Check if enough time has passed since last check
            time_since_last_check = current_time - signal["last_check_time"]
            if time_since_last_check < 1.0:  # Check every 1 second
                return None

            # Get current price
            if instId not in self.price_history or not self.price_history[instId]:
                return None

            current_price = self.price_history[instId][-1][1]

            # Check if price drop rate is stable (not accelerating)
            price_1s_ago = self._get_price_at_time(instId, 1.0)
            if price_1s_ago and price_1s_ago > 0:
                drop_1s = (current_price - price_1s_ago) / price_1s_ago

                # If drop rate is within stable threshold, count as stable
                if drop_1s >= STABLE_DROP_THRESHOLD:
                    signal["stable_count"] += 1
                else:
                    # Reset count if drop is too fast
                    signal["stable_count"] = 0
                    logger.debug(
                        f"⏸️ {instId} Drop rate too fast: {drop_1s*100:.3f}% < "
                        f"{STABLE_DROP_THRESHOLD*100:.3f}%, resetting stability"
                    )

            signal["last_check_time"] = current_time

            # If we have enough consecutive stable checks, ready to buy
            if signal["stable_count"] >= STABILITY_CHECK_SECONDS:
                limit_price = signal["limit_price"]
                logger.warning(
                    f"✅ {instId} Price stable, ready to buy "
                    f"(stable for {signal['stable_count']}s, limit={limit_price:.6f})"
                )
                # Remove from pending signals
                del self.pending_signals[instId]
                return limit_price

            logger.debug(
                f"⏳ {instId} Stability check: {signal['stable_count']}/{STABILITY_CHECK_SECONDS} "
                f"(current={current_price:.6f})"
            )
            return None

    def clear_signal(self, instId: str):
        """Clear pending signal (e.g., after buy or cancel)"""
        with self.lock:
            if instId in self.pending_signals:
                del self.pending_signals[instId]
                logger.debug(f"🗑️ {instId} Cleared pending buy signal")

    def reset_crypto(self, instId: str):
        """Reset all data for a crypto"""
        with self.lock:
            if instId in self.price_history:
                del self.price_history[instId]
            if instId in self.pending_signals:
                del self.pending_signals[instId]
