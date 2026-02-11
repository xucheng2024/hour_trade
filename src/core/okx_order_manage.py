# flake8: noqa
import base64
import hashlib
import hmac
import json
import math
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import psycopg
import requests
from dotenv import load_dotenv
from okx.Account import AccountAPI
from okx.MarketData import MarketAPI
from okx.Trade import TradeAPI

# Load environment variables
load_dotenv()

import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning)
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.WARNING)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

_sell_lock = threading.Lock()


def _noop_play_sound(_sound: str):
    return None


def _select_valid_fill_price(order_data: dict) -> tuple[str, float]:
    """Return best available fill price string (prefer avgPx over fillPx)."""
    avg_px = str(order_data.get("avgPx", "") or "").strip()
    fill_px = str(order_data.get("fillPx", "") or "").strip()

    for candidate in (avg_px, fill_px):
        if not candidate:
            continue
        try:
            candidate_float = float(candidate)
            if candidate_float > 0:
                return candidate, candidate_float
        except (ValueError, TypeError):
            continue

    return "", 0.0


# Only use file logging if logs directory exists or can be created
# In Railway/Vercel, prefer stdout logging
log_dir = Path("logs")
try:
    # Create directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)
    # Try to create the file handler
    log_file = log_dir / "order_management.log"
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except (OSError, PermissionError, FileNotFoundError):
    # If we can't create/write to logs directory, just use stdout
    # This is expected in Railway/Vercel environments
    # Silently fail - stdout logging will be used instead
    pass


def pre_sell(instId, marketDataAPI):

    candle_attempts = 3
    for candle_attempt in range(candle_attempts):
        try:
            result = marketDataAPI.get_candlesticks(instId=instId, bar="15m")
            break
        except Exception as e:
            logging.error("sp sell candle:%s", e)
            time.sleep(1)

    if not result:
        logging.error(
            "Failed to retrieve candlestick data after %d attempts", candle_attempts
        )
        return None

    try:
        cur_candle = result["data"][0]
        cur_low = float(cur_candle[3])
        cur_open = float(cur_candle[1])
        cur_close = float(cur_candle[4])

        last_candle = result["data"][1]
        last_low = float(last_candle[3])
        last_close = float(last_candle[4])
    except (IndexError, KeyError, ValueError) as e:
        logging.error("Error processing candlestick data: %s", e)
        return None

    if cur_close < last_low:
        return -1
    else:
        return 1


def order_update(instId, ordId, tradeAPI, conn, cur):

    attempts = 3
    for attempt in range(attempts):
        try:

            tradeAPI.cancel_order(instId=instId, ordId=ordId)

            result = tradeAPI.get_order(instId=instId, ordId=ordId)

            data = result["data"][0]
            size = data.get("accFillSz", "")
            price_to_save, _ = _select_valid_fill_price(data)
            order_state = data.get("state", "")
            order_size = data.get("sz", "0")

            try:
                filled_size = float(size) if size not in ("", None) else 0.0
            except (ValueError, TypeError):
                filled_size = 0.0

            try:
                total_size = float(order_size) if order_size not in ("", None) else 0.0
            except (ValueError, TypeError):
                total_size = 0.0

            if filled_size <= 0:
                new_state = "canceled"
            elif order_state == "filled" or (
                total_size > 0 and abs(filled_size - total_size) < 0.000001
            ):
                new_state = "filled"
            else:
                new_state = "partially_filled"

            if new_state in ("filled", "partially_filled"):
                # Derive sell_time from fillTime (next hour 55 min) for consistency
                fill_time_ms = data.get("fillTime", "")
                if fill_time_ms and fill_time_ms != "":
                    try:
                        fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                    except (ValueError, TypeError):
                        fill_time = datetime.now()
                else:
                    fill_time = datetime.now()

                next_hour = fill_time.replace(minute=55, second=0, microsecond=0)
                next_hour = next_hour + timedelta(hours=1)
                sell_time_ms = int(next_hour.timestamp() * 1000)

                if price_to_save:
                    sql_statement = """
                    UPDATE orders
                    SET state = %s, size = %s, price = %s, sell_time = %s
                    WHERE instId = %s AND ordId = %s;
                    """
                    cur.execute(
                        sql_statement,
                        (new_state, size, price_to_save, sell_time_ms, instId, ordId),
                    )
                else:
                    sql_statement = """
                    UPDATE orders
                    SET state = %s, size = %s, sell_time = %s
                    WHERE instId = %s AND ordId = %s;
                    """
                    cur.execute(
                        sql_statement,
                        (new_state, size, sell_time_ms, instId, ordId),
                    )
            else:
                sql_statement = """
                UPDATE orders
                SET state = %s
                WHERE instId = %s AND ordId = %s;
                """
                cur.execute(sql_statement, (new_state, instId, ordId))

            conn.commit()

        except Exception as e:
            logger.error("order_detail:%s,%s,%s", instId, ordId, e)


flag = "0"

# Master API credentials from environment
master_apikey = os.getenv("OKX_API_KEY", "")
master_secretkey = os.getenv("OKX_SECRET", "")
master_passphrase = os.getenv("OKX_PASSPHRASE", "")

if not all([master_apikey, master_secretkey, master_passphrase]):
    logger.error("OKX API credentials not found in environment variables")


initial_attempts = 3

tradeAPI_dict = {}

