import base64
import hashlib
import hmac
import json
import math
import os
import time
import warnings
from datetime import datetime, timedelta
from typing import Dict, Optional

# Make numpy and pandas optional - they're only used in some functions
try:
    import numpy as np
    import pandas as pd
    HAS_NUMPY = True
except ImportError:
    np = None
    pd = None
    HAS_NUMPY = False

import requests
from okx.Account import AccountAPI
from okx.MarketData import MarketAPI
from okx.PublicData import PublicAPI
from okx.Trade import TradeAPI

warnings.filterwarnings("ignore", category=RuntimeWarning)
import logging
import sys
from pathlib import Path

# Add parent directory to path to import blacklist_manager
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from crypto_remote.blacklist_manager import BlacklistManager
except ImportError:
    # Fallback if import fails
    BlacklistManager = None

# Singleton instances for API clients
_trade_api: Optional[TradeAPI] = None
_market_api: Optional[MarketAPI] = None
_public_api: Optional[PublicAPI] = None

# Cache for instrument precision info
_instrument_precision_cache: Dict[str, Dict] = {}


# def pre_buy(instId,marketDataAPI):
#     count = 0

#     while True:
#         try:

#             result = marketDataAPI.get_ticker(
#                 instId=instId
#             )

#             last = float(result['data'][0]['last'])
#             bidPx = float(result['data'][0]['bidPx'])
#             logging.warning("prebuy:%s,%s,%s",instId,last,bidPx)
#         except Exception as e:
#             logging.error("rkt pre_buy:%s,%s",instId,e)
#             count = count + 1

#         if count>3 or last <= bidPx:
#             return bidPx

#         time.sleep(0.2)

# def pre_sell(instId,marketDataAPI):

#     candle_attempts = 3
#     for candle_attempt in range(candle_attempts):
#         try:
#             result = marketDataAPI.get_candlesticks(
#                 instId=instId,
#                 bar = '15m'
#             )
#             break
#         except Exception as e:
#             logging.error("sp sell candle:%s",e)
#             time.sleep(1)

#     cur_candle = result['data'][0]
#     cur_open = float(cur_candle[1])
#     cur_high = float(cur_candle[2])
#     cur_low = float(cur_candle[3])
#     cur_close = float(cur_candle[4])
#     last_candle = result['data'][1]
#     last_open = float(last_candle[1])
#     last_high = float(last_candle[2])
#     last_low = float(last_candle[3])
#     last_close = float(last_candle[4])

#     if cur_low < last_low: return -1
#     else:
#         return 1


def get_trade_api(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    api_passphrase: Optional[str] = None,
    trading_flag: str = "0",
    simulation_mode: bool = False,
) -> Optional[TradeAPI]:
    """Get or initialize TradeAPI instance (singleton)

    Args:
        api_key: OKX API key (if None, reads from env)
        api_secret: OKX API secret (if None, reads from env)
        api_passphrase: OKX API passphrase (if None, reads from env)
        trading_flag: Trading flag ("0"=production, "1"=demo)
        simulation_mode: If True, allows None if API keys not provided

    Returns:
        TradeAPI instance, or None if in simulation mode without API keys
    """
    global _trade_api
    if _trade_api is None:
        if api_key is None:
            api_key = os.getenv("OKX_API_KEY")
        if api_secret is None:
            api_secret = os.getenv("OKX_SECRET")
        if api_passphrase is None:
            api_passphrase = os.getenv("OKX_PASSPHRASE")

        if simulation_mode and not all([api_key, api_secret, api_passphrase]):
            logging.debug("Simulation mode: TradeAPI not initialized (no API keys)")
            return None
        try:
            _trade_api = TradeAPI(
                api_key, api_secret, api_passphrase, False, trading_flag
            )
        except Exception as e:
            if simulation_mode:
                logging.warning(
                    f"Simulation mode: TradeAPI init failed: {e}, continuing without it"
                )
                return None
            raise
    return _trade_api


def get_market_api(trading_flag: str = "0") -> MarketAPI:
    """Get or initialize MarketAPI instance (singleton)

    Args:
        trading_flag: Trading flag ("0"=production, "1"=demo)

    Returns:
        MarketAPI instance
    """
    global _market_api
    if _market_api is None:
        _market_api = MarketAPI(flag=trading_flag)
    return _market_api


def get_public_api(trading_flag: str = "0") -> PublicAPI:
    """Get or initialize PublicAPI instance (singleton)

    Args:
        trading_flag: Trading flag ("0"=production, "1"=demo)

    Returns:
        PublicAPI instance
    """
    global _public_api
    if _public_api is None:
        _public_api = PublicAPI(flag=trading_flag)
    return _public_api


