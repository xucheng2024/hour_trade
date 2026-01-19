#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Price and Reference Price Management
Handles fetching and caching of hourly open prices for limit calculations
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from okx.MarketData import MarketAPI

logger = logging.getLogger(__name__)


class PriceManager:
    """Manages reference prices (hourly open prices) for limit calculations"""

    def __init__(self, market_api: MarketAPI, lock: threading.Lock):
        """Initialize PriceManager

        Args:
            market_api: MarketAPI instance
            lock: Thread lock for thread-safe operations
        """
        self.market_api = market_api
        self.lock = lock
        self.reference_prices: Dict[str, float] = {}
        self.reference_price_fetch_time: Dict[str, float] = {}
        self.reference_price_fetch_attempts: Dict[str, int] = {}

    def fetch_current_hour_open_price(self, instId: str) -> Optional[float]:
        """Fetch current hour's open price for a cryptocurrency

        Args:
            instId: Instrument ID

        Returns:
            Current hour's open price or None if failed
        """
        try:
            # Use 1H (1 hour) candlestick
            result = self.market_api.get_candlesticks(
                instId=instId, bar="1H", limit="1"
            )

            if result.get("code") == "0" and result.get("data"):
                data = result["data"]
                if data and len(data) > 0:
                    # Data format: [timestamp, open, high, low, close, volume, ...]
                    candle = data[0]
                    candle_ts = int(candle[0]) / 1000  # Convert ms to seconds
                    hour_open = float(candle[1])

                    # Verify the timestamp to ensure we got the current hour's candle
                    # ✅ FIX: Use UTC timezone for all comparisons (OKX timestamps are UTC)
                    current_hour_start_utc = datetime.now(timezone.utc).replace(
                        minute=0, second=0, microsecond=0
                    )
                    candle_hour_start_utc = datetime.fromtimestamp(
                        candle_ts, tz=timezone.utc
                    ).replace(minute=0, second=0, microsecond=0)

                    # Check if the candle belongs to the current hour
                    # Allow small tolerance (±60 seconds) for timing differences
                    time_diff_seconds = abs(
                        (candle_hour_start_utc - current_hour_start_utc).total_seconds()
                    )
                    if time_diff_seconds <= 60:
                        ts_str = candle_hour_start_utc.strftime("%H:%M:%S UTC")
                        logger.info(
                            f"📊 {instId} current hour's open price: "
                            f"${hour_open:.6f} (ts={ts_str})"
                        )
                        return hour_open
                    else:
                        # Got different hour's candle
                        expected_hour = current_hour_start_utc.strftime("%H:00 UTC")
                        got_hour = candle_hour_start_utc.strftime("%H:00 UTC")
                        logger.warning(
                            f"⚠️ {instId} got different hour's candle: "
                            f"expected hour={expected_hour}, "
                            f"got hour={got_hour}, open=${hour_open:.6f}, "
                            f"diff={time_diff_seconds:.0f}s"
                        )
                        return None
            else:
                error_msg = result.get("msg", "Unknown error")
                logger.warning(
                    f"⚠️ Failed to get current hour's open for {instId}: {error_msg}"
                )
        except Exception as e:
            logger.error(f"Error fetching current hour's open for {instId}: {e}")
        return None

    def initialize_reference_prices(self, crypto_limits: Dict[str, float]):
        """Initialize reference prices (current hour's open) for all cryptos

        Args:
            crypto_limits: Dict of instId -> limit_percent
        """
        logger.warning(
            "🔄 Initializing reference prices (current hour's open) for all cryptos..."
        )
        count = 0
        for instId in crypto_limits.keys():
            open_price = self.fetch_current_hour_open_price(instId)
            if open_price and open_price > 0:
                with self.lock:
                    self.reference_prices[instId] = open_price
                    # Reset fetch attempts on successful initialization
                    self.reference_price_fetch_attempts[instId] = 0
                count += 1
            time.sleep(0.1)  # Rate limiting
        logger.warning(
            f"✅ Initialized {count}/{len(crypto_limits)} reference prices "
            f"(current hour's open)"
        )

    def get_reference_price(self, instId: str) -> Optional[float]:
        """Get cached reference price for an instrument

        Args:
            instId: Instrument ID

        Returns:
            Reference price or None if not available
        """
        with self.lock:
            return self.reference_prices.get(instId)

    def set_reference_price(self, instId: str, price: float):
        """Set reference price for an instrument

        Args:
            instId: Instrument ID
            price: Reference price
        """
        with self.lock:
            self.reference_prices[instId] = price

    def remove_reference_price(self, instId: str):
        """Remove reference price for an instrument

        Args:
            instId: Instrument ID
        """
        with self.lock:
            if instId in self.reference_prices:
                del self.reference_prices[instId]
            if instId in self.reference_price_fetch_time:
                del self.reference_price_fetch_time[instId]
            if instId in self.reference_price_fetch_attempts:
                del self.reference_price_fetch_attempts[instId]

    def fetch_2h_ago_close_price(self, instId: str) -> Optional[float]:
        """Fetch closing price from 2 hours ago

        Args:
            instId: Instrument ID

        Returns:
            Closing price from 2 hours ago or None if failed
        """
        try:
            # Fetch 3 candles to ensure we get the one from 2 hours ago
            result = self.market_api.get_candlesticks(
                instId=instId, bar="1H", limit="3"
            )

            if result.get("code") == "0" and result.get("data"):
                data = result["data"]
                if data and len(data) >= 2:
                    # Data is ordered from newest to oldest
                    # data[0] = current hour, data[1] = 1 hour ago, data[2] = 2 hours ago
                    candle_2h_ago = data[2] if len(data) >= 3 else data[1]
                    candle_ts = int(candle_2h_ago[0]) / 1000  # Convert ms to seconds
                    close_price = float(candle_2h_ago[4])  # Close price

                    # Verify the timestamp is approximately 2 hours ago
                    # ✅ FIX: Use UTC timezone for all comparisons (OKX timestamps are UTC)
                    current_hour_start_utc = datetime.now(timezone.utc).replace(
                        minute=0, second=0, microsecond=0
                    )
                    candle_hour_start_utc = datetime.fromtimestamp(
                        candle_ts, tz=timezone.utc
                    ).replace(minute=0, second=0, microsecond=0)
                    hours_diff = (
                        current_hour_start_utc - candle_hour_start_utc
                    ).total_seconds() / 3600

                    # Allow tolerance: should be between 1.5 and 2.5 hours ago
                    if 1.5 <= hours_diff <= 2.5:
                        ts_str = candle_hour_start_utc.strftime("%H:00 UTC")
                        logger.debug(
                            f"📊 {instId} 2h ago close price: "
                            f"${close_price:.6f} (hour={ts_str}, diff={hours_diff:.1f}h)"
                        )
                        return close_price
                    else:
                        logger.warning(
                            f"⚠️ {instId} got unexpected hour candle: "
                            f"expected ~2h ago, got {hours_diff:.1f}h ago "
                            f"(current_utc={current_hour_start_utc.strftime('%H:00 UTC')}, "
                            f"candle_utc={candle_hour_start_utc.strftime('%H:00 UTC')})"
                        )
                        return None
            else:
                error_msg = result.get("msg", "Unknown error")
                logger.warning(
                    f"⚠️ Failed to get 2h ago close for {instId}: {error_msg}"
                )
        except Exception as e:
            logger.error(f"Error fetching 2h ago close for {instId}: {e}")
        return None

    def check_2h_gain_filter(
        self, instId: str, current_open_price: float, gain_threshold: float = 5.0
    ) -> Tuple[bool, Optional[float]]:
        """Check if 2-hour gain exceeds threshold (skip buy if gain > threshold)

        Args:
            instId: Instrument ID
            current_open_price: Current hour's open price
            gain_threshold: Gain threshold in percentage (default: 5.0%)

        Returns:
            Tuple of (should_skip_buy, gain_percentage)
            should_skip_buy: True if gain > threshold (should skip buy)
            gain_percentage: Calculated gain percentage or None if failed
        """
        close_2h_ago = self.fetch_2h_ago_close_price(instId)
        if close_2h_ago is None or close_2h_ago <= 0:
            # If we can't get the 2h ago price, allow buy (fail open)
            logger.debug(
                f"⚠️ {instId} Cannot get 2h ago close price, allowing buy (fail open)"
            )
            return False, None

        gain_pct = ((current_open_price - close_2h_ago) / close_2h_ago) * 100
        should_skip = gain_pct > gain_threshold

        if should_skip:
            logger.warning(
                f"🚫 {instId} SKIP BUY: 2h gain {gain_pct:.2f}% > {gain_threshold}% "
                f"(current_open=${current_open_price:.6f} vs 2h_close=${close_2h_ago:.6f})"
            )
        else:
            logger.debug(
                f"✅ {instId} 2h gain check passed: {gain_pct:.2f}% <= {gain_threshold}%"
            )

        return should_skip, gain_pct
