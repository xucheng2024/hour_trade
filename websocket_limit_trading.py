#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real-time Trading System using WebSocket
Subscribes to OKX tickers and candles, buys at limit prices, sells at next hour close
"""

import json
import logging
import os
import sys
import threading
import time
import warnings
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
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
TRADING_FLAG = os.getenv("TRADING_FLAG", "0")  # 0=production, 1=demo

# Trading Configuration
TRADING_AMOUNT_USDT = int(
    os.getenv("TRADING_AMOUNT_USDT", "100")
)  # Amount per trade in USDT
STRATEGY_NAME = "hourly_limit_ws"
MOMENTUM_STRATEGY_NAME = "momentum_volume_exhaustion"
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "true").lower() == "true"

# Strategy Parameters - Environment configurable
INTRA_HOUR_CHECK_THROTTLE_SECONDS = int(
    os.getenv("INTRA_HOUR_CHECK_THROTTLE_SECONDS", "30")
)
CANDLE_TIMEOUT_MINUTES = int(os.getenv("CANDLE_TIMEOUT_MINUTES", "90"))
TIMEOUT_CHECK_INTERVAL_SECONDS = int(os.getenv("TIMEOUT_CHECK_INTERVAL_SECONDS", "60"))

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
# Railway logs are billed, reduce file logging frequency
# Only log to stdout in Railway (file logging disabled by default)
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
# Reduce debug logging for high-frequency market data
REDUCE_MARKET_DATA_LOGS = os.getenv("REDUCE_MARKET_DATA_LOGS", "true").lower() == "true"

handlers = [logging.StreamHandler()]

if LOG_TO_FILE:
    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    handlers.append(file_handler)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=handlers,
)
logger = logging.getLogger(__name__)

# Import extracted modules (after logger is initialized)
# Import core utilities first (they don't depend on numpy/pandas)
try:
    from core.trading_utils import load_crypto_limits as _load_crypto_limits
    from core.trading_utils import calculate_limit_price as _calculate_limit_price
    from core.trading_utils import extract_base_currency as _extract_base_currency
    from core.trading_utils import play_sound as _play_sound
    from core.trading_utils import (
        check_blacklist_before_buy as _check_blacklist_before_buy,
    )
    from core.trading_utils import (
        remove_crypto_from_system as _remove_crypto_from_system,
    )
    from core.trading_utils import (
        initialize_momentum_strategy_history as _initialize_momentum_strategy_history,
    )
except ImportError as e:
    logger.error(f"Failed to import core trading_utils: {e}")
    _load_crypto_limits = None
    _calculate_limit_price = None
    _extract_base_currency = None
    _play_sound = None
    _check_blacklist_before_buy = None
    _remove_crypto_from_system = None
    _initialize_momentum_strategy_history = None

# Import other modules (may depend on numpy/pandas)
try:
    from core.okx_functions import format_number as _format_number
    from core.okx_functions import get_instrument_precision as _get_instrument_precision
    from core.okx_functions import get_market_api as _get_market_api
    from core.okx_functions import get_public_api as _get_public_api
    from core.okx_functions import get_trade_api as _get_trade_api
except ImportError as e:
    logger.warning(f"Failed to import okx_functions (numpy/pandas may be missing): {e}")
    _format_number = None
    _get_instrument_precision = None
    _get_market_api = None
    _get_public_api = None
    _get_trade_api = None

try:
    from core.order_processing import buy_limit_order as _buy_limit_order
    from core.order_processing import buy_momentum_order as _buy_momentum_order
    from core.order_processing import sell_market_order as _sell_market_order
    from core.order_processing import sell_momentum_order as _sell_momentum_order
except ImportError as e:
    logger.warning(f"Failed to import order_processing: {e}")
    _buy_limit_order = None
    _buy_momentum_order = None
    _sell_market_order = None
    _sell_momentum_order = None

try:
    from core.order_sync import OrderSyncManager
except ImportError as e:
    logger.warning(f"Failed to import order_sync: {e}")
    OrderSyncManager = None

try:
    from core.order_timeout import (
        check_and_cancel_unfilled_order_after_timeout as _check_and_cancel_unfilled_order_after_timeout,
    )
except ImportError as e:
    logger.warning(f"Failed to import order_timeout: {e}")
    _check_and_cancel_unfilled_order_after_timeout = None

try:
    from core.price_manager import PriceManager
except ImportError as e:
    logger.warning(f"Failed to import price_manager: {e}")
    PriceManager = None

try:
    from core.signal_processing import process_buy_signal as _process_buy_signal
    from core.signal_processing import process_sell_signal as _process_sell_signal
    from core.signal_processing import (
        process_momentum_buy_signal as _process_momentum_buy_signal,
    )
    from core.signal_processing import (
        process_momentum_sell_signal as _process_momentum_sell_signal,
    )
except ImportError as e:
    logger.warning(f"Failed to import signal_processing: {e}")
    _process_buy_signal = None
    _process_sell_signal = None
    _process_momentum_buy_signal = None
    _process_momentum_sell_signal = None

try:
    from core.websocket_connection import candle_open as _candle_open
    from core.websocket_connection import connect_websocket as _connect_websocket
    from core.websocket_connection import ticker_open as _ticker_open
except ImportError as e:
    logger.warning(f"Failed to import websocket_connection: {e}")
    _candle_open = None
    _connect_websocket = None
    _ticker_open = None

try:
    from core.websocket_handlers import on_candle_message as _on_candle_message
    from core.websocket_handlers import on_ticker_message as _on_ticker_message
except ImportError as e:
    logger.warning(f"Failed to import websocket_handlers: {e}")
    _on_candle_message = None
    _on_ticker_message = None

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
)  # instId -> {ordId, buy_price, buy_time, next_hour_close_time, fill_time, ...}
# Momentum strategy active orders (separate tracking)
momentum_active_orders: Dict[str, Dict] = (
    {}
)  # instId -> {ordIds: [str], buy_prices: [float], buy_sizes: [float], next_hour_close_times: [datetime], ...}
# ✅ FIX: Throttle intra-hour buy signal checks to prevent CPU overload
last_intra_hour_check: Dict[str, datetime] = {}  # instId -> last check time
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
    """Initialize momentum strategy with historical 1H candle data"""
    if _initialize_momentum_strategy_history:
        _initialize_momentum_strategy_history(
            momentum_strategy, crypto_limits, get_market_api
        )
    else:
        logger.error(
            "initialize_momentum_strategy_history not available - module import failed"
        )


# WebSocket connections for unsubscribe (using dict refs for module compatibility)
ticker_ws_ref: Dict[str, Optional[websocket.WebSocketApp]] = {"ws": None}
candle_ws_ref: Dict[str, Optional[websocket.WebSocketApp]] = {"ws": None}
ws_lock = threading.Lock()

# Backward compatibility
ticker_ws = ticker_ws_ref["ws"]
candle_ws = candle_ws_ref["ws"]

# ✅ NEW: Track last 1H candle receive time for monitoring
# Format: instId -> last_candle_timestamp
last_1h_candle_time: Dict[str, datetime] = {}


def get_trade_api() -> Optional[TradeAPI]:
    """Get or initialize TradeAPI instance (singleton)

    Returns:
        TradeAPI instance, or None if in simulation mode without API keys
    """
    return _get_trade_api(
        API_KEY, API_SECRET, API_PASSPHRASE, TRADING_FLAG, SIMULATION_MODE
    )


def get_market_api() -> MarketAPI:
    """Get or initialize MarketAPI instance (singleton)"""
    return _get_market_api(TRADING_FLAG)


def get_public_api() -> PublicAPI:
    """Get or initialize PublicAPI instance (singleton)"""
    return _get_public_api(TRADING_FLAG)


def get_instrument_precision(instId: str, use_cache: bool = True) -> Optional[Dict]:
    """Get instrument precision info (lotSz, tickSz, minSz) from OKX API
    Returns None if API call fails, falls back to format_number default behavior
    """
    return _get_instrument_precision(instId, use_cache, TRADING_FLAG)


def get_db_connection(max_retries=None, retry_delay=None):
    """Get PostgreSQL database connection with retry logic

    Note: Neon database URL includes '-pooler' which provides connection pooling
    at the database level. For high-load scenarios, consider implementing
    application-level connection pooling (e.g., psycopg2.pool) to further
    reduce connection overhead.
    """
    # Environment-configurable connection parameters
    max_retries = max_retries or int(os.getenv("DB_CONNECT_MAX_RETRIES", "3"))
    retry_delay = retry_delay or float(os.getenv("DB_CONNECT_RETRY_DELAY", "1.0"))
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))  # Reduced from 10 to 5

    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=connect_timeout)
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
    """Play sound notification (buy or sell)"""
    if _play_sound:
        _play_sound(sound_type)
    else:
        logger.debug("play_sound not available - module import failed")


def format_number(number, instId: Optional[str] = None):
    """Format number according to OKX precision requirements
    If instId is provided, uses OKX instrument precision (lotSz) for better accuracy
    Falls back to heuristic precision if instrument info is not available

    Args:
        number: Number to format (price or size)
        instId: Optional instrument ID (e.g., 'BTC-USDT') to use instrument-specific precision
    """
    if _format_number is None:
        logger.error("format_number module not available - module import failed")
        raise RuntimeError("format_number function not available")
    return _format_number(number, instId, TRADING_FLAG)


def extract_base_currency(instId):
    """Extract base currency from instId (e.g., 'BTC-USDT' -> 'BTC')"""
    if _extract_base_currency:
        return _extract_base_currency(instId)
    if "-" in instId:
        return instId.split("-")[0]
    return instId


def remove_crypto_from_system(instId: str):
    """Remove crypto from hour_limit table, memory, and unsubscribe from WebSocket"""
    if _remove_crypto_from_system:
        return _remove_crypto_from_system(
            instId,
            get_db_connection,
            crypto_limits,
            current_prices,
            reference_prices,
            reference_price_fetch_time,
            reference_price_fetch_attempts,
            pending_buys,
            active_orders,
            lock,
            unsubscribe_from_websocket,
        )
    logger.error("remove_crypto_from_system not available - module import failed")
    return False


def unsubscribe_from_websocket(instId: str):
    """Unsubscribe from ticker and candle WebSocket for a specific crypto"""
    try:
        with ws_lock:
            # Unsubscribe from ticker
            if ticker_ws_ref["ws"]:
                try:
                    msg = {
                        "op": "unsubscribe",
                        "args": [{"channel": "tickers", "instId": instId}],
                    }
                    ticker_ws_ref["ws"].send(json.dumps(msg))
                    logger.warning(f"📡 Unsubscribed ticker for {instId}")
                except Exception as e:
                    logger.error(f"Error unsubscribing ticker for {instId}: {e}")

            # Unsubscribe from candle
            if candle_ws_ref["ws"]:
                try:
                    msg = {
                        "op": "unsubscribe",
                        "args": [{"channel": "candle1H", "instId": instId}],
                    }
                    candle_ws_ref["ws"].send(json.dumps(msg))
                    logger.warning(f"📡 Unsubscribed candle for {instId}")
                except Exception as e:
                    logger.error(f"Error unsubscribing candle for {instId}: {e}")
    except Exception as e:
        logger.error(f"Error in unsubscribe_from_websocket for {instId}: {e}")


def check_blacklist_before_buy(instId, auto_remove=True):
    """Check if crypto is blacklisted. If blacklisted and auto_remove=True, remove from system."""
    if _check_blacklist_before_buy:
        return _check_blacklist_before_buy(
            instId,
            auto_remove,
            BlacklistManager,
            extract_base_currency,
            remove_crypto_from_system,
        )
    logger.error("check_blacklist_before_buy not available - module import failed")
    return False


def load_crypto_limits():
    """Load crypto limits from hour_limit table in database"""
    global crypto_limits
    if _load_crypto_limits:
        try:
            crypto_limits = _load_crypto_limits(get_db_connection)
            return len(crypto_limits) > 0
        except Exception as e:
            logger.error(f"Failed to load crypto limits from database: {e}")
            return False
    logger.error("load_crypto_limits not available - module import failed")
    return False


def calculate_limit_price(
    reference_price: float, base_limit_percent: float, instId: str
) -> float:
    """Calculate limit buy price"""
    if _calculate_limit_price:
        return _calculate_limit_price(reference_price, base_limit_percent, instId)
    return reference_price * (base_limit_percent / 100.0)


# Initialize price manager if available
price_manager: Optional[PriceManager] = None
if PriceManager is not None:
    try:
        price_manager = PriceManager(get_market_api(), lock)
        logger.info("✅ PriceManager initialized")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize PriceManager: {e}")
        price_manager = None

# Order sync manager will be initialized after process_sell_signal and process_momentum_sell_signal are defined
order_sync_manager: Optional[object] = None


def fetch_current_hour_open_price(instId: str) -> Optional[float]:
    """Fetch current hour's open price for a cryptocurrency"""
    if price_manager is None:
        logger.error(
            f"PriceManager not available, cannot fetch open price for {instId}"
        )
        return None
    return price_manager.fetch_current_hour_open_price(instId)


