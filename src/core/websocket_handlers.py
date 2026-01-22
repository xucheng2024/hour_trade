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
    stable_active_orders: dict,
    stable_pending_buys: dict,
    stable_strategy: Optional[object],
    batch_active_orders: dict,
    batch_pending_buys: dict,
    batch_strategy: Optional[object],
    lock: threading.Lock,
    fetch_current_hour_open_price_func,
    calculate_limit_price_func,
    process_buy_signal_func,
    process_stable_buy_signal_func,
    process_batch_buy_signal_func,
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
                        # ✅ FIX: Price deduplication - skip original if unchanged,
                        # but still allow stable strategy update_price + check_stability
                        # Allows stability seconds to accumulate during flat markets
                        with lock:
                            old_price = current_prices.get(instId)
                            price_unchanged = old_price == last_price
                            # Always update for consistency
                            current_prices[instId] = last_price

                            if (
                                instId in reference_price_fetch_attempts
                                and reference_price_fetch_attempts[instId] > 0
                            ):
                                reference_price_fetch_attempts[instId] = 0
                                logger.debug(
                                    f"📊 Reset reference_price_fetch_attempts "
                                    f"for {instId} on ticker update (coin is active)"
                                )

                            # Skip original strategy if already in pending_buys
                            # or active_orders
                            skip_original = (
                                instId in pending_buys or instId in active_orders
                            )

                        # ✅ FIX: Always update stable strategy (even if price unchanged)
                        # Allows stability seconds to accumulate during flat markets
                        # Runs independently, outside main lock to avoid deadlock
                        # stable_strategy has its own RLock, so calling it is safe
                        if stable_strategy is not None:
                            stable_strategy.update_price(instId, last_price)
                            # Check if stable strategy has pending signal ready
                            limit_price_stable = stable_strategy.check_stability(instId)
                            if limit_price_stable:
                                # Check stable strategy state (thread-safe check)
                                with lock:
                                    if (
                                        instId in stable_pending_buys
                                        and instId not in stable_active_orders
                                    ):
                                        should_trigger_stable = True
                                    else:
                                        should_trigger_stable = False

                                if should_trigger_stable:
                                    # Price is stable, trigger buy
                                    logger.warning(
                                        f"✅ STABLE BUY READY: {instId}, "
                                        f"limit={limit_price_stable:.6f}"
                                    )
                                    if thread_pool:
                                        thread_pool.submit(
                                            process_stable_buy_signal_func,
                                            instId,
                                            limit_price_stable,
                                        )
                                    else:
                                        threading.Thread(
                                            target=process_stable_buy_signal_func,
                                            args=(instId, limit_price_stable),
                                            daemon=True,
                                        ).start()

                        # ✅ FIX: Skip original if price unchanged OR already active
                        # Stable strategy already ran above, accumulates stability seconds
                        if price_unchanged or skip_original:
                            continue

                        # Get reference price and limit_percent outside lock
                        with lock:
                            ref_price = reference_prices.get(instId)
                            limit_percent = crypto_limits[instId]

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

                        # Check stable strategy buy signal independently (before original strategy check)
                        # This allows stable strategy to register even when original strategy is active
                        if stable_strategy is not None and last_price <= limit_price:
                            # Check if not already registered or active for stable strategy
                            with lock:
                                instId_not_in_stable = (
                                    instId not in stable_pending_buys
                                    and instId not in stable_active_orders
                                )

                            if instId_not_in_stable:
                                # Check 2h gain filter for stable strategy too
                                should_skip_buy_stable, gain_pct_stable = (
                                    check_2h_gain_filter_func(instId, ref_price)
                                )
                                if not should_skip_buy_stable:
                                    # Register stable buy signal (will wait for stability)
                                    # register_buy_signal uses its own RLock, safe to call outside main lock
                                    if stable_strategy.register_buy_signal(
                                        instId, limit_price
                                    ):
                                        with lock:
                                            stable_pending_buys[instId] = True
                                        logger.warning(
                                            f"📝 STABLE BUY SIGNAL REGISTERED: {instId}, "
                                            f"limit={limit_price:.6f}, waiting for stability"
                                        )

                        # Check batch strategy buy signal independently (before original strategy check)
                        # This allows batch strategy to register even when other strategies are active
                        if batch_strategy is not None and last_price <= limit_price:
                            # Check if not already registered or active for batch strategy
                            with lock:
                                instId_not_in_batch = (
                                    instId not in batch_pending_buys
                                    and instId not in batch_active_orders
                                )

                            if instId_not_in_batch:
                                # Check 2h gain filter for batch strategy too
                                should_skip_buy_batch, gain_pct_batch = (
                                    check_2h_gain_filter_func(instId, ref_price)
                                )
                                if not should_skip_buy_batch:
                                    # Register batch buy signal (will trigger first batch immediately)
                                    # register_buy_signal uses its own RLock, safe to call outside main lock
                                    if batch_strategy.register_buy_signal(
                                        instId, limit_price
                                    ):
                                        with lock:
                                            batch_pending_buys[instId] = True
                                        logger.warning(
                                            f"📝 BATCH BUY SIGNAL REGISTERED: {instId}, "
                                            f"limit={limit_price:.6f}, batches=30/30/40 USDT"
                                        )
                                        # Trigger first batch immediately
                                        # ✅ FIX: Removed manual thread scheduling to avoid thread storm
                                        # Batch strategy's get_next_batch() already checks time delays
                                        # Subsequent batches will be triggered automatically when time is ready
                                        if thread_pool:
                                            thread_pool.submit(
                                                process_batch_buy_signal_func,
                                                instId,
                                                limit_price,
                                            )
                                        else:
                                            import threading

                                            threading.Thread(
                                                target=process_batch_buy_signal_func,
                                                args=(instId, limit_price),
                                                daemon=True,
                                            ).start()

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
    active_orders: dict,
    stable_active_orders: dict,
    batch_active_orders: dict,
    lock: threading.Lock,
    process_sell_signal_func,
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

                        with lock:
                            now = datetime.now()

                            # Check original strategy orders
                            if instId in active_orders:
                                order_info = active_orders[instId]
                                next_hour_close = order_info.get("next_hour_close_time")

                                # High: Check next_hour_close_time before selling
                                # Medium: Block if next_hour_close_time is missing
                                if not next_hour_close:
                                    logger.warning(
                                        f"🚫 {instId} KLINE CONFIRMED but missing next_hour_close_time, "
                                        f"blocking sell to prevent premature sale"
                                    )
                                elif now < next_hour_close:
                                    logger.debug(
                                        f"⏸️ {instId} KLINE CONFIRMED but not ready to sell yet: "
                                        f"now={now.strftime('%H:%M:%S')}, "
                                        f"sell_time={next_hour_close.strftime('%H:%M:%S')}"
                                    )
                                elif order_info.get("sell_triggered", False):
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

                            # Check stable strategy orders
                            if instId in stable_active_orders:
                                order_info = stable_active_orders[instId]
                                next_hour_close = order_info.get("next_hour_close_time")

                                if not next_hour_close:
                                    logger.warning(
                                        f"🚫 {instId} KLINE CONFIRMED but missing next_hour_close_time (stable), "
                                        f"blocking sell to prevent premature sale"
                                    )
                                elif now < next_hour_close:
                                    logger.debug(
                                        f"⏸️ {instId} KLINE CONFIRMED but not ready to sell yet (stable): "
                                        f"now={now.strftime('%H:%M:%S')}, "
                                        f"sell_time={next_hour_close.strftime('%H:%M:%S')}"
                                    )
                                elif order_info.get("sell_triggered", False):
                                    logger.debug(
                                        f"⚠️ Stable sell already triggered for {instId}, skipping duplicate candle confirm"
                                    )
                                else:
                                    stable_active_orders[instId][
                                        "sell_triggered"
                                    ] = True
                                    close_price = (
                                        float(candle_data[4])
                                        if len(candle_data) > 4
                                        else 0
                                    )
                                    logger.warning(
                                        f"🕐 KLINE CONFIRMED: {instId}, "
                                        f"close_price={close_price:.6f}, trigger SELL (stable)"
                                    )
                                    # ✅ FIX: Use process_sell_signal_func for stable orders too (each order is independent)
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

                            # Check batch strategy orders
                            if instId in batch_active_orders:
                                order_info = batch_active_orders[instId]
                                next_hour_close = order_info.get("next_hour_close_time")

                                if not next_hour_close:
                                    logger.warning(
                                        f"🚫 {instId} KLINE CONFIRMED but missing next_hour_close_time (batch), "
                                        f"blocking sell to prevent premature sale"
                                    )
                                elif now < next_hour_close:
                                    logger.debug(
                                        f"⏸️ {instId} KLINE CONFIRMED but not ready to sell yet (batch): "
                                        f"now={now.strftime('%H:%M:%S')}, "
                                        f"sell_time={next_hour_close.strftime('%H:%M:%S')}"
                                    )
                                elif order_info.get("sell_triggered", False):
                                    logger.debug(
                                        f"⚠️ Batch sell already triggered for {instId}, skipping duplicate candle confirm"
                                    )
                                else:
                                    batch_active_orders[instId]["sell_triggered"] = True
                                    close_price = (
                                        float(candle_data[4])
                                        if len(candle_data) > 4
                                        else 0
                                    )
                                    logger.warning(
                                        f"🕐 KLINE CONFIRMED: {instId}, "
                                        f"close_price={close_price:.6f}, trigger SELL (batch)"
                                    )
                                    # ✅ FIX: Use process_sell_signal_func for batch orders too (each order is independent)
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

    except Exception as e:
        logger.error(f"Candle message error: {msg_string}, {e}")
