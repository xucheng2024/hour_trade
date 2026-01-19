#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Processing Functions
Handles buy and sell order placement and database recording
"""

import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from okx.Trade import TradeAPI

logger = logging.getLogger(__name__)


def buy_limit_order(
    instId: str,
    limit_price: float,
    size: float,
    tradeAPI: TradeAPI,
    conn,
    strategy_name: str,
    simulation_mode: bool,
    format_number_func,
    check_blacklist_func,
    play_sound_func,
) -> Optional[str]:
    """Place limit buy order and record in database"""
    # Check blacklist before buying
    if check_blacklist_func(instId):
        return None

    buy_price = format_number_func(limit_price, instId)
    size = format_number_func(size, instId)

    if simulation_mode:
        ordId = f"HLW-SIM-{uuid.uuid4().hex[:12]}"
        amount_usdt = float(buy_price) * float(size)
        logger.warning(
            f"🛒 [SIM] BUY: {instId}, price={buy_price}, size={size}, "
            f"amount={amount_usdt:.2f} USDT, ordId={ordId}"
        )
    else:
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
                            f"{strategy_name} buy limit: {instId}, no ordId in response"
                        )
                        failed_flag = 1
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{strategy_name} buy limit failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{strategy_name} buy limit error: {instId}, {e}")
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
        order_state = "filled" if simulation_mode else ""

        cur.execute(
            """INSERT INTO orders (instId, flag, ordId, create_time,
                       orderType, state, price, size, sell_time, side)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                instId,
                strategy_name,
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
        play_sound_func("buy")
        return ordId
    except Exception as e:
        logger.error(
            f"{strategy_name} buy limit DB error: {instId}, ordId may be undefined, {e}"
        )
        conn.rollback()
        return None
    finally:
        cur.close()


def sell_market_order(
    instId: str,
    ordId: str,
    size: float,
    tradeAPI: TradeAPI,
    conn,
    strategy_name: str,
    simulation_mode: bool,
    format_number_func,
    play_sound_func,
    get_market_api_func,
    current_prices: dict,
    lock,
) -> bool:
    """Place market sell order and record in database"""
    size = format_number_func(size, instId)

    if simulation_mode:
        with lock:
            sell_price = current_prices.get(instId, 0.0)

        if sell_price <= 0:
            try:
                market_api = get_market_api_func()
                ticker_result = market_api.get_ticker(instId=instId)
                if ticker_result.get("code") == "0" and ticker_result.get("data"):
                    ticker_data = ticker_result["data"]
                    if ticker_data and len(ticker_data) > 0:
                        sell_price = float(ticker_data[0].get("last", 0))
            except Exception as e:
                logger.warning(f"⚠️ Could not get current price for {instId}: {e}")

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"💰 [SIM] SELL: {instId}, price={sell_price:.6f}, "
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
                                    f"💰 SELL ORDER: {instId}, "
                                    f"fill price={sell_price:.6f}, "
                                    f"size={size}, ordId={order_id}"
                                )
                            else:
                                with lock:
                                    sell_price = current_prices.get(instId, 0.0)
                                logger.warning(
                                    f"💰 SELL ORDER: {instId}, "
                                    f"using current price={sell_price:.6f}, "
                                    f"ordId={order_id}"
                                )
                        else:
                            with lock:
                                sell_price = current_prices.get(instId, 0.0)
                            logger.warning(
                                f"💰 SELL ORDER: {instId}, "
                                f"using current price={sell_price:.6f}, "
                                f"ordId={order_id}"
                            )
                    except Exception as e:
                        with lock:
                            sell_price = current_prices.get(instId, 0.0)
                        logger.warning(
                            f"💰 SELL ORDER: {instId}, "
                            f"using current price={sell_price:.6f}, "
                            f"error: {e}, ordId={order_id}"
                        )

                    failed_flag = 0
                    break
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{strategy_name} sell market failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{strategy_name} sell market error: {instId}, {e}")
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(1)

        if failed_flag > 0:
            logger.error(
                f"❌ {strategy_name} SELL FAILED: {instId}, ordId={ordId}, all {max_attempts} attempts failed"
            )
            return False

    # Update database
    cur = conn.cursor()
    try:
        sell_price_str = (
            format_number_func(sell_price, instId) if sell_price > 0 else ""
        )
        # Update sell_time to actual sell time (current time)
        actual_sell_time = int(datetime.now().timestamp() * 1000)

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s, sell_time = %s "
            "WHERE instId = %s AND ordId = %s AND flag = %s",
            (
                "sold out",
                sell_price_str,
                actual_sell_time,
                instId,
                ordId,
                strategy_name,
            ),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {strategy_name} SELL DB UPDATE FAILED: {instId}, ordId={ordId}, no rows updated"
            )
            return False

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"✅ SELL SAVED: {instId}, price={sell_price_str}, "
            f"size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
        play_sound_func("sell")
        return True
    except Exception as e:
        logger.error(f"{strategy_name} sell market DB error: {instId}, {ordId}, {e}")
        conn.rollback()
        return False
    finally:
        cur.close()


