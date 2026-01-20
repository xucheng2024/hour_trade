#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Signal Processing Functions
Handles buy and sell signal processing
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def process_buy_signal(
    instId: str,
    limit_price: float,
    strategy_name: str,
    trading_amount_usdt: float,
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    buy_limit_order_func,
    check_blacklist_func,
    active_orders: dict,
    pending_buys: dict,
    lock: threading.Lock,
    check_and_cancel_unfilled_order_func,
    current_prices: Optional[
        dict
    ] = None,  # Optional current prices dict to get actual market price
):
    """Process buy signal in separate thread"""
    try:
        if check_blacklist_func(instId):
            logger.warning(f"🚫 Skipping buy signal for {instId} - blacklisted")
            with lock:
                if instId in pending_buys:
                    del pending_buys[instId]
            return

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for {instId}")
            return

        # ✅ FIX: Use current market price (<= limit_price) instead of limit_price
        # If current price > limit_price, limit order won't fill, so use current price
        actual_buy_price = limit_price
        current_price = None
        if current_prices is not None:
            with lock:
                current_price = current_prices.get(instId)
            if current_price and current_price > 0:
                if simulation_mode and current_price > limit_price:
                    logger.warning(
                        f"🧪 [SIM] BUY SKIP: {instId} current={current_price:.6f} "
                        f"> limit={limit_price:.6f}"
                    )
                    with lock:
                        if instId in pending_buys:
                            del pending_buys[instId]
                    return
                # Use current price if it's <= limit_price, otherwise use limit_price
                actual_buy_price = min(current_price, limit_price)
                if actual_buy_price < limit_price:
                    logger.warning(
                        f"💰 BUY: {instId} using current price={actual_buy_price:.6f} "
                        f"instead of limit={limit_price:.6f} (current <= limit)"
                    )

        size = trading_amount_usdt / actual_buy_price

        conn = get_db_connection_func()
        try:
            ordId = buy_limit_order_func(instId, actual_buy_price, size, api, conn)
            if ordId:
                with lock:
                    if instId in pending_buys:
                        del pending_buys[instId]
                    now = datetime.now()
                    # ✅ FIX: Always sell at next hour's 55 minutes
                    # Calculate next hour's 55 minutes
                    sell_time = now.replace(minute=55, second=0, microsecond=0)
                    # Always add 1 hour to ensure we sell at next hour's close
                    sell_time = sell_time + timedelta(hours=1)
                    active_orders[instId] = {
                        "ordId": ordId,
                        "buy_price": actual_buy_price,  # ✅ FIX: Store actual buy price used
                        "buy_time": now,
                        "next_hour_close_time": sell_time,
                        "sell_triggered": False,
                    }
                    logger.warning(
                        f"📊 ACTIVE ORDER: {instId}, ordId={ordId}, "
                        f"buy_price={actual_buy_price:.6f}, "
                        f"sell_time={sell_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )

                    if not simulation_mode:
                        threading.Thread(
                            target=check_and_cancel_unfilled_order_func,
                            args=(instId, ordId, api, strategy_name),
                            daemon=True,
                        ).start()
            else:
                logger.error(
                    f"❌ Failed to create buy order for {instId}, cleaning up pending_buys"
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


def process_sell_signal(
    instId: str,
    strategy_name: str,
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    sell_market_order_func,
    active_orders: dict,
    lock: threading.Lock,
):
    """Process sell signal at next hour close (idempotent)"""
    try:
        ordId = None
        with lock:
            if instId in active_orders:
                order_info = active_orders[instId].copy()
                ordId = order_info.get("ordId")
            else:
                logger.debug(
                    f"{strategy_name} Order not in active_orders: {instId}, will try to recover from DB"
                )

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for sell: {instId}")
            return

        conn = get_db_connection_func()
        try:
            cur = conn.cursor()
            try:
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
                        (instId, strategy_name),
                    )
                    row = cur.fetchone()
                    if row:
                        ordId = row[0]
                        db_state = row[1] if row[1] else ""
                        db_size = row[2] if row[2] else "0"
                    else:
                        logger.debug(
                            f"{strategy_name} No sellable order found in DB: {instId}"
                        )
                        return
                else:
                    cur.execute(
                        "SELECT state, size FROM orders WHERE instId = %s "
                        "AND ordId = %s AND flag = %s",
                        (instId, ordId, strategy_name),
                    )
                    row = cur.fetchone()

                    if not row:
                        logger.error(
                            f"{strategy_name} Order not found: {instId}, {ordId}"
                        )
                        with lock:
                            if instId in active_orders:
                                del active_orders[instId]
                        return

                    db_state = row[0] if row[0] else ""
                    db_size = row[1] if row[1] else "0"

                if db_state == "sold out":
                    logger.warning(f"{strategy_name} Already sold: {instId}, {ordId}")
                    with lock:
                        if instId in active_orders:
                            del active_orders[instId]
                    return

                if (
                    db_state not in ["filled", "partially_filled"]
                    or not db_size
                    or db_size == "0"
                ):
                    logger.warning(
                        f"{strategy_name} Order not ready to sell: {instId}, {ordId}, "
                        f"state={db_state}, size={db_size}"
                    )
                    if db_state == "":
                        logger.info(
                            f"{strategy_name} Order still pending fill: {instId}, {ordId}, will retry later"
                        )
                        with lock:
                            if instId in active_orders:
                                active_orders[instId]["sell_triggered"] = False
                                active_orders[instId][
                                    "last_sell_attempt_time"
                                ] = datetime.now()
                    else:
                        with lock:
                            if instId in active_orders:
                                del active_orders[instId]
                    return

                # ✅ FIX Issue 2: For partially_filled orders, verify actual filled size via API
                # The DB size should already be updated by timeout handler, but double-check via API
                try:
                    size = float(db_size)
                    if size <= 0:
                        logger.error(
                            f"{strategy_name} Invalid size for selling: {instId}, {ordId}, size={db_size}"
                        )
                        return

                    # ✅ FIX Issue 2: If partially_filled, verify actual filled size matches DB
                    if db_state == "partially_filled" and not simulation_mode:
                        try:
                            order_result = api.get_order(instId=instId, ordId=ordId)
                            if order_result.get("code") == "0" and order_result.get(
                                "data"
                            ):
                                order_info = order_result["data"][0]
                                acc_fill_sz = order_info.get("accFillSz", "0")
                                actual_filled_size = (
                                    float(acc_fill_sz) if acc_fill_sz else 0.0
                                )

                                if (
                                    actual_filled_size > 0
                                    and abs(actual_filled_size - size) > 0.000001
                                ):
                                    logger.warning(
                                        f"⚠️ {strategy_name} Size mismatch for {instId}, ordId={ordId}: "
                                        f"DB size={size}, API accFillSz={actual_filled_size}, using API value"
                                    )
                                    size = actual_filled_size
                                    # Update DB with correct size
                                    cur_update = conn.cursor()
                                    try:
                                        cur_update.execute(
                                            "UPDATE orders SET size = %s WHERE instId = %s AND ordId = %s AND flag = %s",
                                            (
                                                str(actual_filled_size),
                                                instId,
                                                ordId,
                                                strategy_name,
                                            ),
                                        )
                                        conn.commit()
                                        cur_update.close()
                                    except Exception as e:
                                        logger.warning(
                                            f"⚠️ Could not update DB size: {e}"
                                        )
                                        cur_update.close()
                        except Exception as e:
                            logger.warning(
                                f"⚠️ {strategy_name} Could not verify filled size via API for {instId}, ordId={ordId}: {e}, "
                                f"using DB size={size}"
                            )
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"{strategy_name} Cannot convert size to float: {instId}, {ordId}, "
                        f"size={db_size}, error={e}"
                    )
                    return
            finally:
                cur.close()

            sell_success = sell_market_order_func(instId, ordId, size, api, conn)

            if sell_success:
                with lock:
                    if instId in active_orders:
                        del active_orders[instId]
                        logger.warning(
                            f"{strategy_name} Sold and removed: {instId}, {ordId}"
                        )
            else:
                logger.error(
                    f"❌ {strategy_name} SELL FAILED: {instId}, {ordId}, "
                    f"keeping in active_orders for retry"
                )
                with lock:
                    if instId in active_orders:
                        active_orders[instId]["sell_triggered"] = False
                        logger.warning(
                            f"{strategy_name} Reset sell_triggered for {instId}, {ordId} to allow retry"
                        )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_sell_signal error: {instId}, {e}")
        with lock:
            if instId in active_orders:
                active_orders[instId]["sell_triggered"] = False
                logger.warning(
                    f"{strategy_name} Reset sell_triggered for {instId} after exception to allow retry"
                )


