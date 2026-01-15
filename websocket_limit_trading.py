#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real-time Trading System using WebSocket
Subscribes to OKX tickers and candles, buys at limit prices, sells at next hour close
"""

import json
import logging
import math
import os
import subprocess
import sys
import threading
import time
import uuid
import warnings
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Dict, Optional

import psycopg2
import psycopg2.extras
import websocket
from dotenv import load_dotenv
from okx.MarketData import MarketAPI
from okx.Trade import TradeAPI

# Add src directory to path to import blacklist_manager
sys.path.insert(0, str(Path(__file__).parent / "src"))
try:
    from crypto_remote.blacklist_manager import BlacklistManager
except ImportError:
    BlacklistManager = None

warnings.filterwarnings("ignore", category=RuntimeWarning)

# Load environment variables
load_dotenv()

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIMITS_FILE = os.path.join(BASE_DIR, "valid_crypto_limits.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "websocket_limit_trading.log")

# Database Configuration - Use PostgreSQL instead of SQLite
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

# API Configuration - Load from environment variables
API_KEY = os.getenv("OKX_API_KEY")
API_SECRET = os.getenv("OKX_SECRET")
API_PASSPHRASE = os.getenv("OKX_PASSPHRASE")
TRADING_FLAG = "0"  # 0=production, 1=demo

if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
    raise ValueError(
        "OKX API credentials not found in environment variables. Please set OKX_API_KEY, OKX_SECRET, and OKX_PASSPHRASE"
    )

# Trading Configuration
TRADING_AMOUNT_USDT = int(
    os.getenv("TRADING_AMOUNT_USDT", "100")
)  # Amount per trade in USDT
STRATEGY_NAME = "hourly_limit_ws"
SIMULATION_MODE = (
    os.getenv("SIMULATION_MODE", "true").lower() == "true"
)  # True=simulation (record only, no real trading), False=real trading

# Setup logging
# TimedRotatingFileHandler: rotate daily, keep 3 days
file_handler = TimedRotatingFileHandler(
    LOG_FILE,
    when="midnight",
    interval=1,
    backupCount=3,
    encoding="utf-8",
)
file_handler.suffix = "%Y-%m-%d"
console_handler = logging.StreamHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[file_handler, console_handler],
)
logger = logging.getLogger(__name__)

# Global variables
crypto_limits: Dict[str, float] = {}  # instId -> limit_percent
current_prices: Dict[str, float] = {}  # instId -> last_price
pending_buys: Dict[str, bool] = {}  # instId -> has_pending_buy
active_orders: Dict[str, Dict] = (
    {}
)  # instId -> {ordId, buy_price, buy_time, next_hour_close_time}
lock = threading.Lock()

# WebSocket connections for unsubscribe
ticker_ws: Optional[websocket.WebSocketApp] = None
candle_ws: Optional[websocket.WebSocketApp] = None
ws_lock = threading.Lock()

# Initialize TradeAPI instance (singleton pattern)
trade_api: Optional[TradeAPI] = None


def get_trade_api() -> TradeAPI:
    """Get or initialize TradeAPI instance (singleton)"""
    global trade_api
    if trade_api is None:
        trade_api = TradeAPI(API_KEY, API_SECRET, API_PASSPHRASE, False, TRADING_FLAG)
    return trade_api


def get_db_connection(max_retries=3, retry_delay=1):
    """Get PostgreSQL database connection with retry logic"""
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
            # Test connection
            cur = conn.cursor()
            try:
                cur.execute("SELECT 1")
            finally:
                cur.close()
            return conn
        except (psycopg2.Error, psycopg2.OperationalError) as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
            else:
                logger.error(
                    f"Database connection failed after {max_retries} attempts: {e}"
                )
                raise


def play_sound(sound_type: str):
    """Play sound notification (buy or sell)

    Args:
        sound_type: 'buy' or 'sell'
    """
    try:
        if sys.platform == "darwin":  # macOS
            if sound_type == "buy":
                # Play buy sound (Glass sound for buy)
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Glass.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sound_type == "sell":
                # Play sell sound (Hero sound for sell)
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Hero.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        elif sys.platform == "win32":  # Windows
            import winsound

            if sound_type == "buy":
                winsound.Beep(800, 200)  # Higher pitch for buy
            elif sound_type == "sell":
                winsound.Beep(600, 300)  # Lower pitch for sell
        else:  # Linux
            # Try to use beep or speaker-test
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
        # Silently fail if sound can't be played
        logger.debug(f"Could not play sound: {e}")


def format_number(number):
    """Format number according to OKX precision requirements"""
    number = float(number)
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


def remove_crypto_from_system(instId: str):
    """Remove crypto from hour_limit table, memory, and unsubscribe from WebSocket"""
    try:
        # Remove from database hour_limit table
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM hour_limit WHERE inst_id = %s", (instId,))
            conn.commit()
            logger.warning(f"🗑️ Removed {instId} from hour_limit table")
            cur.close()
        finally:
            conn.close()

        # Remove from memory
        with lock:
            if instId in crypto_limits:
                del crypto_limits[instId]
            if instId in current_prices:
                del current_prices[instId]
            if instId in pending_buys:
                del pending_buys[instId]
            if instId in active_orders:
                del active_orders[instId]
            logger.warning(f"🗑️ Removed {instId} from memory")

        # Unsubscribe from WebSocket
        unsubscribe_from_websocket(instId)

        return True
    except Exception as e:
        logger.error(f"Error removing {instId} from system: {e}")
        return False


def unsubscribe_from_websocket(instId: str):
    """Unsubscribe from ticker and candle WebSocket for a specific crypto"""
    try:
        with ws_lock:
            # Unsubscribe from ticker
            if ticker_ws:
                try:
                    msg = {
                        "op": "unsubscribe",
                        "args": [{"channel": "tickers", "instId": instId}],
                    }
                    ticker_ws.send(json.dumps(msg))
                    logger.warning(f"📡 Unsubscribed ticker for {instId}")
                except Exception as e:
                    logger.error(f"Error unsubscribing ticker for {instId}: {e}")

            # Unsubscribe from candle
            if candle_ws:
                try:
                    msg = {
                        "op": "unsubscribe",
                        "args": [{"channel": "candle1H", "instId": instId}],
                    }
                    candle_ws.send(json.dumps(msg))
                    logger.warning(f"📡 Unsubscribed candle for {instId}")
                except Exception as e:
                    logger.error(f"Error unsubscribing candle for {instId}: {e}")
    except Exception as e:
        logger.error(f"Error in unsubscribe_from_websocket for {instId}: {e}")


def check_blacklist_before_buy(instId, auto_remove=True):
    """Check if crypto is blacklisted. If blacklisted and auto_remove=True,
    remove from system."""
    if BlacklistManager is None:
        logger.warning(
            f"BlacklistManager not available, skipping blacklist check " f"for {instId}"
        )
        return False

    try:
        blacklist_manager = BlacklistManager(logger=logger)
        base_currency = extract_base_currency(instId)

        # Check if already blacklisted
        if blacklist_manager.is_blacklisted(base_currency):
            reason = blacklist_manager.get_blacklist_reason(base_currency)
            logger.warning(
                f"🚫 BLOCKED BUY: {instId} (base: {base_currency}) "
                f"is blacklisted: {reason}"
            )

            # Remove from system: unsubscribe and remove from hour_limit
            if auto_remove:
                logger.warning(
                    f"🗑️ Removing {instId} from system "
                    f"(unsubscribe + remove from hour_limit)"
                )
                remove_crypto_from_system(instId)

            return True

        # If not blacklisted, return False to allow buy
        return False
    except Exception as e:
        logger.error(f"Error checking blacklist for {instId}: {e}")
        # On error, allow buy (fail open) but log the error
        return False


def load_crypto_limits():
    """Load crypto limits from hour_limit table in database"""
    global crypto_limits
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Load limits from hour_limit table
        cur.execute("SELECT inst_id, limit_percent FROM hour_limit")
        rows = cur.fetchall()

        crypto_limits = {row[0]: float(row[1]) for row in rows}

        cur.close()
        conn.close()

        logger.warning(f"Loaded {len(crypto_limits)} crypto limits from database")
        return True
    except Exception as e:
        logger.error(f"Failed to load crypto limits from database: {e}")
        return False


def calculate_limit_price(current_price: float, limit_percent: float) -> float:
    """Calculate limit buy price based on limit_percent"""
    return current_price * (limit_percent / 100.0)


def buy_limit_order(
    instId: str, limit_price: float, size: float, tradeAPI: TradeAPI, conn
) -> Optional[str]:
    """Place limit buy order and record in database"""
    # Check blacklist before buying
    if check_blacklist_before_buy(instId):
        # Already blacklisted, block the buy
        return None

    buy_price = format_number(limit_price)
    size = format_number(size)

    if SIMULATION_MODE:
        # Simulation mode: generate fake ordId with strategy prefix for isolation
        ordId = f"HLW-SIM-{uuid.uuid4().hex[:12]}"  # HLW = Hourly Limit WS
        amount_usdt = float(buy_price) * float(size)
        logger.warning(
            f"🛒 [SIM] BUY: {instId}, price={buy_price}, size={size}, amount={amount_usdt:.2f} USDT, ordId={ordId}"
        )
    else:
        # Real trading mode
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

                # Check API response code (best practice from crypto_remote)
                if result.get("code") == "0":
                    order_data = result.get("data", [{}])[0]
                    ordId = order_data.get("ordId")
                    result_msg = order_data.get("sMsg", "")

                    if ordId:
                        amount_usdt = float(buy_price) * float(size)
                        logger.warning(
                            f"🛒 BUY ORDER: {instId}, price={buy_price}, size={size}, amount={amount_usdt:.2f} USDT, ordId={ordId}"
                        )
                        failed_flag = 0
                        break
                    else:
                        logger.error(
                            f"{STRATEGY_NAME} buy limit: {instId}, no ordId in response"
                        )
                        failed_flag = 1
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{STRATEGY_NAME} buy limit failed: {instId}, code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{STRATEGY_NAME} buy limit error: {instId}, {e}")
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(1)

        if failed_flag > 0:
            return None

    # Record in database
    cur = conn.cursor()
    try:
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        create_time = int(now.timestamp() * 1000)
        sell_time = int(next_hour.timestamp() * 1000)

        # In simulation mode, assume order is filled immediately
        # In real trading mode, state starts as "" and will be updated by timeout check
        order_state = "filled" if SIMULATION_MODE else ""

        cur.execute(
            """INSERT INTO orders (instId, flag, ordId, create_time, orderType, state, price, size, sell_time, side)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                instId,
                STRATEGY_NAME,
                ordId,
                create_time,
                "limit",
                order_state,
                buy_price,
                size,
                sell_time,
                "buy",
            ),
        )
        conn.commit()
        amount_usdt = float(buy_price) * float(size)
        logger.warning(
            f"✅ BUY SAVED: {instId}, price={buy_price}, size={size}, amount={amount_usdt:.2f} USDT, ordId={ordId}"
        )

        # Play buy sound
        play_sound("buy")

        return ordId
    except Exception as e:
        logger.error(f"{STRATEGY_NAME} buy limit DB error: {instId}, {ordId}, {e}")
        conn.rollback()
    finally:
        cur.close()

    return ordId


