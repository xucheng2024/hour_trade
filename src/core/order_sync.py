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
        stable_strategy_name: str,
        batch_strategy_name: str,
        get_db_connection: Callable,
        get_trade_api: Callable,
        active_orders: Dict,
        stable_active_orders: Dict,
        batch_active_orders: Dict,
        stable_strategy: Optional[object],
        batch_strategy: Optional[object],
        lock: threading.Lock,
        process_sell_signal: Callable,
        process_stable_sell_signal: Callable,
        process_batch_sell_signal: Callable,
        simulation_mode: bool = False,
    ):
        """Initialize OrderSyncManager

        Args:
            strategy_name: Strategy name for original orders
            stable_strategy_name: Strategy name for stable orders
            batch_strategy_name: Strategy name for batch orders
            get_db_connection: Function to get database connection
            get_trade_api: Function to get TradeAPI instance
            active_orders: Dict of active orders (original strategy)
            stable_active_orders: Dict of active orders (stable strategy)
            batch_active_orders: Dict of active orders (batch strategy)
            stable_strategy: Stable strategy instance (optional)
            batch_strategy: Batch strategy instance (optional)
            lock: Thread lock for thread-safe operations
            process_sell_signal: Function to process sell signal (original)
            process_stable_sell_signal: Function to process sell signal (stable)
            process_batch_sell_signal: Function to process sell signal (batch)
        """
        import os

        self.strategy_name = strategy_name
        self.stable_strategy_name = stable_strategy_name
        self.batch_strategy_name = batch_strategy_name
        self.get_db_connection = get_db_connection
        self.get_trade_api = get_trade_api
        self.active_orders = active_orders
        self.stable_active_orders = stable_active_orders
        self.batch_active_orders = batch_active_orders
        self.stable_strategy = stable_strategy
        self.batch_strategy = batch_strategy
        self.lock = lock
        self.process_sell_signal = process_sell_signal
        self.process_stable_sell_signal = process_stable_sell_signal
        self.process_batch_sell_signal = process_batch_sell_signal
        self.simulation_mode = simulation_mode
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

            # Capture threading module in closure to avoid UnboundLocalError
            import threading as threading_module

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

            threading_module.Thread(target=run_deep_recovery, daemon=True).start()

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

                if (
                    not self.simulation_mode
                    and api is not None
                    and api_call_count < max_api_calls_per_cycle
                ):
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
                # ✅ FIX: Always sell at next hour's 55 minutes
                # Calculate next hour's 55 minutes
                next_hour = fill_time.replace(minute=55, second=0, microsecond=0)
                # Always add 1 hour to ensure we sell at next hour's close
                next_hour = next_hour + timedelta(hours=1)

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

            # Recover stable strategy orders
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
                (self.stable_strategy_name, cutoff_time, recovery_limit),
            )
            rows = cur.fetchall()

            # Reset API call count for stable strategy recovery
            # (reuse the same rate limiting from original strategy recovery)
            stable_api_call_count = api_call_count

            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                with self.lock:
                    if instId in self.stable_active_orders:
                        continue

                # Get fillTime from OKX API (same logic as original strategy)
                fill_time = None
                next_hour = None

                if (
                    not self.simulation_mode
                    and api is not None
                    and stable_api_call_count < max_api_calls_per_cycle
                ):
                    try:
                        result = api.get_order(instId=instId, ordId=ordId)
                        stable_api_call_count += 1
                        if stable_api_call_count < max_api_calls_per_cycle:
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
                                        f"✅ RECOVER: Using OKX fillTime for stable {instId}, ordId={ordId}: "
                                        f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                                except (ValueError, TypeError) as e:
                                    logger.warning(
                                        f"⚠️ RECOVER: Invalid fillTime from OKX for stable {instId}: {fill_time_ms}, "
                                        f"falling back to create_time: {e}"
                                    )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ RECOVER: Failed to get order from OKX for stable {instId}, "
                            f"ordId={ordId}: {e}, falling back to create_time"
                        )
                elif stable_api_call_count >= max_api_calls_per_cycle:
                    logger.debug(
                        f"⏸️ RECOVER: API rate limit reached ({max_api_calls_per_cycle} calls), "
                        f"using create_time for remaining stable orders"
                    )

                # Fallback to create_time if fillTime not available
                if fill_time is None:
                    fill_time = datetime.fromtimestamp(create_time_ms / 1000)
                    logger.info(
                        f"📝 RECOVER: Using create_time as fallback for stable {instId}, ordId={ordId} "
                        f"(API unavailable or rate limited)"
                    )

                # Calculate next_hour_close_time from fill_time
                # ✅ FIX: Always sell at next hour's 55 minutes
                # Calculate next hour's 55 minutes
                next_hour = fill_time.replace(minute=55, second=0, microsecond=0)
                # Always add 1 hour to ensure we sell at next hour's close
                next_hour = next_hour + timedelta(hours=1)

                # Only recover if past sell time
                if now >= next_hour:
                    logger.warning(
                        f"🔄 RECOVER: Found stable order not in memory: {instId}, "
                        f"ordId={ordId}, state={db_state}, fill_time={fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"recovering to stable_active_orders"
                    )

                    with self.lock:
                        self.stable_active_orders[instId] = {
                            "ordId": ordId,
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                            "fill_time": fill_time,
                            "last_sell_attempt_time": None,
                        }

                    # Trigger sell immediately
                    logger.warning(
                        f"⏰ RECOVER SELL: {instId} (stable), "
                        f"triggering sell for recovered order"
                    )
                    import threading

                    threading.Thread(
                        target=self.process_stable_sell_signal,
                        args=(instId,),
                        daemon=True,
                    ).start()

            # Recover batch strategy orders
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
                (self.batch_strategy_name, cutoff_time, recovery_limit),
            )
            rows = cur.fetchall()

            # Group batch orders by instId
            batch_orders_by_inst = {}
            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                if instId not in batch_orders_by_inst:
                    batch_orders_by_inst[instId] = []
                batch_orders_by_inst[instId].append(
                    {
                        "ordId": ordId,
                        "create_time_ms": create_time_ms,
                        "db_state": db_state,
                        "db_size": db_size,
                    }
                )

            # Reset API call count for batch strategy recovery
            batch_api_call_count = stable_api_call_count

            for instId, orders in batch_orders_by_inst.items():
                with self.lock:
                    if instId in self.batch_active_orders:
                        continue

                # Get fillTime from all orders and use the latest one
                # This ensures next_hour_close_time is correct even if later batches fill much later
                # ✅ OPTIMIZED: Only call API for first order per instId to avoid rate limits
                # Batch orders are usually filled close together, so one API call is sufficient
                latest_fill_time = None
                latest_create_time_ms = None
                ordIds = []
                total_size = 0.0

                # Collect all order info first
                for order_info in orders:
                    ordId = order_info["ordId"]
                    create_time_ms = order_info["create_time_ms"]
                    db_size = order_info["db_size"]
                    ordIds.append(ordId)
                    total_size += float(db_size) if db_size else 0.0

                    # Track latest create_time as fallback
                    if (
                        latest_create_time_ms is None
                        or create_time_ms > latest_create_time_ms
                    ):
                        latest_create_time_ms = create_time_ms

                # Try to get fillTime from OKX API for first order only (batches fill close together)
                if (
                    not self.simulation_mode
                    and api is not None
                    and batch_api_call_count < max_api_calls_per_cycle
                    and orders
                ):
                    first_order = orders[0]
                    first_ordId = first_order["ordId"]
                    try:
                        result = api.get_order(instId=instId, ordId=first_ordId)
                        batch_api_call_count += 1
                        if batch_api_call_count < max_api_calls_per_cycle:
                            time.sleep(api_call_delay)

                        if result and result.get("data") and len(result["data"]) > 0:
                            order_data = result["data"][0]
                            fill_time_ms = order_data.get("fillTime", "")
                            if fill_time_ms and fill_time_ms != "":
                                try:
                                    latest_fill_time = datetime.fromtimestamp(
                                        int(fill_time_ms) / 1000
                                    )
                                    logger.info(
                                        f"✅ RECOVER: Using OKX fillTime for batch {instId} (from first order {first_ordId}): "
                                        f"{latest_fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                                except (ValueError, TypeError) as e:
                                    logger.warning(
                                        f"⚠️ RECOVER: Invalid fillTime from OKX for batch {instId}, ordId={first_ordId}: {fill_time_ms}, "
                                        f"falling back to create_time: {e}"
                                    )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ RECOVER: Failed to get order from OKX for batch {instId}, "
                            f"ordId={first_ordId}: {e}, falling back to create_time"
                        )

                # Fallback to latest create_time if fillTime not available
                if latest_fill_time is None:
                    latest_fill_time = datetime.fromtimestamp(
                        latest_create_time_ms / 1000
                    )
                    logger.info(
                        f"📝 RECOVER: Using create_time as fallback for batch {instId} "
                        f"(API unavailable or rate limited)"
                    )

                # Calculate next_hour_close_time from latest fill_time
                next_hour = latest_fill_time.replace(minute=55, second=0, microsecond=0)
                next_hour = next_hour + timedelta(hours=1)

                # Only recover if past sell time
                if now >= next_hour:
                    logger.warning(
                        f"🔄 RECOVER: Found batch orders not in memory: {instId}, "
                        f"ordIds={ordIds}, fill_time={latest_fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"recovering to batch_active_orders"
                    )

                    # Restore to batch_active_orders
                    with self.lock:
                        self.batch_active_orders[instId] = {
                            "ordIds": ordIds,
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                            "fill_time": latest_fill_time,
                            "last_sell_attempt_time": None,
                            "total_size": total_size,
                        }

                    # Trigger sell immediately
                    logger.warning(
                        f"⏰ RECOVER SELL: {instId} (batch), "
                        f"triggering sell for recovered orders"
                    )
                    import threading

                    threading.Thread(
                        target=self.process_batch_sell_signal,
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

                if (
                    not self.simulation_mode
                    and api is not None
                    and api_call_count < max_api_calls_per_cycle
                ):
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
                # ✅ FIX: Always sell at next hour's 55 minutes
                # Calculate next hour's 55 minutes
                next_hour = fill_time.replace(minute=55, second=0, microsecond=0)
                # Always add 1 hour to ensure we sell at next hour's close
                next_hour = next_hour + timedelta(hours=1)

                # Only recover if past sell time
                if now >= next_hour:
                    logger.warning(
                        f"🔄 DEEP RECOVER: Found stuck stable order: {instId}, "
                        f"ordId={ordId}, state={db_state}, fill_time={fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"recovering to stable_active_orders"
                    )

                    # Restore to stable_active_orders
                    with self.lock:
                        self.stable_active_orders[instId] = {
                            "ordId": ordId,
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                            "fill_time": fill_time,
                            "last_sell_attempt_time": None,
                        }

                    # Trigger sell immediately
                    logger.warning(
                        f"⏰ DEEP RECOVER SELL: {instId} (stable), "
                        f"triggering sell for recovered order"
                    )
                    import threading

                    threading.Thread(
                        target=self.process_stable_sell_signal,
                        args=(instId,),
                        daemon=True,
                    ).start()
                    recovered_count += 1

            # Recover stable strategy orders
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
                (self.stable_strategy_name, cutoff_time, deep_recovery_limit),
            )
            rows = cur.fetchall()

            if len(rows) >= deep_recovery_limit:
                logger.warning(
                    f"⚠️ DEEP RECOVER: Hit {deep_recovery_limit} limit for stable strategy, "
                    f"there may be more stuck orders"
                )

            api_call_count = 0
            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                with self.lock:
                    if instId in self.stable_active_orders:
                        continue

                # Get fillTime from OKX API (same logic as original strategy)
                fill_time = None
                next_hour = None

                if (
                    not self.simulation_mode
                    and api is not None
                    and api_call_count < max_api_calls_per_cycle
                ):
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
                                        f"✅ DEEP RECOVER: Using OKX fillTime for stable {instId}, ordId={ordId}: "
                                        f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                                except (ValueError, TypeError) as e:
                                    logger.warning(
                                        f"⚠️ DEEP RECOVER: Invalid fillTime from OKX for stable {instId}: {fill_time_ms}, "
                                        f"falling back to create_time: {e}"
                                    )
                    except Exception as e:
                        logger.debug(
                            f"⚠️ DEEP RECOVER: Failed to get order from OKX for stable {instId}, "
                            f"ordId={ordId}: {e}, falling back to create_time"
                        )

                # Fallback to create_time if fillTime not available
                if fill_time is None:
                    fill_time = datetime.fromtimestamp(create_time_ms / 1000)

                # Calculate next_hour_close_time from fill_time
                # ✅ FIX: Always sell at next hour's 55 minutes
                # Calculate next hour's 55 minutes
                next_hour = fill_time.replace(minute=55, second=0, microsecond=0)
                # Always add 1 hour to ensure we sell at next hour's close
                next_hour = next_hour + timedelta(hours=1)

                # Only recover if past sell time
                if now >= next_hour:
                    logger.warning(
                        f"🔄 DEEP RECOVER: Found stuck stable order: {instId}, "
                        f"ordId={ordId}, state={db_state}, fill_time={fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"recovering to stable_active_orders"
                    )

                    with self.lock:
                        self.stable_active_orders[instId] = {
                            "ordId": ordId,
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                            "fill_time": fill_time,
                            "last_sell_attempt_time": None,
                        }

                    import threading

                    threading.Thread(
                        target=self.process_stable_sell_signal,
                        args=(instId,),
                        daemon=True,
                    ).start()
                    recovered_count += 1

            # Recover batch strategy orders
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
                (self.batch_strategy_name, cutoff_time, deep_recovery_limit),
            )
            rows = cur.fetchall()

            if len(rows) >= deep_recovery_limit:
                logger.warning(
                    f"⚠️ DEEP RECOVER: Hit {deep_recovery_limit} limit for batch strategy, "
                    f"there may be more stuck orders"
                )

            # Group batch orders by instId
            batch_orders_by_inst = {}
            for row in rows:
                instId = row[0]
                ordId = row[1]
                create_time_ms = row[2]
                db_state = row[3]
                db_size = row[4]

                if instId not in batch_orders_by_inst:
                    batch_orders_by_inst[instId] = []
                batch_orders_by_inst[instId].append(
                    {
                        "ordId": ordId,
                        "create_time_ms": create_time_ms,
                        "db_state": db_state,
                        "db_size": db_size,
                    }
                )

            api_call_count = 0
            for instId, orders in batch_orders_by_inst.items():
                with self.lock:
                    if instId in self.batch_active_orders:
                        continue

                # Get fillTime from all orders and use the latest one
                # ✅ OPTIMIZED: Only call API for first order per instId to avoid rate limits
                # Batch orders are usually filled close together, so one API call is sufficient
                latest_fill_time = None
                latest_create_time_ms = None
                ordIds = []
                total_size = 0.0

                # Collect all order info first
                for order_info in orders:
                    ordId = order_info["ordId"]
                    create_time_ms = order_info["create_time_ms"]
                    db_size = order_info["db_size"]
                    ordIds.append(ordId)
                    total_size += float(db_size) if db_size else 0.0

                    # Track latest create_time as fallback
                    if (
                        latest_create_time_ms is None
                        or create_time_ms > latest_create_time_ms
                    ):
                        latest_create_time_ms = create_time_ms

                # Try to get fillTime from OKX API for first order only (batches fill close together)
                if (
                    api is not None
                    and api_call_count < max_api_calls_per_cycle
                    and orders
                ):
                    first_order = orders[0]
                    first_ordId = first_order["ordId"]
                    try:
                        result = api.get_order(instId=instId, ordId=first_ordId)
                        api_call_count += 1
                        if api_call_count < max_api_calls_per_cycle:
                            time.sleep(api_call_delay)

                        if result and result.get("data") and len(result["data"]) > 0:
                            order_data = result["data"][0]
                            fill_time_ms = order_data.get("fillTime", "")
                            if fill_time_ms and fill_time_ms != "":
                                try:
                                    latest_fill_time = datetime.fromtimestamp(
                                        int(fill_time_ms) / 1000
                                    )
                                except (ValueError, TypeError):
                                    pass
                    except Exception as e:
                        logger.debug(
                            f"⚠️ DEEP RECOVER: Failed to get order from OKX for batch {instId}, "
                            f"ordId={first_ordId}: {e}, falling back to create_time"
                        )

                # Fallback to latest create_time if fillTime not available
                if latest_fill_time is None:
                    latest_fill_time = datetime.fromtimestamp(
                        latest_create_time_ms / 1000
                    )

                # Calculate next_hour_close_time from latest fill_time
                next_hour = latest_fill_time.replace(minute=55, second=0, microsecond=0)
                next_hour = next_hour + timedelta(hours=1)

                # Only recover if past sell time
                if now >= next_hour:
                    logger.warning(
                        f"🔄 DEEP RECOVER: Found stuck batch orders: {instId}, "
                        f"ordIds={ordIds}, fill_time={latest_fill_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"recovering to batch_active_orders"
                    )

                    with self.lock:
                        self.batch_active_orders[instId] = {
                            "ordIds": ordIds,
                            "next_hour_close_time": next_hour,
                            "sell_triggered": False,
                            "fill_time": latest_fill_time,
                            "last_sell_attempt_time": None,
                            "total_size": total_size,
                        }

                    import threading

                    threading.Thread(
                        target=self.process_batch_sell_signal,
                        args=(instId,),
                        daemon=True,
                    ).start()
                    recovered_count += 1

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