def process_stable_buy_signal(
    instId: str,
    limit_price: float,
    strategy_name: str,
    trading_amount_usdt: float,
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    buy_stable_order_func,
    check_blacklist_func,
    stable_active_orders: dict,
    stable_pending_buys: dict,
    stable_strategy: Optional[object],
    lock: threading.Lock,
    check_and_cancel_unfilled_order_func,
    current_prices: Optional[
        dict
    ] = None,  # Optional current prices dict to get actual market price
):
    """Process stable strategy buy signal in separate thread"""
    try:
        if check_blacklist_func(instId):
            logger.warning(f"🚫 Skipping stable buy signal for {instId} - blacklisted")
            with lock:
                if instId in stable_pending_buys:
                    del stable_pending_buys[instId]
                if stable_strategy:
                    stable_strategy.clear_signal(instId)
            return

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for {instId}")
            return

        # ✅ FIX: Use current market price (<= limit_price) instead of limit_price
        # If current price > limit_price, limit order won't fill, so use current price
        actual_buy_price = limit_price
        current_price = None
        if current_prices is not None:
            with lock:
                current_price = current_prices.get(instId)
            if current_price and current_price > 0:
                if simulation_mode and current_price > limit_price:
                    logger.warning(
                        f"🧪 [SIM] STABLE BUY SKIP: {instId} current={current_price:.6f} "
                        f"> limit={limit_price:.6f}"
                    )
                    with lock:
                        if instId in stable_pending_buys:
                            del stable_pending_buys[instId]
                    if stable_strategy:
                        stable_strategy.clear_signal(instId)
                    return
                # Use current price if it's <= limit_price, otherwise use limit_price
                actual_buy_price = min(current_price, limit_price)
                if actual_buy_price < limit_price:
                    logger.warning(
                        f"💰 STABLE BUY: {instId} using current price={actual_buy_price:.6f} "
                        f"instead of limit={limit_price:.6f} (current <= limit)"
                    )

        size = trading_amount_usdt / actual_buy_price

        conn = get_db_connection_func()
        try:
            ordId = buy_stable_order_func(instId, actual_buy_price, size, api, conn)
            if ordId:
                with lock:
                    if instId in stable_pending_buys:
                        del stable_pending_buys[instId]
                    if stable_strategy:
                        stable_strategy.clear_signal(instId)
                    now = datetime.now()
                    sell_time = now.replace(minute=55, second=0, microsecond=0)
                    sell_time = sell_time + timedelta(hours=1)
                    stable_active_orders[instId] = {
                        "ordId": ordId,
                        "buy_price": actual_buy_price,  # ✅ FIX: Store actual buy price used
                        "buy_time": now,
                        "next_hour_close_time": sell_time,
                        "sell_triggered": False,
                    }
                    logger.warning(
                        f"📊 STABLE ACTIVE ORDER: {instId}, ordId={ordId}, "
                        f"buy_price={actual_buy_price:.6f}, "
                        f"sell_time={sell_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )

                    if not simulation_mode:
                        threading.Thread(
                            target=check_and_cancel_unfilled_order_func,
                            args=(instId, ordId, api, strategy_name),
                            daemon=True,
                        ).start()
            else:
                logger.error(
                    f"❌ Failed to create stable buy order for {instId}, cleaning up"
                )
                with lock:
                    if instId in stable_pending_buys:
                        del stable_pending_buys[instId]
                    if stable_strategy:
                        stable_strategy.clear_signal(instId)
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_stable_buy_signal error: {instId}, {e}")
        with lock:
            if instId in stable_pending_buys:
                del stable_pending_buys[instId]
            if stable_strategy:
                stable_strategy.clear_signal(instId)


def process_stable_sell_signal(
    instId: str,
    strategy_name: str,
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    sell_stable_order_func,
    stable_active_orders: dict,
    stable_strategy: Optional[object],
    lock: threading.Lock,
):
    """Process stable strategy sell signal at next hour close (idempotent)"""
    try:
        ordId = None
        with lock:
            if instId in stable_active_orders:
                order_info = stable_active_orders[instId].copy()
                ordId = order_info.get("ordId")
            else:
                logger.debug(
                    f"{strategy_name} Order not in stable_active_orders: {instId}, will try to recover from DB"
                )

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for sell: {instId}")
            return

        conn = get_db_connection_func()
        try:
            cur = conn.cursor()
            try:
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
                        (instId, strategy_name),
                    )
                    row = cur.fetchone()
                    if row:
                        ordId = row[0]
                        db_state = row[1] if row[1] else ""
                        db_size = row[2] if row[2] else "0"
                    else:
                        logger.debug(
                            f"{strategy_name} No sellable order found in DB: {instId}"
                        )
                        return
                else:
                    cur.execute(
                        "SELECT state, size FROM orders WHERE instId = %s "
                        "AND ordId = %s AND flag = %s",
                        (instId, ordId, strategy_name),
                    )
                    row = cur.fetchone()

                    if not row:
                        logger.error(
                            f"{strategy_name} Order not found: {instId}, {ordId}"
                        )
                        with lock:
                            if instId in stable_active_orders:
                                del stable_active_orders[instId]
                        return

                    db_state = row[0] if row[0] else ""
                    db_size = row[1] if row[1] else "0"

                if db_state == "sold out":
                    logger.warning(f"{strategy_name} Already sold: {instId}, {ordId}")
                    with lock:
                        if instId in stable_active_orders:
                            del stable_active_orders[instId]
                    return

                if (
                    db_state not in ["filled", "partially_filled"]
                    or not db_size
                    or db_size == "0"
                ):
                    logger.warning(
                        f"{strategy_name} Order not ready to sell: {instId}, {ordId}, "
                        f"state={db_state}, size={db_size}"
                    )
                    if db_state == "":
                        logger.info(
                            f"{strategy_name} Order still pending fill: {instId}, {ordId}, will retry later"
                        )
                        with lock:
                            if instId in stable_active_orders:
                                stable_active_orders[instId]["sell_triggered"] = False
                                stable_active_orders[instId][
                                    "last_sell_attempt_time"
                                ] = datetime.now()
                    else:
                        with lock:
                            if instId in stable_active_orders:
                                del stable_active_orders[instId]
                    return

                # ✅ FIX Issue 2: For partially_filled orders, verify actual filled size via API
                # The DB size should already be updated by timeout handler, but double-check via API
                try:
                    size = float(db_size)
                    if size <= 0:
                        logger.error(
                            f"{strategy_name} Invalid size for selling: {instId}, {ordId}, size={db_size}"
                        )
                        return

                    # ✅ FIX Issue 2: If partially_filled, verify actual filled size matches DB
                    if db_state == "partially_filled" and not simulation_mode:
                        try:
                            order_result = api.get_order(instId=instId, ordId=ordId)
                            if order_result.get("code") == "0" and order_result.get(
                                "data"
                            ):
                                order_info = order_result["data"][0]
                                acc_fill_sz = order_info.get("accFillSz", "0")
                                actual_filled_size = (
                                    float(acc_fill_sz) if acc_fill_sz else 0.0
                                )

                                if (
                                    actual_filled_size > 0
                                    and abs(actual_filled_size - size) > 0.000001
                                ):
                                    logger.warning(
                                        f"⚠️ {strategy_name} Size mismatch for {instId}, ordId={ordId}: "
                                        f"DB size={size}, API accFillSz={actual_filled_size}, using API value"
                                    )
                                    size = actual_filled_size
                                    # Update DB with correct size
                                    cur_update = conn.cursor()
                                    try:
                                        cur_update.execute(
                                            "UPDATE orders SET size = %s WHERE instId = %s AND ordId = %s AND flag = %s",
                                            (
                                                str(actual_filled_size),
                                                instId,
                                                ordId,
                                                strategy_name,
                                            ),
                                        )
                                        conn.commit()
                                        cur_update.close()
                                    except Exception as e:
                                        logger.warning(
                                            f"⚠️ Could not update DB size: {e}"
                                        )
                                        cur_update.close()
                        except Exception as e:
                            logger.warning(
                                f"⚠️ {strategy_name} Could not verify filled size via API for {instId}, ordId={ordId}: {e}, "
                                f"using DB size={size}"
                            )
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"{strategy_name} Cannot convert size to float: {instId}, {ordId}, "
                        f"size={db_size}, error={e}"
                    )
                    return
            finally:
                cur.close()

            sell_success = sell_stable_order_func(instId, ordId, size, api, conn)

            if sell_success:
                with lock:
                    if instId in stable_active_orders:
                        del stable_active_orders[instId]
                        logger.warning(
                            f"{strategy_name} Sold and removed: {instId}, {ordId}"
                        )
                    if stable_strategy:
                        stable_strategy.reset_crypto(instId)
            else:
                logger.error(
                    f"❌ {strategy_name} SELL FAILED: {instId}, {ordId}, "
                    f"keeping in stable_active_orders for retry"
                )
                with lock:
                    if instId in stable_active_orders:
                        stable_active_orders[instId]["sell_triggered"] = False
                        logger.warning(
                            f"{strategy_name} Reset sell_triggered for {instId}, {ordId} to allow retry"
                        )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_stable_sell_signal error: {instId}, {e}")
        with lock:
            if instId in stable_active_orders:
                stable_active_orders[instId]["sell_triggered"] = False
                logger.warning(
                    f"{strategy_name} Reset sell_triggered for {instId} after exception to allow retry"
                )