def sell_market_order(instId: str, ordId: str, size: float, tradeAPI: TradeAPI, conn):
    """Place market sell order"""
    size = format_number(size)

    # Get sell price from current_prices (for simulation) or actual trade
    with lock:
        sell_price = current_prices.get(instId, 0.0)

    if SIMULATION_MODE:
        # Simulation mode: skip actual trading, use current price as sell price
        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"💰 [SIM] SELL: {instId}, price={sell_price:.6f}, size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
    else:
        # Real trading mode
        max_attempts = 3
        failed_flag = 0

        for attempt in range(max_attempts):
            try:
                result = tradeAPI.place_order(
                    instId=instId,
                    tdMode="cash",
                    side="sell",
                    ordType="market",
                    sz=str(
                        size
                    ),  # Use string format (best practice from crypto_remote)
                    tgtCcy="base_ccy",  # Explicitly specify (best practice)
                )

                # Check API response code (best practice from crypto_remote)
                if result.get("code") == "0":
                    order_data = result.get("data", [{}])[0]
                    order_id = order_data.get("ordId", "N/A")
                    sell_amount_usdt = (
                        float(sell_price) * float(size) if sell_price > 0 else 0
                    )
                    logger.warning(
                        f"💰 SELL ORDER: {instId}, price={sell_price:.6f}, size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={order_id}"
                    )
                    failed_flag = 0
                    break
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{STRATEGY_NAME} sell market failed: {instId}, code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{STRATEGY_NAME} sell market error: {instId}, {e}")
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(1)

        if failed_flag > 0:
            return

    # Update database
    cur = conn.cursor()
    try:
        # Format sell price for database
        sell_price_str = format_number(sell_price) if sell_price > 0 else ""

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s WHERE instId = %s AND ordId = %s AND flag = %s",
            ("sold out", sell_price_str, instId, ordId, STRATEGY_NAME),
        )
        conn.commit()
        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"✅ SELL SAVED: {instId}, price={sell_price_str}, size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )

        # Play sell sound
        play_sound("sell")
    except Exception as e:
        logger.error(f"{STRATEGY_NAME} sell market DB error: {instId}, {ordId}, {e}")
        conn.rollback()
    finally:
        cur.close()


