#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trading Records Web Viewer
Display trading records grouped by cryptocurrency with profit calculation
"""

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import psycopg
from dotenv import load_dotenv
from flask import Flask, render_template_string
from psycopg.rows import dict_row

# Load environment variables
load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

STRATEGY_NAME = "hourly_limit_ws"

# Simple in-memory cache (TTL: 5 seconds)
_cache_data = None
_cache_timestamp = 0
CACHE_TTL = 5  # seconds


def get_db_connection():
    """Get PostgreSQL database connection"""
    return psycopg.connect(DATABASE_URL)


HTML_TEMPLATE = """  # noqa: E501
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Records</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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

        .trade-buy { color: #10b981; font-weight: 600; }
        .trade-sell { color: #ef4444; font-weight: 600; }

        .trade-state {
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .state-sold { background: #d1fae5; color: #065f46; }
        .state-active { background: #fef3c7; color: #92400e; }

        .trades-table tbody tr.row-latest {
            background: #d1fae5;
            border-left: 3px solid #10b981;
        }

        .trades-table tbody tr.row-latest:hover {
            background: #a7f3d0;
        }

        @media (max-width: 768px) {
            body { padding: 12px; }
            .summary { grid-template-columns: 1fr; }
            .crypto-header { flex-direction: column; align-items: flex-start; gap: 8px; }
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
                <div class="summary-value">{{ total_cryptos }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Trades</div>
                <div class="summary-value">{{ total_trades }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Profit</div>
                <div class="summary-value {{ 'profit-positive' if total_profit > 0 else 'profit-negative' if total_profit < 0 else '' }}">
                    {{ "%.2f"|format(total_profit) }} USDT
                </div>
            </div>
        </div>

        {% for crypto, data in cryptos.items() %}
        <div class="crypto-section">
            <div class="crypto-header">
                <div class="crypto-name">{{ crypto }}</div>
                <div class="crypto-profit {{ 'profit-positive' if data.profit > 0 else 'profit-negative' if data.profit < 0 else 'profit-zero' }}">
                    {{ "%.2f"|format(data.profit) }} USDT ({{ "%.2f"|format(data.profit_pct) }}%)
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
                        <th>State</th>
                    </tr>
                </thead>
                <tbody>
                    {% for trade in data.trades %}
                    <tr {% if trade.is_latest %}class="row-latest"{% endif %}>
                        <td>
                            {% if trade.state == 'sold out' and trade.sell_time %}
                                {{ trade.sell_time }}
                            {% else %}
                                {{ trade.buy_time }}
                            {% endif %}
                        </td>
                        <td class="trade-{{ trade.side }}">{{ trade.side|upper }}</td>
                        <td>{{ trade.price }}</td>
                        <td>{{ trade.size }}</td>
                        <td>{{ "%.2f"|format(trade.amount) }}</td>
                        <td>
                            <span class="trade-state state-{{ trade.state_class }}">
                                {{ trade.state }}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


def get_trading_records():
    """Get trading records from database grouped by cryptocurrency"""
    global _cache_data, _cache_timestamp

    # Check cache
    current_time = time.time()
    if _cache_data is not None and (current_time - _cache_timestamp) < CACHE_TTL:
        age = current_time - _cache_timestamp
        print(f"[Cache Hit] Returning cached data (age: {age:.1f}s)")
        return _cache_data

    print("[Cache Miss] Querying database...")
    query_start = time.time()

    conn = get_db_connection()
    cur = conn.cursor(row_factory=dict_row)

    try:
        # Get all orders for this strategy (including sell_price)
        # Use LIKE to match both 'hourly_limit_ws' and 'hourly_limit_ws_test'
        # Add LIMIT to improve performance
        cur.execute(
            """
            SELECT instId, ordId, create_time, orderType, state, price, size,
                   sell_time, side, sell_price
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

        # Group by cryptocurrency
        cryptos = defaultdict(
            lambda: {
                "trades": [],
                "profit": 0.0,
                "profit_pct": 0.0,
                "buy_amount": 0.0,
                "sell_amount": 0.0,
            }
        )

        # Optimize timestamp formatting - define format function once
        def format_time(ts):
            if ts:
                # Convert to UTC datetime first
                utc_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                # Convert to Singapore time (UTC+8)
                sgt_tz = timezone(timedelta(hours=8))
                sgt_dt = utc_dt.astimezone(sgt_tz)
                return sgt_dt.strftime("%Y-%m-%d %H:%M:%S")
            return None

        process_start = time.time()
        for row in rows:
            instId = row["instid"]
            buy_price = float(row["price"]) if row["price"] else 0.0
            sell_price = float(row["sell_price"]) if row.get("sell_price") else 0.0
            size = float(row["size"]) if row["size"] else 0.0
            state = row["state"] if row["state"] else "active"

            # Optimize timestamp conversions - only convert once
            create_time_ts = row["create_time"]
            sell_time_ts = row.get("sell_time")
            buy_time_str = format_time(create_time_ts)

            # Display sell time if sold, otherwise buy time
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

            # Calculate amount based on buy price
            if buy_price > 0 and size > 0:
                trade["amount"] = buy_price * size
            else:
                trade["amount"] = 0.0

            cryptos[instId]["trades"].append(trade)

            # Calculate profit using sell_price from the same buy order
            if trade["side"] == "buy":
                cryptos[instId]["buy_amount"] += trade["amount"]
                # If sell_price exists, calculate sell amount
                if sell_price > 0 and size > 0:
                    sell_amount = sell_price * size
                    cryptos[instId]["sell_amount"] += sell_amount

        # Calculate profit for each crypto
        for instId, data in cryptos.items():
            total_buy_amount = data["buy_amount"]
            total_sell_amount = data["sell_amount"]
            total_profit = total_sell_amount - total_buy_amount

            data["profit"] = total_profit
            if total_buy_amount > 0:
                data["profit_pct"] = (total_profit / total_buy_amount) * 100

            # Sort trades by time
            data["trades"].sort(key=lambda x: x["time"], reverse=True)

            # Mark the latest (first) trade
            if data["trades"]:
                data["trades"][0]["is_latest"] = True

        result = dict(cryptos)
        print(f"[Process Time] Processed data in {time.time() - process_start:.2f}s")
        print(f"[Total Time] {time.time() - query_start:.2f}s")

        # Update cache
        _cache_data = result
        _cache_timestamp = time.time()

        return result
    finally:
        cur.close()
        conn.close()


@app.route("/")
def index():
    """Display trading records"""
    cryptos = get_trading_records()

    # Calculate totals
    total_cryptos = len(cryptos)
    total_trades = sum(len(data["trades"]) for data in cryptos.values())
    total_profit = sum(data["profit"] for data in cryptos.values())

    return render_template_string(
        HTML_TEMPLATE,
        strategy_name=STRATEGY_NAME,
        cryptos=cryptos,
        total_cryptos=total_cryptos,
        total_trades=total_trades,
        total_profit=total_profit,
    )


if __name__ == "__main__":
    print("Starting trading records viewer...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host="0.0.0.0", port=5000)
