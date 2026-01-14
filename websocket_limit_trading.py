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
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional

import psycopg2
import psycopg2.extras
import websocket
from dotenv import load_dotenv
from okx.MarketData import MarketAPI
from okx.Trade import TradeAPI

warnings.filterwarnings("ignore", category=RuntimeWarning)

# Load environment variables
load_dotenv()

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIMITS_FILE = os.path.join(BASE_DIR, "valid_crypto_limits.json")
LOG_FILE = os.path.join(BASE_DIR, "websocket_limit_trading.log")

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
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=100 * 1024 * 1024, backupCount=3),
        logging.StreamHandler(),
    ],
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


def get_db_connection():
    """Get PostgreSQL database connection"""
    return psycopg2.connect(DATABASE_URL)


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


def load_crypto_limits():
    """Load crypto limits from JSON file"""
    global crypto_limits
    try:
        with open(LIMITS_FILE, "r") as f:
            data = json.load(f)
        crypto_limits = {
            symbol: data["cryptos"][symbol]["limit_percent"]
            for symbol in data["cryptos"].keys()
        }
        logger.warning(f"Loaded {len(crypto_limits)} crypto limits")
        return True
    except Exception as e:
        logger.error(f"Failed to load crypto limits: {e}")
        return False


def calculate_limit_price(current_price: float, limit_percent: float) -> float:
    """Calculate limit buy price based on limit_percent"""
    return current_price * (limit_percent / 100.0)


def buy_limit_order(
    instId: str, limit_price: float, size: float, tradeAPI: TradeAPI, conn
) -> Optional[str]:
    """Place limit buy order and record in database"""
    buy_price = format_number(limit_price)
    size = format_number(size)

    if SIMULATION_MODE:
        # Simulation mode: generate fake ordId with strategy prefix for isolation
        ordId = f"HLW-SIM-{uuid.uuid4().hex[:12]}"  # HLW = Hourly Limit WS
        logger.warning(
            f"{STRATEGY_NAME} [SIM] buy limit: {instId}, price={buy_price}, size={size}, ordId={ordId}"
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
                        logger.warning(
                            f"{STRATEGY_NAME} buy limit: {instId}, price={buy_price}, size={size}, ordId={ordId}"
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
        logger.warning(f"{STRATEGY_NAME} buy limit DB: {instId}, ordId={ordId}")

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
        logger.warning(
            f"{STRATEGY_NAME} [SIM] sell market: {instId}, size={size}, price={sell_price}, ordId={ordId}"
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
                    logger.warning(
                        f"{STRATEGY_NAME} sell market: {instId}, size={size}, ordId={order_id}"
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
        logger.warning(
            f"{STRATEGY_NAME} sell market DB: {instId}, ordId={ordId}, sell_price={sell_price_str}"
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
                                    pending_buys[instId] = True
                                    # Trigger buy in separate thread to avoid blocking
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
        # Initialize trade API if not already done
        if "trade_api" not in globals():
            global trade_api
            trade_api = TradeAPI(
                API_KEY, API_SECRET, API_PASSPHRASE, False, TRADING_FLAG
            )

        # Calculate size
        size = TRADING_AMOUNT_USDT / limit_price

        # Place limit buy order
        conn = get_db_connection()
        try:
            ordId = buy_limit_order(instId, limit_price, size, trade_api, conn)
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
                        f"{STRATEGY_NAME} Active order: {instId}, ordId={ordId}, sell_time={next_hour}"
                    )

                    # Start 1-minute timeout check thread (only in real trading mode)
                    # In simulation mode, orders are assumed to be filled immediately
                    if not SIMULATION_MODE:
                        threading.Thread(
                            target=check_and_cancel_unfilled_order_after_timeout,
                            args=(instId, ordId, trade_api),
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

        # Initialize trade API if not already done
        if "trade_api" not in globals():
            global trade_api
            trade_api = TradeAPI(
                API_KEY, API_SECRET, API_PASSPHRASE, False, TRADING_FLAG
            )

        # ✅ FIX: Check order state and prevent duplicate sells
        conn = get_db_connection()
        try:
            cur = conn.cursor()

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
            cur.close()

            # Place market sell order
            sell_market_order(instId, ordId, size, trade_api, conn)

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


def connect_websocket(url, on_message, on_open):
    """Connect to WebSocket with reconnection logic"""
    while True:
        try:
            ws = websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_error=lambda ws, error: logger.warning(f"WebSocket error: {error}"),
                on_close=lambda ws: logger.warning("WebSocket closed"),
                on_open=on_open,
            )

            def send_ping(ws):
                while True:
                    time.sleep(20)
                    try:
                        ws.send("ping")
                    except:
                        break

            ping_thread = threading.Thread(target=send_ping, args=(ws,), daemon=True)
            ping_thread.start()
            ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            logger.warning("Retrying in 5 seconds...")
            time.sleep(5)


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

    # Initialize database connection
    try:
        conn = get_db_connection()
        conn.close()
        logger.warning(f"✅ Connected to PostgreSQL database successfully")
    except Exception as e:
        logger.error(f"Database error: {e}")
        return

    # Start ticker WebSocket
    ticker_url = "wss://ws.okx.com:8443/ws/v5/public"
    ticker_thread = threading.Thread(
        target=connect_websocket,
        args=(ticker_url, on_ticker_message, ticker_open),
        daemon=True,
    )
    ticker_thread.start()

    # Start candle WebSocket
    candle_url = "wss://ws.okx.com:8443/ws/v5/business"
    candle_thread = threading.Thread(
        target=connect_websocket,
        args=(candle_url, on_candle_message, candle_open),
        daemon=True,
    )
    candle_thread.start()

    logger.warning("WebSocket connections started, waiting for messages...")

    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
            # Periodic status log
            with lock:
                logger.info(
                    f"Status: {len(current_prices)} prices, {len(active_orders)} active orders"
                )
    except KeyboardInterrupt:
        logger.warning("Shutting down...")


if __name__ == "__main__":
    main()
