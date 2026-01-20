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
    """Check if crypto is blacklisted.
    If blacklisted and auto_remove=True, remove from system.
    """
    if BlacklistManager_class is None:
        return False

    try:
        blacklist_manager = BlacklistManager_class(logger=logger)
        base_currency = extract_base_currency_func(instId)

        if blacklist_manager.is_blacklisted(base_currency):
            reason = blacklist_manager.get_blacklist_reason(base_currency)
            logger.warning(
                f"🚫 BLOCKED BUY: {instId} (base: {base_currency}) "
                f"is blacklisted: {reason}"
            )

            if auto_remove:
                logger.warning(
                    f"🗑️ Removing {instId} from system "
                    f"(unsubscribe + remove from hour_limit)"
                )
                remove_crypto_from_system_func(instId)

            return True

        return False
    except Exception as e:
        logger.error(f"❌ Error checking blacklist for {instId}: {e}")
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
