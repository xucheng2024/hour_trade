#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Signal Processing Functions
Handles buy and sell signal processing for both original and momentum strategies
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

        size = trading_amount_usdt / limit_price

        conn = get_db_connection_func()
        try:
            ordId = buy_limit_order_func(instId, limit_price, size, api, conn)
            if ordId:
                with lock:
                    if instId in pending_buys:
                        del pending_buys[instId]
                    now = datetime.now()
                    # Sell at 55 minutes of current hour (e.g., 10:55)
                    sell_time = now.replace(minute=55, second=0, microsecond=0)
                    # If current time is past 55 minutes, sell at next hour's 55 minutes
                    if now.minute >= 55:
                        sell_time = sell_time + timedelta(hours=1)
                    active_orders[instId] = {
                        "ordId": ordId,
                        "buy_price": limit_price,
                        "buy_time": now,
                        "next_hour_close_time": sell_time,
                        "sell_triggered": False,
                    }
                    logger.warning(
                        f"📊 ACTIVE ORDER: {instId}, ordId={ordId}, "
                        f"buy_price={limit_price:.6f}, "
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

                try:
                    size = float(db_size)
                    if size <= 0:
                        logger.error(
                            f"{strategy_name} Invalid size for selling: {instId}, {ordId}, size={db_size}"
                        )
                        return
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


def process_momentum_buy_signal(
    instId: str,
    buy_price: float,
    buy_pct: float,
    strategy_name: str,
    trading_amount_usdt: float,
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    buy_momentum_order_func,
    check_blacklist_func,
    momentum_active_orders: dict,
    momentum_pending_buys: dict,
    momentum_strategy: Optional[object],
    lock: threading.Lock,
    check_and_cancel_unfilled_order_func,
):
    """Process momentum strategy buy signal in separate thread"""
    try:
        if check_blacklist_func(instId):
            logger.warning(
                f"🚫 Skipping momentum buy signal for {instId} - blacklisted"
            )
            with lock:
                if instId in momentum_pending_buys:
                    del momentum_pending_buys[instId]
            return

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for {instId}")
            return

        conn = get_db_connection_func()
        try:
            ordId = buy_momentum_order_func(instId, buy_price, buy_pct, api, conn)
            if ordId:
                with lock:
                    if instId in momentum_pending_buys:
                        del momentum_pending_buys[instId]

                    if momentum_strategy is not None:
                        total_amount = trading_amount_usdt * buy_pct
                        size = total_amount / buy_price if buy_price > 0 else 0
                        momentum_strategy.record_buy(instId, buy_price, size, ordId)

                    now = datetime.now()
                    # Sell at 55 minutes of current hour (e.g., 10:55)
                    sell_time = now.replace(minute=55, second=0, microsecond=0)
                    # If current time is past 55 minutes, sell at next hour's 55 minutes
                    if now.minute >= 55:
                        sell_time = sell_time + timedelta(hours=1)

                    # ✅ OPTIMIZED: Use dict keyed by ordId instead of parallel lists
                    if instId not in momentum_active_orders:
                        momentum_active_orders[instId] = {
                            "orders": {},  # ordId -> {buy_price, buy_size, buy_time, next_hour_close_time}
                            "sell_triggered": False,
                        }

                    total_amount = trading_amount_usdt * buy_pct
                    size = total_amount / buy_price if buy_price > 0 else 0
                    momentum_active_orders[instId]["orders"][ordId] = {
                        "buy_price": buy_price,
                        "buy_size": size,
                        "buy_time": now,
                        "next_hour_close_time": sell_time,
                    }

                    logger.warning(
                        f"📊 MOMENTUM ACTIVE ORDER: {instId}, ordId={ordId}, "
                        f"buy_price={buy_price:.6f}, pct={buy_pct:.1%}, "
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


def process_momentum_sell_signal(
    instId: str,
    strategy_name: str,
    simulation_mode: bool,
    get_trade_api_func,
    get_db_connection_func,
    sell_momentum_order_func,
    momentum_active_orders: dict,
    momentum_strategy: Optional[object],
    lock: threading.Lock,
):
    """Process momentum strategy sell signal at next hour close (idempotent)"""
    try:
        now = datetime.now()
        ordIds = []
        with lock:
            if instId in momentum_active_orders:
                order_info = momentum_active_orders[instId].copy()
                orders_dict = order_info.get("orders", {})
                # ✅ OPTIMIZED: Iterate through orders dict instead of parallel lists
                for ordId, order_data in orders_dict.items():
                    order_sell_time = order_data.get("next_hour_close_time")
                    if order_sell_time and now >= order_sell_time:
                        ordIds.append(ordId)
                    elif order_sell_time:
                        logger.debug(
                            f"⏸️ {strategy_name} Order {ordId} for {instId} "
                            f"not ready to sell yet (sell_time={order_sell_time.strftime('%Y-%m-%d %H:%M:%S')})"
                        )
                    else:
                        # No sell time, assume ready
                        ordIds.append(ordId)

        # Only query DB if instId doesn't exist in memory
        # If it exists in memory but no ordId is ready, don't query DB
        # (that would ignore per-order sell times and could sell early)
        if not ordIds:
            with lock:
                instId_in_memory = instId in momentum_active_orders
            if instId_in_memory:
                logger.debug(
                    f"{strategy_name} {instId} exists in memory but no orders ready yet, "
                    f"skipping DB query to avoid early sell"
                )
                return

            # Only query DB if instId is not in memory (recovery case)
            conn = get_db_connection_func()
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
                    (instId, strategy_name),
                )
                rows = cur.fetchall()
                if rows:
                    ordIds = [row[0] for row in rows]
                    logger.warning(
                        f"🔄 RECOVER: Found momentum orders in DB for {instId}, count={len(ordIds)}"
                    )
                else:
                    logger.debug(f"{strategy_name} No sellable orders found: {instId}")
                    return
                cur.close()
            finally:
                conn.close()

        if not ordIds:
            logger.warning(f"{strategy_name} No order IDs for {instId}")
            with lock:
                if instId in momentum_active_orders:
                    del momentum_active_orders[instId]
            return

        api = get_trade_api_func()
        if api is None and not simulation_mode:
            logger.error(f"{strategy_name} TradeAPI not available for sell: {instId}")
            return

        conn = get_db_connection_func()
        try:
            for ordId in ordIds:
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT state, size FROM orders WHERE instId = %s "
                        "AND ordId = %s AND flag = %s",
                        (instId, ordId, strategy_name),
                    )
                    row = cur.fetchone()

                    if not row:
                        logger.warning(
                            f"{strategy_name} Order not found: {instId}, {ordId}"
                        )
                        with lock:
                            if instId in momentum_active_orders:
                                # ✅ FIXED: Use orders dict instead of legacy lists
                                if ordId in momentum_active_orders[instId].get("orders", {}):
                                    del momentum_active_orders[instId]["orders"][ordId]
                        continue

                    db_state = row[0] if row[0] else ""
                    db_size = row[1] if row[1] else "0"

                    if db_state == "sold out":
                        logger.debug(f"{strategy_name} Already sold: {instId}, {ordId}")
                        continue

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
                                f"{strategy_name} Order still pending fill: {instId}, {ordId}, "
                                f"will retry later, continuing to next order"
                            )
                            # Note: Orders dict already tracks all orders, no need for separate pending_ordIds
                            # The order will be retried on next sell check if it becomes filled
                        continue

                    try:
                        size = float(db_size)
                        if size <= 0:
                            logger.error(
                                f"{strategy_name} Invalid size for selling: {instId}, {ordId}, size={db_size}"
                            )
                            continue
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"{strategy_name} Cannot convert size to float: {instId}, {ordId}, "
                            f"size={db_size}, error={e}"
                        )
                        continue
                finally:
                    cur.close()

                sell_success = sell_momentum_order_func(instId, ordId, size, api, conn)

                if not sell_success:
                    logger.error(
                        f"❌ {strategy_name} SELL FAILED: {instId}, {ordId}, "
                        f"skipping remaining orders for this crypto"
                    )
                    with lock:
                        if instId in momentum_active_orders:
                            momentum_active_orders[instId]["sell_triggered"] = False
                            logger.warning(
                                f"{strategy_name} Reset sell_triggered for {instId}, {ordId} to allow retry"
                            )
                    return

                with lock:
                    if instId in momentum_active_orders:
                        # ✅ OPTIMIZED: Simple dict deletion instead of complex index management
                        if ordId in momentum_active_orders[instId].get("orders", {}):
                            del momentum_active_orders[instId]["orders"][ordId]

            with lock:
                if instId in momentum_active_orders:
                    # ✅ OPTIMIZED: Check orders dict instead of ordIds list
                    if not momentum_active_orders[instId].get("orders", {}):
                        del momentum_active_orders[instId]
                        if momentum_strategy is not None:
                            momentum_strategy.reset_position(instId)
                        logger.warning(f"{strategy_name} Sold and removed: {instId}")
                    else:
                        momentum_active_orders[instId]["sell_triggered"] = False
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_momentum_sell_signal error: {instId}, {e}")
        with lock:
            if instId in momentum_active_orders:
                momentum_active_orders[instId]["sell_triggered"] = False
                logger.warning(
                    f"{strategy_name} Reset sell_triggered for {instId} after exception to allow retry"
                )
