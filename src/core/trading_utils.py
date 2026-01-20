#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trading Utility Functions
Common utility functions for trading operations
"""

import logging
import subprocess
import sys
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def play_sound(sound_type: str):
    """Play sound notification (buy or sell)"""
    try:
        if sys.platform == "darwin":
            if sound_type == "buy":
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Glass.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sound_type == "sell":
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Hero.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        elif sys.platform == "win32":
            import winsound

            if sound_type == "buy":
                winsound.Beep(800, 200)
            elif sound_type == "sell":
                winsound.Beep(600, 300)
        else:
            if sound_type == "buy":
                subprocess.Popen(
                    ["beep", "-f", "800", "-l", "200"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sound_type == "sell":
                subprocess.Popen(
                    ["beep", "-f", "600", "-l", "300"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    except Exception as e:
        logger.debug(f"Could not play sound: {e}")


def extract_base_currency(instId: str) -> str:
    """Extract base currency from instId (e.g., 'BTC-USDT' -> 'BTC')"""
    if "-" in instId:
        return instId.split("-")[0]
    return instId


def remove_crypto_from_system(
    instId: str,
    get_db_connection_func,
    crypto_limits: dict,
    current_prices: dict,
    reference_prices: dict,
    reference_price_fetch_time: dict,
    reference_price_fetch_attempts: dict,
    pending_buys: dict,
    active_orders: dict,
    lock,
    unsubscribe_from_websocket_func,
):
    """Remove crypto from hour_limit table, memory, and unsubscribe from WebSocket"""
    try:
        conn = get_db_connection_func()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM hour_limit WHERE inst_id = %s", (instId,))
            conn.commit()
            logger.warning(f"🗑️ Removed {instId} from hour_limit table")
            cur.close()
        finally:
            conn.close()

        with lock:
            if instId in crypto_limits:
                del crypto_limits[instId]
            if instId in current_prices:
                del current_prices[instId]
            if instId in reference_prices:
                del reference_prices[instId]
            if instId in reference_price_fetch_time:
                del reference_price_fetch_time[instId]
            if instId in reference_price_fetch_attempts:
                del reference_price_fetch_attempts[instId]
            if instId in pending_buys:
                del pending_buys[instId]
            if instId in active_orders:
                del active_orders[instId]
            logger.warning(f"🗑️ Removed {instId} from memory")

        unsubscribe_from_websocket_func(instId)
        return True
    except Exception as e:
        logger.error(f"Error removing {instId} from system: {e}")
        return False


def check_blacklist_before_buy(
    instId: str,
    auto_remove: bool,
    BlacklistManager_class: Optional[type],
    extract_base_currency_func,
    remove_crypto_from_system_func,
):
    """Check if crypto is blacklisted. If blacklisted and auto_remove=True, remove from system."""
    if BlacklistManager_class is None:
        logger.warning(
            f"BlacklistManager not available, skipping blacklist check for {instId}"
        )
        return False

    try:
        blacklist_manager = BlacklistManager_class(logger=logger)
        base_currency = extract_base_currency_func(instId)

        if blacklist_manager.is_blacklisted(base_currency):
            reason = blacklist_manager.get_blacklist_reason(base_currency)
            logger.warning(
                f"🚫 BLOCKED BUY: {instId} (base: {base_currency}) is blacklisted: {reason}"
            )

            if auto_remove:
                logger.warning(
                    f"🗑️ Removing {instId} from system (unsubscribe + remove from hour_limit)"
                )
                remove_crypto_from_system_func(instId)

            return True

        return False
    except Exception as e:
        logger.error(f"Error checking blacklist for {instId}: {e}")
        return False


def load_crypto_limits(get_db_connection_func) -> Dict[str, float]:
    """Load crypto limits from hour_limit table in database"""
    conn = None
    try:
        conn = get_db_connection_func()
        cur = conn.cursor()
        cur.execute("SELECT inst_id, limit_percent FROM hour_limit")
        rows = cur.fetchall()
        crypto_limits = {row[0]: float(row[1]) for row in rows}
        cur.close()
        conn.close()
        logger.warning(f"Loaded {len(crypto_limits)} crypto limits from database")
        return crypto_limits
    except Exception as e:
        logger.error(f"Failed to load crypto limits from database: {e}")
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return {}


def calculate_limit_price(
    reference_price: float, base_limit_percent: float, instId: str
) -> float:
    """Calculate limit buy price"""
    return reference_price * (base_limit_percent / 100.0)


def initialize_momentum_strategy_history(
    momentum_strategy: Optional[object],
    crypto_limits: dict,
    get_market_api_func,
):
    """Initialize momentum strategy with historical 1H candle data"""
    if momentum_strategy is None:
        return

    if not crypto_limits:
        logger.warning("⚠️ No crypto limits loaded, skipping history initialization")
        return

    logger.warning(
        f"📊 Initializing momentum strategy history for {len(crypto_limits)} cryptos..."
    )

    market_api = get_market_api_func()
    if not market_api:
        logger.error("❌ Market API not available, cannot initialize history")
        return

    from core.momentum_volume_strategy import M

    initialized_count = 0
    failed_count = 0
    vol_backfilled_count = 0

    # Calculate candles needed: max(M+1 for momentum, VOL_HISTORY_HOURS+24 for volatility)
    # OKX limit max is 300, which is exactly what we need
    vol_history_hours = momentum_strategy.VOL_HISTORY_HOURS
    candles_needed_momentum = M + 1  # 49 for momentum
    candles_needed_vol = (
        vol_history_hours + 24
    )  # 300 for volatility (276 hours + 24h rolling)
    candles_to_fetch = min(300, max(candles_needed_momentum, candles_needed_vol))

    for instId in crypto_limits.keys():
        try:
            # Fetch candles once (up to OKX limit of 300)
            result = market_api.get_candlesticks(
                instId=instId, bar="1H", limit=str(candles_to_fetch)
            )

            if result.get("code") == "0" and result.get("data"):
                candles = result["data"]
                if candles and len(candles) > 0:
                    # Step 1: Initialize momentum history (uses first M+1 candles)
                    momentum_success = momentum_strategy.initialize_history(
                        instId, candles, logger
                    )

                    if momentum_success:
                        initialized_count += 1

                        # Step 2: Backfill volatility history (uses all available candles)
                        try:
                            vol_success = momentum_strategy.backfill_volatility_history(
                                instId, candles, logger
                            )
                            if vol_success:
                                vol_backfilled_count += 1
                            else:
                                logger.debug(
                                    f"⚠️ {instId} Volatility backfill failed, "
                                    f"but momentum history initialized"
                                )
                        except Exception as vol_e:
                            logger.warning(
                                f"⚠️ {instId} Error backfilling volatility history: {vol_e}, "
                                f"but momentum history initialized"
                            )
                    else:
                        failed_count += 1
                else:
                    logger.debug(f"⚠️ {instId} No candle data returned")
                    failed_count += 1
            else:
                error_msg = result.get("msg", "Unknown error")
                logger.debug(f"⚠️ {instId} Failed to fetch history: {error_msg}")
                failed_count += 1

            import time

            time.sleep(0.1)
        except Exception as e:
            logger.error(f"❌ {instId} Error initializing history: {e}")
            failed_count += 1

    logger.warning(
        f"📊 History initialization complete: {initialized_count} momentum "
        f"succeeded, {vol_backfilled_count} volatility backfilled, "
        f"{failed_count} failed"
    )
