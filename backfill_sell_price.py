#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill missing sell_price for sold orders.

Strategy:
1) If sell_order_id exists -> use TradeAPI.get_order avgPx/fillPx
2) Else if sell_time exists -> use MarketAPI candlestick close (approx)
3) Optional final fallback -> ticker last price (approx)
"""

import argparse
import logging
import os
import sys
import time

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from core.okx_functions import get_market_api, get_trade_api  # noqa: E402
from utils.db_connection import get_database_connection  # noqa: E402


def fetch_price_from_order(trade_api, inst_id, sell_order_id):
    """Fetch avgPx/fillPx from order details."""
    try:
        result = trade_api.get_order(instId=inst_id, ordId=sell_order_id)
        if result.get("code") == "0" and result.get("data"):
            info = result["data"][0]
            avg_px = info.get("avgPx") or info.get("fillPx")
            if avg_px:
                return float(avg_px), "sell_order"
    except Exception as e:
        logging.warning(
            "get_order failed: instId=%s sell_order_id=%s err=%s",
            inst_id,
            sell_order_id,
            e,
        )
    return None, "sell_order_failed"


def fetch_price_from_candle(market_api, inst_id, sell_time_ms, bar):
    """Fetch candlestick close price near sell_time (approx)."""
    try:
        result = market_api.get_candlesticks(
            instId=inst_id,
            bar=bar,
            limit="1",
            after=str(sell_time_ms),
        )
        if result.get("code") == "0" and result.get("data"):
            candle = result["data"][0]
            # Format: [ts, open, high, low, close, volume, ...]
            close_px = candle[4]
            if close_px:
                return float(close_px), f"candle_{bar}"
    except Exception as e:
        logging.warning(
            "get_candlesticks failed: instId=%s sell_time=%s err=%s",
            inst_id,
            sell_time_ms,
            e,
        )
    return None, "candle_failed"


def fetch_price_from_ticker(market_api, inst_id):
    """Fetch last ticker price (approx)."""
    try:
        result = market_api.get_ticker(instId=inst_id)
        if result.get("code") == "0" and result.get("data"):
            last_px = result["data"][0].get("last", "")
            if last_px:
                return float(last_px), "ticker"
    except Exception as e:
        logging.warning("get_ticker failed: instId=%s err=%s", inst_id, e)
    return None, "ticker_failed"


def main():
    parser = argparse.ArgumentParser(description="Backfill missing sell_price")
    parser.add_argument("--limit", type=int, default=50, help="Max rows to update")
    parser.add_argument("--bar", type=str, default="1m", help="Candle bar size")
    parser.add_argument("--dry-run", action="store_true", help="Do not update DB")
    parser.add_argument(
        "--use-ticker-fallback",
        action="store_true",
        help="Use ticker price if candle/order unavailable",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    trade_api = get_trade_api(simulation_mode=False)
    market_api = get_market_api()

    if trade_api is None:
        logging.error("TradeAPI not initialized. Check OKX API credentials.")
        sys.exit(1)

    conn = get_database_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, instId, ordId, sell_order_id, sell_time
        FROM orders
        WHERE state = 'sold out'
          AND (sell_price IS NULL OR sell_price = '' OR sell_price = '0')
        ORDER BY sell_time DESC NULLS LAST, create_time DESC
        LIMIT %s
        """,
        (args.limit,),
    )

    rows = cur.fetchall()
    if not rows:
        logging.info("No rows to backfill.")
        cur.close()
        conn.close()
        return

    updated = 0
    for row in rows:
        order_id = row[0]
        inst_id = row[1]
        buy_ord_id = row[2]
        sell_order_id = row[3]
        sell_time = row[4]

        price = None
        source = "none"

        # 1) Try sell_order_id
        if sell_order_id:
            price, source = fetch_price_from_order(trade_api, inst_id, sell_order_id)

        # 2) Try candle close near sell_time
        if price is None and sell_time:
            price, source = fetch_price_from_candle(
                market_api, inst_id, sell_time, args.bar
            )

        # 3) Ticker fallback
        if price is None and args.use_ticker_fallback:
            price, source = fetch_price_from_ticker(market_api, inst_id)

        if price is None or price <= 0:
            logging.warning(
                "Skip: id=%s instId=%s ordId=%s (no price, source=%s)",
                order_id,
                inst_id,
                buy_ord_id,
                source,
            )
            continue

        if args.dry_run:
            logging.info(
                "DRY-RUN: id=%s instId=%s ordId=%s sell_price=%.8f source=%s",
                order_id,
                inst_id,
                buy_ord_id,
                price,
                source,
            )
        else:
            cur.execute(
                "UPDATE orders SET sell_price = %s WHERE id = %s",
                (str(price), order_id),
            )
            conn.commit()
            updated += 1
            logging.info(
                "UPDATED: id=%s instId=%s ordId=%s sell_price=%.8f source=%s",
                order_id,
                inst_id,
                buy_ord_id,
                price,
                source,
            )

        time.sleep(0.1)  # Rate limiting

    cur.close()
    conn.close()
    logging.info("Done. Updated %s rows.", updated)


if __name__ == "__main__":
    main()
