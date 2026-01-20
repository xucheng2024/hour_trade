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
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.WARNING)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

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
            size = data["accFillSz"]
            price = data["fillPx"]
            new_state = "completed" if size not in ("", "0") else "canceled"

            if new_state == "completed":
                sql_statement = """
                UPDATE orders
                SET state = %s, size = %s, price = %s
                WHERE instId = %s AND ordId = %s;
                """
                cur.execute(sql_statement, (new_state, size, price, instId, ordId))
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

                if orderType == "mrk" or "limit":
                    order_update(instId, ordId, tradeAPI_dict[flag], conn, cur)

        now = datetime.now()
        state_value = "completed"
        sell_time_value = int((now).timestamp() * 1000)
        side = "buy"

        sql_statement = (
            "SELECT * FROM orders WHERE state = %s and sell_time < %s and side = %s;"
        )
        cur.execute(sql_statement, (state_value, sell_time_value, side))

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

                # Lazy import to avoid circular import issues
                from src.core.okx_functions import sell_market

                sell_market(instId, ordId, size, tradeAPI_dict[flag], flag, conn)

    cur.close()
    conn.close()


main()