def initialize_reference_prices():
    """Initialize reference prices (current hour's open) for all cryptos"""
    if price_manager is None:
        logger.error("PriceManager not available, cannot initialize reference prices")
        return
    price_manager.initialize_reference_prices(crypto_limits)
    # Sync with global reference_prices dict
    with lock:
        reference_prices.update(price_manager.reference_prices)


def buy_limit_order(
    instId: str, limit_price: float, size: float, tradeAPI: TradeAPI, conn
) -> Optional[str]:
    """Place limit buy order and record in database"""
    if _buy_limit_order:
        return _buy_limit_order(
            instId,
            limit_price,
            size,
            tradeAPI,
            conn,
            STRATEGY_NAME,
            SIMULATION_MODE,
            format_number,
            check_blacklist_before_buy,
            play_sound,
        )
    logger.error("buy_limit_order not available - module import failed")
    return None


def sell_market_order(
    instId: str, ordId: str, size: float, tradeAPI: TradeAPI, conn
) -> bool:
    """Place market sell order"""
    if _sell_market_order:
        return _sell_market_order(
            instId,
            ordId,
            size,
            tradeAPI,
            conn,
            STRATEGY_NAME,
            SIMULATION_MODE,
            format_number,
            play_sound,
            get_market_api,
            current_prices,
            lock,
        )
    logger.error("sell_market_order not available - module import failed")
    return False


