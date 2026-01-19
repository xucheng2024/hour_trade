#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket Message Handlers
Handles ticker and candle WebSocket messages
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def on_ticker_message(
    ws,
    msg_string: str,
    crypto_limits: dict,
    current_prices: dict,
    reference_prices: dict,
    reference_price_fetch_time: dict,
    reference_price_fetch_attempts: dict,
    pending_buys: dict,
    active_orders: dict,
    lock: threading.Lock,
    fetch_current_hour_open_price_func,
    calculate_limit_price_func,
    process_buy_signal_func,
    check_2h_gain_filter_func,  # Function to check 2h gain filter
    thread_pool=None,  # Optional thread pool for async processing
):
    """Handle ticker WebSocket messages"""
    if msg_string == "pong":
        return

    try:
        m = json.loads(msg_string)
        ev = m.get("event")
        data = m.get("data")

        if ev == "error":
            logger.error(f"Ticker WebSocket error: {msg_string}")
        elif ev in ["subscribe", "unsubscribe"]:
            logger.info(f"Ticker {ev}: {msg_string}")
        elif data and isinstance(data, list):
            for ticker in data:
                instId = ticker.get("instId")
                if instId in crypto_limits:
                    last_price = float(ticker.get("last", 0))

                    if last_price > 0:
                        # ✅ OPTIMIZED: Skip if price hasn't changed (deduplication)
                        with lock:
                            old_price = current_prices.get(instId)
                            if old_price == last_price:
                                continue  # Price unchanged, skip processing
                            current_prices[instId] = last_price

                            if (
                                instId in reference_price_fetch_attempts
                                and reference_price_fetch_attempts[instId] > 0
                            ):
                                reference_price_fetch_attempts[instId] = 0
                                logger.debug(
                                    f"📊 Reset reference_price_fetch_attempts for {instId} "
                                    f"on ticker update (coin is active)"
                                )

                            if (
                                instId not in pending_buys
                                and instId not in active_orders
                            ):
                                limit_percent = crypto_limits[instId]
                                ref_price = reference_prices.get(instId)

                        if ref_price is None or ref_price <= 0:
                            with lock:
                                last_fetch = reference_price_fetch_time.get(instId, 0)
                                fetch_attempts = reference_price_fetch_attempts.get(
                                    instId, 0
                                )
                                time_since_fetch = time.time() - last_fetch
                                min_wait = min(5 * (2 ** min(fetch_attempts, 4)), 60)

                                if time_since_fetch < min_wait:
                                    logger.debug(
                                        f"⏳ Skipping reference price fetch for {instId}: "
                                        f"backoff ({time_since_fetch:.1f}s < {min_wait}s)"
                                    )
                                    continue

                                reference_price_fetch_time[instId] = time.time()

                            logger.warning(
                                f"⚠️ No reference price for {instId}, fetching current hour's open..."
                            )
                            ref_price = fetch_current_hour_open_price_func(instId)
                            if ref_price and ref_price > 0:
                                with lock:
                                    if (
                                        instId not in pending_buys
                                        and instId not in active_orders
                                    ):
                                        reference_prices[instId] = ref_price
                                        reference_price_fetch_attempts[instId] = 0
                            else:
                                with lock:
                                    reference_price_fetch_attempts[instId] = (
                                        fetch_attempts + 1
                                    )
                                logger.warning(
                                    f"⚠️ Failed to get reference price for {instId}, skipping buy check "
                                    f"(will retry after backoff, attempts={fetch_attempts + 1})"
                                )
                                continue

                        limit_price = calculate_limit_price_func(
                            ref_price, limit_percent, instId
                        )

                        if last_price <= limit_price:
                            # ✅ NEW: Check 2-hour gain filter before buying
                            should_skip_buy, gain_pct = check_2h_gain_filter_func(
                                instId, ref_price
                            )
                            if should_skip_buy:
                                logger.warning(
                                    f"🚫 {instId} BUY BLOCKED by 2h gain filter: "
                                    f"gain={gain_pct:.2f}% > 5% "
                                    f"(current_open=${ref_price:.6f})"
                                )
                                continue

                            with lock:
                                if instId in pending_buys or instId in active_orders:
                                    continue
                                pending_buys[instId] = True

                            gain_info = (
                                f", 2h_gain={gain_pct:.2f}%"
                                if gain_pct is not None
                                else ""
                            )
                            logger.warning(
                                f"🚀 BUY SIGNAL: {instId}, "
                                f"current={last_price:.6f} <= limit={limit_price:.6f} "
                                f"(ref={ref_price:.6f}, {limit_percent}%{gain_info})"
                            )
                            # ✅ OPTIMIZED: Use thread pool if available, otherwise create thread
                            if thread_pool:
                                thread_pool.submit(
                                    process_buy_signal_func, instId, limit_price
                                )
                            else:
                                threading.Thread(
                                    target=process_buy_signal_func,
                                    args=(instId, limit_price),
                                    daemon=True,
                                ).start()
                        else:
                            # Reduce high-frequency market data logging
                            import os

                            reduce_market_logs = (
                                os.getenv("REDUCE_MARKET_DATA_LOGS", "true").lower()
                                == "true"
                            )
                            if not reduce_market_logs:
                                price_diff_pct = (
                                    (last_price - limit_price) / ref_price
                                ) * 100
                                if price_diff_pct < 2.0:
                                    logger.debug(
                                        f"📊 {instId} close to limit: "
                                        f"current={last_price:.6f}, "
                                        f"limit={limit_price:.6f}, "
                                        f"diff={price_diff_pct:.2f}%"
                                    )
    except Exception as e:
        logger.error(f"Ticker message error: {msg_string}, {e}")