def on_ticker_message(ws, msg_string):
    """Handle ticker WebSocket messages"""
    if msg_string == "pong":
        return

    try:
        m = json.loads(msg_string)
        ev = m.get("event")
        data = m.get("data")

        if ev == "error":
            logger.error(f"Ticker WebSocket error: {msg_string}")
        elif ev in ["subscribe", "unsubscribe"]:
            logger.info(f"Ticker {ev}: {msg_string}")
        elif data and isinstance(data, list):
            for ticker in data:
                instId = ticker.get("instId")
                if instId in crypto_limits:
                    last_price = float(ticker.get("last", 0))
                    if last_price > 0:
                        with lock:
                            current_prices[instId] = last_price

                            # Check if we should buy
                            if (
                                instId not in pending_buys
                                and instId not in active_orders
                            ):
                                limit_percent = crypto_limits[instId]
                                limit_price = calculate_limit_price(
                                    last_price, limit_percent
                                )

                                if last_price <= limit_price:
                                    logger.warning(
                                        f"🚀 BUY SIGNAL: {instId}, price={last_price:.6f} <= limit={limit_price:.6f} ({limit_percent}%)"
                                    )
                                    pending_buys[instId] = True
                                    # Trigger buy in separate thread to avoid blocking
                                    # Blacklist check will happen in process_buy_signal
                                    threading.Thread(
                                        target=process_buy_signal,
                                        args=(instId, limit_price),
                                        daemon=True,
                                    ).start()
    except Exception as e:
        logger.error(f"Ticker message error: {msg_string}, {e}")


