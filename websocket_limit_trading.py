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
from okx.PublicData import PublicAPI
from okx.Trade import TradeAPI

# Add src directory to path to import blacklist_manager
sys.path.insert(0, str(Path(__file__).parent / "src"))
try:
    from crypto_remote.blacklist_manager import BlacklistManager
except ImportError:
    BlacklistManager = None

# Import momentum-volume strategy
try:
    from core.momentum_volume_strategy import MomentumVolumeStrategy
except ImportError:
    MomentumVolumeStrategy = None

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

# Trading Configuration
TRADING_AMOUNT_USDT = int(
    os.getenv("TRADING_AMOUNT_USDT", "100")
)  # Amount per trade in USDT
STRATEGY_NAME = "hourly_limit_ws"
MOMENTUM_STRATEGY_NAME = "momentum_volume_exhaustion"
SIMULATION_MODE = (
    os.getenv("SIMULATION_MODE", "true").lower() == "true"
)

# ✅ FIX: Only require API credentials in real trading mode
# Simulation mode can run without real API keys
if not SIMULATION_MODE:
    if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
        raise ValueError(
            "OKX API credentials not found in environment variables. "
            "Please set OKX_API_KEY, OKX_SECRET, and OKX_PASSPHRASE. "
            "Or set SIMULATION_MODE=true to run without API keys."
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
reference_prices: Dict[str, float] = (
    {}
)  # instId -> current hour's open price (reference for limit calculation)
# ✅ FIX: Cache reference price fetch attempts to prevent rate limiting
reference_price_fetch_time: Dict[str, float] = {}  # instId -> last fetch timestamp
reference_price_fetch_attempts: Dict[str, int] = (
    {}
)  # instId -> consecutive fetch failures
pending_buys: Dict[str, bool] = {}  # instId -> has_pending_buy
active_orders: Dict[str, Dict] = (
    {}
)  # instId -> {ordId, buy_price, buy_time, next_hour_close_time}
# Momentum strategy active orders (separate tracking)
momentum_active_orders: Dict[str, Dict] = (
    {}
)  # instId -> {ordIds: [str], buy_prices: [float], buy_sizes: [float], ...}
momentum_pending_buys: Dict[str, bool] = {}  # instId -> has_pending_buy
lock = threading.Lock()

# Initialize momentum-volume strategy
momentum_strategy: Optional[MomentumVolumeStrategy] = None
if MomentumVolumeStrategy is not None:
    momentum_strategy = MomentumVolumeStrategy()
    logger.warning("✅ Momentum-Volume Exhaustion strategy initialized")
else:
    logger.warning("⚠️ Momentum-Volume strategy not available")


def initialize_momentum_strategy_history():
    """Initialize momentum strategy with historical 1H candle data

    Fetches last M+1 (11) 1H candles from OKX API for each crypto
    to avoid waiting 11 hours after program startup.
    """
    if momentum_strategy is None:
        return

    if not crypto_limits:
        logger.warning("⚠️ No crypto limits loaded, skipping history initialization")
        return

    logger.warning(
        f"📊 Initializing momentum strategy history for {len(crypto_limits)} cryptos..."
    )

    market_api = get_market_api()
    if not market_api:
        logger.error("❌ Market API not available, cannot initialize history")
        return

    # Import M from strategy module
    from core.momentum_volume_strategy import M

    initialized_count = 0
    failed_count = 0

    for instId in crypto_limits.keys():
        try:
            # Fetch last M+1 (11) 1H candles
            result = market_api.get_candlesticks(
                instId=instId, bar="1H", limit=str(M + 1)
            )

            if result.get("code") == "0" and result.get("data"):
                candles = result["data"]
                if candles and len(candles) > 0:
                    success = momentum_strategy.initialize_history(
                        instId, candles, logger
                    )
                    if success:
                        initialized_count += 1
                    else:
                        failed_count += 1
                else:
                    logger.debug(f"⚠️ {instId} No candle data returned")
                    failed_count += 1
            else:
                error_msg = result.get("msg", "Unknown error")
                logger.debug(f"⚠️ {instId} Failed to fetch history: {error_msg}")
                failed_count += 1

            # Small delay to avoid rate limiting
            time.sleep(0.1)

        except Exception as e:
            logger.error(f"❌ {instId} Error initializing history: {e}")
            failed_count += 1

    logger.warning(
        f"📊 History initialization complete: "
        f"{initialized_count} succeeded, {failed_count} failed"
    )


# WebSocket connections for unsubscribe
ticker_ws: Optional[websocket.WebSocketApp] = None
candle_ws: Optional[websocket.WebSocketApp] = None
ws_lock = threading.Lock()

# ✅ NEW: Track last 1H candle receive time for monitoring
# Format: instId -> last_candle_timestamp
last_1h_candle_time: Dict[str, datetime] = {}
CANDLE_TIMEOUT_MINUTES = 90  # Alert if no candle received for 90 minutes

# Initialize TradeAPI instance (singleton pattern)
trade_api: Optional[TradeAPI] = None
market_api: Optional[MarketAPI] = None
public_api: Optional[PublicAPI] = None

# Cache for instrument precision info (lotSz, tickSz, minSz)
instrument_precision_cache: Dict[str, Dict] = (
    {}
)  # instId -> {lotSz, tickSz, minSz, lotPrecision, tickPrecision}


def get_trade_api() -> Optional[TradeAPI]:
    """Get or initialize TradeAPI instance (singleton)
    
    Returns:
        TradeAPI instance, or None if in simulation mode without API keys
    """
    global trade_api
    if trade_api is None:
        # ✅ FIX: In simulation mode, allow None if API keys not provided
        if SIMULATION_MODE and not all([API_KEY, API_SECRET, API_PASSPHRASE]):
            logger.debug("Simulation mode: TradeAPI not initialized (no API keys)")
            return None
        try:
            trade_api = TradeAPI(API_KEY, API_SECRET, API_PASSPHRASE, False, TRADING_FLAG)
        except Exception as e:
            if SIMULATION_MODE:
                logger.warning(f"Simulation mode: TradeAPI init failed: {e}, continuing without it")
                return None
            raise
    return trade_api


def get_market_api() -> MarketAPI:
    """Get or initialize MarketAPI instance (singleton)"""
    global market_api
    if market_api is None:
        market_api = MarketAPI(flag=TRADING_FLAG)
    return market_api


def get_public_api() -> PublicAPI:
    """Get or initialize PublicAPI instance (singleton)"""
    global public_api
    if public_api is None:
        public_api = PublicAPI(flag=TRADING_FLAG)
    return public_api


def get_instrument_precision(instId: str, use_cache: bool = True) -> Optional[Dict]:
    """Get instrument precision info (lotSz, tickSz, minSz) from OKX API
    Returns None if API call fails, falls back to format_number default behavior
    """
    # Check cache first
    if use_cache and instId in instrument_precision_cache:
        return instrument_precision_cache[instId]

    try:
        api = get_public_api()
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
                instrument_precision_cache[instId] = precision_info
                logger.debug(
                    f"📊 Cached instrument precision for {instId}: {precision_info}"
                )
                return precision_info
    except Exception as e:
        logger.debug(f"⚠️ Failed to get instrument precision for {instId}: {e}")

    return None


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
                    f"Database connection failed "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
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


def format_number(number, instId: Optional[str] = None):
    """Format number according to OKX precision requirements
    If instId is provided, uses OKX instrument precision (lotSz) for better accuracy
    Falls back to heuristic precision if instrument info is not available

    Args:
        number: Number to format (price or size)
        instId: Optional instrument ID (e.g., 'BTC-USDT') to use instrument-specific precision
    """
    number = float(number)

    # ✅ OPTIMIZE: Try to use OKX instrument precision if instId is provided
    if instId:
        precision_info = get_instrument_precision(instId, use_cache=True)
        if precision_info:
            # For size/quantity, use lotSz precision
            # For price, use tickSz precision
            # Determine if this is likely a price or size based on value
            # (prices are usually > 0.001, sizes vary)
            # Use lotSz for now as it's more commonly needed for order sizes
            lot_precision = precision_info.get("lotPrecision", 0)
            lot_sz = float(precision_info.get("lotSz", "1"))

            # Round to lotSz increment
            if lot_sz > 0:
                # Round to nearest lotSz increment
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
    conn = None
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
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return False


def calculate_limit_price(
    reference_price: float, base_limit_percent: float, instId: str
) -> float:
    """Calculate limit buy price

    Args:
        reference_price: Current hour's open price
        base_limit_percent: Base limit percentage from database
        instId: Instrument ID (not used, kept for compatibility)

    Returns:
        Limit price
    """
    return reference_price * (base_limit_percent / 100.0)


def fetch_current_hour_open_price(instId: str) -> Optional[float]:
    """Fetch current hour's open price for a cryptocurrency"""
    try:
        market_api = get_market_api()
        # ✅ FIX: Use 1H (1 hour) candlestick instead of 1D (1 day)
        # Strategy is hourly trading: buy at current hour, sell at next hour
        # So reference price should be current hour's open, not daily open
        result = market_api.get_candlesticks(instId=instId, bar="1H", limit="1")

        if result.get("code") == "0" and result.get("data"):
            data = result["data"]
            if data and len(data) > 0:
                # Data format: [timestamp, open, high, low, close, volume, ...]
                # data[0] = [ts, open, high, low, close, vol,
                #            volCcy, volCcyQuote, confirm]
                candle = data[0]
                candle_ts = int(candle[0]) / 1000  # Convert ms to seconds
                hour_open = float(candle[1])

                # ✅ FIX: Verify the timestamp to ensure we got the current hour's candle
                # OKX K-line timestamp (ts) is the start time of that hour
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
                    # (probably previous hour if called too early at hour start)
                    expected_hour = datetime.fromtimestamp(current_hour_start).strftime(
                        "%H:00"
                    )
                    got_hour = datetime.fromtimestamp(candle_hour_start).strftime(
                        "%H:00"
                    )
                    logger.warning(
                        f"⚠️ {instId} got different hour's candle: "
                        f"expected hour={expected_hour}, "
                        f"got hour={got_hour}, open=${hour_open:.6f}"
                    )
                    # Return None to trigger retry or use fallback
                    return None
        else:
            error_msg = result.get("msg", "Unknown error")
            logger.warning(
                f"⚠️ Failed to get current hour's open for {instId}: {error_msg}"
            )
    except Exception as e:
        logger.error(f"Error fetching current hour's open for {instId}: {e}")
    return None


def initialize_reference_prices():
    """Initialize reference prices (current hour's open) for all cryptos"""
    logger.warning(
        "🔄 Initializing reference prices (current hour's open) for all cryptos..."
    )
    count = 0
    for instId in crypto_limits.keys():
        open_price = fetch_current_hour_open_price(instId)
        if open_price and open_price > 0:
            with lock:
                reference_prices[instId] = open_price
                # Reset fetch attempts on successful initialization
                reference_price_fetch_attempts[instId] = 0
            count += 1
        time.sleep(0.1)  # Rate limiting
    logger.warning(
        f"✅ Initialized {count}/{len(crypto_limits)} reference prices "
        f"(current hour's open)"
    )


def buy_limit_order(
    instId: str, limit_price: float, size: float, tradeAPI: TradeAPI, conn
) -> Optional[str]:
    """Place limit buy order and record in database"""
    # Check blacklist before buying
    if check_blacklist_before_buy(instId):
        # Already blacklisted, block the buy
        return None

    buy_price = format_number(limit_price, instId)
    size = format_number(size, instId)

    if SIMULATION_MODE:
        # Simulation mode: generate fake ordId with strategy prefix for isolation
        ordId = f"HLW-SIM-{uuid.uuid4().hex[:12]}"  # HLW = Hourly Limit WS
        amount_usdt = float(buy_price) * float(size)
        logger.warning(
            f"🛒 [SIM] BUY: {instId}, price={buy_price}, size={size}, "
            f"amount={amount_usdt:.2f} USDT, ordId={ordId}"
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

                    if ordId:
                        amount_usdt = float(buy_price) * float(size)
                        logger.warning(
                            f"🛒 BUY ORDER: {instId}, price={buy_price}, "
                            f"size={size}, amount={amount_usdt:.2f} USDT, "
                            f"ordId={ordId}"
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
                        f"{STRATEGY_NAME} buy limit failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
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
            """INSERT INTO orders (instId, flag, ordId, create_time,
                       orderType, state, price, size, sell_time, side)
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
            f"✅ BUY SAVED: {instId}, price={buy_price}, size={size}, "
            f"amount={amount_usdt:.2f} USDT, ordId={ordId}"
        )

        # Play buy sound
        play_sound("buy")

        return ordId
    except Exception as e:
        logger.error(
            f"{STRATEGY_NAME} buy limit DB error: {instId}, "
            f"ordId may be undefined, {e}"
        )
        conn.rollback()
        # ✅ FIX: Return None on error instead of potentially undefined ordId
        return None
    finally:
        cur.close()


def sell_market_order(
    instId: str, ordId: str, size: float, tradeAPI: TradeAPI, conn
) -> bool:
    """Place market sell order

    Returns:
        True if sell order was successfully placed and recorded, False otherwise
    """
    size = format_number(size, instId)

    if SIMULATION_MODE:
        # Simulation mode: skip actual trading, use current price as sell price
        # ✅ FIX: Try to get current price, if not available use a reasonable estimate
        with lock:
            sell_price = current_prices.get(instId, 0.0)

        # If no current price in memory, try to get from ticker API
        if sell_price <= 0:
            try:
                market_api = get_market_api()
                ticker_result = market_api.get_ticker(instId=instId)
                if ticker_result.get("code") == "0" and ticker_result.get("data"):
                    ticker_data = ticker_result["data"]
                    if ticker_data and len(ticker_data) > 0:
                        sell_price = float(ticker_data[0].get("last", 0))
                        logger.info(
                            f"📊 {instId} fetched current price for simulation: "
                            f"${sell_price:.6f}"
                        )
            except Exception as e:
                logger.warning(f"⚠️ Could not get current price for {instId}: {e}")

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"💰 [SIM] SELL: {instId}, price={sell_price:.6f}, size={size}, "
            f"amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
    else:
        # Real trading mode
        max_attempts = 3
        failed_flag = 0
        sell_price = 0.0

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

                    # ✅ FIX: Get actual fill price from order
                    # (OKX official API returns weighted average)
                    # get_order() returns fillPx which is already
                    # the weighted average of all fills
                    # No need to call get_fills() separately
                    # - simpler and more efficient
                    time.sleep(0.5)  # Small delay to ensure order is processed
                    try:
                        order_result = tradeAPI.get_order(instId=instId, ordId=order_id)
                        if order_result.get("code") == "0" and order_result.get("data"):
                            order_info = order_result["data"][0]
                            fill_px = order_info.get("fillPx", "")
                            acc_fill_sz = order_info.get("accFillSz", "0")

                            # fillPx from OKX is already
                            # the weighted average of all fills
                            if (
                                fill_px
                                and fill_px != ""
                                and acc_fill_sz
                                and float(acc_fill_sz) > 0
                            ):
                                sell_price = float(fill_px)
                                logger.warning(
                                    f"💰 SELL ORDER: {instId}, "
                                    f"fill price={sell_price:.6f} "
                                    f"(weighted avg from OKX), "
                                    f"size={size}, ordId={order_id}"
                                )
                            else:
                                # Fill price not available yet,
                                # fallback to current price
                                with lock:
                                    sell_price = current_prices.get(instId, 0.0)
                                logger.warning(
                                    f"💰 SELL ORDER: {instId}, "
                                    f"using current price={sell_price:.6f} "
                                    f"(fill price not available yet), "
                                    f"size={size}, ordId={order_id}"
                                )
                        else:
                            # Order query failed, fallback to current price
                            with lock:
                                sell_price = current_prices.get(instId, 0.0)
                            logger.warning(
                                f"💰 SELL ORDER: {instId}, "
                                f"using current price={sell_price:.6f} "
                                f"(order query failed), "
                                f"size={size}, ordId={order_id}"
                            )
                    except Exception as e:
                        # Fallback to current price on error
                        with lock:
                            sell_price = current_prices.get(instId, 0.0)
                        logger.warning(
                            f"💰 SELL ORDER: {instId}, "
                            f"using current price={sell_price:.6f} "
                            f"(error getting fill price: {e}), "
                            f"size={size}, ordId={order_id}"
                        )

                    failed_flag = 0
                    break
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{STRATEGY_NAME} sell market failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
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
            logger.error(
                f"❌ {STRATEGY_NAME} SELL FAILED: {instId}, ordId={ordId}, "
                f"all {max_attempts} attempts failed"
            )
            return False

    # Update database - verify update succeeded
    cur = conn.cursor()
    try:
        # Format sell price for database
        sell_price_str = format_number(sell_price, instId) if sell_price > 0 else ""

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s "
            "WHERE instId = %s AND ordId = %s AND flag = %s",
            ("sold out", sell_price_str, instId, ordId, STRATEGY_NAME),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {STRATEGY_NAME} SELL DB UPDATE FAILED: {instId}, ordId={ordId}, "
                f"no rows updated"
            )
            return False

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"✅ SELL SAVED: {instId}, price={sell_price_str}, size={size}, "
            f"amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )

        play_sound("sell")
        return True
    except Exception as e:
        logger.error(f"{STRATEGY_NAME} sell market DB error: {instId}, {ordId}, {e}")
        conn.rollback()
        return False
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
                    # For ticker updates, we don't have per-period volume
                    # Use a normalized approach: estimate volume from price activity
                    # or use 24h volume normalized (less accurate but works)
                    # Note: Ticker volume is 24h cumulative, not per-tick
                    # We'll use a small normalized value for ticker updates
                    # Real volume data should come from candle WebSocket
                    # Note: volume_24h not used - volume tracking relies on candle data

                    if last_price > 0:
                        with lock:
                            current_prices[instId] = last_price

                            # ✅ FIX: Reset fetch attempts on ticker update to allow recovery from high backoff
                            # If we're receiving ticker updates, the coin is active and we should be able to fetch reference price
                            if (
                                instId in reference_price_fetch_attempts
                                and reference_price_fetch_attempts[instId] > 0
                            ):
                                reference_price_fetch_attempts[instId] = 0
                                logger.debug(
                                    f"📊 Reset reference_price_fetch_attempts for {instId} "
                                    f"on ticker update (coin is active)"
                                )

                            # ✅ OPTIMIZATION: Don't update from ticker - only use 1H candle data
                            # Strategy now requires unified time scale (1H candles only)
                            # Price and volume will be updated together from candle WebSocket
                            # This ensures M=10 represents a true 10-hour window

                            # Check if we should buy (original strategy)
                            if (
                                instId not in pending_buys
                                and instId not in active_orders
                            ):
                                limit_percent = crypto_limits[instId]

                                # Get reference price (current hour's open),
                                # fetch if not available
                                ref_price = reference_prices.get(instId)

                        # If no reference price, try to fetch it
                        # (outside lock to avoid blocking)
                        if ref_price is None or ref_price <= 0:
                            # ✅ FIX: Add backoff/cache to prevent rate limiting
                            with lock:
                                last_fetch = reference_price_fetch_time.get(instId, 0)
                                fetch_attempts = reference_price_fetch_attempts.get(
                                    instId, 0
                                )
                                time_since_fetch = time.time() - last_fetch

                                # Backoff: wait at least 5 seconds between fetches for same instId
                                # Exponential backoff: 5s, 10s, 20s, 40s (max 60s)
                                min_wait = min(5 * (2 ** min(fetch_attempts, 4)), 60)

                                if time_since_fetch < min_wait:
                                    logger.debug(
                                        f"⏳ Skipping reference price fetch for {instId}: "
                                        f"backoff ({time_since_fetch:.1f}s < {min_wait}s)"
                                    )
                                    continue

                                # Update fetch time
                                reference_price_fetch_time[instId] = time.time()

                            logger.warning(
                                f"⚠️ No reference price for {instId}, "
                                f"fetching current hour's open..."
                            )
                            ref_price = fetch_current_hour_open_price(instId)
                            if ref_price and ref_price > 0:
                                with lock:
                                    # Double-check conditions after fetching
                                    # (another thread might have started buying)
                                    if (
                                        instId not in pending_buys
                                        and instId not in active_orders
                                    ):
                                        reference_prices[instId] = ref_price
                                        # Reset fetch attempts on success
                                        reference_price_fetch_attempts[instId] = 0
                            else:
                                # ✅ FIX: Increment fetch attempts and skip this check
                                with lock:
                                    reference_price_fetch_attempts[instId] = (
                                        fetch_attempts + 1
                                    )
                                logger.warning(
                                    f"⚠️ Failed to get reference price for "
                                    f"{instId}, skipping buy check "
                                    f"(will retry after backoff, attempts={fetch_attempts + 1})"
                                )
                                continue

                        # Calculate limit price
                        limit_price = calculate_limit_price(
                            ref_price, limit_percent, instId
                        )

                        # Check if current price has dropped to or below limit price
                        if last_price <= limit_price:
                            # ✅ FIX: Double-check conditions and set
                            # pending_buys atomically to prevent race condition
                            with lock:
                                # Re-check conditions to prevent race condition
                                if instId in pending_buys or instId in active_orders:
                                    # Another thread already started
                                    # processing this signal
                                    continue
                                # Set pending_buys atomically within the lock
                                pending_buys[instId] = True

                            logger.warning(
                                f"🚀 BUY SIGNAL: {instId}, "
                                f"current={last_price:.6f} <= limit={limit_price:.6f} "
                                f"(ref={ref_price:.6f}, {limit_percent}%)"
                            )
                            # Trigger buy in separate thread to avoid blocking
                            # Blacklist check will happen in process_buy_signal
                            threading.Thread(
                                target=process_buy_signal,
                                args=(instId, limit_price),
                                daemon=True,
                            ).start()
                        else:
                            # Log when price is close but not yet at limit
                            # (for debugging)
                            price_diff_pct = (
                                (last_price - limit_price) / ref_price
                            ) * 100
                            if price_diff_pct < 2.0:  # Within 2% of limit
                                logger.debug(
                                    f"📊 {instId} close to limit: "
                                    f"current={last_price:.6f}, "
                                    f"limit={limit_price:.6f}, "
                                    f"diff={price_diff_pct:.2f}%"
                                )

                    # ✅ OPTIMIZATION: Momentum strategy buy signal moved to candle event
                    # Now uses unified time scale (1H candle) for both history and trigger
                    # Signal check removed from ticker to maintain consistency
    except Exception as e:
        logger.error(f"Ticker message error: {msg_string}, {e}")


def check_and_cancel_unfilled_order_after_timeout(
    instId: str, ordId: str, tradeAPI: TradeAPI, strategy_name: str = STRATEGY_NAME
):
    """Check order status after 1 minute timeout, cancel if not filled"""
    # Skip timeout check in simulation mode (orders are virtual)
    if SIMULATION_MODE or ordId.startswith("HLW-SIM-") or ordId.startswith("MVE-SIM-"):
        return

    try:
        time.sleep(60)  # Wait 1 minute

        # ✅ FIX: Check if order exists quickly with lock, then release for API/DB operations
        with lock:
            order_exists = False
            if strategy_name == STRATEGY_NAME:
                if (
                    instId in active_orders
                    and active_orders[instId].get("ordId") == ordId
                ):
                    order_exists = True
            elif strategy_name == MOMENTUM_STRATEGY_NAME:
                if instId in momentum_active_orders:
                    if ordId in momentum_active_orders[instId].get("ordIds", []):
                        order_exists = True

            if not order_exists:
                # Order already processed or removed
                return

        # ✅ FIX: Release lock before API/DB operations to avoid blocking
        # Check order status
        try:
            result = tradeAPI.get_order(instId=instId, ordId=ordId)
            if result and result.get("data") and len(result["data"]) > 0:
                order_data = result["data"][0]
                acc_fill_sz = order_data.get("accFillSz", "0")
                fill_px = order_data.get("fillPx", "0")
                state = order_data.get("state", "")
                # ✅ FIX: Get fillTime from OKX order data (more accurate than local time)
                fill_time_ms = order_data.get("fillTime", "")
                filled_size = (
                    float(acc_fill_sz) if acc_fill_sz and acc_fill_sz != "" else 0.0
                )
                # ✅ FIX: Handle partially_filled - cancel remaining unfilled portion
                is_fully_filled = state == "filled" and filled_size > 0
                is_partially_filled = state == "partially_filled" and filled_size > 0

                if is_partially_filled:
                    # ✅ FIX: Partially filled: keep in active_orders, update with filled size, recalculate sell_time
                    logger.warning(
                        f"{strategy_name} Order partially filled: {instId}, ordId={ordId}, "
                        f"filled={acc_fill_sz}, state={state}"
                    )

                    # ✅ FIX: Use OKX fillTime if available, otherwise fallback to local time
                    if fill_time_ms and fill_time_ms != "":
                        try:
                            fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                            logger.info(
                                f"{strategy_name} Using OKX fillTime for {instId}, ordId={ordId}: "
                                f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"{strategy_name} Invalid fillTime from OKX: {fill_time_ms}, "
                                f"using local time: {e}"
                            )
                            fill_time = datetime.now()
                    else:
                        logger.warning(
                            f"{strategy_name} No fillTime from OKX for {instId}, ordId={ordId}, "
                            f"using local time (may have clock drift)"
                        )
                        fill_time = datetime.now()

                    next_hour = fill_time.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)
                    sell_time_ms = int(next_hour.timestamp() * 1000)

                    # ✅ FIX: Use accFillSz string directly to preserve precision
                    # Validate that accFillSz is a valid numeric string
                    if not acc_fill_sz or acc_fill_sz == "" or acc_fill_sz == "0":
                        logger.error(
                            f"{strategy_name} Invalid accFillSz for partially filled order: "
                            f"{instId}, ordId={ordId}, accFillSz={acc_fill_sz}"
                        )
                        return

                    # Update database with actual filled size (as string to preserve precision) and recalculated sell_time
                    conn = get_db_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            """UPDATE orders
                               SET state = %s, size = %s, price = %s, sell_time = %s
                               WHERE instId = %s AND ordId = %s AND flag = %s""",
                            (
                                "partially_filled",
                                acc_fill_sz,  # Use string directly to preserve precision
                                fill_px,
                                sell_time_ms,
                                instId,
                                ordId,
                                strategy_name,
                            ),
                        )
                        conn.commit()
                        cur.close()
                    finally:
                        conn.close()

                    # Cancel remaining unfilled portion
                    try:
                        tradeAPI.cancel_order(instId=instId, ordId=ordId)
                        logger.warning(
                            f"{strategy_name} Canceled remaining unfilled portion: "
                            f"{instId}, ordId={ordId}"
                        )
                    except Exception as e:
                        logger.error(
                            f"{strategy_name} Error canceling partial order: {instId}, {ordId}, {e}"
                        )

                    # ✅ FIX: Keep in active_orders with updated filled_size and recalculated next_hour_close_time
                    with lock:
                        if strategy_name == STRATEGY_NAME:
                            if instId in active_orders:
                                active_orders[instId]["filled_size"] = filled_size
                                active_orders[instId]["fill_price"] = (
                                    float(fill_px) if fill_px else 0.0
                                )
                                active_orders[instId][
                                    "next_hour_close_time"
                                ] = next_hour
                                active_orders[instId]["fill_time"] = fill_time
                                logger.warning(
                                    f"{strategy_name} Updated active_order for partial fill: {instId}, "
                                    f"filled_size={filled_size}, next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                )
                        elif strategy_name == MOMENTUM_STRATEGY_NAME:
                            if instId in momentum_active_orders:
                                if ordId in momentum_active_orders[instId].get(
                                    "ordIds", []
                                ):
                                    idx = momentum_active_orders[instId][
                                        "ordIds"
                                    ].index(ordId)
                                    # Update sizes to reflect partial fill
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_sizes", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_sizes"][
                                            idx
                                        ] = filled_size
                                    # Update next_hour_close_time based on fill time
                                    momentum_active_orders[instId][
                                        "next_hour_close_time"
                                    ] = next_hour
                                    logger.warning(
                                        f"{strategy_name} Updated momentum_active_order for partial fill: {instId}, "
                                        f"ordId={ordId}, filled_size={filled_size}, "
                                        f"next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                    )
                    return

                if not is_fully_filled:
                    # Order not filled after 1 minute, cancel it
                    tradeAPI.cancel_order(instId=instId, ordId=ordId)
                    logger.warning(
                        f"{strategy_name} Canceled unfilled order after 1 minute: "
                        f"{instId}, ordId={ordId}"
                    )

                    # Update database
                    conn = get_db_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE orders SET state = %s "
                            "WHERE instId = %s AND ordId = %s AND flag = %s",
                            ("canceled", instId, ordId, strategy_name),
                        )
                        conn.commit()
                        cur.close()
                    finally:
                        conn.close()

                    # Remove from active_orders or momentum_active_orders
                    with lock:
                        if strategy_name == STRATEGY_NAME:
                            if instId in active_orders:
                                del active_orders[instId]
                        elif strategy_name == MOMENTUM_STRATEGY_NAME:
                            if instId in momentum_active_orders:
                                # Remove this ordId from the list
                                if ordId in momentum_active_orders[instId].get(
                                    "ordIds", []
                                ):
                                    idx = momentum_active_orders[instId][
                                        "ordIds"
                                    ].index(ordId)
                                    momentum_active_orders[instId]["ordIds"].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_prices", []
                                        )
                                    ):
                                        momentum_active_orders[instId][
                                            "buy_prices"
                                        ].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_sizes", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_sizes"].pop(
                                            idx
                                        )
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_times", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_times"].pop(
                                            idx
                                        )
                                # If no more orders, remove the entry
                                if not momentum_active_orders[instId].get("ordIds", []):
                                    del momentum_active_orders[instId]
                else:
                    # ✅ FIX: Order is filled, update database with actual fill info and recalculate sell_time
                    logger.warning(
                        f"{strategy_name} Order filled within 1 minute: "
                        f"{instId}, ordId={ordId}, "
                        f"fillSize={acc_fill_sz}, fillPrice={fill_px}"
                    )

                    # ✅ FIX: Use OKX fillTime if available, otherwise fallback to local time
                    fill_time_ms = order_data.get("fillTime", "")
                    if fill_time_ms and fill_time_ms != "":
                        try:
                            fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                            logger.info(
                                f"{strategy_name} Using OKX fillTime for {instId}, ordId={ordId}: "
                                f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"{strategy_name} Invalid fillTime from OKX: {fill_time_ms}, "
                                f"using local time: {e}"
                            )
                            fill_time = datetime.now()
                    else:
                        logger.warning(
                            f"{strategy_name} No fillTime from OKX for {instId}, ordId={ordId}, "
                            f"using local time (may have clock drift)"
                        )
                        fill_time = datetime.now()

                    next_hour = fill_time.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)
                    sell_time_ms = int(next_hour.timestamp() * 1000)

                    # ✅ FIX: Use accFillSz string directly to preserve precision
                    # Validate that accFillSz is a valid numeric string
                    if not acc_fill_sz or acc_fill_sz == "" or acc_fill_sz == "0":
                        logger.error(
                            f"{strategy_name} Invalid accFillSz for filled order: "
                            f"{instId}, ordId={ordId}, accFillSz={acc_fill_sz}"
                        )
                        return

                    # Update database with filled status, actual fill data (as string to preserve precision), and recalculated sell_time
                    conn = get_db_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            """UPDATE orders
                               SET state = %s, size = %s, price = %s, sell_time = %s
                               WHERE instId = %s AND ordId = %s AND flag = %s""",
                            (
                                "filled",
                                acc_fill_sz,  # Use string directly to preserve precision
                                fill_px,
                                sell_time_ms,
                                instId,
                                ordId,
                                strategy_name,
                            ),
                        )
                        conn.commit()

                        # ✅ FIX: Update active_orders with actual filled size and recalculated next_hour_close_time
                        with lock:
                            if strategy_name == STRATEGY_NAME:
                                if instId in active_orders:
                                    active_orders[instId]["filled_size"] = filled_size
                                    active_orders[instId]["fill_price"] = (
                                        float(fill_px) if fill_px else 0.0
                                    )
                                    active_orders[instId][
                                        "next_hour_close_time"
                                    ] = next_hour
                                    active_orders[instId]["fill_time"] = fill_time
                                    logger.warning(
                                        f"{strategy_name} Updated active_order for fill: {instId}, "
                                        f"next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                    )
                            elif strategy_name == MOMENTUM_STRATEGY_NAME:
                                if instId in momentum_active_orders:
                                    # Update next_hour_close_time based on fill time
                                    momentum_active_orders[instId][
                                        "next_hour_close_time"
                                    ] = next_hour
                                    logger.warning(
                                        f"{strategy_name} Updated momentum_active_order for fill: {instId}, "
                                        f"ordId={ordId}, next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                    )

                        cur.close()
                    finally:
                        conn.close()
        except Exception as e:
            logger.error(
                f"{strategy_name} Error checking order status after timeout "
                f"{instId}, {ordId}: {e}"
            )
    except Exception as e:
        logger.error(f"{strategy_name} Error in timeout check {instId}, {ordId}: {e}")


def buy_momentum_order(
    instId: str, buy_price: float, buy_pct: float, tradeAPI: TradeAPI, conn
) -> Optional[str]:
    """Place momentum strategy buy order and record in database"""
    # Check blacklist before buying
    if check_blacklist_before_buy(instId):
        return None

    # Calculate size based on buy percentage
    total_amount = TRADING_AMOUNT_USDT * buy_pct
    size = total_amount / buy_price if buy_price > 0 else 0

    buy_price_str = format_number(buy_price, instId)
    size_str = format_number(size, instId)

    if SIMULATION_MODE:
        ordId = f"MVE-SIM-{uuid.uuid4().hex[:12]}"  # MVE = Momentum Volume Exhaustion
        amount_usdt = float(buy_price_str) * float(size_str)
        logger.warning(
            f"🛒 [SIM] MOMENTUM BUY: {instId}, price={buy_price_str}, "
            f"size={size_str}, amount={amount_usdt:.2f} USDT, "
            f"pct={buy_pct:.1%}, ordId={ordId}"
        )
    else:
        max_attempts = 3
        failed_flag = 0
        ordId = None

        for attempt in range(max_attempts):
            try:
                result = tradeAPI.place_order(
                    instId=instId,
                    tdMode="cash",
                    side="buy",
                    ordType="limit",
                    px=buy_price_str,
                    sz=size_str,
                )

                if result.get("code") == "0":
                    order_data = result.get("data", [{}])[0]
                    ordId = order_data.get("ordId")
                    if ordId:
                        amount_usdt = float(buy_price_str) * float(size_str)
                        logger.warning(
                            f"🛒 MOMENTUM BUY ORDER: {instId}, price={buy_price_str}, "
                            f"size={size_str}, amount={amount_usdt:.2f} USDT, "
                            f"pct={buy_pct:.1%}, ordId={ordId}"
                        )
                        failed_flag = 0
                        break
                    else:
                        logger.error(
                            f"{MOMENTUM_STRATEGY_NAME} buy limit: {instId}, no ordId"
                        )
                        failed_flag = 1
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{MOMENTUM_STRATEGY_NAME} buy limit failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{MOMENTUM_STRATEGY_NAME} buy limit error: {instId}, {e}")
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
        order_state = "filled" if SIMULATION_MODE else ""

        cur.execute(
            """INSERT INTO orders (instId, flag, ordId, create_time,
                       orderType, state, price, size, sell_time, side)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                instId,
                MOMENTUM_STRATEGY_NAME,
                ordId,
                create_time,
                "limit",
                order_state,
                buy_price_str,
                size_str,
                sell_time,
                "buy",
            ),
        )
        conn.commit()
        amount_usdt = float(buy_price_str) * float(size_str)
        logger.warning(
            f"✅ MOMENTUM BUY SAVED: {instId}, price={buy_price_str}, "
            f"size={size_str}, amount={amount_usdt:.2f} USDT, "
            f"pct={buy_pct:.1%}, ordId={ordId}"
        )

        play_sound("buy")
        return ordId
    except Exception as e:
        logger.error(
            f"{MOMENTUM_STRATEGY_NAME} buy limit DB error: {instId}, "
            f"ordId may be undefined, {e}"
        )
        conn.rollback()
        return None
    finally:
        cur.close()


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
        if api is None and not SIMULATION_MODE:
            logger.error(f"{STRATEGY_NAME} TradeAPI not available for {instId}")
            return

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
                        "sell_triggered": False,
                        # ✅ FIX: Initialize flag to prevent duplicate sells
                    }
                    logger.warning(
                        f"📊 ACTIVE ORDER: {instId}, ordId={ordId}, "
                        f"buy_price={limit_price:.6f}, "
                        f"sell_time={next_hour.strftime('%Y-%m-%d %H:%M:%S')}"
                    )

                    # Start 1-minute timeout check thread (only in real trading mode)
                    # In simulation mode, orders are assumed to be filled immediately
                    if not SIMULATION_MODE:
                        threading.Thread(
                            target=check_and_cancel_unfilled_order_after_timeout,
                            args=(instId, ordId, api, STRATEGY_NAME),
                            daemon=True,
                        ).start()
            else:
                # ✅ FIX: Order creation failed, clean up pending_buys
                logger.error(
                    f"❌ Failed to create buy order for {instId}, "
                    f"cleaning up pending_buys"
                )
                with lock:
                    if instId in pending_buys:
                        del pending_buys[instId]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_buy_signal error: {instId}, {e}")
        with lock:
            if instId in pending_buys:
                del pending_buys[instId]