def on_ticker_message(ws, msg_string):
    """Handle ticker WebSocket messages"""
    if _on_ticker_message:
        _on_ticker_message(
            ws,
            msg_string,
            crypto_limits,
            current_prices,
            reference_prices,
            reference_price_fetch_time,
            reference_price_fetch_attempts,
            pending_buys,
            active_orders,
            lock,
            fetch_current_hour_open_price,
            calculate_limit_price,
            process_buy_signal,
        )
    else:
        logger.error("on_ticker_message not available - module import failed")


def check_and_cancel_unfilled_order_after_timeout(
    instId: str, ordId: str, tradeAPI: TradeAPI, strategy_name: str = STRATEGY_NAME
):
    """Check order status after 1 minute timeout, cancel if not filled"""
    if _check_and_cancel_unfilled_order_after_timeout:
        _check_and_cancel_unfilled_order_after_timeout(
            instId,
            ordId,
            tradeAPI,
            strategy_name,
            SIMULATION_MODE,
            get_db_connection,
            active_orders,
            momentum_active_orders,
            lock,
        )
    else:
        logger.error(
            "check_and_cancel_unfilled_order_after_timeout not available - module import failed"
        )


def buy_momentum_order(
    instId: str, buy_price: float, buy_pct: float, tradeAPI: TradeAPI, conn
) -> Optional[str]:
    """Place momentum strategy buy order and record in database"""
    if _buy_momentum_order:
        return _buy_momentum_order(
            instId,
            buy_price,
            buy_pct,
            tradeAPI,
            conn,
            MOMENTUM_STRATEGY_NAME,
            TRADING_AMOUNT_USDT,
            SIMULATION_MODE,
            format_number,
            check_blacklist_before_buy,
            play_sound,
        )
    logger.error("buy_momentum_order not available - module import failed")
    return None