def check_and_cancel_unfilled_order_after_timeout(
    instId: str, ordId: str, tradeAPI: TradeAPI
):
    """Check order status after 1 minute timeout, cancel if not filled"""
    # Skip timeout check in simulation mode (orders are virtual)
    if SIMULATION_MODE or ordId.startswith("HLW-SIM-"):
        return

    try:
        time.sleep(60)  # Wait 1 minute

        # Check if order still exists in active_orders
        with lock:
            if (
                instId not in active_orders
                or active_orders[instId].get("ordId") != ordId
            ):
                # Order already processed or removed
                return

            # Check order status
            try:
                result = tradeAPI.get_order(instId=instId, ordId=ordId)
                if result and result.get("data") and len(result["data"]) > 0:
                    order_data = result["data"][0]
                    acc_fill_sz = order_data.get("accFillSz", "0")
                    fill_px = order_data.get("fillPx", "0")
                    state = order_data.get("state", "")
                    filled_size = (
                        float(acc_fill_sz) if acc_fill_sz and acc_fill_sz != "" else 0.0
                    )
                    is_filled = filled_size > 0 or state in [
                        "filled",
                        "partially_filled",
                    ]

                    if not is_filled:
                        # Order not filled after 1 minute, cancel it
                        tradeAPI.cancel_order(instId=instId, ordId=ordId)
                        logger.warning(
                            f"{STRATEGY_NAME} Canceled unfilled order after 1 minute: {instId}, ordId={ordId}"
                        )

                        # Update database
                        conn = get_db_connection()
                        try:
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE orders SET state = %s WHERE instId = %s AND ordId = %s AND flag = %s",
                                ("canceled", instId, ordId, STRATEGY_NAME),
                            )
                            conn.commit()
                            cur.close()
                        finally:
                            conn.close()

                        # Remove from active_orders
                        with lock:
                            if instId in active_orders:
                                del active_orders[instId]
                    else:
                        # ✅ FIX: Order is filled, update database with actual fill info
                        logger.warning(
                            f"{STRATEGY_NAME} Order filled within 1 minute: {instId}, ordId={ordId}, fillSize={acc_fill_sz}, fillPrice={fill_px}"
                        )

                        # Update database with filled status and actual fill data
                        conn = get_db_connection()
                        try:
                            cur = conn.cursor()
                            cur.execute(
                                """UPDATE orders 
                                   SET state = %s, size = %s, price = %s 
                                   WHERE instId = %s AND ordId = %s AND flag = %s""",
                                (
                                    "filled",
                                    acc_fill_sz,
                                    fill_px,
                                    instId,
                                    ordId,
                                    STRATEGY_NAME,
                                ),
                            )
                            conn.commit()

                            # Update active_orders with actual filled size
                            with lock:
                                if instId in active_orders:
                                    active_orders[instId]["filled_size"] = filled_size
                                    active_orders[instId]["fill_price"] = (
                                        float(fill_px) if fill_px else 0.0
                                    )

                            cur.close()
                        finally:
                            conn.close()
            except Exception as e:
                logger.error(
                    f"{STRATEGY_NAME} Error checking order status after timeout {instId}, {ordId}: {e}"
                )
    except Exception as e:
        logger.error(f"{STRATEGY_NAME} Error in timeout check {instId}, {ordId}: {e}")