def get_instrument_precision(
    instId: str, use_cache: bool = True, trading_flag: str = "0"
) -> Optional[Dict]:
    """Get instrument precision info (lotSz, tickSz, minSz) from OKX API
    Returns None if API call fails, falls back to format_number default behavior

    Args:
        instId: Instrument ID (e.g., 'BTC-USDT')
        use_cache: Whether to use cached result
        trading_flag: Trading flag ("0"=production, "1"=demo)

    Returns:
        Dict with precision info or None
    """
    global _instrument_precision_cache
    # Check cache first
    if use_cache and instId in _instrument_precision_cache:
        return _instrument_precision_cache[instId]

    try:
        api = get_public_api(trading_flag)
        result = api.get_instruments(instType="SPOT", instId=instId)

        if result.get("code") == "0" and result.get("data"):
            instruments = result["data"]
            if instruments and len(instruments) > 0:
                inst = instruments[0]
                tick_sz = inst.get("tickSz", "")
                lot_sz = inst.get("lotSz", "")
                min_sz = inst.get("minSz", "")

                # Calculate precision (decimal places)
                def count_decimal_places(s: str) -> int:
                    if "." in s:
                        return len(s.split(".")[-1].rstrip("0"))
                    return 0

                precision_info = {
                    "tickSz": tick_sz,
                    "tickPrecision": count_decimal_places(tick_sz),
                    "lotSz": lot_sz,
                    "lotPrecision": count_decimal_places(lot_sz),
                    "minSz": min_sz,
                    "minPrecision": count_decimal_places(min_sz),
                }

                # Cache the result
                _instrument_precision_cache[instId] = precision_info
                logging.debug(
                    f"📊 Cached instrument precision for {instId}: {precision_info}"
                )
                return precision_info
    except Exception as e:
        logging.debug(f"⚠️ Failed to get instrument precision for {instId}: {e}")

    return None


def format_number(number, instId: Optional[str] = None, trading_flag: str = "0"):
    """Format number according to OKX precision requirements
    If instId is provided, uses OKX instrument precision (lotSz) for better accuracy
    Falls back to heuristic precision if instrument info is not available

    Args:
        number: Number to format (price or size)
        instId: Optional instrument ID (e.g., 'BTC-USDT') to use instrument-specific precision
        trading_flag: Trading flag ("0"=production, "1"=demo)
    """
    number = float(number)

    # Try to use OKX instrument precision if instId is provided
    if instId:
        precision_info = get_instrument_precision(
            instId, use_cache=True, trading_flag=trading_flag
        )
        if precision_info:
            lot_precision = precision_info.get("lotPrecision", 0)
            lot_sz = float(precision_info.get("lotSz", "1"))

            # Round to lotSz increment
            if lot_sz > 0:
                rounded = round(number / lot_sz) * lot_sz
                # Format with appropriate precision
                if lot_precision > 0:
                    return f"{rounded:.{lot_precision}f}".rstrip("0").rstrip(".")
                else:
                    return f"{int(rounded)}"

    # Fallback to original heuristic precision
    if number > 100:
        number = int(number)
    elif number > 1:
        number = int(number * 100) / 100
    else:
        digit = int(-math.log(number, 10) + 1)
        scale_factor = (10**digit) * 100
        number = int(number * scale_factor) / scale_factor
        decimal_places = digit + 2
        formatted_number = f"{number:.{decimal_places}f}"
        return formatted_number
    return f"{number}"


def extract_base_currency(instId):
    """Extract base currency from instId (e.g., 'BTC-USDT' -> 'BTC')"""
    if "-" in instId:
        return instId.split("-")[0]
    return instId


def check_blacklist_before_buy(instId, strategy):
    """Check if crypto is blacklisted before buying."""
    if BlacklistManager is None:
        logging.warning(
            f"{strategy} BlacklistManager not available, skipping blacklist check"
        )
        return False

    try:
        blacklist_manager = BlacklistManager(logger=logging.getLogger(__name__))
        base_currency = extract_base_currency(instId)

        # Check if already blacklisted
        if blacklist_manager.is_blacklisted(base_currency):
            reason = blacklist_manager.get_blacklist_reason(base_currency)
            logging.warning(
                f"{strategy} 🚫 BLOCKED BUY: {instId} "
                f"(base: {base_currency}) is blacklisted: {reason}"
            )
            return True

        # If not blacklisted, return False to allow buy
        return False
    except Exception as e:
        logging.error(f"{strategy} Error checking blacklist for {instId}: {e}")
        # On error, allow buy (fail open) but log the error
        return False