def process_momentum_buy_signal(instId: str, buy_price: float, buy_pct: float):
    """Process momentum strategy buy signal in separate thread"""
    try:
        # Check blacklist before processing buy signal
        if check_blacklist_before_buy(instId):
            logger.warning(
                f"🚫 Skipping momentum buy signal for {instId} - blacklisted"
            )
            with lock:
                if instId in momentum_pending_buys:
                    del momentum_pending_buys[instId]
            return

        # Get trade API instance
        api = get_trade_api()
        if api is None and not SIMULATION_MODE:
            logger.error(
                f"{MOMENTUM_STRATEGY_NAME} TradeAPI not available for {instId}"
            )
            return

        # Place buy order
        conn = get_db_connection()
        try:
            ordId = buy_momentum_order(instId, buy_price, buy_pct, api, conn)
            if ordId:
                with lock:
                    if instId in momentum_pending_buys:
                        del momentum_pending_buys[instId]

                    # Record in momentum strategy
                    if momentum_strategy is not None:
                        total_amount = TRADING_AMOUNT_USDT * buy_pct
                        size = total_amount / buy_price if buy_price > 0 else 0
                        momentum_strategy.record_buy(instId, buy_price, size, ordId)

                    # Track in active orders
                    now = datetime.now()
                    next_hour = now.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)

                    if instId not in momentum_active_orders:
                        momentum_active_orders[instId] = {
                            "ordIds": [],
                            "buy_prices": [],
                            "buy_sizes": [],
                            "buy_times": [],
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                        }

                    momentum_active_orders[instId]["ordIds"].append(ordId)
                    momentum_active_orders[instId]["buy_prices"].append(buy_price)
                    total_amount = TRADING_AMOUNT_USDT * buy_pct
                    size = total_amount / buy_price if buy_price > 0 else 0
                    momentum_active_orders[instId]["buy_sizes"].append(size)
                    momentum_active_orders[instId]["buy_times"].append(now)

                    logger.warning(
                        f"📊 MOMENTUM ACTIVE ORDER: {instId}, ordId={ordId}, "
                        f"buy_price={buy_price:.6f}, pct={buy_pct:.1%}, "
                        f"sell_time={next_hour.strftime('%Y-%m-%d %H:%M:%S')}"
                    )

                    # Start 1-minute timeout check thread (only in real trading mode)
                    if not SIMULATION_MODE:
                        threading.Thread(
                            target=check_and_cancel_unfilled_order_after_timeout,
                            args=(instId, ordId, api, MOMENTUM_STRATEGY_NAME),
                            daemon=True,
                        ).start()
            else:
                logger.error(
                    f"❌ Failed to create momentum buy order for {instId}, "
                    f"cleaning up momentum_pending_buys"
                )
                with lock:
                    if instId in momentum_pending_buys:
                        del momentum_pending_buys[instId]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_momentum_buy_signal error: {instId}, {e}")
        with lock:
            if instId in momentum_pending_buys:
                del momentum_pending_buys[instId]


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
                ]  # Latest candle [ts, o, h, l, c, vol, volCcy, ...]
                # candle_data: [timestamp, open, high, low, close, volume, ...]
                if isinstance(candle_data, list) and len(candle_data) >= 9:
                    candle_ts = int(candle_data[0]) / 1000  # Convert ms to seconds
                    candle_hour = datetime.fromtimestamp(candle_ts).replace(
                        minute=0, second=0, microsecond=0
                    )
                    open_price = float(candle_data[1])  # Open price at index 1
                    confirm = str(candle_data[8])  # confirm is at index 8

                    # ✅ FIX: Update reference price from WebSocket candle data
                    # (more accurate and real-time)
                    # When a new hour starts, WebSocket sends the new hour's
                    # candle with open price
                    # This is better than calling REST API which may have
                    # timing issues
                    if instId in crypto_limits:
                        with lock:
                            # Update reference price if this is the current
                            # hour's candle
                            current_hour = datetime.now().replace(
                                minute=0, second=0, microsecond=0
                            )
                            # ✅ FIX: Strictly check - only accept current hour's candle
                            # Allow small tolerance (±60 seconds) for timing differences
                            time_diff = abs(
                                (candle_hour - current_hour).total_seconds()
                            )
                            if time_diff <= 60:
                                # This is current hour's candle
                                reference_prices[instId] = open_price
                                # ✅ OPTIMIZE: Reset fetch attempts on candle update
                                # This allows recovery even if ticker updates are missing
                                if (
                                    instId in reference_price_fetch_attempts
                                    and reference_price_fetch_attempts[instId] > 0
                                ):
                                    reference_price_fetch_attempts[instId] = 0
                                    logger.debug(
                                        f"📊 Reset reference_price_fetch_attempts for {instId} "
                                        f"on candle update (coin is active)"
                                    )
                                logger.debug(
                                    f"📊 {instId} updated reference price from "
                                    f"WebSocket: ${open_price:.6f} "
                                    f"(hour={candle_hour.strftime('%H:00')})"
                                )

                    # ✅ CRITICAL FIX: Update history only on confirmed candles
                    # 'confirm' = '1' means candle is confirmed (closed)
                    # OKX sends multiple unconfirmed updates during the hour, which would
                    # break the 1H unified time scale (M=10 would not represent 10 hours)
                    if confirm == "1":
                        # ✅ NEW: Track last confirmed candle time for monitoring
                        now = datetime.now()
                        with lock:
                            last_1h_candle_time[instId] = now
                        
                        # Update momentum strategy with confirmed candle data
                        # (only confirmed candles ensure true 1H time scale)
                        if momentum_strategy is not None and instId in crypto_limits:
                            candle_volume = (
                                float(candle_data[5]) if len(candle_data) > 5 else 0.0
                            )
                            close_price = (
                                float(candle_data[4])
                                if len(candle_data) > 4
                                else open_price
                            )
                            # Use volCcy (index 6) which is in quote currency (USDT)
                            # This is more consistent for comparison across different cryptos
                            volume_ccy = (
                                float(candle_data[6])
                                if len(candle_data) > 6
                                else candle_volume
                            )
                            # Use volume_ccy if available, otherwise fallback to base volume
                            volume_to_use = (
                                volume_ccy if volume_ccy > 0 else candle_volume
                            )
                            if volume_to_use > 0:
                                momentum_strategy.update_price_volume(
                                    instId, close_price, volume_to_use
                                )

                                # ✅ CRITICAL FIX: Check buy signal only on confirmed candles
                                # Using unconfirmed candles would trigger on temporary data
                                # (e.g., 30min/1min close prices), causing false signals
                                if (
                                    momentum_strategy is not None
                                    and instId in crypto_limits
                                ):
                                    should_buy, buy_pct = (
                                        momentum_strategy.check_buy_signal(
                                            instId, close_price
                                        )
                                    )
                                    if should_buy and buy_pct:
                                        with lock:
                                            # Check if already processing or has active orders
                                            if instId in momentum_pending_buys:
                                                logger.debug(
                                                    f"⏭️ {instId} Momentum buy already pending, skipping"
                                                )
                                            elif instId in momentum_active_orders:
                                                logger.debug(
                                                    f"⏭️ {instId} Momentum order already active, skipping"
                                                )
                                            else:
                                                # Check if already at max position
                                                position = (
                                                    momentum_strategy.get_position_info(
                                                        instId
                                                    )
                                                )
                                                if (
                                                    position
                                                    and position.get(
                                                        "total_buy_pct", 0.0
                                                    )
                                                    >= 0.70
                                                ):
                                                    logger.debug(
                                                        f"⏸️ {instId} Already at max position: "
                                                        f"{position.get('total_buy_pct', 0.0):.1%}"
                                                    )
                                                else:
                                                    momentum_pending_buys[instId] = True

                                                    logger.warning(
                                                        f"🎯 MOMENTUM BUY SIGNAL (confirmed 1H candle): {instId}, "
                                                        f"close_price={close_price:.6f}, buy_pct={buy_pct:.1%}"
                                                    )
                                                    # Trigger buy in separate thread
                                                    threading.Thread(
                                                        target=process_momentum_buy_signal,
                                                        args=(
                                                            instId,
                                                            close_price,
                                                            buy_pct,
                                                        ),
                                                        daemon=True,
                                                    ).start()

                        # Process sell signals for confirmed candles
                        # ✅ FIX: Check with lock to prevent race condition
                        # and duplicate triggers
                        with lock:
                            # Check original strategy
                            if instId in active_orders:
                                # Mark as processing to prevent duplicate triggers
                                # ✅ FIX: sell_triggered will be reset if sell fails
                                if active_orders[instId].get("sell_triggered", False):
                                    logger.debug(
                                        f"⚠️ Sell already triggered for {instId}, "
                                        f"skipping duplicate candle confirm"
                                    )
                                else:
                                    active_orders[instId]["sell_triggered"] = True
                                    # This hour's candle just closed, sell the position
                                    close_price = (
                                        float(candle_data[4])
                                        if len(candle_data) > 4
                                        else 0
                                    )
                                    logger.warning(
                                        f"🕐 KLINE CONFIRMED: {instId}, "
                                        f"close_price={close_price:.6f}, trigger SELL (original)"
                                    )
                                    threading.Thread(
                                        target=process_sell_signal,
                                        args=(instId,),
                                        daemon=True,
                                    ).start()

                            # Check momentum strategy
                            if instId in momentum_active_orders:
                                if momentum_active_orders[instId].get(
                                    "sell_triggered", False
                                ):
                                    logger.debug(
                                        f"⚠️ Momentum sell already triggered for {instId}, "
                                        f"skipping duplicate candle confirm"
                                    )
                                else:
                                    momentum_active_orders[instId][
                                        "sell_triggered"
                                    ] = True
                                    close_price = (
                                        float(candle_data[4])
                                        if len(candle_data) > 4
                                        else 0
                                    )
                                    logger.warning(
                                        f"🕐 KLINE CONFIRMED: {instId}, "
                                        f"close_price={close_price:.6f}, trigger SELL (momentum)"
                                    )
                                    threading.Thread(
                                        target=process_momentum_sell_signal,
                                        args=(instId,),
                                        daemon=True,
                                    ).start()
                    
                    # ✅ ENHANCEMENT: Check buy signal on unconfirmed candles (for intra-hour triggers)
                    # This allows buying during the hour if conditions are met
                    # Note: History is only updated on confirmed candles to maintain 1H time scale
                    # But we can check signals on any candle update using current price
                    # This logic is OUTSIDE the confirm block to enable intra-hour triggers
                    # Skip if confirm == "1" (already checked in confirm block above)
                    if confirm != "1" and momentum_strategy is not None and instId in crypto_limits:
                        # Use current close price from unconfirmed candle for signal check
                        # (but don't update history - that only happens on confirm)
                        current_close_price = (
                            float(candle_data[4])
                            if len(candle_data) > 4
                            else open_price
                        )
                        
                        # Check buy signal with current price (intra-hour trigger)
                        # This allows buying during the hour, not just at close
                        should_buy, buy_pct = momentum_strategy.check_buy_signal(
                            instId, current_close_price
                        )
                        if should_buy and buy_pct:
                            with lock:
                                # Check if already processing or has active orders
                                if instId in momentum_pending_buys:
                                    logger.debug(
                                        f"⏭️ {instId} Momentum buy already pending (intra-hour), skipping"
                                    )
                                elif instId in momentum_active_orders:
                                    logger.debug(
                                        f"⏭️ {instId} Momentum order already active (intra-hour), skipping"
                                    )
                                else:
                                    # Check if already at max position
                                    position = momentum_strategy.get_position_info(instId)
                                    if (
                                        position
                                        and position.get("total_buy_pct", 0.0) >= 0.70
                                    ):
                                        logger.debug(
                                            f"⏸️ {instId} Already at max position (intra-hour): "
                                            f"{position.get('total_buy_pct', 0.0):.1%}"
                                        )
                                    else:
                                        momentum_pending_buys[instId] = True

                                        logger.warning(
                                            f"🎯 MOMENTUM BUY SIGNAL (intra-hour): {instId}, "
                                            f"current_price={current_close_price:.6f}, buy_pct={buy_pct:.1%}"
                                        )
                                        # Trigger buy in separate thread
                                        threading.Thread(
                                            target=process_momentum_buy_signal,
                                            args=(
                                                instId,
                                                current_close_price,
                                                buy_pct,
                                            ),
                                            daemon=True,
                                        ).start()
    except Exception as e:
        logger.error(f"Candle message error: {msg_string}, {e}")


