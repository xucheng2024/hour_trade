#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vercel API - Trading Records Viewer (Native Python HTTP Handler)
"""

import json
import os
import time
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler

import psycopg2
import psycopg2.extras

STRATEGY_NAME = "hourly_limit_ws"

# Simple in-memory cache (TTL: 5 seconds)
_cache_data = None
_cache_timestamp = 0
CACHE_TTL = 5  # seconds

# HTML Template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Records</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont,
                'Segoe UI', Roboto, sans-serif;
            background: #fafafa;
            color: #1a1a1a;
            line-height: 1.5;
            padding: 16px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            font-size: 18px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 16px;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 16px;
        }
        .summary-item {
            background: #fff;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #e5e5e5;
        }
        .summary-label {
            font-size: 11px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        .summary-value {
            font-size: 20px;
            font-weight: 600;
            color: #1a1a1a;
        }
        .summary-value.profit-positive { color: #10b981; }
        .summary-value.profit-negative { color: #ef4444; }
        .crypto-section {
            background: #fff;
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            margin-bottom: 12px;
            overflow: hidden;
        }
        .crypto-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid #e5e5e5;
            background: #fafafa;
        }
        .crypto-name {
            font-size: 14px;
            font-weight: 600;
            color: #1a1a1a;
        }
        .crypto-profit {
            font-size: 14px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
        }
        .profit-positive { color: #10b981; background: #d1fae5; }
        .profit-negative { color: #ef4444; background: #fee2e2; }
        .profit-zero { color: #666; background: #f3f4f6; }
        .trades-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        .trades-table th {
            background: #fafafa;
            color: #666;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 8px 16px;
            text-align: left;
            border-bottom: 1px solid #e5e5e5;
        }
        .trades-table td {
            padding: 10px 16px;
            border-bottom: 1px solid #f0f0f0;
            color: #1a1a1a;
        }
        .trades-table tbody tr:hover {
            background: #fafafa;
        }
        .trades-table tbody tr:last-child td {
            border-bottom: none;
        }
        .side-buy { color: #10b981; font-weight: 600; }
        .side-sell { color: #ef4444; font-weight: 600; }
        .status-badge {
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .status-active { background: #fef3c7; color: #92400e; }
        .status-sold { background: #d1fae5; color: #065f46; }
        .trades-table tbody tr.row-latest {
            background: #d1fae5;
            border-left: 3px solid #10b981;
        }
        .trades-table tbody tr.row-latest:hover {
            background: #a7f3d0;
        }
        .error {
            background: #fff;
            text-align: center;
            padding: 40px 30px;
            border-radius: 6px;
            border: 1px solid #e5e5e5;
        }
        .error h3 {
            font-size: 18px;
            margin-bottom: 8px;
            color: #1a1a1a;
        }
        .error p {
            color: #666;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .error code {
            background: #f5f5f5;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: Monaco, monospace;
            color: #1a1a1a;
            font-size: 12px;
        }
        @media (max-width: 768px) {
            body { padding: 12px; }
            .summary { grid-template-columns: 1fr; }
            .crypto-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }
            .trades-table th, .trades-table td { padding: 8px 12px; font-size: 12px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Records</h1>
        <div class="summary">
            <div class="summary-item">
                <div class="summary-label">Cryptos</div>
                <div class="summary-value">{total_cryptos}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Trades</div>
                <div class="summary-value">{total_trades}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Profit</div>
                <div class="summary-value {profit_class}">{total_profit}</div>
            </div>
        </div>
        {crypto_sections}
    </div>
</body>
</html>"""


def get_database_connection():
    """Get PostgreSQL database connection"""
    try:
        database_url = os.getenv("DATABASE_URL")

        if not database_url:
            error_msg = "DATABASE_URL environment variable is required"
            print(f"[ERROR] {error_msg}")
            raise ValueError(error_msg)

        if not database_url.startswith("postgresql://"):
            error_msg = "DATABASE_URL must be a PostgreSQL connection string"
            print(f"[ERROR] {error_msg}")
            raise ValueError(error_msg)

        print("[DB] Connecting to database...")
        conn = psycopg2.connect(database_url)
        print("[DB] Connection successful")
        return conn
    except Exception as e:
        print(f"[DB ERROR] Failed to connect: {e}")
        import traceback

        traceback.print_exc()
        raise


