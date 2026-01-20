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
    current_prices: Optional[dict] = None,
    lock: Optional[object] = None,
) -> Optional[str]:
    """Place limit buy order and record in database"""
    # Check blacklist before buying
    if check_blacklist_func(instId):
        logger.warning(
            f"🚫 buy_limit_order: {instId} is blacklisted, blocking order placement"
        )
        return None

    # ✅ FIX: In simulation mode, use current price if it's less than limit price
    actual_price = limit_price
    if simulation_mode and current_prices is not None:
        if lock:
            with lock:
                current_price = current_prices.get(instId)
        else:
            current_price = current_prices.get(instId)
        if current_price and current_price > 0 and current_price < limit_price:
            actual_price = current_price
            logger.warning(
                f"💰 [SIM] BUY: {instId} using current price={actual_price:.6f} "
                f"instead of limit={limit_price:.6f} (current < limit)"
            )

    buy_price = format_number_func(actual_price, instId)
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
                        # ✅ FIX: Immediately check order status to get actual fill price
                        # If limit order price > market price, it fills immediately at market price
                        time.sleep(0.5)  # Wait a bit for order to be processed
                        try:
                            order_result = tradeAPI.get_order(
                                instId=instId, ordId=ordId
                            )
                            if order_result.get("code") == "0" and order_result.get(
                                "data"
                            ):
                                order_info = order_result["data"][0]
                                fill_px = order_info.get("fillPx", "")
                                acc_fill_sz = order_info.get("accFillSz", "0")

                                # If order is filled or partially filled, use actual fill price
                                if (
                                    fill_px
                                    and fill_px != ""
                                    and acc_fill_sz
                                    and float(acc_fill_sz) > 0
                                ):
                                    actual_fill_price = float(fill_px)
                                    actual_fill_size = float(acc_fill_sz)
                                    amount_usdt = actual_fill_price * actual_fill_size
                                    logger.warning(
                                        f"🛒 BUY ORDER FILLED: {instId}, "
                                        f"fill_price={actual_fill_price:.6f} (limit={buy_price}), "
                                        f"fill_size={actual_fill_size:.6f}, amount={amount_usdt:.2f} USDT, ordId={ordId}"
                                    )
                                    # Update buy_price to actual fill price for database
                                    buy_price = format_number_func(
                                        actual_fill_price, instId
                                    )
                                    size = format_number_func(actual_fill_size, instId)
                                else:
                                    amount_usdt = float(buy_price) * float(size)
                                    logger.warning(
                                        f"🛒 BUY ORDER: {instId}, price={buy_price}, "
                                        f"size={size}, amount={amount_usdt:.2f} USDT, "
                                        f"ordId={ordId} (pending)"
                                    )
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Could not get immediate order status for {instId}, ordId={ordId}: {e}, "
                                f"using limit price={buy_price}"
                            )
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
        # ✅ FIX: Always sell at next hour's 55 minutes (next hour after purchase)
        # Calculate next hour's 55 minutes
        sell_time_dt = now.replace(minute=55, second=0, microsecond=0)
        # Always add 1 hour to ensure we sell at next hour's close
        sell_time_dt = sell_time_dt + timedelta(hours=1)
        create_time = int(now.timestamp() * 1000)
        sell_time = int(sell_time_dt.timestamp() * 1000)
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
        # Keep original sell_time (planned sell time), don't update to actual sell time
        # This preserves the intended sell time for reporting/analysis

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s "
            "WHERE instId = %s AND ordId = %s AND flag = %s",
            (
                "sold out",
                sell_price_str,
                instId,
                ordId,
                strategy_name,
            ),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {strategy_name} SELL DB UPDATE FAILED: {instId}, "
                f"ordId={ordId}, no rows updated"
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