def process_buy_signal(instId: str, limit_price: float):
    """Process buy signal in separate thread"""
    if _process_buy_signal:
        _process_buy_signal(
            instId,
            limit_price,
            STRATEGY_NAME,
            TRADING_AMOUNT_USDT,
            SIMULATION_MODE,
            get_trade_api,
            get_db_connection,
            buy_limit_order,
            check_blacklist_before_buy,
            active_orders,
            pending_buys,
            lock,
            check_and_cancel_unfilled_order_after_timeout,
        )
    else:
        logger.error("process_buy_signal not available - module import failed")


def process_momentum_buy_signal(instId: str, buy_price: float, buy_pct: float):
    """Process momentum strategy buy signal in separate thread"""
    if _process_momentum_buy_signal:
        _process_momentum_buy_signal(
            instId,
            buy_price,
            buy_pct,
            MOMENTUM_STRATEGY_NAME,
            TRADING_AMOUNT_USDT,
            SIMULATION_MODE,
            get_trade_api,
            get_db_connection,
            buy_momentum_order,
            check_blacklist_before_buy,
            momentum_active_orders,
            momentum_pending_buys,
            momentum_strategy,
            lock,
            check_and_cancel_unfilled_order_after_timeout,
        )
    else:
        logger.error("process_momentum_buy_signal not available - module import failed")


