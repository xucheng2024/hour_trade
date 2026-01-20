#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Timeout Check
Handles checking and canceling unfilled orders after timeout
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Environment-configurable timeout
ORDER_TIMEOUT_SECONDS = int(os.getenv("ORDER_TIMEOUT_SECONDS", "60"))


def check_and_cancel_unfilled_order_after_timeout(
    instId: str,
    ordId: str,
    tradeAPI,
    strategy_name: str,
    simulation_mode: bool,
    get_db_connection_func,
    active_orders: dict,
    stable_active_orders: dict,
    batch_active_orders: dict,
    batch_strategy: Optional[object],
    batch_pending_buys: dict,
    batch_strategy_name: str,
    lock,
):
    """Check order status after timeout, cancel if not filled"""
    if (
        simulation_mode
        or ordId.startswith("HLW-SIM-")
        or ordId.startswith("STB-SIM-")
        or ordId.startswith("BAT-SIM-")
    ):
        return

    try:
        time.sleep(ORDER_TIMEOUT_SECONDS)

        with lock:
            order_exists = False
            if instId in active_orders and active_orders[instId].get("ordId") == ordId:
                order_exists = True
            elif (
                instId in stable_active_orders
                and stable_active_orders[instId].get("ordId") == ordId
            ):
                order_exists = True
            elif instId in batch_active_orders and ordId in batch_active_orders[
                instId
            ].get("ordIds", []):
                order_exists = True

            if not order_exists:
                return

        try:
            result = tradeAPI.get_order(instId=instId, ordId=ordId)
            if result and result.get("data") and len(result["data"]) > 0:
                order_data = result["data"][0]
                acc_fill_sz = order_data.get("accFillSz", "0")
                fill_px = order_data.get("fillPx", "0")
                state = order_data.get("state", "")
                fill_time_ms = order_data.get("fillTime", "")
                filled_size = (
                    float(acc_fill_sz) if acc_fill_sz and acc_fill_sz != "" else 0.0
                )
                is_fully_filled = state == "filled" and filled_size > 0
                is_partially_filled = state == "partially_filled" and filled_size > 0

                if is_partially_filled:
                    logger.warning(
                        f"{strategy_name} Order partially filled: {instId}, ordId={ordId}, "
                        f"filled={acc_fill_sz}, state={state}"
                    )

                    if fill_time_ms and fill_time_ms != "":
                        try:
                            fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                            logger.info(
                                f"{strategy_name} Using OKX fillTime for {instId}, ordId={ordId}: "
                                f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"{strategy_name} Invalid fillTime from OKX: {fill_time_ms}, using local time: {e}"
                            )
                            fill_time = datetime.now()
                    else:
                        logger.warning(
                            f"{strategy_name} No fillTime from OKX for {instId}, ordId={ordId}, using local time"
                        )
                        fill_time = datetime.now()

                    # ✅ FIX: Always sell at next hour's 55 minutes
                    # Calculate next hour's 55 minutes
                    next_hour = fill_time.replace(minute=55, second=0, microsecond=0)
                    # Always add 1 hour to ensure we sell at next hour's close
                    next_hour = next_hour + timedelta(hours=1)
                    sell_time_ms = int(next_hour.timestamp() * 1000)

                    if not acc_fill_sz or acc_fill_sz == "" or acc_fill_sz == "0":
                        logger.error(
                            f"{strategy_name} Invalid accFillSz for partially filled order: "
                            f"{instId}, ordId={ordId}, accFillSz={acc_fill_sz}"
                        )
                        return

                    conn = get_db_connection_func()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            """UPDATE orders
                               SET state = %s, size = %s, price = %s, sell_time = %s
                               WHERE instId = %s AND ordId = %s AND flag = %s""",
                            (
                                "partially_filled",
                                acc_fill_sz,
                                fill_px,
                                sell_time_ms,
                                instId,
                                ordId,
                                strategy_name,
                            ),
                        )
                        conn.commit()
                        cur.close()
                    finally:
                        conn.close()

                    try:
                        tradeAPI.cancel_order(instId=instId, ordId=ordId)
                        logger.warning(
                            f"{strategy_name} Canceled remaining unfilled portion: {instId}, ordId={ordId}"
                        )
                    except Exception as e:
                        logger.error(
                            f"{strategy_name} Error canceling partial order: {instId}, {ordId}, {e}"
                        )

                    with lock:
                        if (
                            instId in active_orders
                            and active_orders[instId].get("ordId") == ordId
                        ):
                            active_orders[instId]["filled_size"] = filled_size
                            active_orders[instId]["fill_price"] = (
                                float(fill_px) if fill_px else 0.0
                            )
                            active_orders[instId]["next_hour_close_time"] = next_hour
                            active_orders[instId]["fill_time"] = fill_time
                            logger.warning(
                                f"{strategy_name} Updated active_order for partial fill: {instId}, "
                                f"filled_size={filled_size}, next_hour_close={next_hour.strftime('%H:%M:%S')}"
                            )
                        elif (
                            instId in stable_active_orders
                            and stable_active_orders[instId].get("ordId") == ordId
                        ):
                            stable_active_orders[instId]["filled_size"] = filled_size
                            stable_active_orders[instId]["fill_price"] = (
                                float(fill_px) if fill_px else 0.0
                            )
                            stable_active_orders[instId][
                                "next_hour_close_time"
                            ] = next_hour
                            stable_active_orders[instId]["fill_time"] = fill_time
                            logger.warning(
                                f"{strategy_name} Updated stable_active_order for partial fill: {instId}, "
                                f"filled_size={filled_size}, next_hour_close={next_hour.strftime('%H:%M:%S')}"
                            )
                        elif (
                            instId in batch_active_orders
                            and ordId in batch_active_orders[instId].get("ordIds", [])
                        ):
                            # For batch orders, update the specific batch
                            batch_active_orders[instId]["filled_size"] = (
                                batch_active_orders[instId].get("filled_size", 0.0)
                                + filled_size
                            )
                            batch_active_orders[instId][
                                "next_hour_close_time"
                            ] = next_hour
                            batch_active_orders[instId]["fill_time"] = fill_time
                            logger.warning(
                                f"{strategy_name} Updated batch_active_order for partial fill: {instId}, "
                                f"filled_size={filled_size}, next_hour_close={next_hour.strftime('%H:%M:%S')}"
                            )
                    return

                if not is_fully_filled:
                    tradeAPI.cancel_order(instId=instId, ordId=ordId)
                    logger.warning(
                        f"{strategy_name} Canceled unfilled order after 1 minute: {instId}, ordId={ordId}"
                    )

                    conn = get_db_connection_func()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE orders SET state = %s WHERE instId = %s AND ordId = %s AND flag = %s",
                            ("canceled", instId, ordId, strategy_name),
                        )
                        conn.commit()
                        cur.close()
                    finally:
                        conn.close()

                    with lock:
                        if (
                            instId in active_orders
                            and active_orders[instId].get("ordId") == ordId
                        ):
                            del active_orders[instId]
                        elif (
                            instId in stable_active_orders
                            and stable_active_orders[instId].get("ordId") == ordId
                        ):
                            del stable_active_orders[instId]
                        elif (
                            instId in batch_active_orders
                            and ordId in batch_active_orders[instId].get("ordIds", [])
                        ):
                            # Remove ordId from batch list
                            batch_active_orders[instId]["ordIds"].remove(ordId)
                            # Update total_size if available
                            if "total_size" in batch_active_orders[instId]:
                                # Try to get actual size from DB to subtract
                                try:
                                    conn = get_db_connection_func()
                                    cur = conn.cursor()
                                    cur.execute(
                                        "SELECT size FROM orders WHERE instId = %s AND ordId = %s AND flag = %s",
                                        (instId, ordId, batch_strategy_name),
                                    )
                                    row = cur.fetchone()
                                    if row and row[0]:
                                        canceled_size = float(row[0])
                                        batch_active_orders[instId]["total_size"] = max(
                                            0.0,
                                            batch_active_orders[instId]["total_size"]
                                            - canceled_size,
                                        )
                                    cur.close()
                                    conn.close()
                                except Exception as e:
                                    logger.warning(
                                        f"⚠️ Could not get canceled order size for {instId}, ordId={ordId}: {e}"
                                    )

                            if not batch_active_orders[instId].get("ordIds"):
                                # All batches canceled or completed, reset state
                                del batch_active_orders[instId]
                                if batch_strategy:
                                    batch_strategy.reset_crypto(instId)
                                if instId in batch_pending_buys:
                                    del batch_pending_buys[instId]
                                    logger.warning(
                                        f"🔄 Reset batch strategy state for {instId} after order cancellation"
                                    )
                            else:
                                # Some batches still active, but this one was canceled
                                # Reset batch strategy to allow retry for this batch
                                if batch_strategy:
                                    # Find which batch index this was and reset it
                                    # We can't easily determine the batch index, so reset the whole crypto
                                    # This allows a new batch signal to be registered
                                    batch_strategy.reset_crypto(instId)
                                if instId in batch_pending_buys:
                                    del batch_pending_buys[instId]
                                    logger.warning(
                                        f"🔄 Reset batch strategy state for {instId} after partial batch cancellation"
                                    )
                else:
                    logger.warning(
                        f"{strategy_name} Order filled within 1 minute: {instId}, ordId={ordId}, "
                        f"fillSize={acc_fill_sz}, fillPrice={fill_px}"
                    )

                    fill_time_ms = order_data.get("fillTime", "")
                    if fill_time_ms and fill_time_ms != "":
                        try:
                            fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                            logger.info(
                                f"{strategy_name} Using OKX fillTime for {instId}, ordId={ordId}: "
                                f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"{strategy_name} Invalid fillTime from OKX: {fill_time_ms}, using local time: {e}"
                            )
                            fill_time = datetime.now()
                    else:
                        logger.warning(
                            f"{strategy_name} No fillTime from OKX for {instId}, ordId={ordId}, using local time"
                        )
                        fill_time = datetime.now()

                    # ✅ FIX: Always sell at next hour's 55 minutes
                    # Calculate next hour's 55 minutes
                    next_hour = fill_time.replace(minute=55, second=0, microsecond=0)
                    # Always add 1 hour to ensure we sell at next hour's close
                    next_hour = next_hour + timedelta(hours=1)
                    sell_time_ms = int(next_hour.timestamp() * 1000)

                    if not acc_fill_sz or acc_fill_sz == "" or acc_fill_sz == "0":
                        logger.error(
                            f"{strategy_name} Invalid accFillSz for filled order: {instId}, ordId={ordId}, accFillSz={acc_fill_sz}"
                        )
                        return

                    conn = get_db_connection_func()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            """UPDATE orders
                               SET state = %s, size = %s, price = %s, sell_time = %s
                               WHERE instId = %s AND ordId = %s AND flag = %s""",
                            (
                                "filled",
                                acc_fill_sz,
                                fill_px,
                                sell_time_ms,
                                instId,
                                ordId,
                                strategy_name,
                            ),
                        )
                        conn.commit()

                        with lock:
                            if (
                                instId in active_orders
                                and active_orders[instId].get("ordId") == ordId
                            ):
                                active_orders[instId]["filled_size"] = filled_size
                                active_orders[instId]["fill_price"] = (
                                    float(fill_px) if fill_px else 0.0
                                )
                                active_orders[instId][
                                    "next_hour_close_time"
                                ] = next_hour
                                active_orders[instId]["fill_time"] = fill_time
                                logger.warning(
                                    f"{strategy_name} Updated active_order for fill: {instId}, "
                                    f"next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                )
                            elif (
                                instId in stable_active_orders
                                and stable_active_orders[instId].get("ordId") == ordId
                            ):
                                stable_active_orders[instId][
                                    "filled_size"
                                ] = filled_size
                                stable_active_orders[instId]["fill_price"] = (
                                    float(fill_px) if fill_px else 0.0
                                )
                                stable_active_orders[instId][
                                    "next_hour_close_time"
                                ] = next_hour
                                stable_active_orders[instId]["fill_time"] = fill_time
                                logger.warning(
                                    f"{strategy_name} Updated stable_active_order for fill: {instId}, "
                                    f"next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                )
                            elif (
                                instId in batch_active_orders
                                and ordId
                                in batch_active_orders[instId].get("ordIds", [])
                            ):
                                # For batch orders, update the specific batch
                                batch_active_orders[instId]["filled_size"] = (
                                    batch_active_orders[instId].get("filled_size", 0.0)
                                    + filled_size
                                )
                                batch_active_orders[instId][
                                    "next_hour_close_time"
                                ] = next_hour
                                batch_active_orders[instId]["fill_time"] = fill_time
                                logger.warning(
                                    f"{strategy_name} Updated batch_active_order for fill: {instId}, "
                                    f"next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                )

                        cur.close()
                    finally:
                        conn.close()
        except Exception as e:
            logger.error(
                f"{strategy_name} Error checking order status after timeout {instId}, {ordId}: {e}"
            )
    except Exception as e:
        logger.error(f"{strategy_name} Error in timeout check {instId}, {ordId}: {e}")