def buy_momentum_order(
    instId: str,
    buy_price: float,
    buy_pct: float,
    tradeAPI: TradeAPI,
    conn,
    strategy_name: str,
    trading_amount_usdt: float,
    simulation_mode: bool,
    format_number_func,
    check_blacklist_func,
    play_sound_func,
) -> Optional[str]:
    """Place momentum strategy buy order and record in database"""
    if check_blacklist_func(instId):
        return None

    total_amount = trading_amount_usdt * buy_pct
    size = total_amount / buy_price if buy_price > 0 else 0

    buy_price_str = format_number_func(buy_price, instId)
    size_str = format_number_func(size, instId)

    if simulation_mode:
        ordId = f"MVE-SIM-{uuid.uuid4().hex[:12]}"
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
                        logger.error(f"{strategy_name} buy limit: {instId}, no ordId")
                        failed_flag = 1
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{strategy_name} buy limit failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{strategy_name} buy limit error: {instId}, {e}")
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
        order_state = "filled" if simulation_mode else ""

        cur.execute(
            """INSERT INTO orders (instId, flag, ordId, create_time,
                       orderType, state, price, size, sell_time, side)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                instId,
                strategy_name,
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
        play_sound_func("buy")
        return ordId
    except Exception as e:
        logger.error(
            f"{strategy_name} buy limit DB error: {instId}, ordId may be undefined, {e}"
        )
        conn.rollback()
        return None
    finally:
        cur.close()


def sell_momentum_order(
    instId: str,
    ordId: str,
    size: float,
    tradeAPI: TradeAPI,
    conn,
    strategy_name: str,
    simulation_mode: bool,
    format_number_func,
    play_sound_func,
    get_market_api_func,
    current_prices: dict,
    lock,
) -> bool:
    """Place momentum strategy market sell order"""
    size = format_number_func(size, instId)

    if simulation_mode:
        with lock:
            sell_price = current_prices.get(instId, 0.0)

        if sell_price <= 0:
            try:
                market_api = get_market_api_func()
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
                        f"{strategy_name} sell market failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{strategy_name} sell market error: {instId}, {e}")
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(1)

        if failed_flag > 0:
            logger.error(
                f"❌ {strategy_name} SELL FAILED: {instId}, ordId={ordId}, "
                f"all {max_attempts} attempts failed"
            )
            return False

    # Update database
    cur = conn.cursor()
    try:
        sell_price_str = (
            format_number_func(sell_price, instId) if sell_price > 0 else ""
        )
        # Update sell_time to actual sell time (current time)
        actual_sell_time = int(datetime.now().timestamp() * 1000)

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s, sell_time = %s "
            "WHERE instId = %s AND ordId = %s AND flag = %s",
            (
                "sold out",
                sell_price_str,
                actual_sell_time,
                instId,
                ordId,
                strategy_name,
            ),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {strategy_name} SELL DB UPDATE FAILED: {instId}, ordId={ordId}, no rows updated"
            )
            return False

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"✅ MOMENTUM SELL SAVED: {instId}, price={sell_price_str}, "
            f"size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
        play_sound_func("sell")
        return True
    except Exception as e:
        logger.error(f"{strategy_name} sell market DB error: {instId}, {ordId}, {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