def get_trading_records():
    """Get trading records from PostgreSQL database"""
    global _cache_data, _cache_timestamp

    try:
        # Check cache
        current_time = time.time()
        if _cache_data is not None and (current_time - _cache_timestamp) < CACHE_TTL:
            age = current_time - _cache_timestamp
            print(f"[Cache Hit] Returning cached data (age: {age:.1f}s)")
            return _cache_data

        print("[Cache Miss] Querying database...")
        query_start = time.time()
    except Exception as e:
        print(f"[Cache Error] {e}, continuing with fresh query...")
        query_start = time.time()

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT instId, ordId, create_time, orderType, state,
                   price, size, sell_time, side, sell_price
            FROM orders
            WHERE flag LIKE %s
            ORDER BY create_time DESC
            LIMIT 1000
        """,
            (f"{STRATEGY_NAME}%",),
        )

        rows = cur.fetchall()
        print(
            f"[Query Time] Fetched {len(rows)} rows in {time.time() - query_start:.2f}s"
        )

        cryptos = defaultdict(
            lambda: {
                "trades": [],
                "profit": 0.0,
                "profit_pct": 0.0,
                "buy_amount": 0.0,
                "sell_amount": 0.0,
            }
        )

        # Optimize timestamp formatting
        def format_time(ts):
            if ts:
                return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
            return None

        process_start = time.time()
        for row in rows:
            instId = row["instid"]
            buy_price = float(row["price"]) if row["price"] else 0.0
            sell_price = float(row["sell_price"]) if row.get("sell_price") else 0.0
            size = float(row["size"]) if row["size"] else 0.0
            state = row["state"] if row["state"] else "active"

            create_time_ts = row["create_time"]
            sell_time_ts = row.get("sell_time")
            buy_time_str = format_time(create_time_ts)

            if state == "sold out" and sell_time_ts:
                display_time = format_time(sell_time_ts)
            else:
                display_time = buy_time_str

            trade = {
                "ordId": row["ordid"],
                "time": display_time,
                "buy_time": buy_time_str,
                "sell_time": format_time(sell_time_ts),
                "side": row["side"],
                "price": buy_price,
                "sell_price": sell_price,
                "size": size,
                "state": state,
                "state_class": "sold" if state == "sold out" else "active",
            }

            if buy_price > 0 and size > 0:
                trade["amount"] = buy_price * size
            else:
                trade["amount"] = 0.0

            cryptos[instId]["trades"].append(trade)

            if trade["side"] == "buy":
                cryptos[instId]["buy_amount"] += trade["amount"]
                if sell_price > 0 and size > 0:
                    sell_amount = sell_price * size
                    cryptos[instId]["sell_amount"] += sell_amount

        for instId, data in cryptos.items():
            total_buy_amount = data["buy_amount"]
            total_sell_amount = data["sell_amount"]
            total_profit = total_sell_amount - total_buy_amount
            data["profit"] = total_profit
            if total_buy_amount > 0:
                data["profit_pct"] = (total_profit / total_buy_amount) * 100
            data["trades"].sort(key=lambda x: x["time"], reverse=True)

            if data["trades"]:
                data["trades"][0]["is_latest"] = True

        result = dict(cryptos)
        print(f"[Process Time] Processed data in {time.time() - process_start:.2f}s")
        print(f"[Total Time] {time.time() - query_start:.2f}s")

        try:
            global _cache_data, _cache_timestamp
            _cache_data = result
            _cache_timestamp = time.time()
        except Exception as cache_err:
            print(f"[Cache Update Warning] {cache_err}")

        cur.close()
        conn.close()

        return result
    except Exception as e:
        print(f"Database error: {e}")
        import traceback

        traceback.print_exc()
        return {}


def render_html(cryptos):
    """Render HTML template with data"""
    total_cryptos = len(cryptos)
    total_trades = sum(len(data["trades"]) for data in cryptos.values())
    total_profit = sum(data["profit"] for data in cryptos.values())

    profit_class = ""
    if total_profit > 0:
        profit_class = "profit-positive"
    elif total_profit < 0:
        profit_class = "profit-negative"

    profit_str = f"{total_profit:.2f} USDT"

    crypto_sections = ""
    if cryptos:
        for crypto, data in cryptos.items():
            profit_pct_str = f"{data['profit_pct']:.2f}%"
            profit_value_str = f"{data['profit']:.2f} USDT ({profit_pct_str})"

            profit_class_crypto = ""
            if data["profit"] > 0:
                profit_class_crypto = "profit-positive"
            elif data["profit"] < 0:
                profit_class_crypto = "profit-negative"
            else:
                profit_class_crypto = "profit-zero"

            trades_html = ""
            for trade in data["trades"]:
                row_class = 'class="row-latest"' if trade.get("is_latest") else ""
                time_str = (
                    trade["sell_time"]
                    if (trade["state"] == "sold out" and trade["sell_time"])
                    else trade["buy_time"]
                )
                side_class = f"side-{trade['side']}"
                status_class = f"status-{trade['state_class']}"

                trades_html += f"""
                    <tr {row_class}>
                        <td>{time_str}</td>
                        <td>
                            <span class="{side_class}">
                                {trade['side'].upper()}
                            </span>
                        </td>
                        <td>{trade['price']:.2f}</td>
                        <td>{trade['size']:.6f}</td>
                        <td>{trade['amount']:.2f}</td>
                        <td>
                            <span class="status-badge {status_class}">
                                {trade['state']}
                            </span>
                        </td>
                    </tr>"""

            crypto_sections += f"""
        <div class="crypto-section">
            <div class="crypto-header">
                <div class="crypto-name">{crypto}</div>
                <div class="crypto-profit {profit_class_crypto}">
                    {profit_value_str}
                </div>
            </div>
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Type</th>
                        <th>Price</th>
                        <th>Size</th>
                        <th>Amount</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {trades_html}
                </tbody>
            </table>
        </div>"""
    else:
        crypto_sections = """
        <div class="error">
            <h3>No Trading Records Found</h3>
            <p>Start the trading bot to generate records:</p>
            <p><code>python websocket_limit_trading.py</code></p>
        </div>"""

    return HTML_TEMPLATE.format(
        total_cryptos=total_cryptos,
        total_trades=total_trades,
        total_profit=profit_str,
        profit_class=profit_class,
        crypto_sections=crypto_sections,
    )


class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless function handler"""

    def do_GET(self):
        """Handle GET requests"""
        path = self.path.split("?")[0]  # Remove query string

        try:
            if path == "/" or path == "":
                # HTML dashboard
                cryptos = get_trading_records()
                html_content = render_html(cryptos)

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))

            elif path == "/api/orders":
                # JSON API
                cryptos = get_trading_records()

                total_cryptos = len(cryptos)
                total_trades = sum(len(data["trades"]) for data in cryptos.values())
                total_profit = sum(data["profit"] for data in cryptos.values())

                response = {
                    "success": True,
                    "data": {
                        "total_cryptos": total_cryptos,
                        "total_trades": total_trades,
                        "total_profit": total_profit,
                        "cryptos": cryptos,
                    },
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(response, default=str).encode("utf-8"))

            elif path == "/api/health":
                # Health check
                response = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "service": "hour-trade-api",
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))

            else:
                # 404 Not Found
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

        except Exception as e:
            print(f"[ERROR] Handler error: {e}")
            import traceback

            traceback.print_exc()

            error_response = json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "message": "Internal server error. Check logs for details.",
                }
            )

            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(error_response.encode("utf-8"))