def buy_stable_order(
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
    current_prices: Optional[dict] = None,
    lock: Optional[object] = None,
) -> Optional[str]:
    """Place stable strategy buy order and record in database"""
    if check_blacklist_func(instId):
        return None

    # ✅ FIX: In simulation mode, use current price if it's less than limit price
    actual_price = limit_price
    if simulation_mode and current_prices is not None:
        if lock:
            with lock:
                current_price = current_prices.get(instId)
        else:
            current_price = current_prices.get(instId)
        if current_price and current_price > 0 and current_price < limit_price:
            actual_price = current_price
            logger.warning(
                f"💰 [SIM] STABLE BUY: {instId} using current price={actual_price:.6f} "
                f"instead of limit={limit_price:.6f} (current < limit)"
            )

    buy_price = format_number_func(actual_price, instId)
    size = format_number_func(size, instId)

    if simulation_mode:
        ordId = f"STB-SIM-{uuid.uuid4().hex[:12]}"
        amount_usdt = float(buy_price) * float(size)
        logger.warning(
            f"🛒 [SIM] STABLE BUY: {instId}, price={buy_price}, size={size}, "
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
                        # ✅ FIX: Immediately check order status to get actual fill price
                        # If limit order price > market price, it fills immediately at market price
                        time.sleep(0.5)  # Wait a bit for order to be processed
                        try:
                            order_result = tradeAPI.get_order(
                                instId=instId, ordId=ordId
                            )
                            if order_result.get("code") == "0" and order_result.get(
                                "data"
                            ):
                                order_info = order_result["data"][0]
                                fill_px = order_info.get("fillPx", "")
                                acc_fill_sz = order_info.get("accFillSz", "0")

                                # If order is filled or partially filled, use actual fill price
                                if (
                                    fill_px
                                    and fill_px != ""
                                    and acc_fill_sz
                                    and float(acc_fill_sz) > 0
                                ):
                                    actual_fill_price = float(fill_px)
                                    actual_fill_size = float(acc_fill_sz)
                                    amount_usdt = actual_fill_price * actual_fill_size
                                    logger.warning(
                                        f"🛒 STABLE BUY ORDER FILLED: {instId}, "
                                        f"fill_price={actual_fill_price:.6f} (limit={buy_price}), "
                                        f"fill_size={actual_fill_size:.6f}, amount={amount_usdt:.2f} USDT, ordId={ordId}"
                                    )
                                    # Update buy_price to actual fill price for database
                                    buy_price = format_number_func(
                                        actual_fill_price, instId
                                    )
                                    size = format_number_func(actual_fill_size, instId)
                                else:
                                    amount_usdt = float(buy_price) * float(size)
                                    logger.warning(
                                        f"🛒 STABLE BUY ORDER: {instId}, price={buy_price}, "
                                        f"size={size}, amount={amount_usdt:.2f} USDT, "
                                        f"ordId={ordId} (pending)"
                                    )
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Could not get immediate order status for {instId}, ordId={ordId}: {e}, "
                                f"using limit price={buy_price}"
                            )
                            amount_usdt = float(buy_price) * float(size)
                            logger.warning(
                                f"🛒 STABLE BUY ORDER: {instId}, price={buy_price}, "
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
        sell_time_dt = now.replace(minute=55, second=0, microsecond=0)
        sell_time_dt = sell_time_dt + timedelta(hours=1)
        create_time = int(now.timestamp() * 1000)
        sell_time = int(sell_time_dt.timestamp() * 1000)
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
            f"✅ STABLE BUY SAVED: {instId}, price={buy_price}, size={size}, "
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


def sell_stable_order(
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
    """Place stable strategy market sell order"""
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
            f"💰 [SIM] STABLE SELL: {instId}, price={sell_price:.6f}, "
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
                                    f"💰 STABLE SELL ORDER: {instId}, "
                                    f"fill price={sell_price:.6f}, "
                                    f"size={size}, ordId={order_id}"
                                )
                            else:
                                with lock:
                                    sell_price = current_prices.get(instId, 0.0)
                                logger.warning(
                                    f"💰 STABLE SELL ORDER: {instId}, "
                                    f"using current price={sell_price:.6f}, "
                                    f"ordId={order_id}"
                                )
                        else:
                            with lock:
                                sell_price = current_prices.get(instId, 0.0)
                            logger.warning(
                                f"💰 STABLE SELL ORDER: {instId}, "
                                f"using current price={sell_price:.6f}, "
                                f"ordId={order_id}"
                            )
                    except Exception as e:
                        with lock:
                            sell_price = current_prices.get(instId, 0.0)
                        logger.warning(
                            f"💰 STABLE SELL ORDER: {instId}, "
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

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s "
            "WHERE instId = %s AND ordId = %s AND flag = %s",
            (
                "sold out",
                sell_price_str,
                instId,
                ordId,
                strategy_name,
            ),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {strategy_name} SELL DB UPDATE FAILED: {instId}, "
                f"ordId={ordId}, no rows updated"
            )
            return False

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"✅ STABLE SELL SAVED: {instId}, price={sell_price_str}, "
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


def buy_batch_order(
    instId: str,
    limit_price: float,
    size: float,
    batch_index: int,
    tradeAPI: TradeAPI,
    conn,
    strategy_name: str,
    simulation_mode: bool,
    format_number_func,
    check_blacklist_func,
    play_sound_func,
    current_prices: Optional[dict] = None,
    lock: Optional[object] = None,
) -> Optional[str]:
    """Place batch strategy buy order and record in database"""
    if check_blacklist_func(instId):
        return None

    # ✅ FIX: In simulation mode, use current price if it's less than limit price
    actual_price = limit_price
    if simulation_mode and current_prices is not None:
        if lock:
            with lock:
                current_price = current_prices.get(instId)
        else:
            current_price = current_prices.get(instId)
        if current_price and current_price > 0 and current_price < limit_price:
            actual_price = current_price
            logger.warning(
                f"💰 [SIM] BATCH BUY: {instId} using current price={actual_price:.6f} "
                f"instead of limit={limit_price:.6f} (current < limit)"
            )

    buy_price = format_number_func(actual_price, instId)
    size = format_number_func(size, instId)

    if simulation_mode:
        ordId = f"BAT-SIM-{uuid.uuid4().hex[:12]}"
        amount_usdt = float(buy_price) * float(size)
        logger.warning(
            f"🛒 [SIM] BATCH BUY: {instId}, batch={batch_index + 1}, price={buy_price}, size={size}, "
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
                        # ✅ FIX: Immediately check order status to get actual fill price
                        # If limit order price > market price, it fills immediately at market price
                        time.sleep(0.5)  # Wait a bit for order to be processed
                        try:
                            order_result = tradeAPI.get_order(
                                instId=instId, ordId=ordId
                            )
                            if order_result.get("code") == "0" and order_result.get(
                                "data"
                            ):
                                order_info = order_result["data"][0]
                                fill_px = order_info.get("fillPx", "")
                                acc_fill_sz = order_info.get("accFillSz", "0")

                                # If order is filled or partially filled, use actual fill price
                                if (
                                    fill_px
                                    and fill_px != ""
                                    and acc_fill_sz
                                    and float(acc_fill_sz) > 0
                                ):
                                    actual_fill_price = float(fill_px)
                                    actual_fill_size = float(acc_fill_sz)
                                    amount_usdt = actual_fill_price * actual_fill_size
                                    logger.warning(
                                        f"🛒 BATCH BUY ORDER FILLED: {instId}, batch={batch_index + 1}, "
                                        f"fill_price={actual_fill_price:.6f} (limit={buy_price}), "
                                        f"fill_size={actual_fill_size:.6f}, amount={amount_usdt:.2f} USDT, ordId={ordId}"
                                    )
                                    # Update buy_price to actual fill price for database
                                    buy_price = format_number_func(
                                        actual_fill_price, instId
                                    )
                                    size = format_number_func(actual_fill_size, instId)
                                else:
                                    amount_usdt = float(buy_price) * float(size)
                                    logger.warning(
                                        f"🛒 BATCH BUY ORDER: {instId}, batch={batch_index + 1}, price={buy_price}, "
                                        f"size={size}, amount={amount_usdt:.2f} USDT, ordId={ordId} (pending)"
                                    )
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Could not get immediate order status for {instId}, ordId={ordId}: {e}, "
                                f"using limit price={buy_price}"
                            )
                            amount_usdt = float(buy_price) * float(size)
                            logger.warning(
                                f"🛒 BATCH BUY ORDER: {instId}, batch={batch_index + 1}, price={buy_price}, "
                                f"size={size}, amount={amount_usdt:.2f} USDT, ordId={ordId}"
                            )

                        failed_flag = 0
                        break
                    else:
                        logger.error(
                            f"{strategy_name} batch buy limit: {instId}, no ordId in response"
                        )
                        failed_flag = 1
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{strategy_name} batch buy limit failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{strategy_name} batch buy limit error: {instId}, {e}")
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(1)

        if failed_flag > 0:
            return None

    # Record in database
    cur = conn.cursor()
    try:
        now = datetime.now()
        sell_time_dt = now.replace(minute=55, second=0, microsecond=0)
        sell_time_dt = sell_time_dt + timedelta(hours=1)
        create_time = int(now.timestamp() * 1000)
        sell_time = int(sell_time_dt.timestamp() * 1000)
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
            f"✅ BATCH BUY SAVED: {instId}, batch={batch_index + 1}, price={buy_price}, size={size}, "
            f"amount={amount_usdt:.2f} USDT, ordId={ordId}"
        )
        play_sound_func("buy")
        return ordId
    except Exception as e:
        logger.error(
            f"{strategy_name} batch buy limit DB error: {instId}, ordId may be undefined, {e}"
        )
        conn.rollback()
        return None
    finally:
        cur.close()