def process_sell_signal(instId: str):
    """Process sell signal at next hour close (idempotent)
    
    Features:
    - Idempotent: checks DB state first, returns early if already sold
    - Strict dedup: sets sell_triggered before attempt, resets on failure
    - Self-healing: works even if order not in active_orders (recovered from DB)
    """
    try:
        # ✅ ENHANCED: Get ordId from memory or DB
        ordId = None
        with lock:
            if instId in active_orders:
                order_info = active_orders[instId].copy()
                ordId = order_info.get("ordId")
            else:
                logger.debug(
                    f"{STRATEGY_NAME} Order not in active_orders: {instId}, "
                    f"will try to recover from DB"
                )

        # Get trade API instance
        api = get_trade_api()
        if api is None and not SIMULATION_MODE:
            logger.error(
                f"{STRATEGY_NAME} TradeAPI not available for sell: {instId}"
            )
            return

        # ✅ ENHANCED: Check order state and prevent duplicate sells (idempotent)
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            try:
                # If ordId not in memory, try to find it from DB
                if not ordId:
                    cur.execute(
                        """
                        SELECT ordId, state, size FROM orders
                        WHERE instId = %s AND flag = %s
                          AND state IN ('filled', 'partially_filled')
                          AND (sell_price IS NULL OR sell_price = '')
                        ORDER BY create_time DESC
                        LIMIT 1
                        """,
                        (instId, STRATEGY_NAME),
                    )
                    row = cur.fetchone()
                    if row:
                        ordId = row[0]
                        db_state = row[1] if row[1] else ""
                        db_size = row[2] if row[2] else "0"
                    else:
                        logger.debug(
                            f"{STRATEGY_NAME} No sellable order found in DB: {instId}"
                        )
                        return
                else:
                    # Query state and size together to validate order
                    cur.execute(
                        "SELECT state, size FROM orders WHERE instId = %s "
                        "AND ordId = %s AND flag = %s",
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

                # ✅ IDEMPOTENT: Prevent duplicate sells - check if already sold
                if db_state == "sold out":
                    logger.warning(f"{STRATEGY_NAME} Already sold: {instId}, {ordId}")
                    with lock:
                        if instId in active_orders:
                            del active_orders[instId]
                    return

                # ✅ FIX: Allow both "filled" and "partially_filled" states for selling
                # Use actual filled size for selling
                if (
                    db_state not in ["filled", "partially_filled"]
                    or not db_size
                    or db_size == "0"
                ):
                    logger.warning(
                        f"{STRATEGY_NAME} Order not ready to sell: {instId}, {ordId}, "
                        f"state={db_state}, size={db_size}"
                    )
                    # ✅ FIX: Don't remove from active_orders if state is empty or not filled yet
                    # Wait for order to be filled (might be delayed)
                    if db_state == "":
                        logger.info(
                            f"{STRATEGY_NAME} Order still pending fill: {instId}, {ordId}, "
                            f"will retry later"
                        )
                        # Reset sell_triggered to allow retry, but record attempt time for cooldown
                        with lock:
                            if instId in active_orders:
                                active_orders[instId]["sell_triggered"] = False
                                active_orders[instId][
                                    "last_sell_attempt_time"
                                ] = datetime.now()
                    else:
                        # Order is canceled or in invalid state, remove it
                        logger.warning(
                            f"{STRATEGY_NAME} Order in invalid state, removing: {instId}, {ordId}, "
                            f"state={db_state}"
                        )
                        with lock:
                            if instId in active_orders:
                                del active_orders[instId]
                    return

                # ✅ FIX: Use db_size string directly and validate precision before converting
                # This ensures we use the exact accFillSz value stored in database
                try:
                    size = float(db_size)
                    if size <= 0:
                        logger.error(
                            f"{STRATEGY_NAME} Invalid size for selling: {instId}, {ordId}, "
                            f"size={db_size}"
                        )
                        return
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"{STRATEGY_NAME} Cannot convert size to float: {instId}, {ordId}, "
                        f"size={db_size}, error={e}"
                    )
                    return
            finally:
                cur.close()

            # Place market sell order - verify success
            sell_success = sell_market_order(instId, ordId, size, api, conn)

            # ✅ FIX: Only remove from active orders AFTER successful sell
            if sell_success:
                with lock:
                    if instId in active_orders:
                        del active_orders[instId]
                        logger.warning(
                            f"{STRATEGY_NAME} Sold and removed: {instId}, {ordId}"
                        )
            else:
                logger.error(
                    f"❌ {STRATEGY_NAME} SELL FAILED: {instId}, {ordId}, "
                    f"keeping in active_orders for retry"
                )
                # ✅ FIX: Reset sell_triggered flag to allow retry
                with lock:
                    if instId in active_orders:
                        active_orders[instId]["sell_triggered"] = False
                        logger.warning(
                            f"{STRATEGY_NAME} Reset sell_triggered for {instId}, {ordId} to allow retry"
                        )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_sell_signal error: {instId}, {e}")
        # ✅ FIX: Don't clean up on exception - keep order for retry
        # Only reset sell_triggered flag to allow retry
        with lock:
            if instId in active_orders:
                active_orders[instId]["sell_triggered"] = False
                logger.warning(
                    f"{STRATEGY_NAME} Reset sell_triggered for {instId} after exception to allow retry"
                )


