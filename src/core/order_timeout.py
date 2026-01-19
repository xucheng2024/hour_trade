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
    momentum_active_orders: dict,
    lock,
):
    """Check order status after timeout, cancel if not filled"""
    if simulation_mode or ordId.startswith("HLW-SIM-") or ordId.startswith("MVE-SIM-"):
        return

    try:
        time.sleep(ORDER_TIMEOUT_SECONDS)

        with lock:
            order_exists = False
            if strategy_name == "hourly_limit_ws":
                if (
                    instId in active_orders
                    and active_orders[instId].get("ordId") == ordId
                ):
                    order_exists = True
            elif strategy_name == "momentum_volume_exhaustion":
                if instId in momentum_active_orders:
                    if ordId in momentum_active_orders[instId].get("ordIds", []):
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

                    next_hour = fill_time.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)
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
                        if strategy_name == "hourly_limit_ws":
                            if instId in active_orders:
                                active_orders[instId]["filled_size"] = filled_size
                                active_orders[instId]["fill_price"] = (
                                    float(fill_px) if fill_px else 0.0
                                )
                                active_orders[instId][
                                    "next_hour_close_time"
                                ] = next_hour
                                active_orders[instId]["fill_time"] = fill_time
                                logger.warning(
                                    f"{strategy_name} Updated active_order for partial fill: {instId}, "
                                    f"filled_size={filled_size}, next_hour_close={next_hour.strftime('%H:%M:%S')}"
                                )
                        elif strategy_name == "momentum_volume_exhaustion":
                            if instId in momentum_active_orders:
                                if ordId in momentum_active_orders[instId].get(
                                    "ordIds", []
                                ):
                                    idx = momentum_active_orders[instId][
                                        "ordIds"
                                    ].index(ordId)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_sizes", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_sizes"][
                                            idx
                                        ] = filled_size
                                    # Update next_hour_close_times list, not singular next_hour_close_time
                                    if (
                                        "next_hour_close_times"
                                        not in momentum_active_orders[instId]
                                    ):
                                        momentum_active_orders[instId][
                                            "next_hour_close_times"
                                        ] = []
                                    if idx < len(
                                        momentum_active_orders[instId][
                                            "next_hour_close_times"
                                        ]
                                    ):
                                        momentum_active_orders[instId][
                                            "next_hour_close_times"
                                        ][idx] = next_hour
                                    else:
                                        # Extend list if needed
                                        while (
                                            len(
                                                momentum_active_orders[instId][
                                                    "next_hour_close_times"
                                                ]
                                            )
                                            <= idx
                                        ):
                                            momentum_active_orders[instId][
                                                "next_hour_close_times"
                                            ].append(next_hour)
                                        momentum_active_orders[instId][
                                            "next_hour_close_times"
                                        ][idx] = next_hour
                                    logger.warning(
                                        f"{strategy_name} Updated momentum_active_order for partial fill: {instId}, "
                                        f"ordId={ordId}, filled_size={filled_size}, "
                                        f"next_hour_close={next_hour.strftime('%H:%M:%S')}"
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
                        if strategy_name == "hourly_limit_ws":
                            if instId in active_orders:
                                del active_orders[instId]
                        elif strategy_name == "momentum_volume_exhaustion":
                            if instId in momentum_active_orders:
                                if ordId in momentum_active_orders[instId].get(
                                    "ordIds", []
                                ):
                                    idx = momentum_active_orders[instId][
                                        "ordIds"
                                    ].index(ordId)
                                    momentum_active_orders[instId]["ordIds"].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_prices", []
                                        )
                                    ):
                                        momentum_active_orders[instId][
                                            "buy_prices"
                                        ].pop(idx)
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_sizes", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_sizes"].pop(
                                            idx
                                        )
                                    if idx < len(
                                        momentum_active_orders[instId].get(
                                            "buy_times", []
                                        )
                                    ):
                                        momentum_active_orders[instId]["buy_times"].pop(
                                            idx
                                        )
                                    if (
                                        "next_hour_close_times"
                                        in momentum_active_orders[instId]
                                    ):
                                        if idx < len(
                                            momentum_active_orders[instId][
                                                "next_hour_close_times"
                                            ]
                                        ):
                                            momentum_active_orders[instId][
                                                "next_hour_close_times"
                                            ].pop(idx)
                                if not momentum_active_orders[instId].get("ordIds", []):
                                    del momentum_active_orders[instId]
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

                    next_hour = fill_time.replace(
                        minute=0, second=0, microsecond=0
                    ) + timedelta(hours=1)
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
                            if strategy_name == "hourly_limit_ws":
                                if instId in active_orders:
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
                            elif strategy_name == "momentum_volume_exhaustion":
                                if instId in momentum_active_orders:
                                    if ordId in momentum_active_orders[instId].get(
                                        "ordIds", []
                                    ):
                                        idx = momentum_active_orders[instId][
                                            "ordIds"
                                        ].index(ordId)
                                        if (
                                            "next_hour_close_times"
                                            not in momentum_active_orders[instId]
                                        ):
                                            momentum_active_orders[instId][
                                                "next_hour_close_times"
                                            ] = []
                                        if idx < len(
                                            momentum_active_orders[instId][
                                                "next_hour_close_times"
                                            ]
                                        ):
                                            momentum_active_orders[instId][
                                                "next_hour_close_times"
                                            ][idx] = next_hour
                                        else:
                                            while (
                                                len(
                                                    momentum_active_orders[instId][
                                                        "next_hour_close_times"
                                                    ]
                                                )
                                                <= idx
                                            ):
                                                momentum_active_orders[instId][
                                                    "next_hour_close_times"
                                                ].append(next_hour)
                                            momentum_active_orders[instId][
                                                "next_hour_close_times"
                                            ][idx] = next_hour
                                    logger.warning(
                                        f"{strategy_name} Updated momentum_active_order for fill: {instId}, "
                                        f"ordId={ordId}, next_hour_close={next_hour.strftime('%H:%M:%S')}"
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