def process_batch_buy_signal(
    instId: str,
    limit_price: float,
    strategy_name: str,
    batch_strategy: Optional[object],
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    buy_batch_order_func,
    check_blacklist_func,
    batch_active_orders: dict,
    batch_pending_buys: dict,
    lock: threading.Lock,
    check_and_cancel_unfilled_order_func,
    thread_pool=None,  # Optional thread pool for scheduling next batch
    process_batch_buy_signal_func=None,  # Optional callback to trigger next batch
    current_prices: Optional[
        dict
    ] = None,  # Optional current prices dict to get actual market price
):
    """Process batch strategy buy signal - handles multiple batches with delays"""
    try:
        if check_blacklist_func(instId):
            logger.warning(f"🚫 Skipping batch buy signal for {instId} - blacklisted")
            with lock:
                if instId in batch_pending_buys:
                    del batch_pending_buys[instId]
                if batch_strategy:
                    batch_strategy.reset_crypto(instId)
            return

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for {instId}")
            return

        # Get next batch to buy
        if not batch_strategy:
            return

        batch_info = batch_strategy.get_next_batch(instId)
        if not batch_info:
            logger.debug(f"⏳ {instId} No batch ready to buy")
            return

        batch_index, amount_usdt, batch_limit_price = batch_info

        # ✅ FIX: Use current market price (<= limit_price) instead of limit_price
        # If current price > limit_price, limit order won't fill, so use current price
        actual_buy_price = batch_limit_price
        current_price = None
        if current_prices is not None:
            with lock:
                current_price = current_prices.get(instId)
            if current_price and current_price > 0:
                if simulation_mode and current_price > batch_limit_price:
                    logger.warning(
                        f"🧪 [SIM] BATCH BUY SKIP: {instId} current={current_price:.6f} "
                        f"> limit={batch_limit_price:.6f}"
                    )
                    with lock:
                        if instId in batch_pending_buys:
                            del batch_pending_buys[instId]
                    if batch_strategy:
                        batch_strategy.reset_crypto(instId)
                    return
                # Use current price if it's <= limit_price, otherwise use limit_price
                actual_buy_price = min(current_price, batch_limit_price)
                if actual_buy_price < batch_limit_price:
                    logger.warning(
                        f"💰 BATCH BUY: {instId} using current price={actual_buy_price:.6f} "
                        f"instead of limit={batch_limit_price:.6f} (current <= limit)"
                    )

        size = amount_usdt / actual_buy_price

        conn = get_db_connection_func()
        try:
            ordId = buy_batch_order_func(
                instId, actual_buy_price, size, batch_index, api, conn
            )
            if ordId:
                # Get actual filled size from database (formatted size that was used)
                actual_size = size
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT size FROM orders WHERE instId = %s AND ordId = %s AND flag = %s",
                        (instId, ordId, strategy_name),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        actual_size = float(row[0])
                    cur.close()
                except Exception as e:
                    logger.warning(
                        f"⚠️ Could not get actual size from DB for {instId}, ordId={ordId}: {e}, using computed size"
                    )

                # Mark batch as filled
                batch_strategy.mark_batch_filled(instId, batch_index)

                with lock:
                    now = datetime.now()
                    sell_time = now.replace(minute=55, second=0, microsecond=0)
                    sell_time = sell_time + timedelta(hours=1)

                    # Store batch order info
                    if instId not in batch_active_orders:
                        batch_active_orders[instId] = {
                            "ordIds": [],
                            "buy_price": actual_buy_price,  # ✅ FIX: Store actual buy price used
                            "buy_time": now,
                            "next_hour_close_time": sell_time,
                            "sell_triggered": False,
                            "total_size": 0.0,
                        }
                    else:
                        # Update buy_price if this batch used a different price
                        # Use average or latest price (for simplicity, use latest)
                        batch_active_orders[instId]["buy_price"] = actual_buy_price

                    batch_active_orders[instId]["ordIds"].append(ordId)
                    batch_active_orders[instId]["total_size"] += actual_size

                    logger.warning(
                        f"📊 BATCH ACTIVE ORDER (batch {batch_index + 1}/3): {instId}, "
                        f"ordId={ordId}, price={actual_buy_price:.6f}, amount={amount_usdt:.2f} USDT, "
                        f"total_batches={len(batch_active_orders[instId]['ordIds'])}/3"
                    )

                    # Clear batch_pending_buys if all batches are complete
                    if not batch_strategy.is_batch_active(instId):
                        if instId in batch_pending_buys:
                            del batch_pending_buys[instId]
                            logger.warning(
                                f"✅ All batches completed for {instId}, cleared batch_pending_buys"
                            )
                    else:
                        # ✅ FIX: Auto-schedule next batch using thread pool (bounded)
                        # Schedule next batch check after 30 seconds (batch delay)
                        # This avoids creating unbounded threads for sleep operations
                        def schedule_next_batch_check():
                            import time

                            time.sleep(30)  # Wait for batch delay
                            if batch_strategy and batch_strategy.is_batch_active(
                                instId
                            ):
                                next_batch_info = batch_strategy.get_next_batch(instId)
                                if next_batch_info:
                                    # ✅ CRITICAL FIX: Actually trigger next batch instead of just logging
                                    if process_batch_buy_signal_func:
                                        logger.warning(
                                            f"⏰ Auto-triggering next batch for {instId} after delay"
                                        )
                                        process_batch_buy_signal_func(
                                            instId, batch_limit_price
                                        )
                                    else:
                                        logger.error(
                                            f"❌ Cannot trigger next batch for {instId}: process_batch_buy_signal_func not provided"
                                        )

                        # Use thread pool to avoid unbounded thread creation
                        if thread_pool:
                            thread_pool.submit(schedule_next_batch_check)
                        else:
                            threading.Thread(
                                target=schedule_next_batch_check, daemon=True
                            ).start()

                    if not simulation_mode:
                        threading.Thread(
                            target=check_and_cancel_unfilled_order_func,
                            args=(instId, ordId, api, strategy_name),
                            daemon=True,
                        ).start()
            else:
                logger.error(
                    f"❌ Failed to create batch buy order for {instId}, batch {batch_index + 1}"
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_batch_buy_signal error: {instId}, {e}")


def process_batch_sell_signal(
    instId: str,
    strategy_name: str,
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    sell_market_order_func,
    batch_active_orders: dict,
    batch_pending_buys: dict,
    batch_strategy: Optional[object],
    lock: threading.Lock,
):
    """Process batch strategy sell signal - sells each batch order separately"""
    try:
        ordIds = []
        with lock:
            if instId in batch_active_orders:
                order_info = batch_active_orders[instId].copy()
                ordIds = order_info.get("ordIds", [])
            else:
                logger.debug(
                    f"{strategy_name} Order not in batch_active_orders: {instId}, will try to recover from DB"
                )

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for sell: {instId}")
            return

        conn = get_db_connection_func()
        try:
            # If no ordIds in memory, recover from DB
            if not ordIds:
                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        SELECT ordId FROM orders
                        WHERE instId = %s AND flag = %s
                          AND state IN ('filled', 'partially_filled')
                          AND (sell_price IS NULL OR sell_price = '')
                        ORDER BY create_time ASC
                        """,
                        (instId, strategy_name),
                    )
                    rows = cur.fetchall()
                    ordIds = [row[0] for row in rows]
                finally:
                    cur.close()

            if not ordIds:
                logger.debug(
                    f"{strategy_name} No sellable batch orders found: {instId}"
                )
                with lock:
                    if instId in batch_active_orders:
                        del batch_active_orders[instId]
                    if batch_strategy:
                        batch_strategy.reset_crypto(instId)
                    if instId in batch_pending_buys:
                        del batch_pending_buys[instId]
                return

            # ✅ FIX: Sell each batch order separately (like normal sell)
            successful_sells = 0
            failed_sells = 0

            for ordId in ordIds:
                cur = conn.cursor()
                try:
                    # Check order state and size
                    cur.execute(
                        "SELECT state, size FROM orders WHERE instId = %s "
                        "AND ordId = %s AND flag = %s",
                        (instId, ordId, strategy_name),
                    )
                    row = cur.fetchone()

                    if not row:
                        logger.warning(
                            f"{strategy_name} Batch order not found: {instId}, {ordId}"
                        )
                        failed_sells += 1
                        continue

                    db_state = row[0] if row[0] else ""
                    db_size = row[1] if row[1] else "0"

                    if db_state == "sold out":
                        logger.debug(
                            f"{strategy_name} Batch order already sold: {instId}, {ordId}"
                        )
                        successful_sells += 1
                        continue

                    if (
                        db_state not in ["filled", "partially_filled"]
                        or not db_size
                        or db_size == "0"
                    ):
                        logger.warning(
                            f"{strategy_name} Batch order not ready to sell: {instId}, {ordId}, "
                            f"state={db_state}, size={db_size}"
                        )
                        failed_sells += 1
                        continue

                    # ✅ FIX Issue 2: For partially_filled orders, verify actual filled size via API
                    # The DB size should already be updated by timeout handler, but double-check via API
                    try:
                        size = float(db_size)
                        if size <= 0:
                            logger.error(
                                f"{strategy_name} Invalid size for batch sell: {instId}, {ordId}, size={db_size}"
                            )
                            failed_sells += 1
                            continue

                        # ✅ FIX Issue 2: If partially_filled, verify actual filled size matches DB
                        if db_state == "partially_filled" and not simulation_mode:
                            try:
                                order_result = api.get_order(instId=instId, ordId=ordId)
                                if order_result.get("code") == "0" and order_result.get(
                                    "data"
                                ):
                                    order_info = order_result["data"][0]
                                    acc_fill_sz = order_info.get("accFillSz", "0")
                                    actual_filled_size = (
                                        float(acc_fill_sz) if acc_fill_sz else 0.0
                                    )

                                    if (
                                        actual_filled_size > 0
                                        and abs(actual_filled_size - size) > 0.000001
                                    ):
                                        logger.warning(
                                            f"⚠️ {strategy_name} Batch size mismatch for {instId}, ordId={ordId}: "
                                            f"DB size={size}, API accFillSz={actual_filled_size}, using API value"
                                        )
                                        size = actual_filled_size
                                        # Update DB with correct size
                                        cur_update = conn.cursor()
                                        try:
                                            cur_update.execute(
                                                "UPDATE orders SET size = %s WHERE instId = %s AND ordId = %s AND flag = %s",
                                                (
                                                    str(actual_filled_size),
                                                    instId,
                                                    ordId,
                                                    strategy_name,
                                                ),
                                            )
                                            conn.commit()
                                            cur_update.close()
                                        except Exception as e:
                                            logger.warning(
                                                f"⚠️ Could not update DB size: {e}"
                                            )
                                            cur_update.close()
                            except Exception as e:
                                logger.warning(
                                    f"⚠️ {strategy_name} Could not verify filled size via API for {instId}, ordId={ordId}: {e}, "
                                    f"using DB size={size}"
                                )
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"{strategy_name} Cannot convert size to float: {instId}, {ordId}, "
                            f"size={db_size}, error={e}"
                        )
                        failed_sells += 1
                        continue
                finally:
                    cur.close()

                # Sell this batch order separately
                sell_success = sell_market_order_func(instId, ordId, size, api, conn)

                if sell_success:
                    successful_sells += 1
                    logger.warning(
                        f"✅ {strategy_name} BATCH SELL: {instId}, ordId={ordId} sold successfully"
                    )
                else:
                    failed_sells += 1
                    logger.error(
                        f"❌ {strategy_name} BATCH SELL FAILED: {instId}, ordId={ordId}"
                    )

            # Clean up if all orders are sold
            if successful_sells > 0 and failed_sells == 0:
                with lock:
                    if instId in batch_active_orders:
                        del batch_active_orders[instId]
                    if batch_strategy:
                        batch_strategy.reset_crypto(instId)
                    if instId in batch_pending_buys:
                        del batch_pending_buys[instId]
                    logger.warning(
                        f"{strategy_name} All {successful_sells} batch orders sold: {instId}"
                    )
            else:
                # ✅ CRITICAL: Reset sell_triggered to allow retry on next check
                # This covers: partial failures, all failures, or no orders processed
                if failed_sells > 0:
                    logger.warning(
                        f"{strategy_name} BATCH SELL: {instId}, "
                        f"successful={successful_sells}, failed={failed_sells}, "
                        f"keeping in batch_active_orders for retry"
                    )
                elif successful_sells == 0 and failed_sells == 0:
                    logger.warning(
                        f"{strategy_name} BATCH SELL: {instId}, "
                        f"no orders processed, keeping in batch_active_orders for retry"
                    )
                else:
                    # successful_sells > 0 and failed_sells > 0 (partial success)
                    logger.warning(
                        f"{strategy_name} BATCH SELL: {instId}, "
                        f"partial success: {successful_sells} sold, {failed_sells} failed, "
                        f"keeping in batch_active_orders for retry"
                    )

                with lock:
                    if instId in batch_active_orders:
                        batch_active_orders[instId]["sell_triggered"] = False
                        logger.warning(
                            f"{strategy_name} Reset sell_triggered for {instId} "
                            f"to allow retry (successful={successful_sells}, failed={failed_sells})"
                        )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_batch_sell_signal error: {instId}, {e}")
        with lock:
            if instId in batch_active_orders:
                batch_active_orders[instId]["sell_triggered"] = False