def process_buy_signal(instId: str, limit_price: float):
    """Process buy signal in separate thread"""
    try:
        # Check blacklist before processing buy signal
        if check_blacklist_before_buy(instId):
            logger.warning(f"🚫 Skipping buy signal for {instId} - blacklisted")
            with lock:
                if instId in pending_buys:
                    del pending_buys[instId]
            return

        # Get trade API instance
        api = get_trade_api()

        # Calculate size
        size = TRADING_AMOUNT_USDT / limit_price

        # Place limit buy order
        conn = get_db_connection()
        try:
            ordId = buy_limit_order(instId, limit_price, size, api, conn)
            if ordId:
                with lock:
                    if instId in pending_buys:
                        del pending_buys[instId]
                    now = datetime.now()
                    next_hour = now.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)
                    active_orders[instId] = {
                        "ordId": ordId,
                        "buy_price": limit_price,
                        "buy_time": now,
                        "next_hour_close_time": next_hour,
                    }
                    logger.warning(
                        f"📊 ACTIVE ORDER: {instId}, ordId={ordId}, buy_price={limit_price:.6f}, sell_time={next_hour.strftime('%Y-%m-%d %H:%M:%S')}"
                    )

                    # Start 1-minute timeout check thread (only in real trading mode)
                    # In simulation mode, orders are assumed to be filled immediately
                    if not SIMULATION_MODE:
                        threading.Thread(
                            target=check_and_cancel_unfilled_order_after_timeout,
                            args=(instId, ordId, api),
                            daemon=True,
                        ).start()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_buy_signal error: {instId}, {e}")
        with lock:
            if instId in pending_buys:
                del pending_buys[instId]


