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
                    # ✅ FIX: Always sell at next hour's 55 minutes
                    # Calculate next hour's 55 minutes
                    sell_time = now.replace(minute=55, second=0, microsecond=0)
                    # Always add 1 hour to ensure we sell at next hour's close
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

        size = trading_amount_usdt / limit_price

        conn = get_db_connection_func()
        try:
            ordId = buy_stable_order_func(instId, limit_price, size, api, conn)
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
                        "buy_price": limit_price,
                        "buy_time": now,
                        "next_hour_close_time": sell_time,
                        "sell_triggered": False,
                    }
                    logger.warning(
                        f"📊 STABLE ACTIVE ORDER: {instId}, ordId={ordId}, "
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
        size = amount_usdt / batch_limit_price

        conn = get_db_connection_func()
        try:
            ordId = buy_batch_order_func(
                instId, batch_limit_price, size, batch_index, api, conn
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
                            "buy_price": batch_limit_price,
                            "buy_time": now,
                            "next_hour_close_time": sell_time,
                            "sell_triggered": False,
                            "total_size": 0.0,
                        }
                    
                    batch_active_orders[instId]["ordIds"].append(ordId)
                    batch_active_orders[instId]["total_size"] += actual_size
                    
                    logger.warning(
                        f"📊 BATCH ACTIVE ORDER (batch {batch_index + 1}/3): {instId}, "
                        f"ordId={ordId}, amount={amount_usdt:.2f} USDT, "
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
                        # Schedule next batch check after 10 seconds (batch delay)
                        # This avoids creating unbounded threads for sleep operations
                        def schedule_next_batch_check():
                            import time
                            time.sleep(10)  # Wait for batch delay
                            if batch_strategy and batch_strategy.is_batch_active(instId):
                                next_batch_info = batch_strategy.get_next_batch(instId)
                                if next_batch_info:
                                    # ✅ CRITICAL FIX: Actually trigger next batch instead of just logging
                                    if process_batch_buy_signal_func:
                                        logger.warning(
                                            f"⏰ Auto-triggering next batch for {instId} after delay"
                                        )
                                        process_batch_buy_signal_func(instId, batch_limit_price)
                                    else:
                                        logger.error(
                                            f"❌ Cannot trigger next batch for {instId}: process_batch_buy_signal_func not provided"
                                        )
                        
                        # Use thread pool to avoid unbounded thread creation
                        if thread_pool:
                            thread_pool.submit(schedule_next_batch_check)
                        else:
                            threading.Thread(target=schedule_next_batch_check, daemon=True).start()

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
    sell_batch_order_func,
    batch_active_orders: dict,
    batch_pending_buys: dict,
    batch_strategy: Optional[object],
    lock: threading.Lock,
):
    """Process batch strategy sell signal - sells all batches"""
    try:
        ordIds = []
        total_size = 0.0
        with lock:
            if instId in batch_active_orders:
                order_info = batch_active_orders[instId].copy()
                ordIds = order_info.get("ordIds", [])
                total_size = order_info.get("total_size", 0.0)
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
                        SELECT ordId, size FROM orders
                        WHERE instId = %s AND flag = %s
                          AND state IN ('filled', 'partially_filled')
                          AND (sell_price IS NULL OR sell_price = '')
                        ORDER BY create_time ASC
                        """,
                        (instId, strategy_name),
                    )
                    rows = cur.fetchall()
                    for row in rows:
                        ordIds.append(row[0])
                        total_size += float(row[1]) if row[1] else 0.0
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

            # ✅ FIX: Get actual filled sizes from DB to avoid oversell risk
            # Orders can be partially filled or canceled, so we need actual filled sizes
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT SUM(CAST(size AS FLOAT)) as total_filled_size
                    FROM orders
                    WHERE instId = %s AND flag = %s
                      AND ordId = ANY(%s)
                      AND state IN ('filled', 'partially_filled')
                      AND (sell_price IS NULL OR sell_price = '')
                    """,
                    (instId, strategy_name, ordIds),
                )
                row = cur.fetchone()
                if row and row[0]:
                    actual_total_size = float(row[0])
                    logger.warning(
                        f"📊 BATCH SELL: {instId}, using actual filled size={actual_total_size:.6f} "
                        f"(memory total={total_size:.6f})"
                    )
                    total_size = actual_total_size
                else:
                    logger.warning(
                        f"⚠️ BATCH SELL: {instId}, no filled orders found in DB, using memory total={total_size:.6f}"
                    )
            except Exception as e:
                logger.warning(
                    f"⚠️ BATCH SELL: {instId}, error getting actual sizes from DB: {e}, using memory total={total_size:.6f}"
                )
            finally:
                cur.close()

            if total_size <= 0:
                logger.error(
                    f"❌ {strategy_name} BATCH SELL: {instId}, invalid total_size={total_size}, skipping sell"
                )
                with lock:
                    if instId in batch_active_orders:
                        del batch_active_orders[instId]
                    if batch_strategy:
                        batch_strategy.reset_crypto(instId)
                    if instId in batch_pending_buys:
                        del batch_pending_buys[instId]
                return

            # Sell all batches using actual filled size from DB
            sell_success = sell_batch_order_func(instId, ordIds[0], total_size, api, conn)

            if sell_success:
                # Mark all batches as sold in DB
                cur = conn.cursor()
                try:
                    for ordId in ordIds:
                        cur.execute(
                            "UPDATE orders SET state = %s WHERE instId = %s AND ordId = %s AND flag = %s",
                            ("sold out", instId, ordId, strategy_name),
                        )
                    conn.commit()
                finally:
                    cur.close()

                with lock:
                    if instId in batch_active_orders:
                        del batch_active_orders[instId]
                    if batch_strategy:
                        batch_strategy.reset_crypto(instId)
                    if instId in batch_pending_buys:
                        del batch_pending_buys[instId]
                    logger.warning(
                        f"{strategy_name} All batches sold and removed: {instId}"
                    )
            else:
                logger.error(
                    f"❌ {strategy_name} BATCH SELL FAILED: {instId}, "
                    f"keeping in batch_active_orders for retry"
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"process_batch_sell_signal error: {instId}, {e}")
        with lock:
            if instId in batch_active_orders:
                batch_active_orders[instId]["sell_triggered"] = False