def on_candle_message(ws, msg_string):
    """Handle candle WebSocket messages"""
    if _on_candle_message:
        _on_candle_message(
            ws,
            msg_string,
            crypto_limits,
            reference_prices,
            reference_price_fetch_attempts,
            last_1h_candle_time,
            last_intra_hour_check,
            active_orders,
            momentum_active_orders,
            momentum_pending_buys,
            momentum_strategy,
            lock,
            process_sell_signal,
            process_momentum_buy_signal,
            process_momentum_sell_signal,
            INTRA_HOUR_CHECK_THROTTLE_SECONDS,
        )
    else:
        logger.error("on_candle_message not available - module import failed")


def process_sell_signal(instId: str):
    """Process sell signal at next hour close (idempotent)"""
    if _process_sell_signal:
        _process_sell_signal(
            instId,
            STRATEGY_NAME,
            SIMULATION_MODE,
            get_trade_api,
            get_db_connection,
            sell_market_order,
            active_orders,
            lock,
        )
    else:
        logger.error("process_sell_signal not available - module import failed")


def process_momentum_sell_signal(instId: str):
    """Process momentum strategy sell signal at next hour close (idempotent)"""
    if _process_momentum_sell_signal:
        _process_momentum_sell_signal(
            instId,
            MOMENTUM_STRATEGY_NAME,
            SIMULATION_MODE,
            get_trade_api,
            get_db_connection,
            sell_momentum_order,
            momentum_active_orders,
            momentum_strategy,
            lock,
        )
    else:
        logger.error(
            "process_momentum_sell_signal not available - module import failed"
        )


