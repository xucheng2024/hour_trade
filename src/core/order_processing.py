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
from typing import Optional, Tuple

from okx.Trade import TradeAPI

logger = logging.getLogger(__name__)


def _get_sell_price_with_fallback(
    instId: str,
    order_id: str,
    tradeAPI: TradeAPI,
    get_market_api_func,
    current_prices: dict,
    lock,
    requested_size: Optional[float] = None,
) -> Tuple[float, str, list, bool]:
    """Get sell price with fallback chain: avgPx/fillPx -> current_prices -> ticker

    Args:
        requested_size: The original order size to verify full fill (optional)

    Returns:
        Tuple of (sell_price, price_source, failure_chain, is_confirmed_filled)
        - sell_price: The retrieved price (0.0 if all failed)
        - price_source: Source of the price (avgPx/fillPx/current_prices/ticker/unknown)
        - failure_chain: List of failure reasons for debugging
        - is_confirmed_filled: True if order is FULLY filled, False otherwise
    """
    sell_price = 0.0
    price_source = "unknown"
    failure_chain = []
    is_confirmed_filled = False

    try:
        # Step 1: Try get_order API (prefer avgPx, then fillPx)
        # ✅ CRITICAL: Only use price if order is FULLY filled
        order_result = tradeAPI.get_order(instId=instId, ordId=order_id)
        if order_result.get("code") == "0" and order_result.get("data"):
            order_info = order_result["data"][0]
            avg_px = order_info.get("avgPx", "")
            fill_px = order_info.get("fillPx", "")
            acc_fill_sz = order_info.get("accFillSz", "0")
            acc_fill_sz_float = float(acc_fill_sz) if acc_fill_sz else 0.0
            order_state = order_info.get("state", "")
            sz = order_info.get("sz", "0")
            sz_float = float(sz) if sz else 0.0

            # ✅ Check if order is FULLY filled (not just partially)
            if acc_fill_sz_float > 0:
                # Verify full fill: either state is 'filled' or accFillSz equals requested size
                is_fully_filled = False
                if order_state == "filled":
                    is_fully_filled = True
                elif (
                    requested_size
                    and abs(acc_fill_sz_float - requested_size) < 0.000001
                ):
                    # accFillSz matches requested size (with float tolerance)
                    is_fully_filled = True
                elif sz_float > 0 and abs(acc_fill_sz_float - sz_float) < 0.000001:
                    # accFillSz matches order size (with float tolerance)
                    is_fully_filled = True
                elif order_state == "partially_filled":
                    # Explicitly partially filled, not fully filled
                    is_fully_filled = False
                    failure_chain.append(
                        f"get_order: partially filled (accFillSz={acc_fill_sz_float}, "
                        f"requested={requested_size}, state={order_state})"
                    )
                else:
                    # Unknown state, be conservative and assume not fully filled
                    is_fully_filled = False
                    failure_chain.append(
                        f"get_order: uncertain fill status (accFillSz={acc_fill_sz_float}, "
                        f"state={order_state}, requested={requested_size})"
                    )

                if is_fully_filled:
                    # ✅ Order is FULLY filled, use actual fill price
                    is_confirmed_filled = True
                    if avg_px and avg_px != "":
                        sell_price = float(avg_px)
                        price_source = "avgPx"
                    elif fill_px and fill_px != "":
                        sell_price = float(fill_px)
                        price_source = "fillPx"
                    else:
                        failure_chain.append(
                            "get_order: fully filled but no avgPx/fillPx"
                        )
            else:
                # ✅ Order not filled yet, do NOT use fallback prices
                failure_chain.append("get_order: accFillSz=0 (order not filled)")
        else:
            failure_chain.append("get_order: API failed or no data")
    except Exception as e:
        failure_chain.append(f"get_order: exception={str(e)}")

    # ✅ CRITICAL: Only use fallback prices if order is FULLY filled
    # If get_order failed or not fully filled, do NOT use current_prices/ticker
    # This prevents marking order as "sold out" when it's not actually fully filled
    if not is_confirmed_filled:
        return 0.0, "unknown", failure_chain, False

    # Step 2: Fallback to current_prices (only if order is confirmed filled)
    if sell_price <= 0:
        with lock:
            sell_price = current_prices.get(instId, 0.0)
        if sell_price > 0:
            price_source = "current_prices"
        else:
            failure_chain.append("current_prices: not found or 0")

    # Step 3: Final fallback to get_ticker API (only if order is confirmed filled)
    if sell_price <= 0:
        try:
            market_api = get_market_api_func()
            ticker_result = market_api.get_ticker(instId=instId)
            if ticker_result.get("code") == "0" and ticker_result.get("data"):
                ticker_data = ticker_result["data"]
                if ticker_data and len(ticker_data) > 0:
                    last_price = ticker_data[0].get("last", 0)
                    if last_price and float(last_price) > 0:
                        sell_price = float(last_price)
                        price_source = "ticker"
                    else:
                        failure_chain.append("ticker: last=0 or invalid")
                else:
                    failure_chain.append("ticker: no data")
            else:
                failure_chain.append("ticker: API failed")
        except Exception as e2:
            failure_chain.append(f"ticker: exception={str(e2)}")

    return sell_price, price_source, failure_chain, is_confirmed_filled


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


