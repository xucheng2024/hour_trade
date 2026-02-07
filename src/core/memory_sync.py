#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Synchronization Module
Syncs active_orders with database to prevent memory leaks
"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)


def sync_active_orders_with_db(
    get_db_connection_func,
    active_orders: Dict,
    pending_buys: Dict,
    stable_active_orders: Dict,
    stable_pending_buys: Dict,
    batch_active_orders: Dict,
    batch_pending_buys: Dict,
    gap_active_orders: Dict,
    gap_pending_buys: Dict,
    lock: threading.Lock,
    strategy_name: str = "hourly_limit_ws",
    stable_strategy_name: str = "stable_buy_ws",
    batch_strategy_name: str = "batch_buy_ws",
    gap_strategy_name: str = "original_gap",
):
    """Sync active_orders with database to fix inconsistencies

    This function:
    1. Clears memory entries for orders that are sold out in DB
    2. Adds memory entries for orders that are unsold in DB

    Should be called:
    - On startup
    - Periodically (e.g., every 5 minutes)
    """
    try:
        conn = get_db_connection_func()
        try:
            cur = conn.cursor()

            # Strategy configurations
            strategies = [
                (strategy_name, active_orders, pending_buys, "original"),
                (
                    stable_strategy_name,
                    stable_active_orders,
                    stable_pending_buys,
                    "stable",
                ),
                (batch_strategy_name, batch_active_orders, batch_pending_buys, "batch"),
                (gap_strategy_name, gap_active_orders, gap_pending_buys, "gap"),
            ]

            for strategy_flag, active_dict, pending_dict, label in strategies:
                # Get all unsold orders from DB for this strategy
                cur.execute(
                    """
                    SELECT DISTINCT instId, ordId, create_time, size, price
                    FROM orders
                    WHERE flag = %s
                      AND state IN ('filled', 'partially_filled')
                      AND (sell_price IS NULL OR sell_price = '')
                    ORDER BY instId, create_time DESC
                    """,
                    (strategy_flag,),
                )
                db_unsold = cur.fetchall()

                # Build set of instIds that should be in memory
                db_active_instIds = set()
                db_orders = {}
                for row in db_unsold:
                    instId = row[0]
                    db_active_instIds.add(instId)
                    if instId not in db_orders:
                        db_orders[instId] = {
                            "ordId": row[1],
                            "create_time": row[2],
                            "size": row[3],
                            "price": row[4],
                        }

                with lock:
                    # Get current memory state
                    memory_active_instIds = set(active_dict.keys())
                    memory_pending_instIds = set(pending_dict.keys())

                    # Find inconsistencies
                    # 1. In memory but not in DB (already sold) - REMOVE from memory
                    stale_in_memory = memory_active_instIds - db_active_instIds
                    for instId in stale_in_memory:
                        del active_dict[instId]
                        logger.warning(
                            f"🧹 [{label}] Cleaned stale memory: {instId} "
                            f"(sold in DB but still in active_orders)"
                        )

                    # 2. In DB but not in memory (missing) - ADD to memory
                    missing_in_memory = db_active_instIds - memory_active_instIds
                    for instId in missing_in_memory:
                        order_info = db_orders[instId]
                        create_dt = datetime.fromtimestamp(
                            order_info["create_time"] / 1000
                        )
                        # Calculate next hour close time
                        sell_time = create_dt.replace(
                            minute=55, second=0, microsecond=0
                        )
                        from datetime import timedelta

                        sell_time = sell_time + timedelta(hours=1)

                        active_dict[instId] = {
                            "ordId": order_info["ordId"],
                            "buy_price": (
                                float(order_info["price"]) if order_info["price"] else 0
                            ),
                            "buy_time": create_dt,
                            "next_hour_close_time": sell_time,
                            "sell_triggered": False,
                        }
                        logger.warning(
                            f"🔄 [{label}] Restored missing memory: "
                            f"{instId}, ordId={order_info['ordId']} "
                            f"(exists in DB but not in memory)"
                        )

                    # 3. Clean up stale pending_buys (shouldn't persist long)
                    stale_pending = (
                        memory_pending_instIds
                        - db_active_instIds
                        - memory_active_instIds
                    )
                    for instId in stale_pending:
                        del pending_dict[instId]
                        logger.warning(
                            f"🧹 [{label}] Cleaned stale pending_buys: {instId}"
                        )

                    if (
                        not stale_in_memory
                        and not missing_in_memory
                        and not stale_pending
                    ):
                        logger.info(
                            f"✅ [{label}] Memory in sync: "
                            f"{len(memory_active_instIds)} active, "
                            f"{len(memory_pending_instIds)} pending"
                        )

            cur.close()
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"❌ Memory sync failed: {e}")


def start_periodic_sync(
    get_db_connection_func,
    active_orders: Dict,
    pending_buys: Dict,
    stable_active_orders: Dict,
    stable_pending_buys: Dict,
    batch_active_orders: Dict,
    batch_pending_buys: Dict,
    gap_active_orders: Dict,
    gap_pending_buys: Dict,
    lock: threading.Lock,
    interval_seconds: int = 300,  # Default: 5 minutes
    strategy_name: str = "hourly_limit_ws",
    stable_strategy_name: str = "stable_buy_ws",
    batch_strategy_name: str = "batch_buy_ws",
    gap_strategy_name: str = "original_gap",
):
    """Start periodic memory sync in background thread

    Args:
        interval_seconds: How often to sync (default: 300 seconds = 5 minutes)
    """

    def sync_loop():
        while True:
            try:
                time.sleep(interval_seconds)
                logger.info("🔄 Running periodic memory sync...")
                sync_active_orders_with_db(
                    get_db_connection_func,
                    active_orders,
                    pending_buys,
                    stable_active_orders,
                    stable_pending_buys,
                    batch_active_orders,
                    batch_pending_buys,
                    gap_active_orders,
                    gap_pending_buys,
                    lock,
                    strategy_name,
                    stable_strategy_name,
                    batch_strategy_name,
                    gap_strategy_name,
                )
            except Exception as e:
                logger.error(f"❌ Periodic sync error: {e}")

    sync_thread = threading.Thread(
        target=sync_loop, daemon=True, name="MemorySyncThread"
    )
    sync_thread.start()
    logger.warning(f"✅ Periodic memory sync started (interval: {interval_seconds}s)")