def sell_momentum_order(
    instId: str, ordId: str, size: float, tradeAPI: TradeAPI, conn
) -> bool:
    """Place momentum strategy market sell order"""
    if _sell_momentum_order:
        return _sell_momentum_order(
            instId,
            ordId,
            size,
            tradeAPI,
            conn,
            MOMENTUM_STRATEGY_NAME,
            SIMULATION_MODE,
            format_number,
            play_sound,
            get_market_api,
            current_prices,
            lock,
        )
    logger.error("sell_momentum_order not available - module import failed")
    return False


# Initialize order sync manager after process_sell_signal and process_momentum_sell_signal are defined
if OrderSyncManager is not None and order_sync_manager is None:
    try:
        order_sync_manager = OrderSyncManager(
            strategy_name=STRATEGY_NAME,
            momentum_strategy_name=MOMENTUM_STRATEGY_NAME,
            get_db_connection=get_db_connection,
            get_trade_api=get_trade_api,
            active_orders=active_orders,
            momentum_active_orders=momentum_active_orders,
            momentum_strategy=momentum_strategy,
            lock=lock,
            process_sell_signal=process_sell_signal,
            process_momentum_sell_signal=process_momentum_sell_signal,
        )
        logger.info("✅ OrderSyncManager initialized")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize OrderSyncManager: {e}")
        order_sync_manager = None


def ticker_open(ws):
    """Handle ticker WebSocket connection open"""
    if _ticker_open:
        _ticker_open(ws, crypto_limits)
    else:
        logger.error("ticker_open not available - module import failed")


def candle_open(ws):
    """Handle candle WebSocket connection open"""
    if _candle_open:
        _candle_open(ws, crypto_limits)
    else:
        logger.error("candle_open not available - module import failed")


def connect_websocket(url, on_message, on_open, ws_type="ticker"):
    """Connect to WebSocket with reconnection logic and exponential backoff"""
    if _connect_websocket:
        _connect_websocket(
            url, on_message, on_open, ws_type, ticker_ws_ref, candle_ws_ref, ws_lock
        )
    else:
        logger.error("connect_websocket not available - module import failed")


def sync_orders_from_database():
    """Sync active_orders with database state
    This handles cases where external processes or manual operations
    sold orders but websocket_limit_trading.py memory still thinks they're active
    """
    if order_sync_manager:
        order_sync_manager.sync_orders_from_database()
    else:
        logger.warning("OrderSyncManager not available, skipping sync")


def recover_orders_from_database(now: datetime):
    """Reverse validation: find filled orders in DB that should be sold

    This handles cases where:
    - Orders are filled but not in active_orders (process restart)
    - WS confirm message was missed
    - Memory state was lost

    Args:
        now: Current datetime for time comparison
    """
    if order_sync_manager:
        order_sync_manager.recover_orders_from_database(now)
    else:
        logger.warning("OrderSyncManager not available, skipping recovery")


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


def get_thread_count():
    """Get current thread count for monitoring"""
    return threading.active_count()