def process_momentum_sell_signal(instId: str):
    """Process momentum strategy sell signal at next hour close (idempotent)
    
    Features:
    - Idempotent: checks DB state first, returns early if already sold
    - Self-healing: works even if orders not in momentum_active_orders
    """
    try:
        # ✅ ENHANCED: Get ordIds from memory or DB
        ordIds = []
        with lock:
            if instId in momentum_active_orders:
                order_info = momentum_active_orders[instId].copy()
                ordIds = order_info.get("ordIds", [])

        # If not in memory, try to recover from DB
        if not ordIds:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT ordId FROM orders
                    WHERE instId = %s AND flag = %s
                      AND state IN ('filled', 'partially_filled')
                      AND (sell_price IS NULL OR sell_price = '')
                    ORDER BY create_time DESC
                    """,
                    (instId, MOMENTUM_STRATEGY_NAME),
                )
                rows = cur.fetchall()
                if rows:
                    ordIds = [row[0] for row in rows]
                    logger.warning(
                        f"🔄 RECOVER: Found momentum orders in DB for {instId}, "
                        f"count={len(ordIds)}"
                    )
                else:
                    logger.debug(
                        f"{MOMENTUM_STRATEGY_NAME} No sellable orders found: {instId}"
                    )
                    return
                cur.close()
            finally:
                conn.close()

        if not ordIds:
            logger.warning(f"{MOMENTUM_STRATEGY_NAME} No order IDs for {instId}")
            with lock:
                if instId in momentum_active_orders:
                    del momentum_active_orders[instId]
            return

        # Get trade API instance
        api = get_trade_api()
        if api is None and not SIMULATION_MODE:
            logger.error(
                f"{MOMENTUM_STRATEGY_NAME} TradeAPI not available for sell: {instId}"
            )
            return

        # Sell all orders for this crypto
        conn = get_db_connection()
        try:
            for ordId in ordIds:
                cur = conn.cursor()
                try:
                    # Query state and size
                    cur.execute(
                        "SELECT state, size FROM orders WHERE instId = %s "
                        "AND ordId = %s AND flag = %s",
                        (instId, ordId, MOMENTUM_STRATEGY_NAME),
                    )
                    row = cur.fetchone()

                    if not row:
                        logger.warning(
                            f"{MOMENTUM_STRATEGY_NAME} Order not found: {instId}, {ordId}"
                        )
                        with lock:
                            if instId in momentum_active_orders:
                                if ordId in momentum_active_orders[instId].get(
                                    "ordIds", []
                                ):
                                    idx = momentum_active_orders[instId][
                                        "ordIds"
                                    ].index(ordId)
                                    momentum_active_orders[instId]["ordIds"].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_prices", []
                                        )
                                    ):
                                        momentum_active_orders[instId][
                                            "buy_prices"
                                        ].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_sizes", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_sizes"].pop(
                                            idx
                                        )
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_times", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_times"].pop(
                                            idx
                                        )
                        continue

                    db_state = row[0] if row[0] else ""
                    db_size = row[1] if row[1] else "0"

                    # Skip if already sold
                    if db_state == "sold out":
                        logger.debug(
                            f"{MOMENTUM_STRATEGY_NAME} Already sold: {instId}, {ordId}"
                        )
                        continue

                    # ✅ FIX: Allow both "filled" and "partially_filled" states for selling
                    # Use actual filled size for selling
                    if (
                        db_state not in ["filled", "partially_filled"]
                        or not db_size
                        or db_size == "0"
                    ):
                        logger.warning(
                            f"{MOMENTUM_STRATEGY_NAME} Order not ready to sell: {instId}, {ordId}, "
                            f"state={db_state}, size={db_size}"
                        )
                        # ✅ OPTIMIZE: Track pending ordId state with timestamp to prevent permanent skip
                        # Don't return here as it would block other ordIds from selling
                        if db_state == "":
                            logger.info(
                                f"{MOMENTUM_STRATEGY_NAME} Order still pending fill: {instId}, {ordId}, "
                                f"will retry later, continuing to next order"
                            )
                            with lock:
                                if instId in momentum_active_orders:
                                    # Track pending ordIds with timestamp for retry tracking
                                    if (
                                        "pending_ordIds"
                                        not in momentum_active_orders[instId]
                                    ):
                                        momentum_active_orders[instId][
                                            "pending_ordIds"
                                        ] = {}
                                    momentum_active_orders[instId]["pending_ordIds"][
                                        ordId
                                    ] = {
                                        "first_pending_time": momentum_active_orders[
                                            instId
                                        ]["pending_ordIds"]
                                        .get(ordId, {})
                                        .get("first_pending_time")
                                        or datetime.now(),
                                        "retry_count": momentum_active_orders[instId][
                                            "pending_ordIds"
                                        ]
                                        .get(ordId, {})
                                        .get("retry_count", 0)
                                        + 1,
                                        "last_check_time": datetime.now(),
                                    }
                                    logger.debug(
                                        f"{MOMENTUM_STRATEGY_NAME} Tracked pending ordId: {instId}, {ordId}, "
                                        f"retry_count={momentum_active_orders[instId]['pending_ordIds'][ordId]['retry_count']}"
                                    )
                        continue

                    # ✅ FIX: Use db_size string directly and validate precision before converting
                    # This ensures we use the exact accFillSz value stored in database
                    try:
                        size = float(db_size)
                        if size <= 0:
                            logger.error(
                                f"{MOMENTUM_STRATEGY_NAME} Invalid size for selling: {instId}, {ordId}, "
                                f"size={db_size}"
                            )
                            continue
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"{MOMENTUM_STRATEGY_NAME} Cannot convert size to float: {instId}, {ordId}, "
                            f"size={db_size}, error={e}"
                        )
                        continue
                finally:
                    cur.close()

                # Place market sell order - verify success
                sell_success = sell_momentum_order(instId, ordId, size, api, conn)

                if not sell_success:
                    logger.error(
                        f"❌ {MOMENTUM_STRATEGY_NAME} SELL FAILED: {instId}, {ordId}, "
                        f"skipping remaining orders for this crypto"
                    )
                    # ✅ FIX: Reset sell_triggered flag to allow retry
                    with lock:
                        if instId in momentum_active_orders:
                            momentum_active_orders[instId]["sell_triggered"] = False
                            logger.warning(
                                f"{MOMENTUM_STRATEGY_NAME} Reset sell_triggered for {instId}, {ordId} to allow retry"
                            )
                    # Don't remove from active_orders if sell failed
                    return

                with lock:
                    if instId in momentum_active_orders:
                        if ordId in momentum_active_orders[instId].get("ordIds", []):
                            idx = momentum_active_orders[instId]["ordIds"].index(ordId)
                            momentum_active_orders[instId]["ordIds"].pop(idx)
                            if idx < len(
                                momentum_active_orders[instId].get("buy_prices", [])
                            ):
                                momentum_active_orders[instId]["buy_prices"].pop(idx)
                            if idx < len(
                                momentum_active_orders[instId].get("buy_sizes", [])
                            ):
                                momentum_active_orders[instId]["buy_sizes"].pop(idx)
                            if idx < len(
                                momentum_active_orders[instId].get("buy_times", [])
                            ):
                                momentum_active_orders[instId]["buy_times"].pop(idx)

            # ✅ FIX: Only remove when all ordIds are cleared
            with lock:
                if instId in momentum_active_orders:
                    if not momentum_active_orders[instId].get("ordIds", []):
                        del momentum_active_orders[instId]
                        if momentum_strategy is not None:
                            momentum_strategy.reset_position(instId)
                        logger.warning(
                            f"{MOMENTUM_STRATEGY_NAME} Sold and removed: {instId}"
                        )
                    else:
                        momentum_active_orders[instId]["sell_triggered"] = False
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_momentum_sell_signal error: {instId}, {e}")
        # ✅ FIX: Don't clean up on exception - keep order for retry
        # Only reset sell_triggered flag to allow retry
        with lock:
            if instId in momentum_active_orders:
                momentum_active_orders[instId]["sell_triggered"] = False
                logger.warning(
                    f"{MOMENTUM_STRATEGY_NAME} Reset sell_triggered for {instId} after exception to allow retry"
                )


def sell_momentum_order(
    instId: str, ordId: str, size: float, tradeAPI: TradeAPI, conn
) -> bool:
    """Place momentum strategy market sell order

    Returns:
        True if sell order was successfully placed and recorded, False otherwise
    """
    size = format_number(size, instId)

    if SIMULATION_MODE:
        with lock:
            sell_price = current_prices.get(instId, 0.0)

        if sell_price <= 0:
            try:
                market_api = get_market_api()
                ticker_result = market_api.get_ticker(instId=instId)
                if ticker_result.get("code") == "0" and ticker_result.get("data"):
                    ticker_data = ticker_result["data"]
                    if ticker_data and len(ticker_data) > 0:
                        sell_price = float(ticker_data[0].get("last", 0))
            except Exception as e:
                logger.warning(f"⚠️ Could not get current price for {instId}: {e}")

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"💰 [SIM] MOMENTUM SELL: {instId}, price={sell_price:.6f}, "
            f"size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
    else:
        max_attempts = 3
        failed_flag = 0
        sell_price = 0.0

        for attempt in range(max_attempts):
            try:
                result = tradeAPI.place_order(
                    instId=instId,
                    tdMode="cash",
                    side="sell",
                    ordType="market",
                    sz=str(size),
                    tgtCcy="base_ccy",
                )

                if result.get("code") == "0":
                    order_data = result.get("data", [{}])[0]
                    order_id = order_data.get("ordId", "N/A")

                    time.sleep(0.5)
                    try:
                        order_result = tradeAPI.get_order(instId=instId, ordId=order_id)
                        if order_result.get("code") == "0" and order_result.get("data"):
                            order_info = order_result["data"][0]
                            fill_px = order_info.get("fillPx", "")
                            acc_fill_sz = order_info.get("accFillSz", "0")

                            if (
                                fill_px
                                and fill_px != ""
                                and acc_fill_sz
                                and float(acc_fill_sz) > 0
                            ):
                                sell_price = float(fill_px)
                                logger.warning(
                                    f"💰 MOMENTUM SELL ORDER: {instId}, "
                                    f"fill price={sell_price:.6f}, "
                                    f"size={size}, ordId={order_id}"
                                )
                            else:
                                with lock:
                                    sell_price = current_prices.get(instId, 0.0)
                                logger.warning(
                                    f"💰 MOMENTUM SELL ORDER: {instId}, "
                                    f"using current price={sell_price:.6f}, "
                                    f"ordId={order_id}"
                                )
                        else:
                            with lock:
                                sell_price = current_prices.get(instId, 0.0)
                            logger.warning(
                                f"💰 MOMENTUM SELL ORDER: {instId}, "
                                f"using current price={sell_price:.6f}, "
                                f"ordId={order_id}"
                            )
                    except Exception as e:
                        with lock:
                            sell_price = current_prices.get(instId, 0.0)
                        logger.warning(
                            f"💰 MOMENTUM SELL ORDER: {instId}, "
                            f"using current price={sell_price:.6f}, "
                            f"error: {e}, ordId={order_id}"
                        )

                    failed_flag = 0
                    break
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{MOMENTUM_STRATEGY_NAME} sell market failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(
                    f"{MOMENTUM_STRATEGY_NAME} sell market error: {instId}, {e}"
                )
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(1)

        if failed_flag > 0:
            logger.error(
                f"❌ {MOMENTUM_STRATEGY_NAME} SELL FAILED: {instId}, ordId={ordId}, "
                f"all {max_attempts} attempts failed"
            )
            return False

    # Update database - verify update succeeded
    cur = conn.cursor()
    try:
        sell_price_str = format_number(sell_price, instId) if sell_price > 0 else ""

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s "
            "WHERE instId = %s AND ordId = %s AND flag = %s",
            ("sold out", sell_price_str, instId, ordId, MOMENTUM_STRATEGY_NAME),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {MOMENTUM_STRATEGY_NAME} SELL DB UPDATE FAILED: {instId}, ordId={ordId}, "
                f"no rows updated"
            )
            return False

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"✅ MOMENTUM SELL SAVED: {instId}, price={sell_price_str}, "
            f"size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )

        play_sound("sell")
        return True
    except Exception as e:
        logger.error(
            f"{MOMENTUM_STRATEGY_NAME} sell market DB error: {instId}, {ordId}, {e}"
        )
        conn.rollback()
        return False
    finally:
        cur.close()


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


def sync_orders_from_database():
    """Sync active_orders with database state
    This handles cases where external processes or manual operations
    sold orders but websocket_limit_trading.py memory still thinks they're active
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check original strategy orders
        with lock:
            orders_to_check = list(active_orders.items())

        for instId, order_info in orders_to_check:
            ordId = order_info.get("ordId")
            if not ordId:
                continue

            try:
                # Check database state
                cur.execute(
                    "SELECT state FROM orders WHERE instId = %s AND ordId = %s AND flag = %s",
                    (instId, ordId, STRATEGY_NAME),
                )
                row = cur.fetchone()

                if row:
                    db_state = row[0] if row[0] else ""
                    # If database says sold but memory thinks active, sync memory
                    if db_state == "sold out":
                        with lock:
                            if (
                                instId in active_orders
                                and active_orders[instId].get("ordId") == ordId
                            ):
                                logger.warning(
                                    f"🔄 SYNC: {instId} (original) already sold in DB, "
                                    f"removing from active_orders"
                                )
                                del active_orders[instId]
            except Exception as e:
                logger.debug(f"Error checking order {instId}/{ordId}: {e}")

        # Check momentum strategy orders
        with lock:
            momentum_orders_to_check = list(momentum_active_orders.items())

        for instId, order_info in momentum_orders_to_check:
            ordIds = order_info.get("ordIds", [])
            if not ordIds:
                continue

            try:
                # Check each order in the list
                ordIds_to_remove = []
                for ordId in ordIds:
                    cur.execute(
                        "SELECT state FROM orders WHERE instId = %s AND ordId = %s AND flag = %s",
                        (instId, ordId, MOMENTUM_STRATEGY_NAME),
                    )
                    row = cur.fetchone()

                    if row:
                        db_state = row[0] if row[0] else ""
                        if db_state == "sold out":
                            ordIds_to_remove.append(ordId)

                # Remove sold orders from memory
                if ordIds_to_remove:
                    with lock:
                        if instId in momentum_active_orders:
                            for ordId in ordIds_to_remove:
                                if ordId in momentum_active_orders[instId].get(
                                    "ordIds", []
                                ):
                                    idx = momentum_active_orders[instId][
                                        "ordIds"
                                    ].index(ordId)
                                    momentum_active_orders[instId]["ordIds"].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_prices", []
                                        )
                                    ):
                                        momentum_active_orders[instId][
                                            "buy_prices"
                                        ].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_sizes", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_sizes"].pop(
                                            idx
                                        )
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_times", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_times"].pop(
                                            idx
                                        )
                                    logger.warning(
                                        f"🔄 SYNC: {instId} (momentum) ordId={ordId} already sold in DB, "
                                        f"removing from momentum_active_orders"
                                    )

                            # If no more orders, remove the entry
                            if not momentum_active_orders[instId].get("ordIds", []):
                                del momentum_active_orders[instId]
                                if momentum_strategy is not None:
                                    momentum_strategy.reset_position(instId)
                                logger.warning(
                                    f"🔄 SYNC: {instId} (momentum) all orders sold, "
                                    f"removed from momentum_active_orders"
                                )
            except Exception as e:
                logger.debug(f"Error checking momentum orders {instId}: {e}")

        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error in sync_orders_from_database: {e}")