def _execute_market_sell(
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
    log_prefix: str = "SELL",
) -> bool:
    """Common logic for executing market sell orders (used by all strategies)"""
    # ✅ FIX Issue 1: Keep size_float for arithmetic, only format string for order payload
    size_float = float(size)
    size_str = format_number_func(size_float, instId)

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

        sell_amount_usdt = float(sell_price) * size_float if sell_price > 0 else 0
        logger.warning(
            f"💰 [SIM] {log_prefix}: {instId}, price={sell_price:.6f}, "
            f"size={size_str}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
    else:
        max_attempts = 3
        failed_flag = 0
        sell_price = 0.0
        order_id = None  # ✅ Store order_id to avoid duplicate orders on retry

        # ✅ FIX: Check DB for existing sell_order_id linked to this specific buy ordId
        # This ensures we only reuse sell orders that belong to this exact buy order
        cur_check = conn.cursor()
        try:
            # ✅ FIX: Verify sell_order_id column exists (runtime check, fails fast if missing)
            # Schema migration should be done via init_database.py, not in hot path
            try:
                cur_check.execute(
                    """
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                      AND table_name = 'orders' 
                      AND column_name = 'sell_order_id'
                    """
                )
                column_exists = cur_check.fetchone() is not None
                if not column_exists:
                    logger.error(
                        f"❌ CRITICAL: sell_order_id column is missing from orders table! "
                        f"Please run 'python init_database.py' to add the column. "
                        f"Sell order linkage will not work for {instId}, ordId={ordId}"
                    )
                    # Continue without linkage rather than failing completely
            except Exception as e:
                logger.error(
                    f"❌ CRITICAL: Could not verify sell_order_id column existence: {e}. "
                    f"Sell order linkage may not work for {instId}, ordId={ordId}"
                )
                # Continue without linkage rather than failing completely

            # Check for existing sell_order_id for this specific buy order
            try:
                cur_check.execute(
                    "SELECT sell_order_id FROM orders WHERE instId = %s AND ordId = %s",
                    (instId, ordId),
                )
                row = cur_check.fetchone()
                if row and row[0]:
                    existing_sell_order_id = row[0]
                    # Verify the sell order still exists and check its state
                    try:
                        order_result = tradeAPI.get_order(
                            instId=instId, ordId=existing_sell_order_id
                        )
                        if order_result.get("code") == "0" and order_result.get("data"):
                            order_info = order_result["data"][0]
                            sell_order_state = order_info.get("state", "")
                            if sell_order_state in ["live", "partially_filled"]:
                                logger.warning(
                                    f"🔄 {log_prefix}: Found existing active sell order_id={existing_sell_order_id} "
                                    f"for buy ordId={ordId}, will poll instead of placing new order"
                                )
                                order_id = existing_sell_order_id
                            elif sell_order_state == "filled":
                                # ✅ FIX: If sell order is already filled, finalize the DB row instead of placing new order
                                logger.warning(
                                    f"✅ {log_prefix}: Found existing filled sell order_id={existing_sell_order_id} "
                                    f"for buy ordId={ordId}, finalizing DB record instead of placing new order"
                                )
                                # Get sell price from the filled order
                                (
                                    sell_price,
                                    price_source,
                                    failure_chain,
                                    is_confirmed_filled,
                                ) = _get_sell_price_with_fallback(
                                    instId,
                                    existing_sell_order_id,
                                    tradeAPI,
                                    get_market_api_func,
                                    current_prices,
                                    lock,
                                    requested_size=size_float,
                                )

                                if is_confirmed_filled and sell_price > 0:
                                    # Update database to mark as sold out
                                    sell_price_str = format_number_func(
                                        sell_price, instId
                                    )
                                    cur_check.execute(
                                        "UPDATE orders SET state = %s, sell_price = %s "
                                        "WHERE instId = %s AND ordId = %s",
                                        (
                                            "sold out",
                                            sell_price_str,
                                            instId,
                                            ordId,
                                        ),
                                    )
                                    conn.commit()

                                    sell_amount_usdt = (
                                        float(sell_price) * size_float
                                        if sell_price > 0
                                        else 0
                                    )
                                    logger.warning(
                                        f"✅ {log_prefix} FINALIZED: {instId}, price={sell_price_str} "
                                        f"(from {price_source}), size={size_str}, amount={sell_amount_usdt:.2f} USDT, "
                                        f"buy_ordId={ordId}, sell_ordId={existing_sell_order_id}"
                                    )
                                    play_sound_func("sell")
                                    return True
                                else:
                                    # ✅ FIX: If filled but price missing, keep linkage and retry later instead of placing new order
                                    logger.warning(
                                        f"⚠️ {log_prefix}: Existing filled sell order {existing_sell_order_id} "
                                        f"but could not get sell_price yet. Chain: {' -> '.join(failure_chain)}. "
                                        f"Keeping linkage and will retry price fetch later to avoid double-sell."
                                    )
                                    # Keep the linkage - do NOT clear it or place new order
                                    # Return False to allow retry on next call
                                    return False
                            else:
                                # ✅ CRITICAL FIX: Sell order is canceled or unknown state
                                # Check for partial fills before clearing linkage to prevent overselling
                                acc_fill_sz = order_info.get("accFillSz", "0")
                                acc_fill_sz_float = (
                                    float(acc_fill_sz) if acc_fill_sz else 0.0
                                )

                                if acc_fill_sz_float > 0:
                                    # ✅ PARTIAL FILL DETECTED: Update remaining size before clearing linkage
                                    logger.warning(
                                        f"⚠️ {log_prefix}: Existing sell order {existing_sell_order_id} "
                                        f"has state={sell_order_state} but partial fill detected: "
                                        f"accFillSz={acc_fill_sz_float}, original size={size_float}"
                                    )

                                    # Calculate remaining size to sell
                                    remaining_size = size_float - acc_fill_sz_float

                                    if remaining_size > 0:
                                        # Update database with remaining size
                                        remaining_size_str = format_number_func(
                                            remaining_size, instId
                                        )
                                        cur_check.execute(
                                            "UPDATE orders SET size = %s, sell_order_id = NULL "
                                            "WHERE instId = %s AND ordId = %s",
                                            (
                                                remaining_size_str,
                                                instId,
                                                ordId,
                                            ),
                                        )
                                        conn.commit()

                                        # Update size_float for the new sell order
                                        size_float = remaining_size
                                        size_str = format_number_func(
                                            size_float, instId
                                        )

                                        logger.warning(
                                            f"✅ {log_prefix}: Updated remaining size to {remaining_size_str} "
                                            f"after partial fill of {acc_fill_sz_float}. "
                                            f"Will place new sell order for remaining amount."
                                        )
                                    else:
                                        # Fully filled despite state being canceled/unknown
                                        # This shouldn't happen, but handle it gracefully
                                        logger.error(
                                            f"❌ {log_prefix}: Sell order {existing_sell_order_id} "
                                            f"state={sell_order_state} but accFillSz={acc_fill_sz_float} >= "
                                            f"original size={size_float}. This is unexpected. "
                                            f"Attempting to fetch sell_price before marking as sold out."
                                        )

                                        # ✅ FIX: Attempt to fetch sell_price before marking as sold out
                                        # This ensures PnL/reporting is accurate
                                        (
                                            sell_price,
                                            price_source,
                                            failure_chain,
                                            is_confirmed_filled,
                                        ) = _get_sell_price_with_fallback(
                                            instId,
                                            existing_sell_order_id,
                                            tradeAPI,
                                            get_market_api_func,
                                            current_prices,
                                            lock,
                                            requested_size=size_float,
                                        )

                                        # Prepare UPDATE statement with or without sell_price
                                        if sell_price > 0:
                                            sell_price_str = format_number_func(
                                                sell_price, instId
                                            )
                                            cur_check.execute(
                                                "UPDATE orders SET state = %s, sell_price = %s, sell_order_id = NULL "
                                                "WHERE instId = %s AND ordId = %s",
                                                (
                                                    "sold out",
                                                    sell_price_str,
                                                    instId,
                                                    ordId,
                                                ),
                                            )
                                            sell_amount_usdt = (
                                                float(sell_price) * size_float
                                            )
                                            logger.warning(
                                                f"✅ {log_prefix} FINALIZED: {instId}, price={sell_price_str} "
                                                f"(from {price_source}), size={size_str}, amount={sell_amount_usdt:.2f} USDT, "
                                                f"buy_ordId={ordId}, sell_ordId={existing_sell_order_id}"
                                            )
                                            play_sound_func("sell")
                                        else:
                                            # Could not get sell_price, but still mark as sold out to prevent overselling
                                            # Log warning for reporting/PnL issues
                                            logger.error(
                                                f"⚠️ {log_prefix}: Sell order {existing_sell_order_id} fully filled "
                                                f"but could not get sell_price. Chain: {' -> '.join(failure_chain)}. "
                                                f"Marking as sold out without price - this may affect PnL reporting."
                                            )
                                            cur_check.execute(
                                                "UPDATE orders SET state = %s, sell_order_id = NULL "
                                                "WHERE instId = %s AND ordId = %s",
                                                (
                                                    "sold out",
                                                    instId,
                                                    ordId,
                                                ),
                                            )

                                        conn.commit()
                                        return True
                                else:
                                    # No partial fill, safe to clear linkage
                                    logger.warning(
                                        f"⚠️ {log_prefix}: Existing sell order {existing_sell_order_id} "
                                        f"has state={sell_order_state} with no fills, clearing linkage"
                                    )
                                    cur_check.execute(
                                        "UPDATE orders SET sell_order_id = NULL WHERE instId = %s AND ordId = %s",
                                        (instId, ordId),
                                    )
                                    conn.commit()
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Could not verify existing sell order {existing_sell_order_id}: {e}. "
                            f"Will retry verification on next attempt instead of clearing linkage or placing new order."
                        )
                        # ✅ FIX: Short-circuit current call when get_order verification fails
                        # Keep linkage and return False to retry later without placing new sell
                        # This prevents duplicate sells on transient API failures
                        return False
            except Exception as e:
                # If column doesn't exist, this will fail - log and continue
                if "sell_order_id" in str(e).lower() or "column" in str(e).lower():
                    logger.error(
                        f"❌ CRITICAL: sell_order_id column access failed: {e}. "
                        f"Please run 'python init_database.py' to add the column."
                    )
                else:
                    logger.debug(
                        f"⚠️ Could not check for existing sell_order_id in DB: {e}"
                    )
        finally:
            cur_check.close()

        for attempt in range(max_attempts):
            try:
                # ✅ CRITICAL: Only place order on first attempt, then poll same order_id
                if order_id is None:
                    result = tradeAPI.place_order(
                        instId=instId,
                        tdMode="cash",
                        side="sell",
                        ordType="market",
                        sz=size_str,
                        tgtCcy="base_ccy",
                    )

                    if result.get("code") == "0":
                        order_data = result.get("data", [{}])[0]
                        order_id = order_data.get("ordId")

                        # ✅ FIX: Treat missing ordId as failure and allow retry
                        if not order_id or order_id == "N/A" or order_id == "":
                            logger.error(
                                f"❌ {strategy_name} sell market returned code=0 but missing ordId: {instId}, "
                                f"response={result}, treating as failure and will retry"
                            )
                            failed_flag = 1
                            if attempt < max_attempts - 1:
                                time.sleep(1)
                            continue

                        # ✅ FIX: Store sell_order_id in DB linked to this specific buy ordId
                        cur_save = conn.cursor()
                        try:
                            cur_save.execute(
                                "UPDATE orders SET sell_order_id = %s WHERE instId = %s AND ordId = %s",
                                (order_id, instId, ordId),
                            )
                            conn.commit()
                        except Exception as e:
                            # Log error loudly if column is missing
                            if (
                                "sell_order_id" in str(e).lower()
                                or "column" in str(e).lower()
                            ):
                                logger.error(
                                    f"❌ CRITICAL: Could not save sell_order_id to DB (column missing?): {e}. "
                                    f"Please run 'python init_database.py' to add the column."
                                )
                            else:
                                logger.warning(
                                    f"⚠️ Could not save sell_order_id to DB: {e}"
                                )
                        finally:
                            cur_save.close()

                        logger.warning(
                            f"📤 {log_prefix} ORDER PLACED: {instId}, sell_ordId={order_id}, "
                            f"buy_ordId={ordId}, size={size_str}, attempt={attempt + 1}/{max_attempts}"
                        )
                    else:
                        error_msg = result.get("msg", "Unknown error")
                        logger.error(
                            f"{strategy_name} sell market failed: {instId}, "
                            f"code={result.get('code')}, msg={error_msg}"
                        )
                        failed_flag = 1
                        if attempt < max_attempts - 1:
                            time.sleep(1)
                        continue

                # ✅ Poll the same order_id (don't place new order on retry)
                if order_id:
                    time.sleep(0.5 if attempt == 0 else 2)  # Shorter wait first time
                    sell_price, price_source, failure_chain, is_confirmed_filled = (
                        _get_sell_price_with_fallback(
                            instId,
                            order_id,
                            tradeAPI,
                            get_market_api_func,
                            current_prices,
                            lock,
                            requested_size=size_float,
                        )
                    )

                    if is_confirmed_filled and sell_price > 0:
                        logger.warning(
                            f"💰 {log_prefix} ORDER: {instId}, "
                            f"price={sell_price:.6f} (from {price_source}), "
                            f"ordId={order_id}, fully filled"
                        )
                        failed_flag = 0
                        break
                    elif not is_confirmed_filled:
                        logger.warning(
                            f"⏳ {log_prefix} ORDER: {instId}, ordId={order_id}, "
                            f"order not fully filled yet, will retry polling (attempt {attempt + 1}/{max_attempts})"
                        )
                        if attempt < max_attempts - 1:
                            failed_flag = 1
                        else:
                            logger.error(
                                f"❌ {log_prefix} ORDER: {instId}, ordId={order_id}, "
                                f"order not fully filled after {max_attempts} attempts, "
                                f"NOT updating to sold out (data consistency)"
                            )
                            return False
                    else:
                        logger.error(
                            f"❌ {log_prefix} ORDER: {instId}, ordId={order_id}, strategy={strategy_name}, "
                            f"FAILED to get sell_price. Chain: {' -> '.join(failure_chain)}"
                        )
                        failed_flag = 1

                if failed_flag > 0 and attempt < max_attempts - 1:
                    time.sleep(2)  # Wait before retry
            except Exception as e:
                logger.error(f"{strategy_name} sell market error: {instId}, {e}")
                failed_flag = 1
                if attempt < max_attempts - 1:
                    time.sleep(2)

        if failed_flag > 0:
            logger.error(
                f"❌ {strategy_name} {log_prefix} FAILED: {instId}, ordId={ordId}, "
                f"all {max_attempts} attempts failed"
            )
            return False

    # Update database
    # ✅ CRITICAL: Only update to sold out if we have confirmed filled price
    cur = conn.cursor()
    try:
        if sell_price <= 0:
            logger.error(
                f"❌ {strategy_name} {log_prefix}: {instId}, ordId={ordId}, "
                f"WARNING: sell_price is {sell_price} after all attempts! "
                f"NOT updating to sold out to maintain data consistency. "
                f"Check logs above for failure chain details."
            )
            return False

        sell_price_str = format_number_func(sell_price, instId)

        cur.execute(
            "UPDATE orders SET state = %s, sell_price = %s "
            "WHERE instId = %s AND ordId = %s",
            (
                "sold out",
                sell_price_str,
                instId,
                ordId,
            ),
        )
        rows_updated = cur.rowcount
        conn.commit()

        if rows_updated == 0:
            logger.error(
                f"❌ {strategy_name} {log_prefix} DB UPDATE FAILED: {instId}, "
                f"ordId={ordId}, no rows updated"
            )
            return False

        sell_amount_usdt = float(sell_price) * size_float if sell_price > 0 else 0
        logger.warning(
            f"✅ {log_prefix} SAVED: {instId}, price={sell_price_str}, "
            f"size={size_str}, amount={sell_amount_usdt:.2f} USDT, ordId={ordId}"
        )
        play_sound_func("sell")
        return True
    except Exception as e:
        logger.error(
            f"{strategy_name} sell market DB error: {instId}, ordId={ordId}, {e}"
        )
        conn.rollback()
        return False
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
    return _execute_market_sell(
        instId,
        ordId,
        size,
        tradeAPI,
        conn,
        strategy_name,
        simulation_mode,
        format_number_func,
        play_sound_func,
        get_market_api_func,
        current_prices,
        lock,
        log_prefix="SELL",
    )


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
    return _execute_market_sell(
        instId,
        ordId,
        size,
        tradeAPI,
        conn,
        strategy_name,
        simulation_mode,
        format_number_func,
        play_sound_func,
        get_market_api_func,
        current_prices,
        lock,
        log_prefix="STABLE SELL",
    )


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
    return _execute_market_sell(
        instId,
        ordId,
        size,
        tradeAPI,
        conn,
        strategy_name,
        simulation_mode,
        format_number_func,
        play_sound_func,
        get_market_api_func,
        current_prices,
        lock,
        log_prefix="BATCH SELL",
    )
