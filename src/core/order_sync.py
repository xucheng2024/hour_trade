#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Synchronization and Recovery
Handles syncing orders between memory and database, and recovering lost orders

Recommended DB indexes for performance:
    CREATE INDEX idx_orders_flag_state_sell_price ON orders(flag, state, sell_price)
        WHERE sell_price IS NULL OR sell_price = '';
    CREATE INDEX idx_orders_instid_ordid_flag ON orders(instId, ordId, flag);
    CREATE INDEX idx_orders_flag_createtime ON orders(flag, create_time DESC);
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class OrderSyncManager:
    """Manages order synchronization and recovery from database"""

    def __init__(
        self,
        strategy_name: str,
        momentum_strategy_name: str,
        get_db_connection: Callable,
        get_trade_api: Callable,
        active_orders: Dict,
        momentum_active_orders: Dict,
        momentum_strategy: Optional[object],
        lock: threading.Lock,
        process_sell_signal: Callable,
        process_momentum_sell_signal: Callable,
    ):
        """Initialize OrderSyncManager

        Args:
            strategy_name: Strategy name for original orders
            momentum_strategy_name: Strategy name for momentum orders
            get_db_connection: Function to get database connection
            get_trade_api: Function to get TradeAPI instance
            active_orders: Dict of active orders (original strategy)
            momentum_active_orders: Dict of active orders (momentum strategy)
            momentum_strategy: Momentum strategy instance (optional)
            lock: Thread lock for thread-safe operations
            process_sell_signal: Function to process sell signal (original)
            process_momentum_sell_signal: Function to process sell signal (momentum)
        """
        import os

        self.strategy_name = strategy_name
        self.momentum_strategy_name = momentum_strategy_name
        self.get_db_connection = get_db_connection
        self.get_trade_api = get_trade_api
        self.active_orders = active_orders
        self.momentum_active_orders = momentum_active_orders
        self.momentum_strategy = momentum_strategy
        self.lock = lock
        self.process_sell_signal = process_sell_signal
        self.process_momentum_sell_signal = process_momentum_sell_signal
        self.last_deep_recovery_time: Optional[datetime] = None
        self.deep_recovery_running: bool = False
        self.deep_recovery_interval_seconds = int(
            os.getenv("DEEP_RECOVERY_INTERVAL_SECONDS", "86400")
        )  # Default 24 hours
        self.deep_recovery_execution_times: list = []  # Track execution times

    def sync_orders_from_database(self):
        """Sync active_orders with database state
        This handles cases where external processes or manual operations
        sold orders but websocket_limit_trading.py memory still thinks they're active
        """
        try:
            conn = self.get_db_connection()
            cur = conn.cursor()

            # Check original strategy orders
            with self.lock:
                orders_to_check = list(self.active_orders.items())

            # Build mapping of ordId -> instId for batch querying
            ordId_to_instId = {}
            all_ordIds = []
            for instId, order_info in orders_to_check:
                ordId = order_info.get("ordId")
                if not ordId:
                    continue
                ordId_to_instId[ordId] = instId
                all_ordIds.append(ordId)

            # Batch query all orders in a single query
            if all_ordIds:
                try:
                    cur.execute(
                        """
                        SELECT instId, ordId, state FROM orders
                        WHERE ordId = ANY(%s) AND flag = %s
                        """,
                        (all_ordIds, self.strategy_name),
                    )
                    rows = cur.fetchall()

                    # Build a map of (instId, ordId) -> state
                    db_states = {
                        (row[0], row[1]): row[2] if row[2] else "" for row in rows
                    }

                    # Find orders that are sold out
                    orders_to_remove = []
                    for ordId, instId in ordId_to_instId.items():
                        state = db_states.get((instId, ordId), "")
                        if state == "sold out":
                            orders_to_remove.append((instId, ordId))

                    # Remove sold orders from memory
                    if orders_to_remove:
                        with self.lock:
                            for instId, ordId in orders_to_remove:
                                if (
                                    instId in self.active_orders
                                    and self.active_orders[instId].get("ordId") == ordId
                                ):
                                    logger.warning(
                                        f"🔄 SYNC: {instId} (original) ordId={ordId} already sold in DB, "
                                        f"removing from active_orders"
                                    )
                                    del self.active_orders[instId]
                except Exception as e:
                    logger.debug(f"Error checking original orders: {e}")

            # Check momentum strategy orders
            with self.lock:
                momentum_orders_to_check = list(self.momentum_active_orders.items())

            for instId, order_info in momentum_orders_to_check:
                ordIds = order_info.get("ordIds", [])
                if not ordIds:
                    continue

                try:
                    cur.execute(
                        """
                        SELECT ordId, state FROM orders
                        WHERE instId = %s AND ordId = ANY(%s) AND flag = %s
                        """,
                        (instId, ordIds, self.momentum_strategy_name),
                    )
                    rows = cur.fetchall()

                    # Build a map of ordId -> state
                    db_states = {row[0]: row[1] if row[1] else "" for row in rows}

                    # Find orders that are sold out
                    ordIds_to_remove = [
                        ordId for ordId in ordIds if db_states.get(ordId) == "sold out"
                    ]

                    # Remove sold orders from memory
                    if ordIds_to_remove:
                        with self.lock:
                            if instId in self.momentum_active_orders:
                                for ordId in ordIds_to_remove:
                                    if ordId in self.momentum_active_orders[instId].get(
                                        "ordIds", []
                                    ):
                                        idx = self.momentum_active_orders[instId][
                                            "ordIds"
                                        ].index(ordId)
                                        self.momentum_active_orders[instId][
                                            "ordIds"
                                        ].pop(idx)
                                        if idx < len(
                                            self.momentum_active_orders[instId].get(
                                                "buy_prices", []
                                            )
                                        ):
                                            self.momentum_active_orders[instId][
                                                "buy_prices"
                                            ].pop(idx)
                                        if idx < len(
                                            self.momentum_active_orders[instId].get(
                                                "buy_sizes", []
                                            )
                                        ):
                                            self.momentum_active_orders[instId][
                                                "buy_sizes"
                                            ].pop(idx)
                                        if idx < len(
                                            self.momentum_active_orders[instId].get(
                                                "buy_times", []
                                            )
                                        ):
                                            self.momentum_active_orders[instId][
                                                "buy_times"
                                            ].pop(idx)
                                        if (
                                            "next_hour_close_times"
                                            in self.momentum_active_orders[instId]
                                        ):
                                            if idx < len(
                                                self.momentum_active_orders[instId][
                                                    "next_hour_close_times"
                                                ]
                                            ):
                                                self.momentum_active_orders[instId][
                                                    "next_hour_close_times"
                                                ].pop(idx)
                                        logger.warning(
                                            f"🔄 SYNC: {instId} (momentum) ordId={ordId} already sold in DB, "
                                            f"removing from momentum_active_orders"
                                        )

                                # If no more orders, remove the entry
                                if not self.momentum_active_orders[instId].get(
                                    "ordIds", []
                                ):
                                    del self.momentum_active_orders[instId]
                                    if self.momentum_strategy is not None:
                                        self.momentum_strategy.reset_position(instId)
                                    logger.warning(
                                        f"🔄 SYNC: {instId} (momentum) all orders sold, "
                                        f"removed from momentum_active_orders"
                                    )
                except Exception as e:
                    logger.debug(f"Error checking momentum orders {instId}: {e}")

            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Error in sync_orders_from_database: {e}")

    def recover_orders_from_database(self, now: datetime):
        """Reverse validation: find filled orders in DB that should be sold

        This handles cases where:
        - Orders are filled but not in active_orders (process restart)
        - WS confirm message was missed
        - Memory state was lost

        Also triggers deep recovery once per day to catch older stuck orders.

        Args:
            now: Current datetime for time comparison
        """
        # Check if deep recovery is needed (configurable interval)
        # Run in background thread to avoid blocking the timeout loop
        if not self.deep_recovery_running and (
            self.last_deep_recovery_time is None
            or (now - self.last_deep_recovery_time).total_seconds()
            >= self.deep_recovery_interval_seconds
        ):
            logger.info(
                f"🔄 Starting deep recovery scan in background thread (interval={self.deep_recovery_interval_seconds}s)..."
            )
            # Mark as running to prevent multiple concurrent deep recoveries
            self.deep_recovery_running = True
            self.last_deep_recovery_time = now

            def run_deep_recovery():
                start_time = time.time()
                try:
                    self.deep_recover_orders_from_database(now)
                    execution_time = time.time() - start_time
                    self.deep_recovery_execution_times.append(execution_time)
                    # Keep only last 10 execution times
                    if len(self.deep_recovery_execution_times) > 10:
                        self.deep_recovery_execution_times.pop(0)
                    avg_time = sum(self.deep_recovery_execution_times) / len(
                        self.deep_recovery_execution_times
                    )
                    logger.info(
                        f"✅ Deep recovery completed successfully in {execution_time:.2f}s "
                        f"(avg: {avg_time:.2f}s)"
                    )
                except Exception as e:
                    logger.error(
                        f"❌ Deep recovery failed, will retry on next cycle: {e}"
                    )
                    # Reset timestamp on failure so it retries sooner
                    self.last_deep_recovery_time = None
                finally:
                    # Always clear running flag when done
                    self.deep_recovery_running = False

            threading.Thread(target=run_deep_recovery, daemon=True).start()

        try:
            conn = self.get_db_connection()
            cur = conn.cursor()

            # Recover original strategy orders
            # Only check orders from last N hours to reduce DB load (configurable)
            recovery_hours = int(os.getenv("RECOVERY_HOURS", "24"))
            recovery_limit = int(os.getenv("RECOVERY_LIMIT", "100"))
            cutoff_time = int(
                (now - timedelta(hours=recovery_hours)).timestamp() * 1000
            )
            cur.execute(
                """
                SELECT instId, ordId, create_time, state, size
                FROM orders
                WHERE flag = %s
                  AND state IN ('filled', 'partially_filled')
                  AND (sell_price IS NULL OR sell_price = '')
                  AND create_time > %s
                ORDER BY create_time DESC
                LIMIT %s
                """,
                (self.strategy_name, cutoff_time, recovery_limit),
            )
            rows = cur.fetchall()

            # Rate limiting for OKX API calls (environment-configurable)
            api = self.get_trade_api()
            api_call_count = 0
            max_api_calls_per_cycle = int(os.getenv("RECOVERY_MAX_API_CALLS", "20"))
            api_call_delay = float(os.getenv("RECOVERY_API_CALL_DELAY", "0.1"))

            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                # Check if already in active_orders
                with self.lock:
                    if instId in self.active_orders:
                        continue

                # Get fillTime from OKX API
                fill_time = None
                next_hour = None

                if api is not None and api_call_count < max_api_calls_per_cycle:
                    try:
                        result = api.get_order(instId=instId, ordId=ordId)
                        api_call_count += 1
                        if api_call_count < max_api_calls_per_cycle:
                            time.sleep(api_call_delay)

                        if result and result.get("data") and len(result["data"]) > 0:
                            order_data = result["data"][0]
                            fill_time_ms = order_data.get("fillTime", "")
                            if fill_time_ms and fill_time_ms != "":
                                try:
                                    fill_time = datetime.fromtimestamp(
                                        int(fill_time_ms) / 1000
                                    )
                                    logger.info(
                                        f"✅ RECOVER: Using OKX fillTime for {instId}, ordId={ordId}: "
                                        f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                                except (ValueError, TypeError) as e:
                                    logger.warning(
                                        f"⚠️ RECOVER: Invalid fillTime from OKX: {fill_time_ms}, "
                                        f"falling back to create_time: {e}"
                                    )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ RECOVER: Failed to get order from OKX for {instId}, "
                            f"ordId={ordId}: {e}, falling back to create_time"
                        )
                elif api_call_count >= max_api_calls_per_cycle:
                    logger.debug(
                        f"⏸️ RECOVER: API rate limit reached ({max_api_calls_per_cycle} calls), "
                        f"using create_time for remaining orders"
                    )

                # Fallback to create_time if fillTime not available
                if fill_time is None:
                    fill_time = datetime.fromtimestamp(create_time_ms / 1000)
                    logger.info(
                        f"📝 RECOVER: Using create_time as fallback for {instId}, ordId={ordId} "
                        f"(API unavailable or rate limited)"
                    )

                # Calculate next_hour_close_time from fill_time
                next_hour = fill_time.replace(
                    minute=0, second=0, microsecond=0
                ) + timedelta(hours=1)

                # Only recover if past sell time
                if now >= next_hour:
                    logger.warning(
                        f"🔄 RECOVER: Found filled order not in memory: {instId}, "
                        f"ordId={ordId}, state={db_state}, fill_time={fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"recovering to active_orders"
                    )

                    # Restore to active_orders
                    with self.lock:
                        self.active_orders[instId] = {
                            "ordId": ordId,
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                            "fill_time": fill_time,
                            "last_sell_attempt_time": None,
                        }

                    # Trigger sell immediately
                    logger.warning(
                        f"⏰ RECOVER SELL: {instId} (original), "
                        f"triggering sell for recovered order"
                    )
                    import threading

                    threading.Thread(
                        target=self.process_sell_signal, args=(instId,), daemon=True
                    ).start()

            # Recover momentum strategy orders
            # Use same optimized cutoff (configurable hours, limit)
            cur.execute(
                """
                SELECT instId, ordId, create_time, state, size
                FROM orders
                WHERE flag = %s
                  AND state IN ('filled', 'partially_filled')
                  AND (sell_price IS NULL OR sell_price = '')
                  AND create_time > %s
                ORDER BY create_time DESC
                LIMIT %s
                """,
                (self.momentum_strategy_name, cutoff_time, recovery_limit),
            )
            rows = cur.fetchall()

            # Group by instId for momentum (can have multiple orders)
            momentum_orders_by_inst = {}
            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                if instId not in momentum_orders_by_inst:
                    momentum_orders_by_inst[instId] = []

                momentum_orders_by_inst[instId].append(
                    {
                        "ordId": ordId,
                        "create_time": datetime.fromtimestamp(create_time_ms / 1000),
                        "create_time_ms": create_time_ms,
                        "state": db_state,
                        "size": db_size,
                    }
                )

            # Process momentum orders
            for instId, orders in momentum_orders_by_inst.items():
                with self.lock:
                    existing_ordIds = set()
                    if instId in self.momentum_active_orders:
                        existing_ordIds = set(
                            self.momentum_active_orders[instId].get("ordIds", [])
                        )

                # Filter to only process missing ordIds
                missing_orders = [
                    o for o in orders if o["ordId"] not in existing_ordIds
                ]
                if not missing_orders:
                    continue

                # Get fillTime from OKX API for each order
                orders_with_fill_time = []
                api_call_count = 0
                max_api_calls_per_cycle = int(os.getenv("RECOVERY_MAX_API_CALLS", "20"))
                api_call_delay = float(os.getenv("RECOVERY_API_CALL_DELAY", "0.1"))

                for order in missing_orders:
                    ordId = order["ordId"]
                    fill_time = None

                    if api is not None and api_call_count < max_api_calls_per_cycle:
                        try:
                            result = api.get_order(instId=instId, ordId=ordId)
                            api_call_count += 1
                            if api_call_count < max_api_calls_per_cycle:
                                time.sleep(api_call_delay)

                            if (
                                result
                                and result.get("data")
                                and len(result["data"]) > 0
                            ):
                                order_data = result["data"][0]
                                fill_time_ms = order_data.get("fillTime", "")
                                if fill_time_ms and fill_time_ms != "":
                                    try:
                                        fill_time = datetime.fromtimestamp(
                                            int(fill_time_ms) / 1000
                                        )
                                        logger.debug(
                                            f"✅ RECOVER: Using OKX fillTime for momentum {instId}, "
                                            f"ordId={ordId}: {fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                        )
                                    except (ValueError, TypeError):
                                        pass
                        except Exception as e:
                            logger.debug(
                                f"⚠️ RECOVER: Failed to get order from OKX for momentum {instId}, "
                                f"ordId={ordId}: {e}, falling back to create_time"
                            )
                    elif api_call_count >= max_api_calls_per_cycle:
                        logger.debug(
                            f"⏸️ RECOVER: API rate limit reached for momentum {instId}, "
                            f"using create_time for remaining orders"
                        )

                    if fill_time is None:
                        fill_time = order["create_time"]
                        logger.info(
                            f"📝 RECOVER: Using create_time as fallback for momentum {instId}, "
                            f"ordId={ordId}: {fill_time.strftime('%Y-%m-%d %H:%M:%S')} "
                            f"(API unavailable or rate limited)"
                        )

                    next_hour = fill_time.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)

                    orders_with_fill_time.append(
                        {
                            "ordId": ordId,
                            "fill_time": fill_time,
                            "next_hour_close_time": next_hour,
                            "size": order["size"],
                        }
                    )

                # Group orders by next_hour_close_time
                orders_by_hour = {}
                for order_info in orders_with_fill_time:
                    next_hour_key = order_info["next_hour_close_time"]
                    if next_hour_key not in orders_by_hour:
                        orders_by_hour[next_hour_key] = []
                    orders_by_hour[next_hour_key].append(order_info)

                # Recover each group separately (only if past sell time)
                for next_hour, hour_orders in orders_by_hour.items():
                    if now >= next_hour:
                        logger.warning(
                            f"🔄 RECOVER: Found momentum orders not in memory: {instId}, "
                            f"count={len(hour_orders)}, next_hour={next_hour.strftime('%Y-%m-%d %H:%M:%S')}, "
                            f"recovering to momentum_active_orders"
                        )

                        with self.lock:
                            if instId in self.momentum_active_orders:
                                existing = self.momentum_active_orders[instId]
                                if "next_hour_close_times" not in existing:
                                    old_time = existing.get(
                                        "next_hour_close_time", next_hour
                                    )
                                    existing["next_hour_close_times"] = [
                                        old_time
                                    ] * len(existing.get("ordIds", []))

                                existing["ordIds"].extend(
                                    [o["ordId"] for o in hour_orders]
                                )
                                existing["buy_sizes"].extend(
                                    [float(o["size"]) for o in hour_orders]
                                )
                                existing["buy_times"].extend(
                                    [o["fill_time"] for o in hour_orders]
                                )
                                existing["next_hour_close_times"].extend(
                                    [o["next_hour_close_time"] for o in hour_orders]
                                )
                            else:
                                self.momentum_active_orders[instId] = {
                                    "ordIds": [o["ordId"] for o in hour_orders],
                                    "buy_prices": [],
                                    "buy_sizes": [
                                        float(o["size"]) for o in hour_orders
                                    ],
                                    "buy_times": [o["fill_time"] for o in hour_orders],
                                    "next_hour_close_times": [
                                        o["next_hour_close_time"] for o in hour_orders
                                    ],
                                    "sell_triggered": False,
                                    "last_sell_attempt_time": None,
                                }

                        # Trigger sell immediately
                        logger.warning(
                            f"⏰ RECOVER SELL: {instId} (momentum), "
                            f"triggering sell for recovered orders"
                        )
                        import threading

                        threading.Thread(
                            target=self.process_momentum_sell_signal,
                            args=(instId,),
                            daemon=True,
                        ).start()

            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Error in recover_orders_from_database: {e}")

    def deep_recover_orders_from_database(self, now: datetime):
        """Deep recovery: checks older orders (7 days) with higher limit (500)

        This handles stuck orders that the regular recovery (24h, limit 100) might miss.
        Should be called less frequently (e.g., once per day) to avoid DB load.

        Args:
            now: Current datetime for time comparison
        """
        try:
            conn = self.get_db_connection()
            cur = conn.cursor()

            # Deep recovery: configurable window and limit
            deep_recovery_days = int(os.getenv("DEEP_RECOVERY_DAYS", "7"))
            deep_recovery_limit = int(os.getenv("DEEP_RECOVERY_LIMIT", "500"))
            cutoff_time = int(
                (now - timedelta(days=deep_recovery_days)).timestamp() * 1000
            )

            logger.info(
                f"🔍 DEEP RECOVER: Scanning last {deep_recovery_days} days (limit {deep_recovery_limit}) for stuck orders"
            )

            # Recover original strategy orders
            cur.execute(
                """
                SELECT instId, ordId, create_time, state, size
                FROM orders
                WHERE flag = %s
                  AND state IN ('filled', 'partially_filled')
                  AND (sell_price IS NULL OR sell_price = '')
                  AND create_time > %s
                ORDER BY create_time DESC
                LIMIT %s
                """,
                (self.strategy_name, cutoff_time, deep_recovery_limit),
            )
            rows = cur.fetchall()

            if len(rows) >= deep_recovery_limit:
                logger.warning(
                    f"⚠️ DEEP RECOVER: Hit {deep_recovery_limit} limit for original strategy, "
                    f"there may be more stuck orders"
                )

            # Rate limiting for OKX API calls (environment-configurable)
            api = self.get_trade_api()
            api_call_count = 0
            max_api_calls_per_cycle = int(
                os.getenv("DEEP_RECOVERY_MAX_API_CALLS", "50")
            )  # Higher limit for deep recovery
            api_call_delay = float(os.getenv("DEEP_RECOVERY_API_CALL_DELAY", "0.1"))

            recovered_count = 0
            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                # Check if already in active_orders
                with self.lock:
                    if instId in self.active_orders:
                        continue

                # Get fillTime from OKX API
                fill_time = None
                next_hour = None

                if api is not None and api_call_count < max_api_calls_per_cycle:
                    try:
                        result = api.get_order(instId=instId, ordId=ordId)
                        api_call_count += 1
                        if api_call_count < max_api_calls_per_cycle:
                            time.sleep(api_call_delay)

                        if result and result.get("data") and len(result["data"]) > 0:
                            order_data = result["data"][0]
                            fill_time_ms = order_data.get("fillTime", "")
                            if fill_time_ms and fill_time_ms != "":
                                try:
                                    fill_time = datetime.fromtimestamp(
                                        int(fill_time_ms) / 1000
                                    )
                                except (ValueError, TypeError):
                                    pass
                    except Exception as e:
                        logger.debug(
                            f"⚠️ DEEP RECOVER: Failed to get order from OKX for {instId}, "
                            f"ordId={ordId}: {e}, falling back to create_time"
                        )

                # Fallback to create_time if fillTime not available
                if fill_time is None:
                    fill_time = datetime.fromtimestamp(create_time_ms / 1000)

                # Calculate next_hour_close_time from fill_time
                next_hour = fill_time.replace(
                    minute=0, second=0, microsecond=0
                ) + timedelta(hours=1)

                # Only recover if past sell time
                if now >= next_hour:
                    logger.warning(
                        f"🔄 DEEP RECOVER: Found stuck order: {instId}, "
                        f"ordId={ordId}, state={db_state}, fill_time={fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"recovering to active_orders"
                    )

                    # Restore to active_orders
                    with self.lock:
                        self.active_orders[instId] = {
                            "ordId": ordId,
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                            "fill_time": fill_time,
                            "last_sell_attempt_time": None,
                        }

                    # Trigger sell immediately
                    logger.warning(
                        f"⏰ DEEP RECOVER SELL: {instId} (original), "
                        f"triggering sell for recovered order"
                    )
                    import threading

                    threading.Thread(
                        target=self.process_sell_signal, args=(instId,), daemon=True
                    ).start()
                    recovered_count += 1

            # Recover momentum strategy orders
            cur.execute(
                """
                SELECT instId, ordId, create_time, state, size
                FROM orders
                WHERE flag = %s
                  AND state IN ('filled', 'partially_filled')
                  AND (sell_price IS NULL OR sell_price = '')
                  AND create_time > %s
                ORDER BY create_time DESC
                LIMIT %s
                """,
                (self.momentum_strategy_name, cutoff_time, deep_recovery_limit),
            )
            rows = cur.fetchall()

            if len(rows) >= deep_recovery_limit:
                logger.warning(
                    f"⚠️ DEEP RECOVER: Hit {deep_recovery_limit} limit for momentum strategy, "
                    f"there may be more stuck orders"
                )

            # Group by instId for momentum (can have multiple orders)
            momentum_orders_by_inst = {}
            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                if instId not in momentum_orders_by_inst:
                    momentum_orders_by_inst[instId] = []

                momentum_orders_by_inst[instId].append(
                    {
                        "ordId": ordId,
                        "create_time": datetime.fromtimestamp(create_time_ms / 1000),
                        "create_time_ms": create_time_ms,
                        "state": db_state,
                        "size": db_size,
                    }
                )

            # Process momentum orders
            api_call_count = 0
            for instId, orders in momentum_orders_by_inst.items():
                with self.lock:
                    existing_ordIds = set()
                    if instId in self.momentum_active_orders:
                        existing_ordIds = set(
                            self.momentum_active_orders[instId].get("ordIds", [])
                        )

                # Filter to only process missing ordIds
                missing_orders = [
                    o for o in orders if o["ordId"] not in existing_ordIds
                ]
                if not missing_orders:
                    continue

                # Get fillTime from OKX API for each order
                orders_with_fill_time = []

                for order in missing_orders:
                    ordId = order["ordId"]
                    fill_time = None

                    if api is not None and api_call_count < max_api_calls_per_cycle:
                        try:
                            result = api.get_order(instId=instId, ordId=ordId)
                            api_call_count += 1
                            if api_call_count < max_api_calls_per_cycle:
                                time.sleep(api_call_delay)

                            if (
                                result
                                and result.get("data")
                                and len(result["data"]) > 0
                            ):
                                order_data = result["data"][0]
                                fill_time_ms = order_data.get("fillTime", "")
                                if fill_time_ms and fill_time_ms != "":
                                    try:
                                        fill_time = datetime.fromtimestamp(
                                            int(fill_time_ms) / 1000
                                        )
                                    except (ValueError, TypeError):
                                        pass
                        except Exception as e:
                            logger.debug(
                                f"⚠️ DEEP RECOVER: Failed to get order from OKX for momentum {instId}, "
                                f"ordId={ordId}: {e}, falling back to create_time"
                            )

                    if fill_time is None:
                        fill_time = order["create_time"]

                    next_hour = fill_time.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)

                    orders_with_fill_time.append(
                        {
                            "ordId": ordId,
                            "fill_time": fill_time,
                            "next_hour_close_time": next_hour,
                            "size": order["size"],
                        }
                    )

                # Group orders by next_hour_close_time
                orders_by_hour = {}
                for order_info in orders_with_fill_time:
                    next_hour_key = order_info["next_hour_close_time"]
                    if next_hour_key not in orders_by_hour:
                        orders_by_hour[next_hour_key] = []
                    orders_by_hour[next_hour_key].append(order_info)

                # Recover each group separately (only if past sell time)
                for next_hour, hour_orders in orders_by_hour.items():
                    if now >= next_hour:
                        logger.warning(
                            f"🔄 DEEP RECOVER: Found stuck momentum orders: {instId}, "
                            f"count={len(hour_orders)}, next_hour={next_hour.strftime('%Y-%m-%d %H:%M:%S')}, "
                            f"recovering to momentum_active_orders"
                        )

                        with self.lock:
                            if instId in self.momentum_active_orders:
                                existing = self.momentum_active_orders[instId]
                                if "next_hour_close_times" not in existing:
                                    old_time = existing.get(
                                        "next_hour_close_time", next_hour
                                    )
                                    existing["next_hour_close_times"] = [
                                        old_time
                                    ] * len(existing.get("ordIds", []))

                                existing["ordIds"].extend(
                                    [o["ordId"] for o in hour_orders]
                                )
                                existing["buy_sizes"].extend(
                                    [float(o["size"]) for o in hour_orders]
                                )
                                existing["buy_times"].extend(
                                    [o["fill_time"] for o in hour_orders]
                                )
                                existing["next_hour_close_times"].extend(
                                    [o["next_hour_close_time"] for o in hour_orders]
                                )
                            else:
                                self.momentum_active_orders[instId] = {
                                    "ordIds": [o["ordId"] for o in hour_orders],
                                    "buy_prices": [],
                                    "buy_sizes": [
                                        float(o["size"]) for o in hour_orders
                                    ],
                                    "buy_times": [o["fill_time"] for o in hour_orders],
                                    "next_hour_close_times": [
                                        o["next_hour_close_time"] for o in hour_orders
                                    ],
                                    "sell_triggered": False,
                                    "last_sell_attempt_time": None,
                                }

                        # Trigger sell immediately
                        logger.warning(
                            f"⏰ DEEP RECOVER SELL: {instId} (momentum), "
                            f"triggering sell for recovered orders"
                        )
                        import threading

                        threading.Thread(
                            target=self.process_momentum_sell_signal,
                            args=(instId,),
                            daemon=True,
                        ).start()
                        recovered_count += len(hour_orders)

            cur.close()
            conn.close()

            if recovered_count > 0:
                logger.warning(
                    f"✅ DEEP RECOVER: Recovered {recovered_count} stuck order(s)"
                )
            else:
                logger.info("✅ DEEP RECOVER: No stuck orders found")

        except Exception as e:
            logger.error(f"Error in deep_recover_orders_from_database: {e}")
