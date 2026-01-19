#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Price and Reference Price Management
Handles fetching and caching of hourly open prices for limit calculations
"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional

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
                    current_hour_start = (
                        datetime.now()
                        .replace(minute=0, second=0, microsecond=0)
                        .timestamp()
                    )
                    candle_hour_start = (
                        datetime.fromtimestamp(candle_ts)
                        .replace(minute=0, second=0, microsecond=0)
                        .timestamp()
                    )

                    # Check if the candle belongs to the current hour
                    # Allow small tolerance (±60 seconds) for timing differences
                    if abs(candle_hour_start - current_hour_start) <= 60:
                        ts_str = datetime.fromtimestamp(candle_ts).strftime("%H:%M:%S")
                        logger.info(
                            f"📊 {instId} current hour's open price: "
                            f"${hour_open:.6f} (ts={ts_str})"
                        )
                        return hour_open
                    else:
                        # Got different hour's candle
                        expected_hour = datetime.fromtimestamp(
                            current_hour_start
                        ).strftime("%H:00")
                        got_hour = datetime.fromtimestamp(candle_hour_start).strftime(
                            "%H:00"
                        )
                        logger.warning(
                            f"⚠️ {instId} got different hour's candle: "
                            f"expected hour={expected_hour}, "
                            f"got hour={got_hour}, open=${hour_open:.6f}"
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