for initial_attempt in range(initial_attempts):
    try:
        marketDataAPI = MarketAPI(flag=flag)

        master_accountAPI = AccountAPI(
            master_apikey, master_secretkey, master_passphrase, False, flag
        )
        tradeAPI_dict["master"] = TradeAPI(
            master_apikey, master_secretkey, master_passphrase, False, flag
        )
        tradeAPI_dict["rkt_1m_dw"] = tradeAPI_dict["master"]
        tradeAPI_dict["rkt_1H_up"] = tradeAPI_dict["master"]
        tradeAPI_dict["rkt_1m_up"] = tradeAPI_dict["master"]
        tradeAPI_dict["dw_1D"] = tradeAPI_dict["master"]
        tradeAPI_dict["dw_1H"] = tradeAPI_dict["master"]
        tradeAPI_dict["dw_2H"] = tradeAPI_dict["master"]
        tradeAPI_dict["dw_15m"] = tradeAPI_dict["master"]

        break
    except Exception as e:
        logger.error("api initial:%s", e)
        time.sleep(1)


def main():

    is_checked = None
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment variables")

    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()

    while True:
        now = datetime.now()
        if is_checked is not None and is_checked == now.second // 10:
            continue

        is_checked = now.second // 10

        try:
            sql_update_query = """
            UPDATE orders
            SET state = 'canceled'
            WHERE (ordId = '' OR ordId IS NULL) AND state != 'canceled';
            """
            cur.execute(sql_update_query)
            conn.commit()

            state_value = ""
            create_time_value = int((now - timedelta(seconds=10)).timestamp() * 1000)
            sql_statement = (
                "SELECT * FROM orders WHERE state = %s and create_time < %s;"
            )
            cur.execute(sql_statement, (state_value, create_time_value))
        except Exception as e:
            logger.error("ord mng update:%s", e)

        rows = cur.fetchall()

        df = pd.DataFrame(
            rows,
            columns=[
                "instId",
                "flag",
                "ordId",
                "create_time",
                "orderType",
                "state",
                "price",
                "size",
                "sell_time",
                "side",
            ],
        )

        if len(df) != 0:
            logger.warning("ord mng update:%s", df.to_string())

            for index, each in df.iterrows():
                instId = each["instId"]
                ordId = each["ordId"]
                orderType = each["orderType"]
                flag = each["flag"]

                if orderType in ("mrk", "limit"):
                    order_update(instId, ordId, tradeAPI_dict[flag], conn, cur)

        now = datetime.now()
        state_value = "filled"
        sell_time_value = int((now).timestamp() * 1000)
        side = "buy"

        # Recover stuck selling orders (e.g., process crash after claiming)
        stuck_threshold_ms = int((now - timedelta(minutes=5)).timestamp() * 1000)
        cur.execute(
            """
            UPDATE orders
            SET state = 'filled'
            WHERE state = 'selling'
              AND (sell_price IS NULL OR sell_price = '')
              AND sell_time < %s
            """,
            (stuck_threshold_ms,),
        )
        conn.commit()

        sql_statement = (
            "SELECT * FROM orders WHERE state IN ('filled', 'partially_filled') "
            "AND (sell_price IS NULL OR sell_price = '') "
            "AND sell_time < %s and side = %s;"
        )
        cur.execute(sql_statement, (sell_time_value, side))

        rows = cur.fetchall()

        df = pd.DataFrame(
            rows,
            columns=[
                "instId",
                "flag",
                "ordId",
                "create_time",
                "orderType",
                "state",
                "price",
                "size",
                "sell_time",
                "side",
            ],
        )

        if len(df) > 0:
            if os.getenv("ORDER_MANAGE_SELL_ENABLED", "0") != "1":
                logger.warning(
                    "ORDER_MANAGE_SELL_ENABLED=0, skipping okx_order_manage sell path"
                )
                cur.close()
                conn.close()
                continue

            logger.warning("ord mng to sell:%s", df.to_string())
            result = master_accountAPI.get_account_balance()
            details = result["data"][0]["details"]

            currency_dict = {}

            for each in details:
                eqUsd = float(each["eqUsd"])
                if eqUsd < 1:
                    continue

                id = each["ccy"] + "-USDT"
                size = float(each["availBal"])
                currency_dict[id] = size

            for index, each in df.iterrows():
                instId = each["instId"]

                if instId not in currency_dict:
                    continue

                ordId = each["ordId"]
                size = float(each["size"])

                real_size = currency_dict[instId]
                if size > real_size or (real_size > size and real_size < 1.5 * size):
                    size = real_size

                flag = each["flag"]

                is_sell = pre_sell(instId, marketDataAPI)
                if is_sell > 0:
                    continue

                # Guard against duplicate sell attempts by claiming the order
                cur.execute(
                    """
                    UPDATE orders
                    SET state = 'selling'
                    WHERE instId = %s AND ordId = %s
                      AND state IN ('filled', 'partially_filled')
                      AND (sell_price IS NULL OR sell_price = '')
                    """,
                    (instId, ordId),
                )
                conn.commit()
                if cur.rowcount == 0:
                    continue

                # Use shared sell logic from order_processing
                from src.core.okx_functions import format_number, get_market_api
                from src.core.order_processing import sell_market_order

                sell_success = sell_market_order(
                    instId=instId,
                    ordId=ordId,
                    size=size,
                    tradeAPI=tradeAPI_dict[flag],
                    conn=conn,
                    strategy_name=flag,
                    simulation_mode=False,
                    format_number_func=format_number,
                    play_sound_func=_noop_play_sound,
                    get_market_api_func=get_market_api,
                    current_prices={},
                    lock=_sell_lock,
                )

                # If sell did not update sell_price, revert state for retry
                if not sell_success:
                    cur.execute(
                        """
                        UPDATE orders
                        SET state = 'filled'
                        WHERE instId = %s AND ordId = %s
                          AND state = 'selling'
                          AND (sell_price IS NULL OR sell_price = '')
                        """,
                        (instId, ordId),
                    )
                    conn.commit()

    cur.close()
    conn.close()


main()