def sell_batch_order(
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
    """Place batch strategy market sell order"""
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
            f"💰 [SIM] BATCH SELL: {instId}, price={sell_price:.6f}, "
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
                                    f"💰 BATCH SELL ORDER: {instId}, "
                                    f"fill price={sell_price:.6f}, "
                                    f"size={size}, ordId={order_id}"
                                )
                            else:
                                with lock:
                                    sell_price = current_prices.get(instId, 0.0)
                                logger.warning(
                                    f"💰 BATCH SELL ORDER: {instId}, "
                                    f"using current price={sell_price:.6f}, "
                                    f"ordId={order_id}"
                                )
                        else:
                            with lock:
                                sell_price = current_prices.get(instId, 0.0)
                            logger.warning(
                                f"💰 BATCH SELL ORDER: {instId}, "
                                f"using current price={sell_price:.6f}, "
                                f"ordId={order_id}"
                            )
                    except Exception as e:
                        with lock:
                            sell_price = current_prices.get(instId, 0.0)
                        logger.warning(
                            f"💰 BATCH SELL ORDER: {instId}, "
                            f"using current price={sell_price:.6f}, "
                            f"error: {e}, ordId={order_id}"
                        )

                    failed_flag = 0
                    break
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.error(
                        f"{strategy_name} batch sell market failed: {instId}, "
                        f"code={result.get('code')}, msg={error_msg}"
                    )
                    failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"{strategy_name} batch sell market error: {instId}, {e}")
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(1)

        if failed_flag > 0:
            logger.error(
                f"❌ {strategy_name} BATCH SELL FAILED: {instId}, ordId={ordId}, "
                f"all {max_attempts} attempts failed"
            )
            return False

    # Update database
    cur = conn.cursor()
    try:
        sell_price_str = (
            format_number_func(sell_price, instId) if sell_price > 0 else ""
        )

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s "
            "WHERE instId = %s AND ordId = %s AND flag = %s",
            (
                "sold out",
                sell_price_str,
                instId,
                ordId,
                strategy_name,
            ),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {strategy_name} BATCH SELL DB UPDATE FAILED: {instId}, "
                f"ordId={ordId}, no rows updated"
            )
            return False

        sell_amount_usdt = float(sell_price) * float(size) if sell_price > 0 else 0
        logger.warning(
            f"✅ BATCH SELL SAVED: {instId}, price={sell_price_str}, "
            f"size={size}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
        play_sound_func("sell")
        return True
    except Exception as e:
        logger.error(
            f"{strategy_name} batch sell market DB error: {instId}, {ordId}, {e}"
        )
        conn.rollback()
        return False
    finally:
        cur.close()
