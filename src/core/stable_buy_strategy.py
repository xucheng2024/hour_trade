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

# Accelerated drop thresholds (base, before volatility adjustment)
DROP_1S_THRESHOLD = -0.0015  # -0.15% in 1 second
DROP_3S_THRESHOLD = -0.0030  # -0.30% in 3 seconds

# Stability check parameters
STABILITY_REQUIRED_SECONDS = 10  # Require stable for 10 seconds
STABLE_DROP_THRESHOLD = -0.0005  # -0.05% per second considered stable

# History and volatility windows
HISTORY_WINDOW_SECONDS = 15  # Keep recent history for stability checks
VOLATILITY_WINDOW_SECONDS = 10  # Window to estimate volatility
VOLATILITY_MIN_POINTS = 5
VOLATILITY_MULTIPLIER = 2.5


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
                self.price_history[instId] = deque()

            timestamp = time.time()
            self.price_history[instId].append((timestamp, price))
            self._prune_history(instId)

    def _prune_history(self, instId: str):
        if instId not in self.price_history:
            return
        cutoff = time.time() - HISTORY_WINDOW_SECONDS
        history = self.price_history[instId]
        while history and history[0][0] < cutoff:
            history.popleft()

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

    def _compute_volatility(self, instId: str) -> Optional[float]:
        if instId not in self.price_history:
            return None
        history = list(self.price_history[instId])
        if len(history) < VOLATILITY_MIN_POINTS:
            return None

        cutoff = time.time() - VOLATILITY_WINDOW_SECONDS
        window = [p for p in history if p[0] >= cutoff]
        if len(window) < VOLATILITY_MIN_POINTS:
            return None

        returns = []
        for i in range(1, len(window)):
            prev = window[i - 1][1]
            curr = window[i][1]
            if prev and prev > 0:
                returns.append((curr - prev) / prev)

        if len(returns) < 2:
            return None

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        return variance**0.5

    def _dynamic_threshold(self, instId: str, base_threshold: float) -> float:
        volatility = self._compute_volatility(instId)
        if volatility is None or volatility <= 0:
            return base_threshold
        dynamic = -VOLATILITY_MULTIPLIER * volatility
        return min(base_threshold, dynamic)

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

            current_price = history[-1][1]
            drop_1s_threshold = self._dynamic_threshold(instId, DROP_1S_THRESHOLD)
            drop_3s_threshold = self._dynamic_threshold(instId, DROP_3S_THRESHOLD)

            # Check 1 second drop
            price_1s_ago = self._get_price_at_time(instId, 1.0)
            if price_1s_ago and price_1s_ago > 0:
                drop_1s = (current_price - price_1s_ago) / price_1s_ago
                if drop_1s <= drop_1s_threshold:
                    logger.debug(
                        f"🚫 {instId} Accelerated drop detected (1s): "
                        f"{drop_1s*100:.3f}% <= {drop_1s_threshold*100:.3f}%"
                    )
                    return True

            # Check 3 second drop
            price_3s_ago = self._get_price_at_time(instId, 3.0)
            if price_3s_ago and price_3s_ago > 0:
                drop_3s = (current_price - price_3s_ago) / price_3s_ago
                if drop_3s <= drop_3s_threshold:
                    logger.debug(
                        f"🚫 {instId} Accelerated drop detected (3s): "
                        f"{drop_3s*100:.3f}% <= {drop_3s_threshold*100:.3f}%"
                    )
                    return True

            return False

    def register_buy_signal(self, instId: str, limit_price: float) -> bool:
        """Register a buy signal and start stability check

        Args:
            instId: Instrument ID
            limit_price: Limit price for buy

        Returns:
            True if signal registered, False if already registered or in accelerated
            drop
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
                "stable_seconds": 0.0,
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
                signal["stable_seconds"] = 0.0
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
                stable_threshold = self._dynamic_threshold(
                    instId, STABLE_DROP_THRESHOLD
                )

                # If drop rate is within stable threshold, count as stable
                if drop_1s >= stable_threshold:
                    signal["stable_seconds"] += time_since_last_check
                else:
                    # Reset count if drop is too fast
                    signal["stable_seconds"] = 0.0
                    logger.debug(
                        f"⏸️ {instId} Drop rate too fast: {drop_1s*100:.3f}% < "
                        f"{stable_threshold*100:.3f}%, resetting stability"
                    )

            signal["last_check_time"] = current_time

            # If we have enough stable time, ready to buy
            if signal["stable_seconds"] >= STABILITY_REQUIRED_SECONDS:
                # Recalculate limit price based on latest price
                limit_price = min(signal["limit_price"], current_price)
                logger.warning(
                    f"✅ {instId} Price stable, ready to buy "
                    f"(stable for {signal['stable_seconds']:.1f}s, "
                    f"limit={limit_price:.6f})"
                )
                # Remove from pending signals
                del self.pending_signals[instId]
                return limit_price

            logger.debug(
                f"⏳ {instId} Stability check: {signal['stable_seconds']:.1f}/"
                f"{STABILITY_REQUIRED_SECONDS}s "
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
