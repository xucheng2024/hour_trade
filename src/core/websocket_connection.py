#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket Connection Management
Handles WebSocket connection, subscription, and reconnection
"""

import json
import logging
import threading
import time

import websocket

logger = logging.getLogger(__name__)


def ticker_open(ws, crypto_limits: dict):
    """Handle ticker WebSocket connection open"""
    logger.warning("Ticker WebSocket opened")
    symbols = list(crypto_limits.keys())
    if symbols:
        batch_size = 100
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            msg = {
                "op": "subscribe",
                "args": [{"channel": "tickers", "instId": instId} for instId in batch],
            }
            ws.send(json.dumps(msg))
            time.sleep(0.1)
        logger.warning(f"Subscribed to {len(symbols)} tickers")
    else:
        logger.error("No symbols to subscribe!")


def candle_open(ws, crypto_limits: dict):
    """Handle candle WebSocket connection open"""
    logger.warning("Candle WebSocket opened")
    symbols = list(crypto_limits.keys())
    if symbols:
        msg = {
            "op": "subscribe",
            "args": [{"channel": "candle1H", "instId": instId} for instId in symbols],
        }
        ws.send(json.dumps(msg))
        logger.warning(f"Subscribed to {len(symbols)} 1H candles")
    else:
        logger.error("No symbols to subscribe!")


def connect_websocket(
    url: str,
    on_message,
    on_open,
    ws_type: str,
    ticker_ws_ref: dict,
    candle_ws_ref: dict,
    ws_lock: threading.Lock,
):
    """Connect to WebSocket with reconnection logic and exponential backoff"""
    import os

    # Environment-configurable reconnection parameters
    initial_delay = float(os.getenv("WS_RECONNECT_INITIAL_DELAY", "1.0"))
    max_delay = float(
        os.getenv("WS_RECONNECT_MAX_DELAY", "300")
    )  # Increased from 60 to 300 (5 min)
    backoff_multiplier = float(os.getenv("WS_RECONNECT_BACKOFF_MULTIPLIER", "2.0"))
    min_stable_time = float(
        os.getenv("WS_MIN_STABLE_TIME", "60.0")
    )  # Minimum stable time before resetting delay

    reconnect_delay = initial_delay
    last_successful_connect = None

    while True:
        try:

            def on_close_handler(ws, close_status_code=None, close_msg=None):
                """Handle WebSocket close event"""
                with ws_lock:
                    if ws_type == "ticker":
                        ticker_ws_ref["ws"] = None
                    elif ws_type == "candle":
                        candle_ws_ref["ws"] = None

                if close_status_code is not None:
                    logger.warning(
                        f"WebSocket closed: code={close_status_code}, msg={close_msg}"
                    )
                else:
                    logger.warning("WebSocket closed")

            ws = websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_error=lambda ws, error: logger.warning(f"WebSocket error: {error}"),
                on_close=on_close_handler,
                on_open=on_open,
            )

            with ws_lock:
                if ws_type == "ticker":
                    ticker_ws_ref["ws"] = ws
                elif ws_type == "candle":
                    candle_ws_ref["ws"] = ws

            def send_ping(ws):
                while True:
                    time.sleep(20)
                    try:
                        ws.send("ping")
                    except Exception:
                        break

            ping_thread = threading.Thread(target=send_ping, args=(ws,), daemon=True)
            ping_thread.start()

            # Track successful connection time
            last_successful_connect = time.time()
            reconnect_delay = initial_delay  # Reset delay on successful connection
            ws.run_forever()

        except KeyboardInterrupt:
            logger.warning("WebSocket connection interrupted by user")
            raise
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")

            # Reset delay if connection was stable for min_stable_time
            if last_successful_connect:
                stable_duration = time.time() - last_successful_connect
                if stable_duration >= min_stable_time:
                    reconnect_delay = initial_delay
                    logger.info(
                        f"Connection was stable for {stable_duration:.1f}s, resetting delay"
                    )

            logger.warning(f"Retrying in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * backoff_multiplier, max_delay)