def on_candle_message(
    ws,
    msg_string: str,
    crypto_limits: dict,
    reference_prices: dict,
    reference_price_fetch_attempts: dict,
    last_1h_candle_time: dict,
    last_intra_hour_check: dict,
    active_orders: dict,
    momentum_active_orders: dict,
    momentum_pending_buys: dict,
    momentum_strategy: Optional[object],
    lock: threading.Lock,
    process_sell_signal_func,
    process_momentum_buy_signal_func,
    process_momentum_sell_signal_func,
    INTRA_HOUR_CHECK_THROTTLE_SECONDS: int,
    thread_pool=None,  # Optional thread pool for async processing
):
    """Handle candle WebSocket messages"""
    if msg_string == "pong":
        return

    try:
        m = json.loads(msg_string)
        ev = m.get("event")
        data = m.get("data")
        arg = m.get("arg", {})

        if ev == "error":
            logger.error(f"Candle WebSocket error: {msg_string}")
        elif ev in ["subscribe", "unsubscribe"]:
            logger.info(f"Candle {ev}: {msg_string}")
        elif data and isinstance(data, list) and len(data) > 0:
            channel = arg.get("channel", "")
            if "candle1H" in channel:
                instId = arg.get("instId")
                candle_data = data[0]
                if isinstance(candle_data, list) and len(candle_data) >= 9:
                    candle_ts = int(candle_data[0]) / 1000
                    candle_hour = datetime.fromtimestamp(candle_ts).replace(
                        minute=0, second=0, microsecond=0
                    )
                    open_price = float(candle_data[1])
                    confirm = str(candle_data[8])

                    if instId in crypto_limits:
                        with lock:
                            current_hour = datetime.now().replace(
                                minute=0, second=0, microsecond=0
                            )
                            time_diff = abs(
                                (candle_hour - current_hour).total_seconds()
                            )
                            if time_diff <= 60:
                                reference_prices[instId] = open_price
                                if (
                                    instId in reference_price_fetch_attempts
                                    and reference_price_fetch_attempts[instId] > 0
                                ):
                                    reference_price_fetch_attempts[instId] = 0
                                    logger.debug(
                                        f"📊 Reset reference_price_fetch_attempts for {instId} "
                                        f"on candle update (coin is active)"
                                    )
                                logger.debug(
                                    f"📊 {instId} updated reference price from "
                                    f"WebSocket: ${open_price:.6f} (hour={candle_hour.strftime('%H:00')})"
                                )

                    if confirm == "1":
                        now = datetime.now()
                        with lock:
                            last_1h_candle_time[instId] = now

                        if momentum_strategy is not None and instId in crypto_limits:
                            candle_volume = (
                                float(candle_data[5]) if len(candle_data) > 5 else 0.0
                            )
                            close_price = (
                                float(candle_data[4])
                                if len(candle_data) > 4
                                else open_price
                            )
                            volume_ccy = (
                                float(candle_data[6])
                                if len(candle_data) > 6
                                else candle_volume
                            )
                            volume_to_use = (
                                volume_ccy if volume_ccy > 0 else candle_volume
                            )
                            if volume_to_use > 0:
                                momentum_strategy.update_price_volume(
                                    instId, close_price, volume_to_use
                                )

                                if (
                                    momentum_strategy is not None
                                    and instId in crypto_limits
                                ):
                                    should_buy, buy_pct = (
                                        momentum_strategy.check_buy_signal(
                                            instId, close_price
                                        )
                                    )
                                    if should_buy and buy_pct:
                                        with lock:
                                            if instId in momentum_pending_buys:
                                                logger.debug(
                                                    f"⏭️ {instId} Momentum buy already pending, skipping"
                                                )
                                            elif instId in momentum_active_orders:
                                                logger.debug(
                                                    f"⏭️ {instId} Momentum order already active, skipping"
                                                )
                                            else:
                                                position = (
                                                    momentum_strategy.get_position_info(
                                                        instId
                                                    )
                                                )
                                                if (
                                                    position
                                                    and position.get(
                                                        "total_buy_pct", 0.0
                                                    )
                                                    >= 0.70
                                                ):
                                                    logger.debug(
                                                        f"⏸️ {instId} Already at max position: "
                                                        f"{position.get('total_buy_pct', 0.0):.1%}"
                                                    )
                                                else:
                                                    momentum_pending_buys[instId] = True
                                                    logger.warning(
                                                        f"🎯 MOMENTUM BUY SIGNAL (confirmed 1H candle): {instId}, "
                                                        f"close_price={close_price:.6f}, buy_pct={buy_pct:.1%}"
                                                    )
                                                    # ✅ OPTIMIZED: Use thread pool if available
                                                    if thread_pool:
                                                        thread_pool.submit(
                                                            process_momentum_buy_signal_func,
                                                            instId,
                                                            close_price,
                                                            buy_pct,
                                                        )
                                                    else:
                                                        threading.Thread(
                                                            target=process_momentum_buy_signal_func,
                                                            args=(
                                                                instId,
                                                                close_price,
                                                                buy_pct,
                                                            ),
                                                            daemon=True,
                                                        ).start()

                        with lock:
                            if instId in active_orders:
                                if active_orders[instId].get("sell_triggered", False):
                                    logger.debug(
                                        f"⚠️ Sell already triggered for {instId}, skipping duplicate candle confirm"
                                    )
                                else:
                                    active_orders[instId]["sell_triggered"] = True
                                    close_price = (
                                        float(candle_data[4])
                                        if len(candle_data) > 4
                                        else 0
                                    )
                                    logger.warning(
                                        f"🕐 KLINE CONFIRMED: {instId}, "
                                        f"close_price={close_price:.6f}, trigger SELL (original)"
                                    )
                                    # ✅ OPTIMIZED: Use thread pool if available
                                    if thread_pool:
                                        thread_pool.submit(
                                            process_sell_signal_func, instId
                                        )
                                    else:
                                        threading.Thread(
                                            target=process_sell_signal_func,
                                            args=(instId,),
                                            daemon=True,
                                        ).start()

                            if instId in momentum_active_orders:
                                if momentum_active_orders[instId].get(
                                    "sell_triggered", False
                                ):
                                    logger.debug(
                                        f"⚠️ Momentum sell already triggered for {instId}, "
                                        f"skipping duplicate candle confirm"
                                    )
                                else:
                                    momentum_active_orders[instId][
                                        "sell_triggered"
                                    ] = True
                                    close_price = (
                                        float(candle_data[4])
                                        if len(candle_data) > 4
                                        else 0
                                    )
                                    logger.warning(
                                        f"🕐 KLINE CONFIRMED: {instId}, "
                                        f"close_price={close_price:.6f}, trigger SELL (momentum)"
                                    )
                                    # ✅ OPTIMIZED: Use thread pool if available
                                    if thread_pool:
                                        thread_pool.submit(
                                            process_momentum_sell_signal_func, instId
                                        )
                                    else:
                                        threading.Thread(
                                            target=process_momentum_sell_signal_func,
                                            args=(instId,),
                                            daemon=True,
                                        ).start()

                    if (
                        confirm != "1"
                        and momentum_strategy is not None
                        and instId in crypto_limits
                    ):
                        now = datetime.now()
                        last_check = last_intra_hour_check.get(instId)
                        if (
                            last_check is None
                            or (now - last_check).total_seconds()
                            >= INTRA_HOUR_CHECK_THROTTLE_SECONDS
                        ):
                            last_intra_hour_check[instId] = now

                            current_close_price = (
                                float(candle_data[4])
                                if len(candle_data) > 4
                                else open_price
                            )

                            should_buy, buy_pct = momentum_strategy.check_buy_signal(
                                instId, current_close_price
                            )
                            if should_buy and buy_pct:
                                with lock:
                                    if instId in momentum_pending_buys:
                                        logger.debug(
                                            f"⏭️ {instId} Momentum buy already pending (intra-hour), skipping"
                                        )
                                    elif instId in momentum_active_orders:
                                        logger.debug(
                                            f"⏭️ {instId} Momentum order already active (intra-hour), skipping"
                                        )
                                    else:
                                        position = momentum_strategy.get_position_info(
                                            instId
                                        )
                                        if (
                                            position
                                            and position.get("total_buy_pct", 0.0)
                                            >= 0.70
                                        ):
                                            logger.debug(
                                                f"⏸️ {instId} Already at max position (intra-hour): "
                                                f"{position.get('total_buy_pct', 0.0):.1%}"
                                            )
                                        else:
                                            momentum_pending_buys[instId] = True
                                            logger.warning(
                                                f"🎯 MOMENTUM BUY SIGNAL (intra-hour): {instId}, "
                                                f"current_price={current_close_price:.6f}, buy_pct={buy_pct:.1%}"
                                            )
                                            threading.Thread(
                                                target=process_momentum_buy_signal_func,
                                                args=(
                                                    instId,
                                                    current_close_price,
                                                    buy_pct,
                                                ),
                                                daemon=True,
                                            ).start()
    except Exception as e:
        logger.error(f"Candle message error: {msg_string}, {e}")
