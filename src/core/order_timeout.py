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
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Environment-configurable timeout
ORDER_TIMEOUT_SECONDS = int(os.getenv("ORDER_TIMEOUT_SECONDS", "60"))


def _select_valid_fill_price(order_data: dict) -> tuple[str, float]:
    """Return best available fill price string (prefer avgPx over fillPx)."""
    avg_px = str(order_data.get("avgPx", "") or "").strip()
    fill_px = str(order_data.get("fillPx", "") or "").strip()

    for candidate in (avg_px, fill_px):
        if not candidate:
            continue
        try:
            candidate_float = float(candidate)
            if candidate_float > 0:
                return candidate, candidate_float
        except (ValueError, TypeError):
            continue

    return "", 0.0


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
    batch_strategy: Optional[Any],
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
                price_to_save, price_float = _select_valid_fill_price(order_data)
                state = order_data.get("state", "")
                fill_time_ms = order_data.get("fillTime", "")
                filled_size = (
                    float(acc_fill_sz) if acc_fill_sz and acc_fill_sz != "" else 0.0
                )
                is_fully_filled = state == "filled" and filled_size > 0
                is_partially_filled = state == "partially_filled" and filled_size > 0

                if is_partially_filled:
                    logger.warning(
                        f"{strategy_name} Order partially filled: {instId}, "
                        f"ordId={ordId}, filled={acc_fill_sz}, state={state}"
                    )

                    if fill_time_ms and fill_time_ms != "":
                        try:
                            fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                            logger.info(
                                f"{strategy_name} OKX fillTime {instId}, {ordId}: "
                                f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"{strategy_name} Invalid fillTime from OKX: "
                                f"{fill_time_ms}, using local time: {e}"
                            )
                            fill_time = datetime.now()
                    else:
                        logger.warning(
                            f"{strategy_name} No fillTime from OKX for {instId}, "
                            f"ordId={ordId}, using local time"
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
                            f"{strategy_name} Invalid accFillSz for partial order: "
                            f"{instId}, ordId={ordId}, accFillSz={acc_fill_sz}"
                        )
                        return

                    conn = get_db_connection_func()
                    try:
                        cur = conn.cursor()
                        if price_to_save:
                            cur.execute(
                                """UPDATE orders
                                   SET state = %s, size = %s, price = %s, sell_time = %s
                                   WHERE instId = %s AND ordId = %s AND flag = %s""",
                                (
                                    "partially_filled",
                                    acc_fill_sz,
                                    price_to_save,
                                    sell_time_ms,
                                    instId,
                                    ordId,
                                    strategy_name,
                                ),
                            )
                        else:
                            cur.execute(
                                """UPDATE orders
                                   SET state = %s, size = %s, sell_time = %s
                                   WHERE instId = %s AND ordId = %s AND flag = %s""",
                                (
                                    "partially_filled",
                                    acc_fill_sz,
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
                            f"{strategy_name} Canceled remaining unfilled: "
                            f"{instId}, ordId={ordId}"
                        )
                    except Exception as e:
                        logger.error(
                            f"{strategy_name} Error canceling partial order: "
                            f"{instId}, {ordId}, {e}"
                        )

                    with lock:
                        if (
                            instId in active_orders
                            and active_orders[instId].get("ordId") == ordId
                        ):
                            active_orders[instId]["filled_size"] = filled_size
                            active_orders[instId]["fill_price"] = price_float
                            active_orders[instId]["next_hour_close_time"] = next_hour
                            active_orders[instId]["fill_time"] = fill_time
                            nxt = next_hour.strftime("%H:%M:%S")
                            logger.warning(
                                f"{strategy_name} Updated active_order partial: "
                                f"{instId}, filled_size={filled_size}, next={nxt}"
                            )
                        elif (
                            instId in stable_active_orders
                            and stable_active_orders[instId].get("ordId") == ordId
                        ):
                            stable_active_orders[instId]["filled_size"] = filled_size
                            stable_active_orders[instId]["fill_price"] = price_float
                            stable_active_orders[instId][
                                "next_hour_close_time"
                            ] = next_hour
                            stable_active_orders[instId]["fill_time"] = fill_time
                            nxt = next_hour.strftime("%H:%M:%S")
                            logger.warning(
                                f"{strategy_name} Updated stable_active_order partial: "
                                f"{instId}, filled_size={filled_size}, next={nxt}"
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
                            nxt = next_hour.strftime("%H:%M:%S")
                            logger.warning(
                                f"{strategy_name} Updated batch_active_order partial: "
                                f"{instId}, filled_size={filled_size}, next={nxt}"
                            )
                    return

                if not is_fully_filled:
                    tradeAPI.cancel_order(instId=instId, ordId=ordId)
                    logger.warning(
                        f"{strategy_name} Canceled unfilled after 1 min: "
                        f"{instId}, ordId={ordId}"
                    )

                    conn = get_db_connection_func()
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE orders SET state = %s WHERE instId = %s "
                            "AND ordId = %s AND flag = %s",
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
                                        "SELECT size FROM orders WHERE instId = %s "
                                        "AND ordId = %s AND flag = %s",
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
                                        f"⚠️ Could not get canceled size "
                                        f"{instId}, {ordId}: {e}"
                                    )

                            if not batch_active_orders[instId].get("ordIds"):
                                # All batches canceled or completed, reset state
                                del batch_active_orders[instId]
                                if batch_strategy:
                                    batch_strategy.reset_crypto(instId)
                                if instId in batch_pending_buys:
                                    del batch_pending_buys[instId]
                                    logger.warning(
                                        f"🔄 Reset batch strategy for {instId} "
                                        "after order cancellation"
                                    )
                            else:
                                # Some batches still active, but this one was canceled
                                # Reset batch strategy to allow retry for this batch
                                if batch_strategy:
                                    # Find which batch index this was and reset
                                    # We can't easily determine batch index,
                                    # so reset the whole crypto for new signal
                                    batch_strategy.reset_crypto(instId)
                                if instId in batch_pending_buys:
                                    del batch_pending_buys[instId]
                                    logger.warning(
                                        f"🔄 Reset batch for {instId} "
                                        "after partial batch cancellation"
                                    )
                else:
                    logger.warning(
                        f"{strategy_name} Order filled within 1 min: "
                        f"{instId}, ordId={ordId}, fillSz={acc_fill_sz}, "
                        f"fillPx={price_to_save or 'N/A'}"
                    )

                    fill_time_ms = order_data.get("fillTime", "")
                    if fill_time_ms and fill_time_ms != "":
                        try:
                            fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000)
                            logger.info(
                                f"{strategy_name} OKX fillTime {instId}, {ordId}: "
                                f"{fill_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"{strategy_name} Invalid fillTime from OKX: "
                                f"{fill_time_ms}, using local time: {e}"
                            )
                            fill_time = datetime.now()
                    else:
                        logger.warning(
                            f"{strategy_name} No fillTime from OKX for {instId}, "
                            f"ordId={ordId}, using local time"
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
                            f"{strategy_name} Invalid accFillSz for filled: "
                            f"{instId}, ordId={ordId}, accFillSz={acc_fill_sz}"
                        )
                        return

                    conn = get_db_connection_func()
                    try:
                        cur = conn.cursor()
                        if price_to_save:
                            cur.execute(
                                """UPDATE orders
                                   SET state = %s, size = %s, price = %s, sell_time = %s
                                   WHERE instId = %s AND ordId = %s AND flag = %s""",
                                (
                                    "filled",
                                    acc_fill_sz,
                                    price_to_save,
                                    sell_time_ms,
                                    instId,
                                    ordId,
                                    strategy_name,
                                ),
                            )
                        else:
                            cur.execute(
                                """UPDATE orders
                                   SET state = %s, size = %s, sell_time = %s
                                   WHERE instId = %s AND ordId = %s AND flag = %s""",
                                (
                                    "filled",
                                    acc_fill_sz,
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
                                active_orders[instId]["fill_price"] = price_float
                                active_orders[instId][
                                    "next_hour_close_time"
                                ] = next_hour
                                active_orders[instId]["fill_time"] = fill_time
                                nxt = next_hour.strftime("%H:%M:%S")
                                logger.warning(
                                    f"{strategy_name} Updated active_order fill: "
                                    f"{instId}, next_hour_close={nxt}"
                                )
                            elif (
                                instId in stable_active_orders
                                and stable_active_orders[instId].get("ordId") == ordId
                            ):
                                stable_active_orders[instId][
                                    "filled_size"
                                ] = filled_size
                                stable_active_orders[instId]["fill_price"] = price_float
                                stable_active_orders[instId][
                                    "next_hour_close_time"
                                ] = next_hour
                                stable_active_orders[instId]["fill_time"] = fill_time
                                nxt = next_hour.strftime("%H:%M:%S")
                                logger.warning(
                                    f"{strategy_name} Updated stable_active fill: "
                                    f"{instId}, next_hour_close={nxt}"
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
                                nxt = next_hour.strftime("%H:%M:%S")
                                logger.warning(
                                    f"{strategy_name} Updated batch_active fill: "
                                    f"{instId}, next_hour_close={nxt}"
                                )

                        cur.close()
                    finally:
                        conn.close()
        except Exception as e:
            logger.error(
                f"{strategy_name} Error checking order after timeout: "
                f"{instId}, {ordId}: {e}"
            )
    except Exception as e:
        logger.error(f"{strategy_name} Error in timeout check {instId}, {ordId}: {e}")
