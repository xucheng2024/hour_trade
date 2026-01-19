#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vercel API - Simplified Version (API Only)
前后端分离版本：只提供JSON API，HTML由前端处理
"""

import json
import os
import time
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler

import psycopg2
import psycopg2.extras

# Configuration
STRATEGY_NAME = "hourly_limit_ws"
MOMENTUM_STRATEGY_NAME = "momentum_volume_exhaustion"
CACHE_TTL = 15
_cache = {"data": None, "timestamp": 0}


def get_db_connection():
    """Get database connection"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found")
    return psycopg2.connect(database_url)


def get_trading_records():
    """Get trading records from database with caching"""
    current_time = time.time()

    # Check cache
    if _cache["data"] and (current_time - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    print("[Cache Miss] Querying database...")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT instId, ordId, create_time, state,
               price, size, sell_time, side, sell_price, flag
        FROM orders
        WHERE flag IN (%s, %s)
        ORDER BY create_time DESC
        LIMIT 500
    """,
        (STRATEGY_NAME, MOMENTUM_STRATEGY_NAME),
    )

    rows = cur.fetchall()

    # Process data - separate by strategy
    cryptos = defaultdict(
        lambda: {
            "trades": [],
            "profit": 0.0,
            "profit_pct": 0.0,
            "buy_amount": 0.0,
            "sell_amount": 0.0,
            "strategies": {
                STRATEGY_NAME: {
                    "trades": [],
                    "profit": 0.0,
                    "profit_pct": 0.0,
                    "buy_amount": 0.0,
                    "sell_amount": 0.0,
                },
                MOMENTUM_STRATEGY_NAME: {
                    "trades": [],
                    "profit": 0.0,
                    "profit_pct": 0.0,
                    "buy_amount": 0.0,
                    "sell_amount": 0.0,
                },
            },
        }
    )

    def fmt_time(ts):
        return (
            datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if ts
            else None
        )

    for row in rows:
        inst_id = row["instid"]
        buy_price = float(row["price"] or 0)
        sell_price = float(row.get("sell_price") or 0)
        size = float(row["size"] or 0)
        state = row["state"] or "active"
        strategy_flag = row.get("flag") or STRATEGY_NAME

        # Calculate profit/loss for this trade
        trade_profit = 0.0
        trade_profit_pct = 0.0
        if buy_price > 0 and sell_price > 0 and size > 0:
            trade_profit = (sell_price - buy_price) * size
            trade_profit_pct = ((sell_price - buy_price) / buy_price) * 100

        trade = {
            "ordId": row["ordid"],
            "buy_time": fmt_time(row["create_time"]),
            "sell_time": fmt_time(row.get("sell_time")),
            "side": row["side"],
            "price": buy_price,
            "sell_price": sell_price,
            "size": size,
            "amount": buy_price * size if buy_price > 0 and size > 0 else 0.0,
            "state": state,
            "profit": trade_profit,
            "profit_pct": trade_profit_pct,
            "strategy": strategy_flag,
        }

        cryptos[inst_id]["trades"].append(trade)

        # Update strategy-specific data
        # ✅ FIX: Only process buy orders for profit calculation
        # Sell orders should not be counted separately
        # (they're already in buy order's sell_price)
        if strategy_flag in cryptos[inst_id]["strategies"]:
            strategy_data = cryptos[inst_id]["strategies"][strategy_flag]
            strategy_data["trades"].append(trade)
            # Only count buy orders for profit calculation
            if trade["side"] == "buy":
                strategy_data["buy_amount"] += trade["amount"]
                # Only count sell_amount if order was actually sold
                # (state == "sold out")
                # This ensures we don't count sell_price from orders
                # that weren't actually sold
                if state == "sold out" and sell_price > 0 and size > 0:
                    strategy_data["sell_amount"] += sell_price * size

        # Update overall data
        # ✅ FIX: Only process buy orders for profit calculation
        if trade["side"] == "buy":
            cryptos[inst_id]["buy_amount"] += trade["amount"]
            # Only count sell_amount if order was actually sold
            # (state == "sold out")
            if state == "sold out" and sell_price > 0 and size > 0:
                cryptos[inst_id]["sell_amount"] += sell_price * size

    # Calculate profit
    for inst_id, data in cryptos.items():
        profit = data["sell_amount"] - data["buy_amount"]
        data["profit"] = profit
        if data["buy_amount"] > 0:
            data["profit_pct"] = (profit / data["buy_amount"]) * 100
        data["trades"].sort(key=lambda x: x["buy_time"], reverse=True)

        # Calculate profit for each strategy
        for strategy_name, strategy_data in data["strategies"].items():
            strategy_profit = strategy_data["sell_amount"] - strategy_data["buy_amount"]
            strategy_data["profit"] = strategy_profit
            if strategy_data["buy_amount"] > 0:
                strategy_data["profit_pct"] = (
                    strategy_profit / strategy_data["buy_amount"]
                ) * 100
            strategy_data["trades"].sort(key=lambda x: x["buy_time"], reverse=True)

    result = dict(cryptos)
    _cache["data"] = result
    _cache["timestamp"] = current_time

    cur.close()
    conn.close()

    return result


class handler(BaseHTTPRequestHandler):
    """Vercel handler - API only"""

    def do_GET(self):
        try:
            path = self.path.split("?")[0]

            # API endpoints
            if path == "/api/orders":
                cryptos = get_trading_records()

                # Calculate strategy totals
                original_profit = sum(
                    d["strategies"][STRATEGY_NAME]["profit"] for d in cryptos.values()
                )
                momentum_profit = sum(
                    d["strategies"][MOMENTUM_STRATEGY_NAME]["profit"]
                    for d in cryptos.values()
                )

                response = {
                    "success": True,
                    "data": {
                        "total_cryptos": len(cryptos),
                        "total_trades": sum(len(d["trades"]) for d in cryptos.values()),
                        "total_profit": sum(d["profit"] for d in cryptos.values()),
                        "strategies": {
                            STRATEGY_NAME: {
                                "profit": original_profit,
                                "trades": sum(
                                    len(d["strategies"][STRATEGY_NAME]["trades"])
                                    for d in cryptos.values()
                                ),
                            },
                            MOMENTUM_STRATEGY_NAME: {
                                "profit": momentum_profit,
                                "trades": sum(
                                    len(
                                        d["strategies"][MOMENTUM_STRATEGY_NAME][
                                            "trades"
                                        ]
                                    )
                                    for d in cryptos.values()
                                ),
                            },
                        },
                        "cryptos": cryptos,
                    },
                }

                body = json.dumps(response, default=str, separators=(",", ":"))

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=15")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            elif path == "/api/health":
                response = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "service": "hour-trade-api",
                    "cache_age": (
                        int(time.time() - _cache["timestamp"])
                        if _cache["timestamp"] > 0
                        else 0
                    ),
                }

                body = json.dumps(response, separators=(",", ":"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            # Frontend - serve static HTML
            elif path == "/" or path == "":
                # Read HTML from file - no escaping needed!
                html_path = os.path.join(os.path.dirname(__file__), "index.html")
                try:
                    with open(html_path, "r", encoding="utf-8") as f:
                        html = f.read()

                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "public, max-age=300")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                except FileNotFoundError:
                    # Fallback minimal HTML
                    html = """<!DOCTYPE html>
<html>
<head><title>Trading Records</title></head>
<body>
    <h1>Trading Records</h1>
    <p>API: <a href="/api/orders">/api/orders</a></p>
    <p>Health: <a href="/api/health">/api/health</a></p>
</body>
</html>"""
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))

            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback

            traceback.print_exc()

            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