def recover_orders_from_database(now: datetime):
    """Reverse validation: find filled orders in DB that should be sold
    
    This handles cases where:
    - Orders are filled but not in active_orders (process restart)
    - WS confirm message was missed
    - Memory state was lost
    
    Args:
        now: Current datetime for time comparison
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # ✅ FIX: Remove 24h and LIMIT restrictions to prevent missing orders
        # Find original strategy orders: filled/partially_filled but not sold
        cur.execute(
            """
            SELECT instId, ordId, create_time, state, size
            FROM orders
            WHERE flag = %s
              AND state IN ('filled', 'partially_filled')
              AND (sell_price IS NULL OR sell_price = '')
            ORDER BY create_time DESC
            """,
            (STRATEGY_NAME,),
        )
        rows = cur.fetchall()

        for row in rows:
            instId = row[0]
            ordId = row[1]
            create_time_ms = row[2]
            db_state = row[3]
            db_size = row[4]

            # Check if already in active_orders
            with lock:
                if instId in active_orders:
                    # Already tracked, skip (will be handled by timeout check)
                    continue

            # ✅ FIX: Get fillTime from OKX API instead of using create_time
            # create_time is when order was placed, fillTime is when it was filled
            # For late fills or partial fills, using fillTime is more accurate
            fill_time = None
            next_hour = None
            
            api = get_trade_api()
            if api is not None:
                try:
                    result = api.get_order(instId=instId, ordId=ordId)
                    if result and result.get("data") and len(result["data"]) > 0:
                        order_data = result["data"][0]
                        fill_time_ms = order_data.get("fillTime", "")
                        if fill_time_ms and fill_time_ms != "":
                            try:
                                fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                                logger.info(
                                    f"✅ RECOVER: Using OKX fillTime for {instId}, ordId={ordId}: "
                                    f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                )
                            except (ValueError, TypeError) as e:
                                logger.warning(
                                    f"⚠️ RECOVER: Invalid fillTime from OKX: {fill_time_ms}, "
                                    f"falling back to create_time: {e}"
                                )
                except Exception as e:
                    logger.warning(
                        f"⚠️ RECOVER: Failed to get order from OKX for {instId}, "
                        f"ordId={ordId}: {e}, falling back to create_time"
                    )
            
            # Fallback to create_time if fillTime not available
            if fill_time is None:
                fill_time = datetime.fromtimestamp(create_time_ms / 1000)
                logger.debug(
                    f"📝 RECOVER: Using create_time as fallback for {instId}, ordId={ordId}"
                )
            
            # Calculate next_hour_close_time from fill_time (or create_time fallback)
            next_hour = fill_time.replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(hours=1)

            # Only recover if past sell time
            if now >= next_hour:
                logger.warning(
                    f"🔄 RECOVER: Found filled order not in memory: {instId}, "
                    f"ordId={ordId}, state={db_state}, fill_time={fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                    f"recovering to active_orders"
                )

                # Restore to active_orders
                with lock:
                    active_orders[instId] = {
                        "ordId": ordId,
                        "next_hour_close_time": next_hour,
                        "sell_triggered": False,
                        "fill_time": fill_time,
                        "last_sell_attempt_time": None,
                    }

                # Trigger sell immediately
                logger.warning(
                    f"⏰ RECOVER SELL: {instId} (original), "
                    f"triggering sell for recovered order"
                )
                threading.Thread(
                    target=process_sell_signal, args=(instId,), daemon=True
                ).start()

        # ✅ FIX: Remove 24h and LIMIT restrictions to prevent missing orders
        # Find momentum strategy orders
        cur.execute(
            """
            SELECT instId, ordId, create_time, state, size
            FROM orders
            WHERE flag = %s
              AND state IN ('filled', 'partially_filled')
              AND (sell_price IS NULL OR sell_price = '')
            ORDER BY create_time DESC
            """,
            (MOMENTUM_STRATEGY_NAME,),
        )
        rows = cur.fetchall()

        # Group by instId for momentum (can have multiple orders)
        momentum_orders_by_inst = {}
        for row in rows:
            instId = row[0]
            ordId = row[1]
            create_time_ms = row[2]
            db_state = row[3]
            db_size = row[4]

            if instId not in momentum_orders_by_inst:
                momentum_orders_by_inst[instId] = []

            momentum_orders_by_inst[instId].append({
                "ordId": ordId,
                "create_time": datetime.fromtimestamp(create_time_ms / 1000),
                "create_time_ms": create_time_ms,
                "state": db_state,
                "size": db_size,
            })

        for instId, orders in momentum_orders_by_inst.items():
            with lock:
                if instId in momentum_active_orders:
                    # Already tracked, skip
                    continue

            # ✅ FIX: Get fillTime from OKX API for each order, use earliest fillTime
            # This ensures accurate sell time calculation for late/partial fills
            earliest_fill_time = None
            api = get_trade_api()
            
            if api is not None:
                for order in orders:
                    ordId = order["ordId"]
                    try:
                        result = api.get_order(instId=instId, ordId=ordId)
                        if result and result.get("data") and len(result["data"]) > 0:
                            order_data = result["data"][0]
                            fill_time_ms = order_data.get("fillTime", "")
                            if fill_time_ms and fill_time_ms != "":
                                try:
                                    fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                                    if earliest_fill_time is None or fill_time < earliest_fill_time:
                                        earliest_fill_time = fill_time
                                    logger.debug(
                                        f"✅ RECOVER: Using OKX fillTime for momentum {instId}, "
                                        f"ordId={ordId}: {fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                                except (ValueError, TypeError):
                                    pass
                    except Exception as e:
                        logger.debug(
                            f"⚠️ RECOVER: Failed to get order from OKX for momentum {instId}, "
                            f"ordId={ordId}: {e}"
                        )
            
            # Fallback to earliest create_time if fillTime not available
            if earliest_fill_time is None:
                earliest_fill_time = min(o["create_time"] for o in orders)
                logger.debug(
                    f"📝 RECOVER: Using earliest create_time as fallback for momentum {instId}"
                )
            
            # Calculate next_hour_close_time from earliest fill_time
            next_hour = earliest_fill_time.replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(hours=1)

            if now >= next_hour:
                logger.warning(
                    f"🔄 RECOVER: Found momentum orders not in memory: {instId}, "
                    f"count={len(orders)}, earliest_fill_time={earliest_fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                    f"recovering to momentum_active_orders"
                )

                # Restore to momentum_active_orders
                with lock:
                    momentum_active_orders[instId] = {
                        "ordIds": [o["ordId"] for o in orders],
                        "buy_prices": [],  # Will be filled from DB if needed
                        "buy_sizes": [float(o["size"]) for o in orders],
                        "buy_times": [earliest_fill_time] * len(orders),  # Use fill_time
                        "next_hour_close_time": next_hour,
                        "sell_triggered": False,
                        "last_sell_attempt_time": None,
                    }

                # Trigger sell immediately
                logger.warning(
                    f"⏰ RECOVER SELL: {instId} (momentum), "
                    f"triggering sell for recovered orders"
                )
                threading.Thread(
                    target=process_momentum_sell_signal, args=(instId,), daemon=True
                ).start()

        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error in recover_orders_from_database: {e}")


def monitor_websocket_health(now: datetime):
    """Monitor WebSocket health: alert if 1H candles not received for too long
    
    Args:
        now: Current datetime for time comparison
    """
    try:
        with lock:
            stale_cryptos = []
            for instId, last_candle_time in list(last_1h_candle_time.items()):
                if instId not in crypto_limits:
                    continue
                    
                time_since_last = (now - last_candle_time).total_seconds() / 60
                if time_since_last > CANDLE_TIMEOUT_MINUTES:
                    stale_cryptos.append((instId, time_since_last))
            
            # Also check cryptos that should have candles but don't
            for instId in crypto_limits.keys():
                if instId not in last_1h_candle_time:
                    # Never received a candle, but that's OK on startup
                    # Only alert if it's been running for a while
                    pass
        
        if stale_cryptos:
            for instId, minutes in stale_cryptos:
                logger.error(
                    f"⚠️ WS HEALTH: {instId} no 1H candle for {minutes:.1f} minutes "
                    f"(>{CANDLE_TIMEOUT_MINUTES}min threshold). "
                    f"Relying on timeout sell mechanism."
                )
    except Exception as e:
        logger.debug(f"Error in monitor_websocket_health: {e}")


def check_sell_timeout():
    """Unified sell scheduler: robust fallback mechanism
    
    Features:
    1. Scans every 60 seconds for orders past sell time
    2. Reverse validation from DB: finds filled orders not yet sold
    3. Self-healing: recovers from WS packet loss, process restart, etc.
    4. Idempotent: prevents duplicate sells via DB state check
    """
    sync_counter = 0
    while True:
        try:
            time.sleep(60)  # ✅ FIX: Check every 60 seconds (was 30)
            now = datetime.now()

            # ✅ FIX: Sync with database every cycle (1 minute)
            # This ensures memory state matches database state
            sync_counter += 1
            sync_orders_from_database()
            
            # ✅ NEW: Reverse validation from DB - find filled orders not yet sold
            recover_orders_from_database(now)
            
            # ✅ NEW: Monitor WebSocket health - alert if candles not received
            monitor_websocket_health(now)

            # ✅ ENHANCED: Check all orders (memory + DB) for sell triggers
            orders_to_sell = []
            
            # Check original strategy orders from memory
            with lock:
                for instId, order_info in list(active_orders.items()):
                    next_hour_close = order_info.get("next_hour_close_time")
                    if next_hour_close and now >= next_hour_close:
                        # Past sell time, check if already triggered
                        if not order_info.get("sell_triggered", False):
                            orders_to_sell.append((instId, "original"))
                            # ✅ STRICT DEDUP: Set sell_triggered BEFORE attempting sell
                            # Will be reset if sell fails
                            order_info["sell_triggered"] = True
                            order_info["last_sell_attempt_time"] = now

                # Check momentum strategy orders from memory
                for instId, order_info in list(momentum_active_orders.items()):
                    next_hour_close = order_info.get("next_hour_close_time")
                    if next_hour_close and now >= next_hour_close:
                        if not order_info.get("sell_triggered", False):
                            orders_to_sell.append((instId, "momentum"))
                            order_info["sell_triggered"] = True
                            order_info["last_sell_attempt_time"] = now

            # Trigger sells outside of lock
            for instId, strategy_type in orders_to_sell:
                logger.warning(
                    f"⏰ TIMEOUT SELL: {instId} ({strategy_type}), "
                    f"next_hour_close_time reached, triggering sell"
                )
                if strategy_type == "original":
                    threading.Thread(
                        target=process_sell_signal, args=(instId,), daemon=True
                    ).start()
                elif strategy_type == "momentum":
                    threading.Thread(
                        target=process_momentum_sell_signal, args=(instId,), daemon=True
                    ).start()
        except Exception as e:
            logger.error(f"Error in check_sell_timeout: {e}")
            time.sleep(60)  # Wait longer on error


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

    # Initialize momentum strategy with historical data
    # This avoids waiting 11 hours after program startup
    initialize_momentum_strategy_history()

    # Initialize reference prices (current hour's open prices)
    initialize_reference_prices()

    # Initialize database connection with retry
    try:
        conn = get_db_connection()
        conn.close()
        logger.warning("✅ Connected to PostgreSQL database successfully")
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

    # ✅ ENHANCED: Recover orders from database on startup
    # This handles process restart - restores active_orders from DB
    logger.warning("🔄 Recovering orders from database on startup...")
    now = datetime.now()
    recover_orders_from_database(now)
    sync_orders_from_database()
    logger.warning("✅ Database recovery and sync completed")

    # ✅ FIX: Start background thread to check sell timeouts (fallback mechanism)
    timeout_check_thread = threading.Thread(
        target=check_sell_timeout, daemon=True, name="SellTimeoutChecker"
    )
    timeout_check_thread.start()
    logger.warning("✅ Sell timeout checker thread started")

    # Keep main thread alive with health check
    last_refresh_hour = datetime.now().replace(minute=0, second=0, microsecond=0)

    try:
        while True:
            time.sleep(60)
            # Periodic status log
            with lock:
                logger.info(
                    f"Status: {len(current_prices)} prices, "
                    f"{len(reference_prices)} reference prices, "
                    f"{len(active_orders)} active orders"
                )

            now = datetime.now()
            current_hour = now.replace(minute=0, second=0, microsecond=0)

            # Hourly refresh: update reference prices at start of new hour
            # ✅ FIX: Refresh every hour since we use hourly open price, not daily
            # ⚠️ IMPORTANT: Delay a few seconds after hour start to ensure
            # new hour's K-line is available
            # OKX may not have the new hour's K-line immediately at 00:00,
            # so wait until 00:05
            if current_hour > last_refresh_hour and now.minute >= 1:
                logger.warning(
                    f"🔄 New hour detected ({current_hour.strftime('%H:00')}), "
                    f"refreshing reference prices (hourly open)..."
                )
                initialize_reference_prices()
                last_refresh_hour = current_hour

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