def on_candle_message(ws, msg_string):
    """Handle candle WebSocket messages"""
    if msg_string == "pong":
        return

    try:
        m = json.loads(msg_string)
        ev = m.get("event")
        data = m.get("data")
        arg = m.get("arg", {})

        if ev == "error":
            logger.error(f"Candle WebSocket error: {msg_string}")
        elif ev in ["subscribe", "unsubscribe"]:
            logger.info(f"Candle {ev}: {msg_string}")
        elif data and isinstance(data, list) and len(data) > 0:
            channel = arg.get("channel", "")
            if "candle1H" in channel:
                instId = arg.get("instId")
                candle_data = data[
                    0
                ]  # Latest candle [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                # candle_data is a list: [timestamp, open, high, low, close, volume, ...]
                if isinstance(candle_data, list) and len(candle_data) >= 9:
                    confirm = str(candle_data[8])  # confirm is at index 8
                    # 'confirm' = '1' means candle is confirmed (closed)
                    if confirm == "1" and instId in active_orders:
                        # This hour's candle just closed, sell the position
                        close_price = (
                            float(candle_data[4]) if len(candle_data) > 4 else 0
                        )
                        logger.warning(
                            f"🕐 KLINE CONFIRMED: {instId}, close_price={close_price:.6f}, trigger SELL"
                        )
                        threading.Thread(
                            target=process_sell_signal, args=(instId,), daemon=True
                        ).start()
    except Exception as e:
        logger.error(f"Candle message error: {msg_string}, {e}")


def process_sell_signal(instId: str):
    """Process sell signal at next hour close"""
    try:
        with lock:
            if instId not in active_orders:
                logger.info(f"{STRATEGY_NAME} No active order for {instId}")
                return
            order_info = active_orders[instId].copy()
            ordId = order_info["ordId"]

        # Get trade API instance
        api = get_trade_api()

        # ✅ FIX: Check order state and prevent duplicate sells
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            try:
                # Query state and size together to validate order
                cur.execute(
                    "SELECT state, size FROM orders WHERE instId = %s AND ordId = %s AND flag = %s",
                    (instId, ordId, STRATEGY_NAME),
                )
                row = cur.fetchone()

                if not row:
                    logger.error(f"{STRATEGY_NAME} Order not found: {instId}, {ordId}")
                    with lock:
                        if instId in active_orders:
                            del active_orders[instId]
                    return

                db_state = row[0] if row[0] else ""
                db_size = row[1] if row[1] else "0"

                # Prevent duplicate sells - check if already sold
                if db_state == "sold out":
                    logger.warning(f"{STRATEGY_NAME} Already sold: {instId}, {ordId}")
                    with lock:
                        if instId in active_orders:
                            del active_orders[instId]
                    return

                # Verify order was filled before selling
                if db_state not in ["filled", ""] or not db_size or db_size == "0":
                    logger.warning(
                        f"{STRATEGY_NAME} Order not filled: {instId}, {ordId}, state={db_state}, size={db_size}"
                    )
                    with lock:
                        if instId in active_orders:
                            del active_orders[instId]
                    return

                size = float(db_size)
            finally:
                cur.close()

            # Place market sell order
            sell_market_order(instId, ordId, size, api, conn)

            # Remove from active orders AFTER successful sell
            with lock:
                if instId in active_orders:
                    del active_orders[instId]
                    logger.warning(
                        f"{STRATEGY_NAME} Sold and removed: {instId}, {ordId}"
                    )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_sell_signal error: {instId}, {e}")
        # Clean up on error to prevent stuck orders
        with lock:
            if instId in active_orders:
                del active_orders[instId]


def ticker_open(ws):
    """Handle ticker WebSocket connection open"""
    logger.warning("Ticker WebSocket opened")
    symbols = list(crypto_limits.keys())
    if symbols:
        # Subscribe to tickers (split into batches if too many)
        batch_size = 100
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            msg = {
                "op": "subscribe",
                "args": [{"channel": "tickers", "instId": instId} for instId in batch],
            }
            ws.send(json.dumps(msg))
            time.sleep(0.1)  # Rate limiting
        logger.warning(f"Subscribed to {len(symbols)} tickers")
    else:
        logger.error("No symbols to subscribe!")


def candle_open(ws):
    """Handle candle WebSocket connection open"""
    logger.warning("Candle WebSocket opened")
    symbols = list(crypto_limits.keys())
    if symbols:
        # Subscribe to 1H candles
        msg = {
            "op": "subscribe",
            "args": [{"channel": "candle1H", "instId": instId} for instId in symbols],
        }
        ws.send(json.dumps(msg))
        logger.warning(f"Subscribed to {len(symbols)} 1H candles")
    else:
        logger.error("No symbols to subscribe!")