def buy_market(instId, size, tradeAPI, strategy, conn, minutes):
    # Check blacklist before buying
    if check_blacklist_before_buy(instId, strategy):
        # Already blacklisted, block the buy
        return None

    size = format_number(size)
    max_attempts = 3

    failed_flag = 0

    for attempt in range(max_attempts):
        try:
            result = tradeAPI.place_order(
                instId=instId,
                tdMode="cash",
                side="buy",
                ordType="market",
                sz=size,
                tgtCcy="base_ccy",
            )

            result_msg = result["data"][0]["sMsg"]
            logging.warning("%s buy mrk:%s,%s,%s", strategy, instId, size, result_msg)
            if "failed" in result_msg:
                time.sleep(1)
                failed_flag = 1
                continue
            failed_flag = 0
            break
        except Exception as e:
            logging.error("%s buy mrk:%s,%s,%s", strategy, instId, size, e)
            failed_flag = 1

    if failed_flag > 0:
        return
    cur = conn.cursor()
    for attempt in range(max_attempts):
        try:
            now = datetime.now()
            ordId = result["data"][0]["ordId"]
            flag = strategy
            create_time = int(now.timestamp() * 1000)
            orderType = "mrk"
            state = ""
            price = ""
            size = ""

            sell_time = int((now + timedelta(minutes=minutes)).timestamp() * 1000)
            side = "buy"

            if ordId is None:
                return
            cur.execute(
                """INSERT INTO orders (instId, flag, ordId, create_time, orderType, state, price, size, sell_time,side)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    instId,
                    flag,
                    ordId,
                    create_time,
                    orderType,
                    state,
                    price,
                    size,
                    sell_time,
                    side,
                ),
            )
            conn.commit()

            logging.warning("%s buy mrk:db:%s,%s,%s", strategy, instId, ordId)

            break
        except Exception as e:
            logging.error("%s buy mrk:db:%s,%s,%s", strategy, instId, ordId, e)

    cur.close()
    return instId, ordId


def buy_limit(instId, buy_price, size, tradeAPI, strategy, conn, minutes):
    # Check blacklist before buying
    if check_blacklist_before_buy(instId, strategy):
        # Already blacklisted, block the buy
        return None

    buy_price = format_number(buy_price)
    size = format_number(size)
    max_attempts = 3
    failed_flag = 0

    for attempt in range(max_attempts):
        try:
            result = tradeAPI.place_order(
                instId=instId,
                tdMode="cash",
                side="buy",
                ordType="limit",
                px=buy_price,
                sz=size,
            )
            result_msg = result["data"][0]["sMsg"]
            main_msg = result["msg"]

            logging.warning(
                "%s buy limit:%s,%s,%s,%s,%s",
                strategy,
                instId,
                buy_price,
                size,
                result_msg,
                main_msg,
            )

            if "failed" in result_msg:
                failed_flag = 1
                continue
            failed_flag = 0
            break
        except Exception as e:
            logging.warning(
                "%s buy limit:%s,%s,%s,%s", strategy, instId, buy_price, size, e
            )
            failed_flag = 1

    if failed_flag > 0:
        return
    cur = conn.cursor()
    for attempt in range(max_attempts):
        try:
            now = datetime.now()
            ordId = result["data"][0]["ordId"]

            if ordId is None:
                return

            flag = strategy
            create_time = int(now.timestamp() * 1000)
            orderType = "limit"
            state = ""
            price = ""
            size = ""
            sell_time = int((now + timedelta(minutes=minutes)).timestamp() * 1000)
            side = "buy"

            cur.execute(
                """INSERT INTO orders (instId, flag, ordId, create_time, orderType, state, price, size, sell_time,side)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    instId,
                    flag,
                    ordId,
                    create_time,
                    orderType,
                    state,
                    price,
                    size,
                    sell_time,
                    side,
                ),
            )
            conn.commit()
            logging.warning("%s buy limit:db:%s,%s,%s", strategy, instId, ordId)

            break
        except Exception as e:
            logging.warning("%s buy limit db:%s,%s,%s", strategy, instId, ordId, e)
    cur.close()
    return instId, ordId


def sell_market(instId, ordId, size, tradeAPI, strategy, conn):
    size = format_number(size)
    max_attempts = 3
    failed_flag = 0

    for attempt in range(max_attempts):
        try:

            result = tradeAPI.place_order(
                instId=instId,
                tdMode="cash",
                side="sell",
                ordType="market",
                sz=size,
                tgtCcy="base_ccy",
            )

            result_msg = result["data"][0]["sMsg"]
            logging.warning("%s sell mrk:%s,%s,%s", strategy, instId, size, result_msg)

            if "failed" in result_msg:
                failed_flag = 1
                continue

            failed_flag = 0
            break
        except Exception as e:
            logging.error("%s sell mrk:%s,%s,%s", strategy, instId, size, e)
            failed_flag = 1

    if failed_flag > 0:
        return
    cur = conn.cursor()
    for attempts in range(max_attempts):
        try:
            new_state = "sold out"

            sql_statement = """
            UPDATE orders
            SET state = %s
            WHERE instId = %s AND ordId = %s;
            """
            cur.execute(sql_statement, (new_state, instId, ordId))
            conn.commit()
            logging.warning("%s sell mrk:db:%s,%s,%s", strategy, instId, ordId)

            break
        except Exception as e:
            logging.error("%s sell mrk db:%s,%s,%s", strategy, instId, ordId, e)

    cur.close()
    return instId, ordId