def monitor_thread_count():
    """Monitor thread count and log warning if too high"""
    thread_count = get_thread_count()
    max_threads = int(os.getenv("MAX_THREADS", "50"))

    if thread_count > max_threads:
        logger.warning(
            f"⚠️ THREAD COUNT: {thread_count} threads active (max: {max_threads}). "
            f"Thread breakdown: WS={2}, timeout={1}, deep_recover={1}, "
            f"buy/sell={thread_count - 4}"
        )
    else:
        logger.debug(f"Thread count: {thread_count}")


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP health check handler for long-lived services (Railway, etc.)

    Note: Not suitable for serverless platforms like Vercel.
    Automatically enabled on Railway (detected via RAILWAY_ENVIRONMENT).
    """

    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            try:
                # Check database connection (gracefully handle errors)
                try:
                    conn = get_db_connection()
                    conn.close()
                    db_status = "ok"
                except Exception as e:
                    db_status = f"error: {str(e)}"

                thread_count = get_thread_count()

                response = {
                    "status": "healthy",
                    "database": db_status,
                    "threads": thread_count,
                    "timestamp": datetime.now().isoformat(),
                }

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
            except Exception as e:
                # Even if health check fails, return 200 with error status
                # This prevents Railway from killing the service during startup
                response = {
                    "status": "starting",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress default HTTP server logging
        pass


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
            time.sleep(TIMEOUT_CHECK_INTERVAL_SECONDS)
            now = datetime.now()

            # ✅ FIX: Sync with database every cycle (1 minute)
            # This ensures memory state matches database state
            sync_counter += 1
            sync_orders_from_database()

            # ✅ NEW: Reverse validation from DB - find filled orders not yet sold
            recover_orders_from_database(now)

            # ✅ NEW: Monitor WebSocket health - alert if candles not received
            monitor_websocket_health(now)

            # ✅ NEW: Monitor thread count
            monitor_thread_count()

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
                # ✅ FIX: Check each order's sell time individually
                for instId, order_info in list(momentum_active_orders.items()):
                    ordIds = order_info.get("ordIds", [])
                    next_hour_close_times = order_info.get("next_hour_close_times", [])
                    # Check if any order is ready to sell
                    has_ready_orders = False
                    for idx, ordId in enumerate(ordIds):
                        if idx < len(next_hour_close_times):
                            order_sell_time = next_hour_close_times[idx]
                            if now >= order_sell_time:
                                has_ready_orders = True
                                break
                        else:
                            # Fallback: if no sell time, assume ready
                            has_ready_orders = True
                            break

                    if has_ready_orders and not order_info.get("sell_triggered", False):
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
            time.sleep(TIMEOUT_CHECK_INTERVAL_SECONDS)  # Wait on error


def main():
    """Main function"""
    logger.warning(f"Starting {STRATEGY_NAME} trading system")

    # Load crypto limits
    max_retries = 3
    retry_delay = 2
    for attempt in range(max_retries):
        if load_crypto_limits():
            break
        if attempt < max_retries - 1:
            logger.warning(
                f"Failed to load crypto limits (attempt {attempt + 1}/{max_retries}), "
                f"retrying in {retry_delay} seconds..."
            )
            time.sleep(retry_delay)
        else:
            logger.error("Failed to load crypto limits after all retries, exiting")
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

    # Start health check HTTP server
    # Default to enabled if RAILWAY_ENVIRONMENT is set (Railway deployment)
    # Or if ENABLE_HEALTH_CHECK_SERVER is explicitly set to true
    is_railway = os.getenv("RAILWAY_ENVIRONMENT") is not None
    enable_health_check = (
        is_railway or os.getenv("ENABLE_HEALTH_CHECK_SERVER", "false").lower() == "true"
    )
    if enable_health_check:
        # Railway provides PORT environment variable - use it if available
        # Otherwise fall back to HEALTH_CHECK_PORT or default 8080
        port = os.getenv("PORT") or os.getenv("HEALTH_CHECK_PORT", "8080")
        health_check_port = int(port)
        try:
            health_server = HTTPServer(
                ("0.0.0.0", health_check_port), HealthCheckHandler
            )
            health_thread = threading.Thread(
                target=health_server.serve_forever,
                daemon=True,
                name="HealthCheckServer",
            )
            health_thread.start()
            logger.warning(
                f"✅ Health check server started on port {health_check_port} "
                f"(PORT={os.getenv('PORT', 'not set')})"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to start health check server: {e}")
    else:
        logger.info(
            "Health check server disabled (set ENABLE_HEALTH_CHECK_SERVER=true to enable)"
        )

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

            # Monitor thread count in main loop
            monitor_thread_count()

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