def connect_websocket(url, on_message, on_open, ws_type="ticker"):
    """Connect to WebSocket with reconnection logic and exponential backoff"""
    global ticker_ws, candle_ws
    reconnect_delay = 1
    max_delay = 60

    while True:
        try:

            def on_close_handler(ws, close_status_code=None, close_msg=None):
                """Handle WebSocket close event"""
                global ticker_ws, candle_ws
                with ws_lock:
                    if ws_type == "ticker":
                        ticker_ws = None
                    elif ws_type == "candle":
                        candle_ws = None

                if close_status_code is not None:
                    logger.warning(
                        f"WebSocket closed: code={close_status_code}, msg={close_msg}"
                    )
                else:
                    logger.warning("WebSocket closed")

            ws = websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_error=lambda ws, error: logger.warning(f"WebSocket error: {error}"),
                on_close=on_close_handler,
                on_open=on_open,
            )

            # Store WebSocket reference
            with ws_lock:
                if ws_type == "ticker":
                    ticker_ws = ws
                elif ws_type == "candle":
                    candle_ws = ws

            def send_ping(ws):
                while True:
                    time.sleep(20)
                    try:
                        ws.send("ping")
                    except Exception:
                        break

            ping_thread = threading.Thread(target=send_ping, args=(ws,), daemon=True)
            ping_thread.start()

            # Reset reconnect delay on successful connection
            reconnect_delay = 1
            ws.run_forever()

        except KeyboardInterrupt:
            logger.warning("WebSocket connection interrupted by user")
            raise
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            logger.warning(f"Retrying in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            # Exponential backoff with max limit
            reconnect_delay = min(reconnect_delay * 2, max_delay)


def main():
    """Main function"""
    logger.warning(f"Starting {STRATEGY_NAME} trading system")

    # Load crypto limits
    if not load_crypto_limits():
        logger.error("Failed to load crypto limits, exiting")
        return

    if not crypto_limits:
        logger.error("No crypto limits loaded, exiting")
        return

    logger.warning(f"Loaded {len(crypto_limits)} cryptos with limits")

    # Initialize database connection with retry
    try:
        conn = get_db_connection()
        conn.close()
        logger.warning(f"✅ Connected to PostgreSQL database successfully")
    except Exception as e:
        logger.error(f"Database error: {e}")
        logger.error("Failed to connect to database, exiting")
        return

    # Start ticker WebSocket
    ticker_url = "wss://ws.okx.com:8443/ws/v5/public"
    ticker_thread = threading.Thread(
        target=connect_websocket,
        args=(ticker_url, on_ticker_message, ticker_open, "ticker"),
        daemon=True,
        name="TickerWebSocket",
    )
    ticker_thread.start()

    # Start candle WebSocket
    candle_url = "wss://ws.okx.com:8443/ws/v5/business"
    candle_thread = threading.Thread(
        target=connect_websocket,
        args=(candle_url, on_candle_message, candle_open, "candle"),
        daemon=True,
        name="CandleWebSocket",
    )
    candle_thread.start()

    logger.warning("WebSocket connections started, waiting for messages...")

    # Keep main thread alive with health check
    try:
        while True:
            time.sleep(60)
            # Periodic status log
            with lock:
                logger.info(
                    f"Status: {len(current_prices)} prices, {len(active_orders)} active orders"
                )

            # Health check: verify WebSocket threads are alive
            if not ticker_thread.is_alive():
                logger.error("Ticker WebSocket thread died, restarting...")
                ticker_thread = threading.Thread(
                    target=connect_websocket,
                    args=(ticker_url, on_ticker_message, ticker_open, "ticker"),
                    daemon=True,
                    name="TickerWebSocket",
                )
                ticker_thread.start()

            if not candle_thread.is_alive():
                logger.error("Candle WebSocket thread died, restarting...")
                candle_thread = threading.Thread(
                    target=connect_websocket,
                    args=(candle_url, on_candle_message, candle_open, "candle"),
                    daemon=True,
                    name="CandleWebSocket",
                )
                candle_thread.start()

    except KeyboardInterrupt:
        logger.warning("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}")
        raise


if __name__ == "__main__":
    main()
